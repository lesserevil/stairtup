# OpenCode Agent System - Comprehensive Documentation (2026)

## 1. AGENT TYPES

### OpenCode Core (Built-in)
- **Build**: Primary agent with full tool access (write, edit, bash).
- **Plan**: Primary agent for analysis and planning; read-only by default.
- **Explore (Subagent)**: Fast read-only codebase exploration.
- **General (Subagent)**: Multi-step task execution with full tool access.

### Oh-My-OpenCode (Specialized)
- **Sisyphus**: Main orchestrator. Plans, delegates, and drives tasks to completion.
- **Hephaestus**: Autonomous deep worker. Research-heavy and end-to-end execution.
- **Prometheus**: Strategic planner. Uses "interview mode" to build verified plans.
- **Oracle**: Architecture and debugging specialist. Deep reasoning.
- **Librarian**: Documentation and codebase search expert.
- **Document Writer**: Specialized in generating technical documentation and prose.

---

## 2. CATEGORIES (Task Delegation)
- **visual-engineering**: Frontend, UI/UX, and design tasks.
- **ultrabrain**: Hard logic, complex architecture, and deep reasoning.
- **deep**: Autonomous research and multi-step execution.
- **quick**: Single-file changes, typos, and minor fixes.
- **artistry**: Creative and artistic tasks requiring high temperature.
- **writing**: Documentation, comments, and prose generation.
- **unspecified-high/low**: General task tiers based on complexity.

---

## 3. MODELS & CAPABILITIES

| Agent/Category | Primary Model | Provider | Strengths |
|----------------|---------------|----------|-----------|
| **Sisyphus** | Claude Opus 4.6 / Kimi K2.5 | Anthropic / Z.AI | Orchestration, parallel execution |
| **Hephaestus** | GPT-5.3 Codex | OpenAI | Deep research, autonomous work |
| **Oracle** | GPT-5.2 | OpenAI | Logic, debugging, architecture |
| **Visual Eng.** | Gemini-3 Pro | Google | Frontend, UI/UX, Vision |
| **Librarian** | Gemini-3 Flash | Google | Speed, search, context handling |
| **Quick** | Claude Haiku 4.5 | Anthropic | Fast, inexpensive fixes |

---

## 4. COST & PRICING (Feb 2026 Estimates)

| Tier | Example Model | Input ($/1M) | Output ($/1M) |
|------|---------------|--------------|---------------|
| **Premium** | Claude Opus 4.5 | $5.00 | $25.00 |
| **Standard** | GPT-5 / Sonnet 4.5 | $1.25 - $3.00 | $10.00 - $15.00 |
| **Budget** | DeepSeek Chat / GPT-5 Nano | $0.05 - $0.28 | $0.40 - $0.42 |

### Subscription Optimization
- **GitHub Copilot**: Included in $19/mo plan; includes Claude/GPT/Gemini.
- **GLM Coding Plan**: $3/mo for high-performance GLM models (Kimi alternative).

---

## 5. CAPABILITIES & STRENGTHS
- **Parallelism**: Fire 5+ specialists in parallel to save time.
- **Hash-Anchored Edits**: Surgical code changes with zero stale-line errors.
- **Strategic Planning**: Prometheus interviews you before writing a line of code.
- **Context Management**: Hierarchical \`AGENTS.md\` files for massive context efficiency.

