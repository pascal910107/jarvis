"""Central configuration management system."""

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from core.monitoring import get_logger, LogContext

from .loader import ConfigLoader, ConfigFormat, save_config
from .schema import ConfigSchema, SchemaValidationError
from .utils import (
    merge_configs, expand_env_vars, get_config_value, 
    set_config_value, mask_sensitive_values
)

logger = get_logger(__name__)


class ConfigNotFoundError(Exception):
    """Raised when a configuration key is not found."""
    pass


@dataclass
class ConfigSource:
    """Configuration source metadata."""
    name: str
    path: Optional[Union[str, Path]] = None
    format: ConfigFormat = ConfigFormat.AUTO
    priority: int = 0  # Higher priority overrides lower
    loaded_at: Optional[datetime] = None
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}


class ConfigManager:
    """Central configuration management system.
    
    Features:
    - Multiple configuration sources with priority
    - Schema validation
    - Runtime updates with change notifications
    - Thread-safe access
    - Environment variable expansion
    """
    
    def __init__(self, schema: Optional[ConfigSchema] = None):
        self.schema = schema
        self.loader = ConfigLoader()
        self._sources: Dict[str, ConfigSource] = {}
        self._config: Dict[str, Any] = {}
        self._change_handlers: List[Callable[[str, Any, Any], None]] = []
        self._lock = threading.RLock()
        
        logger.info("Configuration manager initialized")
    
    def load_source(self, name: str, source: Union[str, Path, Dict[str, Any]],
                   format: ConfigFormat = ConfigFormat.AUTO,
                   priority: int = 0) -> None:
        """Load a configuration source.
        
        Args:
            name: Source identifier
            source: Configuration source (file path or dict)
            format: Configuration format
            priority: Source priority (higher overrides lower)
        """
        with self._lock:
            with LogContext(source_name=name, source_type=format.value):
                logger.info(f"Loading configuration source: {name}")
                
                # Load configuration data
                try:
                    data = self.loader.load(source, format)
                    
                    # Expand environment variables
                    data = expand_env_vars(data)
                    
                    # Create source record
                    config_source = ConfigSource(
                        name=name,
                        path=source if isinstance(source, (str, Path)) else None,
                        format=format,
                        priority=priority,
                        loaded_at=datetime.now(),
                        data=data
                    )
                    
                    self._sources[name] = config_source
                    self._rebuild_config()
                    
                    logger.info(f"Successfully loaded source: {name}",
                               extra={"keys": len(data)})
                    
                except Exception as e:
                    logger.error(f"Failed to load source {name}: {e}")
                    raise
    
    def load_sources(self, sources: List[Dict[str, Any]]) -> None:
        """Load multiple configuration sources.
        
        Args:
            sources: List of source definitions with keys:
                     - name: Source identifier
                     - source: File path or dict
                     - format: Optional format
                     - priority: Optional priority
        """
        for source_def in sources:
            self.load_source(
                name=source_def['name'],
                source=source_def['source'],
                format=source_def.get('format', ConfigFormat.AUTO),
                priority=source_def.get('priority', 0)
            )
    
    def reload_source(self, name: str) -> None:
        """Reload a configuration source."""
        with self._lock:
            if name not in self._sources:
                raise ConfigNotFoundError(f"Source not found: {name}")
            
            source = self._sources[name]
            if source.path:
                logger.info(f"Reloading source: {name}")
                self.load_source(name, source.path, source.format, source.priority)
            else:
                logger.warning(f"Cannot reload source {name}: no file path")
    
    def remove_source(self, name: str) -> None:
        """Remove a configuration source."""
        with self._lock:
            if name in self._sources:
                del self._sources[name]
                self._rebuild_config()
                logger.info(f"Removed configuration source: {name}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        with self._lock:
            value = get_config_value(self._config, key, default)
            
            if value is None and default is None:
                logger.debug(f"Configuration key not found: {key}")
            
            return value
    
    def get_required(self, key: str) -> Any:
        """Get required configuration value.
        
        Args:
            key: Configuration key
            
        Returns:
            Configuration value
            
        Raises:
            ConfigNotFoundError: If key not found
        """
        value = self.get(key)
        if value is None:
            raise ConfigNotFoundError(f"Required configuration not found: {key}")
        return value
    
    def set(self, key: str, value: Any, persist: bool = False,
            source_name: str = "runtime") -> None:
        """Set configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
            persist: Whether to persist to source file
            source_name: Source to update (for persistence)
        """
        with self._lock:
            old_value = get_config_value(self._config, key)
            
            # Update configuration
            set_config_value(self._config, key, value)
            
            # Update source if persisting
            if persist and source_name in self._sources:
                source = self._sources[source_name]
                set_config_value(source.data, key, value)
                
                # Save to file if source has a path
                if source.path:
                    save_config(source.data, source.path, source.format)
                    logger.info(f"Persisted configuration change to {source.path}")
            
            # Notify change handlers
            self._notify_change(key, old_value, value)
            
            logger.info(f"Configuration updated: {key}",
                       extra={"old_value": old_value, "new_value": value})
    
    def update(self, updates: Dict[str, Any], persist: bool = False,
               source_name: str = "runtime") -> None:
        """Update multiple configuration values.
        
        Args:
            updates: Dictionary of updates
            persist: Whether to persist changes
            source_name: Source to update
        """
        for key, value in updates.items():
            self.set(key, value, persist, source_name)
    
    def validate(self) -> List[str]:
        """Validate current configuration against schema.
        
        Returns:
            List of validation errors (empty if valid)
        """
        if not self.schema:
            logger.warning("No schema defined for validation")
            return []
        
        with self._lock:
            errors = self.schema.validate(self._config)
            
            if errors:
                logger.warning(f"Configuration validation found {len(errors)} errors")
                for error in errors:
                    logger.warning(f"Validation error: {error}")
            else:
                logger.info("Configuration validation passed")
            
            return errors
    
    def validate_required(self) -> None:
        """Validate configuration, raising exception on errors.
        
        Raises:
            SchemaValidationError: If validation fails
        """
        errors = self.validate()
        if errors:
            raise SchemaValidationError(errors)
    
    def get_all(self) -> Dict[str, Any]:
        """Get complete configuration."""
        with self._lock:
            return self._config.copy()
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get configuration section.
        
        Args:
            section: Section name (dot notation supported)
            
        Returns:
            Configuration section or empty dict
        """
        value = self.get(section, {})
        return value if isinstance(value, dict) else {}
    
    def get_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get information about loaded sources."""
        with self._lock:
            return {
                name: {
                    "path": str(source.path) if source.path else None,
                    "format": source.format.value,
                    "priority": source.priority,
                    "loaded_at": source.loaded_at.isoformat() if source.loaded_at else None,
                    "keys": len(source.data)
                }
                for name, source in self._sources.items()
            }
    
    def register_change_handler(self, handler: Callable[[str, Any, Any], None]) -> None:
        """Register a configuration change handler.
        
        Args:
            handler: Function called with (key, old_value, new_value)
        """
        with self._lock:
            self._change_handlers.append(handler)
            logger.debug(f"Registered change handler: {handler}")
    
    def unregister_change_handler(self, handler: Callable[[str, Any, Any], None]) -> None:
        """Unregister a configuration change handler."""
        with self._lock:
            if handler in self._change_handlers:
                self._change_handlers.remove(handler)
                logger.debug(f"Unregistered change handler: {handler}")
    
    def export(self, format: ConfigFormat = ConfigFormat.YAML,
               mask_sensitive: bool = True) -> str:
        """Export configuration as string.
        
        Args:
            format: Export format
            mask_sensitive: Whether to mask sensitive values
            
        Returns:
            Configuration string
        """
        import json
        import yaml
        
        with self._lock:
            config = self._config.copy()
            
            if mask_sensitive:
                config = mask_sensitive_values(config)
            
            if format == ConfigFormat.JSON:
                return json.dumps(config, indent=2)
            elif format == ConfigFormat.YAML:
                return yaml.dump(config, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported export format: {format}")
    
    def _rebuild_config(self) -> None:
        """Rebuild configuration from all sources."""
        # Sort sources by priority (lowest first)
        sorted_sources = sorted(
            self._sources.values(),
            key=lambda s: s.priority
        )
        
        # Merge configurations
        configs = [source.data for source in sorted_sources]
        self._config = merge_configs(*configs)
        
        # Apply schema defaults if available
        if self.schema:
            self._config = self.schema.apply_defaults(self._config)
        
        logger.debug(f"Rebuilt configuration from {len(configs)} sources")
    
    def _notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """Notify handlers of configuration change."""
        for handler in self._change_handlers:
            try:
                handler(key, old_value, new_value)
            except Exception as e:
                logger.error(f"Change handler error: {e}")


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def setup_config(sources: List[Dict[str, Any]], 
                schema: Optional[ConfigSchema] = None) -> ConfigManager:
    """Setup global configuration manager.
    
    Args:
        sources: List of configuration sources
        schema: Optional configuration schema
        
    Returns:
        Configured ConfigManager instance
    """
    global _config_manager
    _config_manager = ConfigManager(schema)
    _config_manager.load_sources(sources)
    return _config_manager