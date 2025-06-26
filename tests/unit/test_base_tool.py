"""
Unit tests for BaseTool abstract class.
"""

import pytest
from abc import ABC
from core.base_tool import BaseTool


class ConcreteTool(BaseTool):
    """Concrete implementation of BaseTool for testing."""

    def __init__(self, name="TestTool", description="A test tool"):
        self.name = name
        self.description = description
        self.execution_count = 0
        self.last_result = None

    def execute(self, *args, **kwargs):
        self.execution_count += 1

        # Simple implementation that processes args and kwargs
        if args and kwargs:
            result = (
                f"Executed {self.name} with args: {args} "
                f"and kwargs: {kwargs}"
            )
        elif args:
            result = f"Executed {self.name} with args: {args}"
        elif kwargs:
            result = f"Executed {self.name} with kwargs: {kwargs}"
        else:
            result = f"Executed {self.name} with no parameters"

        self.last_result = result
        return result


class CalculatorTool(BaseTool):
    """A more complex tool implementation for testing."""

    def __init__(self):
        self.name = "Calculator"
        self.operations = {
            "add": lambda x, y: x + y,
            "subtract": lambda x, y: x - y,
            "multiply": lambda x, y: x * y,
            "divide": lambda x, y: x / y if y != 0 else None,
        }

    def execute(self, operation, x, y):
        if operation not in self.operations:
            raise ValueError(f"Unknown operation: {operation}")
        return self.operations[operation](x, y)


class TestBaseTool:
    """Test suite for BaseTool functionality."""

    @pytest.mark.unit
    def test_base_tool_is_abstract(self):
        """Test that BaseTool cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BaseTool()
        assert "Can't instantiate abstract class" in str(exc_info.value)

    @pytest.mark.unit
    def test_base_tool_requires_execute(self):
        """Test that subclasses must implement execute method."""

        class IncompleteTool(BaseTool):
            pass

        with pytest.raises(TypeError):
            IncompleteTool()

    @pytest.mark.unit
    def test_concrete_tool_instantiation(self):
        """Test that a properly implemented tool can be instantiated."""
        tool = ConcreteTool("MyTool", "Does something useful")
        assert tool.name == "MyTool"
        assert tool.description == "Does something useful"
        assert tool.execution_count == 0
        assert tool.last_result is None

    @pytest.mark.unit
    def test_concrete_tool_execute_no_params(self):
        """Test executing tool without parameters."""
        tool = ConcreteTool()
        result = tool.execute()
        assert result == "Executed TestTool with no parameters"
        assert tool.execution_count == 1
        assert tool.last_result == result

    @pytest.mark.unit
    def test_concrete_tool_execute_with_args(self):
        """Test executing tool with positional arguments."""
        tool = ConcreteTool()
        result = tool.execute("arg1", "arg2", 123)
        assert result == "Executed TestTool with args: ('arg1', 'arg2', 123)"
        assert tool.execution_count == 1

    @pytest.mark.unit
    def test_concrete_tool_execute_with_kwargs(self):
        """Test executing tool with keyword arguments."""
        tool = ConcreteTool()
        result = tool.execute(param1="value1", param2=42)
        assert "param1" in result
        assert "value1" in result
        assert "param2" in result
        assert "42" in result

    @pytest.mark.unit
    def test_concrete_tool_execute_mixed_params(self):
        """Test executing tool with both args and kwargs."""
        tool = ConcreteTool()
        result = tool.execute("arg1", param="value")
        assert "arg1" in result
        assert "param" in result
        assert "value" in result

    @pytest.mark.unit
    def test_calculator_tool_operations(self):
        """Test a more complex tool implementation."""
        calc = CalculatorTool()

        # Test basic operations
        assert calc.execute("add", 5, 3) == 8
        assert calc.execute("subtract", 10, 4) == 6
        assert calc.execute("multiply", 3, 7) == 21
        assert calc.execute("divide", 20, 5) == 4

        # Test division by zero
        assert calc.execute("divide", 10, 0) is None

        # Test invalid operation
        with pytest.raises(ValueError) as exc_info:
            calc.execute("modulo", 10, 3)
        assert "Unknown operation: modulo" in str(exc_info.value)

    @pytest.mark.unit
    def test_tool_multiple_executions(self):
        """Test multiple executions of a tool."""
        tool = ConcreteTool()

        # Execute multiple times
        results = []
        for i in range(5):
            result = tool.execute(f"iteration_{i}")
            results.append(result)

        assert tool.execution_count == 5
        assert len(results) == 5
        assert all(f"iteration_{i}" in results[i] for i in range(5))

    @pytest.mark.unit
    def test_tool_inheritance_chain(self):
        """Test that BaseTool is properly inheriting from ABC."""
        assert issubclass(BaseTool, ABC)
        assert issubclass(ConcreteTool, BaseTool)
        assert issubclass(CalculatorTool, BaseTool)
