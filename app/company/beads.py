"""
Beads task system - Claim management with optimistic concurrency control.

This module provides atomic claim operations for beads (issues) using
the beads CLI with optimistic concurrency control to handle race conditions.
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Bead:
    """Represents a bead (issue) from the beads system."""

    id: str
    title: str
    status: str
    priority: int
    issue_type: str
    owner: Optional[str]
    created_at: str
    created_by: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Bead":
        """Create a Bead from a dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            status=data["status"],
            priority=data["priority"],
            issue_type=data["issue_type"],
            owner=data.get("owner"),
            created_at=data["created_at"],
            created_by=data["created_by"],
            updated_at=data["updated_at"],
        )


class BeadNotFoundError(Exception):
    """Raised when a bead is not found."""

    pass


class BeadClaimError(Exception):
    """Raised when a bead claim operation fails."""

    pass


def _run_bd_command(args: list[str], check: bool = True) -> tuple[int, str, str]:
    """
    Run a bd CLI command and return exit code, stdout, and stderr.

    Args:
        args: Command arguments (without 'bd')
        check: Whether to raise on non-zero exit code

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    cmd = ["bd"] + args + ["--json"]
    logger.debug(f"Running bd command: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,  # 30 second timeout for bd operations
    )

    if check and result.returncode != 0:
        logger.error(f"bd command failed: {result.stderr}")
        raise BeadClaimError(f"bd command failed: {result.stderr}")

    return result.returncode, result.stdout, result.stderr


def get_bead(bead_id: str) -> Optional[Bead]:
    """
    Get a bead by ID.

    Args:
        bead_id: The bead ID (e.g., 'stairtup-75l')

    Returns:
        Bead object if found, None otherwise

    Raises:
        BeadClaimError: If the bd command fails
    """
    try:
        code, stdout, stderr = _run_bd_command(["show", bead_id], check=False)

        if code != 0:
            if "not found" in stderr.lower():
                return None
            raise BeadClaimError(f"Failed to get bead: {stderr}")

        data = json.loads(stdout)
        if isinstance(data, list) and len(data) > 0:
            return Bead.from_dict(data[0])
        elif isinstance(data, dict):
            return Bead.from_dict(data)
        else:
            return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse bd output: {e}")
        raise BeadClaimError(f"Invalid JSON from bd: {e}")


def claim_bead(bead_id: str, agent_id: str) -> bool:
    """
    Attempt to claim a bead for an agent using optimistic concurrency control.

    This implements a check-then-update pattern with conflict detection:
    1. Read current status of the bead
    2. If status is 'ready', attempt to update to 'in_progress' with agent as owner
    3. Verify the update succeeded (bead may have been claimed by another agent)

    Args:
        bead_id: The bead ID to claim
        agent_id: The agent claiming the bead

    Returns:
        True if claim succeeded, False if bead is already claimed or not ready

    Raises:
        BeadNotFoundError: If the bead doesn't exist
        BeadClaimError: If the claim operation fails unexpectedly
    """
    logger.info(f"Agent {agent_id} attempting to claim bead {bead_id}")

    # Step 1: Get current bead state
    bead = get_bead(bead_id)
    if bead is None:
        logger.warning(f"Bead {bead_id} not found")
        raise BeadNotFoundError(f"Bead {bead_id} does not exist")

    logger.debug(f"Bead {bead_id} current status: {bead.status}, owner: {bead.owner}")

    # Step 2: Check if already claimed or not in ready state
    if bead.status != "ready":
        logger.info(f"Bead {bead_id} not ready (status: {bead.status}), claim failed")
        return False

    if bead.owner is not None and bead.owner != agent_id:
        logger.info(f"Bead {bead_id} already owned by {bead.owner}, claim failed")
        return False

    # Step 3: Attempt atomic claim using bd's built-in claim flag
    # The --claim flag atomically sets assignee and status, failing if already claimed
    try:
        code, stdout, stderr = _run_bd_command(
            ["update", bead_id, "--claim", "--actor", agent_id],
            check=False,
        )

        if code != 0:
            # Check if this is a conflict (already claimed)
            if "already claimed" in stderr.lower() or "conflict" in stderr.lower():
                logger.info(
                    f"Bead {bead_id} was claimed by another agent during our attempt"
                )
                return False
            logger.error(f"bd update failed: {stderr}")
            raise BeadClaimError(f"Failed to update bead: {stderr}")

        # Step 4: Verify the claim succeeded by re-reading the bead
        # This handles cases where bd update returned success but another agent won
        bead = get_bead(bead_id)
        if bead is None:
            raise BeadClaimError(f"Bead {bead_id} disappeared after claim")

        if bead.owner == agent_id and bead.status == "in_progress":
            logger.info(f"Agent {agent_id} successfully claimed bead {bead_id}")
            return True
        else:
            logger.info(
                f"Bead {bead_id} claim verification failed "
                f"(owner: {bead.owner}, status: {bead.status})"
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout claiming bead {bead_id}")
        raise BeadClaimError(f"Timeout claiming bead {bead_id}")


async def claim_bead_async(bead_id: str, agent_id: str) -> bool:
    """
    Async version of claim_bead.

    Runs the synchronous claim operation in a thread pool to avoid blocking.

    Args:
        bead_id: The bead ID to claim
        agent_id: The agent claiming the bead

    Returns:
        True if claim succeeded, False otherwise
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, claim_bead, bead_id, agent_id)


def release_bead(bead_id: str, agent_id: str) -> bool:
    """
    Release a bead back to ready status.

    Only the owning agent can release a bead.

    Args:
        bead_id: The bead ID to release
        agent_id: The agent releasing the bead

    Returns:
        True if release succeeded, False if not owned by agent
    """
    logger.info(f"Agent {agent_id} attempting to release bead {bead_id}")

    bead = get_bead(bead_id)
    if bead is None:
        raise BeadNotFoundError(f"Bead {bead_id} does not exist")

    if bead.owner != agent_id:
        logger.warning(f"Agent {agent_id} cannot release bead owned by {bead.owner}")
        return False

    try:
        _run_bd_command(
            ["update", bead_id, "--status", "ready", "--assignee", ""],
            check=True,
        )
        logger.info(f"Agent {agent_id} successfully released bead {bead_id}")
        return True
    except BeadClaimError:
        return False


def get_ready_beads() -> list[Bead]:
    """
    Get all beads in 'ready' status.

    Returns:
        List of beads ready to be claimed
    """
    try:
        code, stdout, stderr = _run_bd_command(
            ["list", "--status", "ready"],
            check=False,
        )

        if code != 0:
            logger.error(f"Failed to list ready beads: {stderr}")
            return []

        data = json.loads(stdout)
        if isinstance(data, list):
            return [Bead.from_dict(b) for b in data]
        return []

    except (json.JSONDecodeError, BeadClaimError) as e:
        logger.error(f"Failed to get ready beads: {e}")
        return []
