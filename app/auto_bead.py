"""
Auto-Bead System: Bug reporting with DOM and console capture
Provides a 'Bug' button on any web page that creates beads with full context.
"""

import json
import subprocess
import html
from datetime import datetime
from pathlib import Path
from typing import Any


def create_bug_bead(title: str, description: str, dom_snapshot: str, console_logs: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Create a bead from bug report data.
    
    Args:
        title: Bug title/summary
        description: Detailed bug description
        dom_snapshot: Full DOM HTML capture
        console_logs: List of console log entries
    
    Returns:
        Dict with bead creation result
    """
    # Create bead title with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bead_title = f"[BUG] {title[:50]}..." if len(title) > 50 else f"[BUG] {title}"
    
    # Create comprehensive description
    description_full = f"""
Bug Report - {timestamp}

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
    
    # Save to temporary file for bd CLI
    temp_file = Path(f"temp_bug_{datetime.now().timestamp()}.md")
    with open(temp_file, "w") as f:
        f.write(description_full)
    
    try:
        # Use bd CLI to create bead
        # Write description to temp file for CLI
        result = subprocess.run(
            ["bd", "create", "--title", bead_title, 
             "--description", description_full[:500],
             "--priority", "3"],
            cwd="/home/shedwards/src/stairtup",
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Clean up temp file
            temp_file.unlink(missing_ok=True)
            
            # Extract bead ID from output
            bead_id = extract_bead_id(result.stdout)
            
            return {
                "success": True,
                "bead_id": bead_id,
                "title": bead_title,
                "message": f"Bug reported as bead {bead_id}"
            }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "message": "Failed to create bead"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Exception during bead creation"
        }


def extract_bead_id(output: str) -> str:
    """Extract bead ID from bd CLI output."""
    lines = output.split("\n")
    for line in lines:
        if "[ ]" in line or "[x]" in line:
            parts = line.split()
            if len(parts) > 1 and parts[1].startswith("stairtup-"):
                return parts[1]
    return "__unknown_id__"


def escape_html(text: str) -> str:
    """Escape HTML characters for safe storage."""
    return html.escape(text)


def capture_dom():
    """
    JavaScript function to capture full DOM.
    Returns as pure JS code to be executed in browser context.
    """
    return """
    (function() {
        return {
            fullHtml: document.documentElement.outerHTML,
            location: location.href,
            userAgent: navigator.userAgent,
            screen: {
                width: window.screen.width,
                height: window.screen.height,
                colorDepth: window.screen.colorDepth
            }
        };
    })();
    """


def capture_console_logs():
    """
    JavaScript function to capture all console logs.
    Returns as pure JS code to be executed in browser context.
    """
    return """
    (function() {
        return window._auto_bead_console_logs || [];
    })();
    """
