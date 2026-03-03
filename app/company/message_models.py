"""
Chat message models for AI integration.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ChatRequestPayload:
    """Payload sent from OpenAI API endpoint to Employee agents."""

    messages: list[dict[str, str]]
    model: str
    temperature: float
    max_tokens: Optional[int] = None
    top_p: Optional[float] = 1.0
    stream: bool = False
    stop: Optional[Any] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": self.stream,
            "stop": self.stop,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }


@dataclass
class ChatResponsePayload:
    """Payload returned from Employee agents to OpenAI API endpoint."""

    content: str
    finish_reason: str = "stop"
    tokens_used: Optional[dict[str, int]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "content": self.content,
            "finish_reason": self.finish_reason,
            "tokens_used": self.tokens_used,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class ChatMetadata:
    """Metadata for chat requests/responses."""

    request_id: str
    agent_id: str
    start_time: str
    completion_time: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "start_time": self.start_time,
            "completion_time": self.completion_time,
            "duration_ms": self.duration_ms,
        }
