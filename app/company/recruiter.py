"""
Recruiter - Dynamic Job Description generation and agent hiring system.

This module implements the Recruiter agent that continuously polls for ready beads,
generates dynamic Job Descriptions (JDs) based on bead content using LLM analysis,
and triggers hiring when new agents are needed.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.company.beads import Bead, get_ready_beads
from app.company.cost_tracker import CostTracker
from app.company.slaick import MessageType, Slaick
from app.company.spawner import AgentSpawner
from app.company.types import JobDescription

logger = logging.getLogger(__name__)


# JobDescription is now imported from app.company.types


@dataclass
class Employee:
    """Represents a hired/tracked employee agent."""

    employee_id: str
    role: str
    bead_id: str
    hired_at: str
    status: str = "active"  # active, busy, idle


class Recruiter:
    """
    Recruiter agent that manages the hiring pipeline.

    Responsibilities:
    - Poll beads for 'ready' status tasks
    - Generate dynamic JDs using LLM analysis
    - Track active employees to prevent over-hiring
    - Send HIRE messages via Slaick when spawning is needed
    - Adaptive polling: fast when work available, slow when idle

    Attributes:
        running: Whether the polling loop is active
        slaick: Slaick messaging instance for HIRE notifications
        employees: Dict of bead_id -> Employee to track active workers
        fast_poll_interval: Seconds between polls when work is available
        slow_poll_interval: Seconds between polls when idle
        use_llm: Whether to use real LLM API or mock
    """

    def __init__(
        self,
        slaick: Optional[Slaick] = None,
        fast_poll_interval: float = 1.0,
        slow_poll_interval: float = 5.0,
        use_llm: bool = False,
        employees_file: Optional[Path | str] = None,
        cost_tracker: Optional[CostTracker] = None,
    ):
        """
        Initialize the Recruiter.

        Args:
            slaick: Slaick messaging instance (creates default if None)
            fast_poll_interval: Seconds to sleep when work is available
            slow_poll_interval: Seconds to sleep when idle
            use_llm: Whether to call OpenAI API (False = use mock)
            employees_file: Path to employees.jsonl (creates default if None)
            cost_tracker: CostTracker for budget management (None = unlimited)
        """
        self.running = False
        self.slaick = slaick or Slaick()
        self.employees: dict[str, Employee] = {}
        self.fast_poll_interval = fast_poll_interval
        self.slow_poll_interval = slow_poll_interval
        self.use_llm = use_llm and os.environ.get("OPENAI_API_KEY") is not None
        self.cost_tracker = cost_tracker
        
        # Initialize spawner for agent spawning
        self.spawner = AgentSpawner(
            employees_file=employees_file,
            slaick=self.slaick,
            mock_mode=True,  # Default to mock mode for MVP
        )

        logger.info(
            f"Recruiter initialized (poll: {fast_poll_interval}s fast, "
            f"{slow_poll_interval}s slow, llm={self.use_llm}, "
            f"cost_tracker={'enabled' if cost_tracker else 'disabled'})"
        )

    def has_agent_for_bead(self, bead: Bead) -> bool:
        """
        Check if an employee is already assigned to this bead.

        Args:
            bead: The bead to check

        Returns:
            True if an agent is already handling this bead
        """
        return bead.id in self.employees

    def _analyze_bead_content(self, bead: Bead) -> dict:
        """
        Analyze bead content to extract key characteristics.

        Args:
            bead: The bead to analyze

        Returns:
            Dict with extracted features (keywords, complexity indicators, etc.)
        """
        title_lower = bead.title.lower()

        # Extract keywords from title
        keywords = []
        # Order matters - more specific categories first
        keyword_map = {
            "security": ["security", "vulnerability", "audit", "auth", "encrypt"],
            "docs": ["documentation", "readme", "docstring", "wiki"],
            "frontend": ["frontend", "ui", "ux", "component", "css", "react", "html"],
            "backend": ["backend", "api", "endpoint", "database", "server"],
            "devops": ["deploy", "docker", "kubernetes", "ci/cd", "infrastructure"],
            "testing": ["test", "pytest", "unit test", "integration", "coverage"],
            "database": ["database", "sql", "migration", "schema", "postgres"],
            "ai": ["ai", "llm", "openai", "model", "prompt", "embedding"],
        }

        for category, terms in keyword_map.items():
            if any(term in title_lower for term in terms):
                keywords.append(category)

        # Determine complexity based on priority and issue type
        complexity_indicators = {
            "bug": 0.6,
            "feature": 0.7,
            "refactor": 0.8,
            "architecture": 0.9,
        }
        base_complexity = complexity_indicators.get(bead.issue_type.lower(), 0.5)

        # Higher priority often means more complex or urgent
        priority_multiplier = 1.0 + (bead.priority / 10.0)
        estimated_complexity = min(1.0, base_complexity * priority_multiplier)

        return {
            "keywords": keywords,
            "title": bead.title,
            "issue_type": bead.issue_type,
            "priority": bead.priority,
            "estimated_complexity": estimated_complexity,
        }

    async def generate_jd(self, bead: Bead) -> JobDescription:
        """
        Generate a Job Description for a bead using LLM or mock analysis.

        In production with use_llm=True and OPENAI_API_KEY set, this calls
        the OpenAI API. Otherwise uses rule-based mock that analyzes
        bead content.

        Args:
            bead: The bead to generate JD for

        Returns:
            JobDescription with role, capabilities, category, and cost estimate
        """
        if self.use_llm:
            return await self._generate_jd_with_llm(bead)
        else:
            return self._generate_jd_mock(bead)

    def _generate_jd_mock(self, bead: Bead) -> JobDescription:
        """
        Rule-based mock JD generation for development/testing.

        Analyzes bead title and type to produce appropriate JD without
        API calls (cost-free for tests).

        Args:
            bead: The bead to analyze

        Returns:
            Generated JobDescription
        """
        analysis = self._analyze_bead_content(bead)
        keywords = analysis["keywords"]
        complexity = analysis["estimated_complexity"]

        # Map keywords to role and capabilities
        role_mapping = {
            "security": {
                "role": "Security Auditor",
                "description": "Analyze code for security vulnerabilities and best practices",
                "capabilities": [
                    "code_review",
                    "security_analysis",
                    "vulnerability_scanning",
                ],
                "category": "ultrabrain",
            },
            "frontend": {
                "role": "Frontend Developer",
                "description": "Implement user interfaces and components",
                "capabilities": [
                    "ui_development",
                    "component_design",
                    "css",
                    "accessibility",
                ],
                "category": "visual-engineering",
            },
            "backend": {
                "role": "Backend Developer",
                "description": "Build APIs and server-side functionality",
                "capabilities": ["api_design", "database_modeling", "business_logic"],
                "category": "deep",
            },
            "devops": {
                "role": "DevOps Engineer",
                "description": "Manage deployment infrastructure and CI/CD pipelines",
                "capabilities": [
                    "infrastructure",
                    "docker",
                    "kubernetes",
                    "automation",
                ],
                "category": "ultrabrain",
            },
            "testing": {
                "role": "QA Engineer",
                "description": "Write and maintain test suites for quality assurance",
                "capabilities": ["test_automation", "test_design", "coverage_analysis"],
                "category": "quick",
            },
            "database": {
                "role": "Database Engineer",
                "description": "Design and optimize database schemas and queries",
                "capabilities": ["sql", "schema_design", "performance_optimization"],
                "category": "deep",
            },
            "ai": {
                "role": "AI/ML Engineer",
                "description": "Implement machine learning models and AI integrations",
                "capabilities": [
                    "llm_integration",
                    "prompt_engineering",
                    "model_tuning",
                ],
                "category": "ultrabrain",
            },
            "docs": {
                "role": "Technical Writer",
                "description": "Create clear documentation and guides",
                "capabilities": ["technical_writing", "documentation", "clarity"],
                "category": "quick",
            },
        }

        # Default role if no keywords match
        default_role = {
            "role": "Software Engineer",
            "description": "General software development and problem solving",
            "capabilities": ["problem_solving", "coding", "debugging"],
            "category": "deep",
        }

        # Find best matching role based on keywords
        selected_role = default_role
        for keyword in keywords:
            if keyword in role_mapping:
                selected_role = role_mapping[keyword]
                break

        # Calculate cost estimate based on complexity and category
        base_costs = {
            "quick": 0.02,
            "deep": 0.05,
            "ultrabrain": 0.15,
            "visual-engineering": 0.08,
        }
        base_cost = base_costs.get(selected_role["category"], 0.05)
        cost_estimate = round(base_cost * (1 + complexity), 3)

        return JobDescription(
            role=selected_role["role"],
            description=selected_role["description"],
            required_capabilities=selected_role["capabilities"],
            suggested_category=selected_role["category"],
            cost_estimate=cost_estimate,
            complexity=round(complexity, 2),
        )

    async def _generate_jd_with_llm(self, bead: Bead) -> JobDescription:
        """
        Generate JD using OpenAI API for production use.

        Note: This requires OPENAI_API_KEY environment variable.
        Falls back to mock if API is unavailable.

        Args:
            bead: The bead to analyze

        Returns:
            Generated JobDescription
        """
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

            prompt = f"""Analyze this task and generate a job description for an AI agent to complete it.

Task ID: {bead.id}
Title: {bead.title}
Type: {bead.issue_type}
Priority: {bead.priority}

Generate a JSON response with this structure:
{{
    "role": "Specific role name (e.g., Security Auditor, Frontend Developer)",
    "description": "What this agent will do",
    "required_capabilities": ["capability1", "capability2"],
    "suggested_category": "One of: quick, deep, ultrabrain, visual-engineering",
    "cost_estimate": 0.05,
    "complexity": 0.7
}}

Category guide:
- quick: Simple tasks, low compute (testing, docs, small fixes)
- deep: Moderate complexity requiring analysis (backend, database)
- ultrabrain: Complex multi-step reasoning (security, architecture, AI)
- visual-engineering: UI/UX focused work

Cost should be $0.02-0.15 based on complexity."""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical recruiter analyzing development tasks.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            return JobDescription(
                role=data["role"],
                description=data["description"],
                required_capabilities=data["required_capabilities"],
                suggested_category=data["suggested_category"],
                cost_estimate=data["cost_estimate"],
                complexity=data["complexity"],
            )

        except Exception as e:
            logger.warning(f"LLM JD generation failed, falling back to mock: {e}")
            return self._generate_jd_mock(bead)

    def _generate_employee_id(self, bead: Bead, jd: JobDescription) -> str:
        """Generate a unique employee ID for a new hire."""
        role_slug = jd.role.lower().replace(" ", "-").replace("/", "-")
        return f"{role_slug}-{bead.id}"

    async def post_hire_message(self, bead: Bead, jd: JobDescription) -> dict:
        """
        Send a HIRE message via Slaick to trigger agent spawning.

        Args:
            bead: The bead to be worked on
            jd: The JobDescription for the required agent

        Returns:
            The message dict that was sent
        """
        from datetime import datetime, timezone

        employee_id = self._generate_employee_id(bead, jd)

        payload = {
            "bead_id": bead.id,
            "bead_title": bead.title,
            "employee_id": employee_id,
            "job_description": jd.to_dict(),
            "priority": bead.priority,
        }

        message = self.slaick.append_message(
            from_agent="recruiter",
            to_agent="orchestrator",
            msg_type=MessageType.HIRE,
            payload=payload,
        )

        # Track the employee
        employee = Employee(
            employee_id=employee_id,
            role=jd.role,
            bead_id=bead.id,
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="pending",  # Will become active when agent spawns
        )
        self.employees[bead.id] = employee

        logger.info(f"Posted HIRE message for {employee_id} to handle bead {bead.id}")

        return message

    def release_employee(self, bead_id: str) -> bool:
        """
        Release an employee when their work is complete.

        Args:
            bead_id: The bead ID the employee was working on

        Returns:
            True if employee was released, False if not found
        """
        if bead_id in self.employees:
            employee = self.employees[bead_id]
            employee.status = "completed"
            logger.info(f"Released employee {employee.employee_id} from bead {bead_id}")
            # Keep in dict for audit trail but mark status
            return True
        return False

    def get_active_employee_count(self) -> int:
        """Get count of currently active/pending employees."""
        return sum(
            1 for e in self.employees.values() if e.status in ("active", "pending")
        )

    async def process_bead(self, bead: Bead) -> Optional[JobDescription]:
        """
        Process a single ready bead through the hiring pipeline.

        Args:
            bead: The ready bead to process

        Returns:
            JobDescription if hiring triggered, None if skipped
        """
        if self.has_agent_for_bead(bead):
            logger.debug(f"Skipping bead {bead.id} - already has agent assigned")
            return None

        logger.info(f"Processing bead {bead.id}: {bead.title}")

        # Generate JD
        jd = await self.generate_jd(bead)
        logger.info(
            f"Generated JD for {bead.id}: {jd.role} ({jd.suggested_category}, "
            f"complexity: {jd.complexity}, cost: ${jd.cost_estimate})"
        )

        # Check cost tracker before proceeding
        if self.cost_tracker is not None:
            if not self.cost_tracker.can_afford(jd.cost_estimate, jd.suggested_category):
                logger.warning(
                    f"Cannot afford to hire for bead {bead.id}: "
                    f"cost ${jd.cost_estimate} would exceed budget"
                )
                await self._notify_budget_exceeded(bead, jd)
                return None

        # Post hire message
        await self.post_hire_message(bead, jd)

        # Actually spawn the agent
        try:
            agent_id = await self.spawner.spawn_agent(jd, bead.id)
            logger.info(f"Spawned agent {agent_id} for bead {bead.id}")

            # Record the cost
            if self.cost_tracker is not None:
                self.cost_tracker.record_cost(
                    cost=jd.cost_estimate,
                    agent_id=agent_id,
                    category=jd.suggested_category,
                )

            # Update employee status to active (was pending)
            if bead.id in self.employees:
                self.employees[bead.id].status = "active"
        except Exception as e:
            logger.error(f"Failed to spawn agent for bead {bead.id}: {e}")
            # Mark employee as failed
            if bead.id in self.employees:
                self.employees[bead.id].status = "failed"
            raise

        return jd

    async def _notify_budget_exceeded(self, bead: Bead, jd: JobDescription) -> dict:
        """
        Send an error message when budget is exceeded.

        Args:
            bead: The bead that couldn't be hired for
            jd: The JobDescription that exceeded budget

        Returns:
            The message dict that was sent
        """
        from datetime import datetime, timezone

        payload = {
            "error": "budget_exceeded",
            "bead_id": bead.id,
            "bead_title": bead.title,
            "requested_cost": jd.cost_estimate,
            "category": jd.suggested_category,
        }

        # Add budget info if cost tracker is available
        if self.cost_tracker is not None:
            payload["current_spent"] = self.cost_tracker.get_current_spent()
            payload["budget"] = self.cost_tracker.budget
            payload["remaining"] = self.cost_tracker.get_remaining_budget()

        message = self.slaick.append_message(
            from_agent="recruiter",
            to_agent="ceo",
            msg_type=MessageType.ERROR,
            payload=payload,
        )

        logger.info(f"Sent budget exceeded notification for bead {bead.id}")

        return message

    async def run(self) -> None:
        """
        Main event loop for the Recruiter.

        Continuously polls for ready beads, generates JDs, and triggers hiring.
        Uses adaptive sleep: fast (1s) when work available, slow (5s) when idle.

        Run stop() to terminate the loop gracefully.
        """
        self.running = True
        logger.info("Recruiter event loop started")

        try:
            while self.running:
                ready_beads = get_ready_beads()

                if ready_beads:
                    logger.debug(f"Found {len(ready_beads)} ready beads")

                    for bead in ready_beads:
                        if not self.running:
                            break
                        await self.process_bead(bead)

                    # Fast polling when work available
                    if self.running:
                        await asyncio.sleep(self.fast_poll_interval)
                else:
                    # Slow polling when idle
                    if self.running:
                        await asyncio.sleep(self.slow_poll_interval)

        except asyncio.CancelledError:
            logger.info("Recruiter event loop cancelled")
        except Exception as e:
            logger.error(f"Error in Recruiter event loop: {e}")
            raise
        finally:
            logger.info("Recruiter event loop stopped")

    def stop(self) -> None:
        """Signal the event loop to stop gracefully."""
        self.running = False
        logger.info("Recruiter stop signal received")


async def run_recruiter(
    slaick: Optional[Slaick] = None,
    use_llm: bool = False,
    duration: Optional[float] = None,
) -> Recruiter:
    """
    Convenience function to run the recruiter.

    Args:
        slaick: Optional Slaick instance
        use_llm: Whether to use OpenAI API
        duration: If set, run for this many seconds then stop

    Returns:
        The Recruiter instance after it stops
    """
    recruiter = Recruiter(slaick=slaick, use_llm=use_llm)

    if duration:
        # Run for specified duration
        task = asyncio.create_task(recruiter.run())
        await asyncio.sleep(duration)
        recruiter.stop()
        try:
            await task
        except asyncio.CancelledError:
            pass
    else:
        await recruiter.run()

    return recruiter
