"""
Company module - Core business logic for the agent company system.

This module contains all core components:
- Recruiter: Dynamic job description generation and hiring
- Spawner: Agent instantiation
- Employee: Agent runtime and task execution
- Slaick: JSONL-based messaging system
- Beads: Task tracking (via bd CLI)
- Message models for AI integration
"""

from .beads import Bead, claim_bead_async, get_ready_beads
from .recruiter import Recruiter, run_recruiter
from .spawner import AgentSpawner
from .employee import Employee, EmployeeStatus
from .slaick import MessageType, Slaick
from .message_models import ChatRequestPayload, ChatResponsePayload, ChatMetadata
from .cost_tracker import CostTracker
from .types import JobDescription, Product
from .workspace_manager import WorkspaceManager

__all__ = [
    "Bead",
    "claim_bead_async",
    "get_ready_beads",
    "Recruiter",
    "run_recruiter",
    "AgentSpawner",
    "Employee",
    "EmployeeStatus",
    "MessageType",
    "Slaick",
    "ChatRequestPayload",
    "ChatResponsePayload",
    "ChatMetadata",
    "CostTracker",
    "JobDescription",
    "Product",
    "WorkspaceManager",
]
