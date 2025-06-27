"""Performance metrics collection system for AGI monitoring."""

import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
import psutil
import statistics


class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricValue:
    """Single metric measurement."""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""
    count: int
    sum: float
    min: float
    max: float
    mean: float
    median: float
    p95: float
    p99: float
    stddev: float


class Metric:
    """Base class for metrics."""
    
    def __init__(self, name: str, metric_type: MetricType, 
                 description: str = "", labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.type = metric_type
        self.description = description
        self.labels = labels or {}
        self._lock = threading.Lock()
        self._values: deque = deque(maxlen=10000)  # Keep last 10k values
    
    def record(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a metric value."""
        with self._lock:
            combined_labels = {**self.labels, **(labels or {})}
            self._values.append(MetricValue(
                timestamp=datetime.now(),
                value=value,
                labels=combined_labels
            ))
    
    def get_values(self, since: Optional[datetime] = None) -> List[MetricValue]:
        """Get metric values since a given time."""
        with self._lock:
            if since is None:
                return list(self._values)
            return [v for v in self._values if v.timestamp >= since]
    
    def get_summary(self, window: Optional[timedelta] = None) -> Optional[MetricSummary]:
        """Get summary statistics for the metric."""
        values = self.get_values(
            since=datetime.now() - window if window else None
        )
        
        if not values:
            return None
        
        nums = [v.value for v in values]
        return MetricSummary(
            count=len(nums),
            sum=sum(nums),
            min=min(nums),
            max=max(nums),
            mean=statistics.mean(nums),
            median=statistics.median(nums),
            p95=statistics.quantiles(nums, n=20)[18] if len(nums) > 1 else nums[0],
            p99=statistics.quantiles(nums, n=100)[98] if len(nums) > 1 else nums[0],
            stddev=statistics.stdev(nums) if len(nums) > 1 else 0.0
        )


class Counter(Metric):
    """Counter metric that only increases."""
    
    def __init__(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None):
        super().__init__(name, MetricType.COUNTER, description, labels)
        self._value = 0.0
    
    def increment(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment the counter."""
        if value < 0:
            raise ValueError("Counter can only be incremented with positive values")
        with self._lock:
            self._value += value
            self.record(self._value, labels)
    
    def get(self) -> float:
        """Get current counter value."""
        with self._lock:
            return self._value


class Gauge(Metric):
    """Gauge metric that can go up or down."""
    
    def __init__(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None):
        super().__init__(name, MetricType.GAUGE, description, labels)
        self._value = 0.0
    
    def set(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Set the gauge value."""
        with self._lock:
            self._value = value
            self.record(value, labels)
    
    def increment(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment the gauge."""
        with self._lock:
            self._value += value
            self.record(self._value, labels)
    
    def decrement(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Decrement the gauge."""
        self.increment(-value, labels)
    
    def get(self) -> float:
        """Get current gauge value."""
        with self._lock:
            return self._value


class Histogram(Metric):
    """Histogram metric for tracking distributions."""
    
    def __init__(self, name: str, buckets: Optional[List[float]] = None,
                 description: str = "", labels: Optional[Dict[str, str]] = None):
        super().__init__(name, MetricType.HISTOGRAM, description, labels)
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        self._bucket_counts = defaultdict(int)
    
    def observe(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Record an observation."""
        self.record(value, labels)
        
        # Update bucket counts
        with self._lock:
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[bucket] += 1


class Timer(Metric):
    """Timer metric for measuring durations."""
    
    def __init__(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None):
        super().__init__(name, MetricType.TIMER, description, labels)
    
    def time(self, labels: Optional[Dict[str, str]] = None):
        """Context manager for timing operations."""
        return TimerContext(self, labels)
    
    def record_duration(self, duration_seconds: float, labels: Optional[Dict[str, str]] = None):
        """Record a duration in seconds."""
        self.record(duration_seconds * 1000, labels)  # Store in milliseconds


class TimerContext:
    """Context manager for timing operations."""
    
    def __init__(self, timer: Timer, labels: Optional[Dict[str, str]] = None):
        self.timer = timer
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.timer.record_duration(duration, self.labels)
        return False


class PerformanceMetrics:
    """Collection of performance-related metrics."""
    
    def __init__(self):
        # Latency metrics
        self.perception_latency = Timer("perception_latency_ms", 
                                      "Time taken for perception processing")
        self.reasoning_latency = Timer("reasoning_latency_ms",
                                     "Time taken for reasoning operations")
        self.memory_access_latency = Timer("memory_access_latency_ms",
                                         "Time taken for memory operations")
        self.action_execution_latency = Timer("action_execution_latency_ms",
                                            "Time taken for action execution")
        
        # Throughput metrics
        self.tasks_processed = Counter("tasks_processed_total",
                                     "Total number of tasks processed")
        self.tasks_failed = Counter("tasks_failed_total",
                                  "Total number of failed tasks")
        
        # Queue metrics
        self.queue_size = Gauge("queue_size", "Current size of task queue")
        self.active_workers = Gauge("active_workers", "Number of active workers")


class SystemMetrics:
    """Collection of system-level metrics."""
    
    def __init__(self):
        # CPU metrics
        self.cpu_usage = Gauge("cpu_usage_percent", "CPU usage percentage")
        self.cpu_temperature = Gauge("cpu_temperature_celsius", "CPU temperature")
        
        # Memory metrics
        self.memory_usage = Gauge("memory_usage_bytes", "Memory usage in bytes")
        self.memory_percent = Gauge("memory_usage_percent", "Memory usage percentage")
        
        # Disk metrics
        self.disk_usage = Gauge("disk_usage_bytes", "Disk usage in bytes")
        self.disk_io_read = Counter("disk_io_read_bytes", "Disk read bytes")
        self.disk_io_write = Counter("disk_io_write_bytes", "Disk write bytes")
        
        # Network metrics
        self.network_sent = Counter("network_sent_bytes", "Network bytes sent")
        self.network_recv = Counter("network_recv_bytes", "Network bytes received")
        
        # Start collection thread
        self._stop_event = threading.Event()
        self._collection_thread = threading.Thread(target=self._collect_system_metrics)
        self._collection_thread.daemon = True
        self._collection_thread.start()
    
    def _collect_system_metrics(self):
        """Continuously collect system metrics."""
        while not self._stop_event.is_set():
            try:
                # CPU metrics
                self.cpu_usage.set(psutil.cpu_percent(interval=1))
                
                # Memory metrics
                memory = psutil.virtual_memory()
                self.memory_usage.set(memory.used)
                self.memory_percent.set(memory.percent)
                
                # Disk metrics
                disk = psutil.disk_usage('/')
                self.disk_usage.set(disk.used)
                
                # Network metrics (deltas)
                net_io = psutil.net_io_counters()
                self.network_sent.increment(net_io.bytes_sent)
                self.network_recv.increment(net_io.bytes_recv)
                
            except Exception as e:
                # Log error but continue
                import logging
                logging.debug(f"Error collecting system metrics: {e}")
            
            # Check stop event more frequently
            for _ in range(50):  # Check every 0.1s, total 5s
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)
    
    def stop(self):
        """Stop metric collection."""
        self._stop_event.set()


class CognitiveMetrics:
    """Collection of AGI cognitive metrics."""
    
    def __init__(self):
        # Cognitive load metrics
        self.cognitive_load = Gauge("cognitive_load_percent",
                                  "Current cognitive load percentage")
        self.reasoning_depth = Histogram("reasoning_depth",
                                       buckets=[1, 2, 3, 5, 10, 15, 20],
                                       description="Depth of reasoning chains")
        
        # Learning metrics
        self.learning_rate = Gauge("learning_rate", "Current learning rate")
        self.knowledge_items = Counter("knowledge_items_total",
                                     "Total knowledge items stored")
        
        # Consciousness metrics
        self.consciousness_level = Gauge("consciousness_level",
                                       "Current consciousness/awareness level")
        self.introspection_frequency = Counter("introspection_events_total",
                                             "Total introspection events")
        
        # Goal metrics
        self.active_goals = Gauge("active_goals", "Number of active goals")
        self.goal_completion_rate = Gauge("goal_completion_rate",
                                        "Goal completion rate")


class MetricsCollector:
    """Central metrics collection and management."""
    
    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self._lock = threading.Lock()
        
        # Initialize standard metric collections
        self.performance = PerformanceMetrics()
        self.system = SystemMetrics()
        self.cognitive = CognitiveMetrics()
        
        # Register all metrics
        self._register_collection_metrics(self.performance)
        self._register_collection_metrics(self.system)
        self._register_collection_metrics(self.cognitive)
    
    def _register_collection_metrics(self, collection):
        """Register all metrics from a collection object."""
        for attr_name in dir(collection):
            attr = getattr(collection, attr_name)
            if isinstance(attr, Metric):
                self.register_metric(attr)
    
    def register_metric(self, metric: Metric):
        """Register a metric for collection."""
        with self._lock:
            self.metrics[metric.name] = metric
    
    def get_metric(self, name: str) -> Optional[Metric]:
        """Get a metric by name."""
        with self._lock:
            return self.metrics.get(name)
    
    def get_all_metrics(self) -> Dict[str, Metric]:
        """Get all registered metrics."""
        with self._lock:
            return self.metrics.copy()
    
    def get_summary(self, window: Optional[timedelta] = None) -> Dict[str, Any]:
        """Get summary of all metrics."""
        summary = {}
        
        with self._lock:
            for name, metric in self.metrics.items():
                metric_summary = metric.get_summary(window)
                if metric_summary:
                    summary[name] = {
                        "type": metric.type.value,
                        "summary": metric_summary.__dict__
                    }
                    
                    # Add current value for counters and gauges
                    if isinstance(metric, (Counter, Gauge)):
                        summary[name]["current"] = metric.get()
        
        return summary
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        with self._lock:
            for name, metric in self.metrics.items():
                # Add metric help and type
                lines.append(f"# HELP {name} {metric.description}")
                lines.append(f"# TYPE {name} {metric.type.value}")
                
                # Add metric values
                if isinstance(metric, (Counter, Gauge)):
                    value = metric.get()
                    labels_str = self._format_labels(metric.labels)
                    lines.append(f"{name}{labels_str} {value}")
                elif isinstance(metric, Histogram):
                    # Add histogram buckets
                    for bucket, count in metric._bucket_counts.items():
                        labels = {**metric.labels, "le": str(bucket)}
                        labels_str = self._format_labels(labels)
                        lines.append(f"{name}_bucket{labels_str} {count}")
                    
                    # Add summary
                    summary = metric.get_summary()
                    if summary:
                        labels_str = self._format_labels(metric.labels)
                        lines.append(f"{name}_count{labels_str} {summary.count}")
                        lines.append(f"{name}_sum{labels_str} {summary.sum}")
                
                lines.append("")  # Empty line between metrics
        
        return "\n".join(lines)
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus export."""
        if not labels:
            return ""
        
        label_pairs = [f'{k}="{v}"' for k, v in labels.items()]
        return "{" + ",".join(label_pairs) + "}"
    
    def shutdown(self):
        """Shutdown metrics collection."""
        self.system.stop()


# Global metrics collector instance
_metrics_collector = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector