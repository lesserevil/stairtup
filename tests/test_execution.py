"""
Tests for Work Stealing and Task Execution.

Tests cover:
- Specialization matching (can_do_task)
- Work polling and claiming (poll_for_work)
- Task execution lifecycle (execute_task)
- Full work stealing loop
- Slaick message verification
- Status transitions (Idle -> Busy -> Idle)
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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
def backend_jd():
    """Create a Backend Developer JobDescription for testing."""
    return JobDescription(
        role="Backend Developer",
        description="Build APIs and server-side functionality",
        required_capabilities=["api_design", "database_modeling", "business_logic"],
        suggested_category="deep",
        cost_estimate=0.08,
        complexity=0.6,
    )


@pytest.fixture
def frontend_jd():
    """Create a Frontend Developer JobDescription for testing."""
    return JobDescription(
        role="Frontend Developer",
        description="Build UI components and frontend functionality",
        required_capabilities=["react", "css", "ui_design"],
        suggested_category="deep",
        cost_estimate=0.08,
        complexity=0.6,
    )


class TestSpecializationMatching:
    """Tests for the _can_do_task specialization matching."""

    def test_backend_developer_matches_backend_task(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that Backend Developer can do backend tasks."""
        emp = Employee(
            agent_id="backend-1",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        backend_bead = Bead(
            id="bead-1",
            title="Fix API authentication bug",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        assert emp._can_do_task(backend_bead) is True

    def test_backend_developer_ignores_frontend_task(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that Backend Developer ignores frontend tasks."""
        emp = Employee(
            agent_id="backend-2",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        frontend_bead = Bead(
            id="bead-2",
            title="Fix CSS styling issue",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        assert emp._can_do_task(frontend_bead) is False

    def test_frontend_developer_matches_frontend_task(
        self, temp_employees_file, temp_slaick_file, frontend_jd
    ):
        """Test that Frontend Developer can do frontend tasks."""
        emp = Employee(
            agent_id="frontend-1",
            job_description=frontend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        frontend_bead = Bead(
            id="bead-3",
            title="Update React component",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        assert emp._can_do_task(frontend_bead) is True

    def test_frontend_developer_ignores_backend_task(
        self, temp_employees_file, temp_slaick_file, frontend_jd
    ):
        """Test that Frontend Developer ignores backend tasks."""
        emp = Employee(
            agent_id="frontend-2",
            job_description=frontend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        backend_bead = Bead(
            id="bead-4",
            title="Update database schema",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        assert emp._can_do_task(backend_bead) is False

    def test_generic_role_accepts_all_tasks(
        self, temp_employees_file, temp_slaick_file
    ):
        """Test that generic roles accept all tasks."""
        generic_jd = JobDescription(
            role="Generic Developer",
            description="Can do anything",
            required_capabilities=[],
            suggested_category="deep",
            cost_estimate=0.08,
            complexity=0.6,
        )

        emp = Employee(
            agent_id="generic-1",
            job_description=generic_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        backend_bead = Bead(
            id="bead-5",
            title="Fix API authentication bug",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        frontend_bead = Bead(
            id="bead-6",
            title="Fix CSS styling issue",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        assert emp._can_do_task(backend_bead) is True
        assert emp._can_do_task(frontend_bead) is True

    def test_backend_keywords_match_variations(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that backend keywords match various backend task titles."""
        emp = Employee(
            agent_id="backend-3",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        test_cases = [
            ("API", True),
            ("Database", True),
            ("DB", True),
            ("Python", True),
            ("Backend", True),
            ("Server", True),
        ]

        for keyword, expected in test_cases:
            bead = Bead(
                id=f"bead-{keyword}",
                title=f"Task involving {keyword}",
                status="ready",
                priority=2,
                issue_type="task",
                owner=None,
                created_at="2026-02-21T10:00:00Z",
                created_by="Test",
                updated_at="2026-02-21T10:00:00Z",
            )
            assert emp._can_do_task(bead) == expected, f"Failed for keyword: {keyword}"

    def test_frontend_keywords_match_variations(
        self, temp_employees_file, temp_slaick_file, frontend_jd
    ):
        """Test that frontend keywords match various frontend task titles."""
        emp = Employee(
            agent_id="frontend-3",
            job_description=frontend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        test_cases = [
            ("CSS", True),
            ("HTML", True),
            ("React", True),
            ("UI", True),
            ("UX", True),
            ("Frontend", True),
        ]

        for keyword, expected in test_cases:
            bead = Bead(
                id=f"bead-{keyword}",
                title=f"Task involving {keyword}",
                status="ready",
                priority=2,
                issue_type="task",
                owner=None,
                created_at="2026-02-21T10:00:00Z",
                created_by="Test",
                updated_at="2026-02-21T10:00:00Z",
            )
            assert emp._can_do_task(bead) == expected, f"Failed for keyword: {keyword}"


class TestPollForWork:
    """Tests for the poll_for_work method."""

    @pytest.mark.asyncio
    async def test_poll_returns_none_when_busy(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that poll_for_work returns None when status is BUSY."""
        emp = Employee(
            agent_id="busy-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        await emp.set_status(EmployeeStatus.BUSY)

        result = await emp.poll_for_work()
        assert result is None

    @pytest.mark.asyncio
    async def test_poll_claims_matching_bead(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that poll_for_work claims a matching bead."""
        emp = Employee(
            agent_id="claim-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        backend_bead = Bead(
            id="bead-api-1",
            title="Fix API authentication bug",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch("app.company.employee.get_ready_beads", return_value=[backend_bead]):
            with patch(
                "app.company.employee.claim_bead_async", return_value=True
            ) as mock_claim:
                result = await emp.poll_for_work()

                assert result is not None
                assert result.id == "bead-api-1"
                mock_claim.assert_called_once_with("bead-api-1", "claim-emp")

    @pytest.mark.asyncio
    async def test_poll_skips_non_matching_beads(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that poll_for_work skips beads that don't match specialization."""
        emp = Employee(
            agent_id="skip-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        frontend_bead = Bead(
            id="bead-css-1",
            title="Fix CSS styling issue",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch(
            "app.company.employee.get_ready_beads", return_value=[frontend_bead]
        ):
            with patch("app.company.employee.claim_bead_async") as mock_claim:
                result = await emp.poll_for_work()

                assert result is None
                mock_claim.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_returns_none_when_no_beads_available(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that poll_for_work returns None when no beads are available."""
        emp = Employee(
            agent_id="no-work-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        with patch("app.company.employee.get_ready_beads", return_value=[]):
            result = await emp.poll_for_work()
            assert result is None

    @pytest.mark.asyncio
    async def test_poll_handles_claim_failure(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that poll_for_work handles when another agent claims the bead first."""
        emp = Employee(
            agent_id="fail-claim-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
        )

        backend_bead = Bead(
            id="bead-api-2",
            title="Fix API authentication bug",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch("app.company.employee.get_ready_beads", return_value=[backend_bead]):
            with patch(
                "app.company.employee.claim_bead_async", return_value=False
            ) as mock_claim:
                result = await emp.poll_for_work()

                assert result is None
                mock_claim.assert_called_once_with("bead-api-2", "fail-claim-emp")


class TestTaskExecution:
    """Tests for the execute_task method and status transitions."""

    @pytest.mark.asyncio
    async def test_execute_task_transitions_status(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that execute_task properly transitions status: Idle -> Busy -> Idle."""
        emp = Employee(
            agent_id="exec-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            task_execution_time=0.1,  # Fast execution for testing
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "exec-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        assert emp.status == EmployeeStatus.IDLE

        bead = Bead(
            id="bead-exec-1",
            title="Fix API bug",
            status="in_progress",
            priority=2,
            issue_type="task",
            owner="exec-emp",
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch.object(emp, "_update_bead_status_done", return_value=True):
            await emp.execute_task(bead)

        # Status should be back to IDLE after execution
        assert emp.status == EmployeeStatus.IDLE
        assert emp.get_current_bead() is None

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_execute_task_sends_slaick_messages(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that execute_task sends CLAIM and COMPLETE messages to Slaick."""
        emp = Employee(
            agent_id="slaick-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            task_execution_time=0.1,  # Fast execution for testing
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "slaick-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        bead = Bead(
            id="bead-slaick-1",
            title="Fix API bug",
            status="in_progress",
            priority=2,
            issue_type="task",
            owner="slaick-emp",
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch.object(emp, "_update_bead_status_done", return_value=True):
            await emp.execute_task(bead)

        # Verify Slaick messages
        with open(temp_slaick_file, "r") as f:
            messages = [json.loads(line) for line in f if line.strip()]

        # Find CLAIM message
        claim_messages = [m for m in messages if m.get("type") == "CLAIM"]
        assert len(claim_messages) == 1
        assert claim_messages[0]["payload"]["bead_id"] == "bead-slaick-1"

        # Find COMPLETE message
        complete_messages = [m for m in messages if m.get("type") == "COMPLETE"]
        assert len(complete_messages) == 1
        assert complete_messages[0]["payload"]["bead_id"] == "bead-slaick-1"

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_execute_task_updates_bead_status(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that execute_task updates bead status to 'done'."""
        emp = Employee(
            agent_id="update-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            task_execution_time=0.1,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "update-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        bead = Bead(
            id="bead-update-1",
            title="Fix API bug",
            status="in_progress",
            priority=2,
            issue_type="task",
            owner="update-emp",
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        update_mock = Mock(return_value=True)
        with patch.object(emp, "_update_bead_status_done", update_mock):
            await emp.execute_task(bead)

        # Verify bead status was updated
        update_mock.assert_called_once_with("bead-update-1")

        await emp.shutdown()


class TestWorkStealingLoop:
    """Tests for the full work stealing loop."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_idle_to_busy_to_idle(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test the full lifecycle: Idle -> Busy -> Idle."""
        emp = Employee(
            agent_id="lifecycle-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            poll_interval=0.1,
            task_execution_time=0.1,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "lifecycle-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Verify initial status
        assert emp.status == EmployeeStatus.IDLE

        # Manually execute a task to test lifecycle
        bead = Bead(
            id="bead-lifecycle-1",
            title="Fix API bug",
            status="in_progress",
            priority=2,
            issue_type="task",
            owner="lifecycle-emp",
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch.object(emp, "_update_bead_status_done", return_value=True):
            await emp.execute_task(bead)

        # Verify back to IDLE
        assert emp.status == EmployeeStatus.IDLE

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_work_stealing_loop_starts_with_employee(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that work stealing loop starts automatically with employee."""
        emp = Employee(
            agent_id="auto-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            poll_interval=0.1,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "auto-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Give it a moment to start
        await asyncio.sleep(0.05)

        # Verify work stealing task is running
        assert emp._work_stealing_task is not None
        assert not emp._work_stealing_task.done()

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_work_stealing_loop_stops_on_shutdown(
        self, temp_employees_file, temp_slaick_file, backend_jd
    ):
        """Test that work stealing loop stops on shutdown."""
        emp = Employee(
            agent_id="stop-emp",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            poll_interval=0.1,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "stop-emp",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()
        await asyncio.sleep(0.05)

        # Shutdown
        await emp.shutdown()

        # Verify work stealing task is done
        assert emp._work_stealing_task is None or emp._work_stealing_task.done()


class TestIntegration:
    """Integration tests for work stealing with the full system."""

    @pytest.mark.asyncio
    async def test_backend_agent_claims_backend_task_ignores_frontend(
        self, temp_employees_file, temp_slaick_file
    ):
        """Integration test: Backend agent claims backend task and ignores frontend task."""
        backend_jd = JobDescription(
            role="Backend Developer",
            description="Build APIs",
            required_capabilities=["api_design"],
            suggested_category="deep",
            cost_estimate=0.08,
            complexity=0.6,
        )

        emp = Employee(
            agent_id="integration-backend",
            job_description=backend_jd,
            employees_file=temp_employees_file,
            slaick=Slaick(temp_slaick_file),
            poll_interval=0.1,
            task_execution_time=0.1,
        )

        # Write initial record
        with open(temp_employees_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "agent_id": "integration-backend",
                        "role": "Backend Developer",
                        "status": "active",
                    }
                )
                + "\n"
            )

        await emp.start()

        # Create beads
        backend_bead = Bead(
            id="bead-backend-task",
            title="Implement Python API endpoint",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        frontend_bead = Bead(
            id="bead-frontend-task",
            title="Fix CSS styling",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="Test",
            updated_at="2026-02-21T10:00:00Z",
        )

        # Poll should claim backend but not frontend
        with patch(
            "app.company.employee.get_ready_beads",
            return_value=[frontend_bead, backend_bead],
        ):
            with patch("app.company.employee.claim_bead_async") as mock_claim:
                # First call claims backend_bead, second should not be called for frontend
                mock_claim.side_effect = [True]  # Only backend claim succeeds

                result = await emp.poll_for_work()

                # Should have claimed the backend bead
                assert result is not None
                assert result.id == "bead-backend-task"

                # Verify claim_bead_async was called only once (for backend)
                assert (
                    mock_claim.call_count == 1
                )  # Only called for backend since frontend doesn't match specialization

        await emp.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_agents_race_condition(self, temp_slaick_file):
        """Test that only one agent can claim a bead in a race condition."""
        backend_jd = JobDescription(
            role="Backend Developer",
            description="Build APIs",
            required_capabilities=["api_design"],
            suggested_category="deep",
            cost_estimate=0.08,
            complexity=0.6,
        )

        # Create two employees
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as shared_file:
            shared_path = shared_file.name
            shared_file.write("")

        try:
            emp1 = Employee(
                agent_id="race-agent-1",
                job_description=backend_jd,
                employees_file=shared_path,
                slaick=Slaick(temp_slaick_file),
                poll_interval=0.1,
            )

            emp2 = Employee(
                agent_id="race-agent-2",
                job_description=backend_jd,
                employees_file=shared_path,
                slaick=Slaick(temp_slaick_file),
                poll_interval=0.1,
            )

            # Write initial records
            with open(shared_path, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "agent_id": "race-agent-1",
                            "role": "Backend Developer",
                            "status": "active",
                        }
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "agent_id": "race-agent-2",
                            "role": "Backend Developer",
                            "status": "active",
                        }
                    )
                    + "\n"
                )

            bead = Bead(
                id="race-bead",
                title="Fix Python API bug",
                status="ready",
                priority=2,
                issue_type="task",
                owner=None,
                created_at="2026-02-21T10:00:00Z",
                created_by="Test",
                updated_at="2026-02-21T10:00:00Z",
            )

            # Simulate race: both try to claim, only one succeeds
            claim_count = [0]

            def mock_claim(bead_id, agent_id):
                claim_count[0] += 1
                # First caller wins
                return claim_count[0] == 1

            with patch("app.company.employee.get_ready_beads", return_value=[bead]):
                with patch(
                    "app.company.employee.claim_bead_async", side_effect=mock_claim
                ):
                    # Both poll simultaneously
                    result1, result2 = await asyncio.gather(
                        emp1.poll_for_work(),
                        emp2.poll_for_work(),
                    )

                    # Only one should succeed
                    successes = sum(1 for r in [result1, result2] if r is not None)
                    assert successes == 1, f"Expected 1 success, got {successes}"

        finally:
            os.unlink(shared_path)
