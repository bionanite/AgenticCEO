#!/usr/bin/env python3
"""
ceo_auto.py

Non-interactive auto-runner for the Agentic CEO.

Typical usage (as you already do):

    python ceo_auto.py --company next_ecosystem
    python ceo_auto.py --company guardianfm
    python ceo_auto.py --company remapp

New (optional) usage with MCP + notifications:

    python ceo_auto.py --company next_ecosystem \
        --notify \
        --notify-channels slack,email

You can then hook these commands into cron or n8n so that
each morning, the script runs and drops the briefing into
Slack and/or email via MCP tools.
"""

from __future__ import annotations

import argparse
import os
import json
from typing import List

from company_brain import CompanyBrain, DEFAULT_CONFIG_PATH
from ceo_notifications import NotificationRouter


def run_auto_for_company(
    company_key: str,
    config_path: str,
    mode: str = "auto",
    notify: bool = False,
    notify_channels: List[str] | None = None,
) -> None:
    # Build brain from config
    brain = CompanyBrain.from_config(
        config_path=config_path,
        company_key=company_key,
    )

    company_name = brain.company_profile.name

    print(f"\n=== AUTO RUN for: {company_key} ===")
    print(f"Execution mode: {mode}\n")

    # --- PLAN ---
    print("=== DAILY PLAN ===")
    plan_text = brain.plan_day()
    print(plan_text)

    # --- RUN TASKS ---
    print("\n=== RUN TASKS ===")
    results = brain.run_pending_tasks()
    if results:
        print(json.dumps(results, indent=2, default=str))
    else:
        print("No tasks to run.")

    # --- SNAPSHOT ---
    print("\n=== SNAPSHOT ===")
    snapshot_text = brain.snapshot()
    print(snapshot_text)

    # --- PERSONAL BRIEFING ---
    print("\n=== CEO PERSONAL BRIEFING ===")
    brief_text = brain.personal_briefing()
    print(brief_text)
    print("\n=== AUTO RUN COMPLETE ===")

    # --- OPTIONAL NOTIFICATIONS VIA MCP TOOLS ---
    if notify:
        channels = notify_channels or []
        if not channels:
            # Allow default via env if nothing passed
            env_channels = os.getenv("AGENTIC_NOTIFY_CHANNELS", "slack,email")
            channels = [c.strip() for c in env_channels.split(",") if c.strip()]

        print(f"\n=== NOTIFICATIONS ===")
        print(f"Sending morning briefing via channels: {', '.join(channels)}")

        router = NotificationRouter()
        router.send_briefings(
            company_id=company_key,
            company_name=company_name,
            snapshot_text=snapshot_text,
            brief_text=brief_text,
            channels=channels,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic CEO Auto Runner")
    parser.add_argument(
        "--company",
        type=str,
        default=os.getenv("AGENTIC_CEO_COMPANY", "next_ecosystem"),
        help="Company key from company_config.yaml (e.g. next_ecosystem, guardianfm, remapp)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("AGENTIC_CEO_CONFIG", DEFAULT_CONFIG_PATH),
        help="Path to company config YAML (default: company_config.yaml)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=os.getenv("AGENTIC_CEO_MODE", "auto"),
        choices=["auto", "dry_run", "approval"],
        help="Execution mode label (for logging/printing only for now).",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="If set, send morning briefings via MCP tools (Slack / Email).",
    )
    parser.add_argument(
        "--notify-channels",
        type=str,
        default=None,
        help="Comma-separated channels to notify (e.g. 'slack,email'). "
             "If omitted but --notify is set, uses AGENTIC_NOTIFY_CHANNELS or 'slack,email'.",
    )

    args = parser.parse_args()

    channels: List[str] | None = None
    if args.notify_channels:
        channels = [c.strip() for c in args.notify_channels.split(",") if c.strip()]

    run_auto_for_company(
        company_key=args.company,
        config_path=args.config,
        mode=args.mode,
        notify=args.notify,
        notify_channels=channels,
    )


if __name__ == "__main__":
    main()