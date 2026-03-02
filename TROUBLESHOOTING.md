# Troubleshooting Guide

This guide helps you resolve common issues when working with the StairtUp. If you encounter a problem not covered here, please [open an issue](https://github.com/lesserevil/stairtup/issues).

## Table of Contents

1. [Installation & Setup](#installation--setup)
2. [Running the Application](#running-the-application)
3. [Agent System Issues](#agent-system-issues)
4. [Docker & Deployment](#docker--deployment)
5. [Testing & Debugging](#testing--debugging)
6. [Performance Issues](#performance-issues)
7. [Common Errors](#common-errors)
8. [Getting Help](#getting-help)

---

## Installation & Setup

### Issue: `bd: command not found`

**Symptom:**
```bash
$ bd list
bash: bd: command not found
```

**Solution:**
```bash
# Install Beads CLI
curl -sSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

# Verify installation
bd --version

# Initialize in your project
cd /home/shedwards/src/stairtup
bd init
```

### Issue: Virtual environment not activating

**Symptom:**
```bash
$ source venv/bin/activate
command not found: source
```

**Solution:**
```bash
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Verify activation (prompt should show (venv))
```

### Issue: Dependencies installation fails

**Symptom:**
```bash
$ pip install -r requirements.txt
ERROR: Could not find a version that satisfies the requirement...
```

**Solution:**
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install with explicit Python version
python3 --version  # Ensure you have Python 3.12+
pip install -r requirements.txt

# Try a fresh virtual environment
python3 -m venv venv --clear
source venv/bin/activate
pip install -r requirements.txt
```

### Issue: Permission denied when running Python scripts

**Symptom:**
```bash
$ python app/main.py
Permission denied
```

**Solution:**
```bash
# Make the script executable
chmod +x app/main.py

# Or run via Python interpreter
python app/main.py

# Or use uvicorn directly
uvicorn app.main:app --reload
```

---

## Running the Application

### Issue: Application won't start

**Symptom:**
```bash
$ uvicorn app.main:app --reload
ERROR: [Errno 98] Address already in use
```

**Solution:**
```bash
# Check what's using port 9754
lsof -i :9754  # Linux/macOS
netstat -ano | findstr :9754  # Windows

# Kill the process or use a different port
uvicorn app.main:app --reload --port 8000
```

### Issue: 404 errors on all routes except `/docs`

**Symptom:**
- `/` returns 404
- `/dashboard` returns 404
- Only `/docs` works

**Solution:**
```bash
# Check that templates directory exists
ls -la templates/
# Should show: index.html, dashboard.html

# Check that Jinja2 templates are configured correctly
# In app/main.py, verify:
templates = Jinja2Templates(directory="templates")

# Restart the server
uvicorn app.main:app --reload
```

### Issue: Docker containers fail to start

**Symptom:**
```bash
$ docker-compose up --build
ERROR: for web  ... failed to create container ...
```

**Solution:**
```bash
# Check Docker daemon is running
docker ps

# Check for conflicting containers
docker-compose down
docker-compose -v  # Remove volumes

# Rebuild with fresh state
docker-compose --profile dev up --build --force-recreate

# Check logs
docker-compose logs web
```

---

## Agent System Issues

### Issue: No agents spawning despite ready beads

**Symptom:**
```bash
# See ready beads
bd list
# ID: 1, Status: ready

# But no agents appear in dashboard
# employees.jsonl is empty
```

**Solution:**
```bash
# 1. Verify Recruiter is running
# Check if Recruiter process is active
ps aux | grep recruiter

# 2. Check Slaick message log
cat slaick.jsonl | grep HIRE

# 3. Check Recruiter logs
# If running with Docker:
docker-compose logs recruiter

# 4. Verify mock mode is enabled (default)
# In app/company/recruiter.py, verify:
mock_mode=True

# 5. Check budget (if CostTracker is enabled)
# Verify OPENAI_API_KEY is not set when using mock mode
env | grep OPENAI_API_KEY
```

### Issue: Agents not claiming tasks

**Symptom:**
```bash
# Beads are created and assigned
bd show <id>
# Assignee: emp-role-123

# But employee never claims it
```

**Solution:**
```bash
# 1. Check Employee logs
# Look for "poll_for_work" and "claim" messages

# 2. Verify bd is accessible
bd --version
bd list

# 3. Check for race conditions
# Multiple employees might be trying to claim the same bead

# 4. Verify employee is in IDLE state
# Check employees.jsonl for status: "active" or "busy"

# 5. Check if employee is polling
# Log should show:
# "Employee <id> found N ready beads"
# "Employee <id> attempting to claim bead <id>"
```

### Issue: Agents go offline or "zombie" status

**Symptom:**
```json
// employees.jsonl
{"agent_id": "emp-123", "status": "zombie", "expires_at": "2026-02-23T12:15:00Z"}
```

**Solution:**
```bash
# 1. Check heartbeat interval
# Verify HEARTBEAT_INTERVAL is set appropriately
# Default: 10 seconds

# 2. Verify heartbeat TTL
# Verify HEARTBEAT_TTL is set appropriately
# Default: 30 seconds

# 3. Check system time
date  # Ensure system time is correct

# 4. Check file locking issues
# Heartbeat failures can be due to lock contention

# 5. Restart the Janitor
# The Janitor should run every 2 minutes by default
```

### Issue: Message bus (Slaick) not receiving messages

**Symptom:**
```bash
# Agent sends message but no listener receives it
```

**Solution:**
```bash
# 1. Verify Slaick file exists and is writable
ls -la slaick.jsonl
touch slaick.jsonl  # Create if missing

# 2. Check message format
# Messages should be valid JSONL
cat slaick.jsonl | head -1 | jq .

# 3. Verify listener is running
# Check logs for "Message listener started"
# Check for _listening flag in employee class

# 4. Check poll interval
# Default is 2 seconds
# Try increasing for slower systems:
# agent.start_message_listener(poll_interval=5.0)
```

### Issue: OpenAI API not working

**Symptom:**
```python
# LLM-based JD generation fails
AttributeError: module 'openai' has no attribute 'AsyncOpenAI'
```

**Solution:**
```bash
# 1. Install OpenAI library
pip install openai

# 2. Verify API key is set
env | grep OPENAI_API_KEY

# 3. Test API connection
python -c "from openai import AsyncOpenAI; client = AsyncOpenAI(api_key='your_key'); print('OK')"

# 4. If not using LLM, ensure mock_mode=True
# In app/company/recruiter.py:
self.spawner = AgentSpawner(mock_mode=True)
```

---

## Docker & Deployment

### Issue: Volume permissions denied

**Symptom:**
```bash
$ docker-compose up
ERROR: for web  ... permission denied while trying to connect to the Docker daemon socket
```

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and log back in
# Or run Docker from within the group
newgrp docker

# Verify permissions
docker ps
```

### Issue: Container restarts immediately

**Symptom:**
```bash
$ docker-compose logs web
[...] crashed
$ docker-compose ps
NAME    STATE
web     Restarting (1) 5 seconds ago
```

**Solution:**
```bash
# 1. Check full logs
docker-compose logs web --tail=50

# 2. Check health endpoint
curl http://localhost:9754/health

# 3. Verify environment variables
docker-compose config

# 4. Check for binding conflicts
docker-compose down
docker-compose up -d
```

### Issue: Production deployment slow

**Symptom:**
- Application responds slowly
- High memory usage

**Solution:**
```bash
# 1. Use production config in docker-compose.yml
# Remove --reload flag
command: uvicorn app.main:app

# 2. Add workers for better concurrency
# In docker-compose.yml:
environment:
  - WEB_CONCURRENCY=4
command: uvicorn app.main:app --workers ${WEB_CONCURRENCY}

# 3. Enable caching
# Add Redis for RedisCache

# 4. Profile the application
uvicorn app.main:app --loop uvloop
```

### Issue: CORS errors in browser

**Symptom:**
```
Access to XMLHttpRequest at 'http://localhost:9754/api/...' from origin 'null' has been blocked by CORS policy
```

**Solution:**
```bash
# 1. Run on HTTPS
# Use Let's Encrypt or commercial SSL cert

# 2. Configure CORS headers
# In app/main.py:
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Or use a reverse proxy (nginx)
```

---

## Testing & Debugging

### Issue: Tests failing randomly

**Symptom:**
```bash
$ pytest
FAILED - some tests pass, others fail randomly
```

**Solution:**
```bash
# 1. Run with verbose output
pytest -v

# 2. Run specific failing test
pytest tests/test_employee.py::test_employee_claim

# 3. Check for async issues
pytest -k "async" --asyncio-mode=auto

# 4. Reset test data
rm -f slaick.jsonl employees.jsonl
pytest

# 5. Check for race conditions
# Add random delays or use locks
```

### Issue: Integration tests don't work

**Symptom:**
```bash
$ pytest tests/simulation_swarm.py
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```bash
# 1. Set PYTHONPATH
export PYTHONPATH=/home/shedwards/src/stairtup:$PYTHONPATH
pytest tests/simulation_swarm.py

# 2. Or use pytest.ini
# In pytest.ini:
# pythonpath = .

# 3. Or use venv in project directory
python -m pytest tests/simulation_swarm.py
```

### Issue: E2E simulation not completing

**Symptom:**
```bash
$ pytest tests/e2e_swarm_simulation.py
Test hangs indefinitely
```

**Solution:**
```bash
# 1. Check simulation duration
# In simulation file:
# duration = 60  # seconds

# 2. Add timeout
pytest --timeout=120 tests/e2e_swarm_simulation.py

# 3. Check for infinite loops in logic
# Look for while True: with no break condition

# 4. Add debug logging
pytest -s tests/e2e_swarm_simulation.py
```

### Issue: Can't connect to mock agents

**Symptom:**
```bash
# Employee can't find spawned agents
```

**Solution:**
```bash
# 1. Check spawner.log
cat spawn_requests.jsonl

# 2. Verify mock_mode is enabled
# In app/company/spawner.py:
self.mock_mode = True

# 3. Check employees.jsonl
cat employees.jsonl

# 4. Verify agent IDs match
# Employee polls with agent_id
# Spawner creates with agent_id
# They should be the same
```

---

## Performance Issues

### Issue: High CPU usage

**Symptom:**
- System CPU at 100%
- Unresponsive application

**Solution:**
```bash
# 1. Identify which process is consuming CPU
top
# Look for python or uvicorn processes

# 2. Increase polling intervals
# In Recruiter:
fast_poll_interval=5.0  # Increase from 1.0
slow_poll_interval=30.0  # Increase from 5.0

# 3. Reduce number of concurrent employees
# In Spawner:
MAX_CONCURRENT_AGENTS=5

# 4. Add rate limiting
# Check spawner for rate limiting logic

# 5. Profile the application
python -m cProfile -s time app/main.py
```

### Issue: High memory usage

**Symptom:**
- Application uses >2GB RAM
- System runs out of memory

**Solution:**
```bash
# 1. Check memory usage
htop
# Or
free -h

# 2. Add memory limits to containers
# In docker-compose.yml:
services:
  web:
    deploy:
      resources:
        limits:
          memory: 512M

# 3. Reduce heartbeat interval
# In Employee:
heartbeat_interval=30  # Increase from 10

# 4. Clean up stale message logs
# Slaick can grow large
# Regularly archive or truncate:
truncate -s 0 slaick.jsonl

# 5. Profile memory usage
python -m memory_profiler app/main.py
```

### Issue: Slow message bus

**Symptom:**
- Messages take seconds to transmit
- Agents can't keep up with work

**Solution:**
```bash
# 1. Check file I/O
# Slaick uses JSONL, which can be slow at scale
# Consider using Redis for high scale

# 2. Optimize message writes
# Use atomic appends (already implemented)
# Batch writes if needed

# 3. Increase poll interval
# In Employee:
poll_interval=10.0  # Increase from 5.0

# 4. Check disk I/O
# I/O can be a bottleneck on slow disks
# Consider SSD for message logs

# 5. Use async I/O
# Verify all file operations are async
```

---

## Common Errors

### Error: `ImportError: No module named 'app'`

**Cause:** Python path not set correctly

**Solution:**
```bash
export PYTHONPATH=/home/shedwards/src/stairtup:$PYTHONPATH
```

Or add to `pytest.ini`:
```ini
[pytest]
pythonpath = .
```

### Error: `AttributeError: 'NoneType' object has no attribute 'xxx'`

**Cause:** Object initialized but not fully set up

**Solution:**
```bash
# 1. Check initialization order
# Ensure objects are created before use

# 2. Add null checks
if object is not None:
    object.method()

# 3. Check async initialization
# Ensure await is used
async with Employee(...) as emp:
    # emp is guaranteed to be initialized
```

### Error: `FileNotFoundError: [Errno 2] No such file or directory`

**Cause:** File path incorrect or file doesn't exist

**Solution:**
```bash
# 1. Verify file paths
ls -la employees.jsonl
ls -la slaick.jsonl

# 2. Create files if missing
touch employees.jsonl
touch slaick.jsonl

# 3. Use pathlib for robust paths
from pathlib import Path
file_path = Path("employees.jsonl")
file_path.touch(exist_ok=True)
```

### Error: `fcntl.error: [Errno 13] Permission denied`

**Cause:** File locking permission issue

**Solution:**
```bash
# 1. Check file permissions
ls -la .employees.lock

# 2. Remove lock file if stale
rm .employees.lock

# 3. Fix file permissions
chmod 644 .employees.lock
chmod 755 app/company

# 4. Ensure user has write permissions
chmod +w employees.jsonl
```

### Error: `Race condition in heartbeat updates`

**Symptom:**
- Heartbeat not updating reliably
- Agents marked offline incorrectly

**Solution:**
```bash
# 1. Verify file locking is working
# Check for lock file
ls -la .employees.lock

# 2. Increase interval to reduce contention
heartbeat_interval=30  # Increase

# 3. Verify POSIX locking
# Check that fcntl.flock is used correctly

# 4. Add retry logic
# In heartbeat loop:
try:
    await self._update_heartbeat()
except Exception as e:
    logger.warning(f"Heartbeat failed: {e}, retrying...")
    await asyncio.sleep(5)
    await self._update_heartbeat()
```

---

## Getting Help

### Debug Logs

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
pytest -vvs

# Docker logs
docker-compose logs -f web --tail=100

# System logs
journalctl -u docker -f
```

### Check Configuration

```bash
# Environment variables
env

# Docker Compose configuration
docker-compose config

# Check for typos in env files
cat .env  # if it exists

# Verify dependencies
pip list | grep -E "fastapi|uvicorn|pytest"
```

### Verify System Requirements

```bash
# Python version
python --version

# Docker version
docker --version
docker-compose --version

# Test bd CLI
bd --version

# Check available memory
free -h
```

### Create a Debug Build

```bash
# 1. Get detailed error logs
pytest -xvs 2>&1 | tee debug.log

# 2. Get stack traces
pytest -xvs --tb=long

# 3. Capture runtime info
python -c "import sys; print(sys.version); import os; print(os.uname())"

# 4. Share with maintainers
# Include: error messages, logs, system info, steps to reproduce
```

### File an Issue

When reporting an issue, include:

1. **System Information**
   - Python version
   - OS and version
   - Docker version (if applicable)
   - Installed packages list

2. **Steps to Reproduce**
   - Exact commands used
   - Configuration files involved
   - Expected vs actual behavior

3. **Logs and Errors**
   - Full error traceback
   - Application logs
   - System logs (if applicable)

4. **Environment**
   - Production or development
   - Configuration settings
   - Environment variables

5. **Workarounds**
   - Any temporary fixes tried
   - Workarounds that partially work

---

## Additional Resources

- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) - Technical architecture
- [README.md](./README.md) - Overview and setup
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Development workflow
- [FastAPI Troubleshooting](https://fastapi.tiangolo.com/tutorial/debugging/)
- [Docker Troubleshooting](https://docs.docker.com/config/troubleshoot/)
- [Python Debugging Guide](https://docs.python.org/3/library/debug.html)

---

**Still stuck?** Create a new [GitHub Issue](https://github.com/lesserevil/stairtup/issues) with details about your problem.
