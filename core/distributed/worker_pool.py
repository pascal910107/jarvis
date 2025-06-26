"""Worker pool implementation for managing multiple workers."""

import logging
import multiprocessing
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Type
from concurrent.futures import ProcessPoolExecutor, Future

from .base_worker import BaseWorker, WorkerStatus
from .task_queue import Task

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages a pool of workers for parallel task execution."""
    
    def __init__(self,
                 worker_class: Type[BaseWorker],
                 min_workers: int = 1,
                 max_workers: int = 5,
                 worker_kwargs: Optional[Dict[str, Any]] = None):
        """Initialize the worker pool.
        
        Args:
            worker_class: Class of workers to instantiate
            min_workers: Minimum number of workers to maintain
            max_workers: Maximum number of workers allowed
            worker_kwargs: Arguments to pass to worker initialization
        """
        self.worker_class = worker_class
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.worker_kwargs = worker_kwargs or {}
        
        # Worker management
        self.workers: Dict[str, Dict[str, Any]] = {}
        self.task_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        
        # Thread management
        self._lock = threading.RLock()
        self._shutdown = False
        self._monitor_thread = threading.Thread(target=self._monitor_workers, daemon=True)
        self._result_thread = threading.Thread(target=self._handle_results, daemon=True)
        
        # Task tracking
        self._pending_tasks: Dict[str, Future] = {}
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        
        # Statistics
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_processing_time": 0.0
        }
        
        logger.info(f"Initialized WorkerPool with {min_workers}-{max_workers} {worker_class.__name__} workers")
    
    def start(self):
        """Start the worker pool."""
        with self._lock:
            if not self._shutdown:
                # Start minimum number of workers
                for _ in range(self.min_workers):
                    self._spawn_worker()
                
                # Start monitoring threads
                self._monitor_thread.start()
                self._result_thread.start()
                
                logger.info(f"Started worker pool with {self.min_workers} workers")
    
    def execute_task(self, task: Task) -> Any:
        """Execute a task using the worker pool.
        
        Args:
            task: Task to execute
            
        Returns:
            Task execution result
            
        Raises:
            Exception: If task execution fails
        """
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Worker pool is shutting down")
            
            self._stats["total_tasks"] += 1
            
            # Put task in queue
            self.task_queue.put(task)
            
            # Create future for result tracking
            future = Future()
            self._pending_tasks[task.id] = future
        
        # Wait for result
        try:
            result = future.result(timeout=300.0)  # 5 minute timeout
            return result
        except Exception as e:
            logger.error(f"Task {task.id} execution failed: {e}")
            raise
    
    def scale(self, target_workers: int):
        """Scale the number of workers.
        
        Args:
            target_workers: Target number of workers
        """
        with self._lock:
            target_workers = max(self.min_workers, min(target_workers, self.max_workers))
            current_workers = len(self.workers)
            
            if target_workers > current_workers:
                # Scale up
                for _ in range(target_workers - current_workers):
                    self._spawn_worker()
                logger.info(f"Scaled up to {target_workers} workers")
            elif target_workers < current_workers:
                # Scale down
                workers_to_remove = current_workers - target_workers
                for _ in range(workers_to_remove):
                    self._remove_worker()
                logger.info(f"Scaled down to {target_workers} workers")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.
        
        Returns:
            Dictionary containing pool statistics
        """
        with self._lock:
            worker_stats = []
            for worker_id, worker_info in self.workers.items():
                worker = worker_info["worker"]
                process = worker_info["process"]
                
                worker_stats.append({
                    "worker_id": worker_id,
                    "status": worker.status.value if hasattr(worker, 'status') else "unknown",
                    "is_alive": process.is_alive()
                })
            
            avg_processing_time = (
                self._stats["total_processing_time"] / self._stats["completed_tasks"]
                if self._stats["completed_tasks"] > 0 else 0
            )
            
            return {
                "active_workers": len(self.workers),
                "min_workers": self.min_workers,
                "max_workers": self.max_workers,
                "total_tasks": self._stats["total_tasks"],
                "completed_tasks": self._stats["completed_tasks"],
                "failed_tasks": self._stats["failed_tasks"],
                "average_processing_time": avg_processing_time,
                "pending_tasks": self.task_queue.qsize(),
                "worker_details": worker_stats
            }
    
    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """Shutdown the worker pool.
        
        Args:
            wait: Whether to wait for workers to finish
            timeout: Maximum time to wait for shutdown
        """
        logger.info("Shutting down worker pool...")
        
        with self._lock:
            self._shutdown = True
            
            # Send poison pills to all workers
            for _ in self.workers:
                self.task_queue.put(None)
        
        # Wait for workers to finish
        if wait:
            end_time = time.time() + timeout
            for worker_id, worker_info in list(self.workers.items()):
                remaining = end_time - time.time()
                if remaining > 0:
                    worker_info["process"].join(timeout=remaining)
        
        # Force terminate remaining workers
        with self._lock:
            for worker_id, worker_info in list(self.workers.items()):
                if worker_info["process"].is_alive():
                    logger.warning(f"Force terminating worker {worker_id}")
                    worker_info["process"].terminate()
        
        # Shutdown executor
        self._executor.shutdown(wait=wait)
        
        logger.info("Worker pool shutdown complete")
    
    def _spawn_worker(self):
        """Spawn a new worker process."""
        try:
            # Create worker instance
            worker = self.worker_class(**self.worker_kwargs)
            
            # Create process
            process = multiprocessing.Process(
                target=worker.run,
                args=(self.task_queue, self.result_queue),
                daemon=True
            )
            process.start()
            
            # Track worker
            with self._lock:
                self.workers[worker.worker_id] = {
                    "worker": worker,
                    "process": process,
                    "start_time": time.time()
                }
            
            logger.info(f"Spawned worker {worker.worker_id}")
            
        except Exception as e:
            logger.error(f"Failed to spawn worker: {e}")
    
    def _remove_worker(self):
        """Remove a worker from the pool."""
        with self._lock:
            if not self.workers:
                return
            
            # Choose oldest worker to remove
            worker_id = min(self.workers.keys(), 
                          key=lambda k: self.workers[k]["start_time"])
            
            # Send poison pill
            self.task_queue.put(None)
            
            # Remove from tracking
            worker_info = self.workers.pop(worker_id, None)
            if worker_info:
                logger.info(f"Removed worker {worker_id}")
    
    def _monitor_workers(self):
        """Monitor worker health and restart failed workers."""
        while not self._shutdown:
            try:
                with self._lock:
                    # Check worker health
                    dead_workers = []
                    for worker_id, worker_info in self.workers.items():
                        if not worker_info["process"].is_alive():
                            dead_workers.append(worker_id)
                    
                    # Remove dead workers
                    for worker_id in dead_workers:
                        logger.warning(f"Worker {worker_id} died, removing...")
                        self.workers.pop(worker_id, None)
                    
                    # Maintain minimum workers
                    current_workers = len(self.workers)
                    if current_workers < self.min_workers:
                        for _ in range(self.min_workers - current_workers):
                            self._spawn_worker()
                
                time.sleep(5.0)  # Health check interval
                
            except Exception as e:
                logger.error(f"Error in worker monitor: {e}")
                time.sleep(5.0)
    
    def _handle_results(self):
        """Handle results from workers."""
        while not self._shutdown:
            try:
                # Get result with timeout
                try:
                    result = self.result_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                if result is None:
                    continue
                
                # Process result
                task_id = result.get("task", {}).get("id") if isinstance(result.get("task"), dict) else getattr(result.get("task"), "id", None)
                
                if not task_id:
                    logger.warning("Received result without task ID")
                    continue
                
                with self._lock:
                    future = self._pending_tasks.pop(task_id, None)
                    
                    if result["success"]:
                        self._stats["completed_tasks"] += 1
                        self._stats["total_processing_time"] += result.get("processing_time", 0)
                        
                        if future:
                            future.set_result(result["result"])
                    else:
                        self._stats["failed_tasks"] += 1
                        
                        if future:
                            future.set_exception(Exception(result.get("error", "Unknown error")))
                
                logger.debug(f"Processed result for task {task_id}")
                
            except Exception as e:
                logger.error(f"Error handling result: {e}")


class AdaptiveWorkerPool(WorkerPool):
    """Worker pool with adaptive scaling based on load."""
    
    def __init__(self, *args, scale_up_threshold: float = 0.8, 
                 scale_down_threshold: float = 0.2, **kwargs):
        """Initialize adaptive worker pool.
        
        Args:
            scale_up_threshold: Queue utilization to trigger scale up
            scale_down_threshold: Queue utilization to trigger scale down
        """
        super().__init__(*args, **kwargs)
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self._auto_scale_thread = threading.Thread(target=self._auto_scale, daemon=True)
    
    def start(self):
        """Start the adaptive worker pool."""
        super().start()
        self._auto_scale_thread.start()
    
    def _auto_scale(self):
        """Automatically scale workers based on load."""
        while not self._shutdown:
            try:
                with self._lock:
                    queue_size = self.task_queue.qsize()
                    active_workers = len(self.workers)
                    
                    if active_workers > 0:
                        utilization = queue_size / active_workers
                        
                        if utilization > self.scale_up_threshold and active_workers < self.max_workers:
                            # Scale up
                            self.scale(active_workers + 1)
                        elif utilization < self.scale_down_threshold and active_workers > self.min_workers:
                            # Scale down
                            self.scale(active_workers - 1)
                
                time.sleep(10.0)  # Auto-scale interval
                
            except Exception as e:
                logger.error(f"Error in auto-scale: {e}")
                time.sleep(10.0)