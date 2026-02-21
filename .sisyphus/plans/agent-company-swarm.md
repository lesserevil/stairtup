# Plan: Agent Company Swarm (Self-Organizing Multi-Agent System)

## TL;DR

> **Quick Summary**: Build a self-organizing multi-agent swarm modeled as a startup company. A Recruiter agent dynamically hires employees (spawned via `task()`) based on Job Descriptions generated from `beads` issues.
> 
> **Deliverables**:
> - Core Orchestrator (Recruiter) with event loop
> - Employee Agent Template/Runtime
> - "Slaick" communication interface (`slaick.jsonl`)
> - Persistent Employee Registry (`employees.jsonl`)
> - Cost Tracking & Circuit Breaker
> 
> **Estimated Effort**: Medium-Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 5 → Task 8 → Task 15 → Integration

---

## Context

### Original Request
The user wants to create a semi-persistent agent mob that self-organizes as a company. A Recruiter hires employees based on dynamic Job Descriptions and model costs.

### Interview Summary
**Key Decisions**:
- **Task System**: Use `beads` (bd) for all task tracking.
- **Communication**: "Slaick" - plain text JSONL-based inter-agent chat.
- **Hiring**: Dynamic JD generation/matching (no pre-defined agent types).
- **Concurrency**: Optimistic locking via Dolt/Beads for task claiming.
- **Persistence**: `employees.jsonl` for metadata, `slaick.jsonl` for messages.

### Metis Review
**Identified Gaps** (addressed):
- **Race conditions**: Solved with optimistic concurrency on task claim.
- **Zombie agents**: Solved with lease-based heartbeats and recruiter cleanup.
- **Cost control**: Solved with token-bucket capping and circuit breakers.

---

## Work Objectives

### Core Objective
Implement a robust, self-organizing multi-agent organization that can autonomously execute tasks provided via `beads`.

### Concrete Deliverables
- `src/company/recruiter.ts`: Orchestrator with event loop.
- `src/company/employee.ts`: Base agent runtime.
- `src/company/slaick.ts`: Communication utilities.
- `src/company/beads.ts`: Atomic task claiming logic.
- `slaick.jsonl`: Shared message bus.
- `employees.jsonl`: Registry of active/expired agents.

### Definition of Done
- [ ] Recruiter can detect a new `bead` and hire an appropriate agent.
- [ ] Agent can claim a `bead` atomically and execute it.
- [ ] Agents can communicate via `slaick.jsonl`.
- [ ] System automatically cleans up zombie agents and honors cost caps.

### Must Have
- Atomic task claiming (no duplicate assignments).
- Heartbeat mechanism for agent liveliness.
- Configurable global and per-task cost limits.

### Must NOT Have
- Hard-coded agent role mappings (must be dynamic).
- Centralized task pushing (must be "work stealing" / self-selection).

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: NO
- **Automated tests**: YES (TDD for core logic)
- **Framework**: Vitest (recommended for Node.js speed)
- **Agent-Executed QA**: MANDATORY for every task.

### QA Policy
Every task includes Playwright/CLI scenarios with evidence capture in `.sisyphus/evidence/`.

---

## Execution Strategy

### Parallel Execution Waves

Wave 1 (Foundations):
├── Task 1: Environment & Schema Setup (Dolt/JSONL) [quick]
├── Task 2: Beads Integration & Atomic Claim Logic [unspecified-high]
└── Task 3: Slaick Communication Protocol (JSONL) [quick]

Wave 2 (Recruiter Core):
├── Task 4: Recruiter Event Loop & JD Generation [ultrabrain]
├── Task 5: Agent Spawning Mechanism (task() wrapper) [unspecified-high]
└── Task 6: Cost Tracking & Circuit Breaker [unspecified-high]

Wave 3 (Employee Core):
├── Task 7: Employee Base Runtime & Heartbeat [unspecified-high]
├── Task 8: Task self-selection & Execution Loop [ultrabrain]
└── Task 9: Message handling & Slaick integration [unspecified-high]

Wave 4 (Integration & Safety):
├── Task 10: Zombie cleanup & Lease management [unspecified-high]
├── Task 11: End-to-end Swarm Integration Test [artistry]
└── Task 12: Final QA & Documentation [writing]

---

## TODOs

- [x] 1. Environment & Schema Setup
  **What to do**:
  - Initialize `slaick.jsonl` and `employees.jsonl` with empty arrays.
  - Setup Vitest testing environment.
  - Create Dolt schema for `operations` (cost tracking).
  **QA Scenarios**:
  - `ls slaick.jsonl && ls employees.jsonl`
  - `npx vitest run` should pass.
  **Agent Profile**: `quick`

- [x] 2. Beads Atomic Claim Logic
  **What to do**:
  - Implement `claimBead(id, agentId)` using optimistic concurrency control.
  - Wrap `bd update` with a version/status check to ensure atomicity.
  **QA Scenarios**:
  - Run 5 agents simultaneously trying to claim one bead; only one should succeed.
  **Agent Profile**: `unspecified-high`

- [ ] 3. Slaick Communication Protocol
  **What to do**:
  - Create `Slaick` class for reading/writing JSONL messages.
  - Implement `appendMessage`, `getNewMessages`, and `tailMessages`.
  **QA Scenarios**:
  - Two processes exchange messages; verify both see the full thread.
  **Agent Profile**: `quick`

- [ ] 4. Recruiter Event Loop & JD Generation
  **What to do**:
  - Implement the `Recruiter` polling loop (adaptive sleep).
  - Use high-level LLM call to translate a `bead` description into a JSON Job Description (Role, Model Category, Skills).
  **QA Scenarios**:
  - Provide a complex task bead; verify Recruiter produces a sensible JD (e.g. "Security Auditor").
  **Agent Profile**: `ultrabrain`

- [ ] 5. Agent Spawning Mechanism
  **What to do**:
  - Implement a `task()` wrapper that hires an agent based on a JD.
  - Correctly map JD attributes to `category`, `subagent_type`, and `load_skills`.
  **QA Scenarios**:
  - Recruiter calls spawn for a "Frontend Dev" JD; verify a `visual-engineering` task is launched.
  **Agent Profile**: `unspecified-high`

- [ ] 6. Cost Tracking & Circuit Breaker
  **What to do**:
  - Implement a middleware that tracks model usage and token costs.
  - Add a "Circuit Breaker" that stops hiring if session budget is exceeded.
  **QA Scenarios**:
  - Set budget to $0.01; verify hiring fails after first task.
  **Agent Profile**: `unspecified-high`

- [ ] 7. Employee Base Runtime & Heartbeat
  **What to do**:
  - Create the `Employee` base class.
  - Implement periodic heartbeat writes to `employees.jsonl` (lease based).
  **QA Scenarios**:
  - Start an employee agent; verify its heartbeat updates in the registry every 10s.
  **Agent Profile**: `unspecified-high`

- [ ] 8. Task Self-Selection & Execution Loop
  **What to do**:
  - Implement the "Work Stealing" logic: Agent polls `beads` for tasks matching its JD.
  - Implement the execution loop: Claim → Execute → Report → Finish.
  **QA Scenarios**:
  - Manually create 3 tasks; start 1 agent; verify it picks up and completes tasks one by one.
  **Agent Profile**: `ultrabrain`

- [ ] 9. Message Handling & Slaick Integration
  **What to do**:
  - Add `Slaick` listeners to both Recruiter and Employee.
  - Implement basic "ACK" and "COMPLETE" message flows.
  **QA Scenarios**:
  - Agent sends "Task Started" message; Recruiter logs it to console.
  **Agent Profile**: `unspecified-high`

- [ ] 10. Zombie Cleanup & Lease Management
  **What to do**:
  - Implement Recruiter logic to find agents with expired leases (heartbeats > 30s old).
  - Automatically reset the `bead` status to `ready` for zombie tasks.
  **QA Scenarios**:
  - Kill an active agent process; verify its task is re-queued after 60s.
  **Agent Profile**: `unspecified-high`

- [ ] 11. End-to-End Swarm Integration Test
  **What to do**:
  - Multi-task simulation: CEO creates 10 beads.
  - Recruiter hires 3 agents.
  - Agents complete tasks in parallel.
  **QA Scenarios**:
  - Full simulation run finishes with 10 completed beads and no errors.
  **Agent Profile**: `artistry`

---\n\n## Final Verification Wave

- [ ] F1. Plan Compliance Audit (oracle)
- [ ] F2. Code Quality & Concurrency Review (ultrabrain)
- [ ] F3. E2E Swarm Simulation (artistry)

## Success Criteria
- [ ] Cumulative cost < $1.00 for simulation.
- [ ] Zero race conditions on 100 concurrent claims.
- [ ] All "zombies" re-queued within 60s.

