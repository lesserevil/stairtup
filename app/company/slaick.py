"""
Slaick communication protocol - JSONL-based messaging system for inter-agent communication.

This module provides an append-only JSONL message log for agents to communicate.
Messages are written atomically to ensure thread-safety across processes.
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MessageType(str, Enum):
    """Supported message types for agent communication."""

    HIRE = "HIRE"
    CLAIM = "CLAIM"
    ACK = "ACK"
    PROGRESS = "PROGRESS"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class Slaick:
    """
    JSONL-based messaging system for inter-agent communication.

    Provides append-only message storage with atomic writes for thread-safety.
    Supports filtering by recipient, sender, message type, and message ID.

    Attributes:
        file_path: Path to the JSONL file for message storage
    """

    def __init__(self, file_path: Optional[Path | str] = None):
        """
        Initialize the Slaick message system.

        Args:
            file_path: Path to the JSONL file. Defaults to 'slaick.jsonl' in cwd.
        """
        if file_path is None:
            file_path = Path("slaick.jsonl")
        self.file_path = Path(file_path)
        # Ensure file exists
        self.file_path.touch(exist_ok=True)

    def _generate_timestamp(self) -> str:
        """Generate ISO 8601 timestamp in UTC."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def append_message(
        self,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType | str,
        payload: dict[str, Any],
        message_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Append a message to the JSONL log.

        Uses atomic append operation for thread-safety across processes.

        Args:
            from_agent: ID of the sending agent
            to_agent: ID of the receiving agent
            msg_type: Type of message (MessageType enum or string)
            payload: Message payload data
            message_id: Optional custom message ID (defaults to UUID v4)

        Returns:
            The complete message dict that was written

        Raises:
            IOError: If file write fails
        """
        # Normalize message type
        if isinstance(msg_type, MessageType):
            msg_type = msg_type.value

        # Build message
        message = {
            "id": message_id or str(uuid.uuid4()),
            "timestamp": self._generate_timestamp(),
            "from": from_agent,
            "to": to_agent,
            "type": msg_type,
            "payload": payload,
        }

        # Atomically append to file
        line = json.dumps(message, separators=(",", ":"))
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

        return message

    def _read_all_messages(self) -> list[dict[str, Any]]:
        """
        Read all messages from the JSONL file.

        Returns:
            List of message dicts in order written
        """
        messages = []
        if not self.file_path.exists():
            return messages

        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

        return messages

    def get_messages(
        self,
        since: Optional[str] = None,
        to: Optional[str] = None,
        from_: Optional[str] = None,
        msg_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Query messages with optional filters.

        Args:
            since: Return messages with ID > since_id (exclusive)
            to: Filter by recipient agent ID
            from_: Filter by sender agent ID
            msg_type: Filter by message type

        Returns:
            List of matching message dicts
        """
        messages = self._read_all_messages()

        # Apply filters
        filtered = messages

        if since is not None:
            # Find index of message with since_id
            found = False
            result = []
            for msg in filtered:
                if msg.get("id") == since:
                    found = True
                    continue
                if found:
                    result.append(msg)
            # If since_id not found, return all messages
            if not found:
                result = filtered
            filtered = result

        if to is not None:
            filtered = [m for m in filtered if m.get("to") == to]

        if from_ is not None:
            filtered = [m for m in filtered if m.get("from") == from_]

        if msg_type is not None:
            filtered = [m for m in filtered if m.get("type") == msg_type]

        return filtered

    def get_new_messages(self, since_id: str) -> list[dict[str, Any]]:
        """
        Get all messages written after a specific message ID.

        Args:
            since_id: Message ID to start after (exclusive)

        Returns:
            List of messages written after since_id
        """
        return self.get_messages(since=since_id)

    def get_conversation(
        self, agent1: str, agent2: str, limit: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """
        Get messages between two agents (in either direction).

        Args:
            agent1: First agent ID
            agent2: Second agent ID
            limit: Maximum number of messages to return (most recent)

        Returns:
            List of messages between the two agents, ordered chronologically
        """
        messages = self._read_all_messages()

        # Filter for bidirectional conversation
        conversation = [
            m
            for m in messages
            if (m.get("from") == agent1 and m.get("to") == agent2)
            or (m.get("from") == agent2 and m.get("to") == agent1)
        ]

        if limit is not None:
            conversation = conversation[-limit:]

        return conversation

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        """
        Get the last N messages.

        Args:
            n: Number of most recent messages to return

        Returns:
            List of the last N messages in chronological order
        """
        messages = self._read_all_messages()
        return messages[-n:] if len(messages) > n else messages

    def tail_messages(self, n: int) -> list[dict[str, Any]]:
        """
        Alias for tail() - get last N messages.

        Args:
            n: Number of messages to return

        Returns:
            List of last N messages
        """
        return self.tail(n)

    def get_message_by_id(self, message_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a specific message by ID.

        Args:
            message_id: The message UUID to find

        Returns:
            Message dict if found, None otherwise
        """
        messages = self._read_all_messages()
        for msg in messages:
            if msg.get("id") == message_id:
                return msg
        return None

    def get_unread_for_agent(
        self, agent_id: str, last_read_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get unread messages for an agent.

        Args:
            agent_id: The agent to get messages for
            last_read_id: Last message ID the agent has seen

        Returns:
            List of messages for the agent since last_read_id
        """
        if last_read_id:
            # Get all messages after last_read_id, filtered by recipient
            all_new = self.get_messages(since=last_read_id)
            return [m for m in all_new if m.get("to") == agent_id]
        else:
            # No last read ID - return all messages to this agent
            return self.get_messages(to=agent_id)

    def count_messages(self) -> int:
        """
        Get total message count.

        Returns:
            Number of messages in the log
        """
        return len(self._read_all_messages())
