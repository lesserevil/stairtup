# System Architecture: StairtUp

This document describes the technical architecture and protocols of the agent-based software development swarm.

## High-Level Architecture

The system is built as a set of decoupled services and agent runtimes that communicate through persistent data stores (Beads) and an append-only message bus (Slaick).

```
[ CEO / User ] -> [ Beads Manager (bd) ]
                         |
                         v
[ Recruiter ] <-> [ Slaick (Message Bus) ] <-> [ Spawner ]
                         |                       |
                         |                       v
                         +-------> [ Employees (Agent Runtimes) ]
                                         |
                                         v
                                  [ Target Codebase ]
```

## Technology Stack

- **Backend**: Python 3.12, FastAPI (for API/UI).
- **Frontend**: HTMX, Jinja2 templates (Server-side rendered dashboard).
- **Task Management**: `bd` (Beads) CLI tool.
- **Agent Framework**: OpenCode (High-level task delegation).
- **Messaging**: JSONL-based atomic append-only log.

## Components

### 1. Recruiter (`app/company/recruiter.py`)
The "brain" of the hiring process.
- **Loop**: Polls `get_ready_beads()` every minute.
- **JD Generation**: For each unassigned bead, it generates a `JobDescription` containing:
  - Role (Backend, Frontend, Documentation, etc.)
  - Clear deliverables based on the bead's title/body.
  - Required skills and context.
- **Post-to-Slaick**: Broadcasts a `HIRE` message.

### 2. Spawner (`app/company/spawner.py`)
The factory for new agents.
- **Listener**: Waits for `HIRE` messages in Slaick.
- **Instantiation**: Calls `task()` with specific parameters:
  - `category`: Mapped from JD role.
  - `system_prompt`: A structured 6-section prompt including "Mission", "Company Rules", and "Exit Conditions".
- **Registration**: Records the agent's ID, role, and expiry in `employees.jsonl`.

### 3. Employee (`app/company/employee.py`)
The worker lifecycle manager.
- **Initialization**: Sets up initial heartbeat.
- **Work Loop**:
  - Polling: Finds beads matching its JD role.
  - Claiming: Attempts `bd update --claim`.
  - Execution: Performs the work (simulated in tests, actual work in production).
  - Reporting: Sends `PROGRESS` and `COMPLETE` updates to Slaick.
- **Health Check**: Updates its own heartbeat in the registry periodically.

### 4. Slaick (`app/company/slaick.py`)
A lightweight, filesystem-based messaging protocol.
- **Format**: Each line is a JSON object.
- **Concurrency**: Uses atomic appends to prevent message corruption.
- **Types**:
  - `HIRE`: Hiring request.
  - `ACK`: Confirmation of hiring.
  - `CLAIM`: Task acquisition.
  - `PROGRESS`: Interval status update.
  - `COMPLETE`: Task finished.

## Protocols

### Hiring & Acquisition
1. Recruiter -> Slaick: `HIRE {role, bead_id}`
2. Spawner -> Slaick: `ACK {agent_id, bead_id}`
3. Employee -> Beads: `bd update <id> --claim`
4. Employee -> Slaick: `CLAIM {agent_id, bead_id}`

### Heartbeat & Cleanup
- **TTL**: Employees have a 5-minute lease (default).
- **Heartbeat**: Sent every 30 seconds.
- **Janitor**: Scans `employees.jsonl` every 2 minutes. If `now > last_heartbeat + 120s`, it marks the agent as `OFFLINE`.

## Security & Guardrails

- **Circuit Breaker**: The `CostTracker` enforces a hard spend limit across the swarm.
- **Role Isolation**: Agents can only claim tasks matching their assigned role to prevent "skill drift".
- **POSIX Locking**: All file-based databases use `fcntl.flock` for process-safe updates.
