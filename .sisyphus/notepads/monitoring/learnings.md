# Monitoring & Observability Learnings

## Task: stairtup-6n0.10 - /health/dependencies endpoint

**Implementation Summary:**
- Created `app/api_health.py` module for dependency health checks
- Endpoint registered in `app/main.py` at `/health/dependencies`
- Checks recruiter, spawner, and employees services

**Service Health Logic:**
- **recruiter**: Checks `slaick.jsonl` for HR messages and message count
- **spawner**: Checks `slaick.jsonl` for ACK messages with agent_type=spawner
- **employees**: Checks `employees.jsonl` for active agent count

**Key Patterns:**
- All services read from JSONL files located in project root
- Employee IDs use `employee_id` or fallback to `agent_id`
- Health status determined by message/activity metrics
- Error handling returns healthy=false with error details

## Task: stairtup-6n0.9 - Grafana Dashboard Config

**Implementation Summary:**
- Created `src/monitoring/grafana_dashboard.json`
- Dashboard includes 13 panels for comprehensive monitoring

**Dashboard Panels:**
1. Agent Count Overview (time series)
2. Task Completion Rate (time series)
3. Cost Summary (stat - hiring + execution)
4. Agent Status breakdown (stat - active/inactive)
5. Task Throughput 5m (time series)
6-8. Cost by category (Hiring, Execution) (time series)
9. Heartbeat Latency (time series)
10-12. Queued tasks stats (Ready, In Progress, Open Jobs)
13. System health (Slaick queue depth, API error rate)

**Metrics Used:**
- `agent_total_count`, `agent_active_count`
- `task_completed_count`, `task_rate_total`
- `cost_hiring_by_category`, `cost_execution_by_category`
- `heartbeat_latency_ms`
- `task_ready_count`, `task_in_progress_count`
- `job_open_count`, `slaick_queue_depth`
- `api_error_rate`

## Architecture Notes

**Monitoring Stack:**
- Prometheus for metrics collection
- Grafana for visualization
- JSONL files (slaick.jsonl, employees.jsonl) as data sources
- FastAPI `/health/dependencies` for E2E smoke tests

**Metrics Convention:**
- All metrics prefixed with service/app name
- Categories used for cost breakdowns
- Rate functions for throughput calculations
- Summary stats for queue depth and errors
