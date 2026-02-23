"""Tests for chat message models."""

import pytest
from app.company.message_models import (
    ChatRequestPayload,
    ChatResponsePayload,
    ChatMetadata,
)


class TestChatRequestPayload:
    """Test cases for ChatRequestPayload."""

    def test_init_with_minimal_fields(self):
        """Test initialization with required fields only."""
        payload = ChatRequestPayload(
            messages=[{"role": "user", "content": "Hello"}],
            model="employee-1",
            temperature=0.7,
        )
        assert payload.messages == [{"role": "user", "content": "Hello"}]
        assert payload.model == "employee-1"
        assert payload.temperature == 0.7
        assert payload.max_tokens is None

    def test_init_with_all_fields(self):
        """Test initialization with all optional fields."""
        payload = ChatRequestPayload(
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
            model="employee-1",
            temperature=0.9,
            max_tokens=100,
            top_p=0.8,
            stream=True,
            stop="END",
            frequency_penalty=0.5,
            presence_penalty=0.3,
        )
        assert len(payload.messages) == 2
        assert payload.top_p == 0.8
        assert payload.stream is True
        assert payload.stop == "END"
        assert payload.frequency_penalty == 0.5
        assert payload.presence_penalty == 0.3

    def test_to_dict(self):
        """Test serialization to dictionary."""
        payload = ChatRequestPayload(
            messages=[{"role": "user", "content": "Hello"}],
            model="employee-1",
            temperature=0.7,
        )
        data = payload.to_dict()
        assert data["messages"] == [{"role": "user", "content": "Hello"}]
        assert data["model"] == "employee-1"
        assert data["temperature"] == 0.7
        assert "max_tokens" not in data  # Optional field not in dict when None

    def test_to_dict_with_optional_fields(self):
        """Test serialization with optional fields."""
        payload = ChatRequestPayload(
            messages=[{"role": "user", "content": "Hello"}],
            model="employee-1",
            temperature=0.7,
            max_tokens=100,
            stream=True,
        )
        data = payload.to_dict()
        assert data["max_tokens"] == 100
        assert data["stream"] is True

    def test_to_dict_with_float_precision(self):
        """Test that float precision is preserved."""
        payload = ChatRequestPayload(
            messages=[{"role": "user", "content": "Hello"}],
            model="employee-1",
            temperature=0.123456,
        )
        data = payload.to_dict()
        assert data["temperature"] == 0.123456


class TestChatResponsePayload:
    """Test cases for ChatResponsePayload."""

    def test_init_success_response(self):
        """Test initialization with successful response."""
        payload = ChatResponsePayload(
            content="Here is your answer", finish_reason="stop"
        )
        assert payload.content == "Here is your answer"
        assert payload.finish_reason == "stop"
        assert payload.tokens_used is None
        assert payload.error is None

    def test_init_with_tokens_used(self):
        """Test initialization with token usage data."""
        payload = ChatResponsePayload(
            content="Response",
            finish_reason="stop",
            tokens_used={
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        )
        assert payload.tokens_used == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    def test_init_with_error(self):
        """Test initialization with error."""
        payload = ChatResponsePayload(
            content="", finish_reason="error", error="Agent timed out"
        )
        assert payload.error == "Agent timed out"

    def test_to_dict_success(self):
        """Test serialization of successful response."""
        payload = ChatResponsePayload(content="Response text", finish_reason="stop")
        data = payload.to_dict()
        assert data["content"] == "Response text"
        assert data["finish_reason"] == "stop"
        assert data["tokens_used"] is None
        assert "error" not in data

    def test_to_dict_with_error(self):
        """Test serialization of error response."""
        payload = ChatResponsePayload(
            content="", finish_reason="error", error="Something went wrong"
        )
        data = payload.to_dict()
        assert data["error"] == "Something went wrong"

    def test_to_dict_with_tokens(self):
        """Test serialization with tokens."""
        payload = ChatResponsePayload(
            content="Response",
            finish_reason="stop",
            tokens_used={
                "prompt_tokens": 5,
                "completion_tokens": 10,
                "total_tokens": 15,
            },
        )
        data = payload.to_dict()
        assert data["tokens_used"]["prompt_tokens"] == 5
        assert data["tokens_used"]["completion_tokens"] == 10
        assert data["tokens_used"]["total_tokens"] == 15


class TestChatMetadata:
    """Test cases for ChatMetadata."""

    def test_init_with_required_fields(self):
        """Test initialization with required fields."""
        metadata = ChatMetadata(
            request_id="req-123",
            agent_id="employee-1",
            start_time="2026-02-23T10:00:00Z",
        )
        assert metadata.request_id == "req-123"
        assert metadata.agent_id == "employee-1"
        assert metadata.start_time == "2026-02-23T10:00:00Z"
        assert metadata.completion_time is None
        assert metadata.duration_ms is None

    def test_init_with_optional_fields(self):
        """Test initialization with optional fields."""
        metadata = ChatMetadata(
            request_id="req-123",
            agent_id="employee-1",
            start_time="2026-02-23T10:00:00Z",
            completion_time="2026-02-23T10:00:05Z",
            duration_ms=5000.0,
        )
        assert metadata.completion_time == "2026-02-23T10:00:05Z"
        assert metadata.duration_ms == 5000.0

    def test_to_dict(self):
        """Test serialization."""
        metadata = ChatMetadata(
            request_id="req-123",
            agent_id="employee-1",
            start_time="2026-02-23T10:00:00Z",
            completion_time="2026-02-23T10:00:05Z",
            duration_ms=5000.0,
        )
        data = metadata.to_dict()
        assert data["request_id"] == "req-123"
        assert data["agent_id"] == "employee-1"
        assert data["start_time"] == "2026-02-23T10:00:00Z"
        assert data["completion_time"] == "2026-02-23T10:00:05Z"
        assert data["duration_ms"] == 5000.0

    def test_to_dict_with_only_required_fields(self):
        """Test serialization with only required fields."""
        metadata = ChatMetadata(
            request_id="req-123",
            agent_id="employee-1",
            start_time="2026-02-23T10:00:00Z",
        )
        data = metadata.to_dict()
        assert data["request_id"] == "req-123"
        assert "completion_time" not in data
        assert "duration_ms" not in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
