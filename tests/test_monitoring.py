"""Tests for the monitoring and metrics system."""

import asyncio
import json
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from core.monitoring.monitoring import (
    HealthStatus, HealthCheckResult, HealthCheck, AlertLevel, Alert,
    AlertManager, MonitoringService, DashboardExporter
)
from core.monitoring.metrics import (
    MetricType, MetricValue, Counter, Gauge, Histogram, Timer,
    PerformanceMetrics, SystemMetrics, CognitiveMetrics, MetricsCollector
)


class TestHealthChecks:
    """Test health check functionality."""
    
    def test_health_check_result_creation(self):
        """Test creating health check results."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={"metric": 42}
        )
        
        assert result.name == "test_check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.details["metric"] == 42
        assert isinstance(result.timestamp, datetime)
    
    def test_health_check_execution(self):
        """Test health check execution."""
        check_count = 0
        
        def test_check():
            nonlocal check_count
            check_count += 1
            return HealthCheckResult(
                name="test",
                status=HealthStatus.HEALTHY,
                message=f"Check {check_count}"
            )
        
        health_check = HealthCheck("test", test_check, interval=timedelta(seconds=1))
        
        # First check should execute
        result1 = health_check.check()
        assert result1.message == "Check 1"
        assert check_count == 1
        
        # Immediate second check should return cached result
        result2 = health_check.check()
        assert result2.message == "Check 1"
        assert check_count == 1
        
        # Force check should execute
        result3 = health_check.check(force=True)
        assert result3.message == "Check 2"
        assert check_count == 2
    
    def test_health_check_failure(self):
        """Test health check handling failures."""
        def failing_check():
            raise Exception("Check failed")
        
        health_check = HealthCheck("failing", failing_check)
        result = health_check.check()
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "Check failed" in result.message


class TestAlertManager:
    """Test alert management functionality."""
    
    def test_alert_creation(self):
        """Test creating and managing alerts."""
        manager = AlertManager()
        
        # Create alert
        alert = manager.create_alert(
            level=AlertLevel.WARNING,
            source="test_system",
            message="Test warning",
            details={"value": 100}
        )
        
        assert alert.level == AlertLevel.WARNING
        assert alert.source == "test_system"
        assert alert.message == "Test warning"
        assert alert.details["value"] == 100
        assert not alert.resolved
        
        # Check active alerts
        active = manager.get_active_alerts()
        assert len(active) == 1
        assert active[0].id == alert.id
    
    def test_alert_resolution(self):
        """Test resolving alerts."""
        manager = AlertManager()
        
        # Create and resolve alert
        alert = manager.create_alert(AlertLevel.ERROR, "test", "Error")
        manager.resolve_alert(alert.id)
        
        # Check alert is resolved
        assert alert.resolved
        assert alert.resolved_at is not None
        
        # Check no active alerts
        active = manager.get_active_alerts()
        assert len(active) == 0
    
    def test_alert_filtering(self):
        """Test filtering alerts."""
        manager = AlertManager()
        
        # Create multiple alerts
        manager.create_alert(AlertLevel.INFO, "test", "Info")
        manager.create_alert(AlertLevel.WARNING, "test", "Warning")
        manager.create_alert(AlertLevel.ERROR, "test", "Error")
        
        # Filter by level
        warnings = manager.get_alerts(level=AlertLevel.WARNING)
        assert len(warnings) == 1
        assert warnings[0].level == AlertLevel.WARNING
        
        # Filter by time
        since = datetime.now() - timedelta(minutes=1)
        recent = manager.get_alerts(since=since)
        assert len(recent) == 3
    
    def test_alert_handlers(self):
        """Test alert handler registration and execution."""
        manager = AlertManager()
        handled_alerts = []
        
        def handler(alert: Alert):
            handled_alerts.append(alert)
        
        manager.register_handler(handler)
        
        # Create alert
        alert = manager.create_alert(AlertLevel.CRITICAL, "test", "Critical")
        
        # Check handler was called
        assert len(handled_alerts) == 1
        assert handled_alerts[0].id == alert.id


class TestMetrics:
    """Test metrics collection functionality."""
    
    def test_counter_metric(self):
        """Test counter metric behavior."""
        counter = Counter("test_counter", "Test counter")
        
        # Initial value
        assert counter.get() == 0
        
        # Increment
        counter.increment()
        assert counter.get() == 1
        
        counter.increment(5)
        assert counter.get() == 6
        
        # Should not allow negative increment
        with pytest.raises(ValueError):
            counter.increment(-1)
    
    def test_gauge_metric(self):
        """Test gauge metric behavior."""
        gauge = Gauge("test_gauge", "Test gauge")
        
        # Set value
        gauge.set(42)
        assert gauge.get() == 42
        
        # Increment/decrement
        gauge.increment(8)
        assert gauge.get() == 50
        
        gauge.decrement(10)
        assert gauge.get() == 40
    
    def test_histogram_metric(self):
        """Test histogram metric behavior."""
        histogram = Histogram("test_histogram", buckets=[1, 5, 10])
        
        # Record observations
        histogram.observe(0.5)
        histogram.observe(3)
        histogram.observe(7)
        histogram.observe(15)
        
        # Check bucket counts
        assert histogram._bucket_counts[1] == 1  # 0.5 <= 1
        assert histogram._bucket_counts[5] == 2  # 0.5, 3 <= 5
        assert histogram._bucket_counts[10] == 3  # 0.5, 3, 7 <= 10
    
    def test_timer_metric(self):
        """Test timer metric behavior."""
        timer = Timer("test_timer", "Test timer")
        
        # Time an operation
        with timer.time():
            time.sleep(0.1)
        
        # Check recorded duration
        values = timer.get_values()
        assert len(values) == 1
        assert values[0].value >= 100  # At least 100ms
        
        # Record duration directly
        timer.record_duration(0.5)
        values = timer.get_values()
        assert len(values) == 2
        assert values[1].value == 500  # 500ms
    
    def test_metric_summary(self):
        """Test metric summary statistics."""
        gauge = Gauge("test_summary")
        
        # Record multiple values
        for i in range(10):
            gauge.set(i)
        
        summary = gauge.get_summary()
        assert summary.count == 10
        assert summary.min == 0
        assert summary.max == 9
        assert summary.mean == 4.5
        assert summary.median == 4.5


class TestMetricsCollector:
    """Test central metrics collection."""
    
    def test_metric_registration(self):
        """Test registering and retrieving metrics."""
        collector = MetricsCollector()
        
        # Check standard metrics are registered
        assert collector.get_metric("perception_latency_ms") is not None
        assert collector.get_metric("cpu_usage_percent") is not None
        assert collector.get_metric("cognitive_load_percent") is not None
        
        # Register custom metric
        custom = Counter("custom_metric")
        collector.register_metric(custom)
        assert collector.get_metric("custom_metric") == custom
    
    def test_metrics_summary(self):
        """Test getting metrics summary."""
        collector = MetricsCollector()
        
        # Record some metrics
        collector.performance.tasks_processed.increment(10)
        collector.cognitive.cognitive_load.set(75)
        
        # Get summary
        summary = collector.get_summary()
        assert "tasks_processed_total" in summary
        assert summary["tasks_processed_total"]["current"] == 10
        assert "cognitive_load_percent" in summary
        assert summary["cognitive_load_percent"]["current"] == 75
    
    def test_prometheus_export(self):
        """Test Prometheus format export."""
        collector = MetricsCollector()
        
        # Record metrics
        collector.performance.tasks_processed.increment(5)
        collector.system.cpu_usage.set(50)
        
        # Export
        prometheus_text = collector.export_prometheus()
        
        # Check format
        assert "# HELP tasks_processed_total" in prometheus_text
        assert "# TYPE tasks_processed_total counter" in prometheus_text
        assert "tasks_processed_total 5" in prometheus_text
        assert "# TYPE cpu_usage_percent gauge" in prometheus_text
        assert "cpu_usage_percent 50" in prometheus_text


class TestMonitoringService:
    """Test monitoring service integration."""
    
    def test_service_initialization(self):
        """Test monitoring service setup."""
        service = MonitoringService(prometheus_port=9091)
        
        assert service.prometheus_port == 9091
        assert service.collector is not None
        assert service.alert_manager is not None
        assert len(service.health_checks) > 0  # Default checks registered
    
    def test_health_status_aggregation(self):
        """Test overall health status calculation."""
        service = MonitoringService()
        
        # Register test health checks
        service.register_health_check(
            "healthy",
            lambda: HealthCheckResult("healthy", HealthStatus.HEALTHY)
        )
        service.register_health_check(
            "degraded",
            lambda: HealthCheckResult("degraded", HealthStatus.DEGRADED)
        )
        
        # Get overall status
        status = service.get_health_status()
        assert status["status"] == HealthStatus.DEGRADED.value
        assert len(status["checks"]) >= 2
    
    @patch('psutil.virtual_memory')
    @patch('psutil.cpu_percent')
    def test_default_health_checks(self, mock_cpu, mock_memory):
        """Test default system health checks."""
        # Mock high resource usage
        mock_memory.return_value = MagicMock(percent=85, available=1000000)
        mock_cpu.return_value = 75
        
        service = MonitoringService()
        
        # Check memory health
        memory_check = service.health_checks["memory"]
        result = memory_check.check(force=True)
        assert result.status == HealthStatus.DEGRADED
        
        # Check CPU health
        cpu_check = service.health_checks["cpu"]
        result = cpu_check.check(force=True)
        assert result.status == HealthStatus.DEGRADED
    
    def test_dashboard_exporter(self):
        """Test dashboard export functionality."""
        service = MonitoringService()
        
        # Create some test data
        service.collector.performance.tasks_processed.increment(100)
        service.alert_manager.create_alert(AlertLevel.WARNING, "test", "Test alert")
        
        # Export Grafana dashboard
        dashboard = service.dashboard_exporter.export_grafana_dashboard()
        assert dashboard["dashboard"]["title"] == "Jarvis AGI Monitoring"
        assert len(dashboard["dashboard"]["panels"]) > 0
        
        # Export metrics snapshot
        snapshot = service.dashboard_exporter.export_metrics_snapshot()
        assert "timestamp" in snapshot
        assert "metrics" in snapshot
        assert "health" in snapshot
        assert "alerts" in snapshot
        assert len(snapshot["alerts"]) == 1


class TestPerformanceMetrics:
    """Test performance-specific metrics."""
    
    def test_latency_tracking(self):
        """Test tracking various latency metrics."""
        metrics = PerformanceMetrics()
        
        # Track perception latency
        with metrics.perception_latency.time():
            time.sleep(0.05)
        
        # Track reasoning latency
        with metrics.reasoning_latency.time(labels={"system": "1"}):
            time.sleep(0.02)
        
        # Check values
        perception_values = metrics.perception_latency.get_values()
        assert len(perception_values) == 1
        assert perception_values[0].value >= 50  # At least 50ms
        
        reasoning_values = metrics.reasoning_latency.get_values()
        assert len(reasoning_values) == 1
        assert reasoning_values[0].labels["system"] == "1"
    
    def test_throughput_metrics(self):
        """Test task processing throughput metrics."""
        metrics = PerformanceMetrics()
        
        # Process tasks
        for i in range(10):
            if i % 3 == 0:
                metrics.tasks_failed.increment()
            else:
                metrics.tasks_processed.increment()
        
        assert metrics.tasks_processed.get() == 7
        assert metrics.tasks_failed.get() == 3


class TestCognitiveMetrics:
    """Test cognitive-specific metrics."""
    
    def test_cognitive_load_tracking(self):
        """Test cognitive load and consciousness metrics."""
        metrics = CognitiveMetrics()
        
        # Set cognitive load
        metrics.cognitive_load.set(65)
        assert metrics.cognitive_load.get() == 65
        
        # Track reasoning depth
        metrics.reasoning_depth.observe(3)
        metrics.reasoning_depth.observe(5)
        metrics.reasoning_depth.observe(12)
        
        # Set consciousness level
        metrics.consciousness_level.set(0.8)
        assert metrics.consciousness_level.get() == 0.8
    
    def test_learning_metrics(self):
        """Test learning and knowledge metrics."""
        metrics = CognitiveMetrics()
        
        # Track knowledge items
        for _ in range(50):
            metrics.knowledge_items.increment()
        
        assert metrics.knowledge_items.get() == 50
        
        # Set learning rate
        metrics.learning_rate.set(0.01)
        assert metrics.learning_rate.get() == 0.01


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for monitoring system."""
    
    async def test_monitoring_with_alerts(self):
        """Test monitoring service with alert generation."""
        service = MonitoringService()
        
        # Register a failing health check
        def failing_check():
            return HealthCheckResult(
                name="failing",
                status=HealthStatus.UNHEALTHY,
                message="System failure"
            )
        
        service.register_health_check("failing", failing_check)
        
        # Start service (would normally start HTTP server)
        # service.start()  # Skip actual server start in tests
        
        # Manually trigger health monitoring
        for name, check in service.health_checks.items():
            result = check.check()
            if result.status == HealthStatus.UNHEALTHY:
                service.alert_manager.create_alert(
                    level=AlertLevel.ERROR,
                    source=f"health_check.{name}",
                    message=result.message
                )
        
        # Check alerts were created
        alerts = service.alert_manager.get_active_alerts()
        failing_alerts = [a for a in alerts if a.source == "health_check.failing"]
        assert len(failing_alerts) == 1
    
    async def test_metrics_lifecycle(self):
        """Test complete metrics lifecycle."""
        collector = MetricsCollector()
        
        # Simulate operations
        start = time.time()
        with collector.performance.perception_latency.time():
            await asyncio.sleep(0.01)
        
        with collector.performance.reasoning_latency.time(labels={"system": "2"}):
            await asyncio.sleep(0.02)
        
        collector.performance.tasks_processed.increment()
        collector.cognitive.cognitive_load.set(45)
        
        # Get summary after operations
        summary = collector.get_summary()
        
        # Verify metrics were recorded
        assert "perception_latency_ms" in summary
        assert "reasoning_latency_ms" in summary
        assert "tasks_processed_total" in summary
        assert summary["tasks_processed_total"]["current"] == 1
        assert "cognitive_load_percent" in summary
        assert summary["cognitive_load_percent"]["current"] == 45
        
        # Test cleanup
        collector.shutdown()