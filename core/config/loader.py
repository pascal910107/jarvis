"""Configuration loader supporting multiple formats."""

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml

from core.monitoring import get_logger

logger = get_logger(__name__)


class ConfigFormat(Enum):
    """Supported configuration file formats."""
    YAML = "yaml"
    JSON = "json"
    ENV = "env"
    AUTO = "auto"


class ConfigLoader:
    """Loads configuration from various sources."""
    
    def __init__(self):
        self._loaders = {
            ConfigFormat.YAML: self._load_yaml,
            ConfigFormat.JSON: self._load_json,
            ConfigFormat.ENV: self._load_env,
        }
    
    def load(self, source: Union[str, Path, Dict[str, Any]], 
             format: ConfigFormat = ConfigFormat.AUTO) -> Dict[str, Any]:
        """Load configuration from a source.
        
        Args:
            source: File path, environment prefix, or dict
            format: Configuration format (auto-detected if AUTO)
            
        Returns:
            Configuration dictionary
            
        Raises:
            ValueError: If format cannot be determined or loading fails
        """
        # If source is already a dict, return it
        if isinstance(source, dict):
            logger.debug("Loading configuration from dictionary")
            return source
        
        # Convert to string for processing
        source_str = str(source)
        
        # Auto-detect format if needed
        if format == ConfigFormat.AUTO:
            format = self._detect_format(source_str)
            logger.debug(f"Auto-detected format: {format.value}")
        
        # Load configuration
        loader = self._loaders.get(format)
        if not loader:
            raise ValueError(f"Unsupported format: {format}")
        
        try:
            config = loader(source_str)
            logger.info(f"Loaded configuration from {source_str} ({format.value})")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def load_multiple(self, sources: List[Union[str, Path, Dict[str, Any]]],
                     formats: Optional[List[ConfigFormat]] = None) -> List[Dict[str, Any]]:
        """Load multiple configuration sources.
        
        Args:
            sources: List of configuration sources
            formats: List of formats (auto-detected if None)
            
        Returns:
            List of configuration dictionaries
        """
        if formats is None:
            formats = [ConfigFormat.AUTO] * len(sources)
        elif len(formats) != len(sources):
            raise ValueError("Number of formats must match number of sources")
        
        configs = []
        for source, format in zip(sources, formats):
            try:
                config = self.load(source, format)
                configs.append(config)
            except Exception as e:
                logger.warning(f"Failed to load {source}: {e}")
                configs.append({})
        
        return configs
    
    def _detect_format(self, source: str) -> ConfigFormat:
        """Auto-detect configuration format from source."""
        # Check if it's a file path
        path = Path(source)
        if path.exists() and path.is_file():
            suffix = path.suffix.lower()
            if suffix in ['.yaml', '.yml']:
                return ConfigFormat.YAML
            elif suffix == '.json':
                return ConfigFormat.JSON
            else:
                # Try to detect by content
                try:
                    with open(path, 'r') as f:
                        content = f.read()
                    # Try JSON first
                    try:
                        json.loads(content)
                        return ConfigFormat.JSON
                    except json.JSONDecodeError:
                        # Try YAML
                        yaml.safe_load(content)
                        return ConfigFormat.YAML
                except Exception:
                    raise ValueError(f"Cannot detect format for file: {source}")
        else:
            # Assume it's an environment variable prefix
            return ConfigFormat.ENV
    
    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML configuration file."""
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    
    def _load_json(self, path: str) -> Dict[str, Any]:
        """Load JSON configuration file."""
        with open(path, 'r') as f:
            return json.load(f)
    
    def _load_env(self, prefix: str) -> Dict[str, Any]:
        """Load configuration from environment variables.
        
        Args:
            prefix: Environment variable prefix (e.g., "JARVIS_")
            
        Returns:
            Configuration dictionary with nested keys
        """
        config = {}
        prefix = prefix.upper()
        if not prefix.endswith('_'):
            prefix += '_'
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Remove prefix and convert to lowercase
                config_key = key[len(prefix):].lower()
                
                # Convert underscores to dots for nested keys
                # e.g., JARVIS_MODULE_SETTING -> module.setting
                nested_keys = config_key.split('__')
                
                # Parse value
                parsed_value = self._parse_env_value(value)
                
                # Build nested dictionary
                current = config
                for i, k in enumerate(nested_keys[:-1]):
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                
                current[nested_keys[-1]] = parsed_value
        
        return config
    
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Try to parse as JSON first (handles arrays, objects, booleans, numbers)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Return as string
            return value


def save_config(config: Dict[str, Any], path: Union[str, Path],
                format: Optional[ConfigFormat] = None) -> None:
    """Save configuration to file.
    
    Args:
        config: Configuration dictionary
        path: Output file path
        format: Output format (auto-detected from extension if None)
    """
    path = Path(path)
    
    # Auto-detect format from extension
    if format is None:
        suffix = path.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            format = ConfigFormat.YAML
        elif suffix == '.json':
            format = ConfigFormat.JSON
        else:
            raise ValueError(f"Cannot detect format from extension: {suffix}")
    
    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save configuration
    if format == ConfigFormat.YAML:
        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    elif format == ConfigFormat.JSON:
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
    else:
        raise ValueError(f"Cannot save to format: {format}")
    
    logger.info(f"Saved configuration to {path} ({format.value})")