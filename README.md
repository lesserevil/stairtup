# Agent Company Swarm

A self-organizing autonomous agent company that solves software engineering tasks using a market-based work-stealing philosophy.

## Concept

The project implements a "Swarm Intelligence" approach to software development. Instead of a rigid hierarchy, the company operates as a decentralized marketplace where tasks (Beads) are fulfilled by specialized agents (Employees) coordinated by a core infrastructure (Recruiter, Spawner, Slaick).

### Core Philosophy: Market-Based Work Stealing
- **Beads as Currency**: Every unit of work is a "Bead" - an atomic, trackable issue.
- **Dynamic Specialized Hiring**: The Recruiter doesn't just hire "agents"; it creates Job Descriptions (JDs) specific to currently open Beads.
- **Optimistic Concurrency**: Multiple employees poll for work, but only one can successfully `claim` a bead via atomic status transitions.
- **Self-Healing**: A Janitor routine identifies "zombie" agents (crashed/timed out) and returns their tasks to the pool.

## Key Components

- **Recruiter**: Monitors the work queue, creates JDs, and initiates hiring via Slaick.
- **Spawner**: Orchestrates the instantiation of new OpenCode agents specialized for their JDs.
- **Employee**: The agent runtime. Handles heartbeats, task claiming, execution, and reporting.
- **Slaick**: A thread-safe messaging protocol (JSONL-based) for inter-agent coordination.
- **Beads**: The task registry and status tracker (leveraging the `bd` CLI).

## Setup & Operation

### Prerequisites
- Python 3.12+
- `bd` (beads) issue tracker installed.
- OpenCode environment configured.
- Docker & Docker Compose (for containerized deployment)

### Quick Start

#### Option 1: Docker (Recommended)

1. **Build and run all services**:
   ```bash
   # Production mode - web + background services
   docker-compose --profile full up --build

   # Development mode with hot reload
   docker-compose --profile dev up --build

   # Web only (no background workers)
   docker-compose up --build
   ```

2. **Access the application**:
   - Web dashboard: http://localhost:9754
   - Health check: http://localhost:9754/health

3. **Run background workers separately**:
   ```bash
   # Only recruiter and spawner services
   docker-compose --profile workers up
   ```

4. **View logs**:
   ```bash
   docker-compose logs -f web
   docker-compose logs -f recruiter
   docker-compose logs -f spawner
   ```

5. **Stop all services**:
   ```bash
   docker-compose --profile full down
   ```

#### Option 2: Local Development

1. **Initialize Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the Simulation**:
   Verify the swarm logic by running the integration simulation:
   ```bash
   python tests/simulation_swarm.py
   ```

3. **Start the API**:
   ```bash
   uvicorn app.main:app --reload
   ```

## Swarm Lifecycle

1. **Task Entry**: The CEO or project manager creates Beads using `bd create`.
2. **Hiring**: The Recruiter detects `ready` beads, generates a JD, and posts a `HIRE` message to Slaick.
3. **Spawning**: The Spawner catches the `HIRE` signal, starts a new agent specialized for that JD, and posts an `ACK`.
4. **Execution**: The new Employee claims the bead, marks it `in_progress`, and begins work.
5. **Completion**: Upon finishing, the Employee marks the bead as `done`, posts a `COMPLETE` message, and terminates or waits for more work.

## Monitoring & Safety

- **Cost Tracking**: All agent activity is logged and categorized. A circuit breaker prevents spawning if the budget is exceeded.
- **Heartbeats**: Active agents update their status every 10 seconds.
- **Janitor**: Automatically cleans up orphaned records and resets stalled tasks.
