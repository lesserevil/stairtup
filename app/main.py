"""
Agent Company Swarm - Main FastAPI Application

This module initializes the FastAPI application for the multi-agent company system.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.openai_compat import router as openai_router


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

    def read_employees_jsonl() -> list[dict[str, Any]]:
        """Read and parse the employees.jsonl file."""
        employees_path = Path("employees.jsonl")
        employees = []

        if not employees_path.exists():
            return employees

        try:
            with open(employees_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and line != "[]":
                        try:
                            record = json.loads(line)
                            employees.append(record)
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

        return employees

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        """
        Root endpoint returning the landing page.

        Args:
            request: FastAPI request object

        Returns:
            HTML response with the landing page template
        """
        return templates.TemplateResponse(
            "index.html", {"request": request, "title": "Agent Company Swarm"}
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        """
        CEO Dashboard endpoint with live office view and Slaick feed.

        Args:
            request: FastAPI request object

        Returns:
            HTML response with the dashboard template
        """
        employees = read_employees_jsonl()
        active_employees = [emp for emp in employees if emp.get("status") == "active"]

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "title": "Agent Company Swarm",
                "employees": active_employees,
                "employee_count": len(active_employees),
                "model_count": len(active_employees),
            },
        )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint for monitoring.

        Returns:
            Dictionary with status information
        """
        return {"status": "healthy", "service": "agent-company-swarm"}

    # Mount the OpenAI-compatible API router under /api prefix
    app.include_router(openai_router, prefix="/api")

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Default to port 9754 as requested by the CEO
    uvicorn.run(app, host="0.0.0.0", port=9754, reload=True)
