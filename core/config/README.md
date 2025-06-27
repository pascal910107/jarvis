# Configuration Management System

A flexible, hierarchical configuration management system for the Jarvis AGI project supporting multiple formats, validation, and runtime updates.

## Features

### Multi-Format Support
- **YAML**: Human-readable configuration files
- **JSON**: Machine-readable configuration
- **Environment Variables**: 12-factor app compliance
- **Dictionary**: Direct Python dictionary configuration
- **Auto-detection**: Automatic format detection based on file extension

### Configuration Hierarchy
- Multiple configuration sources with priority-based merging
- Environment variable expansion with defaults and requirements
- Nested configuration with dot-notation access
- Configuration inheritance and overrides

### Validation
- Schema-based validation with type checking
- Field constraints (min/max values, regex patterns)
- Required vs optional fields with defaults
- Custom validation rules

### Runtime Management
- Thread-safe configuration access
- Runtime configuration updates
- Change notifications with handlers
- Configuration persistence

## Usage

### Basic Configuration

```python
from core.config import ConfigManager

# Create configuration manager
config = ConfigManager()

# Load configuration from file
config.load_source("main", "config/jarvis.yaml")

# Get configuration values
host = config.get("server.host")
port = config.get("server.port", default=8080)

# Update configuration
config.set("server.workers", 4)
```

### Multiple Sources with Priority

```python
# Load base configuration (priority 1)
config.load_source("defaults", {
    "server": {"host": "localhost", "port": 8080},
    "debug": False
}, priority=1)

# Load environment overrides (priority 2)
config.load_source("env", "JARVIS", format="env", priority=2)

# Load local overrides (priority 3)
config.load_source("local", "config/local.yaml", priority=3)
```

### Environment Variable Expansion

Configuration files support environment variable expansion:

```yaml
server:
  host: ${JARVIS_HOST:-localhost}           # With default
  port: ${JARVIS_PORT:-8080}               # With default
  api_key: ${JARVIS_API_KEY:?Required}     # Required
  
database:
  url: "postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
```

### Schema Validation

```python
from core.config import ConfigSchema, FieldSchema, FieldType

# Define schema
schema = ConfigSchema([
    FieldSchema("host", FieldType.STRING, required=True),
    FieldSchema("port", FieldType.PORT, required=True),
    FieldSchema("workers", FieldType.INTEGER, min_value=1, max_value=100),
    FieldSchema("log_level", FieldType.ENUM, 
                allowed_values=["DEBUG", "INFO", "WARNING", "ERROR"])
])

# Create manager with schema
config = ConfigManager(schema)

# Validate configuration
errors = config.validate()
if errors:
    for error in errors:
        print(f"Validation error: {error}")
```

### Change Notifications

```python
# Register change handler
def on_config_change(key, old_value, new_value):
    print(f"Config changed: {key} = {old_value} -> {new_value}")

config.register_change_handler(on_config_change)

# Changes will trigger notifications
config.set("debug", True)
```

### Global Configuration

```python
from core.config import setup_config, get_config_manager

# Setup global configuration
sources = [
    {"name": "defaults", "source": "config/defaults.yaml", "priority": 1},
    {"name": "app", "source": "config/app.yaml", "priority": 2},
    {"name": "env", "source": "APP", "format": "env", "priority": 3}
]

setup_config(sources)

# Access global configuration anywhere
config = get_config_manager()
value = config.get("some.key")
```

## Configuration File Example

```yaml
# config/jarvis.yaml
server:
  host: ${JARVIS_HOST:-localhost}
  port: ${JARVIS_PORT:-8080}
  workers: 4
  
cognitive:
  perception:
    latency_threshold_ms: 100
    models:
      vision: resnet50
      
monitoring:
  prometheus:
    enabled: true
    port: 9090
  logging:
    level: ${LOG_LEVEL:-INFO}
    file: logs/jarvis.log
```

## Environment Variables

Environment variables are loaded with the following conventions:

- Prefix: `JARVIS_` (or custom prefix)
- Nested keys: Use double underscore `__`
- Arrays/Objects: Use JSON format

Examples:
```bash
export JARVIS_SERVER__HOST=example.com
export JARVIS_SERVER__PORT=9000
export JARVIS_DEBUG=true
export JARVIS_FEATURES='["perception", "reasoning"]'
```

## Field Types

Supported validation field types:

- `STRING`: String values with length and regex validation
- `INTEGER`: Integer values with min/max constraints
- `FLOAT`: Floating-point values with min/max constraints
- `BOOLEAN`: Boolean true/false values
- `LIST`: Lists with item type validation
- `DICT`: Nested dictionaries with schema validation
- `ENUM`: Values from a predefined set
- `REGEX`: String matching a regex pattern
- `PATH`: File/directory path validation
- `URL`: URL format validation
- `PORT`: Port number (1-65535)

## Best Practices

1. **Layer Configuration**: Use multiple sources with clear priority
   - Defaults (lowest priority)
   - Configuration files
   - Environment variables
   - Runtime overrides (highest priority)

2. **Use Schemas**: Define schemas for validation and documentation

3. **Environment Variables**: Use for deployment-specific settings
   - Secrets and credentials
   - Host/port configurations
   - Feature flags

4. **Sensitive Data**: Never commit sensitive data
   - Use environment variables
   - Use `.env` files (git-ignored)
   - Mask sensitive values in logs

5. **Configuration as Code**: Version control your configuration files

## Advanced Features

### Custom Validation

```python
def validate_custom(config):
    errors = []
    if config.get("server.port") == 80 and not config.get("server.ssl.enabled"):
        errors.append("Port 80 requires SSL to be enabled")
    return errors

# Add custom validation
errors = config.validate()
errors.extend(validate_custom(config.get_all()))
```

### Configuration Export

```python
# Export configuration (with sensitive values masked)
yaml_config = config.export(format="yaml", mask_sensitive=True)
print(yaml_config)

# Export as JSON
json_config = config.export(format="json", mask_sensitive=False)
```

### Dynamic Reloading

```python
# Reload specific source
config.reload_source("app")

# Watch for file changes (using external library)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigReloader(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.yaml'):
            config.reload_source("app")
```

## Testing

```python
import pytest
from core.config import ConfigManager

def test_config():
    config = ConfigManager()
    config.load_source("test", {
        "test_key": "test_value"
    })
    
    assert config.get("test_key") == "test_value"
```

## Troubleshooting

### Common Issues

1. **Environment variables not loading**
   - Check the prefix (e.g., `JARVIS_`)
   - Use double underscore for nesting: `JARVIS_SERVER__PORT`

2. **Validation errors**
   - Check the schema definition
   - Ensure required fields have values or defaults

3. **Configuration not updating**
   - Check source priorities
   - Verify the configuration key path

4. **Sensitive data in logs**
   - Use `mask_sensitive=True` when exporting
   - Configure sensitive key patterns