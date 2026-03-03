"""
OpenAI-compatible API endpoints for the Agent Company Swarm.

This module provides OpenAI API-compatible endpoints for integration
with existing tools and clients that expect OpenAI-style responses.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.company.cost_tracker import CostTracker
from app.company.message_models import ChatRequestPayload, ChatResponsePayload
from app.company.slaick import MessageType, Slaick

router = APIRouter(prefix="/v1", tags=["openai-compat"])

_slaick = Slaick()
_cost_tracker = CostTracker()


# Pydantic models for OpenAI API compatibility
class ChatMessage(BaseModel):
    """A single chat message."""

    role: str = Field(
        ..., description="The role of the message author (system, user, assistant)"
    )
    content: str = Field(..., description="The content of the message")


class ChatCompletionRequest(BaseModel):
    """Request body for chat completions endpoint."""

    model: str = Field(..., description="ID of the model/employee to use")
    messages: list[ChatMessage] = Field(
        ..., description="A list of messages comprising the conversation"
    )
    temperature: float | None = Field(
        1.0, ge=0, le=2, description="Sampling temperature"
    )
    max_tokens: int | None = Field(
        None, ge=1, description="Maximum number of tokens to generate"
    )
    stream: bool | None = Field(
        False, description="Whether to stream back partial progress"
    )
    top_p: float | None = Field(
        1.0, ge=0, le=1, description="Nucleus sampling parameter"
    )
    n: int | None = Field(
        1, ge=1, le=128, description="Number of completions to generate"
    )
    stop: str | list[str] | None = Field(None, description="Stop sequences")
    presence_penalty: float | None = Field(
        0, ge=-2, le=2, description="Presence penalty"
    )
    frequency_penalty: float | None = Field(
        0, ge=-2, le=2, description="Frequency penalty"
    )


class ModelInfo(BaseModel):
    """Information about a model (employee)."""

    id: str = Field(..., description="The model identifier")
    object: str = "model"
    created: int = Field(..., description="Unix timestamp when the model was created")
    owned_by: str = Field(
        default="agent-company", description="Organization that owns the model"
    )


class ModelList(BaseModel):
    """List of available models."""

    object: str = "list"
    data: list[ModelInfo]


class Choice(BaseModel):
    """A single completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str | None = "stop"


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Response from chat completions endpoint."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


def read_employees_jsonl() -> list[dict[str, Any]]:
    """Read and parse the employees.jsonl file."""
    employees_path = Path("employees.jsonl")
    employees = []

    if not employees_path.exists():
        return employees

    try:
        with open(employees_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and line != "[]":
                    try:
                        record = json.loads(line)
                        employees.append(record)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return employees


def read_slaick_jsonl(limit: int = 20) -> list[dict[str, Any]]:
    """Read and parse the slaick.jsonl file, returning the last N entries."""
    slaick_path = Path("slaick.jsonl")
    messages = []

    if not slaick_path.exists():
        return messages

    try:
        with open(slaick_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and line != "[]":
                    try:
                        record = json.loads(line)
                        messages.append(record)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    # Return the last N messages (most recent)
    return messages[-limit:] if len(messages) > limit else messages


@router.get("/models", response_model=ModelList)
async def list_models() -> ModelList:
    """
    List all active employee agents as OpenAI-compatible models.

    Returns:
        A list of models where each model represents an active employee agent.
    """
    employees = read_employees_jsonl()
    models = []

    for emp in employees:
        if emp.get("status") == "active":
            # Use agent_id as the model ID
            model_id = emp.get("agent_id", str(uuid.uuid4())[:8])

            # Parse hired_at timestamp
            hired_at = emp.get("hired_at", "")
            try:
                if hired_at:
                    dt = datetime.fromisoformat(hired_at.replace("Z", "+00:00"))
                    created = int(dt.timestamp())
                else:
                    created = int(time.time())
            except (ValueError, TypeError):
                created = int(time.time())

            model = ModelInfo(
                id=model_id,
                created=created,
                owned_by="agent-company",
            )
            models.append(model)

    # If no active employees, return a default model
    if not models:
        models.append(
            ModelInfo(
                id="agent-company-default",
                created=int(time.time()),
                owned_by="agent-company",
            )
        )

    return ModelList(data=models)


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """
    Create a chat completion using the specified employee agent.

    Routes the chat request to the appropriate employee via Slaick
    messaging system and waits for the response.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    request_id = str(uuid.uuid4())

    user_message = "Hello"
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content[:100]
            break

    model_id = request.model

    employees = read_employees_jsonl()
    target_agent = None
    for emp in employees:
        if emp.get("agent_id") == model_id:
            target_agent = model_id
            break

    if not target_agent:
        logger.warning(f"Agent {model_id} not found, using default agent")
        if employees:
            target_agent = employees[0].get("agent_id")
        else:
            raise HTTPException(
                status_code=404, detail=f"No agents available to handle request"
            )

    if not _cost_tracker.can_afford(0.01, "chat"):
        raise HTTPException(
            status_code=429, detail="Budget exceeded. Circuit breaker tripped."
        )

    chat_request_payload = ChatRequestPayload(
        messages=[
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ],
        model=request.model,
        temperature=request.temperature or 1.0,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stream=request.stream,
        stop=request.stop,
        frequency_penalty=request.frequency_penalty or 0.0,
        presence_penalty=request.presence_penalty or 0.0,
    )

    _slaick.append_message(
        from_agent="api-gateway",
        to_agent=target_agent,
        msg_type=MessageType.CHAT_REQUEST,
        payload={
            "request_id": request_id,
            "chat_request": chat_request_payload.to_dict(),
            "reply_to": "api-gateway",
        },
    )

    logger.info(f"Sent CHAT_REQUEST {request_id} to {target_agent}")

    # Retry logic with exponential backoff
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            response_message = await asyncio.wait_for(
                _wait_for_chat_response(request_id, target_agent), timeout=30.0
            )
            break  # Success, exit retry loop
        except asyncio.TimeoutError:
            if attempt == max_retries - 1:
                # Last attempt failed
                raise HTTPException(
                    status_code=504, 
                    detail=f"Timeout waiting for agent response after {max_retries} attempts"
                )
            # Wait before retry with exponential backoff
            logger.warning(
                f"Timeout on attempt {attempt + 1}/{max_retries}, "
                f"retrying in {retry_delay}s..."
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff

    response_content = response_message.get("content", "No response received")
    tokens_used = response_message.get("tokens_used", {})

    _cost_tracker.record_cost(
        cost=0.01, agent_id=target_agent, category="chat", operation="chat_completion"
    )

    prompt_tokens = tokens_used.get("prompt_tokens", 0)
    completion_tokens = tokens_used.get("completion_tokens", 0)

    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(role="assistant", content=response_content),
                finish_reason=response_message.get("finish_reason", "stop"),
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


async def _wait_for_chat_response(
    request_id: str,
    target_agent: str,
    timeout: float = 30.0,
) -> dict:
    """
    Wait for a CHAT_RESPONSE message from the target agent.

    Args:
        request_id: The request ID to match
        target_agent: The agent that should respond
        timeout: Maximum time to wait in seconds

    Returns:
        The response payload dict
    """
    start_time = time.time()
    last_message_id = None

    while time.time() - start_time < timeout:
        messages = _slaick.get_messages(
            to="api-gateway", msg_type=MessageType.CHAT_RESPONSE.value
        )

        for msg in messages:
            if last_message_id and msg.get("id") == last_message_id:
                continue
            last_message_id = msg.get("id")

            payload = msg.get("payload", {})
            if payload.get("original_request_id") == request_id:
                logger.info(f"Received CHAT_RESPONSE for {request_id}")
                return payload.get("response", {})

        await asyncio.sleep(0.5)

    raise TimeoutError(f"No response from {target_agent} for {request_id}")

    # Calculate mock token counts (rough approximation)
    prompt_tokens = sum(len(msg.content.split()) for msg in request.messages)
    completion_tokens = len(response_content.split())

    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(role="assistant", content=response_content),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@router.get("/slaick/latest", response_class=HTMLResponse)
async def get_slaick_latest_html() -> HTMLResponse:
    """
    Get the latest Slaick messages formatted as HTML for HTMX polling.

    Returns:
        HTML representation of the last 20 Slaick messages.
    """
    messages = read_slaick_jsonl(limit=20)

    if not messages:
        return HTMLResponse(
            content="<div class='slaick-empty'>No messages yet...</div>"
        )

    html_parts = []
    for msg in reversed(messages):  # Most recent first
        timestamp = msg.get("timestamp", "")
        msg_type = msg.get("type", "INFO")
        payload = msg.get("payload", {})

        # Get sender from 'from' field, fallback to agent_id or 'system'
        sender = msg.get("from", "system")

        # Extract content based on message type
        content = ""
        if isinstance(payload, dict):
            if msg_type.upper() == "HIRE":
                # Show the role being hired
                role = payload.get("role", "Unknown Role")
                content = f"Hiring: {role}"
            elif msg_type.upper() == "PROGRESS":
                # Show worker's role and status
                role = payload.get("role", "Agent")
                status_msg = payload.get("message", "Working...")
                content = f"[{role}] {status_msg}"
            else:
                # Try message, role, or stringified payload
                content = payload.get("message") or payload.get("role") or str(payload)
        else:
            content = str(payload)

        # Handle potential missing keys gracefully
        if not content:
            content = "(no content)"
        if not sender:
            sender = "unknown"

        # Format timestamp
        try:
            if timestamp:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            else:
                time_str = "--:--:--"
        except (ValueError, TypeError):
            time_str = "--:--:--"

        # Determine message style based on type
        msg_class = "slaick-info"
        if msg_type.upper() in ["HIRE", "ACK"]:
            msg_class = "slaick-hire"
        elif msg_type.upper() in ["PROGRESS", "HEARTBEAT"]:
            msg_class = "slaick-progress"
        elif msg_type.upper() in ["COMPLETE", "DONE"]:
            msg_class = "slaick-complete"
        elif msg_type.upper() in ["ERROR", "FAIL"]:
            msg_class = "slaick-error"

        html_parts.append(
            f"<div class='slaick-message {msg_class}'>"
            f"<span class='slaick-time'>{time_str}</span>"
            f"<span class='slaick-type'>{msg_type}</span>"
            f"<span class='slaick-sender'>{sender}</span>"
            f"<span class='slaick-content'>{content[:100]}</span>"
            f"</div>"
        )

    return HTMLResponse(content="\n".join(html_parts))


@router.get("/slaick/latest/json")
async def get_slaick_latest_json(limit: int = 20) -> list[dict[str, Any]]:
    """
    Get the latest Slaick messages as JSON.

    Args:
        limit: Maximum number of messages to return (default: 20).

    Returns:
        List of recent Slaick messages.
    """
    return read_slaick_jsonl(limit=limit)


@router.get("/costs")
async def get_cost_breakdown() -> dict[str, Any]:
    """
    Get cost tracking breakdown.

    Returns:
        Dictionary with cost breakdown by category and totals.
    """
    return {
        "budget": _cost_tracker.budget,
        "current_spent": _cost_tracker.current_spent,
        "remaining_budget": _cost_tracker.get_remaining_budget(),
        "category_spending": _cost_tracker.get_all_category_spending(),
        "circuit_breaker_tripped": _cost_tracker.is_circuit_breaker_tripped(),
        "circuit_breaker_reason": _cost_tracker.get_circuit_breaker_reason(),
    }
