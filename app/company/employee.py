"""
Employee Base Runtime - Agent persistency with periodic heartbeat mechanism.

This module implements the Employee class that:
- Manages agent lifecycle with heartbeat updates
- Maintains registry entry with last_heartbeat, expires_at, and status
- Provides atomic JSONL file updates for concurrent safety
- Integrates with Slaick for agent communication
- Supports graceful shutdown
"""

import asyncio
import fcntl
import json
import logging
import os
import signal
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from app.company.slaick import MessageType, Slaick
from app.company.types import JobDescription

logger = logging.getLogger(__name__)


class EmployeeStatus(str, Enum):
    """Employee status states."""

    IDLE = "idle"
    BUSY = "busy"
    ACTIVE = "active"  # Legacy compatibility
    OFFLINE = "offline"


class Employee:
    """
    Base runtime for agent employees with heartbeat mechanism.

    The Employee class manages an agent's lifecycle:
    1. Initializes with agent_id and JobDescription
    2. Starts heartbeat loop (updates registry every 10s)
    3. Posts "Agent Online" to Slaick on startup
    4. Maintains registry entry with status, last_heartbeat, expires_at
    5. Provides graceful shutdown (marks status as offline)

    Attributes:
        agent_id: Unique identifier for this agent
        job_description: JobDescription defining the agent's role
        employees_file: Path to the employees.jsonl registry file
        slaick: Slaick instance for messaging
        heartbeat_interval: Seconds between heartbeat updates (default: 10)
        heartbeat_ttl: Seconds until heartbeat expires (default: 30)
        _status: Current employee status
        _heartbeat_task: Background task for heartbeat loop
        _shutdown_event: Event to signal graceful shutdown
        _is_running: Flag indicating if employee is running
    """

    def __init__(
        self,
        agent_id: str,
        job_description: JobDescription,
        employees_file: Optional[Path | str] = None,
        slaick: Optional[Slaick] = None,
        heartbeat_interval: int = 10,
        heartbeat_ttl: int = 30,
    ):
        """
        Initialize the Employee runtime.

        Args:
            agent_id: Unique identifier for this agent
            job_description: JobDescription defining the agent's role
            employees_file: Path to employees.jsonl file (defaults to 'employees.jsonl')
            slaick: Slaick instance for messaging (creates default if None)
            heartbeat_interval: Seconds between heartbeats (default: 10)
            heartbeat_ttl: Seconds until heartbeat expires (default: 30)
        """
        self.agent_id = agent_id
        self.job_description = job_description

        if employees_file is None:
            employees_file = Path("employees.jsonl")
        self.employees_file = Path(employees_file)

        self.slaick = slaick or Slaick()
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_ttl = heartbeat_ttl

        self._status = EmployeeStatus.IDLE
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._is_running = False
        self._lock = asyncio.Lock()

        logger.info(
            f"Employee {agent_id} initialized with role: {job_description.role}"
        )

    @property
    def status(self) -> EmployeeStatus:
        """Get current employee status."""
        return self._status

    async def set_status(self, status: EmployeeStatus) -> None:
        """
        Update employee status and trigger immediate heartbeat.

        Args:
            status: New status to set
        """
        async with self._lock:
            old_status = self._status
            self._status = status
            logger.info(
                f"Employee {self.agent_id} status: {old_status.value} -> {status.value}"
            )

        # Trigger immediate heartbeat to persist status change
        await self._update_heartbeat()

    async def _generate_timestamp(self) -> str:
        """Generate ISO 8601 timestamp in UTC."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _update_heartbeat(self) -> None:
        """
        Update this employee's heartbeat in the registry.

        Performs atomic update via temp file + rename to ensure:
        - No data loss during concurrent access
        - Other employees' data is not corrupted
        - Registry is always in a consistent state
        """
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.heartbeat_ttl)

            heartbeat_data = {
                "agent_id": self.agent_id,
                "last_heartbeat": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": self._status.value,
            }

            await self._atomic_update_registry(heartbeat_data)

        except Exception as e:
            logger.error(f"Failed to update heartbeat for {self.agent_id}: {e}")
            raise

    async def _atomic_update_registry(self, heartbeat_data: dict[str, Any]) -> None:
        """
        Atomically update this employee's entry in the registry.

        Uses write-to-temp + rename pattern for atomicity.
        Only updates the line matching this agent_id.

        Args:
            heartbeat_data: Heartbeat data to merge into employee record
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_atomic_update, heartbeat_data)

    def _sync_atomic_update(self, heartbeat_data: dict[str, Any]) -> None:
        """
        Synchronous implementation of atomic registry update with file locking.

        Uses POSIX file locking (flock) to prevent race conditions when multiple
        employees update the registry concurrently. Only the agent matching
        this employee's agent_id is updated.

        Args:
            heartbeat_data: Heartbeat data to merge into employee record
        """
        # Ensure file exists
        self.employees_file.touch(exist_ok=True)

        # Create a lock file for exclusive access to the registry
        lock_file_path = self.employees_file.parent / f".employees.lock"

        # Open lock file (create if doesn't exist)
        lock_fd = os.open(str(lock_file_path), os.O_RDWR | os.O_CREAT)

        try:
            # Acquire exclusive lock
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # Read all current records
            records = []
            if self.employees_file.exists():
                with open(self.employees_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                logger.warning(f"Skipping malformed record: {line[:50]}...")
                                continue

            # Find and update this employee's record, or create new if not found
            found = False
            for record in records:
                if record.get("agent_id") == self.agent_id:
                    # Merge heartbeat data into existing record
                    record.update(heartbeat_data)
                    found = True
                    break

            if not found:
                # This shouldn't happen in normal flow (spawner creates record first)
                # But handle gracefully by creating a minimal record
                logger.warning(
                    f"Employee {self.agent_id} not found in registry, creating new entry"
                )
                new_record = {
                    "agent_id": self.agent_id,
                    "role": self.job_description.role,
                    "status": heartbeat_data.get("status", EmployeeStatus.IDLE.value),
                    "last_heartbeat": heartbeat_data.get("last_heartbeat"),
                    "expires_at": heartbeat_data.get("expires_at"),
                }
                records.append(new_record)

            # Write to temp file then atomically rename
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.employees_file.parent,
                prefix=f".employees_{self.agent_id}_",
                suffix=".tmp",
            )

            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    for record in records:
                        f.write(json.dumps(record, separators=(",", ":")) + "\n")
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                os.rename(temp_path, self.employees_file)

            except Exception as e:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                raise e

        finally:
            # Release lock and close lock file
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    async def _heartbeat_loop(self) -> None:
        """
        Background task that periodically updates the heartbeat.

        Runs until _shutdown_event is set. Updates registry every
        heartbeat_interval seconds.
        """
        logger.info(
            f"Heartbeat loop started for {self.agent_id} "
            f"(interval={self.heartbeat_interval}s, ttl={self.heartbeat_ttl}s)"
        )

        try:
            while not self._shutdown_event.is_set():
                await self._update_heartbeat()

                # Wait for next heartbeat or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=self.heartbeat_interval
                    )
                except asyncio.TimeoutError:
                    # Normal timeout, continue with next heartbeat
                    pass

        except asyncio.CancelledError:
            logger.info(f"Heartbeat loop cancelled for {self.agent_id}")
            raise
        except Exception as e:
            logger.error(f"Heartbeat loop error for {self.agent_id}: {e}")
            raise

    async def _send_online_message(self) -> None:
        """Send 'Agent Online' message via Slaick."""
        try:
            payload = {
                "agent_id": self.agent_id,
                "role": self.job_description.role,
                "status": self._status.value,
                "message": "Agent Online",
            }

            self.slaick.append_message(
                from_agent=self.agent_id,
                to_agent="orchestrator",
                msg_type=MessageType.PROGRESS,
                payload=payload,
            )

            logger.info(f"Sent 'Agent Online' message for {self.agent_id}")

        except Exception as e:
            logger.error(f"Failed to send online message for {self.agent_id}: {e}")
            # Don't raise - this is non-critical

    async def start(self) -> None:
        """
        Start the employee runtime.

        This method:
        1. Sends "Agent Online" message via Slaick
        2. Starts the heartbeat background task
        3. Sets up signal handlers for graceful shutdown
        """
        if self._is_running:
            logger.warning(f"Employee {self.agent_id} already running")
            return

        self._is_running = True
        self._shutdown_event.clear()

        # Send online message
        await self._send_online_message()

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"heartbeat_{self.agent_id}"
        )

        # Set up signal handlers for graceful shutdown
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(
                    sig, lambda: asyncio.create_task(self.shutdown())
                )
        except (ValueError, NotImplementedError):
            # Signal handlers not supported in this environment (e.g., Windows, threads)
            logger.debug(f"Signal handlers not available for {self.agent_id}")

        logger.info(f"Employee {self.agent_id} started successfully")

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the employee.

        This method:
        1. Signals heartbeat loop to stop
        2. Waits for heartbeat task to complete
        3. Updates status to OFFLINE
        4. Sends final heartbeat with offline status
        """
        if not self._is_running:
            logger.debug(f"Employee {self.agent_id} not running, nothing to shutdown")
            return

        logger.info(f"Shutting down employee {self.agent_id}")

        # Signal shutdown
        self._shutdown_event.set()

        # Wait for heartbeat task to complete
        if self._heartbeat_task and not self._heartbeat_task.done():
            try:
                await asyncio.wait_for(self._heartbeat_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Heartbeat task did not complete in time for {self.agent_id}"
                )
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass

        # Update status to offline
        self._status = EmployeeStatus.OFFLINE
        try:
            await self._update_heartbeat()
        except Exception as e:
            logger.error(
                f"Failed to send final offline heartbeat for {self.agent_id}: {e}"
            )

        self._is_running = False
        logger.info(f"Employee {self.agent_id} shutdown complete")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures graceful shutdown."""
        await self.shutdown()

    def is_running(self) -> bool:
        """Check if the employee is currently running."""
        return self._is_running

    def get_heartbeat_info(self) -> dict[str, Any]:
        """
        Get current heartbeat information for this employee.

        Returns:
            Dictionary with agent_id, status, last_heartbeat, expires_at
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.heartbeat_ttl)

        return {
            "agent_id": self.agent_id,
            "status": self._status.value,
            "last_heartbeat": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


@asynccontextmanager
async def employee_runtime(
    agent_id: str,
    job_description: JobDescription,
    employees_file: Optional[Path | str] = None,
    slaick: Optional[Slaick] = None,
):
    """
    Context manager for running an Employee with automatic lifecycle management.

    Usage:
        async with employee_runtime(agent_id, jd) as emp:
            # Employee is running with heartbeat active
            await emp.set_status(EmployeeStatus.BUSY)
            # Do work...
        # Employee is automatically shutdown on exit

    Args:
        agent_id: Unique identifier for this agent
        job_description: JobDescription defining the agent's role
        employees_file: Path to employees.jsonl file
        slaick: Slaick instance for messaging

    Yields:
        Employee instance that is started and will be shutdown on exit
    """
    emp = Employee(
        agent_id=agent_id,
        job_description=job_description,
        employees_file=employees_file,
        slaick=slaick,
    )
    await emp.start()
    try:
        yield emp
    finally:
        await emp.shutdown()
