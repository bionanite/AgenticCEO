#!/usr/bin/env python3
"""
ceo_auto.py

Non-interactive auto-runner for the Agentic CEO.

Two modes:
1. One-shot mode (default): Runs once and exits
   python ceo_auto.py --company next_ecosystem

2. Continuous mode (autonomous): Runs continuously on a schedule
   python ceo_auto.py --company next_ecosystem --continuous --interval 3600

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

import asyncio
import argparse
import os
import json
import signal
import sys
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from company_brain import CompanyBrain, DEFAULT_CONFIG_PATH
from agentic_ceo import CEOEvent
try:
    from ceo_notifications import NotificationRouter
except ImportError:
    NotificationRouter = None  # Optional dependency


async def run_auto_for_company(
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
    # plan_day is sync, but we're in async context - wrap it
    import asyncio
    loop = asyncio.get_event_loop()
    plan_text = await loop.run_in_executor(None, brain.plan_day)
    print(plan_text)

    # --- RUN TASKS ---
    print("\n=== RUN TASKS ===")
    results = await brain.run_pending_tasks()
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
    if notify and NotificationRouter:
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


async def run_autonomous_cycle(
    company_key: str,
    config_path: str,
    mode: str = "auto",
) -> Dict[str, Any]:
    """
    Run a single autonomous cycle:
    1. Check KPIs and generate tasks if thresholds breached
    2. Run pending tasks
    3. Follow up on stale/blocked tasks
    4. Generate daily plan if no tasks exist
    5. Return cycle summary
    """
    brain = CompanyBrain.from_config(
        config_path=config_path,
        company_key=company_key,
    )
    
    cycle_start = datetime.utcnow()
    summary = {
        "cycle_start": cycle_start.isoformat(),
        "tasks_generated": 0,
        "tasks_executed": 0,
        "tasks_followed_up": 0,
        "errors": [],
    }
    
    try:
        # 1. Check KPI trends and generate preventive tasks if needed
        import asyncio
        loop = asyncio.get_event_loop()
        
        if brain.kpi_engine.trend_analyzer:
            kpi_thresholds = {
                name: {"min": t.min_value, "max": t.max_value}
                for name, t in brain.kpi_engine.thresholds.items()
            }
            proactive_recs = brain.kpi_engine.trend_analyzer.get_proactive_recommendations(
                kpi_thresholds
            )
            if proactive_recs:
                print(f"[{cycle_start.strftime('%H:%M:%S')}] Found {len(proactive_recs)} proactive KPI recommendations, generating preventive tasks...")
                # Create event for proactive recommendations
                event = CEOEvent(
                    type="kpi_trend_alert",
                    payload={
                        "recommendations": proactive_recs,
                        "source": "trend_analyzer",
                    }
                )
                await loop.run_in_executor(None, brain.ceo.ingest_event, event)
                summary["tasks_generated"] += len([t for t in brain.ceo.state.tasks if t.status != "done"])
        
        # 2. Check if we need to generate daily plan (if no tasks exist)
        pending_tasks = [t for t in brain.ceo.state.tasks if t.status != "done"]
        if not pending_tasks:
            print(f"[{cycle_start.strftime('%H:%M:%S')}] No tasks found, generating daily plan...")
            plan_text = await brain.run_autonomous_cycle()
            summary["tasks_generated"] = len([t for t in brain.ceo.state.tasks if t.status != "done"])
        
        # 3. Run pending tasks
        pending_tasks = [t for t in brain.ceo.state.tasks if t.status != "done"]
        if pending_tasks:
            print(f"[{cycle_start.strftime('%H:%M:%S')}] Running {len(pending_tasks)} pending tasks...")
            results = await brain.run_pending_tasks()
            summary["tasks_executed"] = len(results)
        
        # 4. Follow up on stale/blocked tasks
        follow_up_count = await brain.follow_up_stale_tasks()
        summary["tasks_followed_up"] = follow_up_count
        
    except Exception as e:
        error_msg = f"Error in autonomous cycle: {e}"
        print(f"[ERROR] {error_msg}")
        summary["errors"].append(error_msg)
        import traceback
        summary["traceback"] = traceback.format_exc()
    
    summary["cycle_end"] = datetime.utcnow().isoformat()
    summary["duration_seconds"] = (datetime.utcnow() - cycle_start).total_seconds()
    
    return summary


async def run_continuous_scheduler(
    company_key: str,
    config_path: str,
    interval_seconds: int = 3600,
    mode: str = "auto",
) -> None:
    """
    Run the autonomous CEO continuously on a schedule.
    
    Args:
        company_key: Company key from config
        config_path: Path to company config YAML
        interval_seconds: How often to run a cycle (default: 1 hour)
        mode: Execution mode (auto, approval, dry_run)
    """
    print(f"\n{'='*60}")
    print(f"AgenticCEO Continuous Scheduler")
    print(f"Company: {company_key}")
    print(f"Interval: {interval_seconds} seconds ({interval_seconds/60:.1f} minutes)")
    print(f"Mode: {mode}")
    print(f"{'='*60}\n")
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Received signal {signum}, shutting down gracefully...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    cycle_count = 0
    cycles_file = os.path.join(".agentic_state", "autonomy_cycles.json")
    os.makedirs(".agentic_state", exist_ok=True)
    
    try:
        while not shutdown_event.is_set():
            cycle_count += 1
            cycle_start = datetime.utcnow()
            
            print(f"\n[{cycle_start.strftime('%Y-%m-%d %H:%M:%S')}] Starting cycle #{cycle_count}")
            print("-" * 60)
            
            try:
                summary = await run_autonomous_cycle(
                    company_key=company_key,
                    config_path=config_path,
                    mode=mode,
                )
                
                print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] Cycle #{cycle_count} complete:")
                print(f"  - Tasks generated: {summary.get('tasks_generated', 0)}")
                print(f"  - Tasks executed: {summary.get('tasks_executed', 0)}")
                print(f"  - Tasks followed up: {summary.get('tasks_followed_up', 0)}")
                print(f"  - Duration: {summary.get('duration_seconds', 0):.2f}s")
                
                if summary.get('errors'):
                    print(f"  - Errors: {len(summary['errors'])}")
                    for err in summary['errors']:
                        print(f"    * {err}")
                
                # Write cycle statistics for dashboard
                try:
                    cycle_data = {
                        "total_cycles": cycle_count,
                        "last_cycle_time": cycle_start.isoformat(),
                        "last_cycle_summary": summary,
                        "company_key": company_key,
                        "interval_seconds": interval_seconds,
                    }
                    with open(cycles_file, 'w') as f:
                        json.dump(cycle_data, f, indent=2, default=str)
                except Exception as e:
                    print(f"[WARNING] Failed to write cycle stats: {e}")
                
            except Exception as e:
                print(f"[ERROR] Cycle #{cycle_count} failed: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait for next cycle (or until shutdown signal)
            if not shutdown_event.is_set():
                next_cycle = datetime.utcnow() + timedelta(seconds=interval_seconds)
                print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Next cycle scheduled for {next_cycle.strftime('%H:%M:%S')}")
                print("-" * 60)
                
                # Wait with periodic checks for shutdown signal
                wait_interval = min(60, interval_seconds)  # Check every minute or interval, whichever is smaller
                waited = 0
                while waited < interval_seconds and not shutdown_event.is_set():
                    await asyncio.sleep(wait_interval)
                    waited += wait_interval
        
        print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Scheduler stopped gracefully after {cycle_count} cycles")
        
    except KeyboardInterrupt:
        print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Interrupted by user")
    except Exception as e:
        print(f"\n[FATAL ERROR] Scheduler crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


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
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously on a schedule instead of one-shot execution.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Interval in seconds between cycles when running continuously (default: 3600 = 1 hour).",
    )

    args = parser.parse_args()

    if args.continuous:
        # Continuous mode: run scheduler
        asyncio.run(run_continuous_scheduler(
            company_key=args.company,
            config_path=args.config,
            interval_seconds=args.interval,
            mode=args.mode,
        ))
    else:
        # One-shot mode: original behavior
        channels: List[str] | None = None
        if args.notify_channels:
            channels = [c.strip() for c in args.notify_channels.split(",") if c.strip()]

        asyncio.run(run_auto_for_company(
            company_key=args.company,
            config_path=args.config,
            mode=args.mode,
            notify=args.notify,
            notify_channels=channels,
        ))


if __name__ == "__main__":
    main()