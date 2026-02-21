"""
Shared types and models for the company module.

This module contains dataclasses that are shared across multiple modules
to avoid circular import issues.
"""

from dataclasses import dataclass


@dataclass
class JobDescription:
    """Structured Job Description for agent hiring."""

    role: str
    description: str
    required_capabilities: list[str]
    suggested_category: str
    cost_estimate: float
    complexity: float

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "role": self.role,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "suggested_category": self.suggested_category,
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
            suggested_category=data["suggested_category"],
            cost_estimate=data["cost_estimate"],
            complexity=data["complexity"],
        )
