"""
Auto-Bead System: Bug reporting with DOM and console capture
Provides a 'Bug' button on any web page that creates beads with full context.
"""

import os
import json
import subprocess
import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def get_working_directory() -> str:
    """Get the working directory for the app (works in Docker or local)."""
    cwd = os.getcwd()
    if cwd == "/app" or cwd.startswith("/app/"):
        return "/app"
    if Path(cwd + "/.beads").exists():
        return cwd
    for path in [cwd, "/app", "."]:
        if Path(path + "/.beads").exists():
            return path
    return cwd


def extract_bead_id(output: str) -> str:
    """Extract bead ID from bd CLI output."""
    # bd output format: "✓ Created issue: stairtup-abc123"
    match = re.search(r"(stairtup-[a-z0-9]+)", output, re.IGNORECASE)
    if match:
        return match.group(1)
    return "__unknown_id__"


def create_bug_bead(
    title: str, description: str, dom_snapshot: str, console_logs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create a bead from bug report data."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bead_title = f"[BUG] {title[:50]}..." if len(title) > 50 else f"[BUG] {title}"

    description_full = f"""Bug Report - {timestamp}

## Description
{description}

## Browser Context
- DOM Snapshot: {len(dom_snapshot)} characters
- Console Logs: {len(console_logs)} entries

## Console Logs
{json.dumps(console_logs, indent=2)}

---
Captured via Auto-Bead Bug Reporter
"""

    try:
        result = subprocess.run(
            [
                "bd",
                "create",
                "--title",
                bead_title,
                "--description",
                description_full[:500],
                "--priority",
                "3",
            ],
            cwd=get_working_directory(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # Check both stdout and stderr for bead ID
            output = result.stdout + result.stderr
            bead_id = extract_bead_id(output)
            return {
                "success": True,
                "bead_id": bead_id,
                "title": bead_title,
                "message": f"Bug reported as bead {bead_id}",
            }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "message": "Failed to create bead",
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Exception during bead creation",
        }


def escape_html(text: str) -> str:
    """Escape HTML characters for safe storage."""
    return html.escape(text)
