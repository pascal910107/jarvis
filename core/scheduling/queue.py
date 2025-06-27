"""Priority queue implementations for task scheduling."""

import heapq
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from core.monitoring import get_logger

from .task import Task, TaskPriority, TaskStatus

logger = get_logger(__name__)


class TaskQueue(ABC):
    """Abstract base class for task queues."""
    
    @abstractmethod
    def enqueue(self, task: Task) -> None:
        """Add a task to the queue."""
        pass
    
    @abstractmethod
    def dequeue(self) -> Optional[Task]:
        """Remove and return the highest priority task."""
        pass
    
    @abstractmethod
    def peek(self) -> Optional[Task]:
        """Return the highest priority task without removing it."""
        pass
    
    @abstractmethod
    def remove(self, task_id: str) -> Optional[Task]:
        """Remove a specific task from the queue."""
        pass
    
    @abstractmethod
    def size(self) -> int:
        """Get the number of tasks in the queue."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Remove all tasks from the queue."""
        pass


class PriorityQueue(TaskQueue):
    """Thread-safe priority queue for task scheduling."""
    
    def __init__(self):
        self._heap: List[Tuple[float, int, Task]] = []
        self._task_map: Dict[str, Task] = {}
        self._counter = 0  # For stable sorting
        self._lock = threading.RLock()
        
    def enqueue(self, task: Task) -> None:
        """Add a task to the priority queue."""
        with self._lock:
            if task.id in self._task_map:
                logger.warning(f"Task {task.id} already in queue")
                return
            
            # Use negative priority for max heap behavior
            priority = -task.effective_priority
            
            # Add counter for stable sorting
            self._counter += 1
            entry = (priority, self._counter, task)
            
            heapq.heappush(self._heap, entry)
            self._task_map[task.id] = task
            
            logger.debug(f"Enqueued task {task.id} with priority {task.effective_priority}")
    
    def dequeue(self) -> Optional[Task]:
        """Remove and return the highest priority task."""
        with self._lock:
            while self._heap:
                priority, count, task = heapq.heappop(self._heap)
                
                # Skip removed tasks
                if task.id in self._task_map:
                    del self._task_map[task.id]
                    return task
            
            return None
    
    def peek(self) -> Optional[Task]:
        """Return the highest priority task without removing it."""
        with self._lock:
            # Clean up removed tasks from heap top
            while self._heap:
                priority, count, task = self._heap[0]
                if task.id in self._task_map:
                    return task
                heapq.heappop(self._heap)
            
            return None
    
    def remove(self, task_id: str) -> Optional[Task]:
        """Remove a specific task from the queue."""
        with self._lock:
            task = self._task_map.pop(task_id, None)
            if task:
                logger.debug(f"Removed task {task_id} from queue")
            return task
    
    def update_priority(self, task_id: str, new_priority: int) -> bool:
        """Update task priority (requires re-insertion)."""
        with self._lock:
            task = self.remove(task_id)
            if task:
                # Update the task's effective priority
                task._effective_priority = new_priority
                self.enqueue(task)
                return True
            return False
    
    def size(self) -> int:
        """Get the number of tasks in the queue."""
        with self._lock:
            return len(self._task_map)
    
    def clear(self) -> None:
        """Remove all tasks from the queue."""
        with self._lock:
            self._heap.clear()
            self._task_map.clear()
            self._counter = 0
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks in priority order."""
        with self._lock:
            # Create a copy of the heap and sort
            tasks = []
            for priority, count, task in sorted(self._heap):
                if task.id in self._task_map:
                    tasks.append(task)
            return tasks


class DeadlineQueue(TaskQueue):
    """Queue that prioritizes tasks by deadline (EDF - Earliest Deadline First)."""
    
    def __init__(self):
        self._heap: List[Tuple[datetime, int, Task]] = []
        self._task_map: Dict[str, Task] = {}
        self._counter = 0
        self._lock = threading.RLock()
    
    def enqueue(self, task: Task) -> None:
        """Add a task to the deadline queue."""
        with self._lock:
            if task.id in self._task_map:
                return
            
            # Use deadline as priority (earliest deadline first)
            if task.constraints.deadline:
                deadline = task.constraints.deadline
            else:
                # Tasks without deadlines go to the end
                deadline = datetime.max
            
            self._counter += 1
            entry = (deadline, self._counter, task)
            
            heapq.heappush(self._heap, entry)
            self._task_map[task.id] = task
            
            logger.debug(f"Enqueued task {task.id} with deadline {deadline}")
    
    def dequeue(self) -> Optional[Task]:
        """Remove and return the task with earliest deadline."""
        with self._lock:
            while self._heap:
                deadline, count, task = heapq.heappop(self._heap)
                
                if task.id in self._task_map:
                    del self._task_map[task.id]
                    
                    # Check if deadline was missed
                    if task.has_missed_deadline():
                        task.status = TaskStatus.DEADLINE_MISSED
                        logger.warning(f"Task {task.id} missed deadline")
                    
                    return task
            
            return None
    
    def peek(self) -> Optional[Task]:
        """Return the task with earliest deadline."""
        with self._lock:
            while self._heap:
                deadline, count, task = self._heap[0]
                if task.id in self._task_map:
                    return task
                heapq.heappop(self._heap)
            
            return None
    
    def remove(self, task_id: str) -> Optional[Task]:
        """Remove a specific task."""
        with self._lock:
            return self._task_map.pop(task_id, None)
    
    def size(self) -> int:
        """Get queue size."""
        with self._lock:
            return len(self._task_map)
    
    def clear(self) -> None:
        """Clear the queue."""
        with self._lock:
            self._heap.clear()
            self._task_map.clear()
            self._counter = 0
    
    def get_urgent_tasks(self, threshold: timedelta) -> List[Task]:
        """Get tasks with deadlines approaching within threshold."""
        with self._lock:
            urgent = []
            for _, _, task in self._heap:
                if task.id in self._task_map and task.is_deadline_approaching(threshold):
                    urgent.append(task)
            return urgent


class MultiLevelQueue:
    """Multi-level feedback queue for different task classes."""
    
    def __init__(self, num_levels: int = 4):
        self.num_levels = num_levels
        self._queues: List[deque] = [deque() for _ in range(num_levels)]
        self._task_levels: Dict[str, int] = {}
        self._task_map: Dict[str, Task] = {}
        self._time_slices = [10, 20, 40, 80]  # ms per level
        self._lock = threading.RLock()
        
        # Map priorities to initial queue levels
        self._priority_to_level = {
            TaskPriority.REALTIME: 0,
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
            TaskPriority.BACKGROUND: 3,
            TaskPriority.IDLE: 3,
        }
    
    def enqueue(self, task: Task, level: Optional[int] = None) -> None:
        """Add a task to the appropriate level."""
        with self._lock:
            if task.id in self._task_map:
                return
            
            # Determine initial level
            if level is None:
                level = self._priority_to_level.get(task.priority, 2)
            
            level = max(0, min(level, self.num_levels - 1))
            
            self._queues[level].append(task)
            self._task_levels[task.id] = level
            self._task_map[task.id] = task
            
            logger.debug(f"Enqueued task {task.id} at level {level}")
    
    def dequeue(self) -> Optional[Tuple[Task, int]]:
        """Get next task and its time slice."""
        with self._lock:
            # Check queues from highest to lowest priority
            for level in range(self.num_levels):
                if self._queues[level]:
                    task = self._queues[level].popleft()
                    
                    if task.id in self._task_map:
                        del self._task_levels[task.id]
                        del self._task_map[task.id]
                        
                        time_slice = self._time_slices[min(level, len(self._time_slices) - 1)]
                        return task, time_slice
            
            return None
    
    def demote_task(self, task: Task) -> None:
        """Move task to lower priority level (used after time slice expires)."""
        with self._lock:
            if task.id not in self._task_levels:
                return
            
            current_level = self._task_levels[task.id]
            new_level = min(current_level + 1, self.num_levels - 1)
            
            if new_level != current_level:
                self._task_levels[task.id] = new_level
                logger.debug(f"Demoted task {task.id} from level {current_level} to {new_level}")
            
            self._queues[new_level].append(task)
    
    def promote_task(self, task_id: str) -> bool:
        """Move task to higher priority level."""
        with self._lock:
            if task_id not in self._task_levels:
                return False
            
            task = self._task_map[task_id]
            current_level = self._task_levels[task_id]
            
            # Remove from current queue
            try:
                self._queues[current_level].remove(task)
            except ValueError:
                return False
            
            # Add to higher level
            new_level = max(0, current_level - 1)
            self._queues[new_level].append(task)
            self._task_levels[task_id] = new_level
            
            logger.debug(f"Promoted task {task_id} from level {current_level} to {new_level}")
            return True
    
    def remove(self, task_id: str) -> Optional[Task]:
        """Remove a task from any level."""
        with self._lock:
            if task_id not in self._task_levels:
                return None
            
            task = self._task_map[task_id]
            level = self._task_levels[task_id]
            
            try:
                self._queues[level].remove(task)
                del self._task_levels[task_id]
                del self._task_map[task_id]
                return task
            except ValueError:
                return None
    
    def size(self) -> int:
        """Get total number of tasks."""
        with self._lock:
            return len(self._task_map)
    
    def clear(self) -> None:
        """Clear all queues."""
        with self._lock:
            for queue in self._queues:
                queue.clear()
            self._task_levels.clear()
            self._task_map.clear()
    
    def get_level_sizes(self) -> List[int]:
        """Get number of tasks at each level."""
        with self._lock:
            return [len(queue) for queue in self._queues]