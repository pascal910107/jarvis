"""Configuration utility functions."""

import os
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Union

from core.monitoring import get_logger

logger = get_logger(__name__)


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple configuration dictionaries.
    
    Later configurations override earlier ones. Nested dictionaries
    are merged recursively.
    
    Args:
        *configs: Configuration dictionaries to merge
        
    Returns:
        Merged configuration dictionary
    """
    result = {}
    
    for config in configs:
        if not isinstance(config, dict):
            logger.warning(f"Skipping non-dict config: {type(config)}")
            continue
        
        result = _deep_merge(result, config)
    
    return result


def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = deepcopy(base)
    
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = _deep_merge(result[key], value)
        else:
            # Override value
            result[key] = deepcopy(value)
    
    return result


def expand_env_vars(config: Union[Dict[str, Any], List[Any], str]) -> Union[Dict[str, Any], List[Any], str]:
    """Expand environment variables in configuration values.
    
    Supports:
    - ${VAR_NAME} - Replace with environment variable value
    - ${VAR_NAME:-default} - Use default if variable not set
    - ${VAR_NAME:?error message} - Raise error if variable not set
    
    Args:
        config: Configuration to process
        
    Returns:
        Configuration with environment variables expanded
        
    Raises:
        ValueError: If required environment variable is not set
    """
    if isinstance(config, dict):
        return {k: expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(item) for item in config]
    elif isinstance(config, str):
        return _expand_env_string(config)
    else:
        return config


def _expand_env_string(value: str) -> str:
    """Expand environment variables in a string."""
    # Pattern to match ${VAR}, ${VAR:-default}, ${VAR:?error}
    pattern = r'\$\{([^}]+)\}'
    
    def replacer(match):
        expr = match.group(1)
        
        # Handle ${VAR:-default}
        if ':-' in expr:
            var_name, default = expr.split(':-', 1)
            return os.environ.get(var_name.strip(), default)
        
        # Handle ${VAR:?error}
        elif ':?' in expr:
            var_name, error_msg = expr.split(':?', 1)
            var_value = os.environ.get(var_name.strip())
            if var_value is None:
                raise ValueError(f"Environment variable {var_name} not set: {error_msg}")
            return var_value
        
        # Handle ${VAR}
        else:
            var_name = expr.strip()
            return os.environ.get(var_name, match.group(0))
    
    return re.sub(pattern, replacer, value)


def flatten_config(config: Dict[str, Any], separator: str = '.') -> Dict[str, Any]:
    """Flatten nested configuration dictionary.
    
    Args:
        config: Nested configuration dictionary
        separator: Key separator for flattened keys
        
    Returns:
        Flattened configuration dictionary
        
    Example:
        {'a': {'b': {'c': 1}}} -> {'a.b.c': 1}
    """
    result = {}
    
    def _flatten(obj: Any, prefix: str = ''):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}{separator}{key}" if prefix else key
                _flatten(value, new_key)
        else:
            result[prefix] = obj
    
    _flatten(config)
    return result


def unflatten_config(config: Dict[str, Any], separator: str = '.') -> Dict[str, Any]:
    """Unflatten configuration dictionary.
    
    Args:
        config: Flattened configuration dictionary
        separator: Key separator used in flattened keys
        
    Returns:
        Nested configuration dictionary
        
    Example:
        {'a.b.c': 1} -> {'a': {'b': {'c': 1}}}
    """
    result = {}
    
    for key, value in config.items():
        parts = key.split(separator)
        current = result
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    return result


def get_config_value(config: Dict[str, Any], key: str, 
                     default: Any = None, separator: str = '.') -> Any:
    """Get value from nested configuration using dot notation.
    
    Args:
        config: Configuration dictionary
        key: Dot-separated key path (e.g., 'server.host')
        default: Default value if key not found
        separator: Key separator
        
    Returns:
        Configuration value or default
    """
    parts = key.split(separator)
    current = config
    
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    
    return current


def set_config_value(config: Dict[str, Any], key: str, value: Any,
                     separator: str = '.') -> Dict[str, Any]:
    """Set value in nested configuration using dot notation.
    
    Args:
        config: Configuration dictionary (modified in place)
        key: Dot-separated key path (e.g., 'server.host')
        value: Value to set
        separator: Key separator
        
    Returns:
        Modified configuration dictionary
    """
    parts = key.split(separator)
    current = config
    
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    
    current[parts[-1]] = value
    return config


def mask_sensitive_values(config: Dict[str, Any], 
                         sensitive_keys: Optional[List[str]] = None,
                         mask: str = "***") -> Dict[str, Any]:
    """Mask sensitive values in configuration for logging.
    
    Args:
        config: Configuration dictionary
        sensitive_keys: List of key patterns to mask (regex supported)
        mask: Mask string to use
        
    Returns:
        Configuration with sensitive values masked
    """
    if sensitive_keys is None:
        # Default sensitive key patterns
        sensitive_keys = [
            r'.*password.*',
            r'.*secret.*',
            r'.*key.*',
            r'.*token.*',
            r'.*credential.*',
        ]
    
    # Compile patterns
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in sensitive_keys]
    
    def _mask_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        
        for key, value in obj.items():
            # Check if key matches any sensitive pattern
            is_sensitive = any(pattern.match(key) for pattern in patterns)
            
            if is_sensitive and isinstance(value, (str, int, float)):
                result[key] = mask
            elif isinstance(value, dict):
                result[key] = _mask_dict(value)
            elif isinstance(value, list):
                result[key] = [_mask_dict(item) if isinstance(item, dict) else item 
                              for item in value]
            else:
                result[key] = value
        
        return result
    
    return _mask_dict(config)


def validate_config_structure(config: Dict[str, Any], 
                            required_keys: List[str],
                            separator: str = '.') -> List[str]:
    """Validate that required keys exist in configuration.
    
    Args:
        config: Configuration dictionary
        required_keys: List of required key paths
        separator: Key separator
        
    Returns:
        List of missing keys
    """
    missing = []
    
    for key in required_keys:
        if get_config_value(config, key, separator=separator) is None:
            missing.append(key)
    
    return missing