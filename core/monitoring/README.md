# Monitoring and Logging Framework

This module provides comprehensive monitoring, metrics collection, and structured logging for the Jarvis AGI system.

## Features

### Structured Logging
- JSON-formatted logs for easy parsing and analysis
- Contextual logging with thread-safe context management
- Performance logging decorators
- Cognitive operation tracking

### Metrics Collection
- **Performance Metrics**: Latency tracking for perception, reasoning, memory, and actions
- **System Metrics**: CPU, memory, disk, and network usage
- **Cognitive Metrics**: Cognitive load, consciousness level, reasoning depth
- **Custom Metrics**: Counter, Gauge, Histogram, and Timer types

### Health Monitoring
- Configurable health checks with intervals
- Automatic alert generation for unhealthy services
- Overall system health aggregation

### Alert Management
- Multi-level alerts (INFO, WARNING, ERROR, CRITICAL)
- Alert retention and automatic cleanup
- Custom alert handlers

### Integration
- Prometheus metrics endpoint for scraping
- Grafana dashboard configuration export
- Real-time metrics visualization support

## Usage

### Basic Setup

```python
from core.monitoring.monitoring import MonitoringService
from core.monitoring.logger import setup_logging, get_logger
from core.monitoring.metrics import get_metrics_collector

# Setup structured logging
setup_logging(
    level="INFO",
    structured=True,
    log_file="logs/jarvis.log"
)

# Get logger instance
logger = get_logger(__name__)

# Initialize monitoring service
monitoring = MonitoringService(prometheus_port=9090)
monitoring.start()

# Get metrics collector
metrics = get_metrics_collector()
```

### Logging Examples

```python
# Basic logging with context
with LogContext(user_id="123", operation="inference"):
    logger.info("Starting inference")
    
# Performance logging
@performance_logger("complex_operation")
def process_data(data):
    # Function execution will be timed and logged
    return transform(data)

# Cognitive operation logging
with log_cognitive_operation("perception", "image_processing"):
    result = process_image(image)
```

### Metrics Examples

```python
# Track latency
with metrics.performance.perception_latency.time():
    result = perceive(input_data)

# Count events
metrics.performance.tasks_processed.increment()
metrics.performance.tasks_failed.increment()

# Track values
metrics.cognitive.cognitive_load.set(75.5)
metrics.performance.queue_size.set(queue.size())

# Record distributions
metrics.cognitive.reasoning_depth.observe(depth)
```

### Health Checks

```python
# Register custom health check
def check_model_health():
    if model.is_loaded():
        return HealthCheckResult(
            name="model",
            status=HealthStatus.HEALTHY,
            message="Model loaded and ready"
        )
    else:
        return HealthCheckResult(
            name="model",
            status=HealthStatus.UNHEALTHY,
            message="Model not loaded"
        )

monitoring.register_health_check("model", check_model_health)
```

### Alert Management

```python
# Create alerts
monitoring.alert_manager.create_alert(
    level=AlertLevel.WARNING,
    source="reasoning_engine",
    message="High latency detected",
    details={"latency_ms": 500}
)

# Register alert handler
def handle_critical_alerts(alert):
    if alert.level == AlertLevel.CRITICAL:
        notify_ops_team(alert)
        
monitoring.alert_manager.register_handler(handle_critical_alerts)
```

## Prometheus Integration

The monitoring service exposes metrics in Prometheus format at `http://localhost:9090/metrics`.

Configure Prometheus to scrape the endpoint:

```yaml
scrape_configs:
  - job_name: 'jarvis-agi'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
```

## Grafana Dashboard

Export dashboard configuration:

```python
dashboard_config = monitoring.dashboard_exporter.export_grafana_dashboard()
# Import this JSON into Grafana
```

## Architecture

```
monitoring/
├── logger.py          # Structured logging system
├── metrics.py         # Metrics collection and types
└── monitoring.py      # Main monitoring service with health checks and alerts
```

## Best Practices

1. **Use structured logging**: Always use the provided loggers for consistency
2. **Add context**: Use LogContext to add relevant metadata to log entries
3. **Track key metrics**: Monitor latency, throughput, and resource usage
4. **Set up alerts**: Configure alerts for critical thresholds
5. **Regular health checks**: Implement health checks for all major components
6. **Export metrics**: Use Prometheus/Grafana for visualization and alerting

## Testing

Run the comprehensive test suite:

```bash
pytest tests/test_monitoring.py -v
pytest tests/test_logger.py -v
```

Run the demo to see the monitoring in action:

```bash
python examples/monitoring_demo.py
```

## Performance Considerations

- Metrics are stored in memory with configurable retention
- Logging is asynchronous and thread-safe
- Health checks run on separate threads with intervals
- Prometheus endpoint is lightweight and efficient