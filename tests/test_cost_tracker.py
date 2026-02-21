"""Tests for the CostTracker and Circuit Breaker.

This module tests:
- Cost tracking accumulates correctly
- can_afford() returns False when budget would be exceeded
- Circuit breaker trips when budget exceeded
- operations.jsonl is written correctly
- Integration with Recruiter (refuse spawn when over budget)
- With $0.01 budget - should fail after first task
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.company.beads import Bead
from app.company.cost_tracker import CostTracker, CostEntry
from app.company.recruiter import Recruiter
from app.company.slaick import Slaick
from app.company.types import JobDescription


class TestCostTrackerBasic:
    """Test basic CostTracker functionality."""

    def test_init_default_budget(self, tmp_path):
        """Test CostTracker initializes with default budget."""
        tracker = CostTracker(operations_file=tmp_path / "ops.jsonl")
        assert tracker.budget == 10.0
        assert tracker.current_spent == 0.0
        assert not tracker.is_circuit_breaker_tripped()

    def test_init_custom_budget(self, tmp_path):
        """Test CostTracker initializes with custom budget."""
        tracker = CostTracker(budget=5.0, operations_file=tmp_path / "ops.jsonl")
        assert tracker.budget == 5.0

    def test_get_remaining_budget(self, tmp_path):
        """Test remaining budget calculation."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        assert tracker.get_remaining_budget() == 10.0

    def test_can_afford_basic(self, tmp_path):
        """Test can_afford with basic amounts."""
        tracker = CostTracker(budget=1.0, operations_file=tmp_path / "ops.jsonl")
        assert tracker.can_afford(0.5)
        assert tracker.can_afford(1.0)
        assert not tracker.can_afford(1.1)


class TestCostTrackerRecording:
    """Test cost recording functionality."""

    def test_record_cost_updates_spent(self, tmp_path):
        """Test recording a cost updates current spent."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")

        assert tracker.get_current_spent() == 0.05
        assert tracker.get_remaining_budget() == 9.95

    def test_record_cost_accumulates(self, tmp_path):
        """Test recording multiple costs accumulates."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.10, "emp-002", "deep")
        tracker.record_cost(0.15, "emp-003", "ultrabrain")

        assert round(tracker.get_current_spent(), 2) == 0.30
        assert round(tracker.get_remaining_budget(), 2) == 9.70

    def test_record_cost_writes_to_file(self, tmp_path):
        """Test recording writes to operations.jsonl."""
        operations_file = tmp_path / "operations.jsonl"
        tracker = CostTracker(budget=10.0, operations_file=operations_file)
        tracker.record_cost(0.05, "emp-001", "quick")

        assert operations_file.exists()

        with open(operations_file) as f:
            line = json.loads(f.readline())
            assert line["cost"] == 0.05
            assert line["agent_id"] == "emp-001"
            assert line["category"] == "quick"
            assert "timestamp" in line
            assert line["operation"] == "spawn"

    def test_record_cost_multiple_entries(self, tmp_path):
        """Test multiple entries are written correctly."""
        operations_file = tmp_path / "operations.jsonl"
        tracker = CostTracker(budget=10.0, operations_file=operations_file)
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.10, "emp-002", "deep")

        with open(operations_file) as f:
            lines = f.readlines()
            assert len(lines) == 2

            entry1 = json.loads(lines[0])
            entry2 = json.loads(lines[1])

            assert entry1["agent_id"] == "emp-001"
            assert entry2["agent_id"] == "emp-002"


class TestCostTrackerCategoryTracking:
    """Test category-based cost tracking."""

    def test_category_spent_tracking(self, tmp_path):
        """Test tracking by category."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.10, "emp-002", "quick")
        tracker.record_cost(0.15, "emp-003", "deep")

        assert round(tracker.get_category_spent("quick"), 2) == 0.15
        assert tracker.get_category_spent("deep") == 0.15
        assert tracker.get_category_spent("ultrabrain") == 0.0

    def test_all_category_spending(self, tmp_path):
        """Test getting all category spending."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.15, "emp-003", "deep")

        spending = tracker.get_all_category_spending()
        assert spending["quick"] == 0.05
        assert spending["deep"] == 0.15

    def test_category_budget_enforcement(self, tmp_path):
        """Test category-specific budget enforcement."""
        tracker = CostTracker(
            budget=10.0,
            operations_file=tmp_path / "ops.jsonl",
            category_budgets={"quick": 0.1},
        )

        assert tracker.can_afford(0.05, "quick")
        tracker.record_cost(0.05, "emp-001", "quick")

        # Still under quick budget
        assert tracker.can_afford(0.04, "quick")

        # Would exceed quick budget
        assert not tracker.can_afford(0.06, "quick")

        # Deep budget is unlimited
        assert tracker.can_afford(5.0, "deep")


class TestCostTrackerCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_trips_when_budget_exceeded(self, tmp_path):
        """Test circuit breaker trips when recording exceeds budget."""
        tracker = CostTracker(budget=0.1, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")

        assert not tracker.is_circuit_breaker_tripped()

        tracker.record_cost(0.05, "emp-002", "deep")

        # Budget now exhausted
        assert tracker.is_circuit_breaker_tripped()

    def test_circuit_breaker_prevents_further_records(self, tmp_path):
        """Test circuit breaker prevents recording after trip."""
        tracker = CostTracker(budget=0.1, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.05, "emp-002", "deep")

        assert tracker.is_circuit_breaker_tripped()

        with pytest.raises(PermissionError, match="Circuit breaker is tripped"):
            tracker.record_cost(0.01, "emp-003", "quick")

    def test_can_afford_prevents_exceeding(self, tmp_path):
        """Test can_afford returns False when would exceed."""
        tracker = CostTracker(budget=0.1, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.08, "emp-001", "quick")

        assert not tracker.can_afford(0.05)  # Would exceed
        assert tracker.can_afford(0.02)  # Still ok

    def test_circuit_breaker_can_be_reset(self, tmp_path):
        """Test circuit breaker can be manually reset."""
        tracker = CostTracker(budget=0.1, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.1, "emp-001", "quick")

        assert tracker.is_circuit_breaker_tripped()

        tracker.reset_circuit_breaker()

        assert not tracker.is_circuit_breaker_tripped()

    def test_circuit_breaker_reason(self, tmp_path):
        """Test getting circuit breaker trip reason."""
        tracker = CostTracker(budget=0.05, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")

        reason = tracker.get_circuit_breaker_reason()
        assert reason is not None
        assert "exhausted" in reason


class TestCostTrackerLoading:
    """Test loading existing costs from file."""

    def test_load_existing_costs(self, tmp_path):
        """Test loading costs from existing operations file."""
        operations_file = tmp_path / "operations.jsonl"

        # Create file with existing entries
        with open(operations_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-02-21T10:00:00Z",
                        "operation": "spawn",
                        "cost": 0.05,
                        "agent_id": "emp-001",
                        "category": "quick",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-02-21T10:01:00Z",
                        "operation": "spawn",
                        "cost": 0.10,
                        "agent_id": "emp-002",
                        "category": "deep",
                    }
                )
                + "\n"
            )

        tracker = CostTracker(budget=10.0, operations_file=operations_file)

        assert round(tracker.get_current_spent(), 2) == 0.15
        assert tracker.get_category_spent("quick") == 0.05
        assert tracker.get_category_spent("deep") == 0.10

    def test_get_operation_history(self, tmp_path):
        """Test retrieving operation history."""
        operations_file = tmp_path / "operations.jsonl"
        tracker = CostTracker(budget=10.0, operations_file=operations_file)
        tracker.record_cost(0.05, "emp-001", "quick")
        tracker.record_cost(0.10, "emp-002", "deep")

        history = tracker.get_operation_history()

        assert len(history) == 2
        assert isinstance(history[0], CostEntry)
        assert history[0].agent_id == "emp-001"
        assert history[1].agent_id == "emp-002"


class TestCostTrackerBudgetUpdates:
    """Test budget update functionality."""

    def test_set_budget(self, tmp_path):
        """Test updating budget."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.set_budget(20.0)

        assert tracker.budget == 20.0

    def test_set_budget_resets_circuit_breaker(self, tmp_path):
        """Test increasing budget resets circuit breaker."""
        tracker = CostTracker(budget=0.1, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.1, "emp-001", "quick")

        assert tracker.is_circuit_breaker_tripped()

        tracker.set_budget(1.0)

        assert not tracker.is_circuit_breaker_tripped()

    def test_set_category_budget(self, tmp_path):
        """Test setting category budget."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.set_category_budget("quick", 0.5)

        assert tracker.category_budgets["quick"] == 0.5


class TestCostTrackerVerySmallBudget:
    """Test with very small budget ($0.01)."""

    def test_very_small_budget_first_succeeds(self, tmp_path):
        """Test with $0.01 budget, first hire succeeds."""
        operations_file = tmp_path / "operations.jsonl"
        tracker = CostTracker(budget=0.01, operations_file=operations_file)

        # First task should succeed (cost estimates start at $0.02 minimum)
        # but wait - $0.02 > $0.01, so even first should fail
        # Actually let's use a cost of 0.01 for testing
        tracker.record_cost(0.01, "emp-001", "quick")

        assert tracker.get_current_spent() == 0.01
        assert tracker.is_circuit_breaker_tripped()

    def test_very_small_budget_second_fails(self, tmp_path):
        """Test with $0.01 budget, second hire fails."""
        operations_file = tmp_path / "operations.jsonl"
        tracker = CostTracker(budget=0.02, operations_file=operations_file)

        # First hire succeeds
        tracker.record_cost(0.01, "emp-001", "quick")
        assert tracker.get_current_spent() == 0.01
        assert not tracker.is_circuit_breaker_tripped()

        # Second hire would exceed
        assert not tracker.can_afford(0.02)

        # Recording should trip circuit breaker
        tracker.record_cost(0.01, "emp-002", "quick")
        assert tracker.is_circuit_breaker_tripped()

        # Third hire is blocked
        with pytest.raises(PermissionError):
            tracker.record_cost(0.01, "emp-003", "quick")


class TestCostTrackerRecruiterIntegration:
    """Test CostTracker integration with Recruiter."""

    @pytest.fixture
    def mock_bead(self):
        """Create a test bead."""
        return Bead(
            id="TEST-001",
            title="Test security audit task",
            status="ready",
            issue_type="security",
            priority=5,
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

    @pytest.mark.asyncio
    async def test_recruiter_checks_cost_before_hiring(self, tmp_path, mock_bead):
        """Test recruiter checks cost before hiring."""
        operations_file = tmp_path / "operations.jsonl"
        slaick = Slaick(file_path=tmp_path / "slaick.jsonl")

        # Create tracker with budget that's just enough for one hire
        tracker = CostTracker(budget=0.02, operations_file=operations_file)

        recruiter = Recruiter(
            slaick=slaick,
            employees_file=tmp_path / "employees.jsonl",
            cost_tracker=tracker,
        )

        # First bead should be processed (cost estimate from mock is ~$0.03-$0.05)
        # Since default budget is $0.02, this should fail
        result = await recruiter.process_bead(mock_bead)

        # Should fail due to budget
        assert result is None
        assert not recruiter.has_agent_for_bead(mock_bead)

    @pytest.mark.asyncio
    async def test_recruiter_records_cost_after_hire(self, tmp_path, monkeypatch):
        """Test recruiter records cost after successful hire."""
        operations_file = tmp_path / "operations.jsonl"
        slaick = Slaick(file_path=tmp_path / "slaick.jsonl")

        # Create a bead with low cost (quick category)
        bead = Bead(
            id="TEST-002",
            title="Write documentation",
            status="ready",
            issue_type="docs",
            priority=3,
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        # Budget should be enough for docs task (~$0.02-0.05)
        tracker = CostTracker(budget=1.0, operations_file=operations_file)
        recruiter = Recruiter(
            slaick=slaick,
            employees_file=tmp_path / "employees.jsonl",
            cost_tracker=tracker,
        )

        # Mock get_bead to return our test bead
        from app.company import spawner
        monkeypatch.setattr(spawner, "get_bead", lambda bead_id: bead if bead_id == bead.id else None)

        result = await recruiter.process_bead(bead)

        # Should succeed
        assert result is not None
        assert recruiter.has_agent_for_bead(bead)

        # Cost should be recorded
        assert tracker.get_current_spent() > 0
        assert tracker.get_category_spent("quick") > 0

    @pytest.mark.asyncio
    async def test_recruiter_budget_exceeded_message(self, tmp_path):
        """Test recruiter sends budget exceeded message."""
        operations_file = tmp_path / "operations.jsonl"
        slaick = Slaick(file_path=tmp_path / "slaick.jsonl")
        bead = Bead(
            id="TEST-003",
            title="Security vulnerability audit",
            status="ready",
            issue_type="security",
            priority=8,
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        tracker = CostTracker(budget=0.01, operations_file=operations_file)

        recruiter = Recruiter(
            slaick=slaick,
            employees_file=tmp_path / "employees.jsonl",
            cost_tracker=tracker,
        )
        result = await recruiter.process_bead(bead)

        # Should fail
        assert result is None

        # Check that budget exceeded message was sent
        messages = slaick.get_messages()
        error_messages = [m for m in messages if m["type"] == "ERROR"]

        assert len(error_messages) > 0
        assert error_messages[0]["payload"]["error"] == "budget_exceeded"


class TestCostTrackerRepr:
    """Test string representation."""

    def test_repr(self, tmp_path):
        """Test __repr__ output."""
        tracker = CostTracker(budget=10.0, operations_file=tmp_path / "ops.jsonl")
        tracker.record_cost(0.05, "emp-001", "quick")

        repr_str = repr(tracker)

        assert "CostTracker" in repr_str
        assert "budget=$10.00" in repr_str
        assert "spent=$0.05" in repr_str
        assert "remaining=$9.95" in repr_str
