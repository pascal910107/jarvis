# Real-Time Scheduling Framework

A sophisticated real-time scheduling framework designed for AGI systems, supporting priority-based scheduling, deadline awareness, and latency monitoring.

## Features

### Task Management
- **Priority Levels**: IDLE, BACKGROUND, LOW, NORMAL, HIGH, CRITICAL, REALTIME
- **Task Constraints**: Deadlines, resource requirements, dependencies
- **Real-time Support**: Hard and soft real-time constraints
- **Task Metrics**: Comprehensive latency and performance tracking

### Scheduling Policies
- **Priority Scheduling**: Highest priority first with preemption
- **Deadline Scheduling**: Earliest Deadline First (EDF)
- **Fair Scheduling**: Multi-level feedback queue
- **Real-time Scheduling**: Preemptive scheduling for time-critical tasks

### Advanced Features
- **Priority Inheritance Protocol**: Prevents priority inversion
- **Deadlock Detection**: Circular dependency detection
- **Resource Management**: Acquire/release with wait queues
- **Latency Monitoring**: Real-time tracking with percentiles
- **Preemption Support**: Interrupt lower priority tasks

## Usage

### Basic Task Creation

```python
from core.scheduling import Task, TaskPriority, TaskConstraints

# Simple task
task = Task(
    name="process_image",
    func=process_image_func,
    args=(image_data,),
    priority=TaskPriority.HIGH
)

# Task with constraints
perception_task = Task(
    name="perception",
    func=perceive,
    args=(sensor_data,),
    priority=TaskPriority.REALTIME,
    constraints=TaskConstraints(
        deadline=datetime.now() + timedelta(milliseconds=100),
        max_latency_ms=100,
        is_hard_realtime=True,
        is_preemptible=False
    )
)
```

### Scheduler Setup

```python
from core.scheduling import RealtimeScheduler, SchedulingPolicy

# Create scheduler
scheduler = RealtimeScheduler(
    max_workers=4,
    policy=SchedulingPolicy.PRIORITY
)

# Start scheduler
scheduler.start()

# Submit tasks
scheduler.submit(task1)
scheduler.submit(task2)

# Stop scheduler
scheduler.stop()
```

### Task Dependencies

```python
# Create dependent tasks
task1 = Task("fetch_data", fetch_func)
task2 = Task("process_data", process_func,
             constraints=TaskConstraints(
                 depends_on={task1.id}
             ))

scheduler.submit(task1)
scheduler.submit(task2)  # Will wait for task1
```

### Resource Management

```python
# Tasks requiring resources
memory_task = Task(
    "memory_op",
    memory_func,
    constraints=TaskConstraints(
        required_resources={"memory_store", "cache"}
    )
)

# Acquire resources with priority inheritance
scheduler.acquire_resources(memory_task, ["memory_store"])

# Resources automatically released on completion
```

### Monitoring

```python
# Get latency statistics
stats = scheduler.latency_monitor.get_stats()
print(f"P95 scheduling latency: {stats['REALTIME']['scheduling']['p95_ms']}ms")

# Get overall metrics
metrics = scheduler.metrics.get_summary()
print(f"Success rate: {metrics['success_rate_percent']}%")
print(f"Throughput: {metrics['throughput_per_second']} tasks/sec")
```

## Architecture

### Task Lifecycle

```
PENDING -> READY -> RUNNING -> COMPLETED
   |        |         |
   |        |         +-----> FAILED
   |        |
   |        +--------------> BLOCKED (waiting for resources)
   |
   +-----------------------> CANCELLED
   |
   +-----------------------> DEADLINE_MISSED
```

### Queue Implementations

1. **PriorityQueue**: Binary heap with stable sorting
2. **DeadlineQueue**: EDF scheduling with deadline tracking
3. **MultiLevelQueue**: Fair scheduling with time slices

### Priority Inheritance Protocol

When a high-priority task is blocked by a low-priority task holding a resource:

1. Low-priority task inherits the high priority
2. Inheritance is transitive through blocking chains
3. Priority restored when resource is released

## Real-Time Constraints

### Perception Tasks (<100ms)
```python
Task(
    "perception",
    perceive_func,
    priority=TaskPriority.REALTIME,
    constraints=TaskConstraints(
        max_latency_ms=100,
        is_hard_realtime=True,
        is_preemptible=False
    )
)
```

### System 1 Reasoning (<50ms)
```python
Task(
    "fast_reasoning",
    reason_func,
    priority=TaskPriority.HIGH,
    constraints=TaskConstraints(
        max_latency_ms=50,
        deadline=datetime.now() + timedelta(milliseconds=50)
    )
)
```

### System 2 Reasoning (<500ms)
```python
Task(
    "deep_reasoning",
    deep_reason_func,
    priority=TaskPriority.NORMAL,
    constraints=TaskConstraints(
        max_latency_ms=500,
        cpu_cores=2
    )
)
```

## Performance Optimization

### Preemption Points
For long-running tasks, check preemption signals:

```python
def long_task(preemption_event):
    for i in range(1000):
        if preemption_event.is_set():
            # Save state and yield
            return partial_result
        # Do work...
```

### Batch Processing
Group similar tasks to reduce overhead:

```python
# Instead of individual tasks
for data in dataset:
    scheduler.submit(Task("process", func, args=(data,)))

# Use batch task
scheduler.submit(Task("batch_process", batch_func, args=(dataset,)))
```

### Resource Pooling
Pre-allocate resources to avoid contention:

```python
constraints = TaskConstraints(
    required_resources={"worker_pool_1"},
    cpu_cores=1,
    memory_mb=512
)
```

## Monitoring and Alerts

### Latency Alerts
Configure thresholds for automatic alerting:

```python
# Alerts triggered when P95 latency exceeds thresholds
thresholds = {
    TaskPriority.REALTIME: {"scheduling": 10, "execution": 100},
    TaskPriority.CRITICAL: {"scheduling": 50, "execution": 500}
}
```

### Metrics Collection
All metrics are exported to Prometheus:

- `perception_latency_ms`: Perception processing time
- `reasoning_latency_ms`: Reasoning system latency
- `tasks_processed_total`: Task completion counter
- `queue_size`: Current queue depth
- `active_workers`: Active worker threads

## Best Practices

1. **Set Appropriate Priorities**: Use REALTIME sparingly
2. **Define Deadlines**: Help scheduler make informed decisions
3. **Mark Preemptible Tasks**: Allow system flexibility
4. **Monitor Latencies**: Track P95/P99 for SLA compliance
5. **Handle Failures**: Implement retry logic for critical tasks
6. **Batch When Possible**: Reduce scheduling overhead
7. **Profile Resource Usage**: Set accurate constraints

## Testing

Run the comprehensive test suite:

```bash
pytest tests/test_scheduling.py -v
```

Run the demo to see the scheduler in action:

```bash
python examples/scheduling_demo.py
```

## Troubleshooting

### High Latency
- Check worker utilization
- Review task priorities
- Look for priority inversions
- Consider increasing workers

### Deadline Misses
- Verify deadline feasibility
- Check for resource contention
- Review task dependencies
- Enable preemption for long tasks

### Priority Inversion
- Enable priority inheritance
- Minimize critical sections
- Use appropriate locking granularity