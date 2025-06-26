"""Base worker class for distributed task execution."""

import logging
import multiprocessing
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Callable
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class WorkerStatus(Enum):
    """Worker status states."""
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerMetrics:
    """Metrics for worker performance tracking."""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    last_task_time: Optional[datetime] = None
    error_count: int = 0
    start_time: datetime = None

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()


class BaseWorker(ABC):
    """Abstract base class for distributed workers."""
    
    def __init__(self, worker_id: Optional[str] = None, name: Optional[str] = None):
        """Initialize a worker.
        
        Args:
            worker_id: Unique identifier for the worker
            name: Human-readable name for the worker
        """
        self.worker_id = worker_id or str(uuid.uuid4())
        self.name = name or f"Worker-{self.worker_id[:8]}"
        self.status = WorkerStatus.IDLE
        self.metrics = WorkerMetrics()
        self.current_task: Optional[Any] = None
        self._stop_event = multiprocessing.Event()
        self._pause_event = multiprocessing.Event()
        
        logger.info(f"Initialized worker {self.name} with ID {self.worker_id}")
    
    @abstractmethod
    def process_task(self, task: Any) -> Any:
        """Process a single task.
        
        Args:
            task: The task to process
            
        Returns:
            The result of processing the task
            
        Raises:
            Exception: If task processing fails
        """
        pass
    
    @abstractmethod
    def validate_task(self, task: Any) -> bool:
        """Validate if this worker can handle the given task.
        
        Args:
            task: The task to validate
            
        Returns:
            True if the worker can handle the task, False otherwise
        """
        pass
    
    def run(self, task_queue: Any, result_queue: Any):
        """Main worker loop for processing tasks.
        
        Args:
            task_queue: Queue to receive tasks from
            result_queue: Queue to send results to
        """
        logger.info(f"Worker {self.name} starting...")
        
        while not self._stop_event.is_set():
            # Check if paused
            if self._pause_event.is_set():
                self.status = WorkerStatus.PAUSED
                time.sleep(0.1)
                continue
            
            try:
                # Get task from queue with timeout
                task = task_queue.get(timeout=1.0)
                
                if task is None:  # Poison pill
                    break
                
                # Validate task
                if not self.validate_task(task):
                    logger.warning(f"Worker {self.name} cannot handle task {task}")
                    result_queue.put({
                        "worker_id": self.worker_id,
                        "task": task,
                        "success": False,
                        "error": "Task validation failed"
                    })
                    continue
                
                # Process task
                self.status = WorkerStatus.BUSY
                self.current_task = task
                start_time = time.time()
                
                try:
                    result = self.process_task(task)
                    processing_time = time.time() - start_time
                    
                    # Update metrics
                    self.metrics.tasks_completed += 1
                    self.metrics.total_processing_time += processing_time
                    self.metrics.last_task_time = datetime.now()
                    
                    # Send result
                    result_queue.put({
                        "worker_id": self.worker_id,
                        "task": task,
                        "result": result,
                        "success": True,
                        "processing_time": processing_time
                    })
                    
                except Exception as e:
                    logger.error(f"Worker {self.name} failed to process task: {e}")
                    self.metrics.tasks_failed += 1
                    self.metrics.error_count += 1
                    
                    result_queue.put({
                        "worker_id": self.worker_id,
                        "task": task,
                        "success": False,
                        "error": str(e)
                    })
                
                finally:
                    self.current_task = None
                    self.status = WorkerStatus.IDLE
                    
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Worker {self.name} encountered error: {e}")
                    self.status = WorkerStatus.ERROR
                    time.sleep(1.0)  # Backoff on error
        
        self.status = WorkerStatus.STOPPED
        logger.info(f"Worker {self.name} stopped")
    
    def pause(self):
        """Pause the worker."""
        self._pause_event.set()
        logger.info(f"Worker {self.name} paused")
    
    def resume(self):
        """Resume the worker."""
        self._pause_event.clear()
        logger.info(f"Worker {self.name} resumed")
    
    def stop(self):
        """Stop the worker."""
        self._stop_event.set()
        logger.info(f"Worker {self.name} stopping...")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get worker performance metrics.
        
        Returns:
            Dictionary containing worker metrics
        """
        uptime = (datetime.now() - self.metrics.start_time).total_seconds()
        avg_processing_time = (
            self.metrics.total_processing_time / self.metrics.tasks_completed
            if self.metrics.tasks_completed > 0 else 0
        )
        
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "status": self.status.value,
            "tasks_completed": self.metrics.tasks_completed,
            "tasks_failed": self.metrics.tasks_failed,
            "error_count": self.metrics.error_count,
            "average_processing_time": avg_processing_time,
            "total_processing_time": self.metrics.total_processing_time,
            "uptime_seconds": uptime,
            "last_task_time": self.metrics.last_task_time.isoformat() if self.metrics.last_task_time else None
        }


class ComputeWorker(BaseWorker):
    """Example worker for compute-intensive tasks."""
    
    def __init__(self, worker_id: Optional[str] = None, compute_fn: Optional[Callable] = None):
        super().__init__(worker_id, name=f"ComputeWorker-{worker_id[:8] if worker_id else 'default'}")
        self.compute_fn = compute_fn or (lambda x: x)
    
    def process_task(self, task: Any) -> Any:
        """Process a compute task."""
        if hasattr(task, 'data'):
            return self.compute_fn(task.data)
        return self.compute_fn(task)
    
    def validate_task(self, task: Any) -> bool:
        """Validate compute task."""
        # Accept any task for now, can be customized
        return True