"""
Tests for the Company Janitor specialization.

Tests cover:
- Janitor task detection (_is_janitor_task)
- Zombie agent detection and marking
- Bead reset to ready status
- Slaick notifications for cleanup actions
- File locking for atomic cleanup
- Concurrent safety (multiple janitors)
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.company.beads import Bead
from app.company.employee import Employee, EmployeeStatus
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
def janitor_jd():
    """Create a Janitor JobDescription for testing."""
    return JobDescription(
        role="Company Janitor",
        description="Clean up zombie agents and orphaned tasks",
        required_capabilities=["cleanup", "monitoring"],
        suggested_category="quick",
        cost_estimate=0.02,
        complexity=0.3,
    )


@pytest.fixture
def backend_jd():
    """Create a Backend Developer JobDescription for testing."""
    return JobDescription(
        role="Backend Developer",
        description="Build APIs and server-side functionality",
        required_capabilities=["api_design", "database_modeling"],
        suggested_category="deep",
        cost_estimate=0.08,
        complexity=0.6,
    )


@pytest.fixture
async def janitor_employee(temp_employees_file, temp_slaick_file, janitor_jd):
    """Create a Janitor Employee instance for testing."""
    emp = Employee(
        agent_id="janitor-test-001",
        job_description=janitor_jd,
        employees_file=temp_employees_file,
        slaick=Slaick(temp_slaick_file),
        heartbeat_interval=1,
        heartbeat_ttl=3,
    )
    yield emp
    if emp.is_running():
        await emp.shutdown()


@pytest.fixture
async def backend_employee(temp_employees_file, temp_slaick_file, backend_jd):
    """Create a Backend Developer Employee instance for testing."""
    emp = Employee(
        agent_id="backend-test-001",
        job_description=backend_jd,
        employees_file=temp_employees_file,
        slaick=Slaick(temp_slaick_file),
        heartbeat_interval=1,
        heartbeat_ttl=3,
    )
    yield emp
    if emp.is_running():
        await emp.shutdown()


class TestJanitorTaskDetection:
    """Tests for janitor task detection."""

    def test_is_janitor_task_with_cleanup_title(self, janitor_employee):
        """Test that cleanup tasks are detected as janitor tasks."""
        bead = Bead(
            id="bead-001",
            title="Cleanup zombie agents",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._is_janitor_task(bead) is True

    def test_is_janitor_task_with_zombie_title(self, janitor_employee):
        """Test that zombie tasks are detected as janitor tasks."""
        bead = Bead(
            id="bead-002",
            title="Remove zombie workers",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._is_janitor_task(bead) is True

    def test_is_janitor_task_with_janitor_title(self, janitor_employee):
        """Test that janitor tasks are detected."""
        bead = Bead(
            id="bead-003",
            title="Run janitor cleanup routine",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._is_janitor_task(bead) is True

    def test_is_janitor_task_with_orphan_title(self, janitor_employee):
        """Test that orphan tasks are detected as janitor tasks."""
        bead = Bead(
            id="bead-004",
            title="Clean up orphan tasks",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._is_janitor_task(bead) is True

    def test_is_janitor_task_with_regular_title(self, janitor_employee):
        """Test that regular tasks are NOT detected as janitor tasks."""
        bead = Bead(
            id="bead-005",
            title="Implement user authentication API",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._is_janitor_task(bead) is False


class TestJanitorSpecialization:
    """Tests for janitor specialization matching."""

    def test_janitor_can_do_cleanup_task(self, janitor_employee):
        """Test that janitor can handle cleanup tasks."""
        bead = Bead(
            id="bead-001",
            title="Cleanup zombie agents every 60s",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._can_do_task(bead) is True

    def test_janitor_cannot_do_backend_task(self, janitor_employee):
        """Test that janitor cannot handle backend tasks."""
        bead = Bead(
            id="bead-002",
            title="Implement user authentication API",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert janitor_employee._can_do_task(bead) is False

    def test_backend_cannot_do_janitor_task(self, backend_employee):
        """Test that backend developer cannot handle janitor tasks."""
        bead = Bead(
            id="bead-003",
            title="Cleanup zombie agents",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert backend_employee._can_do_task(bead) is False


class TestZombieDetection:
    """Tests for zombie agent detection."""

    def test_detect_expired_agent(self, temp_employees_file, janitor_employee):
        """Test that expired agents are detected as zombies."""
        # Create an expired agent record
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(seconds=60)  # Expired 60 seconds ago

        expired_agent = {
            "agent_id": "zombie-agent-001",
            "role": "Backend Developer",
            "status": "busy",
            "last_heartbeat": (expired_time - timedelta(seconds=30)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "expires_at": expired_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "current_bead_id": "bead-zombie-001",
        }

        with open(temp_employees_file, "w") as f:
            f.write(json.dumps(expired_agent) + "\n")

        # Run cleanup
        zombies_cleaned = janitor_employee._sync_cleanup_zombies()

        # Verify zombie was detected
        assert zombies_cleaned == 1

        # Verify agent was marked as zombie
        with open(temp_employees_file, "r") as f:
            records = [json.loads(line) for line in f if line.strip()]

        assert len(records) == 1
        assert records[0]["status"] == "zombie"
        assert records[0]["zombie_detected_by"] == "janitor-test-001"
        assert "zombie_detected_at" in records[0]

    def test_skip_valid_agent(self, temp_employees_file, janitor_employee):
        """Test that valid (non-expired) agents are not marked as zombies."""
        # Create a valid agent record
        now = datetime.now(timezone.utc)
        future_time = now + timedelta(seconds=30)  # Valid for 30 more seconds

        valid_agent = {
            "agent_id": "valid-agent-001",
            "role": "Backend Developer",
            "status": "busy",
            "last_heartbeat": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": future_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        with open(temp_employees_file, "w") as f:
            f.write(json.dumps(valid_agent) + "\n")

        # Run cleanup
        zombies_cleaned = janitor_employee._sync_cleanup_zombies()

        # Verify no zombies were cleaned
        assert zombies_cleaned == 0

        # Verify agent was NOT marked as zombie
        with open(temp_employees_file, "r") as f:
            records = [json.loads(line) for line in f if line.strip()]

        assert len(records) == 1
        assert records[0]["status"] == "busy"  # Still busy, not zombie

    def test_skip_already_zombie(self, temp_employees_file, janitor_employee):
        """Test that already marked zombies are skipped."""
        # Create an already-zombie agent record
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(seconds=60)

        zombie_agent = {
            "agent_id": "zombie-agent-002",
            "role": "Backend Developer",
            "status": "zombie",
            "last_heartbeat": (expired_time - timedelta(seconds=30)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "expires_at": expired_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zombie_detected_at": expired_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zombie_detected_by": "other-janitor",
        }

        with open(temp_employees_file, "w") as f:
            f.write(json.dumps(zombie_agent) + "\n")

        # Run cleanup
        zombies_cleaned = janitor_employee._sync_cleanup_zombies()

        # Verify no new zombies were cleaned (already marked)
        assert zombies_cleaned == 0


class TestBeadReset:
    """Tests for resetting beads to ready status."""

    @patch("subprocess.run")
    def test_reset_bead_to_ready(self, mock_run, janitor_employee):
        """Test that bead reset calls bd command correctly."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        janitor_employee._reset_bead_to_ready("bead-001")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "bd" in args
        assert "update" in args
        assert "bead-001" in args
        assert "ready" in args

    @patch("subprocess.run")
    def test_reset_bead_failure_raises(self, mock_run, janitor_employee):
        """Test that bead reset failure raises an exception."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Bead not found"
        )

        with pytest.raises(Exception) as exc_info:
            janitor_employee._reset_bead_to_ready("bead-002")

        assert "bd update failed" in str(exc_info.value)


class TestSlaickNotifications:
    """Tests for Slaick cleanup notifications."""

    def test_zombie_cleanup_message(self, temp_slaick_file, janitor_employee):
        """Test that cleanup sends Slaick message."""
        janitor_employee._send_zombie_cleanup_message("zombie-001", "bead-001")

        # Verify message was written
        with open(temp_slaick_file, "r") as f:
            messages = [json.loads(line) for line in f if line.strip()]

        assert len(messages) == 1
        msg = messages[0]
        assert msg["from"] == "janitor-test-001"
        assert msg["to"] == "orchestrator"
        assert msg["type"] == "PROGRESS"
        assert msg["payload"]["zombie_agent_id"] == "zombie-001"
        assert msg["payload"]["bead_id"] == "bead-001"
        assert "Cleaned up zombie zombie-001" in msg["payload"]["message"]


class TestJanitorRoutine:
    """Tests for the full janitor routine."""

    @pytest.mark.asyncio
    @patch.object(Employee, "_sync_cleanup_zombies")
    @patch.object(Employee, "_update_bead_status_done")
    async def test_janitor_routine_execution(
        self, mock_update_done, mock_cleanup, janitor_employee
    ):
        """Test that janitor routine runs successfully."""
        mock_cleanup.return_value = 2  # Cleaned 2 zombies
        mock_update_done.return_value = True

        bead = Bead(
            id="bead-janitor-001",
            title="Cleanup zombie agents",
            status="in_progress",
            priority=1,
            issue_type="task",
            owner="janitor-test-001",
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )

        # Execute the routine
        await janitor_employee._janitor_routine(bead)

        # Verify cleanup was called
        mock_cleanup.assert_called_once()

        # Verify bead status was updated to done
        mock_update_done.assert_called_once_with("bead-janitor-001")

        # Verify status returned to idle
        assert janitor_employee.status == EmployeeStatus.IDLE


class TestConcurrentSafety:
    """Tests for concurrent cleanup safety."""

    def test_multiple_janitors_safe_cleanup(
        self, temp_employees_file, temp_slaick_file
    ):
        """Test that multiple janitors can run cleanup safely with file locking."""
        # Create an expired agent
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(seconds=60)

        expired_agent = {
            "agent_id": "zombie-agent-003",
            "role": "Backend Developer",
            "status": "busy",
            "last_heartbeat": (expired_time - timedelta(seconds=30)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "expires_at": expired_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        with open(temp_employees_file, "w") as f:
            f.write(json.dumps(expired_agent) + "\n")

        # Create two janitor employees
        janitor1 = Employee(
            agent_id="janitor-001",
            job_description=JobDescription(
                role="Company Janitor",
                description="Cleanup",
                required_capabilities=[],
                suggested_category="quick",
                cost_estimate=0.02,
                complexity=0.3,
            ),
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        janitor2 = Employee(
            agent_id="janitor-002",
            job_description=JobDescription(
                role="Company Janitor",
                description="Cleanup",
                required_capabilities=[],
                suggested_category="quick",
                cost_estimate=0.02,
                complexity=0.3,
            ),
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        # Run cleanup from both janitors
        cleaned1 = janitor1._sync_cleanup_zombies()
        cleaned2 = janitor2._sync_cleanup_zombies()

        # Only one janitor should have cleaned the zombie
        assert cleaned1 + cleaned2 == 1

        # Verify agent is marked as zombie
        with open(temp_employees_file, "r") as f:
            records = [json.loads(line) for line in f if line.strip()]

        assert len(records) == 1
        assert records[0]["status"] == "zombie"


class TestExecuteTaskDelegation:
    """Tests for janitor task delegation in execute_task."""

    @pytest.mark.asyncio
    @patch.object(Employee, "_janitor_routine")
    async def test_execute_task_delegates_to_janitor_routine(
        self, mock_janitor_routine, janitor_employee
    ):
        """Test that janitor tasks are delegated to _janitor_routine."""
        bead = Bead(
            id="bead-cleanup-001",
            title="Cleanup zombie agents",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )

        await janitor_employee.execute_task(bead)

        # Verify _janitor_routine was called
        mock_janitor_routine.assert_called_once_with(bead)

    @pytest.mark.asyncio
    @patch.object(Employee, "_janitor_routine")
    @patch.object(Employee, "_update_bead_status_done")
    async def test_execute_task_regular_task_not_delegated(
        self, mock_update_done, mock_janitor_routine, backend_employee
    ):
        """Test that regular tasks are NOT delegated to _janitor_routine."""
        mock_update_done.return_value = True

        bead = Bead(
            id="bead-regular-001",
            title="Implement user authentication",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )

        await backend_employee.execute_task(bead)

        # Verify _janitor_routine was NOT called
        mock_janitor_routine.assert_not_called()

        # Verify regular execution happened (bead status updated)
        mock_update_done.assert_called_once()


class TestEmployeeStatusZombie:
    """Tests for the ZOMBIE status enum."""

    def test_zombie_status_exists(self):
        """Test that ZOMBIE status is defined in EmployeeStatus."""
        assert hasattr(EmployeeStatus, "ZOMBIE")
        assert EmployeeStatus.ZOMBIE.value == "zombie"

    def test_zombie_status_in_enum_values(self):
        """Test that ZOMBIE is in the list of status values."""
        statuses = [status.value for status in EmployeeStatus]
        assert "zombie" in statuses
