"""Exceptions for the scheduling framework."""


class SchedulingError(Exception):
    """Base exception for scheduling errors."""
    pass


class DeadlineMissedError(SchedulingError):
    """Raised when a task misses its deadline."""
    
    def __init__(self, task_id: str, deadline: str, completed_at: str = None):
        self.task_id = task_id
        self.deadline = deadline
        self.completed_at = completed_at
        
        if completed_at:
            message = f"Task {task_id} missed deadline {deadline}, completed at {completed_at}"
        else:
            message = f"Task {task_id} missed deadline {deadline}, not completed"
        
        super().__init__(message)


class PriorityInversionError(SchedulingError):
    """Raised when priority inversion is detected."""
    
    def __init__(self, high_priority_task: str, low_priority_task: str, resource: str):
        self.high_priority_task = high_priority_task
        self.low_priority_task = low_priority_task
        self.resource = resource
        
        message = (
            f"Priority inversion: high priority task {high_priority_task} "
            f"blocked by low priority task {low_priority_task} on resource {resource}"
        )
        
        super().__init__(message)


class ResourceDeadlockError(SchedulingError):
    """Raised when a resource deadlock is detected."""
    
    def __init__(self, tasks_involved: list, resources: list):
        self.tasks_involved = tasks_involved
        self.resources = resources
        
        message = (
            f"Deadlock detected involving tasks {tasks_involved} "
            f"and resources {resources}"
        )
        
        super().__init__(message)


class TaskNotFoundError(SchedulingError):
    """Raised when a task is not found."""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class InvalidTaskStateError(SchedulingError):
    """Raised when a task is in an invalid state for an operation."""
    
    def __init__(self, task_id: str, current_state: str, expected_states: list):
        self.task_id = task_id
        self.current_state = current_state
        self.expected_states = expected_states
        
        message = (
            f"Task {task_id} is in state {current_state}, "
            f"expected one of {expected_states}"
        )
        
        super().__init__(message)


class InsufficientResourcesError(SchedulingError):
    """Raised when there are insufficient resources to schedule a task."""
    
    def __init__(self, task_id: str, required: dict, available: dict):
        self.task_id = task_id
        self.required = required
        self.available = available
        
        message = (
            f"Insufficient resources for task {task_id}: "
            f"required {required}, available {available}"
        )
        
        super().__init__(message)