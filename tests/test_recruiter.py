"""
Tests for the Recruiter agent and Job Description generation system.

Tests cover:
- JD generation with rule-based mock
- Employee tracking and capacity management
- Adaptive polling loop behavior
- HIRE message posting via Slaick
- Integration with beads and slaick modules
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.company.beads import Bead
from app.company.recruiter import (
    Employee,
    JobDescription,
    Recruiter,
    run_recruiter,
)
from app.company.slaick import MessageType, Slaick


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
def sample_beads():
    """Create multiple sample beads for testing."""
    return [
        Bead(
            id="stairtup-1",
            title="Fix security vulnerability in auth",
            status="ready",
            priority=5,
            issue_type="bug",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test-user",
            updated_at="2026-02-21T10:00:00Z",
        ),
        Bead(
            id="stairtup-2",
            title="Build new React component for dashboard",
            status="ready",
            priority=3,
            issue_type="feature",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test-user",
            updated_at="2026-02-21T10:00:00Z",
        ),
        Bead(
            id="stairtup-3",
            title="Write unit tests for API endpoints",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test-user",
            updated_at="2026-02-21T10:00:00Z",
        ),
    ]


@pytest.fixture
def recruiter(temp_slaick):
    """Create a Recruiter instance for testing."""
    return Recruiter(
        slaick=temp_slaick,
        fast_poll_interval=0.01,  # Fast for tests
        slow_poll_interval=0.05,  # Fast for tests
        use_llm=False,
    )


class TestJobDescription:
    """Tests for JobDescription dataclass."""

    def test_job_description_creation(self):
        """Test creating a JobDescription."""
        jd = JobDescription(
            role="Security Auditor",
            description="Analyze code for security vulnerabilities",
            required_capabilities=["code_review", "security_analysis"],
            suggested_category="ultrabrain",
            cost_estimate=0.08,
            complexity=0.75,
        )

        assert jd.role == "Security Auditor"
        assert jd.suggested_category == "ultrabrain"
        assert jd.complexity == 0.75

    def test_job_description_to_dict(self):
        """Test converting JobDescription to dictionary."""
        jd = JobDescription(
            role="Backend Developer",
            description="Build APIs",
            required_capabilities=["api_design"],
            suggested_category="deep",
            cost_estimate=0.05,
            complexity=0.6,
        )

        data = jd.to_dict()
        assert data["role"] == "Backend Developer"
        assert data["suggested_category"] == "deep"
        assert data["required_capabilities"] == ["api_design"]

    def test_job_description_from_dict(self):
        """Test creating JobDescription from dictionary."""
        data = {
            "role": "Frontend Developer",
            "description": "Build UI components",
            "required_capabilities": ["react", "css"],
            "suggested_category": "quick",
            "cost_estimate": 0.03,
            "complexity": 0.4,
        }

        jd = JobDescription.from_dict(data)
        assert jd.role == "Frontend Developer"
        assert jd.suggested_category == "quick"
        assert len(jd.required_capabilities) == 2


class TestRecruiterInitialization:
    """Tests for Recruiter initialization."""

    def test_recruiter_init_defaults(self, temp_slaick):
        """Test Recruiter initialization with defaults."""
        recruiter = Recruiter(slaick=temp_slaick)

        assert recruiter.running is False
        assert recruiter.slaick == temp_slaick
        assert recruiter.employees == {}
        assert recruiter.fast_poll_interval == 1.0
        assert recruiter.slow_poll_interval == 5.0
        assert recruiter.use_llm is False

    def test_recruiter_init_custom_values(self, temp_slaick):
        """Test Recruiter initialization with custom values."""
        recruiter = Recruiter(
            slaick=temp_slaick,
            fast_poll_interval=0.5,
            slow_poll_interval=2.0,
            use_llm=False,  # Won't enable without API key
        )

        assert recruiter.fast_poll_interval == 0.5
        assert recruiter.slow_poll_interval == 2.0

    def test_recruiter_creates_default_slaick(self):
        """Test that Recruiter creates default Slaick if none provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                recruiter = Recruiter()
                assert recruiter.slaick is not None
                assert recruiter.slaick.file_path.name == "slaick.jsonl"
            finally:
                os.chdir(original_cwd)

    def test_recruiter_llm_requires_api_key(self, temp_slaick):
        """Test that use_llm requires OPENAI_API_KEY."""
        # Ensure no API key is set
        with patch.dict(os.environ, {}, clear=True):
            recruiter = Recruiter(slaick=temp_slaick, use_llm=True)
            assert recruiter.use_llm is False


class TestEmployeeTracking:
    """Tests for employee tracking functionality."""

    def test_has_agent_for_bead(self, recruiter, sample_bead):
        """Test checking if bead has assigned agent."""
        assert recruiter.has_agent_for_bead(sample_bead) is False

        # Add employee manually
        recruiter.employees[sample_bead.id] = Employee(
            employee_id="test-agent",
            role="Test Role",
            bead_id=sample_bead.id,
            hired_at=datetime.now(timezone.utc).isoformat(),
        )

        assert recruiter.has_agent_for_bead(sample_bead) is True

    def test_get_active_employee_count(self, recruiter):
        """Test counting active employees."""
        assert recruiter.get_active_employee_count() == 0

        # Add active employees
        recruiter.employees["bead-1"] = Employee(
            employee_id="agent-1",
            role="Role 1",
            bead_id="bead-1",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )
        recruiter.employees["bead-2"] = Employee(
            employee_id="agent-2",
            role="Role 2",
            bead_id="bead-2",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="pending",
        )
        recruiter.employees["bead-3"] = Employee(
            employee_id="agent-3",
            role="Role 3",
            bead_id="bead-3",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
        )

        # Should count active and pending, not completed
        assert recruiter.get_active_employee_count() == 2

    def test_release_employee(self, recruiter):
        """Test releasing an employee."""
        recruiter.employees["bead-123"] = Employee(
            employee_id="agent-1",
            role="Test Role",
            bead_id="bead-123",
            hired_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )

        result = recruiter.release_employee("bead-123")
        assert result is True
        assert recruiter.employees["bead-123"].status == "completed"

    def test_release_employee_not_found(self, recruiter):
        """Test releasing non-existent employee."""
        result = recruiter.release_employee("non-existent")
        assert result is False


class TestJDGenerationMock:
    """Tests for rule-based mock JD generation."""

    @pytest.mark.asyncio
    async def test_generate_jd_security_bead(self, recruiter):
        """Test JD generation for security-related bead."""
        bead = Bead(
            id="test-1",
            title="Audit security vulnerabilities in auth module",
            status="ready",
            priority=5,
            issue_type="bug",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "Security Auditor"
        assert jd.suggested_category == "ultrabrain"
        assert "security_analysis" in jd.required_capabilities
        assert 0.0 <= jd.complexity <= 1.0
        assert 0.0 <= jd.cost_estimate <= 1.0

    @pytest.mark.asyncio
    async def test_generate_jd_frontend_bead(self, recruiter):
        """Test JD generation for frontend bead."""
        bead = Bead(
            id="test-1",
            title="Build new React component with CSS styling",
            status="ready",
            priority=3,
            issue_type="feature",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "Frontend Developer"
        assert jd.suggested_category == "visual-engineering"
        assert "ui_development" in jd.required_capabilities

    @pytest.mark.asyncio
    async def test_generate_jd_backend_bead(self, recruiter):
        """Test JD generation for backend bead."""
        bead = Bead(
            id="test-1",
            title="Create API endpoint for database queries",
            status="ready",
            priority=4,
            issue_type="feature",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "Backend Developer"
        assert jd.suggested_category == "deep"
        assert "api_design" in jd.required_capabilities

    @pytest.mark.asyncio
    async def test_generate_jd_testing_bead(self, recruiter):
        """Test JD generation for testing bead."""
        bead = Bead(
            id="test-1",
            title="Write pytest unit tests for coverage",
            status="ready",
            priority=2,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "QA Engineer"
        assert jd.suggested_category == "quick"
        assert "test_automation" in jd.required_capabilities

    @pytest.mark.asyncio
    async def test_generate_jd_docs_bead(self, recruiter):
        """Test JD generation for documentation bead."""
        bead = Bead(
            id="test-1",
            title="Write documentation for API endpoints",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "Technical Writer"
        assert jd.suggested_category == "quick"
        assert "technical_writing" in jd.required_capabilities

    @pytest.mark.asyncio
    async def test_generate_jd_default(self, recruiter):
        """Test JD generation for unmatched bead."""
        bead = Bead(
            id="test-1",
            title="Some generic task",
            status="ready",
            priority=3,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        assert jd.role == "Software Engineer"
        assert jd.suggested_category == "deep"

    @pytest.mark.asyncio
    async def test_generate_jd_complexity_based_on_priority(self, recruiter):
        """Test that complexity scales with priority."""
        low_priority_bead = Bead(
            id="test-1",
            title="Security audit",
            status="ready",
            priority=1,
            issue_type="bug",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )
        high_priority_bead = Bead(
            id="test-2",
            title="Security audit",
            status="ready",
            priority=10,
            issue_type="bug",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd_low = await recruiter.generate_jd(low_priority_bead)
        jd_high = await recruiter.generate_jd(high_priority_bead)

        # Higher priority should generally result in higher complexity
        assert jd_high.complexity >= jd_low.complexity


class TestHireMessaging:
    """Tests for HIRE message posting."""

    @pytest.mark.asyncio
    async def test_post_hire_message(self, recruiter, temp_slaick, sample_bead):
        """Test posting a HIRE message."""
        jd = JobDescription(
            role="Security Auditor",
            description="Analyze security",
            required_capabilities=["security"],
            suggested_category="ultrabrain",
            cost_estimate=0.1,
            complexity=0.8,
        )

        message = await recruiter.post_hire_message(sample_bead, jd)

        # Verify message structure
        assert message["from"] == "recruiter"
        assert message["to"] == "orchestrator"
        assert message["type"] == "HIRE"
        assert "payload" in message

        # Verify payload
        payload = message["payload"]
        assert payload["bead_id"] == sample_bead.id
        assert payload["bead_title"] == sample_bead.title
        assert payload["employee_id"] == "security-auditor-stairtup-123"
        assert payload["job_description"]["role"] == "Security Auditor"
        assert payload["priority"] == sample_bead.priority

    @pytest.mark.asyncio
    async def test_post_hire_message_tracks_employee(self, recruiter, sample_bead):
        """Test that posting HIRE message tracks the employee."""
        jd = JobDescription(
            role="Backend Developer",
            description="Build APIs",
            required_capabilities=["api"],
            suggested_category="deep",
            cost_estimate=0.05,
            complexity=0.6,
        )

        await recruiter.post_hire_message(sample_bead, jd)

        # Verify employee was tracked
        assert sample_bead.id in recruiter.employees
        employee = recruiter.employees[sample_bead.id]
        assert employee.role == "Backend Developer"
        assert employee.status == "pending"
        assert employee.bead_id == sample_bead.id

    @pytest.mark.asyncio
    async def test_post_hire_message_writes_to_slaick(
        self, recruiter, temp_slaick, sample_bead
    ):
        """Test that HIRE message is written to Slaick file."""
        jd = JobDescription(
            role="Test Role",
            description="Test description",
            required_capabilities=["test"],
            suggested_category="quick",
            cost_estimate=0.02,
            complexity=0.3,
        )

        await recruiter.post_hire_message(sample_bead, jd)

        # Read messages from Slaick
        messages = temp_slaick.get_messages(msg_type="HIRE")
        assert len(messages) == 1
        assert messages[0]["payload"]["bead_id"] == sample_bead.id


class TestProcessBead:
    """Tests for bead processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_bead_generates_jd_and_posts(self, recruiter, sample_bead):
        """Test processing a bead generates JD and posts HIRE message."""
        with patch.object(
            recruiter, "post_hire_message", new_callable=AsyncMock
        ) as mock_post:
            with patch("app.company.spawner.get_bead", return_value=sample_bead):
                jd = await recruiter.process_bead(sample_bead)

                assert jd is not None
                assert jd.role is not None
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_bead_skips_if_has_agent(self, recruiter, sample_bead):
        """Test that processing skips beads that already have agents."""
        # Pre-assign agent
        recruiter.employees[sample_bead.id] = Employee(
            employee_id="existing-agent",
            role="Existing Role",
            bead_id=sample_bead.id,
            hired_at=datetime.now(timezone.utc).isoformat(),
        )

        with patch.object(
            recruiter, "post_hire_message", new_callable=AsyncMock
        ) as mock_post:
            jd = await recruiter.process_bead(sample_bead)

            assert jd is None
            mock_post.assert_not_called()


class TestAdaptivePolling:
    """Tests for adaptive polling loop behavior."""

    @pytest.mark.asyncio
    async def test_fast_poll_when_work_available(self, recruiter):
        """Test that polling is fast when work is available."""
        recruiter.fast_poll_interval = 0.01
        recruiter.slow_poll_interval = 0.5

        # Mock get_ready_beads to return beads
        bead = Bead(
            id="test-1",
            title="Test bead",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        loop_count = 0
        start_time = asyncio.get_event_loop().time()

        async def mock_process_bead(b):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                recruiter.stop()
            return None

        recruiter.process_bead = mock_process_bead

        with patch("app.company.recruiter.get_ready_beads", return_value=[bead]):
            await recruiter.run()

        elapsed = asyncio.get_event_loop().time() - start_time
        # Should complete quickly with fast polling
        assert elapsed < 0.5  # Much less than slow_poll_interval

    @pytest.mark.asyncio
    async def test_slow_poll_when_idle(self, recruiter):
        """Test that polling is slow when no work is available."""
        recruiter.fast_poll_interval = 0.01
        recruiter.slow_poll_interval = 0.05

        loop_count = 0
        start_time = asyncio.get_event_loop().time()

        original_sleep = asyncio.sleep

        async def counting_sleep(duration):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                recruiter.stop()
            await original_sleep(duration)

        with patch("app.company.recruiter.get_ready_beads", return_value=[]):
            with patch("asyncio.sleep", side_effect=counting_sleep):
                await recruiter.run()

        elapsed = asyncio.get_event_loop().time() - start_time
        # Should use slow polling intervals
        assert loop_count >= 2

    @pytest.mark.asyncio
    async def test_stop_gracefully(self, recruiter):
        """Test that stop() gracefully stops the event loop."""
        recruiter.fast_poll_interval = 0.01
        recruiter.slow_poll_interval = 0.05

        async def stop_after_delay():
            await asyncio.sleep(0.05)
            recruiter.stop()

        with patch("app.company.recruiter.get_ready_beads", return_value=[]):
            stop_task = asyncio.create_task(stop_after_delay())
            await recruiter.run()
            await stop_task

        assert recruiter.running is False


class TestRunRecruiter:
    """Tests for the run_recruiter convenience function."""

    @pytest.mark.asyncio
    async def test_run_recruiter_with_duration(self, temp_slaick):
        """Test running recruiter for a specific duration."""
        with patch("app.company.recruiter.get_ready_beads", return_value=[]):
            recruiter = await run_recruiter(
                slaick=temp_slaick,
                duration=0.05,  # Run for 50ms
            )

        assert recruiter.running is False


class TestIntegration:
    """Integration tests for the full recruiter flow."""

    @pytest.mark.asyncio
    async def test_full_flow_with_mock_beads(
        self, recruiter, temp_slaick, sample_beads
    ):
        """Test complete flow: poll -> generate JD -> post HIRE."""
        with patch("app.company.recruiter.get_ready_beads", return_value=sample_beads):
            with patch("app.company.spawner.get_bead", side_effect=sample_beads):
                # Process all beads
                for bead in sample_beads:
                    await recruiter.process_bead(bead)

        # Verify employees were tracked
        assert len(recruiter.employees) == 3

        # Verify HIRE messages were posted
        messages = temp_slaick.get_messages(msg_type="HIRE")
        assert len(messages) == 3

        # Verify different roles were assigned based on bead content
        roles = {msg["payload"]["job_description"]["role"] for msg in messages}
        assert "Security Auditor" in roles  # From security bead
        assert "Frontend Developer" in roles  # From frontend bead

    @pytest.mark.asyncio
    async def test_no_duplicate_hires(self, recruiter, temp_slaick, sample_bead):
        """Test that same bead doesn't get hired twice."""
        with patch("app.company.recruiter.get_ready_beads", return_value=[sample_bead]):
            with patch("app.company.spawner.get_bead", return_value=sample_bead):
                # Process same bead twice
                await recruiter.process_bead(sample_bead)
                await recruiter.process_bead(sample_bead)

        # Should only have one employee and one message
        assert len(recruiter.employees) == 1
        messages = temp_slaick.get_messages(msg_type="HIRE")
        assert len(messages) == 1


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_generate_jd_with_empty_title(self, recruiter):
        """Test JD generation with minimal bead data."""
        bead = Bead(
            id="test-1",
            title="",
            status="ready",
            priority=1,
            issue_type="task",
            owner=None,
            created_at="2026-02-21T10:00:00Z",
            created_by="test",
            updated_at="2026-02-21T10:00:00Z",
        )

        jd = await recruiter.generate_jd(bead)

        # Should still return a valid JD with defaults
        assert jd.role is not None
        assert jd.suggested_category is not None
        assert 0.0 <= jd.complexity <= 1.0

    @pytest.mark.asyncio
    async def test_employee_id_generation(self, recruiter, sample_bead):
        """Test employee ID generation format."""
        jd = JobDescription(
            role="AI/ML Engineer",
            description="Build AI models",
            required_capabilities=["ai"],
            suggested_category="ultrabrain",
            cost_estimate=0.15,
            complexity=0.9,
        )

        employee_id = recruiter._generate_employee_id(sample_bead, jd)

        # Should contain role slug and bead ID
        assert "ai-ml-engineer" in employee_id
        assert sample_bead.id in employee_id

    def test_bead_content_analysis(self, recruiter, sample_bead):
        """Test bead content analysis extracts keywords."""
        analysis = recruiter._analyze_bead_content(sample_bead)

        assert "keywords" in analysis
        assert "security" in analysis["keywords"]
        assert "estimated_complexity" in analysis
        assert 0.0 <= analysis["estimated_complexity"] <= 1.0
