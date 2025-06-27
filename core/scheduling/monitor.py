"""Monitoring and metrics for the scheduling framework."""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.monitoring import get_logger, get_metrics_collector, AlertLevel

from .task import Task, TaskPriority

logger = get_logger(__name__)
metrics = get_metrics_collector()


@dataclass
class LatencyStats:
    """Latency statistics for a time window."""
    count: int = 0
    sum_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    values: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def add(self, value_ms: float) -> None:
        """Add a latency measurement."""
        self.count += 1
        self.sum_ms += value_ms
        self.min_ms = min(self.min_ms, value_ms)
        self.max_ms = max(self.max_ms, value_ms)
        self.values.append(value_ms)
    
    def mean(self) -> float:
        """Calculate mean latency."""
        return self.sum_ms / self.count if self.count > 0 else 0.0
    
    def percentile(self, p: float) -> float:
        """Calculate percentile (0-100)."""
        if not self.values:
            return 0.0
        
        sorted_values = sorted(self.values)
        index = int((p / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]


class LatencyMonitor:
    """Monitors scheduling and execution latencies."""
    
    def __init__(self, window_size: timedelta = timedelta(minutes=5)):
        self.window_size = window_size
        self._scheduling_stats: Dict[TaskPriority, LatencyStats] = defaultdict(LatencyStats)
        self._execution_stats: Dict[TaskPriority, LatencyStats] = defaultdict(LatencyStats)
        self._total_stats: Dict[TaskPriority, LatencyStats] = defaultdict(LatencyStats)
        self._lock = threading.RLock()
        
        # Thresholds for alerting
        self._thresholds = {
            TaskPriority.REALTIME: {"scheduling": 10, "execution": 100},
            TaskPriority.CRITICAL: {"scheduling": 50, "execution": 500},
            TaskPriority.HIGH: {"scheduling": 100, "execution": 1000},
            TaskPriority.NORMAL: {"scheduling": 500, "execution": 5000},
        }
        
        # Start monitoring thread
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self._monitoring_thread.daemon = True
        self._monitoring_thread.start()
    
    def record_scheduling_latency(self, task: Task, latency_ms: float) -> None:
        """Record task scheduling latency."""
        with self._lock:
            self._scheduling_stats[task.priority].add(latency_ms)
            
            # Update Prometheus metrics
            metrics.performance.perception_latency.record_duration(
                latency_ms / 1000.0,  # Convert to seconds
                labels={"priority": task.priority.name}
            )
            
            # Check threshold
            threshold = self._thresholds.get(task.priority, {}).get("scheduling", float('inf'))
            if latency_ms > threshold:
                logger.warning(
                    f"High scheduling latency for {task.priority.name} task",
                    extra={
                        "task_id": task.id,
                        "latency_ms": latency_ms,
                        "threshold_ms": threshold
                    }
                )
    
    def record_execution_time(self, task: Task, execution_ms: float) -> None:
        """Record task execution time."""
        with self._lock:
            self._execution_stats[task.priority].add(execution_ms)
            
            # Calculate total latency
            if task.metrics.created_at and task.metrics.completed_at:
                total_ms = (
                    task.metrics.completed_at - task.metrics.created_at
                ).total_seconds() * 1000
                self._total_stats[task.priority].add(total_ms)
            
            # Update Prometheus metrics
            if task.name.startswith("perception"):
                metrics.performance.perception_latency.record_duration(
                    execution_ms / 1000.0,
                    labels={"type": "execution"}
                )
            elif task.name.startswith("reasoning"):
                metrics.performance.reasoning_latency.record_duration(
                    execution_ms / 1000.0,
                    labels={"system": "1" if "system1" in task.name else "2"}
                )
            
            # Check threshold
            threshold = self._thresholds.get(task.priority, {}).get("execution", float('inf'))
            if execution_ms > threshold:
                logger.warning(
                    f"High execution time for {task.priority.name} task",
                    extra={
                        "task_id": task.id,
                        "execution_ms": execution_ms,
                        "threshold_ms": threshold
                    }
                )
    
    def get_stats(self, priority: Optional[TaskPriority] = None) -> Dict[str, Dict[str, float]]:
        """Get latency statistics."""
        with self._lock:
            if priority:
                return self._get_priority_stats(priority)
            
            # Get stats for all priorities
            all_stats = {}
            for p in TaskPriority:
                stats = self._get_priority_stats(p)
                if stats["scheduling"]["count"] > 0 or stats["execution"]["count"] > 0:
                    all_stats[p.name] = stats
            
            return all_stats
    
    def _get_priority_stats(self, priority: TaskPriority) -> Dict[str, Dict[str, float]]:
        """Get stats for a specific priority."""
        sched = self._scheduling_stats[priority]
        exec = self._execution_stats[priority]
        total = self._total_stats[priority]
        
        return {
            "scheduling": {
                "count": sched.count,
                "mean_ms": sched.mean(),
                "min_ms": sched.min_ms if sched.count > 0 else 0,
                "max_ms": sched.max_ms,
                "p50_ms": sched.percentile(50),
                "p95_ms": sched.percentile(95),
                "p99_ms": sched.percentile(99),
            },
            "execution": {
                "count": exec.count,
                "mean_ms": exec.mean(),
                "min_ms": exec.min_ms if exec.count > 0 else 0,
                "max_ms": exec.max_ms,
                "p50_ms": exec.percentile(50),
                "p95_ms": exec.percentile(95),
                "p99_ms": exec.percentile(99),
            },
            "total": {
                "count": total.count,
                "mean_ms": total.mean(),
                "min_ms": total.min_ms if total.count > 0 else 0,
                "max_ms": total.max_ms,
                "p50_ms": total.percentile(50),
                "p95_ms": total.percentile(95),
                "p99_ms": total.percentile(99),
            }
        }
    
    def _monitoring_loop(self) -> None:
        """Periodic monitoring and alerting."""
        while True:
            try:
                time.sleep(60)  # Check every minute
                
                # Check for concerning patterns
                self._check_latency_trends()
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}", exc_info=True)
    
    def _check_latency_trends(self) -> None:
        """Check for concerning latency trends."""
        with self._lock:
            for priority in [TaskPriority.REALTIME, TaskPriority.CRITICAL]:
                stats = self._get_priority_stats(priority)
                
                # Check if p95 scheduling latency is too high
                p95_sched = stats["scheduling"]["p95_ms"]
                threshold = self._thresholds.get(priority, {}).get("scheduling", float('inf'))
                
                if p95_sched > threshold * 2:  # 2x threshold for p95
                    from core.monitoring import get_metrics_collector
                    alert_manager = get_metrics_collector().monitoring.alert_manager
                    
                    alert_manager.create_alert(
                        level=AlertLevel.WARNING,
                        source="scheduler.latency_monitor",
                        message=f"High p95 scheduling latency for {priority.name} tasks",
                        details={
                            "p95_ms": p95_sched,
                            "threshold_ms": threshold,
                            "task_count": stats["scheduling"]["count"]
                        }
                    )


class SchedulingMetrics:
    """Comprehensive scheduling metrics collection."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._start_time = datetime.now()
        
        # Task counters by priority
        self._submitted: Dict[TaskPriority, int] = defaultdict(int)
        self._completed: Dict[TaskPriority, int] = defaultdict(int)
        self._failed: Dict[TaskPriority, int] = defaultdict(int)
        self._cancelled: Dict[TaskPriority, int] = defaultdict(int)
        self._deadline_missed: Dict[TaskPriority, int] = defaultdict(int)
        
        # Queue metrics
        self._queue_sizes: deque = deque(maxlen=1000)
        self._worker_utilization: deque = deque(maxlen=1000)
        
        # Resource contention
        self._resource_waits: Dict[str, List[float]] = defaultdict(list)
        self._priority_inversions: int = 0
        self._preemptions: int = 0
    
    def task_submitted(self, task: Task) -> None:
        """Record task submission."""
        with self._lock:
            self._submitted[task.priority] += 1
    
    def task_completed(self, task: Task) -> None:
        """Record task completion."""
        with self._lock:
            self._completed[task.priority] += 1
            
            # Update Prometheus metrics
            metrics.performance.tasks_processed.increment(
                labels={"priority": task.priority.name}
            )
    
    def task_failed(self, task: Task) -> None:
        """Record task failure."""
        with self._lock:
            self._failed[task.priority] += 1
            
            # Update Prometheus metrics
            metrics.performance.tasks_failed.increment(
                labels={"priority": task.priority.name}
            )
    
    def task_cancelled(self, task: Task) -> None:
        """Record task cancellation."""
        with self._lock:
            self._cancelled[task.priority] += 1
    
    def deadline_missed(self, task: Task) -> None:
        """Record deadline miss."""
        with self._lock:
            self._deadline_missed[task.priority] += 1
            
            logger.error(
                f"Deadline missed for task {task.id}",
                extra={
                    "task_name": task.name,
                    "priority": task.priority.name,
                    "deadline": task.constraints.deadline.isoformat() if task.constraints.deadline else None
                }
            )
    
    def record_queue_size(self, size: int) -> None:
        """Record current queue size."""
        with self._lock:
            self._queue_sizes.append((datetime.now(), size))
            
            # Update Prometheus metrics
            metrics.performance.queue_size.set(size)
    
    def record_worker_utilization(self, active: int, total: int) -> None:
        """Record worker utilization."""
        with self._lock:
            utilization = (active / total * 100) if total > 0 else 0
            self._worker_utilization.append((datetime.now(), utilization))
            
            # Update Prometheus metrics
            metrics.performance.active_workers.set(active)
    
    def record_resource_wait(self, resource: str, wait_ms: float) -> None:
        """Record resource wait time."""
        with self._lock:
            self._resource_waits[resource].append(wait_ms)
    
    def record_priority_inversion(self) -> None:
        """Record priority inversion event."""
        with self._lock:
            self._priority_inversions += 1
    
    def record_preemption(self) -> None:
        """Record task preemption."""
        with self._lock:
            self._preemptions += 1
    
    def get_summary(self) -> Dict[str, any]:
        """Get comprehensive metrics summary."""
        with self._lock:
            uptime = (datetime.now() - self._start_time).total_seconds()
            
            # Calculate throughput
            total_completed = sum(self._completed.values())
            throughput = total_completed / uptime if uptime > 0 else 0
            
            # Calculate success rate
            total_tasks = sum(self._submitted.values())
            success_rate = (total_completed / total_tasks * 100) if total_tasks > 0 else 0
            
            # Average queue size
            avg_queue_size = (
                sum(size for _, size in self._queue_sizes) / len(self._queue_sizes)
                if self._queue_sizes else 0
            )
            
            # Average utilization
            avg_utilization = (
                sum(util for _, util in self._worker_utilization) / len(self._worker_utilization)
                if self._worker_utilization else 0
            )
            
            return {
                "uptime_seconds": uptime,
                "total_submitted": total_tasks,
                "total_completed": total_completed,
                "total_failed": sum(self._failed.values()),
                "total_cancelled": sum(self._cancelled.values()),
                "total_deadline_missed": sum(self._deadline_missed.values()),
                "throughput_per_second": throughput,
                "success_rate_percent": success_rate,
                "average_queue_size": avg_queue_size,
                "average_utilization_percent": avg_utilization,
                "priority_inversions": self._priority_inversions,
                "preemptions": self._preemptions,
                "by_priority": {
                    p.name: {
                        "submitted": self._submitted[p],
                        "completed": self._completed[p],
                        "failed": self._failed[p],
                        "cancelled": self._cancelled[p],
                        "deadline_missed": self._deadline_missed[p],
                    }
                    for p in TaskPriority
                    if self._submitted[p] > 0
                }
            }