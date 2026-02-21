"""Cost Tracking and Circuit Breaker for runaway cost prevention.

This module implements the CostTracker class that:
- Tracks cumulative session costs in a JSONL file
- Implements configurable cost limits (global and per-category)
- Acts as a CircuitBreaker that stops hiring when budget exceeded
- Integrates with Recruiter to check costs before spawning
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    """Single cost entry for an operation."""

    timestamp: str
    operation: str
    cost: float
    agent_id: str
    category: str

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "cost": self.cost,
            "agent_id": self.agent_id,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CostEntry":
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            operation=data["operation"],
            cost=data["cost"],
            agent_id=data["agent_id"],
            category=data["category"],
        )


class CostTracker:
    """Tracks costs and implements circuit breaker for budget limits.

    Responsibilities:
    - Track each spawn operation cost (from JD.cost_estimate)
    - Track cumulative session total
    - Track costs by category
    - Check if budget allows for additional spawns
    - Log circuit breaker trips

    Attributes:
        budget: Maximum allowed budget (default $10.00)
        category_budgets: Optional per-category budget limits
        operations_file: Path to JSONL file for cost tracking
        current_spent: Total amount spent so far
        category_spent: Dict mapping category -> amount spent
    """

    DEFAULT_BUDGET = 10.0

    def __init__(
        self,
        budget: float = DEFAULT_BUDGET,
        operations_file: str | Path = "operations.jsonl",
        category_budgets: Optional[dict[str, float]] = None,
    ):
        """Initialize the CostTracker.

        Args:
            budget: Global budget limit (default $10.00)
            operations_file: Path to JSONL file for cost tracking
            category_budgets: Optional dict of category -> budget limit
        """
        self.budget = budget
        self.operations_file = Path(operations_file)
        self.category_budgets = category_budgets or {}

        # Initialize tracking state
        self.current_spent = 0.0
        self.category_spent: dict[str, float] = {}
        self._circuit_breaker_tripped = False
        self._trip_reason: Optional[str] = None

        # Load existing costs from file
        self._load_existing_costs()

        logger.info(
            f"CostTracker initialized: budget=${budget:.2f}, "
            f"spent=${self.current_spent:.2f}, "
            f"remaining=${self.get_remaining_budget():.2f}"
        )

    def _load_existing_costs(self) -> None:
        """Load existing costs from operations.jsonl to calculate current spent."""
        if not self.operations_file.exists():
            logger.debug(f"No existing operations file at {self.operations_file}")
            return

        try:
            with open(self.operations_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        cost = data.get("cost", 0.0)
                        category = data.get("category", "unknown")

                        self.current_spent += cost
                        self.category_spent[category] = (
                            self.category_spent.get(category, 0.0) + cost
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(
                            f"Skipping malformed cost entry at line {line_num}: {e}"
                        )
                        continue

            logger.info(
                f"Loaded {self.current_spent:.2f} in existing costs from "
                f"{self.operations_file}"
            )

        except Exception as e:
            logger.error(f"Failed to load existing costs: {e}")
            # Continue with zero spent - don't fail on load errors

    def can_afford(self, cost: float, category: Optional[str] = None) -> bool:
        """Check if adding this cost would exceed budget.

        Checks both global budget and per-category budget if set.

        Args:
            cost: Cost of the proposed operation
            category: Optional category to check against category budget

        Returns:
            True if the cost can be afforded, False otherwise
        """
        # Check global budget
        if (self.current_spent + cost) > self.budget:
            logger.warning(
                f"Cannot afford: ${cost:.3f} would exceed global budget "
                f"(${self.current_spent:.3f} + ${cost:.3f} > ${self.budget:.3f})"
            )
            return False

        # Check category budget if set
        if category and category in self.category_budgets:
            category_limit = self.category_budgets[category]
            category_current = self.category_spent.get(category, 0.0)
            if (category_current + cost) > category_limit:
                logger.warning(
                    f"Cannot afford: ${cost:.3f} would exceed {category} budget "
                    f"(${category_current:.3f} + ${cost:.3f} > ${category_limit:.3f})"
                )
                return False

        return True

    def record_cost(
        self, cost: float, agent_id: str, category: str, operation: str = "spawn"
    ) -> None:
        """Record a cost and update current spent.

        Args:
            cost: Cost of the operation
            agent_id: ID of the agent spawned
            category: Category of the operation
            operation: Type of operation (default: "spawn")

        Raises:
            PermissionError: If circuit breaker is tripped
        """
        if self._circuit_breaker_tripped:
            raise PermissionError(
                f"Circuit breaker is tripped: {self._trip_reason}. "
                "Call reset_circuit_breaker() to clear."
            )

        # Check if this would exceed budget
        if not self.can_afford(cost, category):
            self._trip_circuit_breaker(
                f"Budget exceeded: tried to spend ${cost:.3f} "
                f"(spent: ${self.current_spent:.3f}, budget: ${self.budget:.3f})"
            )
            raise PermissionError(
                f"Cannot record cost: budget would be exceeded. "
                f"Use can_afford() before recording costs."
            )

        # Create entry
        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation=operation,
            cost=cost,
            agent_id=agent_id,
            category=category,
        )

        # Append to operations file
        try:
            with open(self.operations_file, "a", encoding="utf-8") as f:
                line = json.dumps(entry.to_dict(), separators=(",", ":"))
                f.write(line + "\n")
                f.flush()

            logger.debug(f"Recorded cost: ${cost:.3f} for {agent_id} ({category})")

        except Exception as e:
            logger.error(f"Failed to write cost entry to file: {e}")
            raise

        # Update tracking state
        self.current_spent += cost
        self.category_spent[category] = self.category_spent.get(category, 0.0) + cost

        logger.info(
            f"Cost recorded: ${cost:.3f} for {agent_id} ({category}). "
            f"Total spent: ${self.current_spent:.3f} / ${self.budget:.3f}"
        )

        # Check if we're now at budget limit
        if self.current_spent >= self.budget:
            self._trip_circuit_breaker(
                f"Budget fully exhausted: ${self.current_spent:.3f} / ${self.budget:.3f}"
            )

    def _trip_circuit_breaker(self, reason: str) -> None:
        """Trip the circuit breaker.

        Args:
            reason: Reason for tripping the circuit breaker
        """
        if not self._circuit_breaker_tripped:
            self._circuit_breaker_tripped = True
            self._trip_reason = reason
            logger.error(f"CIRCUIT BREAKER TRIPPED: {reason}")

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker.

        This allows operations to continue after the breaker has tripped.
        Only use this if you've resolved the budget issue or want to force
        continued operation.
        """
        was_tripped = self._circuit_breaker_tripped
        self._circuit_breaker_tripped = False
        self._trip_reason = None
        if was_tripped:
            logger.warning("Circuit breaker has been manually reset")

    def is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is currently tripped.

        Returns:
            True if budget has been exceeded, False otherwise
        """
        return self._circuit_breaker_tripped

    def get_circuit_breaker_reason(self) -> Optional[str]:
        """Get the reason the circuit breaker was tripped.

        Returns:
            Reason string if tripped, None otherwise
        """
        return self._trip_reason

    def get_current_spent(self) -> float:
        """Get total amount spent so far.

        Returns:
            Total spent amount
        """
        return self.current_spent

    def get_remaining_budget(self) -> float:
        """Get remaining budget.

        Returns:
            Remaining budget amount (can be negative if exceeded)
        """
        return self.budget - self.current_spent

    def get_category_spent(self, category: str) -> float:
        """Get amount spent in a specific category.

        Args:
            category: Category to check

        Returns:
            Amount spent in that category (0.0 if none)
        """
        return self.category_spent.get(category, 0.0)

    def get_all_category_spending(self) -> dict[str, float]:
        """Get spending breakdown by category.

        Returns:
            Dict mapping category -> amount spent
        """
        return self.category_spent.copy()

    def get_operation_history(self) -> list[CostEntry]:
        """Get all recorded cost entries from operations file.

        Returns:
            List of CostEntry objects
        """
        entries = []
        if not self.operations_file.exists():
            return entries

        try:
            with open(self.operations_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(CostEntry.from_dict(data))
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping malformed entry: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to read operation history: {e}")

        return entries

    def set_budget(self, new_budget: float) -> None:
        """Update the global budget limit.

        This also resets the circuit breaker if the new budget allows
        for continued operation.

        Args:
            new_budget: New global budget limit
        """
        old_budget = self.budget
        self.budget = new_budget

        # Reset circuit breaker if new budget allows continued operation
        if self._circuit_breaker_tripped and self.current_spent < self.budget:
            logger.info(
                f"Budget increased from ${old_budget:.2f} to ${new_budget:.2f}. "
                "Resetting circuit breaker."
            )
            self.reset_circuit_breaker()
        else:
            logger.info(f"Budget updated: ${old_budget:.2f} -> ${new_budget:.2f}")

    def set_category_budget(self, category: str, budget: float) -> None:
        """Set or update a per-category budget limit.

        Args:
            category: Category name
            budget: Budget limit for this category
        """
        self.category_budgets[category] = budget
        logger.info(f"Set {category} budget limit to ${budget:.2f}")

    def __repr__(self) -> str:
        """String representation of CostTracker state."""
        return (
            f"CostTracker(budget=${self.budget:.2f}, "
            f"spent=${self.current_spent:.2f}, "
            f"remaining=${self.get_remaining_budget():.2f}, "
            f"tripped={self._circuit_breaker_tripped})"
        )
