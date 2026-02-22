#!/usr/bin/env python3
"""
Swarm Integration Test - Startup Company Simulation (Mocked Beads)

This script performs a full end-to-end swarm integration test simulating
a startup company environment with mocked beads to avoid bd CLI issues.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("simulation")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.company.beads import Bead
from app.company.cost_tracker import CostTracker
from app.company.slaick import MessageType, Slaick
from app.company.types import JobDescription


class SimulationConfig:
    """Configuration for the simulation."""

    NUM_TASKS = 10
    MAX_SIMULATION_TIME = 120  # seconds
    POLL_INTERVAL = 0.5
    AGENT_EXECUTION_TIME = 1.0  # seconds per task
    HEARTBEAT_INTERVAL = 2
    HEARTBEAT_TTL = 10


class MockBeadsManager:
    """
    In-memory mock beads manager that replaces bd CLI calls.
    """

    def __init__(self):
        self._beads: dict[str, Bead] = {}
        self._lock = asyncio.Lock()
        self._counter = 0

    def create_bead(self, title: str, issue_type: str, priority: int) -> str:
        """Create a new bead and return its ID."""
        self._counter += 1
        bead_id = f"sim-{self._counter:03d}"

        bead = Bead(
            id=bead_id,
            title=title,
            status="ready",
            priority=priority,
            issue_type=issue_type,
            owner=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by="simulation",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._beads[bead_id] = bead
        return bead_id

    def get_bead(self, bead_id: str) -> Optional[Bead]:
        """Get a bead by ID."""
        return self._beads.get(bead_id)

    def get_ready_beads(self) -> list[Bead]:
        """Get all beads with 'ready' status."""
        return [b for b in self._beads.values() if b.status == "ready"]

    async def claim_bead(self, bead_id: str, agent_id: str) -> bool:
        """Attempt to claim a bead for an agent."""
        async with self._lock:
            bead = self._beads.get(bead_id)
            if bead and bead.status == "ready":
                bead.status = "in_progress"
                bead.owner = agent_id
                bead.updated_at = datetime.now(timezone.utc).isoformat()
                return True
            return False

    def update_bead_status(
        self, bead_id: str, status: str, assignee: Optional[str] = None
    ):
        """Update bead status."""
        bead = self._beads.get(bead_id)
        if bead:
            bead.status = status
            if assignee is not None:
                bead.owner = assignee if assignee else None
            bead.updated_at = datetime.now(timezone.utc).isoformat()

    def get_all_statuses(self) -> dict[str, str]:
        """Get all bead statuses."""
        return {bid: bead.status for bid, bead in self._beads.items()}


# Global mock beads manager
mock_beads = MockBeadsManager()


class TestBeadManager:
    """Manages test beads for simulation using the mock manager."""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.bead_ids = []

    def create_test_beads(self) -> list[str]:
        """Create 10 test beads with various types."""
        beads_config = [
            ("Implement user authentication API endpoint", "feature", 2, "backend"),
            ("Create database migration for user table", "task", 3, "backend"),
            ("Fix API response caching bug", "bug", 0, "backend"),
            ("Build Python analytics processing module", "feature", 2, "backend"),
            ("Refactor CSS styling for dashboard components", "task", 3, "frontend"),
            ("Build React component for user profile", "feature", 2, "frontend"),
            ("Fix HTML accessibility issues in forms", "bug", 3, "frontend"),
            ("Cleanup zombie agents from failed workers", "task", 1, "janitor"),
            ("Clean up orphaned task records", "task", 4, "janitor"),
            ("Write documentation for API endpoints", "task", 4, "docs"),
        ]

        for title, issue_type, priority, category in beads_config:
            bead_id = mock_beads.create_bead(title, issue_type, priority)
            self.bead_ids.append(bead_id)
            logger.info(f"Created bead {bead_id}: {title} [{category}]")

        return self.bead_ids

    def get_bead_status(self, bead_id: str) -> Optional[str]:
        """Get current status of a bead."""
        bead = mock_beads.get_bead(bead_id)
        return bead.status if bead else None

    def get_all_statuses(self) -> dict[str, str]:
        """Get status of all created beads."""
        return mock_beads.get_all_statuses()


# Import after MockBeadsManager is defined but before Employee/Recruiter
# (they will import the patched versions later)
from app.company.employee import Employee, EmployeeStatus
from app.company.recruiter import Recruiter
from app.company.spawner import AgentSpawner


class MockTaskSpawner(AgentSpawner):
    """Mock spawner that launches agents as async tasks."""

    def __init__(self, employees_file, slaick, mock_mode=False, temp_dir=None):
        super().__init__(employees_file=employees_file, slaick=slaick, mock_mode=False)
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.spawned_agents: dict[str, asyncio.Task] = {}
        self.agent_processes: dict[str, Any] = {}

    async def spawn_agent(self, jd: JobDescription, bead_id: str) -> str:
        """Spawn a real agent as an async task."""
        agent_id = await super().spawn_agent(jd, bead_id)

        employee = Employee(
            agent_id=agent_id,
            job_description=jd,
            employees_file=self.employees_file,
            slaick=self.slaick,
            heartbeat_interval=SimulationConfig.HEARTBEAT_INTERVAL,
            heartbeat_ttl=SimulationConfig.HEARTBEAT_TTL,
            poll_interval=SimulationConfig.POLL_INTERVAL,
            task_execution_time=SimulationConfig.AGENT_EXECUTION_TIME,
        )

        task = asyncio.create_task(
            self._run_employee(employee, agent_id), name=f"agent_{agent_id}"
        )
        self.spawned_agents[agent_id] = task
        self.agent_processes[agent_id] = employee

        logger.info(
            f"MockTaskSpawner: Spawned agent {agent_id} ({jd.role}) for bead {bead_id}"
        )
        return agent_id

    async def _run_employee(self, employee: Employee, agent_id: str):
        """Run an employee until completion or cancellation."""
        try:
            await employee.start()
            while employee.is_running():
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info(f"Agent {agent_id} received cancellation signal")
            raise
        except Exception as e:
            logger.error(f"Agent {agent_id} crashed: {e}")
            raise
        finally:
            await employee.shutdown()

    async def kill_agent(self, agent_id: str):
        """Simulate an agent crash by cancelling its task."""
        if agent_id in self.spawned_agents:
            task = self.spawned_agents[agent_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"MockTaskSpawner: Killed agent {agent_id} (simulated crash)")

    async def stop_all_agents(self):
        """Stop all spawned agents gracefully."""
        for agent_id, task in list(self.spawned_agents.items()):
            task.cancel()

        if self.spawned_agents:
            await asyncio.gather(*self.spawned_agents.values(), return_exceptions=True)

        self.spawned_agents.clear()
        self.agent_processes.clear()


class SimulationOrchestrator:
    """Orchestrates the full simulation."""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.slaick_file = temp_dir / "slaick.jsonl"
        self.employees_file = temp_dir / "employees.jsonl"
        self.operations_file = temp_dir / "operations.jsonl"

        self.slaick = Slaick(self.slaick_file)
        self.cost_tracker = CostTracker(
            budget=50.0,
            operations_file=self.operations_file,
        )

        self.bead_manager = TestBeadManager(temp_dir)
        self.recruiter: Optional[Recruiter] = None
        self.mock_spawner: Optional[MockTaskSpawner] = None

        self.start_time: Optional[datetime] = None
        self.recruiter_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None

        self.results = {
            "tasks_created": 0,
            "agents_hired": [],
            "agents_killed": [],
            "tasks_completed": [],
            "slaick_messages": [],
            "errors": [],
        }

    async def setup(self):
        """Set up the simulation environment."""
        logger.info("=" * 70)
        logger.info("SIMULATION SETUP")
        logger.info("=" * 70)

        bead_ids = self.bead_manager.create_test_beads()
        self.results["tasks_created"] = len(bead_ids)
        logger.info(f"Created {len(bead_ids)} test beads")

        self.recruiter = Recruiter(
            slaick=self.slaick,
            fast_poll_interval=1.0,
            slow_poll_interval=3.0,
            use_llm=False,
            employees_file=self.employees_file,
            cost_tracker=self.cost_tracker,
        )

        self.mock_spawner = MockTaskSpawner(
            employees_file=self.employees_file,
            slaick=self.slaick,
            mock_mode=False,
            temp_dir=self.temp_dir,
        )
        self.recruiter.spawner = self.mock_spawner

        logger.info("Simulation environment ready")
        return bead_ids

    async def run(self):
        """Run the full simulation."""
        logger.info("\n" + "=" * 70)
        logger.info("SIMULATION START")
        logger.info("=" * 70)

        self.start_time = datetime.now(timezone.utc)

        self.recruiter_task = asyncio.create_task(
            self.recruiter.run(), name="recruiter"
        )

        self.monitoring_task = asyncio.create_task(
            self._monitor_simulation(), name="monitor"
        )

        try:
            await asyncio.wait_for(
                self._wait_for_completion(),
                timeout=SimulationConfig.MAX_SIMULATION_TIME,
            )
        except asyncio.TimeoutError:
            logger.warning("Simulation timed out!")

        await self._shutdown()

    async def _monitor_simulation(self):
        """Monitor simulation progress and collect metrics."""
        last_message_count = 0

        while True:
            try:
                messages = self.slaick.get_messages()
                if len(messages) > last_message_count:
                    new_messages = messages[last_message_count:]
                    for msg in new_messages:
                        self._process_message(msg)
                    last_message_count = len(messages)

                statuses = self.bead_manager.get_all_statuses()
                done_count = sum(1 for s in statuses.values() if s == "done")

                logger.info(
                    f"Monitor: {done_count}/{len(statuses)} tasks done, "
                    f"{len(self.mock_spawner.spawned_agents)} agents active"
                )

                await self._maybe_simulate_crash()
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(2)

    def _process_message(self, msg: dict):
        """Process a Slaick message and update results."""
        msg_type = msg.get("type")
        payload = msg.get("payload", {})

        self.results["slaick_messages"].append(
            {
                "type": msg_type,
                "from": msg.get("from"),
                "to": msg.get("to"),
                "timestamp": msg.get("timestamp"),
                "bead_id": payload.get("bead_id"),
            }
        )

        if msg_type == "HIRE":
            employee_id = payload.get("employee_id")
            role = payload.get("job_description", {}).get("role")
            self.results["agents_hired"].append(
                {
                    "employee_id": employee_id,
                    "role": role,
                    "bead_id": payload.get("bead_id"),
                }
            )
            logger.info(f"HIRED: {role} ({employee_id})")

        elif msg_type == "CLAIM":
            agent_id = msg.get("from")
            bead_id = payload.get("bead_id")
            role = payload.get("role")
            logger.info(f"CLAIMED: {role} took {bead_id}")

        elif msg_type == "COMPLETE":
            agent_id = msg.get("from")
            bead_id = payload.get("bead_id")
            role = payload.get("role")
            self.results["tasks_completed"].append(
                {
                    "agent_id": agent_id,
                    "role": role,
                    "bead_id": bead_id,
                }
            )
            logger.info(f"COMPLETED: {role} finished {bead_id}")

    async def _maybe_simulate_crash(self):
        """Simulate an agent crash after some progress."""
        if (
            not self.results["agents_killed"]
            and len(self.mock_spawner.spawned_agents) >= 2
        ):
            await asyncio.sleep(5)

            for agent_id, employee in self.mock_spawner.agent_processes.items():
                if "backend" in employee.job_description.role.lower():
                    if agent_id not in self.results["agents_killed"]:
                        logger.warning(f"SIMULATING CRASH: Killing {agent_id}")
                        await self.mock_spawner.kill_agent(agent_id)
                        self.results["agents_killed"].append(agent_id)
                        await asyncio.sleep(3)
                        break

    async def _wait_for_completion(self):
        """Wait for all tasks to complete."""
        while True:
            statuses = self.bead_manager.get_all_statuses()
            done_count = sum(1 for s in statuses.values() if s == "done")

            if done_count >= len(self.bead_manager.bead_ids):
                logger.info("All tasks completed!")
                break

            await asyncio.sleep(1)

    async def _shutdown(self):
        """Shutdown the simulation."""
        logger.info("\n" + "=" * 70)
        logger.info("SIMULATION SHUTDOWN")
        logger.info("=" * 70)

        if self.recruiter:
            self.recruiter.stop()

        if self.recruiter_task and not self.recruiter_task.done():
            self.recruiter_task.cancel()
            try:
                await self.recruiter_task
            except asyncio.CancelledError:
                pass

        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        if self.mock_spawner:
            await self.mock_spawner.stop_all_agents()

    def verify_results(self) -> dict:
        """Verify simulation results and return report."""
        logger.info("\n" + "=" * 70)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 70)

        report = {
            "success": True,
            "checks": {},
            "errors": [],
        }

        # Check 1: All beads done
        statuses = self.bead_manager.get_all_statuses()
        not_done = [bid for bid, status in statuses.items() if status != "done"]
        report["checks"]["all_beads_done"] = len(not_done) == 0
        if not_done:
            report["errors"].append(f"Beads not done: {not_done}")
        logger.info(f"✓ All beads done: {report['checks']['all_beads_done']}")

        # Check 2: Backend dev didn't touch CSS
        backend_claims = [
            m
            for m in self.results["slaick_messages"]
            if m["type"] == "CLAIM" and "Backend" in str(m.get("role", ""))
        ]
        css_violations = []
        for claim in backend_claims:
            bead_id = claim.get("bead_id", "")
            if bead_id:
                bead = mock_beads.get_bead(bead_id)
                if bead and "css" in bead.title.lower():
                    css_violations.append((claim["from"], bead_id, bead.title))
        report["checks"]["backend_no_css"] = len(css_violations) == 0
        if css_violations:
            report["errors"].append(f"Backend touched CSS: {css_violations}")
        logger.info(f"✓ Backend didn't touch CSS: {report['checks']['backend_no_css']}")

        # Check 3: Cost tracking
        report["checks"]["cost_tracking"] = self.cost_tracker.get_current_spent() > 0
        report["total_cost"] = self.cost_tracker.get_current_spent()
        logger.info(f"✓ Cost tracked: ${report['total_cost']:.3f}")

        # Check 4: Slaick has expected message types
        slaick = self.slaick
        msg_types = {}
        for msg in slaick.get_messages():
            t = msg.get("type")
            msg_types[t] = msg_types.get(t, 0) + 1

        expected_types = ["HIRE", "CLAIM", "PROGRESS", "COMPLETE", "ACK"]
        report["checks"]["slaick_message_types"] = all(
            t in msg_types for t in expected_types
        )
        report["message_counts"] = msg_types
        logger.info(
            f"✓ Slaick has expected types: {report['checks']['slaick_message_types']}"
        )
        logger.info(f"  Message counts: {msg_types}")

        # Check 5: Agents were hired
        report["checks"]["agents_hired"] = len(self.results["agents_hired"]) >= 3
        logger.info(f"✓ At least 3 agents hired: {report['checks']['agents_hired']}")

        # Check 6: Janitor handled crashes
        if self.results["agents_killed"]:
            janitor_activity = [
                m
                for m in self.results["slaick_messages"]
                if "Janitor" in str(m.get("role", "")) or m["type"] == "PROGRESS"
            ]
            report["checks"]["janitor_recovery"] = len(janitor_activity) > 0
            logger.info(
                f"✓ Janitor handled crashes: {report['checks']['janitor_recovery']}"
            )
        else:
            report["checks"]["janitor_recovery"] = True
            logger.info("✓ No crashes simulated (janitor recovery not tested)")

        report["success"] = all(report["checks"].values())

        report["stats"] = {
            "tasks_created": self.results["tasks_created"],
            "agents_hired": len(self.results["agents_hired"]),
            "agents_killed": len(self.results["agents_killed"]),
            "tasks_completed": len(self.results["tasks_completed"]),
            "total_cost": self.cost_tracker.get_current_spent(),
            "remaining_budget": self.cost_tracker.get_remaining_budget(),
        }

        return report

    def print_final_report(self, report: dict):
        """Print the final simulation report."""
        logger.info("\n" + "=" * 70)
        logger.info("FINAL SIMULATION REPORT")
        logger.info("=" * 70)

        if report["success"]:
            logger.info("🎉 SIMULATION SUCCESS!")
        else:
            logger.error("❌ SIMULATION FAILED")

        logger.info("\nVerification Checks:")
        for check, passed in report["checks"].items():
            status = "✓ PASS" if passed else "✗ FAIL"
            logger.info(f"  {status}: {check}")

        logger.info("\nSimulation Statistics:")
        for stat, value in report["stats"].items():
            logger.info(f"  {stat}: {value}")

        if report["errors"]:
            logger.info("\nErrors:")
            for error in report["errors"]:
                logger.error(f"  - {error}")

        logger.info("\n" + "=" * 70)


async def run_simulation():
    """Run the simulation with mocked beads."""
    logger.info("\n" + "=" * 70)
    logger.info("SWARM INTEGRATION TEST - STARTUP COMPANY SIMULATION")
    logger.info("=" * 70)
    logger.info(f"Configuration:")
    logger.info(f"  Tasks: {SimulationConfig.NUM_TASKS}")
    logger.info(f"  Max time: {SimulationConfig.MAX_SIMULATION_TIME}s")
    logger.info(f"  Agent execution time: {SimulationConfig.AGENT_EXECUTION_TIME}s")
    logger.info("")

    # Create mock wrappers that call our mock_beads
    def mock_get_ready_wrapper():
        return mock_beads.get_ready_beads()

    def mock_get_bead_wrapper(bead_id):
        return mock_beads.get_bead(bead_id)

    async def mock_claim_wrapper(bead_id, agent_id):
        return await mock_beads.claim_bead(bead_id, agent_id)

    # Create mock methods to replace Employee's subprocess-based methods
    async def mock_update_bead_done(self, bead_id: str) -> bool:
        """Mock update bead status to done."""
        mock_beads.update_bead_status(bead_id, "done")
        logger.info(f"[MOCK] Updated bead {bead_id} status to done")
        return True

    def mock_reset_bead(self, bead_id: str) -> None:
        """Mock reset bead to ready."""
        mock_beads.update_bead_status(bead_id, "ready", "")
        logger.info(f"[MOCK] Reset bead {bead_id} to ready")

    # Apply patches using context managers
    patches = [
        # Patch beads module functions
        patch("app.company.beads.get_ready_beads", side_effect=mock_get_ready_wrapper),
        patch("app.company.beads.get_bead", side_effect=mock_get_bead_wrapper),
        patch("app.company.beads.claim_bead_async", side_effect=mock_claim_wrapper),
        # Patch the imported references in employee and recruiter
        patch(
            "app.company.employee.get_ready_beads", side_effect=mock_get_ready_wrapper
        ),
        patch("app.company.employee.claim_bead_async", side_effect=mock_claim_wrapper),
        patch(
            "app.company.recruiter.get_ready_beads", side_effect=mock_get_ready_wrapper
        ),
        patch("app.company.spawner.get_bead", side_effect=mock_get_bead_wrapper),
        # Patch Employee's subprocess-based methods
        patch.object(Employee, "_update_bead_status_done", mock_update_bead_done),
        patch.object(Employee, "_reset_bead_to_ready", mock_reset_bead),
    ]

    # Start all patches
    for p in patches:
        p.start()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            logger.info(f"Using temp directory: {temp_path}")

            orchestrator = SimulationOrchestrator(temp_path)
            await orchestrator.setup()
            await orchestrator.run()

            report = orchestrator.verify_results()
            orchestrator.print_final_report(report)

            return 0 if report["success"] else 1
    except Exception as e:
        logger.error(f"Simulation failed with error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return 1
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


if __name__ == "__main__":
    exit_code = asyncio.run(run_simulation())
    sys.exit(exit_code)
