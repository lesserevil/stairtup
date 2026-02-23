from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .types import Product


class WorkspaceManager:
    """Manage product workspace directories and related paths."""

    # Base directory for all product workspaces
    PRODUCTS_ROOT = Path("/home/shedwards/src/stairtup/products")

    @staticmethod
    def _resolve_product_path(product_id: str) -> Path:
        """Resolve the root path for a given product ID.

        The special product_id ``stairtup`` refers to the repository root.
        """
        if product_id == "stairtup":
            return Path("/home/shedwards/src/stairtup")
        return WorkspaceManager.PRODUCTS_ROOT / product_id

    @classmethod
    def get_product_path(cls, product_id: str) -> Path:
        """Return the absolute path to the product workspace directory."""
        return cls._resolve_product_path(product_id).resolve()

    @classmethod
    def get_beads_path(cls, product_id: str) -> Path:
        """Return the absolute path to the product's beads storage directory."""
        return cls.get_product_path(product_id) / "beads"

    @classmethod
    def get_employees_path(cls, product_id: str) -> Path:
        """Return the absolute path to the product's employees JSONL file."""
        return cls.get_product_path(product_id) / "employees.jsonl"

    @classmethod
    def get_checkout_path(cls, product_id: str) -> Path:
        """Return the absolute path to the product's checkout directory."""
        return cls.get_product_path(product_id) / "checkout"

    @classmethod
    def create_product_structure(cls, product_id: str, product_name: str) -> None:
        """Create the directory skeleton for a new product.

        The hierarchy created is:
        ``<PRODUCT_ROOT>/<product_id>/``
            ``beads/``                – storage for bead files
            ``checkout/``             – where the repo is checked out
            ``employees.jsonl``       – initially an empty file
        """
        product_path = cls._resolve_product_path(product_id)

        # Create the main product directory and sub-directories
        product_path.mkdir(parents=True, exist_ok=True)
        (product_path / "beads").mkdir(exist_ok=True)
        (product_path / "checkout").mkdir(exist_ok=True)

        # Ensure an empty employees.jsonl exists
        employees_file = product_path / "employees.jsonl"
        if not employees_file.exists():
            employees_file.touch()

    @classmethod
    def list_active_products(cls) -> List[Product]:
        """Read ``products.jsonl`` at the repository root and return a list of Product objects.

        Raises:
            FileNotFoundError: If ``products.jsonl`` cannot be located.
            json.JSONDecodeError: If a line in the file is not valid JSON.
        """
        products_file = Path("/home/shedwards/src/stairtup/products.jsonl")
        if not products_file.is_file():
            raise FileNotFoundError(f"products.jsonl not found at {products_file}")

        products: List[Product] = []
        with products_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                # The JSON fields should match the Product dataclass signature
                product = Product(**data)
                products.append(product)

        return products
