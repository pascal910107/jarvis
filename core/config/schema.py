"""Configuration schema validation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints
import re

from core.monitoring import get_logger

logger = get_logger(__name__)


class FieldType(Enum):
    """Supported field types for configuration validation."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    ENUM = "enum"
    REGEX = "regex"
    PATH = "path"
    URL = "url"
    PORT = "port"
    
    @classmethod
    def from_python_type(cls, python_type: Type) -> 'FieldType':
        """Convert Python type to FieldType."""
        type_map = {
            str: cls.STRING,
            int: cls.INTEGER,
            float: cls.FLOAT,
            bool: cls.BOOLEAN,
            list: cls.LIST,
            dict: cls.DICT,
        }
        
        # Handle Optional types
        if hasattr(python_type, '__origin__'):
            if python_type.__origin__ is Union:
                # Get the non-None type from Optional
                args = [arg for arg in python_type.__args__ if arg is not type(None)]
                if args:
                    python_type = args[0]
        
        return type_map.get(python_type, cls.STRING)


@dataclass
class FieldSchema:
    """Schema definition for a configuration field."""
    name: str
    type: FieldType
    required: bool = True
    default: Any = None
    description: str = ""
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_values: Optional[List[Any]] = None
    regex_pattern: Optional[str] = None
    nested_schema: Optional['ConfigSchema'] = None
    list_item_type: Optional[FieldType] = None
    list_item_schema: Optional['ConfigSchema'] = None
    
    def validate(self, value: Any, path: str = "") -> List[str]:
        """Validate a value against this field schema.
        
        Args:
            value: Value to validate
            path: Field path for error messages
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        field_path = f"{path}.{self.name}" if path else self.name
        
        # Check required
        if value is None:
            if self.required and self.default is None:
                errors.append(f"{field_path}: Required field is missing")
            return errors
        
        # Type validation
        type_validators = {
            FieldType.STRING: self._validate_string,
            FieldType.INTEGER: self._validate_integer,
            FieldType.FLOAT: self._validate_float,
            FieldType.BOOLEAN: self._validate_boolean,
            FieldType.LIST: self._validate_list,
            FieldType.DICT: self._validate_dict,
            FieldType.ENUM: self._validate_enum,
            FieldType.REGEX: self._validate_regex,
            FieldType.PATH: self._validate_path,
            FieldType.URL: self._validate_url,
            FieldType.PORT: self._validate_port,
        }
        
        validator = type_validators.get(self.type)
        if validator:
            errors.extend(validator(value, field_path))
        
        return errors
    
    def _validate_string(self, value: Any, path: str) -> List[str]:
        """Validate string value."""
        errors = []
        
        if not isinstance(value, str):
            errors.append(f"{path}: Expected string, got {type(value).__name__}")
            return errors
        
        if self.min_length is not None and len(value) < self.min_length:
            errors.append(f"{path}: String length {len(value)} is less than minimum {self.min_length}")
        
        if self.max_length is not None and len(value) > self.max_length:
            errors.append(f"{path}: String length {len(value)} exceeds maximum {self.max_length}")
        
        if self.regex_pattern:
            if not re.match(self.regex_pattern, value):
                errors.append(f"{path}: String does not match pattern: {self.regex_pattern}")
        
        return errors
    
    def _validate_integer(self, value: Any, path: str) -> List[str]:
        """Validate integer value."""
        errors = []
        
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: Expected integer, got {type(value).__name__}")
            return errors
        
        if self.min_value is not None and value < self.min_value:
            errors.append(f"{path}: Value {value} is less than minimum {self.min_value}")
        
        if self.max_value is not None and value > self.max_value:
            errors.append(f"{path}: Value {value} exceeds maximum {self.max_value}")
        
        return errors
    
    def _validate_float(self, value: Any, path: str) -> List[str]:
        """Validate float value."""
        errors = []
        
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path}: Expected float, got {type(value).__name__}")
            return errors
        
        value = float(value)
        
        if self.min_value is not None and value < self.min_value:
            errors.append(f"{path}: Value {value} is less than minimum {self.min_value}")
        
        if self.max_value is not None and value > self.max_value:
            errors.append(f"{path}: Value {value} exceeds maximum {self.max_value}")
        
        return errors
    
    def _validate_boolean(self, value: Any, path: str) -> List[str]:
        """Validate boolean value."""
        if not isinstance(value, bool):
            return [f"{path}: Expected boolean, got {type(value).__name__}"]
        return []
    
    def _validate_list(self, value: Any, path: str) -> List[str]:
        """Validate list value."""
        errors = []
        
        if not isinstance(value, list):
            errors.append(f"{path}: Expected list, got {type(value).__name__}")
            return errors
        
        if self.min_length is not None and len(value) < self.min_length:
            errors.append(f"{path}: List length {len(value)} is less than minimum {self.min_length}")
        
        if self.max_length is not None and len(value) > self.max_length:
            errors.append(f"{path}: List length {len(value)} exceeds maximum {self.max_length}")
        
        # Validate list items
        if self.list_item_type or self.list_item_schema:
            for i, item in enumerate(value):
                item_path = f"{path}[{i}]"
                
                if self.list_item_schema:
                    # Validate against nested schema
                    errors.extend(self.list_item_schema.validate(item, item_path))
                elif self.list_item_type:
                    # Validate against simple type
                    item_field = FieldSchema(
                        name=str(i),
                        type=self.list_item_type,
                        allowed_values=self.allowed_values
                    )
                    errors.extend(item_field.validate(item, path))
        
        return errors
    
    def _validate_dict(self, value: Any, path: str) -> List[str]:
        """Validate dictionary value."""
        errors = []
        
        if not isinstance(value, dict):
            errors.append(f"{path}: Expected dict, got {type(value).__name__}")
            return errors
        
        # Validate against nested schema if provided
        if self.nested_schema:
            errors.extend(self.nested_schema.validate(value, path))
        
        return errors
    
    def _validate_enum(self, value: Any, path: str) -> List[str]:
        """Validate enum value."""
        if self.allowed_values and value not in self.allowed_values:
            return [f"{path}: Value '{value}' not in allowed values: {self.allowed_values}"]
        return []
    
    def _validate_regex(self, value: Any, path: str) -> List[str]:
        """Validate value against regex pattern."""
        errors = self._validate_string(value, path)
        if errors:
            return errors
        
        if self.regex_pattern and not re.match(self.regex_pattern, value):
            return [f"{path}: Value does not match pattern: {self.regex_pattern}"]
        
        return []
    
    def _validate_path(self, value: Any, path: str) -> List[str]:
        """Validate file/directory path."""
        errors = self._validate_string(value, path)
        if errors:
            return errors
        
        # Additional path validation could be added here
        # (e.g., check if path exists, is readable, etc.)
        
        return []
    
    def _validate_url(self, value: Any, path: str) -> List[str]:
        """Validate URL."""
        errors = self._validate_string(value, path)
        if errors:
            return errors
        
        # Simple URL validation
        url_pattern = r'^https?://[\w\-._~:/?#[\]@!$&\'()*+,;=]+$'
        if not re.match(url_pattern, value):
            return [f"{path}: Invalid URL format"]
        
        return []
    
    def _validate_port(self, value: Any, path: str) -> List[str]:
        """Validate port number."""
        errors = self._validate_integer(value, path)
        if errors:
            return errors
        
        if not 1 <= value <= 65535:
            return [f"{path}: Port number must be between 1 and 65535"]
        
        return []


class ConfigSchema:
    """Configuration schema for validation."""
    
    def __init__(self, fields: Optional[List[FieldSchema]] = None):
        self.fields: Dict[str, FieldSchema] = {}
        if fields:
            for field in fields:
                self.add_field(field)
    
    def add_field(self, field: FieldSchema) -> None:
        """Add a field to the schema."""
        self.fields[field.name] = field
    
    def validate(self, config: Dict[str, Any], path: str = "") -> List[str]:
        """Validate configuration against schema.
        
        Args:
            config: Configuration dictionary to validate
            path: Base path for error messages
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check all defined fields
        for field_name, field_schema in self.fields.items():
            value = config.get(field_name)
            errors.extend(field_schema.validate(value, path))
        
        # Check for unknown fields
        known_fields = set(self.fields.keys())
        config_fields = set(config.keys())
        unknown_fields = config_fields - known_fields
        
        if unknown_fields:
            for field in unknown_fields:
                field_path = f"{path}.{field}" if path else field
                logger.warning(f"{field_path}: Unknown configuration field")
        
        return errors
    
    def apply_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default values to configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Configuration with defaults applied
        """
        result = config.copy()
        
        for field_name, field_schema in self.fields.items():
            if field_name not in result and field_schema.default is not None:
                result[field_name] = field_schema.default
            elif field_name in result and field_schema.nested_schema:
                # Recursively apply defaults to nested configs
                result[field_name] = field_schema.nested_schema.apply_defaults(
                    result.get(field_name, {})
                )
        
        return result
    
    @classmethod
    def from_dataclass(cls, dataclass_type: Type) -> 'ConfigSchema':
        """Create schema from a dataclass definition.
        
        Args:
            dataclass_type: Dataclass type to create schema from
            
        Returns:
            ConfigSchema instance
        """
        schema = cls()
        
        # Get type hints
        hints = get_type_hints(dataclass_type)
        
        # Get field defaults
        if hasattr(dataclass_type, '__dataclass_fields__'):
            fields = dataclass_type.__dataclass_fields__
        else:
            raise ValueError(f"{dataclass_type} is not a dataclass")
        
        for field_name, field_info in fields.items():
            # Determine if field is required
            required = field_info.default is field.default and \
                      field_info.default_factory is field.default_factory
            
            # Get field type
            python_type = hints.get(field_name, str)
            field_type = FieldType.from_python_type(python_type)
            
            # Create field schema
            field_schema = FieldSchema(
                name=field_name,
                type=field_type,
                required=required,
                default=None if required else field_info.default,
                description=field_info.metadata.get('description', '')
            )
            
            schema.add_field(field_schema)
        
        return schema


class SchemaValidationError(Exception):
    """Raised when configuration validation fails."""
    
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Configuration validation failed with {len(errors)} errors")
    
    def __str__(self):
        return f"Configuration validation errors:\n" + "\n".join(f"  - {e}" for e in self.errors)