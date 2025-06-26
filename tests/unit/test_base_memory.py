"""
Unit tests for BaseMemory abstract class.
"""

import pytest
from abc import ABC
from core.base_memory import BaseMemory


class ConcreteMemory(BaseMemory):
    """Concrete implementation of BaseMemory for testing."""

    def __init__(self, capacity=100):
        self.capacity = capacity
        self.storage = {}
        self.access_count = {}

    def store(self, key, value):
        if len(self.storage) >= self.capacity:
            # Simple eviction: remove least accessed
            if self.access_count:
                least_accessed = min(
                    self.access_count, key=self.access_count.get
                )
                del self.storage[least_accessed]
                del self.access_count[least_accessed]

        self.storage[key] = value
        self.access_count[key] = 0
        return True

    def retrieve(self, key):
        if key in self.storage:
            self.access_count[key] += 1
            return self.storage[key]
        return None


class TestBaseMemory:
    """Test suite for BaseMemory functionality."""

    @pytest.mark.unit
    def test_base_memory_is_abstract(self):
        """Test that BaseMemory cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BaseMemory()
        assert "Can't instantiate abstract class" in str(exc_info.value)

    @pytest.mark.unit
    def test_base_memory_requires_methods(self):
        """Test that subclasses must implement required methods."""

        class IncompleteMemory(BaseMemory):
            def store(self, key, value):
                return True

            # Missing retrieve() method

        with pytest.raises(TypeError):
            IncompleteMemory()

    @pytest.mark.unit
    def test_concrete_memory_instantiation(self):
        """Test that a properly implemented memory can be instantiated."""
        memory = ConcreteMemory(capacity=50)
        assert memory.capacity == 50
        assert len(memory.storage) == 0
        assert len(memory.access_count) == 0

    @pytest.mark.unit
    def test_concrete_memory_store(self):
        """Test storing data in concrete memory."""
        memory = ConcreteMemory()
        result = memory.store("key1", "value1")
        assert result is True
        assert "key1" in memory.storage
        assert memory.storage["key1"] == "value1"
        assert memory.access_count["key1"] == 0

    @pytest.mark.unit
    def test_concrete_memory_retrieve(self):
        """Test retrieving data from concrete memory."""
        memory = ConcreteMemory()
        memory.store("key1", "value1")

        # Retrieve existing key
        result = memory.retrieve("key1")
        assert result == "value1"
        assert memory.access_count["key1"] == 1

        # Retrieve non-existing key
        result = memory.retrieve("nonexistent")
        assert result is None

    @pytest.mark.unit
    def test_memory_capacity_limit(self):
        """Test memory capacity and eviction."""
        memory = ConcreteMemory(capacity=3)

        # Fill memory to capacity
        memory.store("key1", "value1")
        memory.store("key2", "value2")
        memory.store("key3", "value3")

        # Access key2 to increase its access count
        memory.retrieve("key2")
        memory.retrieve("key2")

        # Store new item, should evict least accessed (key1 or key3)
        memory.store("key4", "value4")

        assert len(memory.storage) == 3
        assert "key4" in memory.storage
        # Should not be evicted due to high access
        assert "key2" in memory.storage

    @pytest.mark.unit
    def test_memory_store_retrieve_cycle(self):
        """Test multiple store and retrieve operations."""
        memory = ConcreteMemory()

        # Store multiple items
        test_data = {
            "item1": {"data": "test1"},
            "item2": [1, 2, 3],
            "item3": "simple string",
            "item4": 42,
        }

        for key, value in test_data.items():
            memory.store(key, value)

        # Retrieve and verify all items
        for key, expected_value in test_data.items():
            retrieved = memory.retrieve(key)
            assert retrieved == expected_value

    @pytest.mark.unit
    def test_memory_inheritance_chain(self):
        """Test that BaseMemory is properly inheriting from ABC."""
        assert issubclass(BaseMemory, ABC)
        assert issubclass(ConcreteMemory, BaseMemory)
        assert issubclass(ConcreteMemory, ABC)
