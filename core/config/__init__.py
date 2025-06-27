"""Configuration management system for Jarvis AGI.

This module provides:
- Multi-format configuration loading (YAML, JSON, environment variables)
- Configuration validation with schemas
- Hierarchical configuration with inheritance
- Runtime configuration updates
- Type-safe configuration access
"""

from .loader import ConfigLoader, ConfigFormat
from .schema import ConfigSchema, SchemaValidationError
from .manager import ConfigManager, ConfigNotFoundError
from .utils import merge_configs, expand_env_vars

__all__ = [
    "ConfigLoader",
    "ConfigFormat",
    "ConfigSchema",
    "SchemaValidationError",
    "ConfigManager",
    "ConfigNotFoundError",
    "merge_configs",
    "expand_env_vars",
]