"""
Shared types and models for the company module.

This module contains dataclasses that are shared across multiple modules
to avoid circular import issues.
"""

from dataclasses import dataclass


@dataclass
class JobDescription:
    """Structured Job Description for agent hiring with 7-dimensional ability ranking."""

    role: str
    description: str
    required_capabilities: list[str]
    required_abilities: dict[str, float]
    cost_estimate: float
    complexity: float

    @classmethod
    def get_ability_categories(cls) -> list[str]:
        """Return the valid Galileo-inspired ability categories."""
        return [
            "world-knowledge",
            "reasoning",
            "coding",
            "language-understanding",
            "writing",
            "creative-problem-solving",
            "safety-alignment",
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "role": self.role,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "required_abilities": self.required_abilities,
            "cost_estimate": self.cost_estimate,
            "complexity": self.complexity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JobDescription":
        """Create from dictionary."""
        return cls(
            role=data["role"],
            description=data["description"],
            required_capabilities=data["required_capabilities"],
            required_abilities=data["required_abilities"],
            cost_estimate=data["cost_estimate"],
            complexity=data["complexity"],
        )


from datetime import datetime
from typing import Optional, List

@dataclass
class Product:
    id: int
    name: str
    git_url: Optional[str]
    checkout_path: str
    beads_path: str
    employees_file: str
    status: str
    created_at: datetime

@dataclass
class Deliverable:
    id: int
    project_id: int
    name: str
    acceptance_criteria: str
    status: str
    bead_ids: List[int]

@dataclass
class Project:
    id: int
    product_id: int
    name: str
    description: str
    status: str
    deliverables: List[int]
    created_at: datetime
    target_completion: Optional[datetime] = None
