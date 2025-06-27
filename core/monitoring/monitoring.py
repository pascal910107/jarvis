"""Monitoring service with Prometheus integration and health checks."""

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Callable, Any
from urllib.parse import urlparse, parse_qs

from .logger import get_logger
from .metrics import get_metrics_collector, MetricsCollector


logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


class HealthCheck:
    """Health check interface."""
    
    def __init__(self, name: str, check_fn: Callable[[], HealthCheckResult],
                 interval: timedelta = timedelta(seconds=30)):
        self.name = name
        self.check_fn = check_fn
        self.interval = interval
        self.last_result: Optional[HealthCheckResult] = None
        self.last_check: Optional[datetime] = None
    
    def check(self, force: bool = False) -> HealthCheckResult:
        """Run the health check."""
        now = datetime.now()
        
        # Check if we need to run the check
        if not force and self.last_check and self.last_result:
            if now - self.last_check < self.interval:
                return self.last_result
        
        # Run the check
        try:
            result = self.check_fn()
            self.last_result = result
            self.last_check = now
            return result
        except Exception as e:
            # If check fails, return unhealthy
            result = HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}"
            )
            self.last_result = result
            self.last_check = now
            return result


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert notification."""
    id: str
    level: AlertLevel
    source: str
    message: str
    details: Dict[str, Any] = None
    timestamp: datetime = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self, retention_time: timedelta = timedelta(hours=24)):
        self.alerts: Dict[str, Alert] = {}
        self.retention_time = retention_time
        self.handlers: List[Callable[[Alert], None]] = []
        self._lock = threading.Lock()
        self._alert_counter = 0
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop)
        self._cleanup_thread.daemon = True
        self._cleanup_thread.start()
    
    def register_handler(self, handler: Callable[[Alert], None]):
        """Register an alert handler."""
        self.handlers.append(handler)
    
    def create_alert(self, level: AlertLevel, source: str, message: str,
                    details: Optional[Dict[str, Any]] = None) -> Alert:
        """Create and send an alert."""
        with self._lock:
            self._alert_counter += 1
            alert_id = f"{source}-{self._alert_counter}"
            
            alert = Alert(
                id=alert_id,
                level=level,
                source=source,
                message=message,
                details=details
            )
            
            self.alerts[alert_id] = alert
            
            # Send to handlers
            for handler in self.handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")
            
            logger.info(f"Alert created: {alert_id}",
                       extra={"alert_level": level.value, "source": source})
            
            return alert
    
    def resolve_alert(self, alert_id: str):
        """Mark an alert as resolved."""
        with self._lock:
            if alert_id in self.alerts:
                alert = self.alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.now()
                logger.info(f"Alert resolved: {alert_id}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active (unresolved) alerts."""
        with self._lock:
            return [a for a in self.alerts.values() if not a.resolved]
    
    def get_alerts(self, since: Optional[datetime] = None,
                   level: Optional[AlertLevel] = None) -> List[Alert]:
        """Get alerts matching criteria."""
        with self._lock:
            alerts = list(self.alerts.values())
            
            if since:
                alerts = [a for a in alerts if a.timestamp >= since]
            
            if level:
                alerts = [a for a in alerts if a.level == level]
            
            return alerts
    
    def _cleanup_loop(self):
        """Clean up old alerts periodically."""
        while True:
            try:
                time.sleep(3600)  # Check every hour
                
                with self._lock:
                    now = datetime.now()
                    expired = []
                    
                    for alert_id, alert in self.alerts.items():
                        if alert.resolved:
                            if alert.resolved_at and now - alert.resolved_at > self.retention_time:
                                expired.append(alert_id)
                        elif now - alert.timestamp > self.retention_time:
                            expired.append(alert_id)
                    
                    for alert_id in expired:
                        del self.alerts[alert_id]
                    
                    if expired:
                        logger.info(f"Cleaned up {len(expired)} expired alerts")
                        
            except Exception as e:
                logger.error(f"Alert cleanup failed: {e}")


class PrometheusHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""
    
    def do_GET(self):
        """Handle GET request for metrics."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/metrics':
            # Get metrics in Prometheus format
            collector = get_metrics_collector()
            metrics_text = collector.export_prometheus()
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(metrics_text.encode())
            
        elif parsed_path.path == '/health':
            # Health check endpoint
            monitoring_service = self.server.monitoring_service
            health_status = monitoring_service.get_health_status()
            
            # Determine overall status
            overall_status = HealthStatus.HEALTHY
            for check in health_status['checks']:
                if check['status'] == HealthStatus.UNHEALTHY.value:
                    overall_status = HealthStatus.UNHEALTHY
                    break
                elif check['status'] == HealthStatus.DEGRADED.value:
                    overall_status = HealthStatus.DEGRADED
            
            # Send response
            status_code = 200 if overall_status == HealthStatus.HEALTHY else 503
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(health_status).encode())
            
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"Prometheus endpoint: {format % args}")


class DashboardExporter:
    """Exports metrics and data for dashboard visualization."""
    
    def __init__(self, collector: MetricsCollector, 
                 monitoring_service: 'MonitoringService'):
        self.collector = collector
        self.monitoring_service = monitoring_service
    
    def export_grafana_dashboard(self) -> Dict[str, Any]:
        """Export dashboard configuration for Grafana."""
        return {
            "dashboard": {
                "title": "Jarvis AGI Monitoring",
                "uid": "jarvis-agi",
                "panels": [
                    # Performance panel
                    {
                        "title": "Latency Metrics",
                        "type": "graph",
                        "targets": [
                            {"expr": "perception_latency_ms"},
                            {"expr": "reasoning_latency_ms"},
                            {"expr": "memory_access_latency_ms"},
                            {"expr": "action_execution_latency_ms"}
                        ]
                    },
                    # System resources panel
                    {
                        "title": "System Resources",
                        "type": "graph",
                        "targets": [
                            {"expr": "cpu_usage_percent"},
                            {"expr": "memory_usage_percent"}
                        ]
                    },
                    # Cognitive metrics panel
                    {
                        "title": "Cognitive Metrics",
                        "type": "graph",
                        "targets": [
                            {"expr": "cognitive_load_percent"},
                            {"expr": "consciousness_level"},
                            {"expr": "active_goals"}
                        ]
                    },
                    # Task processing panel
                    {
                        "title": "Task Processing",
                        "type": "stat",
                        "targets": [
                            {"expr": "rate(tasks_processed_total[5m])"},
                            {"expr": "rate(tasks_failed_total[5m])"}
                        ]
                    }
                ]
            }
        }
    
    def export_metrics_snapshot(self) -> Dict[str, Any]:
        """Export current metrics snapshot."""
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": self.collector.get_summary(),
            "health": self.monitoring_service.get_health_status(),
            "alerts": [
                {
                    "id": alert.id,
                    "level": alert.level.value,
                    "source": alert.source,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat()
                }
                for alert in self.monitoring_service.alert_manager.get_active_alerts()
            ]
        }


class MonitoringService:
    """Central monitoring service coordinating metrics, health checks, and alerts."""
    
    def __init__(self, prometheus_port: int = 9090):
        self.prometheus_port = prometheus_port
        self.collector = get_metrics_collector()
        self.alert_manager = AlertManager()
        self.health_checks: Dict[str, HealthCheck] = {}
        self.dashboard_exporter = DashboardExporter(self.collector, self)
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        
        # Register default health checks
        self._register_default_health_checks()
        
        logger.info("Monitoring service initialized")
    
    def _register_default_health_checks(self):
        """Register default system health checks."""
        # Memory health check
        def check_memory():
            import psutil
            memory = psutil.virtual_memory()
            
            if memory.percent > 90:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Memory usage critical: {memory.percent}%",
                    details={"percent": memory.percent, "available": memory.available}
                )
            elif memory.percent > 80:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.DEGRADED,
                    message=f"Memory usage high: {memory.percent}%",
                    details={"percent": memory.percent, "available": memory.available}
                )
            else:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.HEALTHY,
                    message=f"Memory usage normal: {memory.percent}%",
                    details={"percent": memory.percent, "available": memory.available}
                )
        
        self.register_health_check("memory", check_memory)
        
        # CPU health check
        def check_cpu():
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent > 90:
                return HealthCheckResult(
                    name="cpu",
                    status=HealthStatus.UNHEALTHY,
                    message=f"CPU usage critical: {cpu_percent}%",
                    details={"percent": cpu_percent}
                )
            elif cpu_percent > 70:
                return HealthCheckResult(
                    name="cpu",
                    status=HealthStatus.DEGRADED,
                    message=f"CPU usage high: {cpu_percent}%",
                    details={"percent": cpu_percent}
                )
            else:
                return HealthCheckResult(
                    name="cpu",
                    status=HealthStatus.HEALTHY,
                    message=f"CPU usage normal: {cpu_percent}%",
                    details={"percent": cpu_percent}
                )
        
        self.register_health_check("cpu", check_cpu)
    
    def register_health_check(self, name: str, check_fn: Callable[[], HealthCheckResult],
                            interval: timedelta = timedelta(seconds=30)):
        """Register a health check."""
        self.health_checks[name] = HealthCheck(name, check_fn, interval)
        logger.info(f"Registered health check: {name}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status."""
        checks = []
        overall_status = HealthStatus.HEALTHY
        
        for name, health_check in self.health_checks.items():
            result = health_check.check()
            checks.append({
                "name": name,
                "status": result.status.value,
                "message": result.message,
                "details": result.details,
                "timestamp": result.timestamp.isoformat()
            })
            
            # Update overall status
            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "status": overall_status.value,
            "timestamp": datetime.now().isoformat(),
            "checks": checks
        }
    
    def start(self):
        """Start the monitoring service."""
        # Create HTTP server for Prometheus
        handler = type('PrometheusHandler', (PrometheusHandler,), {})
        self._server = HTTPServer(('', self.prometheus_port), handler)
        self._server.monitoring_service = self
        
        # Start server in background thread
        self._server_thread = threading.Thread(target=self._server.serve_forever)
        self._server_thread.daemon = True
        self._server_thread.start()
        
        logger.info(f"Prometheus metrics endpoint started on port {self.prometheus_port}")
        
        # Start periodic health check alerts
        self._start_health_monitoring()
    
    def _start_health_monitoring(self):
        """Start monitoring health checks and create alerts."""
        def monitor_health():
            while self._server:
                try:
                    time.sleep(60)  # Check every minute
                    
                    for name, health_check in self.health_checks.items():
                        result = health_check.check()
                        
                        # Create alerts for unhealthy checks
                        if result.status == HealthStatus.UNHEALTHY:
                            self.alert_manager.create_alert(
                                level=AlertLevel.ERROR,
                                source=f"health_check.{name}",
                                message=result.message,
                                details=result.details
                            )
                        elif result.status == HealthStatus.DEGRADED:
                            self.alert_manager.create_alert(
                                level=AlertLevel.WARNING,
                                source=f"health_check.{name}",
                                message=result.message,
                                details=result.details
                            )
                            
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
        
        monitor_thread = threading.Thread(target=monitor_health)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop(self):
        """Stop the monitoring service."""
        if self._server:
            self._server.shutdown()
            self._server = None
        
        self.collector.shutdown()
        logger.info("Monitoring service stopped")