"""
Unit tests for BaseProtocol abstract class.
"""

import pytest
import json
import base64
from abc import ABC
from core.base_protocol import BaseProtocol


class JSONProtocol(BaseProtocol):
    """JSON-based protocol implementation for testing."""

    def encode(self, data):
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot encode data to JSON: {e}")

    def decode(self, data):
        try:
            return json.loads(data)
        except (TypeError, json.JSONDecodeError) as e:
            raise ValueError(f"Cannot decode JSON data: {e}")


class Base64Protocol(BaseProtocol):
    """Base64-based protocol implementation for testing."""

    def encode(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, bytes):
            data = str(data).encode("utf-8")
        return base64.b64encode(data).decode("ascii")

    def decode(self, data):
        try:
            decoded_bytes = base64.b64decode(data)
            return decoded_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Cannot decode Base64 data: {e}")


class CustomProtocol(BaseProtocol):
    """Custom protocol with prefix/suffix for testing."""

    def __init__(self, prefix="<MSG>", suffix="</MSG>"):
        self.prefix = prefix
        self.suffix = suffix

    def encode(self, data):
        return f"{self.prefix}{data}{self.suffix}"

    def decode(self, data):
        if not data.startswith(self.prefix) or not data.endswith(self.suffix):
            raise ValueError("Invalid message format")

        prefix_len = len(self.prefix)
        suffix_len = len(self.suffix)
        return data[prefix_len:-suffix_len]


class TestBaseProtocol:
    """Test suite for BaseProtocol functionality."""

    @pytest.mark.unit
    def test_base_protocol_is_abstract(self):
        """Test that BaseProtocol cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BaseProtocol()
        assert "Can't instantiate abstract class" in str(exc_info.value)

    @pytest.mark.unit
    def test_base_protocol_requires_methods(self):
        """Test that subclasses must implement required methods."""

        class IncompleteProtocol(BaseProtocol):
            def encode(self, data):
                return str(data)

            # Missing decode() method

        with pytest.raises(TypeError):
            IncompleteProtocol()

    @pytest.mark.unit
    def test_json_protocol_encode(self):
        """Test JSON protocol encoding."""
        protocol = JSONProtocol()

        # Test various data types
        assert protocol.encode({"key": "value"}) == '{"key": "value"}'
        assert protocol.encode([1, 2, 3]) == "[1, 2, 3]"
        assert protocol.encode("string") == '"string"'
        assert protocol.encode(42) == "42"
        assert protocol.encode(True) == "true"
        assert protocol.encode(None) == "null"

    @pytest.mark.unit
    def test_json_protocol_decode(self):
        """Test JSON protocol decoding."""
        protocol = JSONProtocol()

        # Test various JSON strings
        assert protocol.decode('{"key": "value"}') == {"key": "value"}
        assert protocol.decode("[1, 2, 3]") == [1, 2, 3]
        assert protocol.decode('"string"') == "string"
        assert protocol.decode("42") == 42
        assert protocol.decode("true") is True
        assert protocol.decode("null") is None

    @pytest.mark.unit
    def test_json_protocol_encode_decode_cycle(self):
        """Test encoding and decoding cycle."""
        protocol = JSONProtocol()

        test_data = {
            "name": "Test",
            "values": [1, 2, 3],
            "nested": {"key": "value"},
            "boolean": True,
            "null": None,
        }

        encoded = protocol.encode(test_data)
        decoded = protocol.decode(encoded)
        assert decoded == test_data

    @pytest.mark.unit
    def test_json_protocol_error_handling(self):
        """Test JSON protocol error handling."""
        protocol = JSONProtocol()

        # Test encoding error
        with pytest.raises(ValueError) as exc_info:
            protocol.encode(set([1, 2, 3]))  # Sets are not JSON serializable
        assert "Cannot encode data to JSON" in str(exc_info.value)

        # Test decoding error
        with pytest.raises(ValueError) as exc_info:
            protocol.decode("invalid json {")
        assert "Cannot decode JSON data" in str(exc_info.value)

    @pytest.mark.unit
    def test_base64_protocol_encode(self):
        """Test Base64 protocol encoding."""
        protocol = Base64Protocol()

        # Test string encoding
        assert protocol.encode("Hello World") == "SGVsbG8gV29ybGQ="

        # Test bytes encoding
        assert protocol.encode(b"Binary data") == "QmluYXJ5IGRhdGE="

        # Test other types (converted to string)
        assert protocol.encode(12345) == "MTIzNDU="

    @pytest.mark.unit
    def test_base64_protocol_decode(self):
        """Test Base64 protocol decoding."""
        protocol = Base64Protocol()

        assert protocol.decode("SGVsbG8gV29ybGQ=") == "Hello World"
        assert protocol.decode("QmluYXJ5IGRhdGE=") == "Binary data"
        assert protocol.decode("MTIzNDU=") == "12345"

    @pytest.mark.unit
    def test_base64_protocol_cycle(self):
        """Test Base64 encoding and decoding cycle."""
        protocol = Base64Protocol()

        test_strings = [
            "Simple text",
            "Text with special chars: @#$%",
            "Multi\nline\ntext",
            "Unicode: 你好世界",
        ]

        for text in test_strings:
            encoded = protocol.encode(text)
            decoded = protocol.decode(encoded)
            assert decoded == text

    @pytest.mark.unit
    def test_custom_protocol_encode_decode(self):
        """Test custom protocol implementation."""
        protocol = CustomProtocol()

        # Test encoding
        assert protocol.encode("Hello") == "<MSG>Hello</MSG>"

        # Test decoding
        assert protocol.decode("<MSG>Hello</MSG>") == "Hello"

        # Test with custom prefix/suffix
        protocol2 = CustomProtocol(prefix="[START]", suffix="[END]")
        assert protocol2.encode("Test") == "[START]Test[END]"
        assert protocol2.decode("[START]Test[END]") == "Test"

    @pytest.mark.unit
    def test_custom_protocol_error_handling(self):
        """Test custom protocol error handling."""
        protocol = CustomProtocol()

        # Test invalid format
        with pytest.raises(ValueError) as exc_info:
            protocol.decode("Invalid message")
        assert "Invalid message format" in str(exc_info.value)

        with pytest.raises(ValueError):
            protocol.decode("<MSG>Incomplete")

        with pytest.raises(ValueError):
            protocol.decode("NoPrefix</MSG>")

    @pytest.mark.unit
    def test_protocol_inheritance_chain(self):
        """Test that BaseProtocol is properly inheriting from ABC."""
        assert issubclass(BaseProtocol, ABC)
        assert issubclass(JSONProtocol, BaseProtocol)
        assert issubclass(Base64Protocol, BaseProtocol)
        assert issubclass(CustomProtocol, BaseProtocol)
