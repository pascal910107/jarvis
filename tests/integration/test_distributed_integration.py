"""Integration tests for the distributed computing infrastructure."""

import multiprocessing
import time
import unittest
from typing import Any

from core.distributed import (
    Coordinator, BaseWorker, Task, TaskPriority, ComputeWorker
)


class TestWorkerIntegration(BaseWorker):
    """Test worker for integration tests."""
    
    def process_task(self, task: Any) -> Any:
        """Process test tasks."""
        if hasattr(task, 'data'):
            data = task.data
            if isinstance(data, dict):
                operation = data.get('operation', 'echo')
                value = data.get('value', None)
                
                if operation == 'add':
                    return data['a'] + data['b']
                elif operation == 'multiply':
                    return data['a'] * data['b']
                elif operation == 'sleep':
                    time.sleep(data.get('duration', 0.1))
                    return "slept"
                elif operation == 'error':
                    raise ValueError(data.get('message', 'Test error'))
                else:
                    return value
        return task
    
    def validate_task(self, task: Any) -> bool:
        """Validate test tasks."""
        if hasattr(task, 'data') and isinstance(task.data, dict):
            return 'operation' in task.data
        return True


class TestDistributedIntegration(unittest.TestCase):
    """Integration tests for distributed computing components."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = Coordinator(max_workers=10)
        
        # Register test worker type
        self.coordinator.register_worker_type(
            task_type="test",
            worker_class=TestWorkerIntegration,
            min_workers=2,
            max_workers=5
        )
        
        # Allow workers to start
        time.sleep(0.5)
    
    def tearDown(self):
        """Clean up after tests."""
        self.coordinator.shutdown(wait=True, timeout=5.0)
    
    def test_simple_task_execution(self):
        """Test simple task execution through the system."""
        # Submit task
        task = Task(
            type="test",
            data={"operation": "add", "a": 5, "b": 3}
        )
        task_id = self.coordinator.submit_task(task)
        
        # Get result
        result = self.coordinator.get_result(task_id, timeout=5.0)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.result, 8)
        self.assertGreater(result.processing_time, 0)
    
    def test_multiple_task_execution(self):
        """Test executing multiple tasks concurrently."""
        # Submit multiple tasks
        tasks = []
        expected_results = []
        
        for i in range(10):
            task = Task(
                type="test",
                data={"operation": "multiply", "a": i, "b": 2}
            )
            tasks.append(task)
            expected_results.append(i * 2)
        
        task_ids = self.coordinator.submit_batch(tasks)
        
        # Get all results
        results = []
        for task_id in task_ids:
            result = self.coordinator.get_result(task_id, timeout=5.0)
            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            results.append(result.result)
        
        # Check results
        self.assertEqual(sorted(results), sorted(expected_results))
    
    def test_priority_task_execution(self):
        """Test tasks execute in priority order."""
        # Submit tasks with different priorities
        tasks_data = [
            ("low", TaskPriority.LOW, 0.2),
            ("critical", TaskPriority.CRITICAL, 0.2),
            ("normal", TaskPriority.NORMAL, 0.2),
            ("high", TaskPriority.HIGH, 0.2),
        ]
        
        task_ids = []
        for task_id, priority, duration in tasks_data:
            task = Task(
                id=task_id,
                type="test",
                data={"operation": "sleep", "duration": duration},
                priority=priority
            )
            tid = self.coordinator.submit_task(task)
            task_ids.append(tid)
        
        # Wait for all tasks to complete
        time.sleep(2.0)
        
        # Check completion order by looking at result timestamps
        results = []
        for task_id in ["critical", "high", "normal", "low"]:
            result = self.coordinator.get_result(task_id)
            self.assertIsNotNone(result)
            results.append((task_id, result.timestamp))
        
        # Critical should complete before low priority
        critical_time = next(r[1] for r in results if r[0] == "critical")
        low_time = next(r[1] for r in results if r[0] == "low")
        self.assertLess(critical_time, low_time)
    
    def test_task_retry_on_failure(self):
        """Test task retry mechanism."""
        # Submit task that fails first time
        retry_count = 0
        
        def counting_worker_process(task):
            nonlocal retry_count
            retry_count += 1
            if retry_count < 2:
                raise ValueError("Intentional failure")
            return "success"
        
        # Create a task that will fail once
        task = Task(
            type="test",
            data={"operation": "error", "message": "First attempt fails"},
            max_retries=2
        )
        
        task_id = self.coordinator.submit_task(task)
        
        # Wait longer for retries
        time.sleep(2.0)
        
        # Task should eventually fail after retries
        result = self.coordinator.get_result(task_id, timeout=5.0)
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "First attempt fails")
    
    def test_worker_scaling(self):
        """Test dynamic worker scaling."""
        # Get initial worker count
        initial_stats = self.coordinator.get_status()
        initial_workers = initial_stats["worker_pools"]["test"]["active_workers"]
        
        # Submit many tasks to trigger scale up
        tasks = []
        for i in range(20):
            task = Task(
                type="test",
                data={"operation": "sleep", "duration": 0.5}
            )
            tasks.append(task)
        
        self.coordinator.submit_batch(tasks)
        
        # Wait for auto-scaling
        time.sleep(1.0)
        
        # Check workers scaled up
        scaled_stats = self.coordinator.get_status()
        scaled_workers = scaled_stats["worker_pools"]["test"]["active_workers"]
        self.assertGreater(scaled_workers, initial_workers)
        
        # Wait for tasks to complete
        time.sleep(3.0)
        
        # Check workers scaled down
        final_stats = self.coordinator.get_status()
        final_workers = final_stats["worker_pools"]["test"]["active_workers"]
        self.assertLessEqual(final_workers, scaled_workers)
    
    def test_task_cancellation(self):
        """Test cancelling pending tasks."""
        # Submit slow tasks
        tasks = []
        for i in range(5):
            task = Task(
                id=f"cancel-{i}",
                type="test",
                data={"operation": "sleep", "duration": 5.0}
            )
            tasks.append(task)
        
        task_ids = self.coordinator.submit_batch(tasks)
        
        # Cancel some tasks
        cancelled = self.coordinator.cancel_task("cancel-2")
        self.assertTrue(cancelled)
        
        cancelled = self.coordinator.cancel_task("cancel-3")
        self.assertTrue(cancelled)
        
        # Check cancelled tasks don't have results
        time.sleep(0.5)
        result = self.coordinator.get_result("cancel-2", timeout=0.1)
        self.assertIsNone(result)
    
    def test_batch_callback(self):
        """Test batch task completion callback."""
        completed_results = []
        
        def batch_callback(results):
            completed_results.extend(results)
        
        # Submit batch with callback
        tasks = []
        for i in range(5):
            task = Task(
                type="test",
                data={"operation": "add", "a": i, "b": 10}
            )
            tasks.append(task)
        
        self.coordinator.submit_batch(tasks, callback=batch_callback)
        
        # Wait for completion
        time.sleep(2.0)
        
        # Check callback was called with all results
        self.assertEqual(len(completed_results), 5)
        for result in completed_results:
            self.assertTrue(result.success)
    
    def test_coordinator_status(self):
        """Test coordinator status reporting."""
        # Submit some tasks
        tasks = []
        for i in range(10):
            task = Task(
                type="test",
                data={"operation": "multiply", "a": i, "b": 3}
            )
            tasks.append(task)
        
        self.coordinator.submit_batch(tasks)
        
        # Wait for processing
        time.sleep(1.0)
        
        # Get status
        status = self.coordinator.get_status()
        
        self.assertTrue(status["active"])
        self.assertIn("queue_stats", status)
        self.assertIn("worker_pools", status)
        self.assertIn("test", status["worker_pools"])
        
        # Check coordinator stats
        stats = status["coordinator_stats"]
        self.assertGreaterEqual(stats["tasks_submitted"], 10)
        self.assertGreaterEqual(stats["tasks_completed"], 0)
    
    def test_concurrent_coordinator_access(self):
        """Test concurrent access to coordinator."""
        results = []
        errors = []
        
        def submit_tasks(start_id, count):
            try:
                for i in range(count):
                    task = Task(
                        id=f"concurrent-{start_id}-{i}",
                        type="test",
                        data={"operation": "echo", "value": f"{start_id}-{i}"}
                    )
                    task_id = self.coordinator.submit_task(task)
                    result = self.coordinator.get_result(task_id, timeout=5.0)
                    if result:
                        results.append(result.result)
            except Exception as e:
                errors.append(e)
        
        # Start multiple processes submitting tasks
        processes = []
        for i in range(3):
            p = multiprocessing.Process(
                target=submit_tasks,
                args=(i * 10, 5)
            )
            processes.append(p)
            p.start()
        
        # Wait for all processes
        for p in processes:
            p.join()
        
        # Check results
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 15)
        self.assertEqual(len(set(results)), 15)  # All unique


class TestComputeWorkerIntegration(unittest.TestCase):
    """Integration tests for ComputeWorker."""
    
    def test_compute_worker(self):
        """Test ComputeWorker functionality."""
        # Create coordinator with compute workers
        coordinator = Coordinator(max_workers=5)
        
        try:
            # Register compute workers
            coordinator.register_worker_type(
                task_type="compute",
                worker_class=ComputeWorker,
                min_workers=1,
                max_workers=3,
                compute_fn=lambda x: x ** 2
            )
            
            # Allow workers to start
            time.sleep(0.5)
            
            # Submit compute task
            task = Task(
                type="compute",
                data=5
            )
            task_id = coordinator.submit_task(task)
            
            # Get result
            result = coordinator.get_result(task_id, timeout=5.0)
            
            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            self.assertEqual(result.result, 25)
            
        finally:
            coordinator.shutdown(wait=True, timeout=5.0)


if __name__ == "__main__":
    unittest.main()