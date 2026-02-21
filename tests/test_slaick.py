"""
Tests for the Slaick communication protocol.

Tests cover:
- Single process write/read operations
- Concurrent message exchange between processes
- Message ordering and filtering
- Concurrent write safety
"""

import json
import multiprocessing
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from app.company.slaick import MessageType, Slaick

# Module-level helper functions for multiprocessing tests
# These must be at module level to be pickleable


def _writer_process(file_path, agent_id, partner_id, message_count):
    """Process that writes messages and reads thread."""
    slaick = Slaick(file_path)
    written_ids = []

    for i in range(message_count):
        msg = slaick.append_message(
            agent_id,
            partner_id,
            MessageType.PROGRESS,
            {"from": agent_id, "seq": i},
        )
        written_ids.append(msg["id"])
        time.sleep(0.01)

    time.sleep(0.1)
    all_messages = slaick.get_messages()
    return {"written": written_ids, "total_read": len(all_messages)}


def _write_messages(file_path, process_id, count):
    """Write messages from a process."""
    slaick = Slaick(file_path)
    for i in range(count):
        slaick.append_message(
            f"proc-{process_id}",
            "target",
            MessageType.PROGRESS,
            {"process": process_id, "msg": i},
        )
    return count


def _continuous_writer(file_path, message_count):
    """Continuously write messages."""
    slaick = Slaick(file_path)
    for i in range(message_count):
        slaick.append_message("writer", "reader", MessageType.PROGRESS, {"i": i})
        time.sleep(0.005)
    return message_count



class TestSlaickBasicOperations:
    """Test basic message operations in a single process."""

    @pytest.fixture
    def temp_slaick(self):
        """Create a temporary Slaick instance for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name
        slaick = Slaick(temp_path)
        yield slaick
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_append_message_returns_complete_message(self, temp_slaick):
        """Test that append_message returns a complete message dict."""
        msg = temp_slaick.append_message(
            from_agent="agent-1",
            to_agent="agent-2",
            msg_type=MessageType.HIRE,
            payload={"task_id": "bead-123"},
        )

        assert "id" in msg
        assert "timestamp" in msg
        assert msg["from"] == "agent-1"
        assert msg["to"] == "agent-2"
        assert msg["type"] == "HIRE"
        assert msg["payload"] == {"task_id": "bead-123"}
        # Verify UUID format
        uuid.UUID(msg["id"])  # Should not raise

    def test_append_message_with_string_type(self, temp_slaick):
        """Test that string message types work."""
        msg = temp_slaick.append_message(
            from_agent="agent-1",
            to_agent="agent-2",
            msg_type="CUSTOM_TYPE",
            payload={},
        )
        assert msg["type"] == "CUSTOM_TYPE"

    def test_get_all_messages(self, temp_slaick):
        """Test retrieving all messages."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {"n": 1})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {"n": 2})
        temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {"n": 3})

        messages = temp_slaick.get_messages()
        assert len(messages) == 3
        assert messages[0]["payload"]["n"] == 1
        assert messages[1]["payload"]["n"] == 2
        assert messages[2]["payload"]["n"] == 3

    def test_get_messages_filter_by_recipient(self, temp_slaick):
        """Test filtering messages by recipient."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {})
        temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {})

        messages = temp_slaick.get_messages(to="a2")
        assert len(messages) == 2
        assert all(m["to"] == "a2" for m in messages)

    def test_get_messages_filter_by_sender(self, temp_slaick):
        """Test filtering messages by sender."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {})
        temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {})

        messages = temp_slaick.get_messages(from_="a1")
        assert len(messages) == 2
        assert all(m["from"] == "a1" for m in messages)

    def test_get_messages_filter_by_type(self, temp_slaick):
        """Test filtering messages by type."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {})
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})

        messages = temp_slaick.get_messages(msg_type="HIRE")
        assert len(messages) == 2
        assert all(m["type"] == "HIRE" for m in messages)

    def test_get_new_messages_since_id(self, temp_slaick):
        """Test getting messages after a specific ID."""
        msg1 = temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        msg2 = temp_slaick.append_message("a2", "a1", MessageType.ACK, {})
        msg3 = temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {})

        new_messages = temp_slaick.get_new_messages(msg1["id"])
        assert len(new_messages) == 2
        assert new_messages[0]["id"] == msg2["id"]
        assert new_messages[1]["id"] == msg3["id"]

    def test_tail_messages(self, temp_slaick):
        """Test getting last N messages."""
        for i in range(10):
            temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {"i": i})

        tail = temp_slaick.tail(3)
        assert len(tail) == 3
        assert tail[0]["payload"]["i"] == 7
        assert tail[1]["payload"]["i"] == 8
        assert tail[2]["payload"]["i"] == 9

    def test_tail_messages_alias(self, temp_slaick):
        """Test that tail_messages is an alias for tail."""
        for i in range(5):
            temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {"i": i})

        assert temp_slaick.tail(2) == temp_slaick.tail_messages(2)

    def test_get_conversation_bidirectional(self, temp_slaick):
        """Test getting conversation between two agents."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {"n": 1})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {"n": 2})
        temp_slaick.append_message("a1", "a3", MessageType.HIRE, {"n": 3})
        temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {"n": 4})

        conv = temp_slaick.get_conversation("a1", "a2")
        assert len(conv) == 3
        assert conv[0]["payload"]["n"] == 1
        assert conv[1]["payload"]["n"] == 2
        assert conv[2]["payload"]["n"] == 4

    def test_get_conversation_with_limit(self, temp_slaick):
        """Test conversation with limit."""
        for i in range(10):
            temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {"i": i})

        conv = temp_slaick.get_conversation("a1", "a2", limit=3)
        assert len(conv) == 3
        assert conv[-1]["payload"]["i"] == 9

    def test_get_message_by_id(self, temp_slaick):
        """Test retrieving a specific message."""
        msg = temp_slaick.append_message("a1", "a2", MessageType.HIRE, {"data": "test"})

        retrieved = temp_slaick.get_message_by_id(msg["id"])
        assert retrieved is not None
        assert retrieved["id"] == msg["id"]
        assert retrieved["payload"]["data"] == "test"

    def test_get_message_by_id_not_found(self, temp_slaick):
        """Test retrieving non-existent message."""
        result = temp_slaick.get_message_by_id("non-existent-id")
        assert result is None

    def test_get_unread_for_agent(self, temp_slaick):
        """Test getting unread messages for an agent."""
        msg1 = temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {})
        msg3 = temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {})

        # Get all messages for a2
        unread = temp_slaick.get_unread_for_agent("a2")
        assert len(unread) == 2

        # Get messages after msg1
        unread = temp_slaick.get_unread_for_agent("a2", last_read_id=msg1["id"])
        assert len(unread) == 1
        assert unread[0]["id"] == msg3["id"]

    def test_count_messages(self, temp_slaick):
        """Test message counting."""
        assert temp_slaick.count_messages() == 0

        for i in range(5):
            temp_slaick.append_message("a1", "a2", MessageType.PROGRESS, {})

        assert temp_slaick.count_messages() == 5

    def test_message_timestamp_format(self, temp_slaick):
        """Test that timestamps are in correct ISO format."""
        from datetime import datetime

        msg = temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        timestamp = msg["timestamp"]

        # Should parse as ISO 8601
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_all_message_types(self, temp_slaick):
        """Test all supported message types."""
        types = [
            MessageType.HIRE,
            MessageType.CLAIM,
            MessageType.ACK,
            MessageType.PROGRESS,
            MessageType.COMPLETE,
            MessageType.ERROR,
        ]

        for msg_type in types:
            msg = temp_slaick.append_message("a1", "a2", msg_type, {})
            assert msg["type"] == msg_type.value


class TestSlaickFileFormat:
    """Test JSONL file format and integrity."""

    @pytest.fixture
    def temp_slaick(self):
        """Create a temporary Slaick instance."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name
        slaick = Slaick(temp_path)
        yield slaick
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_jsonl_format(self, temp_slaick):
        """Test that file is valid JSONL format."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {"test": True})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {"count": 42})

        with open(temp_slaick.file_path, "r") as f:
            lines = f.readlines()

        assert len(lines) == 2
        for line in lines:
            # Each line should be valid JSON
            data = json.loads(line.strip())
            assert "id" in data
            assert "timestamp" in data


class TestSlaickConcurrentOperations:
    """Test concurrent operations from multiple processes."""

    @pytest.fixture
    def temp_path(self):
        """Create a temporary file path for concurrent tests."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_two_processes_exchange_messages(self, temp_path):
        """Test that two processes can exchange messages and both see full thread."""

        def writer_process(file_path, agent_id, partner_id, message_count):
            """Process that writes messages and reads thread."""
            slaick = Slaick(file_path)
            written_ids = []

            for i in range(message_count):
                msg = slaick.append_message(
                    agent_id,
                    partner_id,
                    MessageType.PROGRESS,
                    {"from": agent_id, "seq": i},
                )
                written_ids.append(msg["id"])
                time.sleep(0.01)  # Small delay to interleave with other process

            # Read all messages after writing
            time.sleep(0.1)  # Wait for other process
            all_messages = slaick.get_messages()
            return {"written": written_ids, "total_read": len(all_messages)}

        # Start two processes that write to the same file
        with multiprocessing.Pool(2) as pool:
            results = [
                pool.apply_async(_writer_process, (temp_path, "agent-a", "agent-b", 5)),
                pool.apply_async(_writer_process, (temp_path, "agent-b", "agent-a", 5)),
            ]

            result_a = results[0].get(timeout=10)
            result_b = results[1].get(timeout=10)

        # Both processes should see all 10 messages
        assert result_a["total_read"] == 10
        assert result_b["total_read"] == 10

        # Each should have written 5 unique messages
        assert len(result_a["written"]) == 5
        assert len(result_b["written"]) == 5
        assert len(set(result_a["written"]) & set(result_b["written"])) == 0

    def test_concurrent_writes_no_corruption(self, temp_path):
        """Test that concurrent writes don't corrupt the JSONL file."""
        num_processes = 4
        messages_per_process = 25

        def write_messages(file_path, process_id, count):
            """Write messages from a process."""
            slaick = Slaick(file_path)
            for i in range(count):
                slaick.append_message(
                    f"proc-{process_id}",
                    "target",
                    MessageType.PROGRESS,
                    {"process": process_id, "msg": i},
                )
            return count

        # Launch multiple processes writing concurrently
        with multiprocessing.Pool(num_processes) as pool:
            results = [
                pool.apply_async(_write_messages, (temp_path, i, messages_per_process))
                for i in range(num_processes)
            ]

            for r in results:
                assert r.get(timeout=30) == messages_per_process

        # Verify file integrity
        slaick = Slaick(temp_path)
        messages = slaick.get_messages()

        # Should have all messages
        assert len(messages) == num_processes * messages_per_process

        # All messages should be valid with required fields
        for msg in messages:
            assert "id" in msg
            assert "timestamp" in msg
            assert "from" in msg
            assert "to" in msg
            assert "type" in msg
            assert "payload" in msg

        # Verify JSONL file is valid
        with open(temp_path, "r") as f:
            lines = f.readlines()

        # Each line should be valid JSON
        for line in lines:
            json.loads(line.strip())

    def test_concurrent_read_while_writing(self, temp_path):
        """Test reading while another process is writing."""

        def continuous_writer(file_path, message_count):
            """Continuously write messages."""
            slaick = Slaick(file_path)
            for i in range(message_count):
                slaick.append_message(
                    "writer", "reader", MessageType.PROGRESS, {"i": i}
                )
                time.sleep(0.005)
            return message_count

        def continuous_reader(file_path, check_count):
            """Continuously read messages."""
            slaick = Slaick(file_path)
            reads = []
            for _ in range(check_count):
                msgs = slaick.get_messages()
                reads.append(len(msgs))
                time.sleep(0.01)
            return reads

        # Writer writes 20 messages
        writer_result = multiprocessing.Process(
            target=_continuous_writer, args=(temp_path, 20)
        )
        writer_result.start()

        # Reader checks while writer is active
        slaick = Slaick(temp_path)
        read_counts = []
        for _ in range(30):
            msgs = slaick.get_messages()
            read_counts.append(len(msgs))
            time.sleep(0.01)

        writer_result.join(timeout=5)

        # Reader should have seen increasing message counts
        # (monotonically non-decreasing due to concurrent reads)
        assert read_counts[-1] >= read_counts[0]
        assert read_counts[-1] == 20  # Should see all messages eventually


class TestSlaickEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def temp_slaick(self):
        """Create a temporary Slaick instance."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name
        slaick = Slaick(temp_path)
        yield slaick
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_empty_file_handling(self, temp_slaick):
        """Test operations on empty file."""
        assert temp_slaick.count_messages() == 0
        assert temp_slaick.get_messages() == []
        assert temp_slaick.tail(10) == []
        assert temp_slaick.get_conversation("a1", "a2") == []

    def test_get_new_messages_not_found(self, temp_slaick):
        """Test get_new_messages with non-existent since_id."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a2", "a1", MessageType.ACK, {})

        # Non-existent since_id should return all messages
        result = temp_slaick.get_new_messages("non-existent")
        assert len(result) == 2

    def test_large_payload(self, temp_slaick):
        """Test handling of large payloads."""
        large_payload = {"data": "x" * 10000}
        msg = temp_slaick.append_message("a1", "a2", MessageType.HIRE, large_payload)

        retrieved = temp_slaick.get_message_by_id(msg["id"])
        assert retrieved["payload"]["data"] == large_payload["data"]

    def test_unicode_payload(self, temp_slaick):
        """Test handling of unicode characters."""
        unicode_payload = {"text": "Hello 世界 🌍 ñoño"}
        msg = temp_slaick.append_message("a1", "a2", MessageType.HIRE, unicode_payload)

        retrieved = temp_slaick.get_message_by_id(msg["id"])
        assert retrieved["payload"]["text"] == unicode_payload["text"]

    def test_nested_payload(self, temp_slaick):
        """Test deeply nested payloads."""
        nested_payload = {
            "level1": {"level2": {"level3": {"data": [1, 2, 3], "flag": True}}}
        }
        msg = temp_slaick.append_message("a1", "a2", MessageType.HIRE, nested_payload)

        retrieved = temp_slaick.get_message_by_id(msg["id"])
        assert retrieved["payload"] == nested_payload

    def test_multiple_filters(self, temp_slaick):
        """Test combining multiple filters."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})
        temp_slaick.append_message("a1", "a2", MessageType.ACK, {})
        temp_slaick.append_message("a2", "a1", MessageType.HIRE, {})
        temp_slaick.append_message("a1", "a3", MessageType.HIRE, {})

        # Multiple filters should AND together
        result = temp_slaick.get_messages(from_="a1", to="a2", msg_type="HIRE")
        assert len(result) == 1

    def test_tail_more_than_exists(self, temp_slaick):
        """Test tail when requesting more messages than exist."""
        temp_slaick.append_message("a1", "a2", MessageType.HIRE, {})

        result = temp_slaick.tail(100)
        assert len(result) == 1


class TestSlaickDefaultPath:
    """Test default file path behavior."""

    def test_default_path_is_slaick_jsonl(self, tmp_path):
        """Test that default path is slaick.jsonl in current directory."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            slaick = Slaick()
            assert slaick.file_path.name == "slaick.jsonl"
            assert slaick.file_path.exists()
        finally:
            os.chdir(original_cwd)

    def test_custom_path(self, tmp_path):
        """Test custom file path."""
        custom_path = tmp_path / "custom.jsonl"
        slaick = Slaick(custom_path)
        assert slaick.file_path == custom_path
        assert slaick.file_path.exists()
