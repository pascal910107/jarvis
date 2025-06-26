"""Task queue implementation for distributed processing."""

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 0  # Highest priority
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4  # Lowest priority


@dataclass
class Task:
    """Represents a task in the distributed system."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "generic"
    data: Any = None
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Compare tasks by priority and creation time."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at


class TaskQueue:
    """Thread-safe priority queue for task management."""
    
    def __init__(self, max_size: Optional[int] = None):
        """Initialize the task queue.
        
        Args:
            max_size: Maximum number of tasks in queue (None for unlimited)
        """
        self.max_size = max_size
        self._queue: List[Task] = []
        self._task_map: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._stats = {
            "total_enqueued": 0,
            "total_dequeued": 0,
            "total_rejected": 0,
            "total_expired": 0
        }
        
        logger.info(f"Initialized TaskQueue with max_size={max_size}")
    
    def put(self, task: Task, block: bool = True, timeout: Optional[float] = None) -> bool:
        """Add a task to the queue.
        
        Args:
            task: Task to add
            block: Whether to block if queue is full
            timeout: Timeout in seconds for blocking
            
        Returns:
            True if task was added, False otherwise
        """
        with self._not_full:
            # Check if queue is full
            if self.max_size is not None:
                if not block and len(self._queue) >= self.max_size:
                    self._stats["total_rejected"] += 1
                    return False
                
                end_time = time.time() + timeout if timeout is not None else None
                while len(self._queue) >= self.max_size:
                    remaining = end_time - time.time() if end_time else None
                    if remaining is not None and remaining <= 0:
                        self._stats["total_rejected"] += 1
                        return False
                    if not self._not_full.wait(remaining):
                        self._stats["total_rejected"] += 1
                        return False
            
            # Add task to queue
            heapq.heappush(self._queue, task)
            self._task_map[task.id] = task
            self._stats["total_enqueued"] += 1
            
            # Notify waiting consumers
            self._not_empty.notify()
            
            logger.debug(f"Added task {task.id} to queue (priority={task.priority.name})")
            return True
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Task]:
        """Get the highest priority task from the queue.
        
        Args:
            block: Whether to block if queue is empty
            timeout: Timeout in seconds for blocking
            
        Returns:
            Task if available, None otherwise
        """
        with self._not_empty:
            # Remove expired tasks
            self._remove_expired_tasks()
            
            # Check if queue is empty
            if not block and not self._queue:
                return None
            
            end_time = time.time() + timeout if timeout is not None else None
            while not self._queue:
                remaining = end_time - time.time() if end_time else None
                if remaining is not None and remaining <= 0:
                    return None
                if not self._not_empty.wait(remaining):
                    return None
            
            # Get task from queue
            task = heapq.heappop(self._queue)
            del self._task_map[task.id]
            self._stats["total_dequeued"] += 1
            
            # Notify waiting producers
            self._not_full.notify()
            
            logger.debug(f"Retrieved task {task.id} from queue")
            return task
    
    def peek(self) -> Optional[Task]:
        """Peek at the highest priority task without removing it.
        
        Returns:
            Task if available, None otherwise
        """
        with self._lock:
            self._remove_expired_tasks()
            return self._queue[0] if self._queue else None
    
    def remove(self, task_id: str) -> bool:
        """Remove a specific task from the queue.
        
        Args:
            task_id: ID of task to remove
            
        Returns:
            True if task was removed, False if not found
        """
        with self._lock:
            if task_id not in self._task_map:
                return False
            
            # Remove from heap (expensive operation)
            task = self._task_map[task_id]
            self._queue.remove(task)
            heapq.heapify(self._queue)
            
            # Remove from map
            del self._task_map[task_id]
            
            # Notify waiting producers
            self._not_full.notify()
            
            logger.debug(f"Removed task {task_id} from queue")
            return True
    
    def update_priority(self, task_id: str, new_priority: TaskPriority) -> bool:
        """Update the priority of a task in the queue.
        
        Args:
            task_id: ID of task to update
            new_priority: New priority level
            
        Returns:
            True if task was updated, False if not found
        """
        with self._lock:
            if task_id not in self._task_map:
                return False
            
            # Remove and re-add with new priority
            task = self._task_map[task_id]
            self._queue.remove(task)
            task.priority = new_priority
            heapq.heappush(self._queue, task)
            
            logger.debug(f"Updated task {task_id} priority to {new_priority.name}")
            return True
    
    def size(self) -> int:
        """Get the current size of the queue."""
        with self._lock:
            return len(self._queue)
    
    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        with self._lock:
            return len(self._queue) == 0
    
    def is_full(self) -> bool:
        """Check if the queue is full."""
        with self._lock:
            return self.max_size is not None and len(self._queue) >= self.max_size
    
    def clear(self):
        """Clear all tasks from the queue."""
        with self._lock:
            self._queue.clear()
            self._task_map.clear()
            self._not_full.notify_all()
            logger.info("Cleared all tasks from queue")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics.
        
        Returns:
            Dictionary containing queue statistics
        """
        with self._lock:
            priority_counts = {}
            for task in self._queue:
                priority_name = task.priority.name
                priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1
            
            return {
                "current_size": len(self._queue),
                "max_size": self.max_size,
                "total_enqueued": self._stats["total_enqueued"],
                "total_dequeued": self._stats["total_dequeued"],
                "total_rejected": self._stats["total_rejected"],
                "total_expired": self._stats["total_expired"],
                "priority_distribution": priority_counts
            }
    
    def get_tasks_by_type(self, task_type: str) -> List[Task]:
        """Get all tasks of a specific type.
        
        Args:
            task_type: Type of tasks to retrieve
            
        Returns:
            List of tasks matching the type
        """
        with self._lock:
            return [task for task in self._queue if task.type == task_type]
    
    def _remove_expired_tasks(self):
        """Remove tasks that have passed their deadline."""
        now = datetime.now()
        expired_tasks = []
        
        for task in self._queue:
            if task.deadline and task.deadline < now:
                expired_tasks.append(task)
        
        for task in expired_tasks:
            self._queue.remove(task)
            del self._task_map[task.id]
            self._stats["total_expired"] += 1
            logger.warning(f"Removed expired task {task.id}")
        
        if expired_tasks:
            heapq.heapify(self._queue)