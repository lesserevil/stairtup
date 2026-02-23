# Contributing to Agent Company Swarm

Thank you for your interest in contributing! This project is a self-organizing multi-agent company system. Whether you're fixing bugs, adding features, improving documentation, or spreading the word, your contribution matters.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Environment](#development-environment)
3. [How to Contribute](#how-to-contribute)
4. [Development Workflow](#development-workflow)
5. [Code Style](#code-style)
6. [Testing Guidelines](#testing-guidelines)
7. [Issue Reporting](#issue-reporting)
8. [Community Guidelines](#community-guidelines)

---

## Getting Started

### Prerequisites

- **Python 3.12+** - Required for the project
- **Beads CLI**: `bd` command-line tool for issue tracking
- **OpenCode** - Required for agent task execution
- **Git** - For version control
- **Docker & Docker Compose** - Optional, for production deployment

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/lesserevil/stairtup.git
   cd stairtup
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

4. Initialize the project:
   ```bash
   bd init
   bd create "Initialize project documentation"
   ```

5. Start the development server:
   ```bash
   # Option 1: Development mode with hot reload
   docker-compose --profile dev up --build

   # Option 2: Local development
   uvicorn app.main:app --reload
   ```

6. Access the application:
   - Dashboard: http://localhost:9754/dashboard
   - API docs: http://localhost:9754/docs
   - Health check: http://localhost:9754/health

---

## Development Environment

### Project Structure

```
stairtup/
├── app/                      # Main application code
│   ├── company/             # Core agent system (Recruiter, Spawner, Employee, Slaick)
│   │   ├── beads.py         # Bead/task management
│   │   ├── cost_tracker.py  # Budget management
│   │   ├── employee.py      # Agent runtime
│   │   ├── slaick.py        # Message bus
│   │   ├── recruiter.py     # Job description generation
│   │   ├── spawner.py       # Agent spawning
│   │   └── types.py         # Shared data models
│   ├── main.py              # FastAPI application
│   └── openai_compat.py     # OpenCode integration
├── tests/                   # Test suite
│   ├── simulation_swarm.py  # Integration tests
│   ├── test_*.py            # Unit tests
│   └── e2e_swarm_simulation.py  # End-to-end tests
├── templates/               # Jinja2 templates (UI)
├── static/                  # Static assets
├── docs/                    # Additional documentation
├── README.md                # Project overview
├── SYSTEM_ARCHITECTURE.md   # Technical architecture
├── AGENTS.md                # Internal agent instructions
└── docker-compose.yml       # Container configuration
```

### Configuration

#### Recruiter Settings

The Recruiter has adaptive polling intervals:

```bash
# In app/company/recruiter.py:
FAST_POLL_INTERVAL=1.0      # Poll when work is available
SLOW_POLL_INTERVAL=5.0     # Poll when idle
HEARTBEAT_INTERVAL=10      # Heartbeat interval (default: 10s)
HEARTBEAT_TTL=30           # Heartbeat time-to-live (default: 30s)
```


#### Docker Configuration

Edit `docker-compose.yml` to customize services:

```yaml
services:
  web:
    build: .
    ports:
      - "9754:9754"
    environment:
      - PYTHONPATH=/app
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    volumes:
      - ./slaick.jsonl:/app/slaick.jsonl
      - ./employees.jsonl:/app/employees.jsonl
      - ./.beads:/app/.beads
      - /home/shedwards/.local/bin/bd:/usr/local/bin/bd:ro
      - .:/app/repo:cached
```

---

## Development Workflow

### 1. Fork the Repository

```bash
# Fork on GitHub (web UI or CLI)
# Then clone your fork:
git clone https://github.com/YOUR_USERNAME/stairtup.git
cd stairtup
git remote add upstream https://github.com/lesserevil/stairtup.git
```

### 2. Create a Feature Branch

```bash
# Create a branch for your changes
git checkout -b feature/your-feature-name
# Or for bug fixes:
git checkout -b fix/your-bug-fix
# Or for documentation:
git checkout -b docs/your-documentation-improvement
```

### 3. Make Your Changes

- Implement your changes following the code style below
- Add tests for new functionality
- Update documentation
- Run tests to verify

### 4. Run Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_employee.py

# Run with verbose output
pytest -v

# Run with type checking
mypy app/
```

### 5. Lint & Format

```bash
# Run linter
ruff check app/

# Run formatter
ruff format app/

# Auto-fix issues
ruff check app/ --fix
ruff format app/
```

### 6. Test Locally

```bash
# Start the development server
docker-compose --profile dev up --build

# Or
uvicorn app.main:app --reload

# Then access the application at http://localhost:9754
```

### 7. Create a Bead

Use the `bd` CLI to track your work:

```bash
# Create a bead for your change
bd create "Add feature X to support Y"

# Update status as you progress
bd update <bead-id> --status in_progress

# Close when complete
bd close <bead-id>
```

### 8. Commit Your Changes

```bash
# Stage changes
git add .

# Commit with conventional commit format
git commit -m "feat: add feature X"

# Types: feat, fix, docs, style, refactor, test, chore
# Examples:
# feat: add new agent category
# fix: resolve employee heartbeat issue
# docs: improve API documentation
# refactor: optimize Slaick message handling
```

### 9. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 10. Create a Pull Request

1. Go to your fork on GitHub
2. Click "New Pull Request"
3. Fill in the PR template:
   - Title
   - Description
   - Test plan
   - Type of change (bug fix, feature, etc.)
4. Submit the PR

### 11. Address Review Feedback

- Respond to comments promptly
- Make requested changes
- Add follow-up commits if needed
- Update PR description if necessary

### 12. Merge

After approval, your PR will be merged:
- Maintainers will merge to `main` or `dev`
- CI checks must pass
- All tests must pass
- Code review must be complete

---

## Code Style

### Python Style Guide

- Follow **PEP 8** conventions
- Use **type hints** for all functions and methods
- Use **docstrings** with Google or NumPy style
- Follow **Black** formatting rules
- Use **Ruff** for linting

### File Organization

- Put each module in its own file
- Group related classes/functions in the same file
- Use clear, descriptive names
- Keep functions focused and small (<50 lines)

### Variable Naming

- Use snake_case for variables and functions
- Use PascalCase for classes
- Use UPPER_CASE for constants
- Use descriptive names over abbreviations

### Comment Style

```python
def process_agent(employee_id: str, timeout: float = 30.0) -> bool:
    """
    Process an agent's work with timeout handling.

    Args:
        employee_id: The unique identifier for the agent
        timeout: Maximum time to wait for processing (seconds)

    Returns:
        True if processing completed successfully, False otherwise

    Raises:
        TimeoutError: If processing exceeds the timeout
    """
    # Implementation here
    pass
```

### Import Order

```python
# Standard library imports
import asyncio
import logging
from pathlib import Path
from typing import Optional

# Third-party imports
from fastapi import FastAPI

# Local application imports
from app.company.types import JobDescription
from app.company.slaick import Slaick
```

---

## Testing Guidelines

### Test Structure

- Tests should be named `test_*.py`
- Test classes should be descriptive
- Test functions should be single-purpose
- Use `assert` statements for checks
- Use descriptive test names

### Example Test

```python
import pytest
from app.company.employee import Employee, EmployeeStatus
from app.company.slaick import Slaick
from app.company.types import JobDescription


@pytest.mark.asyncio
async def test_employee_heartbeat():
    """Test that employee heartbeat updates are persisted correctly."""
    slaick = Slaick()
    jd = JobDescription(
        role="Test Agent",
        description="Testing agent",
        required_capabilities=["test"],
        required_abilities={"reasoning": 0.8},
        cost_estimate=0.1,
        complexity=0.5
    )

    async with Employee(
        agent_id="test-123",
        job_description=jd,
        slaick=slaick,
        heartbeat_interval=1,
        heartbeat_ttl=10
    ) as employee:
        await asyncio.sleep(2)  # Wait for first heartbeat
        assert employee.status == EmployeeStatus.IDLE
        # Verify heartbeat was persisted
        employees = slaick.tail(10)
        assert len(employees) >= 2  # Initial + heartbeat
```

### Test Coverage

- Aim for **>80%** code coverage
- Cover both happy paths and edge cases
- Test error conditions
- Test concurrent operations
- Test integration points

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_employee.py

# Run specific test function
pytest tests/test_employee.py::test_employee_heartbeat

# Run with verbose output
pytest -v

# Run with async support
pytest -k async --asyncio-mode=auto
```

### Test Categories

1. **Unit Tests** (`test_*.py`)
   - Test individual functions and classes
   - Isolated from other components
   - Fast execution

2. **Integration Tests** (`tests/simulation_swarm.py`)
   - Test component interactions
   - Use mock or test data
   - Moderate execution

3. **E2E Tests** (`tests/e2e_swarm_simulation.py`)
   - Test complete workflows
   - Use real agents (when available)
   - Slower execution

---

## Issue Reporting

### Before Opening an Issue

1. Search for existing issues to avoid duplicates
2. Check if the issue is already fixed in the latest version
3. Reproduce the issue with clear steps

### Issue Template

```markdown
## Description
Clear description of the issue

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Environment
- Python version: 3.12
- OS: Ubuntu 22.04
- Docker version: 24.0.7

## Logs
Paste relevant logs here

## Screenshots
If applicable, add screenshots

## Additional Context
Any other context
```

### Types of Issues

- **Bug**: Something isn't working
- **Feature Request**: New functionality you want
- **Documentation**: Missing or unclear docs
- **Performance**: Slow execution or resource usage
- **Security**: Potential vulnerability
- **Other**: Anything else

---

## Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Assume good intentions
- Provide constructive feedback
- Focus on the problem, not the person
- No hate speech, harassment, or discrimination

### Communication

- Use English for all communications
- Be clear and concise
- Ask questions if you're unsure
- Help others when you can
- Celebrate contributions

### Feedback

- Positive reinforcement builds community
- Be specific in feedback
- Explain the reasoning
- Accept feedback gracefully
- Ask for clarification if needed

### Patience

- Understand that maintainers are volunteers
- Allow time for responses
- Follow up politely
- Don't rush or pressure

---

## Getting Help

- **GitHub Issues**: Report bugs or ask questions
- **GitHub Discussions**: Community discussions
- **Documentation**: [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
- **Beads CLI**: Use `bd create` to ask questions as tasks

---

## Recognition

Contributors are acknowledged in:

1. **Code**: Your name in commit messages
2. **PRs**: Your PR is merged and visible
3. **README**: Contributors list (when added)
4. **Changelog**: Major contributions documented

---

## Additional Resources

- [Python Style Guide](https://peps.python.org/pep-0008/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Beads Documentation](https://github.com/steveyegge/beads)
- [Pytest Documentation](https://docs.pytest.org/)

---

Thank you for contributing to the Agent Company Swarm! 🚀

#### Recruiter Settings

The Recruiter has adaptive polling intervals:

```bash
# In app/company/recruiter.py:
FAST_POLL_INTERVAL=1.0      # Poll when work is available
SLOW_POLL_INTERVAL=5.0     # Poll when idle
HEARTBEAT_INTERVAL=10      # Heartbeat interval (default: 10s)
HEARTBEAT_TTL=30           # Heartbeat time-to-live (default: 30s)
```
#### Docker Configuration

Edit `docker-compose.yml` to customize services:

```yaml
services:
  web:
    build: .
    ports:
      - "9754:9754"
    environment:
      - PYTHONPATH=/app
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    volumes:
      - ./slaick.jsonl:/app/slaick.jsonl
      - ./employees.jsonl:/app/employees.jsonl
      - ./.beads:/app/.beads
      - /home/shedwards/.local/bin/bd:/usr/local/bin/bd:ro
      - .:/app/repo:cached
```
