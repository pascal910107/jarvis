"""Real-time scheduling framework for Jarvis AGI.

This module provides:
- Priority-based task scheduling with deadline awareness
- Real-time constraints support (hard and soft)
- Priority inheritance protocol to prevent priority inversion
- Latency monitoring and tracking
- Preemptive scheduling for time-critical tasks
- Integration with distributed computing infrastructure
"""

from .task import Task, TaskPriority, TaskStatus, TaskConstraints
from .queue import PriorityQueue, DeadlineQueue, MultiLevelQueue
from .scheduler import (
    Scheduler, RealtimeScheduler, SchedulingPolicy,
    PriorityInheritanceProtocol
)
from .monitor import LatencyMonitor, SchedulingMetrics
from .exceptions import (
    SchedulingError, DeadlineMissedError, PriorityInversionError
)

__all__ = [
    # Task related
    "Task",
    "TaskPriority",
    "TaskStatus",
    "TaskConstraints",
    
    # Queue implementations
    "PriorityQueue",
    "DeadlineQueue",
    "MultiLevelQueue",
    
    # Scheduler
    "Scheduler",
    "RealtimeScheduler",
    "SchedulingPolicy",
    "PriorityInheritanceProtocol",
    
    # Monitoring
    "LatencyMonitor",
    "SchedulingMetrics",
    
    # Exceptions
    "SchedulingError",
    "DeadlineMissedError",
    "PriorityInversionError",
]