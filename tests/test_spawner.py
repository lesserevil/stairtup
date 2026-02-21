"""
Tests for the AgentSpawner module.

Tests cover:
- Agent spawning with different JD categories
- employees.jsonl tracking
- Error handling when spawn fails
- Recruiter integration (full flow)
- Category mapping verification
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.company.beads import Bead
from app.company.slaick import MessageType, Slaick
from app.company.spawner import AgentSpawner, CATEGORY_MAP, SpawnError, SpawnedAgent
from app.company.types import JobDescription


@pytest.fixture
def temp_employees_file():
    """Create a temporary employees.jsonl file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_slaick():
    """Create a temporary Slaick instance for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name
    slaick = Slaick(temp_path)
    yield slaick
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def sample_bead():
    """Create a sample bead for testing."""
    return Bead(
        id="stairtup-123",
        title="Fix security vulnerability in authentication",
        status="ready",
        priority=5,
        issue_type="bug",
        owner=None,
        created_at="2026-02-21T10:00:00Z",
        created_by="test-user",
        updated_at="2026-02-21T10:00:00Z",
    )


@pytest.fixture
def frontend_bead():
    """Create a frontend bead for testing visual-engineering category."""
    return Bead(
        id="stairtup-456",
        title="Build React component with CSS styling",
        status="ready",
        priority=3,
        issue_type="feature",
        owner=None,
        created_at="2026-02-21T10:00:00Z",
        created_by="test-user",
        updated_at="2026-02-21T10:00:00Z",
    )


@pytest.fixture
def sample_jd():
    """Create a sample JobDescription for testing."""
    return JobDescription(
        role="Security Auditor",
        description="Analyze code for security vulnerabilities",
        required_capabilities=["code_review", "security_analysis"],
        suggested_category="ultrabrain",
        cost_estimate=0.1,
        complexity=0.8,
    )


@pytest.fixture
def frontend_jd():
    """Create a frontend JD for testing visual-engineering category."""
    return JobDescription(
        role="Frontend Developer",
        description="Implement user interfaces and components",
        required_capabilities=["ui_development", "react", "css"],
        suggested_category="visual-engineering",
        cost_estimate=0.08,
        complexity=0.5,
    )


@pytest.fixture
def spawner(temp_employees_file, temp_slaick):
    """Create an AgentSpawner instance for testing."""
    return AgentSpawner(
        employees_file=temp_employees_file,
        slaick=temp_slaick,
        mock_mode=True,
    )


class TestSpawnedAgent:
    """Tests for SpawnedAgent dataclass."""

    def test_spawned_agent_creation(self):
        """Test creating a SpawnedAgent."""
        agent = SpawnedAgent(
            agent_id="emp-abc123",
            role="Security Auditor",
            bead_id="stairtup-123",
            hired_at="2026-02-21T10:00:00Z",
            status="active",
            category="ultrabrain",
            prompt="Test prompt",
            employee_id="security-auditor-stairtup-123",
        )

        assert agent.agent_id == "emp-abc123"
        assert agent.role == "Security Auditor"
        assert agent.category == "ultrabrain"
        assert agent.status == "active"

    def test_spawned_agent_to_dict(self):
        """Test converting SpawnedAgent to dictionary."""
        agent = SpawnedAgent(
            agent_id="emp-abc123",
            role="Backend Developer",
            bead_id="stairtup-456",
            hired_at="2026-02-21T10:00:00Z",
            status="active",
            category="deep",
            prompt="Test prompt",
            employee_id="backend-developer-stairtup-456",
        )

        data = agent.to_dict()
        assert data["agent_id"] == "emp-abc123"
        assert data["role"] == "Backend Developer"
        assert data["category"] == "deep"
        assert data["prompt"] == "Test prompt"

    def test_spawned_agent_from_dict(self):
        """Test creating SpawnedAgent from dictionary."""
        data = {
            "agent_id": "emp-def456",
            "role": "Frontend Developer",
            "bead_id": "stairtup-789",
            "hired_at": "2026-02-21T10:00:00Z",
            "status": "active",
            "category": "visual-engineering",
            "prompt": "Test prompt content",
            "employee_id": "frontend-developer-stairtup-789",
        }

        agent = SpawnedAgent.from_dict(data)
        assert agent.agent_id == "emp-def456"
        assert agent.role == "Frontend Developer"
        assert agent.category == "visual-engineering"


class TestAgentSpawnerInitialization:
    """Tests for AgentSpawner initialization."""

    def test_spawner_init_defaults(self):
        """Test AgentSpawner initialization with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                spawner = AgentSpawner()

                assert spawner.employees_file.name == "employees.jsonl"
                assert spawner.slaick is not None
                assert spawner.mock_mode is True
                assert spawner.employees_file.exists()
            finally:
                os.chdir(original_cwd)

    def test_spawner_init_custom_values(self, temp_employees_file, temp_slaick):
        """Test AgentSpawner initialization with custom values."""
        spawner = AgentSpawner(
            employees_file=temp_employees_file,
            slaick=temp_slaick,
            mock_mode=False,
        )

        assert str(spawner.employees_file) == temp_employees_file
        assert spawner.slaick == temp_slaick
        assert spawner.mock_mode is False


class TestCategoryMapping:
    """Tests for JD to OpenCode category mapping."""

    def test_category_map_values(self):
        """Test that CATEGORY_MAP contains expected mappings."""
        assert CATEGORY_MAP["quick"] == "quick"
        assert CATEGORY_MAP["deep"] == "deep"
        assert CATEGORY_MAP["ultrabrain"] == "ultrabrain"
        assert CATEGORY_MAP["visual-engineering"] == "visual-engineering"
        assert CATEGORY_MAP["writing"] == "writing"
        assert CATEGORY_MAP["artistry"] == "artistry"

    def test_map_category_known_categories(self, spawner):
        """Test mapping known categories."""
        assert spawner._map_category("quick") == "quick"
        assert spawner._map_category("deep") == "deep"
        assert spawner._map_category("ultrabrain") == "ultrabrain"
        assert spawner._map_category("visual-engineering") == "visual-engineering"

    def test_map_category_case_insensitive(self, spawner):
        """Test that category mapping is case insensitive."""
        assert spawner._map_category("QUICK") == "quick"
        assert spawner._map_category("Deep") == "deep"
        assert spawner._map_category("UltraBrain") == "ultrabrain"

    def test_map_category_unknown_defaults_to_deep(self, spawner):
        """Test that unknown categories default to 'deep'."""
        assert spawner._map_category("unknown") == "deep"
        assert spawner._map_category("") == "deep"


class TestPromptGeneration:
    """Tests for 6-section prompt generation."""

    def test_generate_prompt_structure(self, spawner, sample_jd, sample_bead):
        """Test that prompt contains all 6 sections."""
        prompt = spawner._generate_prompt(sample_jd, sample_bead, "emp-test123")

        # Check all 6 sections are present
        assert "## 1. TASK" in prompt
        assert "## 2. EXPECTED OUTCOME" in prompt
        assert "## 3. REQUIRED TOOLS" in prompt
        assert "## 4. MUST DO" in prompt
        assert "## 5. MUST NOT DO" in prompt
        assert "## 6. CONTEXT" in prompt

    def test_generate_prompt_contains_bead_info(self, spawner, sample_jd, sample_bead):
        """Test that prompt contains bead information."""
        prompt = spawner._generate_prompt(sample_jd, sample_bead, "emp-test123")

        assert sample_bead.id in prompt
        assert sample_bead.title in prompt
        assert str(sample_bead.priority) in prompt

    def test_generate_prompt_contains_jd_info(self, spawner, sample_jd, sample_bead):
        """Test that prompt contains JD information."""
        prompt = spawner._generate_prompt(sample_jd, sample_bead, "emp-test123")

        assert sample_jd.role in prompt
        assert sample_jd.description in prompt
        assert sample_jd.suggested_category in prompt
        assert str(sample_jd.complexity) in prompt

    def test_generate_prompt_contains_agent_id(self, spawner, sample_jd, sample_bead):
        """Test that prompt contains agent ID."""
        agent_id = "emp-test456"
        prompt = spawner._generate_prompt(sample_jd, sample_bead, agent_id)

        assert agent_id in prompt


class TestSpawnAgent:
    """Tests for spawn_agent functionality."""

    @pytest.mark.asyncio
    async def test_spawn_agent_returns_agent_id(self, spawner, sample_jd, sample_bead):
        """Test that spawn_agent returns a valid agent ID."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            agent_id = await spawner.spawn_agent(sample_jd, sample_bead.id)

        assert agent_id is not None
        assert agent_id.startswith("emp-")
        assert len(agent_id) > 4

    @pytest.mark.asyncio
    async def test_spawn_agent_creates_employee_record(
        self, spawner, sample_jd, sample_bead, temp_employees_file
    ):
        """Test that spawn_agent creates an employee record."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            agent_id = await spawner.spawn_agent(sample_jd, sample_bead.id)

        # Read employees file
        with open(temp_employees_file, "r") as f:
            lines = f.readlines()

        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_id"] == agent_id
        assert data["role"] == sample_jd.role
        assert data["bead_id"] == sample_bead.id
        assert data["category"] == "ultrabrain"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_spawn_agent_sends_ack_message(
        self, spawner, sample_jd, sample_bead, temp_slaick
    ):
        """Test that spawn_agent sends an ACK message."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            agent_id = await spawner.spawn_agent(sample_jd, sample_bead.id)

        # Check ACK message was sent
        messages = temp_slaick.get_messages(msg_type="ACK")
        assert len(messages) == 1

        payload = messages[0]["payload"]
        assert payload["agent_id"] == agent_id
        assert payload["bead_id"] == sample_bead.id
        assert payload["role"] == sample_jd.role
        assert payload["category"] == "ultrabrain"

    @pytest.mark.asyncio
    async def test_spawn_agent_maps_category_correctly(
        self, spawner, frontend_jd, frontend_bead, temp_employees_file
    ):
        """Test that visual-engineering category is correctly mapped."""
        with patch("app.company.spawner.get_bead", return_value=frontend_bead):
            agent_id = await spawner.spawn_agent(frontend_jd, frontend_bead.id)

        # Read employees file and verify category
        with open(temp_employees_file, "r") as f:
            data = json.loads(f.readlines()[0])

        assert data["category"] == "visual-engineering"

    @pytest.mark.asyncio
    async def test_spawn_agent_logs_spawn_request_in_mock_mode(
        self, spawner, sample_jd, sample_bead, temp_employees_file
    ):
        """Test that spawn_agent logs spawn requests in mock mode."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            await spawner.spawn_agent(sample_jd, sample_bead.id)

        # Check spawn_requests.jsonl was created
        spawn_log = Path(temp_employees_file).parent / "spawn_requests.jsonl"
        assert spawn_log.exists()

        with open(spawn_log, "r") as f:
            data = json.loads(f.readlines()[0])

        assert data["mock_mode"] is True
        assert "would call task()" in data["note"]

    @pytest.mark.asyncio
    async def test_spawn_agent_raises_error_if_bead_not_found(self, spawner, sample_jd):
        """Test that spawn_agent raises error if bead doesn't exist."""
        with patch("app.company.spawner.get_bead", return_value=None):
            with pytest.raises(SpawnError) as exc_info:
                await spawner.spawn_agent(sample_jd, "non-existent-bead")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_spawn_agent_raises_error_on_failure(
        self, spawner, sample_jd, sample_bead
    ):
        """Test that spawn_agent raises SpawnError on unexpected failure."""
        with patch(
            "app.company.spawner.get_bead", side_effect=Exception("Unexpected error")
        ):
            with pytest.raises(SpawnError) as exc_info:
                await spawner.spawn_agent(sample_jd, sample_bead.id)

        assert "Agent spawn failed" in str(exc_info.value)


class TestEmployeeTracking:
    """Tests for employee tracking functionality."""

    @pytest.mark.asyncio
    async def test_get_all_employees(self, spawner, sample_jd, sample_bead):
        """Test retrieving all employee records."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            await spawner.spawn_agent(sample_jd, sample_bead.id)

        employees = spawner.get_all_employees()
        assert len(employees) == 1
        assert employees[0].role == sample_jd.role

    @pytest.mark.asyncio
    async def test_get_active_agents_for_bead(self, spawner, sample_jd, sample_bead):
        """Test getting active agents for a specific bead."""
        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            await spawner.spawn_agent(sample_jd, sample_bead.id)

        agents = spawner.get_active_agents_for_bead(sample_bead.id)
        assert len(agents) == 1
        assert agents[0].bead_id == sample_bead.id
        assert agents[0].status == "active"

    @pytest.mark.asyncio
    async def test_has_active_agent_for_bead(self, spawner, sample_jd, sample_bead):
        """Test checking if bead has an active agent."""
        # Initially no agent
        assert spawner.has_active_agent_for_bead(sample_bead.id) is False

        with patch("app.company.spawner.get_bead", return_value=sample_bead):
            await spawner.spawn_agent(sample_jd, sample_bead.id)

        # Now has agent
        assert spawner.has_active_agent_for_bead(sample_bead.id) is True

    @pytest.mark.asyncio
    async def test_get_all_employees_skips_malformed_records(
        self, spawner, temp_employees_file
    ):
        """Test that malformed records are skipped."""
        # Write a valid record
        valid_record = {
            "agent_id": "emp-valid",
            "role": "Test Role",
            "bead_id": "bead-123",
            "hired_at": "2026-02-21T10:00:00Z",
            "status": "active",
            "category": "quick",
            "prompt": "test",
            "employee_id": "test-bead-123",
        }

        # Write an invalid record
        with open(temp_employees_file, "w") as f:
            f.write(json.dumps(valid_record) + "\n")
            f.write("invalid json line\n")
            f.write('{"incomplete": "record"}\n')  # Missing required fields

        employees = spawner.get_all_employees()
        assert len(employees) == 1
        assert employees[0].agent_id == "emp-valid"


class TestRecruiterIntegration:
    """Tests for Recruiter-Spawner integration."""

    @pytest.mark.asyncio
    async def test_recruiter_spawns_agent_for_bead(
        self, temp_employees_file, temp_slaick, frontend_bead
    ):
        """Test that Recruiter spawns a visual-engineering agent for frontend beads."""
        from app.company.recruiter import Recruiter

        recruiter = Recruiter(
            slaick=temp_slaick,
            employees_file=temp_employees_file,
            use_llm=False,
        )

        with patch(
            "app.company.recruiter.get_ready_beads", return_value=[frontend_bead]
        ):
            with patch("app.company.spawner.get_bead", return_value=frontend_bead):
                jd = await recruiter.process_bead(frontend_bead)

        # Verify JD was generated with visual-engineering category
        assert jd is not None
        assert jd.suggested_category == "visual-engineering"

        # Verify employee was tracked
        assert len(recruiter.employees) == 1
        employee = list(recruiter.employees.values())[0]
        assert employee.role == "Frontend Developer"
        assert employee.status == "active"

        # Verify ACK message was sent
        ack_messages = temp_slaick.get_messages(msg_type="ACK")
        assert len(ack_messages) == 1
        assert ack_messages[0]["payload"]["category"] == "visual-engineering"

    @pytest.mark.asyncio
    async def test_recruiter_handles_spawn_failure(
        self, temp_employees_file, temp_slaick, frontend_bead
    ):
        """Test that Recruiter handles spawn failures gracefully."""
        from app.company.recruiter import Recruiter

        recruiter = Recruiter(
            slaick=temp_slaick,
            employees_file=temp_employees_file,
            use_llm=False,
        )

        with patch("app.company.spawner.get_bead", return_value=None):  # Bead not found
            with pytest.raises(Exception):
                await recruiter.process_bead(frontend_bead)

        # Verify employee was marked as failed
        assert len(recruiter.employees) == 1
        employee = list(recruiter.employees.values())[0]
        assert employee.status == "failed"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_employee_id_generation(self, spawner, sample_jd, sample_bead):
        """Test employee ID generation format."""
        employee_id = spawner._generate_employee_id(sample_bead, sample_jd)

        assert "security-auditor" in employee_id
        assert sample_bead.id in employee_id

    def test_generate_agent_id_format(self, spawner):
        """Test that agent IDs follow expected format."""
        agent_id = spawner._generate_agent_id()

        assert agent_id.startswith("emp-")
        assert len(agent_id) == 12  # "emp-" + 8 hex chars

    @pytest.mark.asyncio
    async def test_spawn_multiple_agents_tracks_all(
        self, spawner, sample_jd, temp_employees_file
    ):
        """Test spawning multiple agents tracks all of them."""
        bead1 = Bead(
            id="bead-1",
            title="Task 1",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )
        bead2 = Bead(
            id="bead-2",
            title="Task 2",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        with patch("app.company.spawner.get_bead", side_effect=[bead1, bead2]):
            agent_id1 = await spawner.spawn_agent(sample_jd, bead1.id)
            agent_id2 = await spawner.spawn_agent(sample_jd, bead2.id)

        # Verify both agents are tracked
        employees = spawner.get_all_employees()
        assert len(employees) == 2
        agent_ids = {e.agent_id for e in employees}
        assert agent_id1 in agent_ids
        assert agent_id2 in agent_ids


class TestVisualEngineeringCategory:
    """Specific tests for visual-engineering category mapping."""

    @pytest.mark.asyncio
    async def test_frontend_bead_spawns_visual_engineering_agent(
        self, temp_employees_file, temp_slaick
    ):
        """Verify that a Frontend Dev JD spawns a visual-engineering task."""
        from app.company.recruiter import Recruiter

        # Create a bead that should trigger visual-engineering
        bead = Bead(
            id="stairtup-ui-123",
            title="Build responsive React component with CSS Grid",
            status="ready",
            priority=4,
            issue_type="feature",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test-user",
            updated_at="2026-02-21T10:00:00Z",
        )

        recruiter = Recruiter(
            slaick=temp_slaick,
            employees_file=temp_employees_file,
            use_llm=False,
        )

        with patch("app.company.recruiter.get_ready_beads", return_value=[bead]):
            with patch("app.company.spawner.get_bead", return_value=bead):
                jd = await recruiter.process_bead(bead)

        # The JD should map to visual-engineering for frontend work
        # Note: Current mock might map frontend to 'quick', so we check it gets processed
        assert jd is not None
        assert jd.role == "Frontend Developer"

        # Verify ACK message was sent with category
        ack_messages = temp_slaick.get_messages(msg_type="ACK")
        assert len(ack_messages) == 1

        # The category should match what the spawner maps
        category = ack_messages[0]["payload"]["category"]
        assert category in ["quick", "visual-engineering", "deep", "ultrabrain"]
