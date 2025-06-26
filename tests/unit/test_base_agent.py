"""
Unit tests for BaseAgent abstract class.
"""

import pytest
from abc import ABC
from core.base_agent import BaseAgent


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    def __init__(self, name="TestAgent"):
        self.name = name
        self.thoughts = []
        self.actions = []

    def think(self, input_data):
        thought = f"Processing: {input_data}"
        self.thoughts.append(thought)
        return thought

    def act(self, action):
        self.actions.append(action)
        return f"Executed: {action}"


class TestBaseAgent:
    """Test suite for BaseAgent functionality."""

    @pytest.mark.unit
    def test_base_agent_is_abstract(self):
        """Test that BaseAgent cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BaseAgent()
        assert "Can't instantiate abstract class" in str(exc_info.value)

    @pytest.mark.unit
    def test_base_agent_requires_methods(self):
        """Test that subclasses must implement required methods."""

        class IncompleteAgent(BaseAgent):
            def think(self, input_data):
                return "thinking"

            # Missing act() method

        with pytest.raises(TypeError):
            IncompleteAgent()

    @pytest.mark.unit
    def test_concrete_agent_instantiation(self):
        """Test that a properly implemented agent can be instantiated."""
        agent = ConcreteAgent("TestBot")
        assert agent.name == "TestBot"
        assert agent.thoughts == []
        assert agent.actions == []

    @pytest.mark.unit
    def test_concrete_agent_think(self):
        """Test the think method of a concrete agent."""
        agent = ConcreteAgent()
        result = agent.think("test input")
        assert result == "Processing: test input"
        assert len(agent.thoughts) == 1
        assert agent.thoughts[0] == "Processing: test input"

    @pytest.mark.unit
    def test_concrete_agent_act(self):
        """Test the act method of a concrete agent."""
        agent = ConcreteAgent()
        result = agent.act("move_forward")
        assert result == "Executed: move_forward"
        assert len(agent.actions) == 1
        assert agent.actions[0] == "move_forward"

    @pytest.mark.unit
    def test_agent_multiple_operations(self):
        """Test multiple think and act operations."""
        agent = ConcreteAgent()

        # Multiple think operations
        agent.think("input1")
        agent.think("input2")
        agent.think("input3")

        # Multiple act operations
        agent.act("action1")
        agent.act("action2")

        assert len(agent.thoughts) == 3
        assert len(agent.actions) == 2
        assert agent.thoughts[1] == "Processing: input2"
        assert agent.actions[1] == "action2"

    @pytest.mark.unit
    def test_agent_inheritance_chain(self):
        """Test that BaseAgent is properly inheriting from ABC."""
        assert issubclass(BaseAgent, ABC)
        assert issubclass(ConcreteAgent, BaseAgent)
        assert issubclass(ConcreteAgent, ABC)
