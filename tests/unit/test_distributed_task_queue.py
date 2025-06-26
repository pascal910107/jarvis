"""Unit tests for the task queue implementation."""

import threading
import time
import unittest
from datetime import datetime, timedelta

from core.distributed import TaskQueue, Task, TaskPriority


class TestTaskQueue(unittest.TestCase):
    """Test cases for TaskQueue class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.queue = TaskQueue()
    
    def test_queue_initialization(self):
        """Test queue initializes correctly."""
        self.assertEqual(self.queue.size(), 0)
        self.assertTrue(self.queue.is_empty())
        self.assertFalse(self.queue.is_full())
    
    def test_queue_with_max_size(self):
        """Test queue with maximum size."""
        queue = TaskQueue(max_size=5)
        self.assertEqual(queue.max_size, 5)
        
        # Fill queue
        for i in range(5):
            task = Task(id=f"test-{i}")
            self.assertTrue(queue.put(task))
        
        self.assertTrue(queue.is_full())
        
        # Try to add more
        task = Task(id="test-overflow")
        self.assertFalse(queue.put(task, block=False))
    
    def test_put_and_get_single_task(self):
        """Test adding and retrieving a single task."""
        task = Task(id="test-1", data="test data")
        
        # Add task
        self.assertTrue(self.queue.put(task))
        self.assertEqual(self.queue.size(), 1)
        self.assertFalse(self.queue.is_empty())
        
        # Get task
        retrieved = self.queue.get()
        self.assertEqual(retrieved.id, "test-1")
        self.assertEqual(retrieved.data, "test data")
        self.assertEqual(self.queue.size(), 0)
        self.assertTrue(self.queue.is_empty())
    
    def test_priority_ordering(self):
        """Test tasks are retrieved in priority order."""
        # Add tasks with different priorities
        tasks = [
            Task(id="low", priority=TaskPriority.LOW),
            Task(id="critical", priority=TaskPriority.CRITICAL),
            Task(id="normal", priority=TaskPriority.NORMAL),
            Task(id="high", priority=TaskPriority.HIGH),
            Task(id="background", priority=TaskPriority.BACKGROUND),
        ]
        
        for task in tasks:
            self.queue.put(task)
        
        # Retrieve tasks - should come out in priority order
        retrieved_ids = []
        while not self.queue.is_empty():
            task = self.queue.get()
            retrieved_ids.append(task.id)
        
        expected_order = ["critical", "high", "normal", "low", "background"]
        self.assertEqual(retrieved_ids, expected_order)
    
    def test_same_priority_fifo(self):
        """Test tasks with same priority are FIFO."""
        # Add tasks with same priority but different creation times
        tasks = []
        for i in range(5):
            task = Task(id=f"task-{i}", priority=TaskPriority.NORMAL)
            tasks.append(task)
            self.queue.put(task)
            time.sleep(0.001)  # Ensure different timestamps
        
        # Retrieve tasks
        retrieved_ids = []
        while not self.queue.is_empty():
            task = self.queue.get()
            retrieved_ids.append(task.id)
        
        expected_order = [f"task-{i}" for i in range(5)]
        self.assertEqual(retrieved_ids, expected_order)
    
    def test_peek(self):
        """Test peeking at the next task."""
        task1 = Task(id="normal", priority=TaskPriority.NORMAL)
        task2 = Task(id="high", priority=TaskPriority.HIGH)
        
        self.queue.put(task1)
        self.queue.put(task2)
        
        # Peek should return high priority task
        peeked = self.queue.peek()
        self.assertEqual(peeked.id, "high")
        
        # Queue size should not change
        self.assertEqual(self.queue.size(), 2)
        
        # Get should return the same task
        retrieved = self.queue.get()
        self.assertEqual(retrieved.id, "high")
        self.assertEqual(self.queue.size(), 1)
    
    def test_remove_task(self):
        """Test removing a specific task."""
        tasks = [
            Task(id="task-1"),
            Task(id="task-2"),
            Task(id="task-3"),
        ]
        
        for task in tasks:
            self.queue.put(task)
        
        # Remove middle task
        self.assertTrue(self.queue.remove("task-2"))
        self.assertEqual(self.queue.size(), 2)
        
        # Try to remove non-existent task
        self.assertFalse(self.queue.remove("task-4"))
        
        # Check remaining tasks
        remaining_ids = []
        while not self.queue.is_empty():
            task = self.queue.get()
            remaining_ids.append(task.id)
        
        self.assertEqual(remaining_ids, ["task-1", "task-3"])
    
    def test_update_priority(self):
        """Test updating task priority."""
        task1 = Task(id="task-1", priority=TaskPriority.LOW)
        task2 = Task(id="task-2", priority=TaskPriority.NORMAL)
        
        self.queue.put(task1)
        self.queue.put(task2)
        
        # Update task-1 to high priority
        self.assertTrue(self.queue.update_priority("task-1", TaskPriority.HIGH))
        
        # Task-1 should now come first
        retrieved = self.queue.get()
        self.assertEqual(retrieved.id, "task-1")
        self.assertEqual(retrieved.priority, TaskPriority.HIGH)
    
    def test_expired_tasks(self):
        """Test removal of expired tasks."""
        # Create expired task
        expired_task = Task(
            id="expired",
            deadline=datetime.now() - timedelta(seconds=1)
        )
        
        # Create valid task
        valid_task = Task(
            id="valid",
            deadline=datetime.now() + timedelta(minutes=1)
        )
        
        self.queue.put(expired_task)
        self.queue.put(valid_task)
        
        # Get should remove expired task and return valid one
        retrieved = self.queue.get()
        self.assertEqual(retrieved.id, "valid")
        self.assertTrue(self.queue.is_empty())
        
        # Check stats
        stats = self.queue.get_stats()
        self.assertEqual(stats["total_expired"], 1)
    
    def test_clear_queue(self):
        """Test clearing the queue."""
        for i in range(5):
            task = Task(id=f"task-{i}")
            self.queue.put(task)
        
        self.assertEqual(self.queue.size(), 5)
        
        self.queue.clear()
        
        self.assertEqual(self.queue.size(), 0)
        self.assertTrue(self.queue.is_empty())
    
    def test_get_stats(self):
        """Test getting queue statistics."""
        # Add various priority tasks
        priorities = [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.NORMAL,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
        ]
        
        for i, priority in enumerate(priorities):
            task = Task(id=f"task-{i}", priority=priority)
            self.queue.put(task)
        
        stats = self.queue.get_stats()
        
        self.assertEqual(stats["current_size"], 7)
        self.assertEqual(stats["total_enqueued"], 7)
        self.assertEqual(stats["total_dequeued"], 0)
        self.assertEqual(stats["priority_distribution"]["CRITICAL"], 1)
        self.assertEqual(stats["priority_distribution"]["HIGH"], 2)
        self.assertEqual(stats["priority_distribution"]["NORMAL"], 3)
        self.assertEqual(stats["priority_distribution"]["LOW"], 1)
    
    def test_get_tasks_by_type(self):
        """Test getting tasks by type."""
        tasks = [
            Task(id="compute-1", type="compute"),
            Task(id="io-1", type="io"),
            Task(id="compute-2", type="compute"),
            Task(id="io-2", type="io"),
            Task(id="compute-3", type="compute"),
        ]
        
        for task in tasks:
            self.queue.put(task)
        
        compute_tasks = self.queue.get_tasks_by_type("compute")
        io_tasks = self.queue.get_tasks_by_type("io")
        
        self.assertEqual(len(compute_tasks), 3)
        self.assertEqual(len(io_tasks), 2)
        
        compute_ids = [t.id for t in compute_tasks]
        self.assertIn("compute-1", compute_ids)
        self.assertIn("compute-2", compute_ids)
        self.assertIn("compute-3", compute_ids)
    
    def test_thread_safety(self):
        """Test queue operations are thread-safe."""
        results = []
        errors = []
        
        def producer(start, count):
            try:
                for i in range(start, start + count):
                    task = Task(id=f"task-{i}")
                    self.queue.put(task)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def consumer(count):
            try:
                for _ in range(count):
                    task = self.queue.get(timeout=5.0)
                    if task:
                        results.append(task.id)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        # Start multiple producers and consumers
        threads = []
        
        # Producers
        for i in range(3):
            t = threading.Thread(target=producer, args=(i * 10, 10))
            threads.append(t)
            t.start()
        
        # Consumers
        for _ in range(2):
            t = threading.Thread(target=consumer, args=(15,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check results
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 30)
        self.assertEqual(len(set(results)), 30)  # All unique
    
    def test_blocking_get_timeout(self):
        """Test blocking get with timeout."""
        start_time = time.time()
        result = self.queue.get(timeout=0.1)
        elapsed = time.time() - start_time
        
        self.assertIsNone(result)
        self.assertGreater(elapsed, 0.09)
        self.assertLess(elapsed, 0.2)
    
    def test_blocking_put_timeout(self):
        """Test blocking put with timeout on full queue."""
        queue = TaskQueue(max_size=1)
        
        # Fill queue
        task1 = Task(id="task-1")
        self.assertTrue(queue.put(task1))
        
        # Try to add with timeout
        task2 = Task(id="task-2")
        start_time = time.time()
        result = queue.put(task2, timeout=0.1)
        elapsed = time.time() - start_time
        
        self.assertFalse(result)
        self.assertGreater(elapsed, 0.09)
        self.assertLess(elapsed, 0.2)


class TestTask(unittest.TestCase):
    """Test cases for Task class."""
    
    def test_task_creation(self):
        """Test task creation with defaults."""
        task = Task()
        
        self.assertIsNotNone(task.id)
        self.assertEqual(task.type, "generic")
        self.assertIsNone(task.data)
        self.assertEqual(task.priority, TaskPriority.NORMAL)
        self.assertIsInstance(task.created_at, datetime)
        self.assertIsNone(task.deadline)
        self.assertEqual(task.retry_count, 0)
        self.assertEqual(task.max_retries, 3)
        self.assertEqual(task.metadata, {})
    
    def test_task_with_custom_values(self):
        """Test task creation with custom values."""
        deadline = datetime.now() + timedelta(hours=1)
        metadata = {"key": "value"}
        
        task = Task(
            id="custom-id",
            type="compute",
            data={"x": 10, "y": 20},
            priority=TaskPriority.HIGH,
            deadline=deadline,
            retry_count=1,
            max_retries=5,
            metadata=metadata
        )
        
        self.assertEqual(task.id, "custom-id")
        self.assertEqual(task.type, "compute")
        self.assertEqual(task.data, {"x": 10, "y": 20})
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.deadline, deadline)
        self.assertEqual(task.retry_count, 1)
        self.assertEqual(task.max_retries, 5)
        self.assertEqual(task.metadata, metadata)
    
    def test_task_comparison(self):
        """Test task comparison for priority queue."""
        task1 = Task(id="1", priority=TaskPriority.HIGH)
        task2 = Task(id="2", priority=TaskPriority.LOW)
        task3 = Task(id="3", priority=TaskPriority.HIGH)
        
        # Different priorities
        self.assertTrue(task1 < task2)
        self.assertFalse(task2 < task1)
        
        # Same priority, different creation times
        time.sleep(0.001)
        task3.created_at = datetime.now()
        self.assertTrue(task1 < task3)


if __name__ == "__main__":
    unittest.main()