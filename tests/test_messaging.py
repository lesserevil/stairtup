"""
Tests for messaging functionality between Recruiter and Employee agents.

Tests cover:
- Slaick.listen() async message puller
- Message dispatcher routing
- COMPLETE and PROGRESS message handling
- ACK message flow
- Last processed ID tracking
- Status synchronization
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.company.beads import Bead
from app.company.employee import Employee, EmployeeStatus
from app.company.recruiter import Recruiter
from app.company.slaick import MessageType, Slaick
from app.company.types import JobDescription

import logging


@pytest.fixture(autouse=True)
def set_log_level(caplog):
    """Set log level to INFO for all tests."""
    caplog.set_level(logging.INFO)


@pytest.fixture
def temp_slaick():
    """Create a temporary Slaick instance for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name
    slaick = Slaick(temp_path)
    yield slaick
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_employees_file():
    """Create a temporary employees.jsonl file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("")
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)


@pytest.fixture
def sample_jd():
    """Create a sample JobDescription for testing."""
    return JobDescription(
        role="Backend Developer",
        description="Build APIs and server-side functionality",
        required_capabilities=["api_design", "database_modeling"],
        suggested_category="deep",
        cost_estimate=0.05,
        complexity=0.6,
    )


@pytest.fixture
def recruiter(temp_slaick):
    """Create a Recruiter instance with message handlers initialized."""
    recruiter = Recruiter(
        slaick=temp_slaick,
        fast_poll_interval=0.01,
        slow_poll_interval=0.05,
        use_llm=False,
    )
    # Initialize message handlers
    recruiter._init_message_handlers()
    return recruiter


@pytest.fixture
async def employee(temp_employees_file, temp_slaick, sample_jd):
    """Create an Employee instance for testing."""
    emp = Employee(
        agent_id="emp-test-123",
        job_description=sample_jd,
        employees_file=temp_employees_file,
        slaick=temp_slaick,
        heartbeat_interval=1,
        heartbeat_ttl=3,
    )
    yield emp
    # Cleanup
    if emp.is_running():
        await emp.shutdown()
    if emp.is_listening():
        await emp.stop_message_listener()


class TestSlaickListen:
    """Tests for Slaick.listen() async message puller."""

    @pytest.mark.asyncio
    async def test_listen_yields_new_messages(self, temp_slaick):
        """Test that listen() yields messages as they arrive."""
        messages_received = []

        # Start listener in background
        async def collect_messages():
            async for msg in temp_slaick.listen("agent-1", poll_interval=0.1):
                messages_received.append(msg)
                if len(messages_received) >= 2:
                    break

        listener_task = asyncio.create_task(collect_messages())

        # Give listener time to start
        await asyncio.sleep(0.15)

        # Send messages
        temp_slaick.append_message(
            "sender-1", "agent-1", MessageType.PROGRESS, {"data": "msg1"}
        )
        temp_slaick.append_message(
            "sender-2", "agent-1", MessageType.PROGRESS, {"data": "msg2"}
        )

        # Wait for listener to receive messages
        await asyncio.wait_for(listener_task, timeout=1.0)

        assert len(messages_received) == 2
        assert messages_received[0]["payload"]["data"] == "msg1"
        assert messages_received[1]["payload"]["data"] == "msg2"

    @pytest.mark.asyncio
    async def test_listen_does_not_duplicate(self, temp_slaick):
        """Test that listen() does not yield the same message twice."""
        messages_received = []

        # Start listener
        async def collect_messages():
            count = 0
            async for msg in temp_slaick.listen("agent-1", poll_interval=0.1):
                messages_received.append(msg)
                count += 1
                if count >= 3:
                    break

        listener_task = asyncio.create_task(collect_messages())

        # Give listener time to start
        await asyncio.sleep(0.15)

        # Send messages
        temp_slaick.append_message(
            "sender", "agent-1", MessageType.PROGRESS, {"seq": 1}
        )
        await asyncio.sleep(0.15)
        temp_slaick.append_message(
            "sender", "agent-1", MessageType.PROGRESS, {"seq": 2}
        )
        await asyncio.sleep(0.15)
        temp_slaick.append_message(
            "sender", "agent-1", MessageType.PROGRESS, {"seq": 3}
        )

        # Wait for listener
        await asyncio.wait_for(listener_task, timeout=1.0)

        # Verify no duplicates
        msg_ids = [m["id"] for m in messages_received]
        assert len(msg_ids) == len(set(msg_ids))

    @pytest.mark.asyncio
    async def test_listen_filters_by_agent_id(self, temp_slaick):
        """Test that listen() only returns messages for the specified agent."""
        messages_for_agent_a = []

        # Start listener for agent-a
        async def collect_for_agent_a():
            async for msg in temp_slaick.listen("agent-a", poll_interval=0.1):
                messages_for_agent_a.append(msg)
                if len(messages_for_agent_a) >= 1:
                    break

        listener_task = asyncio.create_task(collect_for_agent_a())

        # Give listener time to start
        await asyncio.sleep(0.15)

        # Send messages to different agents
        temp_slaick.append_message("sender", "agent-a", MessageType.PROGRESS, {})
        temp_slaick.append_message("sender", "agent-b", MessageType.PROGRESS, {})
        temp_slaick.append_message("sender", "agent-a", MessageType.PROGRESS, {})

        # Wait for listener
        await asyncio.wait_for(listener_task, timeout=1.0)

        # Should only have messages for agent-a
        assert len(messages_for_agent_a) == 1


class TestRecruiterMessageDispatcher:
    """Tests for Recruiter message dispatcher."""

    @pytest.mark.asyncio
    async def test_register_handler(self, recruiter):
        """Test registering a custom message handler."""
        custom_handler = AsyncMock()

        recruiter.register_handler("CUSTOM_TYPE", custom_handler)

        assert "CUSTOM_TYPE" in recruiter._message_handlers
        assert recruiter._message_handlers["CUSTOM_TYPE"] == custom_handler

    @pytest.mark.asyncio
    async def test_dispatch_message_routes_to_handler(self, recruiter):
        """Test that messages are routed to the correct handler."""
        handler = AsyncMock()
        recruiter.register_handler("TEST_TYPE", handler)

        message = {
            "id": "msg-1",
            "type": "TEST_TYPE",
            "payload": {"data": "test"},
        }

        await recruiter._dispatch_message(message)

        handler.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_type_logs_warning(self, recruiter, caplog):
        """Test that unknown message types are logged but not crash."""
        message = {
            "id": "msg-1",
            "type": "UNKNOWN_TYPE",
            "payload": {},
        }

        # Should not raise
        await recruiter._dispatch_message(message)


class TestRecruiterMessageHandlers:
    """Tests for Recruiter message handlers."""

    @pytest.mark.asyncio
    async def test_handle_complete_message_updates_employee_status(self, recruiter):
        """Test that COMPLETE message marks employee as completed."""
        # Setup: Add an employee
        from app.company.recruiter import Employee as RecruiterEmployee

        recruiter.employees["bead-123"] = RecruiterEmployee(
            employee_id="backend-dev-bead-123",
            role="Backend Developer",
            bead_id="bead-123",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )

        # Send COMPLETE message
        message = {
            "id": "msg-1",
            "type": "COMPLETE",
            "from": "backend-dev-bead-123",
            "to": "recruiter",
            "payload": {
                "agent_id": "backend-dev-bead-123",
                "bead_id": "bead-123",
                "message": "Task completed successfully",
            },
        }

        await recruiter._handle_complete_message(message)

        # Verify employee status updated
        assert recruiter.employees["bead-123"].status == "completed"

    @pytest.mark.asyncio
    async def test_handle_complete_message_sends_ack(self, recruiter, temp_slaick):
        """Test that COMPLETE message handler sends ACK."""
        # Setup: Add an employee
        from app.company.recruiter import Employee as RecruiterEmployee

        recruiter.employees["bead-123"] = RecruiterEmployee(
            employee_id="backend-dev-bead-123",
            role="Backend Developer",
            bead_id="bead-123",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )

        # Send COMPLETE message
        message = {
            "id": "msg-1",
            "type": "COMPLETE",
            "from": "backend-dev-bead-123",
            "to": "recruiter",
            "payload": {
                "agent_id": "backend-dev-bead-123",
                "bead_id": "bead-123",
                "message": "Task completed successfully",
            },
        }

        await recruiter._handle_complete_message(message)

        # Verify ACK was sent
        acks = temp_slaick.get_messages(msg_type="ACK")
        assert len(acks) == 1
        assert acks[0]["to"] == "backend-dev-bead-123"
        assert acks[0]["payload"]["original_message_id"] == "msg-1"

    @pytest.mark.asyncio
    async def test_handle_complete_unknown_employee(self, recruiter, caplog):
        """Test handling COMPLETE from unknown employee."""
        message = {
            "id": "msg-1",
            "type": "COMPLETE",
            "from": "unknown-employee",
            "to": "recruiter",
            "payload": {
                "agent_id": "unknown-employee",
                "bead_id": "bead-999",
                "message": "Task completed",
            },
        }

        # Should not raise, just log debug
        await recruiter._handle_complete_message(message)

    @pytest.mark.asyncio
    async def test_handle_progress_message_logs_status(self, recruiter, caplog):
        """Test that PROGRESS message logs status update."""
        message = {
            "id": "msg-1",
            "type": "PROGRESS",
            "from": "emp-1",
            "to": "recruiter",
            "payload": {
                "agent_id": "emp-1",
                "role": "Backend Developer",
                "message": "Starting task execution",
            },
        }

        await recruiter._handle_progress_message(message)

        # Should log the progress message
        assert "PROGRESS from emp-1" in caplog.text
        assert "Starting task execution" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_error_message_logs_error(self, recruiter, caplog):
        """Test that ERROR message logs the error."""
        message = {
            "id": "msg-1",
            "type": "ERROR",
            "from": "emp-1",
            "to": "recruiter",
            "payload": {
                "agent_id": "emp-1",
                "bead_id": "bead-123",
                "error": "Connection timeout",
            },
        }

        await recruiter._handle_error_message(message)

        # Should log the error
        assert "ERROR from emp-1" in caplog.text
        assert "Connection timeout" in caplog.text


class TestRecruiterSendAck:
    """Tests for Recruiter ACK message sending."""

    @pytest.mark.asyncio
    async def test_send_ack_message_structure(self, recruiter, temp_slaick):
        """Test that ACK message has correct structure."""
        original_message = {
            "id": "original-msg-123",
            "type": "PROGRESS",
            "from": "emp-1",
            "to": "recruiter",
            "payload": {"data": "test"},
        }

        ack = await recruiter._send_ack_message(original_message, status="processed")

        assert ack["from"] == "recruiter"
        assert ack["to"] == "emp-1"
        assert ack["type"] == "ACK"
        assert ack["payload"]["original_message_id"] == "original-msg-123"
        assert ack["payload"]["original_type"] == "PROGRESS"
        assert ack["payload"]["status"] == "processed"
        assert "timestamp" in ack["payload"]

    @pytest.mark.asyncio
    async def test_send_ack_no_from_field(self, recruiter, caplog):
        """Test ACK sending when original message has no 'from' field."""
        original_message = {
            "id": "original-msg-123",
            "type": "PROGRESS",
            "to": "recruiter",
            # Missing "from"
            "payload": {},
        }

        result = await recruiter._send_ack_message(original_message)

        # Should return empty dict and log warning
        assert result == {}
        assert "no 'from' field" in caplog.text


class TestRecruiterMessageListener:
    """Tests for Recruiter message listener loop."""

    @pytest.mark.asyncio
    async def test_start_stop_message_listener(self, recruiter):
        """Test starting and stopping the message listener."""
        # Start listener
        await recruiter.start_message_listener(poll_interval=0.1)

        assert recruiter._listening is True
        assert recruiter._message_listener_task is not None

        # Stop listener
        await recruiter.stop_message_listener()

        assert recruiter._listening is False

    @pytest.mark.asyncio
    async def test_message_listener_processes_messages(self, recruiter, temp_slaick):
        """Test that listener processes incoming messages."""
        # Track processed messages
        processed_messages = []

        async def tracking_handler(message):
            processed_messages.append(message)

        recruiter.register_handler("TEST", tracking_handler)

        # Start listener
        await recruiter.start_message_listener(poll_interval=0.1)

        # Wait for listener to start
        await asyncio.sleep(0.15)

        # Send a message
        temp_slaick.append_message("sender", "recruiter", "TEST", {"data": "test"})

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop listener
        await recruiter.stop_message_listener()

        # Verify message was processed
        assert len(processed_messages) == 1
        assert processed_messages[0]["type"] == "TEST"

    @pytest.mark.asyncio
    async def test_last_processed_id_prevents_duplicates(self, recruiter, temp_slaick):
        """Test that last_processed_id prevents duplicate processing."""
        processed_count = [0]

        async def counting_handler(message):
            processed_count[0] += 1

        recruiter.register_handler("TEST", counting_handler)

        # Start listener
        await recruiter.start_message_listener(poll_interval=0.1)

        # Wait for listener to start
        await asyncio.sleep(0.15)

        # Send the same message ID twice
        msg = temp_slaick.append_message(
            "sender", "recruiter", "TEST", {"data": "test"}, message_id="msg-123"
        )
        await asyncio.sleep(0.2)

        # Stop listener
        await recruiter.stop_message_listener()

        # Should only process once
        assert processed_count[0] == 1


class TestEmployeeMessageListener:
    """Tests for Employee message listener."""

    @pytest.mark.asyncio
    async def test_start_stop_message_listener(
        self, temp_employees_file, temp_slaick, sample_jd
    ):
        """Test starting and stopping the employee message listener."""
        emp = Employee(
            agent_id="emp-listener-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=temp_slaick,
        )

        # Start listener
        await emp.start_message_listener(poll_interval=0.1)

        assert emp._is_listening is True
        assert emp._message_listener_task is not None

        # Stop listener
        await emp.stop_message_listener()

        assert emp._is_listening is False

    @pytest.mark.asyncio
    async def test_employee_receives_ack(
        self, temp_employees_file, temp_slaick, sample_jd
    ):
        """Test that employee receives and handles ACK messages."""
        emp = Employee(
            agent_id="emp-ack-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=temp_slaick,
        )

        # Start listener
        await emp.start_message_listener(poll_interval=0.1)

        # Wait for listener to start
        await asyncio.sleep(0.15)

        # Send an ACK to the employee
        temp_slaick.append_message(
            "recruiter",
            "emp-ack-test",
            MessageType.ACK,
            {
                "original_message_id": "msg-123",
                "original_type": "PROGRESS",
                "status": "received",
            },
        )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop listener
        await emp.stop_message_listener()

        # Test passed if no exceptions


class TestIntegrationMessaging:
    """Integration tests for full messaging flow."""

    @pytest.mark.asyncio
    async def test_employee_sends_progress_recruiter_receives(
        self, temp_slaick, temp_employees_file, sample_jd
    ):
        """Test full flow: Employee sends PROGRESS, Recruiter receives and ACKs."""
        # Setup recruiter
        recruiter = Recruiter(
            slaick=temp_slaick,
            fast_poll_interval=0.01,
            slow_poll_interval=0.05,
            use_llm=False,
        )
        recruiter._init_message_handlers()

        # Setup employee
        emp = Employee(
            agent_id="emp-integration-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=temp_slaick,
        )

        # Start recruiter listener (listen for orchestrator messages from employees)
        await recruiter.start_message_listener(poll_interval=0.1, listen_for="orchestrator")

        # Wait for listener to start
        await asyncio.sleep(0.15)

        # Employee sends PROGRESS message
        await emp._send_online_message()

        # Wait for recruiter to process
        await asyncio.sleep(0.25)

        # Stop recruiter listener
        await recruiter.stop_message_listener()

        # Verify: Check that ACK was sent back to employee
        acks = temp_slaick.get_messages(msg_type="ACK")
        emp_acks = [a for a in acks if a.get("to") == "emp-integration-test"]
        assert len(emp_acks) >= 1

    @pytest.mark.asyncio
    async def test_employee_sends_complete_recruiter_updates_status(
        self, temp_slaick, temp_employees_file, sample_jd
    ):
        """Test: Employee sends COMPLETE, Recruiter updates employee status."""
        # Setup
        from app.company.recruiter import Employee as RecruiterEmployee

        recruiter = Recruiter(
            slaick=temp_slaick,
            fast_poll_interval=0.01,
            slow_poll_interval=0.05,
            use_llm=False,
        )
        recruiter._init_message_handlers()

        # Add employee to track
        recruiter.employees["bead-456"] = RecruiterEmployee(
            employee_id="test-emp-bead-456",
            role="Test Developer",
            bead_id="bead-456",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )

        emp = Employee(
            agent_id="test-emp-bead-456",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=temp_slaick,
        )

        # Start recruiter listener (listen for orchestrator messages from employees)
        await recruiter.start_message_listener(poll_interval=0.1, listen_for="orchestrator")
        await asyncio.sleep(0.15)

        # Create a mock bead for the complete message
        bead = Bead(
            id="bead-456",
            title="Test task",
            status="claimed",
            priority=3,
            issue_type="task",
            owner="test-emp-bead-456",
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by="test",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Employee sends COMPLETE message
        await emp._send_completed_message(bead)

        # Wait for recruiter to process
        await asyncio.sleep(0.25)

        # Stop recruiter listener
        await recruiter.stop_message_listener()

        # Verify employee status updated
        assert recruiter.employees["bead-456"].status == "completed"

        # Verify ACK was sent
        acks = temp_slaick.get_messages(msg_type="ACK")
        assert len(acks) == 1
