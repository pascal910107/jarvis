"""Tests for the real-time scheduling framework."""

import asyncio
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import pytest

from core.scheduling import (
    Task, TaskPriority, TaskStatus, TaskConstraints,
    PriorityQueue, DeadlineQueue, MultiLevelQueue,
    Scheduler, RealtimeScheduler, SchedulingPolicy,
    PriorityInheritanceProtocol, LatencyMonitor, SchedulingMetrics,
    DeadlineMissedError, PriorityInversionError
)


class TestTask:
    """Test Task class functionality."""
    
    def test_task_creation(self):
        """Test creating a task."""
        def dummy_func(x):
            return x * 2
        
        task = Task(
            name="test_task",
            func=dummy_func,
            args=(5,),
            priority=TaskPriority.HIGH
        )
        
        assert task.name == "test_task"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
        assert task.effective_priority == TaskPriority.HIGH
    
    def test_task_constraints_validation(self):
        """Test task constraints validation."""
        # Valid constraints
        constraints = TaskConstraints(
            deadline=datetime.now() + timedelta(seconds=10),
            max_duration=timedelta(seconds=5),
            is_hard_realtime=True
        )
        errors = constraints.validate()
        assert len(errors) == 0
        
        # Invalid constraints - min_start_time after deadline
        constraints = TaskConstraints(
            deadline=datetime.now() + timedelta(seconds=10),
            min_start_time=datetime.now() + timedelta(seconds=20)
        )
        errors = constraints.validate()
        assert len(errors) > 0
        assert "min_start_time must be before deadline" in errors[0]
    
    def test_priority_boosting(self):
        """Test priority inheritance boosting."""
        task = Task("test", Mock(), priority=TaskPriority.LOW)
        
        # Boost priority
        boosted = task.boost_priority(TaskPriority.HIGH, "donor1")
        assert boosted is True
        assert task.effective_priority == TaskPriority.HIGH
        assert task.metrics.priority_boosts == 1
        
        # Try to boost with lower priority
        boosted = task.boost_priority(TaskPriority.NORMAL, "donor2")
        assert boosted is False
        assert task.effective_priority == TaskPriority.HIGH
        
        # Release boost
        task.release_priority_boost("donor1")
        assert task.effective_priority == TaskPriority.LOW
    
    def test_task_execution(self):
        """Test task execution."""
        result_holder = []
        
        def test_func(value):
            result_holder.append(value)
            return value * 2
        
        task = Task("test", test_func, args=(10,))
        
        # Execute task
        result = task.execute()
        
        assert result == 20
        assert result_holder == [10]
        assert task.status == TaskStatus.COMPLETED
        assert task.result == 20
        assert task.metrics.execution_time_ms is not None
    
    def test_task_execution_failure(self):
        """Test task execution with failure."""
        def failing_func():
            raise ValueError("Test error")
        
        task = Task("failing", failing_func)
        
        with pytest.raises(ValueError):
            task.execute()
        
        assert task.status == TaskStatus.FAILED
        assert task.error is not None
        assert isinstance(task.error, ValueError)
    
    def test_deadline_checking(self):
        """Test deadline checking."""
        # Task with future deadline
        task = Task(
            "test",
            Mock(),
            constraints=TaskConstraints(
                deadline=datetime.now() + timedelta(seconds=10)
            )
        )
        
        assert not task.has_missed_deadline()
        assert not task.is_deadline_approaching(timedelta(seconds=5))
        assert task.is_deadline_approaching(timedelta(seconds=15))
        
        # Task with past deadline
        task = Task(
            "test",
            Mock(),
            constraints=TaskConstraints(
                deadline=datetime.now() - timedelta(seconds=10)
            )
        )
        
        assert task.has_missed_deadline()
    
    def test_task_comparison(self):
        """Test task comparison for queue ordering."""
        task1 = Task("high", Mock(), priority=TaskPriority.HIGH)
        task2 = Task("normal", Mock(), priority=TaskPriority.NORMAL)
        task3 = Task("high_deadline", Mock(), 
                    priority=TaskPriority.HIGH,
                    constraints=TaskConstraints(
                        deadline=datetime.now() + timedelta(seconds=10)
                    ))
        
        # Higher priority comes first
        assert task1 < task2
        
        # With same priority, deadline task comes first
        assert task3 < task1


class TestPriorityQueue:
    """Test PriorityQueue implementation."""
    
    def test_enqueue_dequeue(self):
        """Test basic queue operations."""
        queue = PriorityQueue()
        
        task1 = Task("low", Mock(), priority=TaskPriority.LOW)
        task2 = Task("high", Mock(), priority=TaskPriority.HIGH)
        task3 = Task("normal", Mock(), priority=TaskPriority.NORMAL)
        
        # Enqueue tasks
        queue.enqueue(task1)
        queue.enqueue(task2)
        queue.enqueue(task3)
        
        assert queue.size() == 3
        
        # Dequeue in priority order
        assert queue.dequeue() == task2  # HIGH
        assert queue.dequeue() == task3  # NORMAL
        assert queue.dequeue() == task1  # LOW
        assert queue.dequeue() is None
    
    def test_peek(self):
        """Test peeking at highest priority task."""
        queue = PriorityQueue()
        
        task1 = Task("task1", Mock(), priority=TaskPriority.NORMAL)
        task2 = Task("task2", Mock(), priority=TaskPriority.HIGH)
        
        queue.enqueue(task1)
        assert queue.peek() == task1
        
        queue.enqueue(task2)
        assert queue.peek() == task2
        assert queue.size() == 2  # Peek doesn't remove
    
    def test_remove_specific_task(self):
        """Test removing a specific task."""
        queue = PriorityQueue()
        
        task1 = Task("task1", Mock())
        task2 = Task("task2", Mock())
        
        queue.enqueue(task1)
        queue.enqueue(task2)
        
        removed = queue.remove(task1.id)
        assert removed == task1
        assert queue.size() == 1
        assert queue.peek() == task2
    
    def test_update_priority(self):
        """Test updating task priority."""
        queue = PriorityQueue()
        
        task1 = Task("task1", Mock(), priority=TaskPriority.LOW)
        task2 = Task("task2", Mock(), priority=TaskPriority.NORMAL)
        
        queue.enqueue(task1)
        queue.enqueue(task2)
        
        # Update task1 to high priority
        updated = queue.update_priority(task1.id, TaskPriority.HIGH)
        assert updated is True
        
        # Now task1 should come first
        assert queue.dequeue().id == task1.id


class TestDeadlineQueue:
    """Test DeadlineQueue implementation."""
    
    def test_deadline_ordering(self):
        """Test tasks are ordered by deadline."""
        queue = DeadlineQueue()
        
        now = datetime.now()
        task1 = Task("task1", Mock(), constraints=TaskConstraints(
            deadline=now + timedelta(seconds=30)
        ))
        task2 = Task("task2", Mock(), constraints=TaskConstraints(
            deadline=now + timedelta(seconds=10)
        ))
        task3 = Task("task3", Mock())  # No deadline
        
        queue.enqueue(task1)
        queue.enqueue(task2)
        queue.enqueue(task3)
        
        # Should dequeue in deadline order
        assert queue.dequeue() == task2  # Earliest deadline
        assert queue.dequeue() == task1
        assert queue.dequeue() == task3  # No deadline last
    
    def test_urgent_tasks(self):
        """Test getting urgent tasks."""
        queue = DeadlineQueue()
        
        now = datetime.now()
        urgent_task = Task("urgent", Mock(), constraints=TaskConstraints(
            deadline=now + timedelta(seconds=5)
        ))
        normal_task = Task("normal", Mock(), constraints=TaskConstraints(
            deadline=now + timedelta(seconds=60)
        ))
        
        queue.enqueue(urgent_task)
        queue.enqueue(normal_task)
        
        urgent = queue.get_urgent_tasks(timedelta(seconds=10))
        assert len(urgent) == 1
        assert urgent[0] == urgent_task


class TestMultiLevelQueue:
    """Test MultiLevelQueue implementation."""
    
    def test_level_assignment(self):
        """Test tasks are assigned to correct levels."""
        queue = MultiLevelQueue()
        
        realtime_task = Task("rt", Mock(), priority=TaskPriority.REALTIME)
        normal_task = Task("normal", Mock(), priority=TaskPriority.NORMAL)
        idle_task = Task("idle", Mock(), priority=TaskPriority.IDLE)
        
        queue.enqueue(realtime_task)
        queue.enqueue(normal_task)
        queue.enqueue(idle_task)
        
        levels = queue.get_level_sizes()
        assert levels[0] == 1  # REALTIME at level 0
        assert levels[2] == 1  # NORMAL at level 2
        assert levels[3] == 1  # IDLE at level 3
    
    def test_task_demotion(self):
        """Test task demotion after time slice."""
        queue = MultiLevelQueue()
        
        task = Task("task", Mock(), priority=TaskPriority.HIGH)
        queue.enqueue(task)
        
        # Dequeue and get time slice
        dequeued, time_slice = queue.dequeue()
        assert dequeued == task
        assert time_slice > 0
        
        # Demote task
        queue.demote_task(task)
        
        # Task should be at lower level
        levels = queue.get_level_sizes()
        assert levels[2] == 1  # Demoted from level 1 to 2
    
    def test_task_promotion(self):
        """Test task promotion."""
        queue = MultiLevelQueue()
        
        task = Task("task", Mock(), priority=TaskPriority.LOW)
        queue.enqueue(task)
        
        # Promote task
        promoted = queue.promote_task(task.id)
        assert promoted is True
        
        # Check task moved to higher level
        levels = queue.get_level_sizes()
        assert levels[2] == 1  # Promoted from level 3 to 2


class TestPriorityInheritanceProtocol:
    """Test priority inheritance protocol."""
    
    def test_resource_acquisition(self):
        """Test acquiring resources."""
        pip = PriorityInheritanceProtocol()
        
        task1 = Task("task1", Mock())
        task2 = Task("task2", Mock())
        
        # First task acquires resource
        acquired = pip.acquire_resource(task1, "resource1")
        assert acquired is True
        
        # Second task tries to acquire same resource
        acquired = pip.acquire_resource(task2, "resource1")
        assert acquired is False
        
        # Task can re-acquire its own resource
        acquired = pip.acquire_resource(task1, "resource1")
        assert acquired is True
    
    def test_priority_inheritance(self):
        """Test priority inheritance when blocked."""
        pip = PriorityInheritanceProtocol()
        
        low_task = Task("low", Mock(), priority=TaskPriority.LOW)
        high_task = Task("high", Mock(), priority=TaskPriority.HIGH)
        
        # Set up task lookup
        pip._task_lookup = {
            low_task.id: low_task,
            high_task.id: high_task
        }
        
        # Low priority task acquires resource
        pip.acquire_resource(low_task, "resource1")
        
        # High priority task tries to acquire
        acquired = pip.acquire_resource(high_task, "resource1")
        assert acquired is False
        
        # Low priority task should have inherited high priority
        assert low_task.effective_priority == TaskPriority.HIGH
    
    def test_resource_release(self):
        """Test releasing resources."""
        pip = PriorityInheritanceProtocol()
        
        task1 = Task("task1", Mock())
        task2 = Task("task2", Mock())
        
        pip._task_lookup = {
            task1.id: task1,
            task2.id: task2
        }
        
        # Task1 acquires resource
        pip.acquire_resource(task1, "resource1")
        
        # Task2 waits for resource
        pip.acquire_resource(task2, "resource1")
        
        # Task1 releases resource
        next_task = pip.release_resource(task1.id, "resource1")
        assert next_task == task2
    
    def test_deadlock_detection(self):
        """Test circular wait detection."""
        pip = PriorityInheritanceProtocol()
        
        task1 = Task("task1", Mock())
        task2 = Task("task2", Mock())
        
        # Create circular wait: task1 -> res1, task2 -> res2
        # task1 waits for res2, task2 waits for res1
        pip.acquire_resource(task1, "res1")
        pip.acquire_resource(task2, "res2")
        pip.acquire_resource(task1, "res2")  # Blocked
        pip.acquire_resource(task2, "res1")  # Blocked - creates cycle
        
        cycles = pip.detect_deadlock()
        assert len(cycles) > 0


class TestRealtimeScheduler:
    """Test real-time scheduler implementation."""
    
    def test_basic_scheduling(self):
        """Test basic task scheduling."""
        scheduler = RealtimeScheduler(max_workers=2)
        scheduler.start()
        
        results = []
        
        def test_func(value):
            results.append(value)
            return value * 2
        
        # Submit tasks
        task1 = Task("task1", test_func, args=(1,))
        task2 = Task("task2", test_func, args=(2,))
        
        scheduler.submit(task1)
        scheduler.submit(task2)
        
        # Wait for completion
        time.sleep(0.1)
        
        assert len(results) == 2
        assert set(results) == {1, 2}
        
        scheduler.stop()
    
    def test_priority_scheduling(self):
        """Test priority-based scheduling."""
        scheduler = RealtimeScheduler(
            max_workers=1,
            policy=SchedulingPolicy.PRIORITY
        )
        scheduler.start()
        
        execution_order = []
        
        def track_execution(name):
            execution_order.append(name)
            time.sleep(0.01)
        
        # Submit tasks in reverse priority order
        low_task = Task("low", track_execution, args=("low",), 
                       priority=TaskPriority.LOW)
        high_task = Task("high", track_execution, args=("high",),
                        priority=TaskPriority.HIGH)
        
        scheduler.submit(low_task)
        scheduler.submit(high_task)
        
        # Wait for completion
        time.sleep(0.1)
        
        # High priority should execute first
        assert execution_order == ["high", "low"]
        
        scheduler.stop()
    
    def test_deadline_scheduling(self):
        """Test deadline-based scheduling."""
        scheduler = RealtimeScheduler(
            max_workers=1,
            policy=SchedulingPolicy.DEADLINE
        )
        scheduler.start()
        
        execution_order = []
        
        def track_execution(name):
            execution_order.append(name)
        
        now = datetime.now()
        
        # Task with later deadline
        task1 = Task("task1", track_execution, args=("task1",),
                    constraints=TaskConstraints(
                        deadline=now + timedelta(seconds=60)
                    ))
        
        # Task with earlier deadline
        task2 = Task("task2", track_execution, args=("task2",),
                    constraints=TaskConstraints(
                        deadline=now + timedelta(seconds=10)
                    ))
        
        scheduler.submit(task1)
        scheduler.submit(task2)
        
        # Wait for completion
        time.sleep(0.1)
        
        # Earlier deadline should execute first
        assert execution_order == ["task2", "task1"]
        
        scheduler.stop()
    
    def test_task_cancellation(self):
        """Test cancelling tasks."""
        scheduler = RealtimeScheduler(max_workers=1)
        scheduler.start()
        
        executed = threading.Event()
        
        def slow_task():
            time.sleep(1)
            executed.set()
        
        task = Task("slow", slow_task)
        scheduler.submit(task)
        
        # Cancel before execution
        cancelled = scheduler.cancel_task(task.id)
        assert cancelled is True
        
        # Wait to ensure it doesn't execute
        time.sleep(0.1)
        assert not executed.is_set()
        assert task.status == TaskStatus.CANCELLED
        
        scheduler.stop()


class TestLatencyMonitor:
    """Test latency monitoring."""
    
    def test_latency_recording(self):
        """Test recording latency metrics."""
        monitor = LatencyMonitor()
        
        task = Task("test", Mock(), priority=TaskPriority.HIGH)
        
        # Record scheduling latency
        monitor.record_scheduling_latency(task, 50.0)
        
        # Record execution time
        monitor.record_execution_time(task, 100.0)
        
        # Get stats
        stats = monitor.get_stats(TaskPriority.HIGH)
        
        assert stats["scheduling"]["count"] == 1
        assert stats["scheduling"]["mean_ms"] == 50.0
        assert stats["execution"]["count"] == 1
        assert stats["execution"]["mean_ms"] == 100.0
    
    def test_percentile_calculation(self):
        """Test percentile calculations."""
        monitor = LatencyMonitor()
        
        task = Task("test", Mock())
        
        # Record multiple latencies
        for i in range(100):
            monitor.record_scheduling_latency(task, float(i))
        
        stats = monitor.get_stats(task.priority)
        
        assert stats["scheduling"]["p50_ms"] == pytest.approx(50, abs=1)
        assert stats["scheduling"]["p95_ms"] == pytest.approx(95, abs=1)
        assert stats["scheduling"]["p99_ms"] == pytest.approx(99, abs=1)


class TestSchedulingMetrics:
    """Test scheduling metrics collection."""
    
    def test_task_metrics(self):
        """Test task-related metrics."""
        metrics = SchedulingMetrics()
        
        task1 = Task("task1", Mock(), priority=TaskPriority.HIGH)
        task2 = Task("task2", Mock(), priority=TaskPriority.NORMAL)
        
        # Record events
        metrics.task_submitted(task1)
        metrics.task_submitted(task2)
        metrics.task_completed(task1)
        metrics.task_failed(task2)
        
        # Get summary
        summary = metrics.get_summary()
        
        assert summary["total_submitted"] == 2
        assert summary["total_completed"] == 1
        assert summary["total_failed"] == 1
        assert summary["success_rate_percent"] == 50.0
    
    def test_queue_metrics(self):
        """Test queue and utilization metrics."""
        metrics = SchedulingMetrics()
        
        # Record queue sizes
        metrics.record_queue_size(5)
        metrics.record_queue_size(10)
        metrics.record_queue_size(7)
        
        # Record utilization
        metrics.record_worker_utilization(2, 4)
        metrics.record_worker_utilization(3, 4)
        
        summary = metrics.get_summary()
        
        assert summary["average_queue_size"] == pytest.approx(7.33, abs=0.1)
        assert summary["average_utilization_percent"] == pytest.approx(62.5, abs=0.1)


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for the scheduling system."""
    
    async def test_perception_task_scheduling(self):
        """Test scheduling perception tasks with <100ms constraint."""
        scheduler = RealtimeScheduler(max_workers=4)
        scheduler.start()
        
        latencies = []
        
        def perception_task(task_id):
            # Simulate perception processing
            time.sleep(0.02)  # 20ms
            return f"perception_{task_id}"
        
        # Create perception tasks with real-time constraints
        tasks = []
        for i in range(10):
            task = Task(
                f"perception_{i}",
                perception_task,
                args=(i,),
                priority=TaskPriority.REALTIME,
                constraints=TaskConstraints(
                    max_latency_ms=100,
                    is_hard_realtime=True,
                    deadline=datetime.now() + timedelta(milliseconds=100)
                )
            )
            tasks.append(task)
            scheduler.submit(task)
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        # Check all tasks completed within constraints
        for task in tasks:
            assert task.status == TaskStatus.COMPLETED
            assert task.metrics.total_latency_ms < 100
        
        scheduler.stop()
    
    async def test_mixed_priority_workload(self):
        """Test handling mixed priority workload."""
        scheduler = RealtimeScheduler(max_workers=2)
        scheduler.start()
        
        results = []
        
        def work_task(name, duration):
            results.append(f"{name}_start")
            time.sleep(duration)
            results.append(f"{name}_end")
        
        # Submit mix of tasks
        critical = Task("critical", work_task, args=("critical", 0.01),
                       priority=TaskPriority.CRITICAL)
        normal = Task("normal", work_task, args=("normal", 0.02),
                     priority=TaskPriority.NORMAL)
        background = Task("background", work_task, args=("background", 0.01),
                         priority=TaskPriority.BACKGROUND)
        
        scheduler.submit(normal)
        scheduler.submit(background)
        await asyncio.sleep(0.01)  # Let them start
        scheduler.submit(critical)  # Should get priority
        
        # Wait for completion
        await asyncio.sleep(0.2)
        
        # Critical should have been prioritized
        assert "critical_start" in results[:4]  # Should start early
        
        scheduler.stop()