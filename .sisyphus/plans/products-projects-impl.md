# Plan: Products and Projects Infrastructure

## TL;DR

> **Quick Summary**: Extend the Agent Swarm with "Product" (git repos) and "Project" (task collections) concepts, enabling multi-product agent orchestration and unified dashboard visibility.
> 
> **Deliverables**:
> - Updated data models (Product, Project, Deliverable)
> - JSONL registries for products and projects
> - Multi-product polling logic in the Recruiter
> - CLI commands for entity management
> - Unified dashboard with Product/Project views
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Model Update → Registry Init → Recruiter Enhancement → Dashboard UI

---

## Context

### Original Request
"ok, let's add the concept of 'products' and 'projects'. 'products' are represented by external git repos. I'll leave it up to you if the checkouts of these repos should be in one container or a separate container or what. Each product can have separate 'projects'. A 'project' is a set of tasks with a deliveable within that product. 'StairtUp' is itself a product."

### Interview Summary
**Key Discussions**:
- **Directory-Based Isolation**: Decided to use a shared container with product-specific directories (`products/<product_id>/workspace`) for simplicity and performance.
- **StairtUp as Product**: The system will treat itself as a product, allowing agents to work on the tool that manages them.
- **Data Persistence**: Use the established JSONL pattern for registries (`products.jsonl`, `projects.jsonl`).

### Metis Review
**Identified Gaps** (addressed):
- **Cross-product state sync**: Ensured Recruiter polls across all active product-specific bead storages.
- **Workspace scoping**: Agents need explicit `product_id` and `workspace_path` in their prompts.
- **CLI/API Consistency**: Dashboard creation of beads must respect product/project scoping.

---

## Work Objectives

### Core Objective
Enable the Agent Swarm to manage multiple external codebases (Products) partitioned into deliverable-focused milestones (Projects) with full agent-automated execution.

### Concrete Deliverables
- `app/company/types.py`: Extended with Product/Project/Deliverable models.
- `products.jsonl`: Storage for product metadata and git info.
- `projects.jsonl`: Storage for project goals and deliverables.
- `app/company/recruiter.py`: Updated to poll across multiple workspaces.
- `templates/dashboard.html`: Updated with product selector and project progress.

### Definition of Done
- [ ] `bd product add <url>` clones repo and registers it.
- [ ] `bd project create <product> <name>` registers project.
- [ ] Recruiter successfully spawns an agent for a bead in an external product workspace.
- [ ] Dashboard shows active employees partitioned by product.

### Must Have
- Products MUST have isolated workspaces.
- Projects MUST have at least one defined deliverable.
- The system MUST treat 'stairtup' as a default product.

### Must NOT Have (Guardrails)
- Do NOT create separate Docker containers per product (use directories).
- Do NOT use heavy databases; stay with JSONL for metadata.
- Do NOT lose the ability to run the system in "StairtUp-only" mode.

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (after)
- **Framework**: pytest
- **Agent-Executed QA**: Mandatory for all Waves.

### QA Policy
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CLI**: Use `interactive_bash` (tmux) to run `bd` commands and verify registry files.
- **API**: Use `curl` to verify dashboard data endpoints.
- **UI**: Use `playwright` to navigate the new product/project views.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Models & Scaffolding):
├── Task 1: Update app/company/types.py with new models [quick]
├── Task 2: Initialize products.jsonl & projects.jsonl with StairtUp defaults [quick]
└── Task 3: Create app/company/workspace_manager.py for directory logic [unspecified-high]

Wave 2 (Product & Project Management):
├── Task 4a: Add Click CLI group structure (product/project) to app/main.py [quick]
├── Task 4b: Implement bd product add <url> subcommand [unspecified-high]
├── Task 4c: Implement bd project create <product> <name> subcommand [unspecified-high]
├── Task 4d: Write test for product/project CLI commands [quick]
├── Task 4e: Add Deliverable tracking logic (status updates) [quick]

Wave 3 (Multi-Product Orchestration):
├── Task 7: Update Recruiter to poll multiple .beads directories [deep]
├── Task 8: Update Spawner to inject product workspace into agent prompts [unspecified-high]
└── Task 9: Add product/project filtering to Slaick messages [quick]

Wave 4 (UI & Verification):
├── Task 10: Build Product/Project navigation in Dashboard [visual-engineering]
├── Task 11: Add per-project progress visualization [visual-engineering]
├── Task 12: E2E Verification: External repo hire loop [deep]
└── Task 13: E2E Verification: Dashboard task creation scoped to Project [deep]

Wave FINAL (Review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
└── Task F3: Multi-product load test simulation (deep)
```

---

## TODOs


- [x] 1. Update app/company/types.py with new models

  **What to do**:
  - Add `Product`, `Project`, and `Deliverable` dataclasses to `app/company/types.py`.
  - Include fields for git URLs, workspace paths, status, and IDs.
  - Extend `Bead` and `SpawnedAgent` with `product_id` and `project_id`.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`coding`]

  **Parallelization**: Wave 1

  **QA Scenarios**:
  ```
  Scenario: Model validation
    Tool: Bash
    Steps:
      1. python3 -c "from app.company.types import Product, Project, Deliverable; print('Success')"
    Expected Result: Success
    Evidence: .sisyphus/evidence/task-1-model-validation.txt
  ```

- [x] 2. Initialize products.jsonl & projects.jsonl with StairtUp defaults

  **What to do**:
  - Create `products.jsonl` with an entry for 'stairtup' (id='stairtup', path='.').
  - Create `projects.jsonl` with a default project for StairtUp.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`coding`]

  **Parallelization**: Wave 1

- [x] 3. Create app/company/workspace_manager.py for directory logic

  **What to do**:
  - Implement `WorkspaceManager` class to manage `products/` directory.
  - Add logic to resolve absolute paths for product-specific beads and employees.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`coding`]

  **Parallelization**: Wave 1

- [ ] 4a. Add Click CLI group structure (product/project) to app/main.py

  **What to do**:
  - Add Click import
  - Create `cli()` group function
  - Add basic commands (run-server, help)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2

- [x] 4b. Implement bd product add <url> subcommand

  **What to do**:
  - Add `product` Click command with `add` subcommand
  - Accept URL as argument
  - Clone repository to products/<product-id>/checkout
  - Register product in products.jsonl
  - Output success message

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 2

- [x] 4c. Implement bd project create <product> <name> subcommand

  **What to do**:
  - Add `project` Click command with `create` subcommand
  - Accept product_id and name as arguments
  - Create project record in projects.jsonl
  - Add description and default status (planning)
  - Output success message

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 2

- [ ] 4d. Write test for product/project CLI commands

  **What to do**:
  - Add pytest test for product add CLI
  - Add pytest test for project create CLI
  - Verify JSONL files are updated correctly
  - Verify proper error handling

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2

- [ ] 4e. Add Deliverable tracking logic (status updates)

- [ ] 7. Update Recruiter to poll multiple .beads directories

  **What to do**:
  - Modify `Recruiter.run()` to iterate through all active products in `products.jsonl`.
  - For each product, call `get_ready_beads()` in its specific `.beads` directory.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`coding`]

  **Parallelization**: Wave 3

- [ ] 10. Build Product/Project navigation in Dashboard

  **What to do**:
  - Add a sidebar or tabs to `templates/dashboard.html` for switching products.
  - Filter the beads and employees list based on the selected product.

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`frontend-ui-ux`]

  **Parallelization**: Wave 4

- [ ] 11. Add per-project progress visualization

  **What to do**:
  - Add a progress bar or deliverable checklist to the dashboard for active projects.

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`frontend-ui-ux`]

  **Parallelization**: Wave 4

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Verify implementation of ALL 4 requested components (Models, Recruiter, Registries, UI). Check "Must Have" list.
- [ ] F2. **Code Quality Review** — `unspecified-high`
  Check for proper error handling in git operations and JSONL writes.
- [ ] F3. **Multi-product load test simulation** — `deep`
  Register 3 mock products, create projects in each, and verify Recruiter handles concurrent hiring across all three.

---

## Commit Strategy
`feat(core): add product and project conceptual layers`

## Success Criteria
- Product registry exists and contains 'stairtup'.
- Recruiter polls multiple directories.
- Dashboard shows product breakdown.
