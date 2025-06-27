"""Monitoring and logging framework for Jarvis AGI system.

This module provides:
- Structured JSON logging with contextual information
- Performance metrics collection (latency, throughput)
- System resource monitoring (CPU, memory, disk, network)
- Cognitive metrics (load, consciousness, reasoning depth)
- Health checks and alerting
- Prometheus metrics endpoint
- Grafana dashboard integration
"""

from .logger import (
    setup_logging,
    get_logger,
    LogContext,
    performance_logger,
    log_operation,
    log_cognitive_operation,
    StructuredLogger,
)

from .metrics import (
    MetricType,
    Counter,
    Gauge,
    Histogram,
    Timer,
    PerformanceMetrics,
    SystemMetrics,
    CognitiveMetrics,
    MetricsCollector,
    get_metrics_collector,
)

from .monitoring import (
    HealthStatus,
    HealthCheckResult,
    HealthCheck,
    AlertLevel,
    Alert,
    AlertManager,
    MonitoringService,
    DashboardExporter,
)

__all__ = [
    # Logger exports
    "setup_logging",
    "get_logger",
    "LogContext",
    "performance_logger",
    "log_operation",
    "log_cognitive_operation",
    "StructuredLogger",
    
    # Metrics exports
    "MetricType",
    "Counter",
    "Gauge", 
    "Histogram",
    "Timer",
    "PerformanceMetrics",
    "SystemMetrics",
    "CognitiveMetrics",
    "MetricsCollector",
    "get_metrics_collector",
    
    # Monitoring exports
    "HealthStatus",
    "HealthCheckResult",
    "HealthCheck",
    "AlertLevel",
    "Alert",
    "AlertManager",
    "MonitoringService",
    "DashboardExporter",
]