"""Demo script showing real-time scheduling framework usage."""

import asyncio
import random
import time
from datetime import datetime, timedelta

from core.scheduling import (
    Task, TaskPriority, TaskConstraints,
    RealtimeScheduler, SchedulingPolicy,
    LatencyMonitor, SchedulingMetrics
)
from core.monitoring import setup_logging, get_logger

# Setup logging
setup_logging(level="INFO")
logger = get_logger(__name__)


class JarvisSchedulingDemo:
    """Demo of scheduling system for Jarvis AGI tasks."""
    
    def __init__(self):
        # Create scheduler with real-time policy
        self.scheduler = RealtimeScheduler(
            max_workers=4,
            policy=SchedulingPolicy.PRIORITY
        )
        
        # Metrics tracking
        self.metrics = SchedulingMetrics()
        self.latency_monitor = self.scheduler.latency_monitor
        
    def create_perception_task(self, sensor_id: int, data: str) -> Task:
        """Create a perception processing task."""
        def process_perception(sensor_id, data):
            logger.info(f"Processing perception from sensor {sensor_id}")
            
            # Simulate visual processing
            time.sleep(random.uniform(0.02, 0.08))  # 20-80ms
            
            features = {
                "sensor": sensor_id,
                "objects": random.randint(1, 5),
                "confidence": random.uniform(0.7, 0.99)
            }
            
            logger.info(f"Perception complete: {features}")
            return features
        
        # Perception tasks have strict latency requirements
        return Task(
            name=f"perception_sensor_{sensor_id}",
            func=process_perception,
            args=(sensor_id, data),
            priority=TaskPriority.REALTIME,
            constraints=TaskConstraints(
                max_latency_ms=100,
                is_hard_realtime=True,
                deadline=datetime.now() + timedelta(milliseconds=100),
                is_preemptible=False  # Don't interrupt perception
            )
        )
    
    def create_reasoning_task(self, perception_data: dict, system: int = 1) -> Task:
        """Create a reasoning task."""
        def perform_reasoning(data, system):
            logger.info(f"System {system} reasoning on: {data}")
            
            if system == 1:
                # Fast intuitive reasoning
                time.sleep(random.uniform(0.01, 0.04))  # 10-40ms
                decision = "react" if data.get("confidence", 0) > 0.8 else "observe"
            else:
                # Slow deliberative reasoning
                time.sleep(random.uniform(0.1, 0.3))  # 100-300ms
                decision = "plan_complex_action"
            
            logger.info(f"Reasoning complete: {decision}")
            return decision
        
        priority = TaskPriority.HIGH if system == 1 else TaskPriority.NORMAL
        max_latency = 50 if system == 1 else 500
        
        return Task(
            name=f"reasoning_system_{system}",
            func=perform_reasoning,
            args=(perception_data, system),
            priority=priority,
            constraints=TaskConstraints(
                max_latency_ms=max_latency,
                deadline=datetime.now() + timedelta(milliseconds=max_latency)
            )
        )
    
    def create_memory_task(self, data: dict, operation: str) -> Task:
        """Create a memory operation task."""
        def memory_operation(data, op):
            logger.info(f"Memory {op}: {data}")
            
            if op == "store":
                time.sleep(random.uniform(0.005, 0.015))  # 5-15ms
            elif op == "retrieve":
                time.sleep(random.uniform(0.002, 0.008))  # 2-8ms
            
            return {"status": "success", "operation": op}
        
        return Task(
            name=f"memory_{operation}",
            func=memory_operation,
            args=(data, operation),
            priority=TaskPriority.HIGH,
            constraints=TaskConstraints(
                max_latency_ms=20,
                required_resources={"memory_store"}
            )
        )
    
    def create_planning_task(self, goal: str) -> Task:
        """Create a planning task."""
        def plan_actions(goal):
            logger.info(f"Planning for goal: {goal}")
            
            # Simulate complex planning
            time.sleep(random.uniform(0.5, 1.0))  # 500ms-1s
            
            plan = {
                "goal": goal,
                "steps": [f"step_{i}" for i in range(random.randint(3, 7))],
                "estimated_time": random.uniform(10, 60)
            }
            
            logger.info(f"Planning complete: {len(plan['steps'])} steps")
            return plan
        
        return Task(
            name=f"planning_{goal}",
            func=plan_actions,
            args=(goal,),
            priority=TaskPriority.NORMAL,
            constraints=TaskConstraints(
                max_duration=timedelta(seconds=2),
                cpu_cores=2  # Planning is CPU intensive
            )
        )
    
    def create_background_task(self, task_type: str) -> Task:
        """Create a background maintenance task."""
        def background_work(task_type):
            logger.info(f"Background task: {task_type}")
            
            # Simulate background work
            time.sleep(random.uniform(0.1, 0.5))
            
            return {"type": task_type, "status": "completed"}
        
        return Task(
            name=f"background_{task_type}",
            func=background_work,
            args=(task_type,),
            priority=TaskPriority.BACKGROUND,
            constraints=TaskConstraints(
                is_preemptible=True  # Can be interrupted
            )
        )
    
    async def simulate_agi_workload(self, duration_seconds: int = 30):
        """Simulate a mixed AGI workload."""
        logger.info("Starting AGI workload simulation")
        logger.info(f"Scheduler policy: {self.scheduler.policy.value}")
        
        # Start the scheduler
        self.scheduler.start()
        
        start_time = time.time()
        task_count = 0
        
        while time.time() - start_time < duration_seconds:
            # Simulate sensor input triggering perception
            if random.random() < 0.7:  # 70% chance of new perception
                sensor_id = random.randint(1, 4)
                perception_task = self.create_perception_task(
                    sensor_id, 
                    f"sensor_data_{task_count}"
                )
                self.scheduler.submit(perception_task)
                self.metrics.task_submitted(perception_task)
                task_count += 1
                
                # Chain reasoning after perception
                if random.random() < 0.8:
                    # Fast reasoning
                    reasoning_task = self.create_reasoning_task(
                        {"sensor": sensor_id}, 
                        system=1
                    )
                    reasoning_task.constraints.depends_on.add(perception_task.id)
                    self.scheduler.submit(reasoning_task)
                    self.metrics.task_submitted(reasoning_task)
                    task_count += 1
                    
                    # Sometimes trigger slow reasoning
                    if random.random() < 0.3:
                        deep_reasoning = self.create_reasoning_task(
                            {"sensor": sensor_id},
                            system=2
                        )
                        deep_reasoning.constraints.depends_on.add(reasoning_task.id)
                        self.scheduler.submit(deep_reasoning)
                        self.metrics.task_submitted(deep_reasoning)
                        task_count += 1
            
            # Memory operations
            if random.random() < 0.5:
                operation = random.choice(["store", "retrieve"])
                memory_task = self.create_memory_task(
                    {"data": f"memory_{task_count}"},
                    operation
                )
                self.scheduler.submit(memory_task)
                self.metrics.task_submitted(memory_task)
                task_count += 1
            
            # Planning tasks
            if random.random() < 0.1:  # 10% chance
                goal = random.choice(["navigate", "manipulate", "communicate"])
                planning_task = self.create_planning_task(goal)
                self.scheduler.submit(planning_task)
                self.metrics.task_submitted(planning_task)
                task_count += 1
            
            # Background tasks
            if random.random() < 0.2:  # 20% chance
                bg_type = random.choice(["cleanup", "indexing", "optimization"])
                bg_task = self.create_background_task(bg_type)
                self.scheduler.submit(bg_task)
                self.metrics.task_submitted(bg_task)
                task_count += 1
            
            # Update metrics
            self.metrics.record_queue_size(self.scheduler._ready_queue.size())
            self.metrics.record_worker_utilization(
                len(self.scheduler._running_tasks),
                self.scheduler.max_workers
            )
            
            # Small delay between submissions
            await asyncio.sleep(random.uniform(0.01, 0.1))
        
        # Wait for remaining tasks to complete
        logger.info("Waiting for remaining tasks to complete...")
        await asyncio.sleep(2)
        
        # Stop scheduler
        self.scheduler.stop()
        
        return task_count
    
    def print_performance_report(self, task_count: int):
        """Print performance metrics report."""
        print("\n" + "=" * 60)
        print("SCHEDULING PERFORMANCE REPORT")
        print("=" * 60)
        
        # Get latency stats
        latency_stats = self.latency_monitor.get_stats()
        
        print("\nLatency Statistics by Priority:")
        print("-" * 60)
        
        for priority_name, stats in latency_stats.items():
            print(f"\n{priority_name}:")
            
            sched = stats["scheduling"]
            if sched["count"] > 0:
                print(f"  Scheduling Latency:")
                print(f"    Mean: {sched['mean_ms']:.2f}ms")
                print(f"    P50:  {sched['p50_ms']:.2f}ms")
                print(f"    P95:  {sched['p95_ms']:.2f}ms")
                print(f"    P99:  {sched['p99_ms']:.2f}ms")
                print(f"    Max:  {sched['max_ms']:.2f}ms")
            
            exec = stats["execution"]
            if exec["count"] > 0:
                print(f"  Execution Time:")
                print(f"    Mean: {exec['mean_ms']:.2f}ms")
                print(f"    P50:  {exec['p50_ms']:.2f}ms")
                print(f"    P95:  {exec['p95_ms']:.2f}ms")
                print(f"    P99:  {exec['p99_ms']:.2f}ms")
                print(f"    Max:  {exec['max_ms']:.2f}ms")
        
        # Get overall metrics
        summary = self.metrics.get_summary()
        
        print("\nOverall Metrics:")
        print("-" * 60)
        print(f"Total Tasks Submitted:    {summary['total_submitted']}")
        print(f"Total Tasks Completed:    {summary['total_completed']}")
        print(f"Total Tasks Failed:       {summary['total_failed']}")
        print(f"Total Deadlines Missed:   {summary['total_deadline_missed']}")
        print(f"Success Rate:             {summary['success_rate_percent']:.1f}%")
        print(f"Throughput:               {summary['throughput_per_second']:.2f} tasks/sec")
        print(f"Average Queue Size:       {summary['average_queue_size']:.1f}")
        print(f"Average CPU Utilization:  {summary['average_utilization_percent']:.1f}%")
        print(f"Priority Inversions:      {summary['priority_inversions']}")
        print(f"Task Preemptions:         {summary['preemptions']}")
        
        print("\nTasks by Priority:")
        print("-" * 60)
        for priority, stats in summary["by_priority"].items():
            print(f"{priority:10s}: {stats['completed']:4d} completed, "
                  f"{stats['failed']:4d} failed, "
                  f"{stats['deadline_missed']:4d} missed deadline")
        
        print("=" * 60)


async def main():
    """Run the scheduling demo."""
    print("Jarvis AGI Real-Time Scheduling Demo")
    print("====================================")
    print()
    print("This demo simulates the scheduling of various AGI tasks:")
    print("- Perception (real-time, <100ms)")
    print("- Reasoning (System 1: fast, System 2: slow)")
    print("- Memory operations")
    print("- Planning")
    print("- Background tasks")
    print()
    
    demo = JarvisSchedulingDemo()
    
    # Run simulation
    print("Running 30-second workload simulation...")
    print()
    
    task_count = await demo.simulate_agi_workload(duration_seconds=30)
    
    # Print report
    demo.print_performance_report(task_count)
    
    print("\nDemo completed!")


if __name__ == "__main__":
    asyncio.run(main())