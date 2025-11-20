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
  - vstaff     → Show basic virtual staff info (placeholder for now)
  - run        → Run all pending tasks (delegation + virtual staff)
  - help       → Show commands
  - quit/exit  → Leave CLI

You can control which company + mode via CLI flags or environment:

  AGENTIC_CEO_CONFIG  → path to company_config.yaml (default: company_config.yaml)
  AGENTIC_CEO_COMPANY → key under companies: (default: next_ecosystem)
  AGENTIC_CEO_MODE    → auto | approval | dry_run (default: auto)

Examples:

  python ceo_cli.py
  python ceo_cli.py --company guardianfm
  python ceo_cli.py --company servionsoft --mode approval
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from company_brain import CompanyBrain

# ------------------------------------------------------------
# CLI helpers
# ------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agentic CEO CLI for any company defined in company_config.yaml"
    )

    parser.add_argument(
        "--config",
        default=os.getenv("AGENTIC_CEO_CONFIG", "company_config.yaml"),
        help="Path to company_config.yaml (default: env AGENTIC_CEO_CONFIG or company_config.yaml)",
    )
    parser.add_argument(
        "--company",
        default=os.getenv("AGENTIC_CEO_COMPANY", "next_ecosystem"),
        help="Company key under `companies:` in YAML (default: env AGENTIC_CEO_COMPANY or 'next_ecosystem')",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "approval", "dry_run"],
        default=os.getenv("AGENTIC_CEO_MODE", "auto"),
        help="Execution mode: auto | approval | dry_run (default: env AGENTIC_CEO_MODE or 'auto')",
    )

    return parser.parse_args()


# ------------------------------------------------------------
# Command implementations
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


def main() -> None:
    args = parse_args()

    try:
        brain = CompanyBrain.from_config(
            config_path=args.config,
            company_key=args.company,
            execution_mode=args.mode,
        )
    except Exception as e:
        print(f"Failed to initialize CompanyBrain: {e}")
        sys.exit(1)

    print("Agentic CEO CLI")
    print(f"- Config:  {args.config}")
    print(f"- Company: {args.company} ({brain.company_profile.name})")
    print(f"- Mode:    {args.mode}")
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