"""Celery configuration and task definitions for distributed processing."""

import logging
from typing import Any, Dict, Optional
from celery import Celery, Task as CeleryTask
from celery.result import AsyncResult

from .distributed import (
    BaseWorker, Task, TaskPriority, Coordinator, ComputeWorker
)

logger = logging.getLogger(__name__)

# Celery configuration
celery_app = Celery(
    "jarvis",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Initialize coordinator for advanced task distribution
coordinator = Coordinator(max_workers=20, max_queue_size=1000)


class JarvisTask(CeleryTask):
    """Base Celery task with enhanced monitoring and error handling."""
    
    def __call__(self, *args, **kwargs):
        """Execute task with monitoring."""
        logger.info(f"Starting task {self.name} with args={args}, kwargs={kwargs}")
        try:
            result = self.run(*args, **kwargs)
            logger.info(f"Task {self.name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Task {self.name} failed: {e}")
            raise
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Task {task_id} failed with exception: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        logger.warning(f"Task {task_id} being retried due to: {exc}")
        super().on_retry(exc, task_id, args, kwargs, einfo)


# Register task base
celery_app.Task = JarvisTask


@celery_app.task(name="jarvis.compute.add")  # type: ignore[misc]
def add(x: int, y: int) -> int:
    """Simple addition task."""
    return x + y


@celery_app.task(name="jarvis.compute.multiply")  # type: ignore[misc]
def multiply(x: int, y: int) -> int:
    """Simple multiplication task."""
    return x * y


@celery_app.task(name="jarvis.distributed.submit_task")  # type: ignore[misc]
def submit_distributed_task(task_type: str, 
                          task_data: Any,
                          priority: str = "NORMAL") -> Dict[str, Any]:
    """Submit a task to the distributed coordinator.
    
    Args:
        task_type: Type of task to execute
        task_data: Data for the task
        priority: Task priority level
        
    Returns:
        Dictionary with task ID and status
    """
    # Create task
    task = Task(
        type=task_type,
        data=task_data,
        priority=TaskPriority[priority]
    )
    
    # Submit to coordinator
    try:
        task_id = coordinator.submit_task(task)
        return {
            "success": True,
            "task_id": task_id,
            "status": "submitted"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(name="jarvis.distributed.get_task_result")  # type: ignore[misc]
def get_distributed_task_result(task_id: str, 
                              timeout: Optional[float] = None) -> Dict[str, Any]:
    """Get the result of a distributed task.
    
    Args:
        task_id: ID of the task
        timeout: Maximum time to wait for result
        
    Returns:
        Dictionary with task result or error
    """
    result = coordinator.get_result(task_id, timeout=timeout)
    
    if result:
        return {
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "processing_time": result.processing_time,
            "worker_id": result.worker_id
        }
    else:
        return {
            "success": False,
            "error": "Task result not available"
        }


@celery_app.task(name="jarvis.system.health_check")  # type: ignore[misc]
def health_check() -> Dict[str, Any]:
    """System health check task."""
    return {
        "status": "healthy",
        "coordinator_status": coordinator.get_status(),
        "celery_stats": celery_app.control.inspect().stats()
    }


# Initialize coordinator with compute workers on module load
try:
    coordinator.register_worker_type(
        task_type="compute",
        worker_class=ComputeWorker,
        min_workers=2,
        max_workers=10
    )
    logger.info("Initialized distributed coordinator with compute workers")
except Exception as e:
    logger.error(f"Failed to initialize coordinator: {e}")


# Helper functions for Celery task management
def submit_async_task(task_name: str, *args, **kwargs) -> AsyncResult:
    """Submit an async task via Celery.
    
    Args:
        task_name: Name of the Celery task
        *args: Task arguments
        **kwargs: Task keyword arguments
        
    Returns:
        AsyncResult object
    """
    task = celery_app.send_task(task_name, args=args, kwargs=kwargs)
    return task


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a Celery task.
    
    Args:
        task_id: Celery task ID
        
    Returns:
        Dictionary with task status information
    """
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "state": result.state,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "result": result.result if result.ready() else None,
        "info": result.info
    }
