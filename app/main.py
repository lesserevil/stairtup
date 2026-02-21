"""
Agent Company Swarm - Main FastAPI Application

This module initializes the FastAPI application for the multi-agent company system.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler for startup and shutdown events.

    Handles initialization of JSONL files and any other startup tasks.
    """
    # Startup: Initialize data files if needed
    from pathlib import Path

    data_files = ["slaick.jsonl", "employees.jsonl"]
    for filename in data_files:
        filepath = Path(filename)
        if not filepath.exists():
            filepath.write_text("[]\n")

    yield

    # Shutdown: Cleanup (if needed)


def create_app() -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Agent Company Swarm",
        description="Self-organizing multi-agent company system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Templates configuration
    templates = Jinja2Templates(directory="templates")

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        """
        Root endpoint returning the main dashboard.

        Args:
            request: FastAPI request object

        Returns:
            HTML response with the dashboard template
        """
        return templates.TemplateResponse(
            "index.html", {"request": request, "title": "Agent Company Swarm"}
        )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint for monitoring.

        Returns:
            Dictionary with status information
        """
        return {"status": "healthy", "service": "agent-company-swarm"}

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
