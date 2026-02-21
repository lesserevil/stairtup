"""
Agent Spawning Mechanism - Spawns agents based on Job Descriptions.

This module implements the AgentSpawner that:
- Maps Job Descriptions to OpenCode task parameters
- Generates 6-section prompts for spawned agents
- Tracks spawned agents in employees.jsonl
- Sends ACK/COMPLETE messages via Slaick
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.company.beads import Bead, get_bead
from app.company.slaick import MessageType, Slaick
from app.company.types import JobDescription

logger = logging.getLogger(__name__)


# Category mapping from JD to OpenCode task categories
CATEGORY_MAP = {
    "quick": "quick",
    "deep": "deep",
    "ultrabrain": "ultrabrain",
    "visual-engineering": "visual-engineering",
    "writing": "writing",
    "artistry": "artistry",
}


@dataclass
class SpawnedAgent:
    """Represents a spawned agent employee."""

    agent_id: str
    role: str
    bead_id: str
    hired_at: str
    status: str
    category: str
    prompt: str
    employee_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "bead_id": self.bead_id,
            "hired_at": self.hired_at,
            "status": self.status,
            "category": self.category,
            "prompt": self.prompt,
            "employee_id": self.employee_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpawnedAgent":
        """Create from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            role=data["role"],
            bead_id=data["bead_id"],
            hired_at=data["hired_at"],
            status=data["status"],
            category=data["category"],
            prompt=data["prompt"],
            employee_id=data["employee_id"],
        )


class AgentSpawner:
    """
    Spawns agents based on Job Descriptions.

    Responsibilities:
    - Generate 6-section prompts for spawned agents
    - Track spawned agents in employees.jsonl
    - Send ACK/COMPLETE messages via Slaick
    - Map JD categories to OpenCode task categories

    Attributes:
        employees_file: Path to the employees.jsonl tracking file
        slaick: Slaick messaging instance for ACK/COMPLETE notifications
        mock_mode: If True, simulates spawning without actual task() calls
    """

    def __init__(
        self,
        employees_file: Optional[Path | str] = None,
        slaick: Optional[Slaick] = None,
        mock_mode: bool = True,
    ):
        """
        Initialize the AgentSpawner.

        Args:
            employees_file: Path to employees.jsonl file. Defaults to 'employees.jsonl' in cwd.
            slaick: Slaick messaging instance (creates default if None)
            mock_mode: If True, simulates spawning without actual task() calls
        """
        if employees_file is None:
            employees_file = Path("employees.jsonl")
        self.employees_file = Path(employees_file)
        self.slaick = slaick or Slaick()
        self.mock_mode = mock_mode

        # Ensure employees file exists
        self.employees_file.touch(exist_ok=True)

        logger.info(
            f"AgentSpawner initialized (employees_file={self.employees_file}, "
            f"mock_mode={mock_mode})"
        )

    def _generate_agent_id(self) -> str:
        """Generate a unique agent ID."""
        return f"emp-{uuid.uuid4().hex[:8]}"

    def _map_category(self, jd_category: str) -> str:
        """
        Map JD category to OpenCode task category.

        Args:
            jd_category: Category from JobDescription

        Returns:
            OpenCode task category
        """
        return CATEGORY_MAP.get(jd_category.lower(), "deep")

    def _generate_prompt(self, jd: JobDescription, bead: Bead, agent_id: str) -> str:
        """
        Generate a 6-section prompt for the spawned agent.

        Args:
            jd: Job Description for the agent
            bead: The bead to work on
            agent_id: The assigned agent ID

        Returns:
            6-section prompt string
        """
        return f"""## 1. TASK
Work on bead {bead.id}: {bead.title}
Job Description: {jd.role}

Your role: {jd.description}
Required capabilities: {", ".join(jd.required_capabilities)}

## 2. EXPECTED OUTCOME
- Complete the task described in the bead
- Report progress via Slaick
- Mark bead as done when finished
- Follow your role-specific guidelines: {jd.suggested_category} category work

## 3. REQUIRED TOOLS
- beads: Claim and update task status
- slaick: Report progress and communicate
- {jd.suggested_category}: Your assigned agent category

## 4. MUST DO
- Claim the bead before working on it
- Send PROGRESS messages every 30s to report status
- Send COMPLETE when work is finished successfully
- Follow best practices for {jd.role} work

## 5. MUST NOT DO
- Do NOT work on beads outside your JD role
- Do NOT claim multiple beads at once
- Do NOT modify code unrelated to your assigned bead
- Do NOT skip progress reporting

## 6. CONTEXT
Bead details:
- ID: {bead.id}
- Type: {bead.issue_type}
- Priority: {bead.priority}/10
- Created: {bead.created_at}
- Description: {bead.description if hasattr(bead, "description") and bead.description else "See bead title for details"}

Agent ID: {agent_id}
Employee ID: {self._generate_employee_id(bead, jd)}
Category: {jd.suggested_category}
Complexity: {jd.complexity}
Cost estimate: ${jd.cost_estimate}
"""

    def _generate_employee_id(self, bead: Bead, jd: JobDescription) -> str:
        """Generate employee ID matching Recruiter's format."""
        role_slug = jd.role.lower().replace(" ", "-").replace("/", "-")
        return f"{role_slug}-{bead.id}"

    def _append_employee_record(self, agent: SpawnedAgent) -> None:
        """
        Append an employee record to employees.jsonl.

        Args:
            agent: SpawnedAgent to record
        """
        line = json.dumps(agent.to_dict(), separators=(",", ":"))
        with open(self.employees_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

        logger.info(
            f"Appended employee record for {agent.agent_id} to {self.employees_file}"
        )

    async def _send_ack_message(self, agent: SpawnedAgent, bead: Bead) -> dict:
        """
        Send an ACK message via Slaick to confirm agent spawn.

        Args:
            agent: The spawned agent
            bead: The bead being worked on

        Returns:
            The message dict that was written
        """
        payload = {
            "agent_id": agent.agent_id,
            "employee_id": agent.employee_id,
            "bead_id": bead.id,
            "bead_title": bead.title,
            "role": agent.role,
            "category": agent.category,
            "prompt_length": len(agent.prompt),
        }

        message = self.slaick.append_message(
            from_agent="spawner",
            to_agent="orchestrator",
            msg_type=MessageType.ACK,
            payload=payload,
        )

        logger.info(f"Sent ACK for agent {agent.agent_id} handling bead {bead.id}")

        return message

    def _write_spawn_request_log(self, agent: SpawnedAgent, jd: JobDescription) -> None:
        """
        Log spawn request details when in mock mode.

        Args:
            agent: The spawned agent
            jd: The Job Description
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent.agent_id,
            "employee_id": agent.employee_id,
            "bead_id": agent.bead_id,
            "role": agent.role,
            "category": agent.category,
            "mock_mode": self.mock_mode,
            "note": "Agent spawn logged (mock_mode=True - would call task() in production)",
        }

        # Write to a separate log file for spawn requests
        spawn_log_file = self.employees_file.parent / "spawn_requests.jsonl"
        with open(spawn_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, separators=(",", ":")) + "\n")

        logger.info(
            f"Mock spawn: Would call task(category='{agent.category}', prompt=...) "
            f"for agent {agent.agent_id}"
        )

    async def spawn_agent(self, jd: JobDescription, bead_id: str) -> str:
        """
        Spawn an agent based on a Job Description.

        This method:
        1. Maps JD category to OpenCode task category
        2. Generates a 6-section prompt
        3. Tracks the agent in employees.jsonl
        4. Sends ACK message via Slaick
        5. Returns the agent ID

        In mock_mode (default), this simulates spawning by:
        - Generating a fake agent_id
        - Writing to employees.jsonl
        - Sending ACK message
        - Logging the spawn request

        In production (mock_mode=False), this would call the actual OpenCode
        task() function to spawn a real agent.

        Args:
            jd: JobDescription for the agent to spawn
            bead_id: ID of the bead the agent will work on

        Returns:
            agent_id: The unique ID of the spawned agent

        Raises:
            SpawnError: If spawning fails
        """
        logger.info(f"Spawning agent for bead {bead_id}: {jd.role}")

        try:
            # Get bead details
            bead = get_bead(bead_id)
            if bead is None:
                raise SpawnError(f"Bead {bead_id} not found")

            # Generate agent ID
            agent_id = self._generate_agent_id()

            # Map category
            category = self._map_category(jd.suggested_category)

            # Generate prompt
            prompt = self._generate_prompt(jd, bead, agent_id)

            # Generate employee ID
            employee_id = self._generate_employee_id(bead, jd)

            # Create agent record
            hired_at = datetime.now(timezone.utc).isoformat()
            agent = SpawnedAgent(
                agent_id=agent_id,
                role=jd.role,
                bead_id=bead_id,
                hired_at=hired_at,
                status="active",
                category=category,
                prompt=prompt,
                employee_id=employee_id,
            )

            # Track in employees.jsonl
            self._append_employee_record(agent)

            # Send ACK message
            await self._send_ack_message(agent, bead)

            # If mock mode, log the spawn request
            if self.mock_mode:
                self._write_spawn_request_log(agent, jd)
            else:
                # In production, this would call the actual task() function
                # task(category=category, prompt=prompt)
                logger.warning("Production spawn mode not yet implemented")

            logger.info(
                f"Successfully spawned agent {agent_id} ({category}) for bead {bead_id}"
            )

            return agent_id

        except SpawnError:
            raise
        except Exception as e:
            logger.error(f"Failed to spawn agent for bead {bead_id}: {e}")
            raise SpawnError(f"Agent spawn failed: {e}") from e

    def get_all_employees(self) -> list[SpawnedAgent]:
        """
        Read all employee records from employees.jsonl.

        Returns:
            List of all SpawnedAgent records
        """
        employees = []
        if not self.employees_file.exists():
            return employees

        with open(self.employees_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        employees.append(SpawnedAgent.from_dict(data))
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping malformed employee record: {e}")
                        continue

        return employees

    def get_active_agents_for_bead(self, bead_id: str) -> list[SpawnedAgent]:
        """
        Get all active agents assigned to a specific bead.

        Args:
            bead_id: The bead ID to check

        Returns:
            List of active SpawnedAgent records for the bead
        """
        all_employees = self.get_all_employees()
        return [
            emp
            for emp in all_employees
            if emp.bead_id == bead_id and emp.status == "active"
        ]

    def has_active_agent_for_bead(self, bead_id: str) -> bool:
        """
        Check if there's an active agent for a bead.

        Args:
            bead_id: The bead ID to check

        Returns:
            True if an active agent exists for the bead
        """
        return len(self.get_active_agents_for_bead(bead_id)) > 0


class SpawnError(Exception):
    """Raised when agent spawning fails."""

    pass
