"""
Performance tests for memory systems.
"""

import pytest
from tests.unit.test_base_memory import ConcreteMemory


class TestMemoryPerformance:
    """Performance test suite for memory operations."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_memory_store_performance(self, benchmark_timer):
        """Test performance of storing items in memory."""
        memory = ConcreteMemory(capacity=10000)

        # Benchmark storing 1000 items
        benchmark_timer.start()
        for i in range(1000):
            memory.store(f"key_{i}", f"value_{i}")
        benchmark_timer.stop()

        assert len(memory.storage) == 1000
        # Should complete in under 1 second
        assert benchmark_timer.elapsed < 1.0
        print(f"\nStore 1000 items: {benchmark_timer.elapsed:.4f} seconds")

    @pytest.mark.performance
    @pytest.mark.slow
    def test_memory_retrieve_performance(self, benchmark_timer):
        """Test performance of retrieving items from memory."""
        memory = ConcreteMemory(capacity=10000)

        # Pre-populate memory
        for i in range(1000):
            memory.store(f"key_{i}", f"value_{i}")

        # Benchmark retrieving all items
        benchmark_timer.start()
        for i in range(1000):
            value = memory.retrieve(f"key_{i}")
            assert value == f"value_{i}"
        benchmark_timer.stop()

        # Should complete in under 0.5 seconds
        assert benchmark_timer.elapsed < 0.5
        print(f"\nRetrieve 1000 items: {benchmark_timer.elapsed:.4f} seconds")

    @pytest.mark.performance
    def test_memory_eviction_performance(self, benchmark_timer):
        """Test performance of memory eviction."""
        memory = ConcreteMemory(capacity=100)

        # Fill memory beyond capacity to trigger evictions
        benchmark_timer.start()
        for i in range(200):
            memory.store(f"key_{i}", f"value_{i}")
        benchmark_timer.stop()

        assert len(memory.storage) == 100  # Should maintain capacity
        # Should be fast even with evictions
        assert benchmark_timer.elapsed < 0.1
        print(
            f"\nStore with eviction (200 items, capacity 100): "
            f"{benchmark_timer.elapsed:.4f} seconds"
        )

    @pytest.mark.performance
    def test_memory_mixed_operations(self, benchmark_timer):
        """Test performance of mixed store/retrieve operations."""
        memory = ConcreteMemory(capacity=1000)

        benchmark_timer.start()
        # Simulate realistic usage pattern
        for i in range(500):
            # Store new item
            memory.store(f"new_{i}", f"data_{i}")

            # Retrieve some existing items
            if i > 10:
                memory.retrieve(f"new_{i-5}")
                memory.retrieve(f"new_{i-10}")
        benchmark_timer.stop()

        assert len(memory.storage) <= 1000
        assert benchmark_timer.elapsed < 1.0
        print(
            f"\nMixed operations (1500 total): "
            f"{benchmark_timer.elapsed:.4f} seconds"
        )
