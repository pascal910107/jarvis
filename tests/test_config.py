"""Tests for the configuration management system."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import pytest
import yaml

from core.config import (
    ConfigLoader, ConfigFormat, ConfigSchema, FieldSchema, FieldType,
    SchemaValidationError, ConfigManager, ConfigNotFoundError,
    merge_configs, expand_env_vars, get_config_value, set_config_value,
    flatten_config, unflatten_config, mask_sensitive_values
)


class TestConfigLoader:
    """Test configuration loader functionality."""
    
    def test_load_yaml(self, tmp_path):
        """Test loading YAML configuration."""
        config_data = {
            "server": {
                "host": "localhost",
                "port": 8080
            },
            "logging": {
                "level": "INFO"
            }
        }
        
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        loader = ConfigLoader()
        loaded = loader.load(config_file)
        
        assert loaded == config_data
        assert loaded["server"]["port"] == 8080
    
    def test_load_json(self, tmp_path):
        """Test loading JSON configuration."""
        config_data = {
            "database": {
                "host": "db.example.com",
                "port": 5432,
                "name": "jarvis"
            }
        }
        
        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        loader = ConfigLoader()
        loaded = loader.load(config_file, ConfigFormat.JSON)
        
        assert loaded == config_data
    
    def test_load_env(self):
        """Test loading from environment variables."""
        # Set test environment variables
        os.environ["TEST_SERVER__HOST"] = "example.com"
        os.environ["TEST_SERVER__PORT"] = "9000"
        os.environ["TEST_DEBUG"] = "true"
        os.environ["TEST_ITEMS"] = '["a", "b", "c"]'
        
        loader = ConfigLoader()
        loaded = loader.load("TEST", ConfigFormat.ENV)
        
        assert loaded["server"]["host"] == "example.com"
        assert loaded["server"]["port"] == 9000  # Parsed as int
        assert loaded["debug"] is True  # Parsed as bool
        assert loaded["items"] == ["a", "b", "c"]  # Parsed as list
        
        # Cleanup
        for key in ["TEST_SERVER__HOST", "TEST_SERVER__PORT", "TEST_DEBUG", "TEST_ITEMS"]:
            del os.environ[key]
    
    def test_load_dict(self):
        """Test loading from dictionary."""
        config_data = {"key": "value"}
        
        loader = ConfigLoader()
        loaded = loader.load(config_data)
        
        assert loaded == config_data
        assert loaded is not config_data  # Should be a copy
    
    def test_auto_format_detection(self, tmp_path):
        """Test automatic format detection."""
        loader = ConfigLoader()
        
        # YAML file
        yaml_file = tmp_path / "config.yml"
        yaml_file.write_text("key: value")
        assert loader._detect_format(str(yaml_file)) == ConfigFormat.YAML
        
        # JSON file
        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}')
        assert loader._detect_format(str(json_file)) == ConfigFormat.JSON
        
        # Non-existent path (assume env)
        assert loader._detect_format("SOME_PREFIX") == ConfigFormat.ENV
    
    def test_load_multiple(self, tmp_path):
        """Test loading multiple configurations."""
        # Create test files
        yaml_file = tmp_path / "base.yaml"
        yaml_file.write_text("base: true\nport: 8080")
        
        json_file = tmp_path / "override.json"
        json_file.write_text('{"port": 9000, "extra": "value"}')
        
        loader = ConfigLoader()
        configs = loader.load_multiple([str(yaml_file), str(json_file)])
        
        assert len(configs) == 2
        assert configs[0]["base"] is True
        assert configs[0]["port"] == 8080
        assert configs[1]["port"] == 9000
        assert configs[1]["extra"] == "value"


class TestConfigSchema:
    """Test configuration schema validation."""
    
    def test_field_validation_string(self):
        """Test string field validation."""
        field = FieldSchema(
            name="host",
            type=FieldType.STRING,
            min_length=1,
            max_length=255,
            regex_pattern=r"^[a-zA-Z0-9.-]+$"
        )
        
        # Valid values
        assert field.validate("localhost") == []
        assert field.validate("example.com") == []
        
        # Invalid values
        errors = field.validate("")
        assert any("less than minimum" in e for e in errors)
        
        errors = field.validate("invalid_host!")
        assert any("does not match pattern" in e for e in errors)
    
    def test_field_validation_integer(self):
        """Test integer field validation."""
        field = FieldSchema(
            name="port",
            type=FieldType.INTEGER,
            min_value=1,
            max_value=65535
        )
        
        # Valid values
        assert field.validate(8080) == []
        assert field.validate(1) == []
        assert field.validate(65535) == []
        
        # Invalid values
        errors = field.validate(0)
        assert any("less than minimum" in e for e in errors)
        
        errors = field.validate(70000)
        assert any("exceeds maximum" in e for e in errors)
        
        errors = field.validate("8080")
        assert any("Expected integer" in e for e in errors)
    
    def test_field_validation_list(self):
        """Test list field validation."""
        field = FieldSchema(
            name="tags",
            type=FieldType.LIST,
            min_length=1,
            max_length=10,
            list_item_type=FieldType.STRING
        )
        
        # Valid values
        assert field.validate(["tag1", "tag2"]) == []
        
        # Invalid values
        errors = field.validate([])
        assert any("less than minimum" in e for e in errors)
        
        errors = field.validate("not a list")
        assert any("Expected list" in e for e in errors)
    
    def test_field_validation_enum(self):
        """Test enum field validation."""
        field = FieldSchema(
            name="level",
            type=FieldType.ENUM,
            allowed_values=["DEBUG", "INFO", "WARNING", "ERROR"]
        )
        
        # Valid values
        assert field.validate("INFO") == []
        
        # Invalid values
        errors = field.validate("TRACE")
        assert any("not in allowed values" in e for e in errors)
    
    def test_field_validation_port(self):
        """Test port field validation."""
        field = FieldSchema(
            name="port",
            type=FieldType.PORT
        )
        
        # Valid values
        assert field.validate(80) == []
        assert field.validate(8080) == []
        
        # Invalid values
        errors = field.validate(0)
        assert any("between 1 and 65535" in e for e in errors)
        
        errors = field.validate(70000)
        assert any("between 1 and 65535" in e for e in errors)
    
    def test_schema_validation(self):
        """Test complete schema validation."""
        schema = ConfigSchema([
            FieldSchema("host", FieldType.STRING, required=True),
            FieldSchema("port", FieldType.PORT, required=True),
            FieldSchema("debug", FieldType.BOOLEAN, required=False, default=False),
            FieldSchema("workers", FieldType.INTEGER, min_value=1, max_value=100)
        ])
        
        # Valid configuration
        config = {
            "host": "localhost",
            "port": 8080,
            "workers": 4
        }
        assert schema.validate(config) == []
        
        # Missing required field
        config = {"port": 8080}
        errors = schema.validate(config)
        assert any("Required field is missing" in e and "host" in e for e in errors)
        
        # Invalid field value
        config = {"host": "localhost", "port": 0}
        errors = schema.validate(config)
        assert any("between 1 and 65535" in e for e in errors)
    
    def test_schema_defaults(self):
        """Test applying default values."""
        schema = ConfigSchema([
            FieldSchema("host", FieldType.STRING, default="localhost"),
            FieldSchema("port", FieldType.INTEGER, default=8080),
            FieldSchema("debug", FieldType.BOOLEAN, default=False)
        ])
        
        config = {"port": 9000}
        result = schema.apply_defaults(config)
        
        assert result["host"] == "localhost"
        assert result["port"] == 9000  # Original value preserved
        assert result["debug"] is False
    
    def test_nested_schema_validation(self):
        """Test nested schema validation."""
        server_schema = ConfigSchema([
            FieldSchema("host", FieldType.STRING),
            FieldSchema("port", FieldType.PORT)
        ])
        
        main_schema = ConfigSchema([
            FieldSchema("server", FieldType.DICT, nested_schema=server_schema)
        ])
        
        # Valid nested config
        config = {
            "server": {
                "host": "localhost",
                "port": 8080
            }
        }
        assert main_schema.validate(config) == []
        
        # Invalid nested config
        config = {
            "server": {
                "host": "localhost",
                "port": 70000
            }
        }
        errors = main_schema.validate(config)
        assert any("between 1 and 65535" in e for e in errors)
    
    def test_schema_from_dataclass(self):
        """Test creating schema from dataclass."""
        @dataclass
        class ServerConfig:
            host: str
            port: int = 8080
            debug: bool = False
            tags: List[str] = field(default_factory=list)
        
        schema = ConfigSchema.from_dataclass(ServerConfig)
        
        # Check fields were created
        assert "host" in schema.fields
        assert "port" in schema.fields
        assert "debug" in schema.fields
        assert "tags" in schema.fields
        
        # Check required vs optional
        assert schema.fields["host"].required is True
        assert schema.fields["port"].required is False
        assert schema.fields["port"].default == 8080


class TestConfigUtils:
    """Test configuration utility functions."""
    
    def test_merge_configs(self):
        """Test configuration merging."""
        base = {
            "server": {"host": "localhost", "port": 8080},
            "logging": {"level": "INFO"}
        }
        
        override1 = {
            "server": {"port": 9000},
            "database": {"host": "db.local"}
        }
        
        override2 = {
            "server": {"host": "example.com"},
            "logging": {"level": "DEBUG", "file": "app.log"}
        }
        
        result = merge_configs(base, override1, override2)
        
        assert result["server"]["host"] == "example.com"  # From override2
        assert result["server"]["port"] == 9000  # From override1
        assert result["logging"]["level"] == "DEBUG"  # From override2
        assert result["logging"]["file"] == "app.log"  # New key
        assert result["database"]["host"] == "db.local"  # From override1
    
    def test_expand_env_vars(self):
        """Test environment variable expansion."""
        os.environ["TEST_HOST"] = "example.com"
        os.environ["TEST_PORT"] = "9000"
        
        config = {
            "server": {
                "host": "${TEST_HOST}",
                "port": "${TEST_PORT}",
                "url": "http://${TEST_HOST}:${TEST_PORT}"
            },
            "backup": "${TEST_BACKUP:-/tmp/backup}",
            "required": "${TEST_REQUIRED:?This variable is required}"
        }
        
        # Test expansion
        result = expand_env_vars(config)
        assert result["server"]["host"] == "example.com"
        assert result["server"]["port"] == "9000"
        assert result["server"]["url"] == "http://example.com:9000"
        assert result["backup"] == "/tmp/backup"  # Default used
        
        # Test required variable error
        with pytest.raises(ValueError, match="This variable is required"):
            expand_env_vars(config)
        
        # Cleanup
        del os.environ["TEST_HOST"]
        del os.environ["TEST_PORT"]
    
    def test_flatten_unflatten_config(self):
        """Test configuration flattening and unflattening."""
        config = {
            "server": {
                "host": "localhost",
                "port": 8080,
                "ssl": {
                    "enabled": True,
                    "cert": "/path/to/cert"
                }
            },
            "debug": False
        }
        
        # Flatten
        flat = flatten_config(config)
        assert flat["server.host"] == "localhost"
        assert flat["server.port"] == 8080
        assert flat["server.ssl.enabled"] is True
        assert flat["server.ssl.cert"] == "/path/to/cert"
        assert flat["debug"] is False
        
        # Unflatten
        unflat = unflatten_config(flat)
        assert unflat == config
    
    def test_get_set_config_value(self):
        """Test getting and setting config values with dot notation."""
        config = {
            "server": {
                "host": "localhost",
                "port": 8080
            }
        }
        
        # Get values
        assert get_config_value(config, "server.host") == "localhost"
        assert get_config_value(config, "server.port") == 8080
        assert get_config_value(config, "server.missing", "default") == "default"
        
        # Set values
        set_config_value(config, "server.port", 9000)
        assert config["server"]["port"] == 9000
        
        set_config_value(config, "new.nested.key", "value")
        assert config["new"]["nested"]["key"] == "value"
    
    def test_mask_sensitive_values(self):
        """Test masking sensitive configuration values."""
        config = {
            "database": {
                "host": "localhost",
                "password": "secret123",
                "api_key": "abc-def-ghi"
            },
            "server": {
                "port": 8080,
                "secret_token": "token123"
            },
            "public_key": "not-sensitive"
        }
        
        masked = mask_sensitive_values(config)
        
        assert masked["database"]["host"] == "localhost"
        assert masked["database"]["password"] == "***"
        assert masked["database"]["api_key"] == "***"
        assert masked["server"]["port"] == 8080
        assert masked["server"]["secret_token"] == "***"
        assert masked["public_key"] == "***"  # Contains 'key'


class TestConfigManager:
    """Test configuration manager functionality."""
    
    def test_load_single_source(self, tmp_path):
        """Test loading a single configuration source."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
server:
  host: localhost
  port: 8080
""")
        
        manager = ConfigManager()
        manager.load_source("main", str(config_file))
        
        assert manager.get("server.host") == "localhost"
        assert manager.get("server.port") == 8080
    
    def test_load_multiple_sources_priority(self, tmp_path):
        """Test loading multiple sources with priority."""
        # Base configuration
        base_file = tmp_path / "base.yaml"
        base_file.write_text("""
server:
  host: localhost
  port: 8080
logging:
  level: INFO
""")
        
        # Override configuration
        override_file = tmp_path / "override.yaml"
        override_file.write_text("""
server:
  port: 9000
logging:
  level: DEBUG
""")
        
        manager = ConfigManager()
        manager.load_source("base", str(base_file), priority=1)
        manager.load_source("override", str(override_file), priority=2)
        
        # Higher priority should override
        assert manager.get("server.host") == "localhost"  # From base
        assert manager.get("server.port") == 9000  # From override
        assert manager.get("logging.level") == "DEBUG"  # From override
    
    def test_runtime_updates(self):
        """Test runtime configuration updates."""
        manager = ConfigManager()
        manager.load_source("default", {"server": {"host": "localhost"}})
        
        # Update value
        manager.set("server.port", 8080)
        assert manager.get("server.port") == 8080
        
        # Update multiple values
        manager.update({
            "server.host": "example.com",
            "debug": True
        })
        assert manager.get("server.host") == "example.com"
        assert manager.get("debug") is True
    
    def test_change_notifications(self):
        """Test configuration change notifications."""
        manager = ConfigManager()
        manager.load_source("default", {})
        
        changes = []
        
        def handler(key, old_value, new_value):
            changes.append((key, old_value, new_value))
        
        manager.register_change_handler(handler)
        
        # Make changes
        manager.set("test.key", "value1")
        manager.set("test.key", "value2")
        
        assert len(changes) == 2
        assert changes[0] == ("test.key", None, "value1")
        assert changes[1] == ("test.key", "value1", "value2")
        
        # Unregister handler
        manager.unregister_change_handler(handler)
        manager.set("test.key", "value3")
        assert len(changes) == 2  # No new changes
    
    def test_schema_validation(self):
        """Test configuration validation with schema."""
        schema = ConfigSchema([
            FieldSchema("host", FieldType.STRING, required=True),
            FieldSchema("port", FieldType.PORT, required=True)
        ])
        
        manager = ConfigManager(schema)
        
        # Valid configuration
        manager.load_source("valid", {"host": "localhost", "port": 8080})
        errors = manager.validate()
        assert errors == []
        
        # Invalid configuration
        manager.load_source("invalid", {"host": "localhost"})
        errors = manager.validate()
        assert len(errors) > 0
        
        with pytest.raises(SchemaValidationError):
            manager.validate_required()
    
    def test_get_required(self):
        """Test getting required configuration values."""
        manager = ConfigManager()
        manager.load_source("default", {"existing": "value"})
        
        # Existing value
        assert manager.get_required("existing") == "value"
        
        # Non-existing value
        with pytest.raises(ConfigNotFoundError):
            manager.get_required("missing")
    
    def test_persistence(self, tmp_path):
        """Test configuration persistence."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("original: value")
        
        manager = ConfigManager()
        manager.load_source("main", str(config_file))
        
        # Update with persistence
        manager.set("new_key", "new_value", persist=True, source_name="main")
        
        # Reload and check
        manager.reload_source("main")
        assert manager.get("new_key") == "new_value"
    
    def test_export(self):
        """Test configuration export."""
        manager = ConfigManager()
        manager.load_source("default", {
            "server": {"host": "localhost", "port": 8080},
            "database": {"password": "secret"}
        })
        
        # Export as YAML
        yaml_export = manager.export(ConfigFormat.YAML, mask_sensitive=True)
        assert "localhost" in yaml_export
        assert "secret" not in yaml_export
        assert "***" in yaml_export
        
        # Export as JSON
        json_export = manager.export(ConfigFormat.JSON, mask_sensitive=False)
        data = json.loads(json_export)
        assert data["database"]["password"] == "secret"
    
    def test_thread_safety(self):
        """Test thread-safe configuration access."""
        import threading
        
        manager = ConfigManager()
        manager.load_source("default", {"counter": 0})
        
        def increment():
            for _ in range(100):
                current = manager.get("counter", 0)
                manager.set("counter", current + 1)
        
        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # With proper locking, this should work correctly
        # (though not guaranteed to be exactly 1000 due to race conditions
        # between get and set - this is just testing no crashes occur)
        assert manager.get("counter") > 0