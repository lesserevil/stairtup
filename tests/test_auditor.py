"""
Tests for the Company Auditor specialization.

Tests cover:
- Auditor task detection (_is_auditor_task)
- Cost efficiency analysis and outlier detection
- AUDIT recommendation posting to Slaick
- Auditor specialization matching
- High-cost outlier identification
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
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
def auditor_jd():
    """Create an Auditor JobDescription for testing."""
    return JobDescription(
        role="Internal Auditor",
        description="Analyze cost efficiency and identify high-cost outliers",
        required_capabilities=["cost_analysis", "efficiency_tracking"],
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
async def auditor_employee(temp_employees_file, temp_slaick_file, auditor_jd):
    """Create an Auditor Employee instance for testing."""
    emp = Employee(
        agent_id="auditor-test-001",
        job_description=auditor_jd,
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


class TestAuditorTaskDetection:
    """Tests for auditor task detection."""

    def test_is_auditor_task_with_audit_title(self, auditor_employee):
        """Test that audit tasks are detected as auditor tasks."""
        bead = Bead(
            id="bead-001",
            title="Audit cost efficiency",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._is_auditor_task(bead) is True

    def test_is_auditor_task_with_cost_analysis_title(self, auditor_employee):
        """Test that cost analysis tasks are detected as auditor tasks."""
        bead = Bead(
            id="bead-002",
            title="Perform cost analysis",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._is_auditor_task(bead) is True

    def test_is_auditor_task_with_efficiency_review_title(self, auditor_employee):
        """Test that efficiency review tasks are detected."""
        bead = Bead(
            id="bead-003",
            title="Run efficiency review",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._is_auditor_task(bead) is True

    def test_is_auditor_task_with_performance_audit_title(self, auditor_employee):
        """Test that performance audit tasks are detected as auditor tasks."""
        bead = Bead(
            id="bead-004",
            title="Performance audit",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._is_auditor_task(bead) is True

    def test_is_auditor_task_with_regular_title(self, auditor_employee):
        """Test that regular tasks are NOT detected as auditor tasks."""
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
        assert auditor_employee._is_auditor_task(bead) is False


class TestAuditorSpecialization:
    """Tests for auditor specialization matching."""

    def test_auditor_can_do_audit_task(self, auditor_employee):
        """Test that auditor can handle audit tasks."""
        bead = Bead(
            id="bead-001",
            title="Audit cost efficiency",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._can_do_task(bead) is True

    def test_auditor_can_do_cost_analysis_task(self, auditor_employee):
        """Test that auditor can handle cost analysis tasks."""
        bead = Bead(
            id="bead-002",
            title="Cost analysis of operations",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert auditor_employee._can_do_task(bead) is True

    def test_auditor_cannot_do_backend_task(self, auditor_employee):
        """Test that auditor cannot handle backend tasks."""
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
        assert auditor_employee._can_do_task(bead) is False

    def test_backend_cannot_do_auditor_task(self, backend_employee):
        """Test that backend developer cannot handle auditor tasks."""
        bead = Bead(
            id="bead-003",
            title="Audit cost efficiency",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )
        assert backend_employee._can_do_task(bead) is False


class TestCostOutlierDetection:
    """Tests for cost outlier detection."""

    def test_detect_high_cost_outlier(self, temp_slaick_file, auditor_employee):
        """Test that high-cost outliers are detected (>2x median)."""
        # Create a temporary operations file with cost data
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as ops_file:
            # Write 5 entries with normal costs
            for i in range(5):
                entry = {
                    "timestamp": "2026-02-21T10:00:00Z",
                    "operation": "spawn",
                    "cost": 0.05,
                    "agent_id": f"agent-{i}",
                    "category": "quick",
                }
                ops_file.write(json.dumps(entry) + "\n")

            # Write 1 entry with high cost (outlier - 3x normal)
            outlier_entry = {
                "timestamp": "2026-02-21T10:05:00Z",
                "operation": "spawn",
                "cost": 0.15,
                "agent_id": "ultrabrain-agent",
                "category": "quick",
            }
            ops_file.write(json.dumps(outlier_entry) + "\n")
            ops_path = ops_file.name

        try:
            # Run the analysis
            result = auditor_employee._sync_analyze_costs(ops_path)

            # Verify outliers were detected
            assert len(result["outliers"]) >= 1

            # Find the ultrabrain outlier
            ultrabrain_outlier = None
            for outlier in result["outliers"]:
                if outlier["agent_id"] == "ultrabrain-agent":
                    ultrabrain_outlier = outlier
                    break

            assert ultrabrain_outlier is not None
            assert ultrabrain_outlier["cost"] == 0.15
            assert ultrabrain_outlier["median_cost"] == 0.05
            assert ultrabrain_outlier["category"] == "quick"
            assert "efficiency_score" in ultrabrain_outlier
            assert "recommendation" in ultrabrain_outlier

        finally:
            os.unlink(ops_path)

    def test_no_outliers_with_normal_costs(self, auditor_employee):
        """Test that no outliers are detected when costs are normal."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as ops_file:
            # Write 5 entries with similar costs
            for i in range(5):
                entry = {
                    "timestamp": "2026-02-21T10:00:00Z",
                    "operation": "spawn",
                    "cost": 0.05,
                    "agent_id": f"agent-{i}",
                    "category": "quick",
                }
                ops_file.write(json.dumps(entry) + "\n")
            ops_path = ops_file.name

        try:
            result = auditor_employee._sync_analyze_costs(ops_path)

            # No outliers should be detected
            assert len(result["outliers"]) == 0
            assert result["total_costs"]["quick"] == 0.25

        finally:
            os.unlink(ops_path)

    def test_efficiency_score_calculation(self, auditor_employee):
        """Test that efficiency scores are calculated correctly."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as ops_file:
            # Normal entries
            for i in range(3):
                entry = {
                    "timestamp": "2026-02-21T10:00:00Z",
                    "operation": "spawn",
                    "cost": 0.04,
                    "agent_id": f"agent-{i}",
                    "category": "deep",
                }
                ops_file.write(json.dumps(entry) + "\n")

            # High-cost outlier
            outlier_entry = {
                "timestamp": "2026-02-21T10:05:00Z",
                "operation": "spawn",
                "cost": 0.12,
                "agent_id": "expensive-agent",
                "category": "deep",
            }
            ops_file.write(json.dumps(outlier_entry) + "\n")
            ops_path = ops_file.name

        try:
            result = auditor_employee._sync_analyze_costs(ops_path)

            assert len(result["outliers"]) == 1
            outlier = result["outliers"][0]

            # Efficiency score = median / cost = 0.04 / 0.12 = 0.33
            assert outlier["efficiency_score"] == 0.33

        finally:
            os.unlink(ops_path)


class TestRecommendationGeneration:
    """Tests for recommendation generation."""

    def test_recommendation_for_ultrabrain_category(self, auditor_employee):
        """Test recommendations for ultrabrain category."""
        rec = auditor_employee._generate_recommendation("ultrabrain", 0.15, 0.05)

        assert "downgrading" in rec.lower()
        assert "$0.150" in rec
        assert "$0.050" in rec
        assert "3.0x" in rec or "3x" in rec

    def test_recommendation_for_high_ratio(self, auditor_employee):
        """Test recommendations for high-cost ratio (>3x)."""
        rec = auditor_employee._generate_recommendation("deep", 0.15, 0.04)

        assert "High-cost outlier" in rec or "task batching" in rec.lower()
        assert "$0.150" in rec or "$0.15" in rec
        assert "$0.040" in rec or "$0.04" in rec

    def test_recommendation_for_moderate_ratio(self, auditor_employee):
        """Test recommendations for moderate cost ratio."""
        rec = auditor_employee._generate_recommendation("quick", 0.09, 0.04)

        assert "Review resource allocation" in rec
        assert "$0.090" in rec or "$0.09" in rec
        assert "$0.040" in rec or "$0.04" in rec


class TestAuditSlaickNotifications:
    """Tests for Slaick audit recommendations."""

    def test_audit_recommendation_message(self, temp_slaick_file, auditor_employee):
        """Test that audit recommendation sends proper Slaick message."""
        outlier = {
            "category": "ultrabrain",
            "agent_id": "ultrabrain-001",
            "cost": 0.15,
            "median_cost": 0.05,
            "efficiency_score": 0.33,
            "recommendation": "Consider downgrading from ultrabrain to 'deep'",
        }

        auditor_employee._send_audit_recommendation(outlier)

        # Verify message was written
        with open(temp_slaick_file, "r") as f:
            messages = [json.loads(line) for line in f if line.strip()]

        assert len(messages) == 1
        msg = messages[0]
        assert msg["from"] == "auditor-test-001"
        assert msg["to"] == "recruiter"
        assert msg["type"] == "AUDIT"
        assert msg["payload"]["type"] == "AUDIT"
        assert msg["payload"]["category"] == "ultrabrain"
        assert msg["payload"]["target_agent"] == "ultrabrain-001"
        assert msg["payload"]["cost"] == 0.15
        assert msg["payload"]["median_cost"] == 0.05
        assert msg["payload"]["efficiency_score"] == 0.33
        assert "AUDIT:" in msg["payload"]["message"]


class TestAuditorRoutine:
    """Tests for the full auditor routine."""

    @pytest.mark.asyncio
    @patch.object(Employee, "_update_bead_status_done")
    async def test_auditor_routine_execution(self, mock_update_done, auditor_employee):
        """Test that auditor routine runs successfully."""
        # Create a temporary operations file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as ops_file:
            for i in range(5):
                entry = {
                    "timestamp": "2026-02-21T10:00:00Z",
                    "operation": "spawn",
                    "cost": 0.05,
                    "agent_id": f"agent-{i}",
                    "category": "quick",
                }
                ops_file.write(json.dumps(entry) + "\n")

            outlier_entry = {
                "timestamp": "2026-02-21T10:05:00Z",
                "operation": "spawn",
                "cost": 0.15,
                "agent_id": "ultrabrain-agent",
                "category": "quick",
            }
            ops_file.write(json.dumps(outlier_entry) + "\n")
            ops_path = ops_file.name

        mock_update_done.return_value = True

        bead = Bead(
            id="bead-audit-001",
            title="Audit cost efficiency",
            status="in_progress",
            priority=1,
            issue_type="task",
            owner="auditor-test-001",
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )

        try:
            # Execute the routine
            await auditor_employee._auditor_routine(bead, ops_path)

            # Verify bead status was updated to done
            mock_update_done.assert_called_once_with("bead-audit-001")

            # Verify status returned to idle
            assert auditor_employee.status == EmployeeStatus.IDLE

        finally:
            os.unlink(ops_path)


class TestExecuteTaskDelegation:
    """Tests for auditor task delegation in execute_task."""

    @pytest.mark.asyncio
    @patch.object(Employee, "_auditor_routine")
    async def test_execute_task_delegates_to_auditor_routine(
        self, mock_auditor_routine, auditor_employee
    ):
        """Test that auditor tasks are delegated to _auditor_routine."""
        bead = Bead(
            id="bead-audit-001",
            title="Audit cost efficiency",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T00:00:00Z",
            created_by="test",
            updated_at="2026-02-21T00:00:00Z",
        )

        await auditor_employee.execute_task(bead)

        # Verify _auditor_routine was called
        mock_auditor_routine.assert_called_once()
        # Verify it was called with the bead
        call_args = mock_auditor_routine.call_args
        assert call_args[0][0].id == "bead-audit-001"

    @pytest.mark.asyncio
    @patch.object(Employee, "_auditor_routine")
    @patch.object(Employee, "_update_bead_status_done")
    async def test_execute_task_regular_task_not_delegated(
        self, mock_update_done, mock_auditor_routine, backend_employee
    ):
        """Test that regular tasks are NOT delegated to _auditor_routine."""
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

        # Verify _auditor_routine was NOT called
        mock_auditor_routine.assert_not_called()

        # Verify regular execution happened (bead status updated)
        mock_update_done.assert_called_once()


class TestMessageTypeAudit:
    """Tests for the AUDIT message type."""

    def test_audit_message_type_exists(self):
        """Test that AUDIT message type is defined in MessageType."""
        assert hasattr(MessageType, "AUDIT")
        assert MessageType.AUDIT.value == "AUDIT"

    def test_audit_message_type_in_enum_values(self):
        """Test that AUDIT is in the list of message type values."""
        message_types = [mt.value for mt in MessageType]
        assert "AUDIT" in message_types
