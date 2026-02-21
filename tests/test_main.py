"""
Tests for the main FastAPI application.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """
    Fixture to provide an async HTTP client for testing.

    Yields:
        AsyncClient configured for the test application
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """
    Test the health check endpoint returns expected status.

    Args:
        client: Async HTTP test client fixture
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "agent-company-swarm"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """
    Test the root endpoint returns HTML response.

    Args:
        client: Async HTTP test client fixture
    """
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
