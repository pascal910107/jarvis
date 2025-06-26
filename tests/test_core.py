import pytest
from core.base_agent import BaseAgent
from core.base_tool import BaseTool
from core.base_memory import BaseMemory
from core.base_protocol import BaseProtocol


def test_base_agent_is_abstract():
    with pytest.raises(TypeError):
        BaseAgent()


def test_base_tool_is_abstract():
    with pytest.raises(TypeError):
        BaseTool()


def test_base_memory_is_abstract():
    with pytest.raises(TypeError):
        BaseMemory()


def test_base_protocol_is_abstract():
    with pytest.raises(TypeError):
        BaseProtocol()
