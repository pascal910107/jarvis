"""Centralized logging system with structured logs for AGI system observability."""

import json
import logging
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional, Union, Callable
import threading
from pathlib import Path

# Thread-local storage for context
_context = threading.local()


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""
    
    def __init__(self, include_context: bool = True):
        super().__init__()
        self.include_context = include_context
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields from record
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "exc_info",
                          "exc_text", "stack_info", "thread", "threadName", "processName",
                          "process", "getMessage", "pathname", "relativeCreated", "msecs"]:
                log_data[key] = value
        
        # Add context if available
        if self.include_context and hasattr(_context, 'data'):
            log_data["context"] = _context.data
        
        return json.dumps(log_data)


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that adds structured context to logs."""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process the logging call to add context."""
        extra = kwargs.get('extra', {})
        
        # Add adapter's extra fields
        for key, value in self.extra.items():
            extra[key] = value
        
        # Add context data
        if hasattr(_context, 'data'):
            extra['context'] = _context.data
        
        kwargs['extra'] = extra
        return msg, kwargs
    
    def with_fields(self, **fields) -> 'StructuredLogger':
        """Create a new logger with additional fields."""
        new_extra = self.extra.copy()
        new_extra.update(fields)
        return StructuredLogger(self.logger, new_extra)


class LogContext:
    """Context manager for adding structured context to logs."""
    
    def __init__(self, **kwargs):
        self.context_data = kwargs
        self.previous_data = None
    
    def __enter__(self):
        """Enter context and save previous state."""
        if not hasattr(_context, 'data'):
            _context.data = {}
        self.previous_data = _context.data.copy()
        _context.data.update(self.context_data)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore previous state."""
        _context.data = self.previous_data
        return False


def performance_logger(operation: str = None):
    """Decorator for logging function performance metrics."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation or f"{func.__module__}.{func.__name__}"
            logger = get_logger(func.__module__)
            
            start_time = time.time()
            success = False
            error = None
            
            try:
                with LogContext(operation=op_name, function=func.__name__):
                    logger.debug(f"Starting operation: {op_name}")
                    result = func(*args, **kwargs)
                    success = True
                    return result
            except Exception as e:
                error = str(e)
                logger.error(f"Operation failed: {op_name}", 
                           exc_info=True,
                           extra={"error": error})
                raise
            finally:
                duration = (time.time() - start_time) * 1000  # Convert to ms
                logger.info(f"Operation completed: {op_name}",
                          extra={
                              "duration_ms": duration,
                              "success": success,
                              "error": error,
                              "performance_metric": True
                          })
        
        return wrapper
    return decorator


def setup_logging(
    level: Union[str, int] = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True,
    structured: bool = True,
    include_context: bool = True
) -> None:
    """Set up the logging configuration for the entire application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output
        console: Whether to log to console
        structured: Whether to use structured JSON logging
        include_context: Whether to include context in structured logs
    """
    # Convert string level to logging constant
    if isinstance(level, str):
        level = getattr(logging, level.upper())
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set root logger level
    root_logger.setLevel(level)
    
    # Create formatter
    if structured:
        formatter = StructuredFormatter(include_context=include_context)
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Add console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Add file handler
    if log_file:
        # Create directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Log startup message
    logger = get_logger(__name__)
    logger.info("Logging system initialized",
                extra={
                    "level": logging.getLevelName(level),
                    "structured": structured,
                    "console": console,
                    "log_file": log_file
                })


def get_logger(name: str, **extra) -> StructuredLogger:
    """Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        **extra: Additional fields to include in all logs from this logger
        
    Returns:
        StructuredLogger instance
    """
    logger = logging.getLogger(name)
    return StructuredLogger(logger, extra)


# Convenience context managers for common operations
@contextmanager
def log_operation(operation: str, logger: Optional[StructuredLogger] = None, **extra):
    """Context manager for logging an operation with timing."""
    if logger is None:
        logger = get_logger(__name__)
    
    start_time = time.time()
    
    with LogContext(operation=operation, **extra):
        logger.info(f"Starting operation: {operation}")
        try:
            yield
            duration = (time.time() - start_time) * 1000
            logger.info(f"Operation completed: {operation}",
                       extra={"duration_ms": duration, "success": True})
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Operation failed: {operation}",
                        exc_info=True,
                        extra={"duration_ms": duration, "success": False})
            raise


@contextmanager
def log_cognitive_operation(layer: str, operation: str, **extra):
    """Context manager for logging cognitive layer operations."""
    with LogContext(cognitive_layer=layer, **extra):
        with log_operation(f"{layer}.{operation}"):
            yield