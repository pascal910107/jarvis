"""Demo script showing how to use the monitoring and logging framework."""

import asyncio
import random
import time
from datetime import timedelta

from core.monitoring.monitoring import (
    MonitoringService, HealthCheckResult, HealthStatus, AlertLevel
)
from core.monitoring.logger import setup_logging, get_logger, LogContext, log_operation
from core.monitoring.metrics import get_metrics_collector


# Setup structured logging
setup_logging(
    level="INFO",
    structured=True,
    log_file="logs/jarvis_demo.log"
)

logger = get_logger(__name__)


class JarvisDemo:
    """Demo AGI system with monitoring."""
    
    def __init__(self):
        self.monitoring = MonitoringService(prometheus_port=9090)
        self.metrics = get_metrics_collector()
        self.is_healthy = True
        
        # Register custom health checks
        self.monitoring.register_health_check(
            "jarvis_core",
            self._check_jarvis_health,
            interval=timedelta(seconds=10)
        )
        
        # Register alert handlers
        self.monitoring.alert_manager.register_handler(self._handle_alert)
        
        logger.info("Jarvis demo initialized")
    
    def _check_jarvis_health(self) -> HealthCheckResult:
        """Custom health check for Jarvis."""
        if self.is_healthy:
            return HealthCheckResult(
                name="jarvis_core",
                status=HealthStatus.HEALTHY,
                message="All systems operational",
                details={"uptime": time.time()}
            )
        else:
            return HealthCheckResult(
                name="jarvis_core",
                status=HealthStatus.UNHEALTHY,
                message="System malfunction detected",
                details={"error": "Simulated failure"}
            )
    
    def _handle_alert(self, alert):
        """Handle monitoring alerts."""
        logger.warning(
            f"Alert received: {alert.message}",
            extra={
                "alert_id": alert.id,
                "alert_level": alert.level.value,
                "alert_source": alert.source
            }
        )
    
    async def perceive(self, input_data: str):
        """Simulate perception processing."""
        with LogContext(operation="perception", input_type="text"):
            logger.info(f"Processing input: {input_data[:50]}...")
            
            # Measure perception latency
            with self.metrics.performance.perception_latency.time():
                # Simulate processing time
                await asyncio.sleep(random.uniform(0.02, 0.08))
                
            logger.info("Perception complete")
            return {"processed": input_data, "features": len(input_data)}
    
    async def reason(self, perception_data: dict, system: int = 1):
        """Simulate reasoning process."""
        with LogContext(operation="reasoning", reasoning_system=system):
            logger.info(f"Starting System {system} reasoning")
            
            # Track reasoning depth
            depth = random.randint(1, 5) if system == 1 else random.randint(3, 15)
            self.metrics.cognitive.reasoning_depth.observe(depth)
            
            # Measure reasoning latency
            with self.metrics.performance.reasoning_latency.time(
                labels={"system": str(system)}
            ):
                # System 1: Fast intuitive
                if system == 1:
                    await asyncio.sleep(random.uniform(0.01, 0.04))
                # System 2: Slow deliberative
                else:
                    await asyncio.sleep(random.uniform(0.1, 0.4))
            
            logger.info(f"Reasoning complete (depth: {depth})")
            return {"decision": f"Action based on {perception_data}", "depth": depth}
    
    async def execute_action(self, action: dict):
        """Simulate action execution."""
        with log_operation("action_execution", logger, action_type="simulated"):
            # Measure execution time
            with self.metrics.performance.action_execution_latency.time():
                await asyncio.sleep(random.uniform(0.05, 0.15))
            
            # Randomly fail some actions
            if random.random() < 0.1:
                self.metrics.performance.tasks_failed.increment()
                raise Exception("Action execution failed")
            
            self.metrics.performance.tasks_processed.increment()
            return {"result": "success", "action": action}
    
    async def process_task(self, task_id: str, input_data: str):
        """Process a complete task through the AGI pipeline."""
        with LogContext(task_id=task_id):
            logger.info(f"Starting task {task_id}")
            
            try:
                # Update queue metrics
                self.metrics.performance.queue_size.decrement()
                self.metrics.performance.active_workers.increment()
                
                # Perception
                perception_result = await self.perceive(input_data)
                
                # Reasoning (System 1 first, then System 2 if needed)
                reasoning_result = await self.reason(perception_result, system=1)
                
                # Complex tasks need System 2
                if reasoning_result["depth"] > 3:
                    logger.info("Engaging System 2 reasoning")
                    reasoning_result = await self.reason(perception_result, system=2)
                
                # Execute action
                action_result = await self.execute_action(reasoning_result)
                
                logger.info(f"Task {task_id} completed successfully")
                return action_result
                
            except Exception as e:
                logger.error(f"Task {task_id} failed", exc_info=True)
                
                # Create alert for task failure
                self.monitoring.alert_manager.create_alert(
                    level=AlertLevel.ERROR,
                    source="task_processor",
                    message=f"Task {task_id} failed: {str(e)}",
                    details={"task_id": task_id, "error": str(e)}
                )
                raise
            finally:
                self.metrics.performance.active_workers.decrement()
    
    async def simulate_cognitive_load(self):
        """Simulate varying cognitive load."""
        while True:
            # Vary cognitive load
            load = 30 + 40 * abs(asyncio.get_event_loop().time() % 60 - 30) / 30
            self.metrics.cognitive.cognitive_load.set(load)
            
            # Update consciousness level based on load
            consciousness = 1.0 - (load / 200)  # Higher load = lower consciousness
            self.metrics.cognitive.consciousness_level.set(consciousness)
            
            # Set active goals
            goals = int(5 + 10 * (1 - load / 100))
            self.metrics.cognitive.active_goals.set(goals)
            
            # Occasional introspection
            if random.random() < 0.1:
                self.metrics.cognitive.introspection_frequency.increment()
                logger.info(
                    "Introspection event",
                    extra={
                        "cognitive_load": load,
                        "consciousness_level": consciousness,
                        "active_goals": goals
                    }
                )
            
            await asyncio.sleep(5)
    
    async def run_demo(self):
        """Run the demo with simulated tasks."""
        # Start monitoring service
        self.monitoring.start()
        logger.info(
            "Monitoring service started",
            extra={"prometheus_port": self.monitoring.prometheus_port}
        )
        
        # Start cognitive load simulation
        asyncio.create_task(self.simulate_cognitive_load())
        
        # Simulate task queue
        task_queue = []
        for i in range(20):
            task_queue.append(f"Task-{i:03d}")
        
        self.metrics.performance.queue_size.set(len(task_queue))
        
        # Process tasks with some concurrency
        active_tasks = []
        task_counter = 0
        
        while task_queue or active_tasks:
            # Start new tasks if we have capacity
            while len(active_tasks) < 3 and task_queue:
                task_id = task_queue.pop(0)
                input_data = f"Process request for {task_id} with data..."
                
                task = asyncio.create_task(
                    self.process_task(task_id, input_data)
                )
                active_tasks.append(task)
                task_counter += 1
            
            # Wait for some tasks to complete
            if active_tasks:
                done, active_tasks = await asyncio.wait(
                    active_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Update queue size
                self.metrics.performance.queue_size.set(len(task_queue))
            
            # Simulate system degradation
            if task_counter == 10:
                logger.warning("Simulating system degradation")
                self.is_healthy = False
                self.monitoring.alert_manager.create_alert(
                    level=AlertLevel.WARNING,
                    source="demo",
                    message="System entering degraded state",
                    details={"tasks_processed": task_counter}
                )
            
            # Simulate recovery
            if task_counter == 15:
                logger.info("System recovering")
                self.is_healthy = True
                
                # Resolve previous alerts
                for alert in self.monitoring.alert_manager.get_active_alerts():
                    if alert.source == "demo":
                        self.monitoring.alert_manager.resolve_alert(alert.id)
            
            await asyncio.sleep(0.1)
        
        # Final summary
        logger.info("Demo completed", extra={
            "total_tasks": task_counter,
            "metrics_summary": self.metrics.get_summary(window=timedelta(minutes=5))
        })
        
        # Print health status
        health_status = self.monitoring.get_health_status()
        logger.info("Final health status", extra={"health": health_status})
        
        # Export dashboard config
        dashboard = self.monitoring.dashboard_exporter.export_grafana_dashboard()
        logger.info("Grafana dashboard config exported", extra={
            "panels": len(dashboard["dashboard"]["panels"])
        })
        
        # Stop monitoring
        self.monitoring.stop()


async def main():
    """Run the monitoring demo."""
    print("=" * 60)
    print("Jarvis AGI Monitoring Demo")
    print("=" * 60)
    print()
    print("This demo simulates an AGI system with:")
    print("- Structured logging to console and file")
    print("- Performance metrics (latency, throughput)")
    print("- System metrics (CPU, memory)")
    print("- Cognitive metrics (load, consciousness)")
    print("- Health checks and alerts")
    print("- Prometheus metrics endpoint on port 9090")
    print()
    print("Metrics available at: http://localhost:9090/metrics")
    print("Health check at: http://localhost:9090/health")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    demo = JarvisDemo()
    
    try:
        await demo.run_demo()
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error("Demo failed", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())