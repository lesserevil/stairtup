"""
Tests for the Employee Base Runtime.

Tests cover:
- Initialization with JD and agent_id
- Heartbeat loop updates to registry
- Status transitions and immediate registry updates
- Graceful shutdown (marks status as 'offline')
- Concurrent safety (multiple agents updating registry)
"""

import asyncio
import json
import multiprocessing
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.company.employee import Employee, EmployeeStatus, employee_runtime
from app.company.slaick import MessageType, Slaick
from app.company.types import JobDescription


@pytest.fixture
def temp_employees_file():
    """Create a temporary employees.jsonl file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("")
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)


@pytest.fixture
def temp_slaick_file():
    """Create a temporary slaick.jsonl file for testing."""
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
        required_capabilities=["api_design", "database_modeling", "business_logic"],
        suggested_category="deep",
        cost_estimate=0.08,
        complexity=0.6,
    )


@pytest.fixture
async def employee(temp_employees_file, temp_slaick_file, sample_jd):
    """Create an Employee instance for testing."""
    emp = Employee(
        agent_id="emp-test-123",
        job_description=sample_jd,
        employees_file=temp_employees_file,
        slaick=Slaick(temp_slaick_file),
        heartbeat_interval=1,  # Fast heartbeat for testing
        heartbeat_ttl=3,
    )
    yield emp
    # Cleanup
    if emp.is_running():
        await emp.shutdown()


class TestEmployeeInitialization:
    """Tests for Employee initialization and basic properties."""

    def test_employee_initialization(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that Employee correctly stores agent_id and JobDescription on initialization."""
        agent_id = "emp-init-test"

        emp = Employee(
            agent_id=agent_id,
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        assert emp.agent_id == agent_id
        assert emp.job_description == sample_jd
        assert emp.job_description.role == "Backend Developer"
        assert emp.job_description.required_capabilities == [
            "api_design",
            "database_modeling",
            "business_logic",
        ]
        assert emp.status == EmployeeStatus.IDLE
        assert not emp.is_running()

    def test_employee_default_values(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that Employee uses default values when optional parameters are omitted."""
        emp = Employee(
            agent_id="emp-default-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        assert emp.heartbeat_interval == 10
        assert emp.heartbeat_ttl == 30

    def test_employee_custom_heartbeat_values(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that Employee accepts custom heartbeat configuration."""
        emp = Employee(
            agent_id="emp-custom-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=5,
            heartbeat_ttl=15,
        )

        assert emp.heartbeat_interval == 5
        assert emp.heartbeat_ttl == 15


class TestHeartbeatMechanism:
    """Tests for the heartbeat loop and registry updates."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_updates_registry(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that the heartbeat loop runs and updates the timestamp in employees.jsonl."""
        emp = Employee(
            agent_id="emp-hb-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        # Write initial record (as spawner would)
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-hb-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        # Start employee
        await emp.start()
        assert emp.is_running()

        # Wait for at least one heartbeat
        await asyncio.sleep(1.5)

        # Shutdown
        await emp.shutdown()

        # Verify heartbeat was written
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        record = lines[0]
        assert record["agent_id"] == "emp-hb-test"
        assert "last_heartbeat" in record
        assert "expires_at" in record
        assert record["status"] == "offline"  # Shutdown sets this

        # Verify timestamps are valid ISO format
        last_hb = datetime.fromisoformat(
            record["last_heartbeat"].replace("Z", "+00:00")
        )
        expires_at = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        assert expires_at > last_hb

    @pytest.mark.asyncio
    async def test_multiple_heartbeat_updates(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that multiple heartbeat updates occur over time."""
        emp = Employee(
            agent_id="emp-multi-hb",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=0.5,
            heartbeat_ttl=2,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-multi-hb",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Wait for multiple heartbeats
        await asyncio.sleep(2.5)

        await emp.shutdown()

        # Verify record exists with updated timestamps
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        assert lines[0]["agent_id"] == "emp-multi-hb"
        assert "last_heartbeat" in lines[0]

    @pytest.mark.asyncio
    async def test_heartbeat_creates_missing_record(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that heartbeat creates a record if agent_id is not found."""
        emp = Employee(
            agent_id="emp-orphan",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        # No initial record - file is empty

        await emp.start()
        await asyncio.sleep(1.5)
        await emp.shutdown()

        # Verify record was created
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        record = lines[0]
        assert record["agent_id"] == "emp-orphan"
        assert record["role"] == "Backend Developer"
        assert "last_heartbeat" in record
        assert "expires_at" in record

    @pytest.mark.asyncio
    async def test_heartbeat_includes_expires_at(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that heartbeat includes expires_at timestamp 30s from now."""
        emp = Employee(
            agent_id="emp-expires-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=30,  # 30 seconds TTL
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-expires-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        await asyncio.sleep(1.5)
        await emp.shutdown()

        # Verify expires_at is set correctly
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        record = lines[0]
        last_hb = datetime.fromisoformat(
            record["last_heartbeat"].replace("Z", "+00:00")
        )
        expires_at = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))

        # Should be approximately 30 seconds apart
        diff = (expires_at - last_hb).total_seconds()
        assert 29 <= diff <= 31  # Allow 1 second tolerance


class TestStatusTransitions:
    """Tests for status transitions and immediate registry updates."""

    @pytest.mark.asyncio
    async def test_status_transitions_update_registry(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that status changes trigger immediate heartbeat updates."""
        emp = Employee(
            agent_id="emp-status-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=10,  # Long interval - status change should trigger immediate update
            heartbeat_ttl=30,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-status-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Change status to busy
        await emp.set_status(EmployeeStatus.BUSY)

        # Immediately check registry - should show busy without waiting for heartbeat interval
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert lines[0]["status"] == "busy"

        # Change status back to idle
        await emp.set_status(EmployeeStatus.IDLE)

        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert lines[0]["status"] == "idle"

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_status_idle_to_busy_transition(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test transition from idle to busy (when taking tasks)."""
        emp = Employee(
            agent_id="emp-work-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-work-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        assert emp.status == EmployeeStatus.IDLE

        # Simulate taking a task
        await emp.set_status(EmployeeStatus.BUSY)
        assert emp.status == EmployeeStatus.BUSY

        # Verify registry updated
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert lines[0]["status"] == "busy"

        # Simulate task completion
        await emp.set_status(EmployeeStatus.IDLE)
        assert emp.status == EmployeeStatus.IDLE

        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert lines[0]["status"] == "idle"

        await emp.shutdown()


class TestGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown_marks_offline(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that shutdown marks the agent status as 'offline'."""
        emp = Employee(
            agent_id="emp-shutdown-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-shutdown-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        await asyncio.sleep(1)

        # Verify running status
        assert emp.is_running()
        assert emp.status != EmployeeStatus.OFFLINE

        # Shutdown
        await emp.shutdown()

        # Verify stopped
        assert not emp.is_running()
        assert emp.status == EmployeeStatus.OFFLINE

        # Verify registry shows offline
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        assert lines[0]["status"] == "offline"
        assert lines[0]["agent_id"] == "emp-shutdown-test"

    @pytest.mark.asyncio
    async def test_shutdown_stops_heartbeat_loop(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that shutdown stops the heartbeat background task."""
        emp = Employee(
            agent_id="emp-stop-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=0.5,
            heartbeat_ttl=1,
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-stop-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        await asyncio.sleep(1)

        # Shutdown
        await emp.shutdown()

        # Wait a bit and verify no more heartbeats are written
        initial_mtime = os.path.getmtime(temp_employees_file)
        await asyncio.sleep(2)
        final_mtime = os.path.getmtime(temp_employees_file)

        # File should not have been modified after shutdown
        assert final_mtime == initial_mtime or (
            final_mtime - initial_mtime < 0.1
        )  # Allow tiny variance

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that calling shutdown multiple times is safe."""
        emp = Employee(
            agent_id="emp-idempotent-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-idempotent-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        await asyncio.sleep(0.5)

        # Shutdown multiple times
        await emp.shutdown()
        await emp.shutdown()
        await emp.shutdown()

        # Should be fine
        assert not emp.is_running()
        assert emp.status == EmployeeStatus.OFFLINE


class TestConcurrentSafety:
    """Tests for concurrent safety with multiple agents."""

    @pytest.mark.asyncio
    async def test_multiple_employees_concurrent_updates(
        self, temp_slaick_file, sample_jd
    ):
        """Test that multiple Employee instances can update the registry without corruption."""
        # Create a shared employees file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            shared_file = f.name
            f.write("")

        try:
            # Create multiple employees
            employees = []
            for i in range(5):
                emp = Employee(
                    agent_id=f"emp-concurrent-{i}",
                    job_description=sample_jd,
                    employees_file=shared_file,
                    slaick=Slaick(temp_slaick_file),
                    heartbeat_interval=0.5,
                    heartbeat_ttl=2,
                )
                employees.append(emp)

            # Write initial records
            with open(shared_file, "w") as f:
                for i in range(5):
                    f.write(
                        json.dumps(
                            {
                                "agent_id": f"emp-concurrent-{i}",
                                "role": "Backend Developer",
                                "status": "active",
                            }
                        )
                        + "\n"
                    )

            # Start all employees
            for emp in employees:
                await emp.start()

            # Let them all heartbeat concurrently
            await asyncio.sleep(2)

            # Shutdown all
            for emp in employees:
                await emp.shutdown()

            # Verify all records are intact and uncorrupted
            with open(shared_file, "r") as f:
                lines = [line.strip() for line in f if line.strip()]

            # Should have 5 records (one per employee)
            assert len(lines) == 5

            # Verify each record is valid JSON and has required fields
            agent_ids_found = set()
            for line in lines:
                record = json.loads(line)
                assert "agent_id" in record
                assert "last_heartbeat" in record
                assert "expires_at" in record
                assert "status" in record
                assert record["status"] == "offline"
                agent_ids_found.add(record["agent_id"])

            # All 5 employees should be present
            expected_ids = {f"emp-concurrent-{i}" for i in range(5)}
            assert agent_ids_found == expected_ids

        finally:
            os.unlink(shared_file)

    @pytest.mark.asyncio
    async def test_concurrent_status_changes(self, temp_slaick_file, sample_jd):
        """Test concurrent status changes don't corrupt the registry."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            shared_file = f.name
            f.write("")

        try:
            emp1 = Employee(
                agent_id="emp-race-1",
                job_description=sample_jd,
                employees_file=shared_file,
                slaick=Slaick(temp_slaick_file),
                heartbeat_interval=1,
                heartbeat_ttl=3,
            )

            emp2 = Employee(
                agent_id="emp-race-2",
                job_description=sample_jd,
                employees_file=shared_file,
                slaick=Slaick(temp_slaick_file),
                heartbeat_interval=1,
                heartbeat_ttl=3,
            )

            # Write initial records
            with open(shared_file, "w") as f:
                f.write(
                    json.dumps(
                        {"agent_id": "emp-race-1", "role": "Dev", "status": "active"}
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {"agent_id": "emp-race-2", "role": "Dev", "status": "active"}
                    )
                    + "\n"
                )

            await emp1.start()
            await emp2.start()

            # Concurrent status changes
            await asyncio.gather(
                emp1.set_status(EmployeeStatus.BUSY),
                emp2.set_status(EmployeeStatus.BUSY),
            )

            # Verify both changes persisted
            with open(shared_file, "r") as f:
                lines = [json.loads(line) for line in f if line.strip()]

            assert len(lines) == 2
            statuses = {line["agent_id"]: line["status"] for line in lines}
            assert statuses["emp-race-1"] == "busy"
            assert statuses["emp-race-2"] == "busy"

            await emp1.shutdown()
            await emp2.shutdown()

        finally:
            os.unlink(shared_file)

    def test_sync_atomic_update_preserves_other_records(self, sample_jd):
        """Test that _sync_atomic_update doesn't overwrite other agents' data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_file = f.name
            f.write("")

        try:
            # Write existing records for other agents
            with open(temp_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "agent_id": "emp-other-1",
                            "role": "Dev",
                            "status": "active",
                            "last_heartbeat": "2026-01-01T00:00:00Z",
                        }
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "agent_id": "emp-other-2",
                            "role": "Dev",
                            "status": "busy",
                            "last_heartbeat": "2026-01-01T00:00:00Z",
                        }
                    )
                    + "\n"
                )

            # Create employee that updates its record
            emp = Employee(
                agent_id="emp-target",
                job_description=sample_jd,
                employees_file=temp_file,
            )

            # Write initial record for this employee
            with open(temp_file, "a") as f:
                f.write(
                    json.dumps(
                        {"agent_id": "emp-target", "role": "Dev", "status": "active"}
                    )
                    + "\n"
                )

            # Update heartbeat
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    emp._atomic_update_registry(
                        {
                            "agent_id": "emp-target",
                            "last_heartbeat": "2026-02-21T19:30:00Z",
                            "expires_at": "2026-02-21T19:30:30Z",
                            "status": "idle",
                        }
                    )
                )
            finally:
                loop.close()

            # Verify all records are preserved
            with open(temp_file, "r") as f:
                lines = [json.loads(line) for line in f if line.strip()]

            assert len(lines) == 3

            agent_data = {line["agent_id"]: line for line in lines}

            # Target employee updated
            assert agent_data["emp-target"]["status"] == "idle"
            assert agent_data["emp-target"]["last_heartbeat"] == "2026-02-21T19:30:00Z"
            assert agent_data["emp-target"]["expires_at"] == "2026-02-21T19:30:30Z"

            # Other employees unchanged
            assert agent_data["emp-other-1"]["status"] == "active"
            assert agent_data["emp-other-1"]["last_heartbeat"] == "2026-01-01T00:00:00Z"
            assert agent_data["emp-other-2"]["status"] == "busy"
            assert agent_data["emp-other-2"]["last_heartbeat"] == "2026-01-01T00:00:00Z"

        finally:
            os.unlink(temp_file)


class TestContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that context manager properly starts and shutdowns employee."""
        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-ctx-test",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        async with employee_runtime(
            agent_id="emp-ctx-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        ) as emp:
            # Inside context - employee should be running
            assert emp.is_running()
            assert emp.agent_id == "emp-ctx-test"

        # Outside context - employee should be shutdown
        assert not emp.is_running()
        assert emp.status == EmployeeStatus.OFFLINE

        # Verify registry shows offline
        with open(temp_employees_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert lines[0]["status"] == "offline"


class TestSlaickIntegration:
    """Tests for Slaick messaging integration."""

    @pytest.mark.asyncio
    async def test_online_message_sent_on_startup(
        self, temp_employees_file, temp_slaick_file, sample_jd
    ):
        """Test that 'Agent Online' message is sent on startup."""
        emp = Employee(
            agent_id="emp-online-msg",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            heartbeat_interval=1,
            heartbeat_ttl=3,
        )

        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "emp-online-msg",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Give message time to be written
        await asyncio.sleep(0.5)

        # Verify message was sent
        with open(temp_slaick_file, "r") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        online_messages = [
            line
            for line in lines
            if line.get("payload", {}).get("message") == "Agent Online"
        ]

        assert len(online_messages) == 1
        assert online_messages[0]["from"] == "emp-online-msg"
        assert online_messages[0]["to"] == "orchestrator"
        assert online_messages[0]["type"] == "PROGRESS"
        assert online_messages[0]["payload"]["role"] == "Backend Developer"

        await emp.shutdown()


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_get_heartbeat_info(self, temp_employees_file, temp_slaick_file, sample_jd):
        """Test that get_heartbeat_info returns correct structure."""
        emp = Employee(
            agent_id="emp-info-test",
            job_description=sample_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        info = emp.get_heartbeat_info()

        assert info["agent_id"] == "emp-info-test"
        assert info["status"] == "idle"
        assert "last_heartbeat" in info
        assert "expires_at" in info

        # Verify timestamps are valid
        last_hb = datetime.fromisoformat(info["last_heartbeat"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(info["expires_at"].replace("Z", "+00:00"))
        assert expires_at > last_hb
