"""Demo script showing configuration management usage."""

import os
from pathlib import Path

from core.config import (
    ConfigManager, ConfigSchema, FieldSchema, FieldType,
    setup_config, get_config_manager
)
from core.monitoring import setup_logging, get_logger

# Setup logging
setup_logging(level="INFO")
logger = get_logger(__name__)


def create_schema():
    """Create configuration schema for validation."""
    # Server schema
    server_schema = ConfigSchema([
        FieldSchema("host", FieldType.STRING, required=True),
        FieldSchema("port", FieldType.PORT, required=True),
        FieldSchema("workers", FieldType.INTEGER, min_value=1, max_value=100),
        FieldSchema("debug", FieldType.BOOLEAN, default=False)
    ])
    
    # Monitoring schema
    monitoring_schema = ConfigSchema([
        FieldSchema("prometheus", FieldType.DICT),
        FieldSchema("logging", FieldType.DICT),
        FieldSchema("health_checks", FieldType.DICT),
        FieldSchema("alerts", FieldType.DICT)
    ])
    
    # Main schema
    main_schema = ConfigSchema([
        FieldSchema("server", FieldType.DICT, nested_schema=server_schema),
        FieldSchema("cognitive", FieldType.DICT),
        FieldSchema("distributed", FieldType.DICT),
        FieldSchema("monitoring", FieldType.DICT, nested_schema=monitoring_schema),
        FieldSchema("hardware", FieldType.DICT),
        FieldSchema("security", FieldType.DICT),
        FieldSchema("features", FieldType.DICT)
    ])
    
    return main_schema


def demo_basic_usage():
    """Demonstrate basic configuration usage."""
    print("\n" + "=" * 60)
    print("BASIC CONFIGURATION USAGE")
    print("=" * 60)
    
    # Create configuration manager
    manager = ConfigManager()
    
    # Load from dictionary
    manager.load_source("defaults", {
        "app_name": "Jarvis AGI",
        "version": "1.0.0",
        "server": {
            "host": "0.0.0.0",
            "port": 8000
        }
    })
    
    # Get configuration values
    print(f"\nApp Name: {manager.get('app_name')}")
    print(f"Version: {manager.get('version')}")
    print(f"Server Host: {manager.get('server.host')}")
    print(f"Server Port: {manager.get('server.port')}")
    
    # Update configuration
    manager.set("server.port", 8080)
    print(f"\nUpdated Port: {manager.get('server.port')}")
    
    # Get section
    server_config = manager.get_section("server")
    print(f"\nServer Config: {server_config}")


def demo_multi_source():
    """Demonstrate multiple configuration sources."""
    print("\n" + "=" * 60)
    print("MULTIPLE CONFIGURATION SOURCES")
    print("=" * 60)
    
    manager = ConfigManager()
    
    # Load base configuration
    manager.load_source("base", {
        "app": "jarvis",
        "debug": False,
        "database": {
            "host": "localhost",
            "port": 5432
        }
    }, priority=1)
    
    # Load environment overrides
    os.environ["APP_DEBUG"] = "true"
    os.environ["APP_DATABASE__HOST"] = "prod-db.example.com"
    manager.load_source("env", "APP", format="env", priority=2)
    
    # Load development overrides
    manager.load_source("dev", {
        "database": {
            "port": 5433,
            "name": "jarvis_dev"
        }
    }, priority=3)
    
    # Show merged configuration
    print("\nMerged Configuration:")
    print(f"  Debug: {manager.get('debug')}")  # From env
    print(f"  Database Host: {manager.get('database.host')}")  # From env
    print(f"  Database Port: {manager.get('database.port')}")  # From dev
    print(f"  Database Name: {manager.get('database.name')}")  # From dev
    
    # Show source information
    print("\nLoaded Sources:")
    for name, info in manager.get_sources().items():
        print(f"  {name}: priority={info['priority']}, keys={info['keys']}")
    
    # Cleanup
    del os.environ["APP_DEBUG"]
    del os.environ["APP_DATABASE__HOST"]


def demo_validation():
    """Demonstrate configuration validation."""
    print("\n" + "=" * 60)
    print("CONFIGURATION VALIDATION")
    print("=" * 60)
    
    # Create schema
    schema = ConfigSchema([
        FieldSchema("host", FieldType.STRING, required=True),
        FieldSchema("port", FieldType.PORT, required=True),
        FieldSchema("workers", FieldType.INTEGER, min_value=1, max_value=10),
        FieldSchema("debug", FieldType.BOOLEAN, default=False),
        FieldSchema("log_level", FieldType.ENUM, 
                   allowed_values=["DEBUG", "INFO", "WARNING", "ERROR"])
    ])
    
    # Create manager with schema
    manager = ConfigManager(schema)
    
    # Load valid configuration
    print("\nTesting valid configuration...")
    manager.load_source("valid", {
        "host": "localhost",
        "port": 8080,
        "workers": 4,
        "log_level": "INFO"
    })
    
    errors = manager.validate()
    print(f"Validation errors: {len(errors)}")
    
    # Test invalid configuration
    print("\nTesting invalid configuration...")
    manager.load_source("invalid", {
        "host": "localhost",
        "port": 70000,  # Invalid port
        "workers": 20,   # Too many workers
        "log_level": "TRACE"  # Invalid level
    })
    
    errors = manager.validate()
    print(f"Validation errors: {len(errors)}")
    for error in errors:
        print(f"  - {error}")


def demo_change_notifications():
    """Demonstrate configuration change notifications."""
    print("\n" + "=" * 60)
    print("CONFIGURATION CHANGE NOTIFICATIONS")
    print("=" * 60)
    
    manager = ConfigManager()
    manager.load_source("default", {"counter": 0})
    
    # Register change handler
    def on_config_change(key, old_value, new_value):
        print(f"Config changed: {key} = {old_value} -> {new_value}")
    
    manager.register_change_handler(on_config_change)
    
    # Make changes
    print("\nMaking configuration changes...")
    manager.set("counter", 1)
    manager.set("counter", 2)
    manager.set("new.feature.enabled", True)
    
    # Batch updates
    print("\nBatch update...")
    manager.update({
        "counter": 10,
        "status": "active"
    })


def demo_real_world_usage():
    """Demonstrate real-world configuration setup."""
    print("\n" + "=" * 60)
    print("REAL-WORLD CONFIGURATION EXAMPLE")
    print("=" * 60)
    
    # Set some environment variables for demo
    os.environ["JARVIS_HOST"] = "api.jarvis.ai"
    os.environ["JARVIS_PORT"] = "443"
    os.environ["JARVIS_DEBUG"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"
    
    # Setup configuration from multiple sources
    config_file = Path(__file__).parent.parent / "config" / "jarvis.yaml"
    
    # Create schema
    schema = create_schema()
    
    # Initialize global configuration
    sources = [
        # Default configuration
        {
            "name": "defaults",
            "source": {
                "server": {"host": "localhost", "port": 8080},
                "monitoring": {"logging": {"level": "INFO"}}
            },
            "priority": 1
        }
    ]
    
    # Add file configuration if it exists
    if config_file.exists():
        sources.append({
            "name": "config_file",
            "source": str(config_file),
            "format": "yaml",
            "priority": 2
        })
        print(f"Loading configuration from: {config_file}")
    else:
        print(f"Configuration file not found: {config_file}")
    
    # Setup global configuration
    manager = setup_config(sources, schema)
    
    # Access configuration
    print("\nServer Configuration:")
    print(f"  Host: {manager.get('server.host')}")
    print(f"  Port: {manager.get('server.port')}")
    print(f"  Debug: {manager.get('server.debug')}")
    
    if manager.get("cognitive"):
        print("\nCognitive Configuration:")
        print(f"  Perception Latency: {manager.get('cognitive.perception.latency_threshold_ms')}ms")
        print(f"  System1 Enabled: {manager.get('cognitive.reasoning.system1.enabled')}")
        print(f"  Working Memory Capacity: {manager.get('cognitive.memory.working.capacity')}")
    
    print("\nMonitoring Configuration:")
    print(f"  Log Level: {manager.get('monitoring.logging.level')}")
    print(f"  Prometheus Enabled: {manager.get('monitoring.prometheus.enabled', False)}")
    
    # Export configuration (with sensitive values masked)
    print("\nExported Configuration (YAML, sensitive values masked):")
    print("-" * 60)
    yaml_export = manager.export(format="yaml", mask_sensitive=True)
    print(yaml_export[:500] + "...")  # Show first 500 chars
    
    # Cleanup
    for key in ["JARVIS_HOST", "JARVIS_PORT", "JARVIS_DEBUG", "LOG_LEVEL"]:
        if key in os.environ:
            del os.environ[key]


def main():
    """Run all configuration demos."""
    print("Configuration Management System Demo")
    print("===================================")
    
    demos = [
        ("Basic Usage", demo_basic_usage),
        ("Multiple Sources", demo_multi_source),
        ("Validation", demo_validation),
        ("Change Notifications", demo_change_notifications),
        ("Real-World Usage", demo_real_world_usage)
    ]
    
    for name, demo_func in demos:
        try:
            demo_func()
        except Exception as e:
            print(f"\nError in {name}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()