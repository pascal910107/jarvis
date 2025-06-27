"""Tests for the structured logging system."""

import json
import logging
import time
from io import StringIO
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch, MagicMock

import pytest

from core.monitoring.logger import (
    StructuredFormatter, StructuredLogger, LogContext,
    performance_logger, setup_logging, get_logger,
    log_operation, log_cognitive_operation
)


class TestStructuredFormatter:
    """Test structured log formatting."""
    
    def test_basic_formatting(self):
        """Test basic JSON log formatting."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )
        
        output = formatter.format(record)
        log_data = json.loads(output)
        
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.module"
        assert log_data["message"] == "Test message"
        assert log_data["module"] == "test"
        assert log_data["function"] == "test_function"
        assert log_data["line"] == 42
        assert "timestamp" in log_data
        assert "thread_id" in log_data
    
    def test_exception_formatting(self):
        """Test formatting with exception info."""
        formatter = StructuredFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
                func="test"
            )
        
        output = formatter.format(record)
        log_data = json.loads(output)
        
        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert log_data["exception"]["message"] == "Test error"
        assert len(log_data["exception"]["traceback"]) > 0
    
    def test_custom_fields(self):
        """Test formatting with custom fields."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
            func="test"
        )
        
        # Add custom fields
        record.user_id = "12345"
        record.request_id = "abc-123"
        
        output = formatter.format(record)
        log_data = json.loads(output)
        
        assert log_data["user_id"] == "12345"
        assert log_data["request_id"] == "abc-123"


class TestStructuredLogger:
    """Test structured logger adapter."""
    
    def test_logger_creation(self):
        """Test creating structured logger."""
        base_logger = logging.getLogger("test")
        logger = StructuredLogger(base_logger, {"service": "test_service"})
        
        assert logger.extra["service"] == "test_service"
    
    def test_with_fields(self):
        """Test adding fields to logger."""
        logger = get_logger("test", service="api")
        logger2 = logger.with_fields(user_id="123", request_id="abc")
        
        assert logger.extra["service"] == "api"
        assert logger2.extra["service"] == "api"
        assert logger2.extra["user_id"] == "123"
        assert logger2.extra["request_id"] == "abc"
        
        # Original logger should not be modified
        assert "user_id" not in logger.extra
    
    def test_logging_with_extra(self):
        """Test logging with extra fields."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        base_logger = logging.getLogger("test_extra")
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)
        
        logger = StructuredLogger(base_logger, {"service": "test"})
        logger.info("Test message", extra={"user_id": "123"})
        
        stream.seek(0)
        output = stream.read()
        log_data = json.loads(output)
        
        assert log_data["message"] == "Test message"
        assert log_data["service"] == "test"
        assert log_data["user_id"] == "123"


class TestLogContext:
    """Test log context management."""
    
    def test_context_manager(self):
        """Test LogContext context manager."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter(include_context=True))
        
        logger = logging.getLogger("test_context")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        with LogContext(operation="test_op", user_id="123"):
            logger.info("Inside context")
        
        logger.info("Outside context")
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # First log should have context
        log1 = json.loads(logs[0])
        assert log1["context"]["operation"] == "test_op"
        assert log1["context"]["user_id"] == "123"
        
        # Second log should not have context
        log2 = json.loads(logs[1])
        assert "context" not in log2 or log2["context"] == {}
    
    def test_nested_contexts(self):
        """Test nested log contexts."""
        from core.monitoring.logger import _context
        
        with LogContext(level1="a"):
            assert _context.data["level1"] == "a"
            
            with LogContext(level2="b", level1="override"):
                assert _context.data["level1"] == "override"
                assert _context.data["level2"] == "b"
            
            # Inner context should be removed
            assert _context.data["level1"] == "a"
            assert "level2" not in _context.data


class TestPerformanceLogger:
    """Test performance logging decorator."""
    
    def test_successful_operation(self):
        """Test logging successful operation."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        logger = logging.getLogger("test_perf")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        @performance_logger("custom_operation")
        def test_function():
            time.sleep(0.01)
            return "result"
        
        result = test_function()
        assert result == "result"
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # Should have start and complete logs
        assert len(logs) >= 2
        
        # Check completion log
        complete_log = None
        for log in logs:
            data = json.loads(log)
            if "Operation completed" in data["message"]:
                complete_log = data
                break
        
        assert complete_log is not None
        assert complete_log["duration_ms"] >= 10
        assert complete_log["success"] is True
        assert complete_log["performance_metric"] is True
    
    def test_failed_operation(self):
        """Test logging failed operation."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        logger = logging.getLogger("test_perf_fail")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        @performance_logger()
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_function()
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # Find error and completion logs
        error_log = None
        complete_log = None
        for log in logs:
            data = json.loads(log)
            if "Operation failed" in data["message"]:
                error_log = data
            elif "Operation completed" in data["message"]:
                complete_log = data
        
        assert error_log is not None
        assert complete_log is not None
        assert complete_log["success"] is False
        assert complete_log["error"] == "Test error"


class TestLoggingSetup:
    """Test logging configuration."""
    
    def test_setup_basic(self):
        """Test basic logging setup."""
        # Clear existing handlers
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        
        setup_logging(level="INFO", console=True, structured=False)
        
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)
        assert root.level == logging.INFO
    
    def test_setup_structured(self):
        """Test structured logging setup."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        
        setup_logging(level=logging.DEBUG, structured=True)
        
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, StructuredFormatter)
    
    def test_setup_with_file(self):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            
            root = logging.getLogger()
            for handler in root.handlers[:]:
                root.removeHandler(handler)
            
            setup_logging(
                level="WARNING",
                log_file=str(log_file),
                console=False,
                structured=True
            )
            
            # Test logging
            logger = get_logger("test")
            logger.warning("Test warning")
            
            # Check file was created and contains log
            assert log_file.exists()
            content = log_file.read_text()
            log_data = json.loads(content.strip())
            assert log_data["level"] == "WARNING"
            assert log_data["message"] == "Test warning"


class TestConvenienceFunctions:
    """Test convenience logging functions."""
    
    def test_log_operation(self):
        """Test log_operation context manager."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        logger = get_logger("test_op")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        with log_operation("test_task", logger, task_id="123"):
            time.sleep(0.01)
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # Should have start and complete logs
        start_log = json.loads(logs[0])
        complete_log = json.loads(logs[1])
        
        assert "Starting operation: test_task" in start_log["message"]
        assert "Operation completed: test_task" in complete_log["message"]
        assert complete_log["duration_ms"] >= 10
        assert complete_log["success"] is True
    
    def test_log_operation_failure(self):
        """Test log_operation with failure."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        logger = get_logger("test_op_fail")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        with pytest.raises(RuntimeError):
            with log_operation("failing_task", logger):
                raise RuntimeError("Task failed")
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # Find error log
        error_log = None
        for log in logs:
            data = json.loads(log)
            if "Operation failed" in data["message"]:
                error_log = data
                break
        
        assert error_log is not None
        assert error_log["success"] is False
    
    def test_log_cognitive_operation(self):
        """Test log_cognitive_operation context manager."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter(include_context=True))
        
        logger = logging.getLogger("test_cog")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        with log_cognitive_operation("perception", "image_processing", 
                                    model="resnet50"):
            logger.info("Processing image")
        
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        
        # Find the processing log
        process_log = None
        for log in logs:
            data = json.loads(log)
            if "Processing image" in data["message"]:
                process_log = data
                break
        
        assert process_log is not None
        assert process_log["context"]["cognitive_layer"] == "perception"
        assert process_log["context"]["model"] == "resnet50"


class TestThreadSafety:
    """Test thread safety of logging components."""
    
    def test_concurrent_logging(self):
        """Test logging from multiple threads."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        
        logger = get_logger("test_threads")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        results = []
        
        def log_messages(thread_id):
            for i in range(10):
                logger.info(f"Message {i}", extra={"thread": thread_id})
            results.append(thread_id)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=log_messages, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Check all threads completed
        assert len(results) == 5
        
        # Check all messages were logged
        stream.seek(0)
        logs = stream.read().strip().split('\n')
        assert len(logs) == 50  # 5 threads * 10 messages
        
        # Verify JSON formatting is intact
        for log in logs:
            data = json.loads(log)  # Should not raise exception
            assert "thread" in data
    
    def test_context_isolation(self):
        """Test that log contexts are thread-isolated."""
        results = {}
        
        def thread_function(thread_id):
            with LogContext(thread_id=thread_id):
                # Sleep to ensure contexts overlap
                time.sleep(0.01)
                from core.monitoring.logger import _context
                results[thread_id] = _context.data.get("thread_id")
        
        # Start threads with different contexts
        threads = []
        for i in range(3):
            t = threading.Thread(target=thread_function, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Each thread should see only its own context
        assert results[0] == 0
        assert results[1] == 1
        assert results[2] == 2