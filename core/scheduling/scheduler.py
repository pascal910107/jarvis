"""Real-time task scheduler with priority inheritance."""

import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, Future

from core.monitoring import get_logger, get_metrics_collector

from .task import Task, TaskStatus, TaskPriority
from .queue import PriorityQueue, DeadlineQueue, MultiLevelQueue
from .monitor import LatencyMonitor
from .exceptions import DeadlineMissedError, PriorityInversionError

logger = get_logger(__name__)
metrics = get_metrics_collector()


class SchedulingPolicy(Enum):
    """Task scheduling policies."""
    PRIORITY = "priority"  # Highest priority first
    DEADLINE = "deadline"  # Earliest deadline first (EDF)
    FAIR = "fair"  # Multi-level feedback queue
    REALTIME = "realtime"  # Real-time with preemption


class PriorityInheritanceProtocol:
    """Implements priority inheritance to prevent priority inversion."""
    
    def __init__(self):
        self._resource_holders: Dict[str, str] = {}  # resource -> task_id
        self._task_resources: Dict[str, Set[str]] = defaultdict(set)  # task_id -> resources
        self._waiting_tasks: Dict[str, List[Tuple[str, Task]]] = defaultdict(list)  # resource -> [(task_id, task)]
        self._lock = threading.RLock()
    
    def acquire_resource(self, task: Task, resource: str) -> bool:
        """Try to acquire a resource for a task."""
        with self._lock:
            holder_id = self._resource_holders.get(resource)
            
            if holder_id is None:
                # Resource is free, acquire it
                self._resource_holders[resource] = task.id
                self._task_resources[task.id].add(resource)
                logger.debug(f"Task {task.id} acquired resource {resource}")
                return True
            
            elif holder_id == task.id:
                # Already own this resource
                return True
            
            else:
                # Resource is held by another task
                self._waiting_tasks[resource].append((task.id, task))
                
                # Check for priority inheritance need
                holder_task = self._get_task_by_id(holder_id)
                if holder_task and task.effective_priority > holder_task.effective_priority:
                    # Boost holder's priority
                    holder_task.boost_priority(task.effective_priority, task.id)
                    logger.info(
                        f"Priority inheritance: task {holder_id} boosted by {task.id}",
                        extra={
                            "resource": resource,
                            "new_priority": task.effective_priority
                        }
                    )
                
                return False
    
    def release_resource(self, task_id: str, resource: str) -> Optional[Task]:
        """Release a resource and return next waiting task."""
        with self._lock:
            if self._resource_holders.get(resource) != task_id:
                return None
            
            # Release the resource
            del self._resource_holders[resource]
            self._task_resources[task_id].discard(resource)
            
            logger.debug(f"Task {task_id} released resource {resource}")
            
            # Find highest priority waiting task
            waiting = self._waiting_tasks.get(resource, [])
            if waiting:
                # Sort by priority
                waiting.sort(key=lambda x: x[1].effective_priority, reverse=True)
                next_task_id, next_task = waiting.pop(0)
                
                # Clean up empty list
                if not waiting:
                    del self._waiting_tasks[resource]
                
                # Release priority boost
                holder_task = self._get_task_by_id(task_id)
                if holder_task:
                    holder_task.release_priority_boost(next_task_id)
                
                return next_task
            
            return None
    
    def release_all_resources(self, task_id: str) -> List[Tuple[str, Task]]:
        """Release all resources held by a task."""
        with self._lock:
            released = []
            resources = list(self._task_resources.get(task_id, []))
            
            for resource in resources:
                next_task = self.release_resource(task_id, resource)
                if next_task:
                    released.append((resource, next_task))
            
            # Clean up task resources
            if task_id in self._task_resources:
                del self._task_resources[task_id]
            
            return released
    
    def get_blocked_tasks(self, resource: str) -> List[Task]:
        """Get tasks waiting for a resource."""
        with self._lock:
            return [task for _, task in self._waiting_tasks.get(resource, [])]
    
    def detect_deadlock(self) -> List[List[str]]:
        """Detect circular wait conditions (deadlocks)."""
        with self._lock:
            # Build wait-for graph
            wait_graph = defaultdict(set)
            
            for resource, waiting in self._waiting_tasks.items():
                holder_id = self._resource_holders.get(resource)
                if holder_id:
                    for waiter_id, _ in waiting:
                        wait_graph[waiter_id].add(holder_id)
            
            # Find cycles using DFS
            cycles = []
            visited = set()
            rec_stack = set()
            
            def dfs(node: str, path: List[str]) -> None:
                visited.add(node)
                rec_stack.add(node)
                path.append(node)
                
                for neighbor in wait_graph.get(node, []):
                    if neighbor not in visited:
                        dfs(neighbor, path[:])
                    elif neighbor in rec_stack:
                        # Found cycle
                        cycle_start = path.index(neighbor)
                        cycles.append(path[cycle_start:])
                
                rec_stack.remove(node)
            
            for node in wait_graph:
                if node not in visited:
                    dfs(node, [])
            
            return cycles
    
    def _get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID (to be implemented by scheduler)."""
        # This will be set by the scheduler
        return getattr(self, '_task_lookup', {}).get(task_id)


class Scheduler(ABC):
    """Abstract base scheduler class."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running_tasks: Dict[str, Future] = {}
        self._completed_tasks: Dict[str, Task] = {}
        self._all_tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._shutdown = False
        
        # Monitoring
        self.latency_monitor = LatencyMonitor()
        
        logger.info(f"Scheduler initialized with {max_workers} workers")
    
    @abstractmethod
    def submit(self, task: Task) -> None:
        """Submit a task for scheduling."""
        pass
    
    @abstractmethod
    def _schedule_next(self) -> Optional[Task]:
        """Select the next task to run."""
        pass
    
    def start(self) -> None:
        """Start the scheduler."""
        self._shutdown = False
        self._scheduler_thread = threading.Thread(target=self._scheduling_loop)
        self._scheduler_thread.daemon = True
        self._scheduler_thread.start()
        logger.info("Scheduler started")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._shutdown = True
        self._executor.shutdown(wait=True)
        logger.info("Scheduler stopped")
    
    def _scheduling_loop(self) -> None:
        """Main scheduling loop."""
        while not self._shutdown:
            try:
                # Check for completed tasks
                self._check_completed_tasks()
                
                # Schedule next task if workers available
                if len(self._running_tasks) < self.max_workers:
                    task = self._schedule_next()
                    if task:
                        self._execute_task(task)
                
                # Small sleep to prevent busy waiting
                time.sleep(0.001)  # 1ms
                
            except Exception as e:
                logger.error(f"Scheduling error: {e}", exc_info=True)
    
    def _execute_task(self, task: Task) -> None:
        """Execute a task in the thread pool."""
        with self._lock:
            # Update task status
            task.status = TaskStatus.READY
            task.metrics.scheduled_at = datetime.now()
            
            # Track scheduling latency
            scheduling_latency = (
                task.metrics.scheduled_at - task.metrics.created_at
            ).total_seconds() * 1000
            
            self.latency_monitor.record_scheduling_latency(task, scheduling_latency)
            
            # Submit to executor
            future = self._executor.submit(self._run_task, task)
            self._running_tasks[task.id] = future
            
            logger.info(
                f"Scheduled task {task.id}",
                extra={
                    "scheduling_latency_ms": scheduling_latency,
                    "priority": task.effective_priority
                }
            )
    
    def _run_task(self, task: Task) -> None:
        """Run a task and handle metrics."""
        start_time = time.time()
        
        try:
            # Execute the task
            task.execute()
            
            # Record execution metrics
            execution_time = (time.time() - start_time) * 1000
            self.latency_monitor.record_execution_time(task, execution_time)
            
            # Update Prometheus metrics
            metrics.performance.tasks_processed.increment()
            
        except Exception as e:
            # Record failure
            metrics.performance.tasks_failed.increment()
            raise
        
        finally:
            with self._lock:
                # Move to completed
                self._completed_tasks[task.id] = task
                self._running_tasks.pop(task.id, None)
    
    def _check_completed_tasks(self) -> None:
        """Check for completed task futures."""
        with self._lock:
            completed = []
            for task_id, future in list(self._running_tasks.items()):
                if future.done():
                    completed.append(task_id)
                    try:
                        future.result()  # Raise any exceptions
                    except Exception as e:
                        logger.error(f"Task {task_id} failed: {e}")
            
            # Clean up completed tasks
            for task_id in completed:
                self._running_tasks.pop(task_id, None)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._all_tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        with self._lock:
            task = self._all_tasks.get(task_id)
            if task and task.status in [TaskStatus.PENDING, TaskStatus.READY]:
                task.cancel()
                return True
            return False


class RealtimeScheduler(Scheduler):
    """Real-time scheduler with preemption and priority inheritance."""
    
    def __init__(self, max_workers: int = 4, policy: SchedulingPolicy = SchedulingPolicy.PRIORITY):
        super().__init__(max_workers)
        self.policy = policy
        
        # Initialize appropriate queue
        if policy == SchedulingPolicy.PRIORITY:
            self._ready_queue = PriorityQueue()
        elif policy == SchedulingPolicy.DEADLINE:
            self._ready_queue = DeadlineQueue()
        elif policy == SchedulingPolicy.FAIR:
            self._ready_queue = MultiLevelQueue()
        else:
            self._ready_queue = PriorityQueue()  # Default
        
        # Priority inheritance protocol
        self._pip = PriorityInheritanceProtocol()
        self._pip._task_lookup = self._all_tasks  # Provide task lookup
        
        # Preemption support
        self._preemptible_tasks: Set[str] = set()
        self._preemption_points: Dict[str, threading.Event] = {}
        
        # Real-time constraints
        self._perception_threshold_ms = 100  # Max latency for perception tasks
        self._hard_realtime_tasks: Set[str] = set()
        
        logger.info(f"Real-time scheduler initialized with policy: {policy.value}")
    
    def submit(self, task: Task) -> None:
        """Submit a task for scheduling."""
        with self._lock:
            # Validate real-time constraints
            if task.constraints.is_hard_realtime:
                if not task.constraints.deadline:
                    raise ValueError("Hard real-time tasks must have deadlines")
                self._hard_realtime_tasks.add(task.id)
            
            # Store task
            self._all_tasks[task.id] = task
            
            # Check dependencies
            if self._dependencies_satisfied(task):
                self._ready_queue.enqueue(task)
            else:
                task.status = TaskStatus.BLOCKED
            
            # Check for preemption opportunity
            if task.priority >= TaskPriority.HIGH:
                self._check_preemption(task)
            
            logger.debug(f"Submitted task {task.id}")
    
    def _schedule_next(self) -> Optional[Task]:
        """Select the next task to run based on policy."""
        with self._lock:
            # Check for deadline-critical tasks first
            if self.policy != SchedulingPolicy.DEADLINE:
                urgent_tasks = self._get_urgent_tasks()
                if urgent_tasks:
                    # Switch to deadline scheduling temporarily
                    task = min(urgent_tasks, key=lambda t: t.constraints.deadline)
                    self._ready_queue.remove(task.id)
                    return task
            
            # Normal scheduling based on policy
            if self.policy == SchedulingPolicy.FAIR:
                result = self._ready_queue.dequeue()
                if result:
                    task, time_slice = result
                    # Set time slice for fair scheduling
                    task.metadata['time_slice_ms'] = time_slice
                    return task
            else:
                return self._ready_queue.dequeue()
    
    def _dependencies_satisfied(self, task: Task) -> bool:
        """Check if task dependencies are satisfied."""
        for dep_id in task.constraints.depends_on:
            dep_task = self._all_tasks.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True
    
    def _check_preemption(self, new_task: Task) -> None:
        """Check if new task should preempt running tasks."""
        if not new_task.constraints.is_hard_realtime:
            return
        
        with self._lock:
            # Find lowest priority running task
            lowest_priority = None
            lowest_task_id = None
            
            for task_id in self._running_tasks:
                task = self._all_tasks.get(task_id)
                if task and task.constraints.is_preemptible:
                    if lowest_priority is None or task.effective_priority < lowest_priority:
                        lowest_priority = task.effective_priority
                        lowest_task_id = task_id
            
            # Preempt if new task has higher priority
            if lowest_task_id and new_task.can_preempt(self._all_tasks[lowest_task_id]):
                self._preempt_task(lowest_task_id)
                logger.info(f"Preempting task {lowest_task_id} for {new_task.id}")
    
    def _preempt_task(self, task_id: str) -> None:
        """Preempt a running task."""
        with self._lock:
            if task_id in self._preemption_points:
                # Signal preemption
                self._preemption_points[task_id].set()
            
            # Cancel the future (may not stop immediately)
            future = self._running_tasks.get(task_id)
            if future:
                future.cancel()
    
    def _get_urgent_tasks(self) -> List[Task]:
        """Get tasks with approaching deadlines."""
        urgent = []
        threshold = timedelta(milliseconds=self._perception_threshold_ms)
        
        for task in self._all_tasks.values():
            if (task.status == TaskStatus.PENDING and 
                task.is_deadline_approaching(threshold)):
                urgent.append(task)
        
        return urgent
    
    def acquire_resources(self, task: Task, resources: List[str]) -> bool:
        """Acquire multiple resources with priority inheritance."""
        acquired = []
        
        for resource in resources:
            if self._pip.acquire_resource(task, resource):
                acquired.append(resource)
            else:
                # Failed to acquire, release what we got
                for res in acquired:
                    self._pip.release_resource(task.id, res)
                
                # Mark task as blocked
                task.status = TaskStatus.BLOCKED
                return False
        
        return True
    
    def release_resources(self, task_id: str) -> None:
        """Release all resources held by a task."""
        released = self._pip.release_all_resources(task_id)
        
        # Unblock waiting tasks
        for resource, next_task in released:
            if next_task.status == TaskStatus.BLOCKED:
                next_task.status = TaskStatus.PENDING
                self._ready_queue.enqueue(next_task)
    
    def detect_deadline_violations(self) -> List[Task]:
        """Find tasks that have missed or will miss deadlines."""
        violations = []
        
        with self._lock:
            for task in self._all_tasks.values():
                if task.status != TaskStatus.COMPLETED:
                    if task.has_missed_deadline():
                        violations.append(task)
                        if task.id in self._hard_realtime_tasks:
                            logger.error(
                                f"Hard real-time deadline missed: {task.id}",
                                extra={"task_name": task.name}
                            )
        
        return violations