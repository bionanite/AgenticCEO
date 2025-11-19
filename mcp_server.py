# mcp_server.py
from __future__ import annotations

from typing import Dict, Any

from mcp.server.fastmcp import FastMCP

from company_brain import CompanyBrain

mcp = FastMCP("CompanyBrain")
brain = CompanyBrain()


@mcp.tool()
def plan_day() -> str:
    """Generate the daily operating plan from the Agentic CEO."""
    return brain.daily_start()


@mcp.tool()
def ingest_event(event_type: str, payload: Dict[str, Any]) -> str:
    """
    Ingest an event into the Company Brain.
    Example event_type: 'daily_check_in', 'kpi_alert', 'client_issue'
    """
    return brain.ingest_event(event_type, payload)


@mcp.tool()
def record_kpi(metric_name: str, value: float, unit: str = "", source: str = "") -> Dict[str, Any]:
    """Record a KPI value and let the CEO react if thresholds are breached."""
    return brain.record_kpi(metric_name, value, unit, source)


@mcp.tool()
def run_pending_tasks() -> Dict[str, Any]:
    """Execute all pending tasks the CEO has created."""
    results = brain.run_pending_tasks()
    return {"results": results}


@mcp.tool()
def reflect() -> str:
    """Generate a reflection summary for today."""
    return brain.reflect()


if __name__ == "__main__":
    # Run as MCP server via stdio
    mcp.run(transport="stdio")