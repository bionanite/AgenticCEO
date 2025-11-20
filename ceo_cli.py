#!/usr/bin/env python3
"""
ceo_cli.py

Tiny CLI for interacting with the Agentic CEO / CompanyBrain.

Commands (interactive prompt):
  - plan       → Ask CEO to plan the day
  - kpi        → Record a KPI reading (and trigger alerts if out of range)
  - event      → Send a custom CEOEvent
  - brief      → Get personal CEO briefing (what the human CEO should do today)
  - snapshot   → High-level daily snapshot
  - tasks      → Show open task tree (parent/child)
  - vstaff     → Show basic virtual staff info
  - run        → Run all pending tasks (delegation + virtual staff)
  - help       → Show commands
  - quit/exit  → Leave CLI
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional
from urllib import request, error as urlerror

from company_brain import CompanyBrain
from agentic_ceo import MCPClient


# ------------------------------------------------------------
# Simple HTTP MCP client (optional)
# ------------------------------------------------------------

class SimpleHTTPMCPClient:
    """
    Minimal HTTP-based MCP client.

    Expects an MCP server that exposes tools at:
        POST {base_url}/tools/{tool_name}
    with JSON body:
        {"args": {...}}

    The response should be JSON. On any failure, we return a structured
    error instead of raising.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/tools/{tool_name}"
        payload = json.dumps({"args": args}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8") or "{}"
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    return {
                        "ok": False,
                        "tool": tool_name,
                        "error": "Invalid JSON returned from MCP server",
                        "raw": body,
                    }
                # If server didn't include ok, assume success
                if isinstance(data, dict) and "ok" not in data:
                    data["ok"] = True
                data.setdefault("tool", tool_name)
                return data
        except urlerror.HTTPError as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": f"HTTPError {e.code}: {e.reason}",
            }
        except urlerror.URLError as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": f"URLError: {e.reason}",
            }
        except Exception as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": str(e),
            }


# ------------------------------------------------------------
# Command helpers
# ------------------------------------------------------------

def cmd_plan(brain: CompanyBrain) -> None:
    print("\n=== DAILY PLAN ===")
    plan = brain.plan_day()
    print(plan)


def cmd_kpi(brain: CompanyBrain) -> None:
    try:
        metric_name = input("Metric name (e.g. MRR, MAU): ").strip()
        if not metric_name:
            print("Metric name is required.")
            return

        val_raw = input("Value (number): ").strip()
        value = float(val_raw)

        unit = input("Unit (e.g. USD, users) [optional]: ").strip() or "auto"
        source = input("Source [default: manual]: ").strip() or "manual"

        res = brain.record_kpi(
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=source,
        )
        print("\nKPI RESULT:")
        print(json.dumps(res, indent=2, default=str))
    except Exception as e:
        print(f"Error recording KPI: {e}")


def cmd_event(brain: CompanyBrain) -> None:
    event_type = input("Event type (e.g. deal_closed, incident): ").strip()
    if not event_type:
        print("Event type is required.")
        return

    payload_raw = input(
        "Payload as JSON (e.g. {\"foo\": \"bar\", \"amount\": 123}): "
    ).strip()

    if not payload_raw:
        payload: Dict[str, Any] = {}
    else:
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return

    try:
        print("\n=== CEO EVENT DECISION ===")
        decision = brain.ingest_event(event_type, payload)
        print(decision)
    except Exception as e:
        print(f"Error ingesting event: {e}")


def cmd_brief(brain: CompanyBrain) -> None:
    print("\n=== CEO PERSONAL BRIEFING ===")
    try:
        text = brain.personal_briefing()
        print(text)
    except Exception as e:
        print(f"Error generating briefing: {e}")


def cmd_snapshot(brain: CompanyBrain) -> None:
    print("\n=== SNAPSHOT ===")
    try:
        snap = brain.snapshot()
        print(snap)
    except Exception as e:
        print(f"Error generating snapshot: {e}")


def cmd_tasks(brain: CompanyBrain) -> None:
    print("\n=== OPEN TASK TREE ===")
    try:
        tree = brain.open_task_tree()
        if not tree.strip():
            print("(no open tasks)")
        else:
            print(tree)
    except Exception as e:
        print(f"Error showing task tree: {e}")


def cmd_vstaff(brain: CompanyBrain) -> None:
    """
    For now, just a lightweight placeholder.

    Later we can wire this to a VirtualEmployeeDashboard helper
    once VirtualStaffManager exposes a snapshot / describe_all method.
    """
    print("\n=== VIRTUAL STAFF (BASIC INFO) ===")
    try:
        print(f"Company ID: {brain.company_id}")
        print("Virtual staff manager is initialized.")
        print("Dashboard view can be added once VirtualStaffManager exposes a snapshot helper.")
    except Exception as e:
        print(f"Error accessing virtual staff: {e}")


def cmd_run(brain: CompanyBrain) -> None:
    print("\n=== RUN PENDING TASKS ===")
    try:
        results = brain.run_pending_tasks()
        if not results:
            print("No pending tasks.")
            return
        print(json.dumps(results, indent=2, default=str))
    except Exception as e:
        print(f"Error running tasks: {e}")


def print_help() -> None:
    print(
        "\nCommands:\n"
        "  plan       - Generate daily plan\n"
        "  kpi        - Record a KPI reading (and handle alerts)\n"
        "  event      - Send a custom CEOEvent\n"
        "  brief      - Show personal CEO briefing (3 actions for the human CEO)\n"
        "  snapshot   - Show compact summary (decisions, KPIs, tokens, etc.)\n"
        "  tasks      - Show open task tree (parent/child tasks)\n"
        "  vstaff     - Show basic virtual staff info\n"
        "  run        - Run all pending tasks (delegation + virtual staff)\n"
        "  help       - Show this help\n"
        "  quit/exit  - Exit CLI\n"
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic CEO CLI")
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("AGENTIC_CEO_CONFIG", "company_config.yaml"),
        help="Path to company_config.yaml (default: env AGENTIC_CEO_CONFIG or company_config.yaml)",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=os.getenv("AGENTIC_CEO_COMPANY", "next_ecosystem"),
        help="Company key from YAML (default: env AGENTIC_CEO_COMPANY or next_ecosystem)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["auto", "approval", "dry_run"],
        default=os.getenv("AGENTIC_CEO_MODE", "auto"),
        help="Execution mode: auto | approval | dry_run (default: env AGENTIC_CEO_MODE or auto)",
    )
    return parser.parse_args(argv)


def build_mcp_client_from_env() -> Optional[MCPClient]:
    base_url = os.getenv("MCP_BASE_URL", "").strip()
    if not base_url:
        return None
    return SimpleHTTPMCPClient(base_url=base_url)


def main() -> None:
    args = parse_args()

    mcp_client = build_mcp_client_from_env()

    try:
        brain = CompanyBrain.from_config(
            config_path=args.config,
            company_key=args.company,
            execution_mode=args.mode,
            mcp_client=mcp_client,
        )
    except Exception as e:
        print(f"Error creating CompanyBrain: {e}")
        sys.exit(1)

    company_name = getattr(brain, "company_profile", None)
    if company_name is not None:
        company_display = f"{args.company} ({brain.company_profile.name})"
    else:
        company_display = args.company

    mcp_status = os.getenv("MCP_BASE_URL", "").strip() or "disabled"

    print("Agentic CEO CLI")
    print(f"- Config:  {args.config}")
    print(f"- Company: {company_display}")
    print(f"- Mode:    {args.mode}")
    print(f"- MCP:     {mcp_status}")
    print("Type 'help' to see available commands.\n")

    while True:
        try:
            cmd = input("ceo> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if cmd in ("quit", "exit"):
            print("Goodbye.")
            break
        elif cmd == "help":
            print_help()
        elif cmd == "plan":
            cmd_plan(brain)
        elif cmd == "kpi":
            cmd_kpi(brain)
        elif cmd == "event":
            cmd_event(brain)
        elif cmd == "brief":
            cmd_brief(brain)
        elif cmd == "snapshot":
            cmd_snapshot(brain)
        elif cmd == "tasks":
            cmd_tasks(brain)
        elif cmd == "vstaff":
            cmd_vstaff(brain)
        elif cmd == "run":
            cmd_run(brain)
        elif cmd == "":
            continue
        else:
            print(f"Unknown command: {cmd!r}. Type 'help'.")


if __name__ == "__main__":
    main()