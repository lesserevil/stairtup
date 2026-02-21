"""
Tests for the beads claim system with optimistic concurrency control.

These tests verify that the claim_bead function correctly handles:
- Normal claim operations
- Race conditions where multiple agents claim the same bead
- Bead not found scenarios
- Already claimed beads
"""

import asyncio
import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from app.company.beads import (
    Bead,
    BeadClaimError,
    BeadNotFoundError,
    claim_bead,
    claim_bead_async,
    get_bead,
    get_ready_beads,
    release_bead,
)


@pytest.fixture
def sample_bead_data():
    """Sample bead data for testing."""
    return {
        "id": "test-123",
        "title": "Test Bead",
        "status": "ready",
        "priority": 2,
        "issue_type": "task",
        "owner": None,
        "created_at": "2026-02-21T19:27:28Z",
        "created_by": "Test",
        "updated_at": "2026-02-21T19:27:28Z",
    }


@pytest.fixture
def claimed_bead_data():
    """Sample claimed bead data."""
    return {
        "id": "test-123",
        "title": "Test Bead",
        "status": "in_progress",
        "priority": 2,
        "issue_type": "task",
        "owner": "agent-1",
        "created_at": "2026-02-21T19:27:28Z",
        "created_by": "Test",
        "updated_at": "2026-02-21T19:27:30Z",
    }


class TestGetBead:
    """Tests for get_bead function."""

    def test_get_bead_success(self, sample_bead_data):
        """Test successfully retrieving a bead."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([sample_bead_data])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            bead = get_bead("test-123")

        assert bead is not None
        assert bead.id == "test-123"
        assert bead.title == "Test Bead"
        assert bead.status == "ready"

    def test_get_bead_not_found(self):
        """Test bead not found scenario."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "bead not found"

        with patch("subprocess.run", return_value=mock_result):
            bead = get_bead("nonexistent")

        assert bead is None

    def test_get_bead_error(self):
        """Test error handling in get_bead."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "database error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(BeadClaimError, match="database error"):
                get_bead("test-123")


class TestClaimBead:
    """Tests for claim_bead function."""

    def test_claim_bead_success(self, sample_bead_data, claimed_bead_data):
        """Test successful bead claim."""
        # Sequence: show (initial), update, show (verify)
        def mock_subprocess_run(cmd, **kwargs):
            mock_result = Mock()
            if "show" in cmd:
                if not hasattr(mock_subprocess_run, "call_count"):
                    mock_subprocess_run.call_count = 0
                mock_subprocess_run.call_count += 1
                mock_result.returncode = 0
                # First show returns ready, second returns claimed
                if mock_subprocess_run.call_count == 1:
                    mock_result.stdout = json.dumps([sample_bead_data])
                else:
                    mock_result.stdout = json.dumps([claimed_bead_data])
            elif "update" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = json.dumps([claimed_bead_data])
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            result = claim_bead("test-123", "agent-1")

        assert result is True

    def test_claim_bead_already_claimed(self, claimed_bead_data):
        """Test claiming a bead that's already in progress."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([claimed_bead_data])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = claim_bead("test-123", "agent-2")

        assert result is False

    def test_claim_bead_not_found(self):
        """Test claiming a non-existent bead."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "not found"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(BeadNotFoundError, match="does not exist"):
                claim_bead("nonexistent", "agent-1")

    def test_claim_bead_conflict_during_update(self, sample_bead_data):
        """Test handling conflict when another agent claims during our attempt."""
        show_result = Mock(
            returncode=0, stdout=json.dumps([sample_bead_data]), stderr=""
        )
        update_result = Mock(
            returncode=1, stdout="", stderr="conflict: already claimed"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [show_result, update_result]

            result = claim_bead("test-123", "agent-1")

        assert result is False


class TestConcurrentClaims:
    """Tests for concurrent claim scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_claims_only_one_succeeds(self, sample_bead_data):
        """
        Test that when 5 agents try to claim the same bead simultaneously,
        only one succeeds.
        """
        # Track which agent successfully claimed
        claimed_by = None
        claim_count = 0

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal claimed_by, claim_count
            mock_result = Mock()

            if "show" in cmd:
                # Return current state of bead
                if claimed_by is None:
                    mock_result.returncode = 0
                    mock_result.stdout = json.dumps(
                        [{**sample_bead_data, "status": "ready", "owner": None}]
                    )
                else:
                    mock_result.returncode = 0
                    mock_result.stdout = json.dumps(
                        [
                            {
                                **sample_bead_data,
                                "status": "in_progress",
                                "owner": claimed_by,
                            }
                        ]
                    )

            elif "update" in cmd and "--claim" in cmd:
                # Simulate atomic claim operation
                agent_id = cmd[cmd.index("--actor") + 1]
                if claimed_by is None:
                    claimed_by = agent_id
                    claim_count += 1
                    mock_result.returncode = 0
                else:
                    mock_result.returncode = 1
                    mock_result.stderr = "already claimed"

            mock_result.stderr = mock_result.stderr or ""
            return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Launch 5 concurrent claim attempts
            tasks = [claim_bead_async("test-123", f"agent-{i}") for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful claims
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)

        # Verify only one agent succeeded
        assert successes == 1, f"Expected 1 success, got {successes}"
        assert failures == 4, f"Expected 4 failures, got {failures}"
        assert claim_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_claims_on_different_beads_all_succeed(
        self, sample_bead_data
    ):
        """Test that agents can concurrently claim different beads."""
        claimed_beads = {}
        call_counts = {}

        def mock_subprocess_run(cmd, **kwargs):
            mock_result = Mock()
            # Parse command: bd show <bead_id> --json OR bd update <bead_id> --claim --actor <agent> --json
            if "show" in cmd:
                bead_id = cmd[-2]  # bead_id is second-to-last (before --json)
            else:
                bead_id = cmd[2]  # bead_id is third arg for update
            
            # Track call count per bead for proper sequencing
            if bead_id not in call_counts:
                call_counts[bead_id] = 0
            
            if "show" in cmd:
                owner = claimed_beads.get(bead_id)
                call_counts[bead_id] += 1
                mock_result.returncode = 0
                mock_result.stdout = json.dumps(
                    [
                        {
                            **sample_bead_data,
                            "id": bead_id,
                            "status": "in_progress" if owner else "ready",
                            "owner": owner,
                        }
                    ]
                )

            elif "update" in cmd and "--claim" in cmd:
                agent_id = cmd[cmd.index("--actor") + 1]
                if bead_id not in claimed_beads:
                    claimed_beads[bead_id] = agent_id
                    mock_result.returncode = 0
                    # Return claimed bead data for verification
                    mock_result.stdout = json.dumps(
                        [
                            {
                                **sample_bead_data,
                                "id": bead_id,
                                "status": "in_progress",
                                "owner": agent_id,
                            }
                        ]
                    )
                else:
                    mock_result.returncode = 1
                    mock_result.stderr = "already claimed"

            mock_result.stderr = mock_result.stderr or ""
            return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Each agent claims a different bead
            tasks = [claim_bead_async(f"bead-{i}", f"agent-{i}") for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed since they're claiming different beads
        successes = sum(1 for r in results if r is True)
        assert successes == 5, f"Expected 5 successes, got {successes}"


class TestReleaseBead:
    """Tests for release_bead function."""

    def test_release_bead_success(self, claimed_bead_data):
        """Test successfully releasing a bead."""
        show_result = Mock(
            returncode=0, stdout=json.dumps([claimed_bead_data]), stderr=""
        )
        update_result = Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [show_result, update_result]

            result = release_bead("test-123", "agent-1")

        assert result is True

    def test_release_bead_wrong_agent(self, claimed_bead_data):
        """Test releasing a bead owned by another agent."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([claimed_bead_data])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = release_bead("test-123", "agent-2")

        assert result is False


class TestGetReadyBeads:
    """Tests for get_ready_beads function."""

    def test_get_ready_beads_success(self, sample_bead_data):
        """Test listing ready beads."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([sample_bead_data, sample_bead_data])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            beads = get_ready_beads()

        assert len(beads) == 2
        assert all(b.status == "ready" for b in beads)

    def test_get_ready_beads_empty(self):
        """Test empty ready beads list."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            beads = get_ready_beads()

        assert beads == []


class TestBeadDataclass:
    """Tests for the Bead dataclass."""

    def test_bead_from_dict(self, sample_bead_data):
        """Test creating Bead from dictionary."""
        bead = Bead.from_dict(sample_bead_data)

        assert bead.id == "test-123"
        assert bead.title == "Test Bead"
        assert bead.status == "ready"
        assert bead.priority == 2
        assert bead.owner is None

    def test_bead_from_dict_with_owner(self, claimed_bead_data):
        """Test creating Bead from dictionary with owner."""
        bead = Bead.from_dict(claimed_bead_data)

        assert bead.owner == "agent-1"
        assert bead.status == "in_progress"
