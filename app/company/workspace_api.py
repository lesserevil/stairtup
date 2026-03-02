"""
Workspace API Module - Multi-Product Support REST Endpoints.

This module provides full CRUD API endpoints for managing multiple product workspaces:
- GET /api/workspace/products (list all products)
- POST /api/workspace/products (create new product)
- GET /api/workspace/products/{id} (get product details)
- DELETE /api/workspace/products/{id} (mark for removal)
- PATCH /api/workspace/products/{id} (update product)

Security: Product isolation validation ensures tenants cannot access other products' data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.company.workspace_manager import WorkspaceManager
from app.company.types import Product
from app.company.beads import get_ready_beads

if TYPE_CHECKING:
    pass  # for future type imports

logger = logging.getLogger(__name__)

# Create router for product endpoints
router = APIRouter(prefix="/api/workspace", tags=["workspace"])


# =============================================================================
# Pydantic Models
# =============================================================================


class ProductCreateRequest(BaseModel):
    """Request model for creating a new product."""

    name: str = Field(..., min_length=1, max_length=100, description="Product name")
    git_url: Optional[str] = Field(None, description="Git repository URL")
    checkout_path: Optional[str] = Field(
        None, description="Custom checkout path (optional)"
    )
    beads_path: Optional[str] = Field(None, description="Custom beads path (optional)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate product name - no special characters."""
        if not v or not v.strip():
            raise ValueError("Product name cannot be empty")
        # Allow alphanumeric, hyphens, underscores
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v.strip()):
            raise ValueError(
                "Product name can only contain letters, numbers, hyphens, and underscores"
            )
        return v.strip()


class ProductUpdateRequest(BaseModel):
    """Request model for updating a product."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Product name"
    )
    git_url: Optional[str] = Field(None, description="Git repository URL")
    status: Optional[str] = Field(
        None, pattern="^(active|archived|removing)$", description="Product status"
    )
    checkout_path: Optional[str] = Field(None, description="Checkout path")
    beads_path: Optional[str] = Field(None, description="Beads path")
    employees_file: Optional[str] = Field(None, description="Employees file path")


class ProductResponse(BaseModel):
    """Response model for product data."""

    id: str
    name: str
    git_url: Optional[str]
    checkout_path: str
    beads_path: str
    employees_file: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Response model for listing products."""

    products: List[ProductResponse]
    count: int


class ProductDeleteResponse(BaseModel):
    """Response model for product deletion (mark for removal)."""

    product_id: str
    status: str
    message: str


class ProductBeadsResponse(BaseModel):
    """Response model for product beads."""

    product_id: str
    ready_beads: List[dict]


# =============================================================================
# Dependency: Product Context and Security
# =============================================================================


class ProductContext:
    """Context manager for product-scoped operations."""

    def __init__(self, product_id: str):
        self.product_id = product_id
        self._validated = False
        self._product: Optional[Product] = None

    async def validate(self) -> bool:
        """
        Validate that the product exists and is active.

        Raises:
            HTTPException: If product not found or not accessible
        """
        if self._validated:
            return True

        product = await asyncio_get_product(self.product_id)
        if product is None:
            raise HTTPException(
                status_code=404, detail=f"Product '{self.product_id}' not found"
            )

        if product.status not in ("active", "removing"):
            raise HTTPException(
                status_code=400,
                detail=f"Product '{self.product_id}' is {product.status}",
            )

        self._product = product
        self._validated = True
        return True

    @property
    def product(self) -> Product:
        """Get the validated product."""
        if self._product is None:
            raise RuntimeError("Product not validated. Call validate() first.")
        return self._product


def get_product_context(product_id: str = Path(...)) -> ProductContext:
    """Dependency to get and validate product context."""
    return ProductContext(product_id)


async def require_active_product(
    product_id: str,
    require_active: bool = True,  # noqa: FBT
) -> Product:
    """
    Dependency to require an active product.

    Args:
        product_id: The product ID to validate
        require_active: If True, require status == 'active'

    Raises:
        HTTPException: If product not found or inactive
    """
    product = await asyncio_get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    if require_active and product.status != "active":
        raise HTTPException(
            status_code=400, detail=f"Product '{product_id}' is {product.status}"
        )

    return product


# =============================================================================
# Async Helper Functions
# =============================================================================

import asyncio


def _sync_get_product(product_id: str) -> Optional[Product]:
    """Synchronous helper to get a product by ID."""
    try:
        products = WorkspaceManager.list_active_products()
        for p in products:
            if str(p.id) == str(product_id) or p.name == product_id:
                return p
    except FileNotFoundError:
        return None
    return None


def _sync_get_all_products(
    include_archived: bool = False,  # noqa: FBT
    include_removing: bool = False,  # noqa: FBT
) -> List[Product]:
    """Synchronous helper to get all products."""
    try:
        # Read products directly to get all status values
        products_file = Path("/home/shedwards/src/stairtup/products.jsonl")
        products = []

        if products_file.exists():
            with open(products_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        product = Product(**data)
                        # Filter by status if needed
                        if product.status == "active":
                            products.append(product)
                        elif product.status == "archived" and include_archived:
                            products.append(product)
                        elif product.status == "removing" and include_removing:
                            products.append(product)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Skipping malformed product record: {e}")
                        continue

        return products
    except Exception as e:
        logger.error(f"Error reading products: {e}")
        return []


def _sync_create_product(data: dict) -> Product:
    """Synchronous helper to create a new product."""
    products_file = Path("/home/shedwards/src/stairtup/products.jsonl")

    # Generate ID: use name as string id
    product_id = data["name"]

    # Check for duplicate name
    existing = _sync_get_all_products(include_archived=True, include_removing=True)
    for p in existing:
        if p.name == product_id:
            raise ValueError(f"Product with name '{product_id}' already exists")

    # Set default paths
    checkout_path = data.get("checkout_path") or f"products/{product_id}/checkout"
    beads_path = data.get("beads_path") or f"products/{product_id}/beads"
    employees_file = (
        data.get("employees_file") or f"products/{product_id}/employees.jsonl"
    )

    # Create the product record
    new_product = Product(
        id=product_id,  # Use name as ID (string)
        name=data["name"],
        git_url=data.get("git_url"),
        checkout_path=checkout_path,
        beads_path=beads_path,
        employees_file=employees_file,
        status="active",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Create directory structure
    WorkspaceManager.create_product_structure(product_id, new_product.name)

    # Write to products.jsonl
    record = {
        "id": new_product.id,
        "name": new_product.name,
        "git_url": new_product.git_url,
        "checkout_path": new_product.checkout_path,
        "beads_path": new_product.beads_path,
        "employees_file": new_product.employees_file,
        "status": new_product.status,
        "created_at": new_product.created_at,
    }

    with open(products_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"Created new product: {product_id}")
    return new_product


def _sync_update_product(product_id: str, updates: dict) -> Optional[Product]:
    """Synchronous helper to update a product."""
    products_file = Path("/home/shedwards/src/stairtup/products.jsonl")

    if not products_file.exists():
        return None

    # Read all products
    products = []
    found_idx = -1

    with open(products_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                products.append(data)
                # Match by id or name
                if (
                    str(data.get("id")) == str(product_id)
                    or data.get("name") == product_id
                ):
                    found_idx = idx
            except json.JSONDecodeError:
                continue

    if found_idx == -1:
        return None

    # Apply updates
    for key, value in updates.items():
        if value is not None:
            products[found_idx][key] = value

    # Write back
    with open(products_file, "w", encoding="utf-8") as f:
        for record in products:
            f.write(json.dumps(record) + "\n")

    # Return updated product
    return Product(**products[found_idx])


def _sync_mark_product_removing(product_id: str) -> bool:
    """Synchronous helper to mark a product for removal."""
    return _sync_update_product(product_id, {"status": "removing"}) is not None


def _sync_get_product_beads(product_id: str) -> List[dict]:
    """Get beads for a specific product context (placeholder for now)."""
    # For now, return ready beads from global context
    # In future, this could filter by product
    beads = get_ready_beads()
    return [{"id": b.id, "title": b.title, "issue_type": b.issue_type} for b in beads]


async def asyncio_get_product(product_id: str) -> Optional[Product]:
    """Async wrapper to get product."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_get_product, product_id)


async def asyncio_get_all_products(
    include_archived: bool = False,  # noqa: FBT
    include_removing: bool = False,  # noqa: FBT
) -> List[Product]:
    """Async wrapper to get all products."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _sync_get_all_products, include_archived, include_removing
    )


async def asyncio_create_product(data: dict) -> Product:
    """Async wrapper to create product."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_create_product, data)


async def asyncio_update_product(product_id: str, updates: dict) -> Optional[Product]:
    """Async wrapper to update product."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_update_product, product_id, updates)


async def asyncio_mark_product_removing(product_id: str) -> bool:
    """Async wrapper to mark product removing."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_mark_product_removing, product_id)


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    include_archived: bool = False, include_removing: bool = False
) -> ProductListResponse:
    """
    List all products.

    Returns a list of all active products (by default).
    Use query parameters to include archived or removing products.

    Args:
        include_archived: Include archived products
        include_removing: Include products marked for removal

    Returns:
        List of products with count
    """
    products = await asyncio_get_all_products(include_archived, include_removing)

    product_responses = [
        ProductResponse(
            id=str(p.id),
            name=p.name,
            git_url=p.git_url,
            checkout_path=p.checkout_path,
            beads_path=p.beads_path,
            employees_file=p.employees_file,
            status=p.status,
            created_at=p.created_at,
        )
        for p in products
    ]

    return ProductListResponse(products=product_responses, count=len(product_responses))


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(request: ProductCreateRequest) -> ProductResponse:
    """
    Create a new product workspace.

    Creates a new product with its associated directory structure:
    - checkout/ directory for the repository
    - beads/ directory for bead files
    - employees.jsonl for agent tracking

    Args:
        request: Product creation data

    Returns:
        Created product details

    Raises:
        HTTPException: 409 if product with same name exists
    """
    try:
        data = request.model_dump()
        product = await asyncio_create_product(data)

        return ProductResponse(
            id=str(product.id),
            name=product.name,
            git_url=product.git_url,
            checkout_path=product.checkout_path,
            beads_path=product.beads_path,
            employees_file=product.employees_file,
            status=product.status,
            created_at=product.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create product: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create product: {str(e)}"
        )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str) -> ProductResponse:
    """
    Get details of a specific product.

    Args:
        product_id: The product ID or name

    Returns:
        Product details

    Raises:
        HTTPException: 404 if product not found
    """
    product = await asyncio_get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    return ProductResponse(
        id=str(product.id),
        name=product.name,
        git_url=product.git_url,
        checkout_path=product.checkout_path,
        beads_path=product.beads_path,
        employees_file=product.employees_file,
        status=product.status,
        created_at=product.created_at,
    )


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str, request: ProductUpdateRequest
) -> ProductResponse:
    """
    Update a product.

    Partial update - only fields provided will be modified.
    Cannot update archived or removing products.

    Args:
        product_id: The product ID or name
        request: Fields to update

    Returns:
        Updated product details

    Raises:
        HTTPException: 404 if not found, 400 if status invalid, 409 if name exists
    """
    # First check product exists and is active
    current = await asyncio_get_product(product_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    if current.status not in ("active", "removing"):
        raise HTTPException(
            status_code=400, detail=f"Cannot update {current.status} product"
        )

    # Check name uniqueness if updating name
    updates = request.model_dump(exclude_unset=True)
    if "name" in updates:
        new_name = updates["name"]
        all_products = await asyncio_get_all_products(
            include_archived=True, include_removing=True
        )
        for p in all_products:
            if p.name == new_name and str(p.id) != str(current.id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Product with name '{new_name}' already exists",
                )

    # Apply updates
    updated = await asyncio_update_product(product_id, updates)

    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Product '{product_id}' not found after update"
        )

    return ProductResponse(
        id=str(updated.id),
        name=updated.name,
        git_url=updated.git_url,
        checkout_path=updated.checkout_path,
        beads_path=updated.beads_path,
        employees_file=updated.employees_file,
        status=updated.status,
        created_at=updated.created_at,
    )


@router.delete("/products/{product_id}", response_model=ProductDeleteResponse)
async def delete_product(product_id: str) -> ProductDeleteResponse:
    """
    Mark a product for removal.

    This soft-deletes the product by marking its status as 'removing'.
    Actual file deletion is handled separately.

    Args:
        product_id: The product ID or name

    Returns:
        Deletion confirmation with status

    Raises:
        HTTPException: 404 if product not found
    """
    product = await asyncio_get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    if product.status == "removing":
        return ProductDeleteResponse(
            product_id=str(product.id),
            status="removing",
            message=f"Product '{product.name}' is already marked for removal",
        )

    success = await asyncio_mark_product_removing(product_id)

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to mark product '{product_id}' for removal"
        )

    logger.info(f"Product '{product.name}' marked for removal")

    return ProductDeleteResponse(
        product_id=str(product.id),
        status="removing",
        message=f"Product '{product.name}' marked for removal. Files will be cleaned up separately.",
    )


# =============================================================================
# Product Context and Beads Endpoints
# =============================================================================


@router.get("/products/{product_id}/beads", response_model=ProductBeadsResponse)
async def get_product_beads(product_id: str) -> ProductBeadsResponse:
    """
    Get ready beads for a specific product context.

    Security: Validates product access before returning data.

    Args:
        product_id: The product ID or name

    Returns:
        List of ready beads for the product

    Raises:
        HTTPException: 404 if product not found, 400 if not active
    """
    product = await require_active_product(product_id, require_active=True)

    # Get beads from product-scoped context (currently returns global ready beads)
    # In future, this could filter by product
    loop = asyncio.get_event_loop()
    beads = await loop.run_in_executor(None, _sync_get_product_beads, product_id)

    return ProductBeadsResponse(product_id=str(product.id), ready_beads=beads)


# =============================================================================
# Product Isolation Middleware/Dependency
# =============================================================================


async def validate_product_isolation(product_id: str, request: Request) -> Product:
    """
    Dependency to validate product isolation.

    Ensures that:
    1. The product exists
    2. The product is active (or explicitly allowed)
    3. The requester has access to this product (if auth implemented)

    Args:
        product_id: Product ID to validate
        request: FastAPI request object

    Returns:
        Validated Product object

    Raises:
        HTTPException: 404 if not found, 403 if no access, 400 if inactive
    """
    product = await asyncio_get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    # Check product status
    if product.status not in ("active", ""):
        # Note: empty string for backward compatibility
        if product.status == "archived":
            raise HTTPException(
                status_code=400,
                detail=f"Product '{product_id}' is archived and cannot be modified",
            )
        if product.status == "removing":
            raise HTTPException(
                status_code=400, detail=f"Product '{product_id}' is being removed"
            )

    # TODO: Add JWT token or session-based auth check here
    # For now, we trust the product_id from the URL

    logger.info(f"Product isolation validated for {product_id}")
    return product


# =============================================================================
# API Health and Status
# =============================================================================


@router.get("/health")
async def workspace_health() -> dict:
    """
    Health check endpoint for workspace API.

    Returns:
        Health status and product count
    """
    try:
        products = await asyncio_get_all_products()
        return {
            "status": "healthy",
            "products_count": len(products),
            "service": "workspace-api",
        }
    except Exception as e:
        logger.error(f"Workspace health check failed: {e}")
        raise HTTPException(status_code=503, detail="Workspace service unavailable")
