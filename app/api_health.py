"""
API health check module for dependency services.
Used for E2E integration tests.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def check_recruiter() -> dict[str, Any]:
    """Check if recruiter service is healthy by examining slaick.jsonl."""
    slaick_path = Path("slaick.jsonl")
    
    if not slaick_path.exists():
        return {
            "healthy": False,
            "details": {"reason": "slaick.jsonl not found"}
        }
    
    try:
        with open(slaick_path, "r") as f:
            lines = f.readlines()
        
        hr_messages = 0
        for line in lines[-100:]:
            try:
                msg = json.loads(line.strip())
                if msg.get("type") == "HR":
                    hr_messages += 1
            except json.JSONDecodeError:
                continue
        
        return {
            "healthy": len(lines) > 0,
            "details": {
                "slaick_messages": len(lines),
                "hr_messages": hr_messages,
            }
        }
    except Exception as e:
        return {"healthy": False, "details": {"error": str(e)}}


def check_spawner() -> dict[str, Any]:
    """Check if spawner service is healthy by examining slaick.jsonl for ACK."""
    slaick_path = Path("slaick.jsonl")
    
    if not slaick_path.exists():
        return {
            "healthy": False,
            "details": {"reason": "slaick.jsonl not found"}
        }
    
    try:
        with open(slaick_path, "r") as f:
            lines = f.readlines()
        
        ack_messages = 0
        spawner_ack = False
        for line in lines[-100:]:
            try:
                msg = json.loads(line.strip())
                if msg.get("type") == "ACK":
                    ack_messages += 1
                    if msg.get("agent_type") == "spawner":
                        spawner_ack = True
            except json.JSONDecodeError:
                continue
        
        return {
            "healthy": spawner_ack or ack_messages > 0,
            "details": {
                "slaick_messages": len(lines),
                "ack_messages": ack_messages,
            }
        }
    except Exception as e:
        return {"healthy": False, "details": {"error": str(e)}}


def check_employees() -> dict[str, Any]:
    """Check if employees are active by examining employees.jsonl."""
    employees_path = Path("employees.jsonl")
    
    if not employees_path.exists():
        return {
            "healthy": False,
            "details": {"reason": "employees.jsonl not found"}
        }
    
    try:
        with open(employees_path, "r") as f:
            lines = f.readlines()
        
        total = 0
        active = []
        for line in lines:
            line = line.strip()
            if line and line != "[]":
                try:
                    emp = json.loads(line)
                    total += 1
                    if emp.get("status") == "active":
                        active.append(emp.get("id", "unknown"))
                except json.JSONDecodeError:
                    continue
        
        return {
            "healthy": total > 0,
            "details": {
                "total_employees": total,
                "active_employees": len(active),
                "active_agent_ids": active[:10],
            }
        }
    except Exception as e:
        return {"healthy": False, "details": {"error": str(e)}}


def get_all_dependencies_status() -> dict[str, Any]:
    """Get health status of all dependency services."""
    services = [
        ("recruiter", check_recruiter),
        ("spawner", check_spawner),
        ("employees", check_employees),
    ]
    
    service_status = {}
    all_healthy = True
    
    for service_name, check_func in services:
        status = {
            "service": service_name,
            "status": "healthy" if check_func()["healthy"] else "unhealthy",
            "details": check_func()["details"],
        }
        service_status[service_name] = status
        if not check_func()["healthy"]:
            all_healthy = False
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "services": service_status,
        "timestamp": datetime.now().isoformat(),
    }
