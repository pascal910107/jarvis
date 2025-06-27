"""Task definitions for the scheduling framework."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Set
from threading import RLock

from core.monitoring import get_logger

logger = get_logger(__name__)


class TaskPriority(IntEnum):
    """Task priority levels (higher values = higher priority)."""
    IDLE = 0
    BACKGROUND = 10
    LOW = 20
    NORMAL = 50
    HIGH = 80
    CRITICAL = 90
    REALTIME = 100


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEADLINE_MISSED = "deadline_missed"


@dataclass
class TaskConstraints:
    """Task execution constraints."""
    # Timing constraints
    deadline: Optional[datetime] = None  # Absolute deadline
    max_duration: Optional[timedelta] = None  # Maximum execution time
    min_start_time: Optional[datetime] = None  # Earliest start time
    
    # Resource constraints
    required_resources: Set[str] = field(default_factory=set)
    cpu_cores: int = 1
    memory_mb: int = 0
    gpu_required: bool = False
    
    # Real-time constraints
    is_hard_realtime: bool = False  # Must meet deadline
    is_preemptible: bool = True  # Can be interrupted
    max_latency_ms: Optional[float] = None  # Max scheduling latency
    
    # Dependencies
    depends_on: Set[str] = field(default_factory=set)  # Task IDs
    
    def validate(self) -> List[str]:
        """Validate constraints consistency."""
        errors = []
        
        if self.deadline and self.min_start_time:
            if self.min_start_time >= self.deadline:
                errors.append("min_start_time must be before deadline")
        
        if self.max_duration and self.max_latency_ms:
            total_ms = self.max_duration.total_seconds() * 1000
            if self.max_latency_ms > total_ms:
                errors.append("max_latency_ms exceeds max_duration")
        
        if self.is_hard_realtime and not self.deadline:
            errors.append("hard realtime tasks must have a deadline")
        
        return errors


@dataclass
class TaskMetrics:
    """Runtime metrics for a task."""
    # Timing metrics
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Latency metrics
    scheduling_latency_ms: Optional[float] = None
    execution_time_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    
    # Resource usage
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    
    # Priority tracking
    initial_priority: Optional[int] = None
    effective_priority: Optional[int] = None  # After inheritance
    priority_boosts: int = 0
    
    def calculate_latencies(self):
        """Calculate latency metrics."""
        if self.scheduled_at and self.created_at:
            self.scheduling_latency_ms = (
                self.scheduled_at - self.created_at
            ).total_seconds() * 1000
        
        if self.completed_at and self.started_at:
            self.execution_time_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000
        
        if self.completed_at and self.created_at:
            self.total_latency_ms = (
                self.completed_at - self.created_at
            ).total_seconds() * 1000


class Task:
    """Schedulable task with priority and constraints."""
    
    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        constraints: Optional[TaskConstraints] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.constraints = constraints or TaskConstraints()
        self.metadata = metadata or {}
        
        # Runtime state
        self.status = TaskStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[Exception] = None
        self.metrics = TaskMetrics(initial_priority=priority)
        
        # Priority inheritance
        self._effective_priority = priority
        self._priority_donors: Set[str] = set()  # Tasks that boosted our priority
        self._lock = RLock()
        
        # Validate constraints
        errors = self.constraints.validate()
        if errors:
            raise ValueError(f"Invalid task constraints: {errors}")
        
        logger.debug(f"Created task {self.id}: {name}", 
                    extra={"priority": priority.name})
    
    @property
    def effective_priority(self) -> int:
        """Get effective priority (including inheritance)."""
        with self._lock:
            return self._effective_priority
    
    def boost_priority(self, new_priority: int, donor_id: str) -> bool:
        """Boost priority through inheritance.
        
        Args:
            new_priority: New priority level
            donor_id: ID of task donating priority
            
        Returns:
            True if priority was boosted
        """
        with self._lock:
            if new_priority > self._effective_priority:
                old_priority = self._effective_priority
                self._effective_priority = new_priority
                self._priority_donors.add(donor_id)
                self.metrics.priority_boosts += 1
                self.metrics.effective_priority = new_priority
                
                logger.info(
                    f"Task {self.id} priority boosted",
                    extra={
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                        "donor": donor_id
                    }
                )
                return True
            return False
    
    def release_priority_boost(self, donor_id: str) -> None:
        """Release priority boost from a specific donor."""
        with self._lock:
            if donor_id in self._priority_donors:
                self._priority_donors.remove(donor_id)
                
                # Recalculate effective priority
                if not self._priority_donors:
                    self._effective_priority = self.priority
                    self.metrics.effective_priority = self.priority
                    
                    logger.debug(
                        f"Task {self.id} priority restored to {self.priority}",
                        extra={"released_by": donor_id}
                    )
    
    def is_ready(self) -> bool:
        """Check if task is ready to run."""
        if self.status != TaskStatus.PENDING:
            return False
        
        # Check time constraints
        now = datetime.now()
        if self.constraints.min_start_time and now < self.constraints.min_start_time:
            return False
        
        # Dependencies are checked by scheduler
        return True
    
    def is_deadline_approaching(self, threshold: timedelta) -> bool:
        """Check if deadline is approaching."""
        if not self.constraints.deadline:
            return False
        
        time_remaining = self.constraints.deadline - datetime.now()
        return time_remaining <= threshold
    
    def has_missed_deadline(self) -> bool:
        """Check if task has missed its deadline."""
        if not self.constraints.deadline:
            return False
        
        return datetime.now() > self.constraints.deadline
    
    def can_preempt(self, other: 'Task') -> bool:
        """Check if this task can preempt another task."""
        # Cannot preempt if we're not higher priority
        if self.effective_priority <= other.effective_priority:
            return False
        
        # Cannot preempt non-preemptible tasks
        if not other.constraints.is_preemptible:
            return False
        
        # Real-time tasks can always preempt lower priority
        if self.priority == TaskPriority.REALTIME:
            return True
        
        # Check if preemption is worth it based on deadlines
        if self.constraints.deadline and other.constraints.deadline:
            our_urgency = (self.constraints.deadline - datetime.now()).total_seconds()
            their_urgency = (other.constraints.deadline - datetime.now()).total_seconds()
            
            # Only preempt if we're significantly more urgent
            return our_urgency < their_urgency * 0.8
        
        return True
    
    def execute(self) -> Any:
        """Execute the task function."""
        self.status = TaskStatus.RUNNING
        self.metrics.started_at = datetime.now()
        
        try:
            logger.debug(f"Executing task {self.id}: {self.name}")
            self.result = self.func(*self.args, **self.kwargs)
            self.status = TaskStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Task {self.id} failed: {e}", exc_info=True)
            self.error = e
            self.status = TaskStatus.FAILED
            raise
            
        finally:
            self.metrics.completed_at = datetime.now()
            self.metrics.calculate_latencies()
            
            # Log metrics
            logger.info(
                f"Task {self.id} completed",
                extra={
                    "status": self.status.value,
                    "execution_time_ms": self.metrics.execution_time_ms,
                    "total_latency_ms": self.metrics.total_latency_ms
                }
            )
        
        return self.result
    
    def cancel(self) -> None:
        """Cancel the task."""
        if self.status in [TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED]:
            self.status = TaskStatus.CANCELLED
            logger.info(f"Task {self.id} cancelled")
    
    def __repr__(self) -> str:
        return (
            f"Task(id={self.id[:8]}, name={self.name}, "
            f"priority={self.priority.name}, status={self.status.value})"
        )
    
    def __lt__(self, other: 'Task') -> bool:
        """Compare tasks for priority queue ordering."""
        # Higher priority value = higher priority (comes first)
        if self.effective_priority != other.effective_priority:
            return self.effective_priority > other.effective_priority
        
        # For same priority, earlier deadline comes first
        if self.constraints.deadline and other.constraints.deadline:
            return self.constraints.deadline < other.constraints.deadline
        elif self.constraints.deadline:
            return True  # Tasks with deadlines come before those without
        elif other.constraints.deadline:
            return False
        
        # For same priority and no deadlines, earlier created comes first
        return self.metrics.created_at < other.metrics.created_at