"""Unit tests for the coordinator implementation."""

import time
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import timedelta

from core.distributed import (
    Coordinator, Task, TaskPriority, BaseWorker, WorkerPool
)


class TestCoordinator(unittest.TestCase):
    """Test cases for Coordinator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = Coordinator(max_workers=5, max_queue_size=100)
        
        # Create mock worker class
        self.mock_worker_class = Mock(spec=BaseWorker)
        self.mock_worker_class.__name__ = "MockWorker"
    
    def tearDown(self):
        """Clean up after tests."""
        self.coordinator.shutdown(wait=False)
    
    def test_coordinator_initialization(self):
        """Test coordinator initializes correctly."""
        self.assertEqual(self.coordinator.max_workers, 5)
        self.assertIsNotNone(self.coordinator.task_queue)
        self.assertEqual(len(self.coordinator.worker_pools), 0)
        self.assertEqual(len(self.coordinator.results), 0)
        self.assertFalse(self.coordinator._shutdown)
    
    def test_register_worker_type(self):
        """Test registering a worker type."""
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class,
            min_workers=2,
            max_workers=4
        )
        
        self.assertIn("compute", self.coordinator.worker_pools)
        pool = self.coordinator.worker_pools["compute"]
        self.assertEqual(pool.min_workers, 2)
        self.assertEqual(pool.max_workers, 4)
    
    def test_register_worker_type_update(self):
        """Test updating an existing worker type."""
        # Register initial
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class,
            min_workers=1,
            max_workers=3
        )
        
        # Update registration
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class,
            min_workers=2,
            max_workers=5
        )
        
        pool = self.coordinator.worker_pools["compute"]
        self.assertEqual(pool.min_workers, 2)
        self.assertEqual(pool.max_workers, 5)
    
    def test_submit_task_no_worker(self):
        """Test submitting task without registered worker."""
        task = Task(type="unknown")
        
        with self.assertRaises(ValueError) as context:
            self.coordinator.submit_task(task)
        
        self.assertIn("No worker registered", str(context.exception))
    
    @patch('core.distributed.coordinator.WorkerPool')
    def test_submit_task_success(self, mock_pool_class):
        """Test successful task submission."""
        # Set up mock pool
        mock_pool = Mock()
        mock_pool.execute_task.return_value = "result"
        mock_pool_class.return_value = mock_pool
        
        # Register worker type
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class
        )
        
        # Submit task
        task = Task(id="test-1", type="compute", data=10)
        task_id = self.coordinator.submit_task(task)
        
        self.assertEqual(task_id, "test-1")
        self.assertEqual(self.coordinator._stats["tasks_submitted"], 1)
    
    def test_submit_task_with_callback(self):
        """Test submitting task with callback."""
        callback_called = False
        callback_result = None
        
        def callback(result):
            nonlocal callback_called, callback_result
            callback_called = True
            callback_result = result
        
        # Register mock worker
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class
        )
        
        # Submit task with callback
        task = Task(type="compute")
        task_id = self.coordinator.submit_task(task, callback=callback)
        
        self.assertIn(task_id, self.coordinator.result_callbacks)
        self.assertEqual(len(self.coordinator.result_callbacks[task_id]), 1)
    
    def test_submit_batch(self):
        """Test submitting multiple tasks as batch."""
        # Register worker
        self.coordinator.register_worker_type(
            task_type="compute",
            worker_class=self.mock_worker_class
        )
        
        # Create batch of tasks
        tasks = [
            Task(id=f"batch-{i}", type="compute", data=i)
            for i in range(5)
        ]
        
        # Submit batch
        task_ids = self.coordinator.submit_batch(tasks)
        
        self.assertEqual(len(task_ids), 5)
        self.assertEqual(self.coordinator._stats["tasks_submitted"], 5)
        for i, task_id in enumerate(task_ids):
            self.assertEqual(task_id, f"batch-{i}")
    
    def test_cancel_task(self):
        """Test cancelling a pending task."""
        # Add task to queue
        task = Task(id="cancel-me")
        self.coordinator.task_queue.put(task)
        
        # Cancel task
        result = self.coordinator.cancel_task("cancel-me")
        self.assertTrue(result)
        self.assertEqual(self.coordinator.task_queue.size(), 0)
        
        # Try to cancel non-existent task
        result = self.coordinator.cancel_task("not-found")
        self.assertFalse(result)
    
    def test_scale_workers(self):
        """Test scaling workers for a task type."""
        # Register worker type
        mock_pool = Mock()
        self.coordinator.worker_pools["compute"] = mock_pool
        
        # Scale workers
        self.coordinator.scale_workers("compute", 8)
        mock_pool.scale.assert_called_once_with(8)
    
    def test_scale_workers_invalid_type(self):
        """Test scaling workers for invalid task type."""
        with self.assertRaises(ValueError) as context:
            self.coordinator.scale_workers("unknown", 5)
        
        self.assertIn("No worker pool", str(context.exception))
    
    def test_get_status(self):
        """Test getting coordinator status."""
        # Register worker and add some stats
        mock_pool = Mock()
        mock_pool.get_stats.return_value = {
            "active_workers": 3,
            "total_tasks": 100
        }
        self.coordinator.worker_pools["compute"] = mock_pool
        
        self.coordinator._stats["tasks_submitted"] = 50
        self.coordinator._stats["tasks_completed"] = 45
        self.coordinator._stats["tasks_failed"] = 5
        
        status = self.coordinator.get_status()
        
        self.assertTrue(status["active"])
        self.assertIn("queue_stats", status)
        self.assertIn("compute", status["worker_pools"])
        self.assertEqual(status["coordinator_stats"]["tasks_submitted"], 50)
        self.assertEqual(status["coordinator_stats"]["tasks_completed"], 45)
        self.assertEqual(status["coordinator_stats"]["tasks_failed"], 5)
    
    def test_shutdown(self):
        """Test coordinator shutdown."""
        # Register worker
        mock_pool = Mock()
        self.coordinator.worker_pools["compute"] = mock_pool
        
        # Shutdown
        self.coordinator.shutdown(wait=False)
        
        self.assertTrue(self.coordinator._shutdown)
        mock_pool.shutdown.assert_called_once_with(wait=False)
        self.assertEqual(self.coordinator.task_queue.size(), 0)
    
    def test_process_task_success(self):
        """Test successful task processing."""
        # Set up mock pool
        mock_pool = Mock()
        mock_pool.execute_task.return_value = 42
        self.coordinator.worker_pools["compute"] = mock_pool
        
        # Process task
        task = Task(id="test-task", type="compute", data=21)
        self.coordinator._process_task(task)
        
        # Check result
        self.assertIn("test-task", self.coordinator.results)
        result = self.coordinator.results["test-task"]
        self.assertTrue(result.success)
        self.assertEqual(result.result, 42)
        self.assertGreater(result.processing_time, 0)
        
        # Check stats
        self.assertEqual(self.coordinator._stats["tasks_completed"], 1)
        self.assertEqual(self.coordinator._stats["tasks_failed"], 0)
    
    def test_process_task_failure_with_retry(self):
        """Test task failure with retry."""
        # Set up mock pool to fail
        mock_pool = Mock()
        mock_pool.execute_task.side_effect = Exception("Task failed")
        self.coordinator.worker_pools["compute"] = mock_pool
        
        # Process task with retries available
        task = Task(
            id="retry-task",
            type="compute",
            retry_count=0,
            max_retries=3,
            priority=TaskPriority.NORMAL
        )
        
        self.coordinator._process_task(task)
        
        # Check task was resubmitted
        self.assertEqual(task.retry_count, 1)
        self.assertEqual(task.priority, TaskPriority.LOW)
        self.assertEqual(self.coordinator._stats["tasks_retried"], 1)
    
    def test_process_task_failure_no_retry(self):
        """Test task failure with no retries left."""
        # Set up mock pool to fail
        mock_pool = Mock()
        mock_pool.execute_task.side_effect = Exception("Task failed")
        self.coordinator.worker_pools["compute"] = mock_pool
        
        # Process task with no retries left
        task = Task(
            id="fail-task",
            type="compute",
            retry_count=3,
            max_retries=3
        )
        
        self.coordinator._process_task(task)
        
        # Check result
        self.assertIn("fail-task", self.coordinator.results)
        result = self.coordinator.results["fail-task"]
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Task failed")
        
        # Check stats
        self.assertEqual(self.coordinator._stats["tasks_failed"], 1)
    
    def test_execute_callbacks(self):
        """Test callback execution."""
        callback_results = []
        
        def callback1(result):
            callback_results.append(("cb1", result.task_id))
        
        def callback2(result):
            callback_results.append(("cb2", result.task_id))
        
        # Add callbacks
        self.coordinator.result_callbacks["test-task"] = [callback1, callback2]
        
        # Create result
        from core.distributed.coordinator import TaskResult
        result = TaskResult(task_id="test-task", success=True)
        self.coordinator.results["test-task"] = result
        
        # Execute callbacks
        self.coordinator._execute_callbacks("test-task")
        
        # Check callbacks were called
        self.assertEqual(len(callback_results), 2)
        self.assertEqual(callback_results[0], ("cb1", "test-task"))
        self.assertEqual(callback_results[1], ("cb2", "test-task"))
        
        # Check callbacks were removed
        self.assertNotIn("test-task", self.coordinator.result_callbacks)
    
    def test_result_cleanup(self):
        """Test old result cleanup."""
        from core.distributed.coordinator import TaskResult
        from datetime import datetime
        
        # Create old and new results
        old_result = TaskResult(task_id="old", success=True)
        old_result.timestamp = datetime.now() - timedelta(hours=2)
        
        new_result = TaskResult(task_id="new", success=True)
        
        self.coordinator.results["old"] = old_result
        self.coordinator.results["new"] = new_result
        
        # Run cleanup
        self.coordinator._cleanup_loop()
        
        # Old result should be removed
        self.assertNotIn("old", self.coordinator.results)
        self.assertIn("new", self.coordinator.results)


class TestTaskResult(unittest.TestCase):
    """Test cases for TaskResult class."""
    
    def test_task_result_success(self):
        """Test successful task result."""
        from core.distributed.coordinator import TaskResult
        
        result = TaskResult(
            task_id="test-1",
            success=True,
            result=42,
            worker_id="worker-1",
            processing_time=1.5
        )
        
        self.assertEqual(result.task_id, "test-1")
        self.assertTrue(result.success)
        self.assertEqual(result.result, 42)
        self.assertIsNone(result.error)
        self.assertEqual(result.worker_id, "worker-1")
        self.assertEqual(result.processing_time, 1.5)
        self.assertIsNotNone(result.timestamp)
    
    def test_task_result_failure(self):
        """Test failed task result."""
        from core.distributed.coordinator import TaskResult
        
        result = TaskResult(
            task_id="test-2",
            success=False,
            error="Task failed"
        )
        
        self.assertEqual(result.task_id, "test-2")
        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertEqual(result.error, "Task failed")
        self.assertIsNone(result.worker_id)
        self.assertEqual(result.processing_time, 0.0)


if __name__ == "__main__":
    unittest.main()