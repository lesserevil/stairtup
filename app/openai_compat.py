import asyncio
import json
import time
import uuid
from datetime import datetime
from functools import wraps
import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.company.slaick import MessageType, Slaick
from app.company.message_models import ChatRequestPayload, ChatResponsePayload, ChatMetadata
from app.company.cost_tracker import CostTracker

# Initialize Slaick and CostTracker
slaick = Slaick(file_path="slaick.jsonl")
cost_tracker = CostTracker(budget=10.0, operations_file="operations.jsonl")
router = APIRouter(prefix="/v1", tags=["openai-compat"])


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

    For now, this returns a mock response acknowledging the request.
    In production, this would route to the actual agent for processing.

    Args:
        request: The chat completion request with model and messages.

    Returns:
        A mock chat completion response.
    """
    # Generate a unique completion ID
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    # Get the last user message for context
    user_message = "Hello"
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content[:100]  # First 100 chars
            break

    # Create a mock response acknowledging the model
    response_content = (
        f"🤖 Agent '{request.model}' received your message: \"{user_message}\"\n\n"
        "This is a mock response. In production, this would be processed by the "
        "actual employee agent through the Slaick messaging system.\n\n"
        f"Parameters: temperature={request.temperature}, max_tokens={request.max_tokens}, stream={request.stream}"
    )

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

async def _get_chat_response(self, request_id: str, employee_id: str) -> ChatResponsePayload:
    """
    Poll Slaick for response from Employee agent.
    
    Args:
        request_id: The request ID we're waiting for
        employee_id: The employee agent ID
    """
    logger.info(f"Waiting for chat response from {employee_id}")
    
    try:
        # Poll Slaick for response with timeout
        start_time = time.time()
        timeout = 120  # 2 minutes
        
        while time.time() - start_time < timeout:
            # Look for response message
            messages = slaick._read_messages(agent_id="orchestrator")
            
            for msg in messages:
                if msg.get("from") == "orchestrator" and msg.get("type") == "CHAT_RESPONSE":
                    return ChatResponsePayload(**msg.get("content", {}))
            
            await asyncio.sleep(1.0)
        
        logger.error(f"Timeout waiting for chat response {request_id}")
        raise HTTPException(
            status_code=504,
            detail="No response from agent within timeout"
        )
    except Exception as e:
        logger.error(f"Error waiting for chat response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error waiting for response: {str(e)}"
        )


def _format_response(self, response: ChatResponsePayload) -> ChatCompletionResponse:
    """
    Format Employee response as OpenAI-compatible response.
    
    Args:
        response: ChatResponsePayload from Employee
        
    Returns:
        ChatCompletionResponse compatible with OpenAI API
    """
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(role="assistant", content=response.content),
                finish_reason=response.finish_reason or "stop",
            )
        ],
        usage=Usage(
            prompt_tokens=len(request.model) * 100,  # Mock token count
            completion_tokens=0,
            total_tokens=len(request.model) * 100,
        ),
    )


@router.get("/health")
async def get_openai_health() -> dict[str, str]:
    """
    Health check endpoint for OpenAI-compatible API layer.
    
    Returns:
        Health status including status of AI endpoints
    """
    return {
        "status": "ready",
        "service": "stairtup-openai-api",
        "version": "0.1.0",
        "endpoints": {
            "chat_completions": "active",
            "models": "active",
        },
        "capabilities": {
            "chat": True,
            "streaming": False,  # TODO: Implement streaming
        },
    }
