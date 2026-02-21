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

from app.company.beads import Bead, claim_bead_async, get_ready_beads
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
        poll_interval: float = 5.0,
        task_execution_time: float = 2.0,
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
            poll_interval: Seconds between work polling attempts (default: 5)
            task_execution_time: Seconds to simulate task execution (default: 2)
        """
        self.agent_id = agent_id
        self.job_description = job_description

        if employees_file is None:
            employees_file = Path("employees.jsonl")
        self.employees_file = Path(employees_file)

        self.slaick = slaick or Slaick()
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_ttl = heartbeat_ttl
        self.poll_interval = poll_interval
        self.task_execution_time = task_execution_time

        self._status = EmployeeStatus.IDLE
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._work_stealing_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._is_running = False
        self._lock = asyncio.Lock()
        self._current_bead: Optional[Bead] = None
        self._is_listening = False
        self._message_listener_task: Optional[asyncio.Task] = None

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

        # Start work stealing loop
        self._work_stealing_task = asyncio.create_task(
            self._work_stealing_loop(), name=f"work_stealing_{self.agent_id}"
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

        # Wait for work stealing task to complete first (may be executing a task)
        if self._work_stealing_task and not self._work_stealing_task.done():
            try:
                # Give more time for work stealing to finish current task
                await asyncio.wait_for(self._work_stealing_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Work stealing task did not complete in time for {self.agent_id}"
                )
                self._work_stealing_task.cancel()
                try:
                    await self._work_stealing_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass

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
    # ==========================================================================

    # ==========================================================================
    # Work Stealing / Task Execution Methods
    # ==========================================================================
    # Work Stealing / Task Execution Methods
    # ==========================================================================

    def _can_do_task(self, bead: Bead) -> bool:
        """
        Check if this employee can handle a task based on their specialization.

        Uses rule-based matching to determine if the bead title matches
        the employee's role (JD). This is a simplified mock for testing -
        in production this could use LLM-based matching.

        Matching rules:
        - Frontend Developer: bead title contains CSS/HTML/React
        - Backend Developer: bead title contains API/DB/Python

        Args:
            bead: The bead to check

        Returns:
            True if this employee can handle the task, False otherwise
        """
        role = self.job_description.role.lower()
        title = bead.title.lower()

        # Frontend Developer matching
        if "frontend" in role:
            frontend_keywords = ["css", "html", "react", "ui", "ux", "frontend"]
            return any(kw in title for kw in frontend_keywords)

        # Backend Developer matching
        if "backend" in role:
            backend_keywords = ["api", "db", "database", "python", "backend", "server"]
            return any(kw in title for kw in backend_keywords)

        # Default: accept all tasks (for generic roles)
        return True

    async def poll_for_work(self) -> Optional[Bead]:
        """
        Poll for available work and attempt to claim a matching bead.

        This method:
        1. Only runs if status is IDLE (availability gate)
        2. Gets all ready beads from the system
        3. Filters beads that match this employee's specialization
        4. Attempts to atomically claim a matching bead
        5. Returns the claimed bead or None

        Returns:
            The claimed Bead if successful, None otherwise
        """
        # Availability gate: only poll if idle
        if self._status != EmployeeStatus.IDLE:
            logger.debug(f"Employee {self.agent_id} is not idle, skipping work poll")
            return None

        try:
            # Get all ready beads
            ready_beads = await asyncio.get_event_loop().run_in_executor(
                None, get_ready_beads
            )

            if not ready_beads:
                return None

            logger.info(f"Employee {self.agent_id} found {len(ready_beads)} ready beads")

            # Try to claim matching beads in priority order
            for bead in ready_beads:
                # Specialization gate: check if we can do this task
                if not self._can_do_task(bead):
                    logger.debug(
                        f"Employee {self.agent_id} cannot handle bead {bead.id}: {bead.title}"
                    )
                    continue

                logger.info(
                    f"Employee {self.agent_id} attempting to claim bead {bead.id}: {bead.title}"
                )

                # Concurrency gate: attempt atomic claim
                claimed = await claim_bead_async(bead.id, self.agent_id)

                if claimed:
                    logger.info(f"Employee {self.agent_id} successfully claimed bead {bead.id}")
                    return bead
                else:
                    logger.debug(
                        f"Employee {self.agent_id} failed to claim bead {bead.id} (already claimed)"
                    )

            return None

        except Exception as e:
            logger.error(f"Error polling for work: {e}")
            return None

    async def _send_claimed_message(self, bead: Bead) -> None:
        """Send 'Claimed task' message via Slaick."""
        try:
            payload = {
                "agent_id": self.agent_id,
                "role": self.job_description.role,
                "bead_id": bead.id,
                "bead_title": bead.title,
                "message": f"Claimed task {bead.id}",
            }

            self.slaick.append_message(
                from_agent=self.agent_id,
                to_agent="orchestrator",
                msg_type=MessageType.CLAIM,
                payload=payload,
            )

            logger.info(f"Sent CLAIM message for bead {bead.id}")

        except Exception as e:
            logger.error(f"Failed to send CLAIM message: {e}")

    async def _send_completed_message(self, bead: Bead) -> None:
        """Send 'Completed task' message via Slaick."""
        try:
            payload = {
                "agent_id": self.agent_id,
                "role": self.job_description.role,
                "bead_id": bead.id,
                "bead_title": bead.title,
                "message": "Completed",
            }

            self.slaick.append_message(
                from_agent=self.agent_id,
                to_agent="orchestrator",
                msg_type=MessageType.COMPLETE,
                payload=payload,
            )

            logger.info(f"Sent COMPLETE message for bead {bead.id}")

        except Exception as e:
            logger.error(f"Failed to send COMPLETE message: {e}")

    async def _update_bead_status_done(self, bead_id: str) -> bool:
        """
        Update bead status to 'done' using bd CLI.

        Args:
            bead_id: The bead ID to update

        Returns:
            True if update succeeded, False otherwise
        """
        import subprocess

        try:
            result = subprocess.run(
                ["bd", "update", bead_id, "--status", "done"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Updated bead {bead_id} status to done")
                return True
            else:
                logger.error(f"Failed to update bead {bead_id}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error updating bead {bead_id}: {e}")
            return False

    async def execute_task(self, bead: Bead) -> None:
        """
        Execute a claimed task.

        This method simulates task execution by:
        1. Setting status to BUSY
        2. Sending CLAIM message via Slaick
        3. Simulating work (async sleep)
        4. Updating bead status to 'done'
        5. Sending COMPLETE message via Slaick
        6. Setting status back to IDLE

        Args:
            bead: The bead to execute
        """
        logger.info(f"Employee {self.agent_id} starting execution of bead {bead.id}")

        # Transition to BUSY
        self._current_bead = bead
        await self.set_status(EmployeeStatus.BUSY)

        # Send CLAIM message
        await self._send_claimed_message(bead)

        try:
            # Simulate work execution
            logger.info(
                f"Employee {self.agent_id} executing bead {bead.id} "
                f"(simulated work for {self.task_execution_time}s)"
            )
            await asyncio.sleep(self.task_execution_time)

            # Update bead status to done
            await self._update_bead_status_done(bead.id)

            # Send COMPLETE message
            await self._send_completed_message(bead)

            logger.info(f"Employee {self.agent_id} completed bead {bead.id}")

        except Exception as e:
            logger.error(f"Error executing bead {bead.id}: {e}")
            # Send ERROR message on failure
            try:
                self.slaick.append_message(
                    from_agent=self.agent_id,
                    to_agent="orchestrator",
                    msg_type=MessageType.ERROR,
                    payload={
                        "agent_id": self.agent_id,
                        "bead_id": bead.id,
                        "error": str(e),
                    },
                )
            except Exception:
                pass

        finally:
            # Always transition back to IDLE
            self._current_bead = None
            await self.set_status(EmployeeStatus.IDLE)

    async def _work_stealing_loop(self) -> None:
        """
        Background task that continuously polls for work.

        Runs until _shutdown_event is set. Implements the work stealing protocol:
        - When IDLE: Poll for work every poll_interval seconds
        - When work found: Claim and execute it
        - When BUSY: Skip polling (don't claim multiple tasks)

        The loop handles the full lifecycle: Idle -> Scan -> Claim -> Busy -> Complete -> Idle
        """
        logger.info(f"Work stealing loop started for {self.agent_id}")

        try:
            while not self._shutdown_event.is_set():
                # Only poll if we're idle
                if self._status == EmployeeStatus.IDLE:
                    bead = await self.poll_for_work()

                    if bead:
                        # Execute the task (this handles status transitions)
                        await self.execute_task(bead)
                    else:
                        # No work available, wait before polling again
                        try:
                            await asyncio.wait_for(
                                self._shutdown_event.wait(), timeout=self.poll_interval
                            )
                        except asyncio.TimeoutError:
                            pass
                else:
                    # We're busy, just wait for next poll cycle
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(), timeout=self.poll_interval
                        )
                    except asyncio.TimeoutError:
                        pass

        except asyncio.CancelledError:
            logger.info(f"Work stealing loop cancelled for {self.agent_id}")
            raise
        except Exception as e:
            logger.error(f"Work stealing loop error for {self.agent_id}: {e}")
            raise

    async def start_work_stealing(self) -> None:
        """
        Start the work stealing background loop.

        This should be called after start() to enable automatic task execution.
        The work stealing loop runs independently of the heartbeat loop.
        """
        if self._work_stealing_task and not self._work_stealing_task.done():
            logger.warning(f"Work stealing already running for {self.agent_id}")
            return

        self._work_stealing_task = asyncio.create_task(
            self._work_stealing_loop(), name=f"work_stealing_{self.agent_id}"
        )
        logger.info(f"Started work stealing loop for {self.agent_id}")

    async def stop_work_stealing(self) -> None:
        """
        Stop the work stealing background loop gracefully.

        Cancels the work stealing task and waits for it to complete.
        """
        if self._work_stealing_task and not self._work_stealing_task.done():
            self._work_stealing_task.cancel()
            try:
                await self._work_stealing_task
            except asyncio.CancelledError:
                pass
            logger.info(f"Stopped work stealing loop for {self.agent_id}")

    def get_current_bead(self) -> Optional[Bead]:
        """Get the bead currently being executed, if any."""
        return self._current_bead

    async def start_message_listener(
        self,
        poll_interval: float = 2.0,
    ) -> None:
        """
        Start listening for messages directed to this employee.

        This is primarily for future use (e.g., receiving commands from
        a supervisor or orchestrator). Currently, employees mainly send
        messages (PROGRESS, COMPLETE, ERROR) but this enables two-way
        communication.

        Args:
            poll_interval: Seconds between message polls
        """
        if self._is_listening:
            logger.warning(f"Message listener already running for {self.agent_id}")
            return

        self._is_listening = True
        self._message_listener_task = asyncio.create_task(
            self._message_listener_loop(poll_interval)
        )

        logger.info(f"Message listener started for {self.agent_id}")

    async def _message_listener_loop(self, poll_interval: float = 2.0) -> None:
        """
        Background loop that listens for incoming messages.

        Args:
            poll_interval: Seconds between polls
        """
        logger.info(f"Message listener loop started for {self.agent_id}")

        try:
            async for message in self.slaick.listen(
                agent_id=self.agent_id,
                poll_interval=poll_interval,
            ):
                if not self._is_listening:
                    break

                msg_id = message.get("id")
                msg_type = message.get("type")

                logger.debug(
                    f"Employee {self.agent_id} received message {msg_id} of type {msg_type}"
                )

                # Handle different message types
                if msg_type == MessageType.ACK.value:
                    await self._handle_ack_message(message)
                else:
                    # For now, just log unknown message types
                    logger.debug(
                        f"Employee {self.agent_id} received unhandled message type: {msg_type}"
                    )

        except asyncio.CancelledError:
            logger.info(f"Message listener loop cancelled for {self.agent_id}")
        except Exception as e:
            logger.error(f"Error in message listener loop for {self.agent_id}: {e}")
        finally:
            logger.info(f"Message listener loop stopped for {self.agent_id}")

    async def _handle_ack_message(self, message: dict) -> None:
        """
        Handle ACK messages from the orchestrator/recruiter.

        Args:
            message: The ACK message dict
        """
        payload = message.get("payload", {})
        original_type = payload.get("original_type")
        status = payload.get("status")

        logger.debug(
            f"Employee {self.agent_id} received ACK for {original_type} with status {status}"
        )

    async def stop_message_listener(self) -> None:
        """Stop the message listener background task."""
        if not self._is_listening:
            return

        self._is_listening = False

        if self._message_listener_task and not self._message_listener_task.done():
            self._message_listener_task.cancel()
            try:
                await self._message_listener_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Message listener stopped for {self.agent_id}")

    def is_listening(self) -> bool:
        """Check if the message listener is running."""
        return self._is_listening



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

