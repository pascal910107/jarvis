"""
Global pytest fixtures and configuration for the test suite.
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from typing import Generator, Any
import yaml


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Provide path to test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture(scope="function")
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test isolation."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture(scope="function")
def mock_config_file(temp_dir: Path) -> Path:
    """Create a mock configuration file for testing."""
    config_path = temp_dir / "config.yaml"
    config_data = {
        "agent": {"name": "TestAgent", "version": "0.1.0"},
        "memory": {"type": "redis", "host": "localhost", "port": 6379},
        "reasoning": {
            "system1": {"enabled": True},
            "system2": {"enabled": True},
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path


@pytest.fixture(scope="function")
def mock_agent_config() -> dict:
    """Provide mock agent configuration."""
    return {
        "name": "TestAgent",
        "capabilities": ["reasoning", "memory", "perception"],
        "max_threads": 4,
        "timeout": 30,
    }


@pytest.fixture(scope="function")
def mock_memory_data() -> list[dict[str, Any]]:
    """Provide mock memory data for testing."""
    return [
        {
            "id": "mem1",
            "type": "sensory",
            "data": "visual input",
            "timestamp": 1234567890,
        },
        {
            "id": "mem2",
            "type": "short_term",
            "data": "recent event",
            "timestamp": 1234567900,
        },
        {
            "id": "mem3",
            "type": "long_term",
            "data": "learned pattern",
            "timestamp": 1234567800,
        },
    ]


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def capture_logs(caplog):
    """Fixture to capture and return logs during tests."""
    with caplog.at_level("DEBUG"):
        yield caplog


# Performance benchmarking fixture
@pytest.fixture
def benchmark_timer():
    """Simple timer for performance testing."""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.time()

        def stop(self):
            self.end_time = time.time()
            return self.elapsed

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

    return Timer()


# Mock Redis fixture for testing without actual Redis
@pytest.fixture
def mock_redis():
    """Mock Redis connection for testing."""

    class MockRedis:
        def __init__(self):
            self.data = {}

        def set(self, key, value):
            self.data[key] = value
            return True

        def get(self, key):
            return self.data.get(key)

        def delete(self, key):
            if key in self.data:
                del self.data[key]
                return 1
            return 0

        def exists(self, key):
            return key in self.data

        def keys(self, pattern="*"):
            if pattern == "*":
                return list(self.data.keys())
            # Simple pattern matching for tests
            return [
                k for k in self.data.keys()
                if pattern.replace("*", "") in k
            ]

    return MockRedis()


# Pytest hooks for custom behavior
def pytest_configure(config):
    """Configure pytest with custom settings."""
    config.addinivalue_line(
        "markers",
        "requires_redis: mark test as requiring Redis connection",
    )
    config.addinivalue_line(
        "markers", "requires_gpu: mark test as requiring GPU"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add automatic markers."""
    for item in items:
        # Add unit marker to tests in test_unit_* files
        if "test_unit_" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Add integration marker to tests in test_integration_* files
        elif "test_integration_" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
