"""Coordinator for managing distributed task execution."""

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Callable, Type
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime, timedelta

from .task_queue import TaskQueue, Task, TaskPriority
from .base_worker import BaseWorker, WorkerStatus
from .worker_pool import WorkerPool

logger = logging.getLogger(__name__)


class TaskResult:
    """Container for task execution results."""
    
    def __init__(self, task_id: str, success: bool, result: Any = None, 
                 error: Optional[str] = None, worker_id: Optional[str] = None,
                 processing_time: float = 0.0):
        self.task_id = task_id
        self.success = success
        self.result = result
        self.error = error
        self.worker_id = worker_id
        self.processing_time = processing_time
        self.timestamp = datetime.now()


class Coordinator:
    """Central coordinator for distributed task execution."""
    
    def __init__(self, 
                 max_workers: int = 10,
                 max_queue_size: Optional[int] = None,
                 result_retention_time: timedelta = timedelta(hours=1)):
        """Initialize the coordinator.
        
        Args:
            max_workers: Maximum number of concurrent workers
            max_queue_size: Maximum size of task queue
            result_retention_time: How long to keep task results
        """
        self.max_workers = max_workers
        self.result_retention_time = result_retention_time
        
        # Core components
        self.task_queue = TaskQueue(max_size=max_queue_size)
        self.worker_pools: Dict[str, WorkerPool] = {}
        self.results: Dict[str, TaskResult] = {}
        self.result_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # Thread management
        self._lock = threading.RLock()
        self._shutdown = False
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        
        # Statistics
        self._stats = {
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_retried": 0,
            "total_processing_time": 0.0
        }
        
        # Start background threads
        self._monitor_thread.start()
        self._cleanup_thread.start()
        
        logger.info(f"Initialized Coordinator with max_workers={max_workers}")
    
    def register_worker_type(self, 
                           task_type: str, 
                           worker_class: Type[BaseWorker],
                           min_workers: int = 1,
                           max_workers: int = 5,
                           **worker_kwargs):
        """Register a worker type for handling specific tasks.
        
        Args:
            task_type: Type of tasks this worker handles
            worker_class: Worker class to instantiate
            min_workers: Minimum number of workers
            max_workers: Maximum number of workers
            **worker_kwargs: Additional arguments for worker initialization
        """
        with self._lock:
            if task_type in self.worker_pools:
                logger.warning(f"Worker type {task_type} already registered, updating...")
            
            # Create worker pool
            pool = WorkerPool(
                worker_class=worker_class,
                min_workers=min_workers,
                max_workers=max_workers,
                worker_kwargs=worker_kwargs
            )
            
            self.worker_pools[task_type] = pool
            pool.start()
            
            logger.info(f"Registered worker type {task_type} with {min_workers}-{max_workers} workers")
    
    def submit_task(self, 
                   task: Task, 
                   callback: Optional[Callable[[TaskResult], None]] = None) -> str:
        """Submit a task for execution.
        
        Args:
            task: Task to execute
            callback: Optional callback for when task completes
            
        Returns:
            Task ID
        """
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Coordinator is shutting down")
            
            # Validate worker pool exists
            if task.type not in self.worker_pools:
                raise ValueError(f"No worker registered for task type: {task.type}")
            
            # Add callback if provided
            if callback:
                self.result_callbacks[task.id].append(callback)
            
            # Submit task to queue
            success = self.task_queue.put(task)
            if success:
                self._stats["tasks_submitted"] += 1
                logger.info(f"Submitted task {task.id} (type={task.type}, priority={task.priority.name})")
            else:
                logger.error(f"Failed to submit task {task.id} - queue full")
                raise RuntimeError("Task queue is full")
            
            # Schedule task execution
            self._executor.submit(self._process_task, task)
            
            return task.id
    
    def submit_batch(self, 
                    tasks: List[Task],
                    callback: Optional[Callable[[List[TaskResult]], None]] = None) -> List[str]:
        """Submit multiple tasks as a batch.
        
        Args:
            tasks: List of tasks to execute
            callback: Optional callback for when all tasks complete
            
        Returns:
            List of task IDs
        """
        task_ids = []
        batch_results = []
        remaining_tasks = len(tasks)
        
        def batch_callback(result: TaskResult):
            nonlocal remaining_tasks
            batch_results.append(result)
            remaining_tasks -= 1
            
            if remaining_tasks == 0 and callback:
                callback(batch_results)
        
        for task in tasks:
            task_id = self.submit_task(task, batch_callback)
            task_ids.append(task_id)
        
        return task_ids
    
    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Optional[TaskResult]:
        """Get the result of a task.
        
        Args:
            task_id: ID of the task
            timeout: Maximum time to wait for result
            
        Returns:
            TaskResult if available, None otherwise
        """
        end_time = time.time() + timeout if timeout else None
        
        while True:
            with self._lock:
                if task_id in self.results:
                    return self.results[task_id]
            
            if end_time and time.time() >= end_time:
                return None
            
            time.sleep(0.1)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task.
        
        Args:
            task_id: ID of the task to cancel
            
        Returns:
            True if task was cancelled, False otherwise
        """
        return self.task_queue.remove(task_id)
    
    def scale_workers(self, task_type: str, target_workers: int):
        """Scale the number of workers for a task type.
        
        Args:
            task_type: Type of tasks
            target_workers: Target number of workers
        """
        with self._lock:
            if task_type not in self.worker_pools:
                raise ValueError(f"No worker pool for task type: {task_type}")
            
            pool = self.worker_pools[task_type]
            pool.scale(target_workers)
            
            logger.info(f"Scaled {task_type} workers to {target_workers}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get coordinator status and statistics.
        
        Returns:
            Dictionary containing status information
        """
        with self._lock:
            worker_stats = {}
            for task_type, pool in self.worker_pools.items():
                worker_stats[task_type] = pool.get_stats()
            
            return {
                "active": not self._shutdown,
                "queue_stats": self.task_queue.get_stats(),
                "worker_pools": worker_stats,
                "coordinator_stats": dict(self._stats),
                "pending_results": len(self.results)
            }
    
    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """Shutdown the coordinator.
        
        Args:
            wait: Whether to wait for pending tasks
            timeout: Maximum time to wait for shutdown
        """
        logger.info("Shutting down coordinator...")
        
        with self._lock:
            self._shutdown = True
            
            # Stop accepting new tasks
            self.task_queue.clear()
            
            # Shutdown worker pools
            for pool in self.worker_pools.values():
                pool.shutdown(wait=wait)
        
        # Shutdown executor
        self._executor.shutdown(wait=wait)
        
        # Wait for threads
        if wait:
            self._monitor_thread.join(timeout=timeout)
            self._cleanup_thread.join(timeout=timeout)
        
        logger.info("Coordinator shutdown complete")
    
    def _process_task(self, task: Task):
        """Process a single task."""
        try:
            # Get appropriate worker pool
            pool = self.worker_pools.get(task.type)
            if not pool:
                self._handle_task_error(task, f"No worker pool for task type: {task.type}")
                return
            
            # Execute task
            start_time = time.time()
            try:
                result = pool.execute_task(task)
                processing_time = time.time() - start_time
                
                # Store result
                task_result = TaskResult(
                    task_id=task.id,
                    success=True,
                    result=result,
                    processing_time=processing_time
                )
                
                with self._lock:
                    self.results[task.id] = task_result
                    self._stats["tasks_completed"] += 1
                    self._stats["total_processing_time"] += processing_time
                
                logger.info(f"Task {task.id} completed successfully in {processing_time:.2f}s")
                
            except Exception as e:
                # Handle task failure
                if task.retry_count < task.max_retries:
                    # Retry task
                    task.retry_count += 1
                    self._stats["tasks_retried"] += 1
                    logger.warning(f"Retrying task {task.id} (attempt {task.retry_count}/{task.max_retries})")
                    
                    # Re-submit with lower priority
                    task.priority = TaskPriority(min(task.priority.value + 1, TaskPriority.BACKGROUND.value))
                    self.task_queue.put(task)
                    self._executor.submit(self._process_task, task)
                else:
                    # Task failed
                    self._handle_task_error(task, str(e))
            
            # Execute callbacks
            self._execute_callbacks(task.id)
            
        except Exception as e:
            logger.error(f"Fatal error processing task {task.id}: {e}")
    
    def _handle_task_error(self, task: Task, error: str):
        """Handle task execution error."""
        task_result = TaskResult(
            task_id=task.id,
            success=False,
            error=error
        )
        
        with self._lock:
            self.results[task.id] = task_result
            self._stats["tasks_failed"] += 1
        
        logger.error(f"Task {task.id} failed: {error}")
        
        # Execute callbacks
        self._execute_callbacks(task.id)
    
    def _execute_callbacks(self, task_id: str):
        """Execute callbacks for a completed task."""
        with self._lock:
            callbacks = self.result_callbacks.pop(task_id, [])
            result = self.results.get(task_id)
        
        if result and callbacks:
            for callback in callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Error executing callback for task {task_id}: {e}")
    
    def _monitor_loop(self):
        """Monitor worker pools and system health."""
        while not self._shutdown:
            try:
                with self._lock:
                    # Monitor worker pools
                    for task_type, pool in self.worker_pools.items():
                        stats = pool.get_stats()
                        
                        # Auto-scale based on queue size
                        queue_size = len(self.task_queue.get_tasks_by_type(task_type))
                        active_workers = stats["active_workers"]
                        
                        if queue_size > active_workers * 5 and active_workers < pool.max_workers:
                            # Scale up
                            pool.scale(min(active_workers + 1, pool.max_workers))
                        elif queue_size == 0 and active_workers > pool.min_workers:
                            # Scale down
                            pool.scale(max(active_workers - 1, pool.min_workers))
                
                time.sleep(5.0)  # Monitor interval
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(5.0)
    
    def _cleanup_loop(self):
        """Clean up old results periodically."""
        while not self._shutdown:
            try:
                with self._lock:
                    now = datetime.now()
                    expired_results = []
                    
                    for task_id, result in self.results.items():
                        if now - result.timestamp > self.result_retention_time:
                            expired_results.append(task_id)
                    
                    for task_id in expired_results:
                        del self.results[task_id]
                    
                    if expired_results:
                        logger.info(f"Cleaned up {len(expired_results)} expired results")
                
                time.sleep(60.0)  # Cleanup interval
                
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                time.sleep(60.0)