"""
Agent Company Swarm - Main FastAPI Application

This module initializes the FastAPI application for the multi-agent company system.
"""

import json
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.openai_compat import router as openai_router
from app.company.workspace_manager import WorkspaceManager
import click


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
            filepath.touch()

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

    @app.get("/health/dependencies", tags=["health"])
    async def health_dependencies() -> dict[str, Any]:
        '''
        Health check endpoint for dependency services.

        Returns status of recruiter, spawner, and employees for E2E tests.

        Returns:
            Dict with overall health and per-dependency status
        '''
        from app.api_health import get_all_dependencies_status
        return get_all_dependencies_status()


    @app.post("/api/tasks/create")
    async def create_task(request: Request) -> dict[str, str]:
        """
        Create a new task (bead) via HTMX.
        
        Returns:
            Dictionary with success message
        """
        try:
            data = await request.json()
            title = data.get("title", "")
            description = data.get("description", "")
            
            if not title:
                return {"status": "error", "message": "Title is required"}
            
            # Create bead using bd CLI
            import subprocess
            result = subprocess.run(
                ["bd", "create", "--title", title, "--description", description],
                capture_output=True,
                text=True,
                cwd="/home/shedwards/src/stairtup"
            )
            
            if result.returncode == 0:
                return {"status": "success", "message": f"Task '{title}' created successfully"}
            else:
                return {"status": "error", "message": result.stderr}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    @app.get("/api/tasks/form", response_class=HTMLResponse)
    async def get_task_form(request: Request) -> HTMLResponse:
        """
        Return the task creation form HTML for HTMX.
        
        Returns:
            HTML form for creating tasks
        """
        html_content = """
        <div id="task-creator" style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 20px;">
            <h3 style="margin-top: 0; color: #f8fafc;">📝 Create New Task</h3>
            <form hx-post="/api/tasks/create" hx-target="#task-result" hx-swap="innerHTML">
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; color: #94a3b8;">Title:</label>
                    <input type="text" name="title" required 
                           style="width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; 
                                  border-radius: 6px; color: #f8fafc; box-sizing: border-box;">
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; color: #94a3b8;">Description:</label>
                    <textarea name="description" rows="3"
                              style="width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; 
                                     border-radius: 6px; color: #f8fafc; box-sizing: border-box;"></textarea>
                </div>
                <button type="submit" 
                        style="background: #3b82f6; color: white; border: none; padding: 10px 20px; 
                               border-radius: 6px; cursor: pointer; font-weight: 600;">
                    Create Task
                </button>
                <div id="task-result" style="margin-top: 15px;"></div>
            </form>
        </div>
        """
        return HTMLResponse(content=html_content)

    # Mount the OpenAI-compatible API router under /api prefix
    app.include_router(openai_router, prefix="/api")
    # Import WorkspaceManager and define route that needs app
    from app.company.workspace_manager import WorkspaceManager

    @app.get("/api/dashboard/live", tags=["dashboard"])
    async def get_dashboard_data() -> dict[str, Any]:
        """Get live dashboard data including employees, beads, cost, and slaick messages."""
        workspace = WorkspaceManager()

        # Get active employees
        from app.company.employee import Employee
        employees = Employee.get_all_active()

        # Get product info
        products = workspace.list_active_products()

        # Get cost tracking
        from app.company.cost_tracker import CostTracker
        cost_tracker = CostTracker(budget=10.0)

        return {
            "employees": [{"employee_id": e["employee_id"], "status": e["status"]} for e in employees],
            "employee_count": len(employees),
            "products": [{"name": p.name, "status": p.status} for p in products],
            "cost_tracker": {
                "total_cost": cost_tracker.get_total_cost(),
                "budget": cost_tracker.budget,
            },
        }

    
    @app.post("/api/bug-report", tags=["bug-report"])
    async def report_bug(request: Request) -> dict[str, Any]:
        """
        Create a bug report bead from browser data.
        
        Captures:
        - Bug description from user
        - Full DOM snapshot
        - Console logs
        - Browser context (URL, viewport, user agent)
        
        Returns:
            Dict with success status and created bead ID
        """
        try:
            data = await request.json()
            
            description = data.get("description", "")
            dom_snapshot = data.get("dom_snapshot", "")
            console_logs = data.get("console_logs", [])
            context = data.get("context", {})
            
            if not description:
                return {"success": False, "message": "Description is required"}
            
            # Import auto bead module
            from app.auto_bead import create_bug_bead
            
            # Create the bug bead
            result = create_bug_bead(
                title=description[:100],
                description=description,
                dom_snapshot=dom_snapshot,
                console_logs=console_logs
            )
            
            return result
            
        except Exception as e:
            return {"success": False, "message": str(e)}

    return app



# Create the application instance
app = create_app()

@click.group()
def cli():
    """Main CLI entry point for Agent Company Swarm tools."""
    pass


@cli.group()
def product():
    """Manage products in the workspace."""
    pass


@cli.group()
def project():
    """Manage projects in the workspace."""
    pass


@product.command()
@click.argument("url")
def add(url: str):
    """Add a new product from a Git repository URL."""
    # Extract product_id from URL (last part after last '/')
    product_id = url.rstrip("/").split("/")[-1].lower()
    product_name = product_id

    # Check if product already exists
    try:
        existing_products = WorkspaceManager.list_active_products()
        for p in existing_products:
            if p.name == product_id:
                click.echo(f"Error: Product '{product_id}' already exists.", err=True)
                raise SystemExit(1)
    except FileNotFoundError:
        # products.jsonl doesn't exist yet, that's fine
        pass

    # Define paths
    checkout_path = Path(f"products/{product_id}/checkout")
    beads_path = Path(f"products/{product_id}/beads")
    employees_file = Path(f"products/{product_id}/employees.jsonl")

    # Clone the repository
    try:
        subprocess.run(
            ["git", "clone", url, str(checkout_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Error cloning repository: {e.stderr}", err=True)
        raise SystemExit(1)

    # Create product directory structure
    WorkspaceManager.create_product_structure(product_id, product_name)

    # Register the product in products.jsonl
    products_file = Path("products.jsonl")
    new_product = {
        "id": 1,  # Simple ID assignment - could be improved
        "name": product_id,
        "git_url": url,
        "checkout_path": str(checkout_path),
        "beads_path": str(beads_path),
        "employees_file": str(employees_file),
        "status": "active",
        "created_at": datetime.now().isoformat(),
    }

    # Find the next available ID
    if products_file.exists():
        with open(products_file, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
            if lines:
                try:
                    last_product = json.loads(lines[-1])
                    new_product["id"] = last_product.get("id", 0) + 1
                except json.JSONDecodeError:
                    pass

    # Append to products.jsonl
    with open(products_file, "a") as f:
        f.write(json.dumps(new_product) + "\n")

    click.echo(f"Product '{product_id}' added successfully.")


@project.command()
@click.argument("product_id")
@click.argument("name")
def create(product_id: str, name: str):
    """Create a new project under a product."""
    # Verify product exists
    try:
        active_products = WorkspaceManager.list_active_products()
        product = next(p for p in active_products if p.name == product_id)
    except StopIteration:
        click.echo(f"Error: Product '{product_id}' does not exist.", err=True)
        raise SystemExit(1)
    except FileNotFoundError:
        click.echo("Error: products.jsonl not found.", err=True)
        raise SystemExit(1)
    # Generate project ID
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    project_id = f"project-{product_id}-{timestamp}"
    # Create project record
    project_record = {
        "id": project_id,
        "product_id": product_id,
        "name": name,
        "description": "",
        "status": "active",
        "deliverables": [],
        "created_at": datetime.now().isoformat(),
        "target_completion": None,
    }
    # Append to projects.jsonl
    projects_file = Path("projects.jsonl")
    with open(projects_file, "a") as f:
        f.write(json.dumps(project_record) + "\n")
    click.echo(f"Project '{project_id}' created successfully under product '{product_id}'.")


@cli.command()
def whoami():
    """Show which product we're working on."""
    # Check for current product context
    context_file = Path(".product_context")
    if context_file.exists():
        with open(context_file, "r") as f:
            product_id = f.read().strip()
        click.echo(f"Current product: {product_id}")
        
        # Show additional context if available
        try:
            products = WorkspaceManager.list_active_products()
            for p in products:
                if p.name == product_id:
                    click.echo(f"  Git URL: {p.git_url}")
                    click.echo(f"  Status: {p.status}")
                    click.echo(f"  Created: {p.created_at}")
                    break
        except FileNotFoundError:
            click.echo("  (products.jsonl not found)")
        except Exception as e:
            click.echo(f"  (could not load product details: {e})")
    else:
        click.echo("No product selected.")
        click.echo("Use 'bd product add <url>' to add a product first.")


import uvicorn


# CLI command to run the server
@cli.command()
def run_server(port: int = 9754, reload: bool = False):
    """Run the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=port, reload=reload)


# CLI command to show CLI help
@cli.command()
def help_cmd():
    """Show help text for the bd CLI."""
    click.echo(click.get_current_context().find_root().get_help())


if __name__ == "__main__":
    cli()
