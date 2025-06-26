"""Unit tests for the base worker implementation."""

import multiprocessing
import time
import unittest
from unittest.mock import Mock, patch
from datetime import datetime

from core.distributed import BaseWorker, WorkerStatus, Task, TaskPriority


class TestWorker(BaseWorker):
    """Test implementation of BaseWorker."""
    
    def process_task(self, task):
        """Simple task processing."""
        if hasattr(task, 'data'):
            return task.data * 2
        return task * 2
    
    def validate_task(self, task):
        """Validate task is a number."""
        if hasattr(task, 'data'):
            return isinstance(task.data, (int, float))
        return isinstance(task, (int, float))


class TestBaseWorker(unittest.TestCase):
    """Test cases for BaseWorker class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.worker = TestWorker()
    
    def test_worker_initialization(self):
        """Test worker initializes correctly."""
        self.assertIsNotNone(self.worker.worker_id)
        self.assertIsNotNone(self.worker.name)
        self.assertEqual(self.worker.status, WorkerStatus.IDLE)
        self.assertEqual(self.worker.metrics.tasks_completed, 0)
        self.assertIsNone(self.worker.current_task)
    
    def test_worker_with_custom_id_and_name(self):
        """Test worker with custom ID and name."""
        worker = TestWorker(worker_id="test-123", name="TestWorker")
        self.assertEqual(worker.worker_id, "test-123")
        self.assertEqual(worker.name, "TestWorker")
    
    def test_process_task(self):
        """Test task processing."""
        result = self.worker.process_task(5)
        self.assertEqual(result, 10)
        
        task = Task(data=7)
        result = self.worker.process_task(task)
        self.assertEqual(result, 14)
    
    def test_validate_task(self):
        """Test task validation."""
        self.assertTrue(self.worker.validate_task(5))
        self.assertTrue(self.worker.validate_task(3.14))
        self.assertFalse(self.worker.validate_task("string"))
        
        task = Task(data=42)
        self.assertTrue(self.worker.validate_task(task))
        
        task = Task(data="invalid")
        self.assertFalse(self.worker.validate_task(task))
    
    def test_pause_and_resume(self):
        """Test worker pause and resume."""
        self.worker.pause()
        self.assertTrue(self.worker._pause_event.is_set())
        
        self.worker.resume()
        self.assertFalse(self.worker._pause_event.is_set())
    
    def test_stop(self):
        """Test worker stop."""
        self.worker.stop()
        self.assertTrue(self.worker._stop_event.is_set())
    
    def test_get_metrics(self):
        """Test getting worker metrics."""
        metrics = self.worker.get_metrics()
        
        self.assertEqual(metrics["worker_id"], self.worker.worker_id)
        self.assertEqual(metrics["name"], self.worker.name)
        self.assertEqual(metrics["status"], WorkerStatus.IDLE.value)
        self.assertEqual(metrics["tasks_completed"], 0)
        self.assertEqual(metrics["tasks_failed"], 0)
        self.assertEqual(metrics["error_count"], 0)
        self.assertEqual(metrics["average_processing_time"], 0)
        self.assertIsNone(metrics["last_task_time"])
    
    def test_worker_run_successful_task(self):
        """Test worker processes tasks successfully."""
        task_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        
        # Add task
        task = Task(id="test-1", data=10)
        task_queue.put(task)
        task_queue.put(None)  # Poison pill
        
        # Run worker
        self.worker.run(task_queue, result_queue)
        
        # Check result
        result = result_queue.get(timeout=1.0)
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 20)
        self.assertEqual(result["task"].id, "test-1")
        self.assertGreater(result["processing_time"], 0)
        
        # Check metrics
        self.assertEqual(self.worker.metrics.tasks_completed, 1)
        self.assertEqual(self.worker.metrics.tasks_failed, 0)
        self.assertIsNotNone(self.worker.metrics.last_task_time)
    
    def test_worker_run_invalid_task(self):
        """Test worker handles invalid tasks."""
        task_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        
        # Add invalid task
        task = Task(id="test-2", data="invalid")
        task_queue.put(task)
        task_queue.put(None)  # Poison pill
        
        # Run worker
        self.worker.run(task_queue, result_queue)
        
        # Check result
        result = result_queue.get(timeout=1.0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Task validation failed")
        self.assertEqual(result["task"].id, "test-2")
    
    def test_worker_run_with_exception(self):
        """Test worker handles exceptions during task processing."""
        # Create worker that throws exception
        class ErrorWorker(BaseWorker):
            def process_task(self, task):
                raise ValueError("Test error")
            
            def validate_task(self, task):
                return True
        
        worker = ErrorWorker()
        task_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        
        # Add task
        task = Task(id="test-3", data=10)
        task_queue.put(task)
        task_queue.put(None)  # Poison pill
        
        # Run worker
        worker.run(task_queue, result_queue)
        
        # Check result
        result = result_queue.get(timeout=1.0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Test error")
        self.assertEqual(result["task"].id, "test-3")
        
        # Check metrics
        self.assertEqual(worker.metrics.tasks_completed, 0)
        self.assertEqual(worker.metrics.tasks_failed, 1)
        self.assertEqual(worker.metrics.error_count, 1)


class TestWorkerStatus(unittest.TestCase):
    """Test cases for WorkerStatus enum."""
    
    def test_worker_status_values(self):
        """Test worker status enum values."""
        self.assertEqual(WorkerStatus.IDLE.value, "idle")
        self.assertEqual(WorkerStatus.BUSY.value, "busy")
        self.assertEqual(WorkerStatus.PAUSED.value, "paused")
        self.assertEqual(WorkerStatus.STOPPED.value, "stopped")
        self.assertEqual(WorkerStatus.ERROR.value, "error")


if __name__ == "__main__":
    unittest.main()