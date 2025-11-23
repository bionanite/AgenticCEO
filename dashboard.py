"""
Agentic CEO – Control Dashboard (Upgraded)

FastAPI app that shows and controls your Agentic CEO:

- Snapshot metrics (today + previous day)
- Company context
- Open tasks table (with approve / run actions)
- System load + tasks-by-area charts
- Virtual employees & their allocated tasks
- Buttons to "Plan Day" and "Run Pending Tasks"

Run via uvicorn (recommended):
    uvicorn dashboard:app --reload --port 8080

Or directly:
    python dashboard.py --port 8080
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from company_brain import CompanyBrain, DEFAULT_CONFIG_PATH, DEFAULT_COMPANY_KEY

# -------------------------------------------------------------------
# Brain lifecycle
# -------------------------------------------------------------------

_brain: Optional[CompanyBrain] = None


def get_brain() -> CompanyBrain:
    """
    Lazy-initialize a single CompanyBrain per process.

    Uses env vars:
      AGENTIC_CEO_CONFIG
      AGENTIC_CEO_COMPANY
    """
    global _brain
    if _brain is not None:
        return _brain

    config_path = os.getenv("AGENTIC_CEO_CONFIG", DEFAULT_CONFIG_PATH)
    company_key = os.getenv("AGENTIC_CEO_COMPANY", DEFAULT_COMPANY_KEY)

    _brain = CompanyBrain.from_config(config_path=config_path, company_key=company_key)
    return _brain


# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------

app = FastAPI(title="Agentic CEO Control Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def parse_snapshot(snapshot: str) -> Dict[str, Any]:
    """
    Parse the textual snapshot produced by CompanyBrain.snapshot()
    to extract numeric metrics.

    Defensive by design so format changes don't crash things.
    """
    metrics: Dict[str, Any] = {
        "date": None,
        "decisions_made": 0,
        "tool_calls": 0,
        "kpi_updates": 0,
        "events_processed": 0,
        "llm_calls": 0,
        "tokens_used": 0,
        "open_tasks": 0,
    }

    if not snapshot:
        return metrics

    # Date line: "Reflection for 2025-11-20:"
    m = re.search(r"Reflection for\s+(\d{4}-\d{2}-\d{2})", snapshot)
    if m:
        metrics["date"] = m.group(1)

    patterns = {
        "decisions_made": r"Decisions made:\s*(\d+)",
        "tool_calls": r"Tool calls executed:\s*(\d+)",
        "kpi_updates": r"KPI updates recorded:\s*(\d+)",
        "events_processed": r"Events processed:\s*(\d+)",
        "llm_calls": r"LLM calls today:\s*(\d+)",
        "tokens_used": r"Total tokens used today:\s*(\d+)",
        "open_tasks": r"Open tasks \(not done\):\s*(\d+)",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, snapshot)
        if m:
            try:
                metrics[key] = int(m.group(1))
            except ValueError:
                pass

    return metrics


def build_tasks_payload() -> Dict[str, Any]:
    """
    Build JSON-safe task list + simple aggregations for charts.
    """
    brain = get_brain()
    ceo = brain.ceo
    tasks: List[Dict[str, Any]] = []

    for t in getattr(ceo.state, "tasks", []) or []:
        tasks.append(
            {
                "id": getattr(t, "id", ""),
                "title": getattr(t, "title", ""),
                "area": getattr(t, "area", "") or "unspecified",
                "priority": getattr(t, "priority", None),
                "owner": getattr(t, "suggested_owner", "") or "",
                "status": getattr(t, "status", "") or "unknown",
                "requires_approval": bool(getattr(t, "requires_approval", False)),
                "approved": bool(getattr(t, "approved", False)),
                "result": getattr(t, "result", None),  # Task execution result/output
            }
        )

    by_area = Counter(task["area"] for task in tasks)
    by_status = Counter(task["status"] for task in tasks)

    return {
        "tasks": tasks,
        "by_area": dict(by_area),
        "by_status": dict(by_status),
    }


def build_vstaff_payload() -> Dict[str, Any]:
    """
    Try to return a normalized view of virtual employees + their tasks.

    We are defensive here because VirtualStaffManager may evolve.
    """
    brain = get_brain()
    vsm = getattr(brain, "virtual_staff", None)
    if vsm is None:
        return {"employees": [], "meta": {}}

    summary: Dict[str, Any] = {}
    if hasattr(vsm, "summarize"):
        summary = vsm.summarize()  # type: ignore[attr-defined]
    elif hasattr(vsm, "to_dict"):
        summary = vsm.to_dict()  # type: ignore[attr-defined]

    if not isinstance(summary, dict):
        return {"employees": [], "meta": {"raw": summary}}

    employees = summary.get("employees") or summary.get("virtual_employees") or []

    # Normalize minimal fields expected by UI
    normalized: List[Dict[str, Any]] = []
    for e in employees:
        if not isinstance(e, dict):
            continue
        normalized.append(
            {
                "id": e.get("id"),
                "name": e.get("name") or e.get("display_name") or e.get("role"),
                "role": e.get("role"),
                "tasks": e.get("tasks") or e.get("assigned_tasks") or [],
                "remaining_slots": e.get("remaining_task_slots") or e.get(
                    "remaining_slots"
                ),
            }
        )

    return {"employees": normalized, "meta": {k: v for k, v in summary.items() if k not in ("employees", "virtual_employees")}}


def get_previous_date_str(offset_days: int = 1) -> str:
    today = get_brain().ceo.state.date  # assume YYYY-MM-DD
    try:
        base = dt.datetime.strptime(today, "%Y-%m-%d").date()
    except Exception:
        base = dt.date.today()
    prev = base - dt.timedelta(days=offset_days)
    return prev.isoformat()


# -------------------------------------------------------------------
# API endpoints – used by frontend JS
# -------------------------------------------------------------------


@app.get("/api/dashboard")
def api_dashboard() -> JSONResponse:
    """
    Structured snapshot for dashboards / APIs using CompanyBrain.get_dashboard_state().
    """
    brain = get_brain()
    state = brain.get_dashboard_state()
    return JSONResponse(state)


@app.get("/api/snapshot")
def api_snapshot(day: str = "today") -> JSONResponse:
    """
    Returns snapshot text + parsed metrics.

    day: "today" | "yesterday" | "d-2" (optional simple offsets)
    """
    brain = get_brain()

    if day == "today":
        snap_text = brain.snapshot()
    else:
        # Very simple date offset parser: "yesterday" or "d-N"
        if day == "yesterday":
            offset = 1
        elif day.startswith("d-"):
            try:
                offset = int(day[2:])
            except ValueError:
                offset = 1
        else:
            offset = 1

        target_date = get_previous_date_str(offset)
        try:
            snap_text = brain.ceo.memory.summarize_day(target_date)
        except Exception:
            snap_text = f"No snapshot available for {target_date}."

    metrics = parse_snapshot(snap_text)

    company = getattr(brain, "company_profile", None)
    if company is None:
        company_info = {}
    else:
        company_info = {
            "id": getattr(brain, "company_id", company.name),
            "name": company.name,
            "industry": getattr(company, "industry", ""),
            "vision": getattr(company, "vision", ""),
            "mission": getattr(company, "mission", ""),
            "north_star_metric": getattr(company, "north_star_metric", ""),
            "primary_markets": getattr(company, "primary_markets", []) or [],
            "products_or_services": getattr(company, "products_or_services", []) or [],
        }

    return JSONResponse(
        {
            "snapshot_text": snap_text,
            "metrics": metrics,
            "company": company_info,
            "day": day,
        }
    )


@app.get("/api/tasks")
def api_tasks() -> JSONResponse:
    """
    Return current tasks + simple aggregations.
    """
    payload = build_tasks_payload()
    brain = get_brain()
    needing_approval = brain.get_tasks_requiring_approval()
    payload["needs_approval_count"] = len(needing_approval)
    return JSONResponse(payload)


@app.get("/api/tasks/requiring_approval")
def api_tasks_requiring_approval() -> JSONResponse:
    brain = get_brain()
    tasks_payload = []
    for t in brain.get_tasks_requiring_approval():
        tasks_payload.append(
            {
                "id": getattr(t, "id", ""),
                "title": getattr(t, "title", ""),
                "area": getattr(t, "area", ""),
                "priority": getattr(t, "priority", None),
                "owner": getattr(t, "suggested_owner", ""),
                "status": getattr(t, "status", ""),
            }
        )
    return JSONResponse({"tasks": tasks_payload})


@app.post("/api/tasks/{task_id}/approve")
def api_approve_task(task_id: str) -> JSONResponse:
    """
    Approve a task so it can run in approval mode.
    """
    brain = get_brain()
    ok = brain.approve_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse({"ok": True, "task_id": task_id})


@app.post("/api/tasks/{task_id}/run")
async def api_run_single_task(task_id: str) -> JSONResponse:
    """
    Run a single task by ID (bypassing run_pending_tasks).

    Used when human approves & triggers an individual item.
    """
    brain = get_brain()
    ceo = brain.ceo
    target = None
    for t in getattr(ceo.state, "tasks", []) or []:
        if getattr(t, "id", None) == task_id:
            target = t
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await ceo.run_task(target)
    return JSONResponse({"ok": True, "task_id": task_id, "result": result})


@app.post("/api/ceo/plan")
async def api_plan_day() -> JSONResponse:
    """
    Ask Agentic CEO to generate a daily plan (tasks will be stored in state).
    """
    brain = get_brain()
    text = await brain.plan_day()
    tasks_payload = build_tasks_payload()
    return JSONResponse({"plan": text, "tasks": tasks_payload})


@app.post("/api/ceo/run_pending")
async def api_run_pending() -> JSONResponse:
    """
    Run all pending tasks (delegation + virtual staff routing).
    """
    brain = get_brain()
    results = await brain.run_pending_tasks()
    # After running, rebuild tasks for UI
    tasks_payload = build_tasks_payload()
    return JSONResponse({"results": results, "tasks": tasks_payload})


@app.get("/api/vstaff")
def api_vstaff() -> JSONResponse:
    """
    Virtual employees + their allocated tasks.
    """
    payload = build_vstaff_payload()
    return JSONResponse(payload)


# -------------------------------------------------------------------
# HTML dashboard – Tailwind + Chart.js, auto-refresh
# -------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <title>Agentic CEO Control Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />

  <!-- Tailwind via CDN -->
  <script src="https://cdn.tailwindcss.com"></script>

  <!-- Chart.js via CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <style>
    body { background: radial-gradient(circle at top, #020617, #020617 40%, #000 100%); }
    .card { background: rgba(15,23,42,0.95); border-radius: 1rem; border: 1px solid rgba(148,163,184,0.25); }
    .pill { border-radius: 9999px; }
  </style>
</head>

<body class="h-full text-slate-100">
<div class="min-h-screen max-w-7xl mx-auto px-4 py-6 space-y-6">

  <!-- Header -->
  <header class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
    <div>
      <h1 class="text-2xl md:text-3xl font-semibold tracking-tight flex items-center gap-2">
        <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-400/40 text-emerald-300 text-sm font-bold">CEO</span>
        <span>Agentic CEO Control Dashboard</span>
      </h1>
      <p class="text-slate-400 text-sm md:text-base mt-1" id="companySub">
        Loading company context…
      </p>
    </div>

    <div class="flex flex-wrap gap-2 items-center">
      <button
        id="btnPlan"
        class="pill px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-sm font-medium shadow-md shadow-emerald-500/30"
      >
        Plan Day
      </button>
      <button
        id="btnRunPending"
        class="pill px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 text-sm font-medium shadow-md shadow-sky-500/30"
      >
        Run Pending Tasks
      </button>
      <button
        id="btnRefresh"
        class="pill px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 text-sm font-medium border border-slate-700"
      >
        Refresh Now
      </button>
      <span class="pill px-3 py-2 text-xs font-mono bg-slate-900/80 border border-slate-700 text-slate-300">
        Auto-refresh: <span id="refreshCountdown">10</span>s
      </span>
    </div>
  </header>

  <!-- Top Grid: Snapshot + Company / Previous Day -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
    <!-- Snapshot Today -->
    <div class="card lg:col-span-2 p-4 md:p-6 space-y-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-sm md:text-base font-semibold text-slate-100">Snapshot – Today</h2>
        <span id="snapshotDateToday" class="text-xs text-slate-400 font-mono">—</span>
      </div>

      <pre id="snapshotTextToday" class="mt-2 text-xs md:text-sm text-slate-300 bg-slate-900/70 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
Loading snapshot…
      </pre>

      <!-- Metric chips -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div class="pill bg-slate-900/80 border border-slate-700 px-3 py-2 flex flex-col">
          <span class="text-slate-400">Decisions</span>
          <span id="metricDecisions" class="text-slate-100 text-lg font-semibold">0</span>
        </div>
        <div class="pill bg-slate-900/80 border border-slate-700 px-3 py-2 flex flex-col">
          <span class="text-slate-400">Tool Calls</span>
          <span id="metricTools" class="text-slate-100 text-lg font-semibold">0</span>
        </div>
        <div class="pill bg-slate-900/80 border border-slate-700 px-3 py-2 flex flex-col">
          <span class="text-slate-400">LLM Calls</span>
          <span id="metricLLM" class="text-slate-100 text-lg font-semibold">0</span>
        </div>
        <div class="pill bg-slate-900/80 border border-slate-700 px-3 py-2 flex flex-col">
          <span class="text-slate-400">Tokens</span>
          <span id="metricTokens" class="text-slate-100 text-lg font-semibold truncate">0</span>
        </div>
      </div>
    </div>

    <!-- Company + Previous Day Summary -->
    <div class="space-y-4">
      <!-- Company -->
      <div class="card p-4 md:p-5 space-y-3">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-100">Company</h2>
          <span id="companyId" class="text-[10px] font-mono text-slate-400"></span>
        </div>

        <div class="space-y-2 text-xs md:text-sm">
          <div>
            <p class="text-slate-400 text-[10px] uppercase tracking-wide">Name</p>
            <p id="companyName" class="text-slate-100 font-medium">—</p>
          </div>
          <div>
            <p class="text-slate-400 text-[10px] uppercase tracking-wide">Industry</p>
            <p id="companyIndustry" class="text-slate-100">—</p>
          </div>
          <div>
            <p class="text-slate-400 text-[10px] uppercase tracking-wide">North Star Metric</p>
            <p id="companyNorthStar" class="text-emerald-300 font-medium">—</p>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <p class="text-slate-400 text-[10px] uppercase tracking-wide">Markets</p>
              <p id="companyMarkets" class="text-slate-100 text-xs">—</p>
            </div>
            <div>
              <p class="text-slate-400 text-[10px] uppercase tracking-wide">Products / Apps</p>
              <p id="companyProducts" class="text-slate-100 text-xs">—</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Previous Day Summary -->
      <div class="card p-4 md:p-5 space-y-2">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-xs md:text-sm font-semibold text-slate-100">Previous Day Summary</h2>
          <span id="snapshotDateYesterday" class="text-[10px] text-slate-400 font-mono">—</span>
        </div>
        <pre id="snapshotTextYesterday" class="mt-1 text-[10px] md:text-xs text-slate-300 bg-slate-900/70 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap">
Loading yesterday…
        </pre>
      </div>
    </div>
  </section>

  <!-- Charts -->
  <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <div class="card p-4 md:p-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-slate-100">System Load Today</h2>
        <span class="text-[10px] text-slate-400 uppercase tracking-wide">Snapshot-based</span>
      </div>
      <canvas id="metricsChart" class="w-full h-56"></canvas>
    </div>

    <div class="card p-4 md:p-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-slate-100">Tasks by Area</h2>
        <span class="text-[10px] text-slate-400 uppercase tracking-wide">All states</span>
      </div>
      <canvas id="tasksAreaChart" class="w-full h-56"></canvas>
    </div>
  </section>

  <!-- Tasks Table -->
  <section class="card p-4 md:p-6 space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex flex-col gap-1">
        <h2 class="text-lg font-semibold text-slate-100">Tasks</h2>
        <p id="tasksSummary" class="text-xs text-slate-400">Loading…</p>
      </div>
      <span id="tasksApprovalBadge" class="pill px-3 py-1 text-[10px] bg-amber-500/10 border border-amber-400/40 text-amber-200 hidden">
        Tasks requiring approval: <span id="tasksApprovalCount">0</span>
      </span>
    </div>

    <div class="overflow-x-auto">
      <table class="min-w-full text-xs md:text-sm text-left">
        <thead class="border-b border-slate-700/80 text-slate-400 text-[11px] uppercase tracking-wide">
          <tr>
            <th class="px-2 py-2">ID</th>
            <th class="px-2 py-2">Title</th>
            <th class="px-2 py-2">Area</th>
            <th class="px-2 py-2">Priority</th>
            <th class="px-2 py-2">Owner</th>
            <th class="px-2 py-2">Status</th>
            <th class="px-2 py-2">Needs Approval</th>
            <th class="px-2 py-2">Approved</th>
            <th class="px-2 py-2">Actions</th>
          </tr>
        </thead>
        <tbody id="tasksTableBody" class="divide-y divide-slate-800/80 text-slate-200">
          <tr><td colspan="9" class="px-2 py-3 text-center text-slate-500">Loading tasks…</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <!-- Virtual Employees -->
  <section class="card p-4 md:p-6 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-100">Virtual Employees & Allocated Tasks</h2>
      <span id="vstaffSummary" class="text-xs text-slate-400">Loading…</span>
    </div>

    <div class="overflow-x-auto">
      <table class="min-w-full text-xs md:text-sm text-left">
        <thead class="border-b border-slate-700/80 text-slate-400 text-[11px] uppercase tracking-wide">
          <tr>
            <th class="px-2 py-2">Employee</th>
            <th class="px-2 py-2">Role</th>
            <th class="px-2 py-2">Remaining Slots</th>
            <th class="px-2 py-2">Tasks</th>
          </tr>
        </thead>
        <tbody id="vstaffTableBody" class="divide-y divide-slate-800/80 text-slate-200">
          <tr><td colspan="4" class="px-2 py-3 text-center text-slate-500">No virtual staff data available yet.</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</div>

<!-- Task Result Modal -->
<div id="resultModal" class="fixed inset-0 bg-black/70 z-50 hidden flex items-center justify-center p-4">
  <div class="card max-w-3xl w-full max-h-[80vh] flex flex-col">
    <div class="flex items-center justify-between p-4 border-b border-slate-700">
      <h3 class="text-lg font-semibold text-slate-100" id="modalTaskTitle">Task Result</h3>
      <button
        id="modalClose"
        class="text-slate-400 hover:text-slate-100 text-xl"
      >&times;</button>
    </div>
    <div class="p-4 overflow-y-auto flex-1">
      <pre id="modalTaskResult" class="text-xs md:text-sm text-slate-300 bg-slate-900/70 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap"></pre>
    </div>
  </div>
</div>

<script>
  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
  let metricsChart = null;
  let tasksAreaChart = null;
  let refreshInterval = 10;
  let countdown = refreshInterval;
  let isRunning = false;

  function updateCountdown() {
    const el = document.getElementById("refreshCountdown");
    if (!el) return;
    countdown -= 1;
    if (countdown <= 0) {
      countdown = refreshInterval;
      fetchAll(false);
    }
    el.textContent = countdown;
  }

  async function fetchSnapshot(day, targetPrefix) {
    const res = await fetch("/api/snapshot?day=" + day);
    const data = await res.json();

    const snapText = data.snapshot_text || "";
    document.getElementById("snapshotText" + targetPrefix).textContent = snapText.trim() || "No snapshot yet.";

    const m = data.metrics || {};
    if (targetPrefix === "Today") {
      document.getElementById("snapshotDateToday").textContent = m.date || "";
      document.getElementById("metricDecisions").textContent = m.decisions_made ?? 0;
      document.getElementById("metricTools").textContent = m.tool_calls ?? 0;
      document.getElementById("metricLLM").textContent = m.llm_calls ?? 0;
      document.getElementById("metricTokens").textContent = m.tokens_used ?? 0;

      // Update metrics chart
      const ctx = document.getElementById("metricsChart").getContext("2d");
      const labels = ["Decisions","Tool Calls","KPI Updates","Events","LLM Calls","Tokens"];
      const values = [
        m.decisions_made || 0,
        m.tool_calls || 0,
        m.kpi_updates || 0,
        m.events_processed || 0,
        m.llm_calls || 0,
        m.tokens_used || 0,
      ];
      if (metricsChart) metricsChart.destroy();
      metricsChart = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{
            label: "Today",
            data: values,
          }],
        },
        options: {
          scales: {
            x: {
              ticks: { color: "#e5e7eb", font: { size: 11 }},
              grid: { display: false },
            },
            y: {
              ticks: { color: "#9ca3af", font: { size: 10 }},
              grid: { color: "rgba(55,65,81,0.5)" },
            },
          },
          plugins: {
            legend: { labels: { color: "#e5e7eb" }},
          },
        },
      });

      const company = data.company || {};
      document.getElementById("companyId").textContent = company.id || "";
      document.getElementById("companyName").textContent = company.name || "—";
      document.getElementById("companyIndustry").textContent = company.industry || "—";
      document.getElementById("companyNorthStar").textContent = company.north_star_metric || "—";
      document.getElementById("companyMarkets").textContent = (company.primary_markets || []).join(", ") || "—";
      document.getElementById("companyProducts").textContent = (company.products_or_services || []).join(", ") || "—";

      const sub = document.getElementById("companySub");
      if (company.name && company.north_star_metric) {
        sub.textContent = company.name + " · North Star: " + company.north_star_metric;
      }
    } else {
      document.getElementById("snapshotDateYesterday").textContent = m.date || "";
    }
  }

  async function fetchTasks(showToast = false) {
    const res = await fetch("/api/tasks");
    const data = await res.json();

    const tasks = data.tasks || [];
    const byArea = data.by_area || {};
    const byStatus = data.by_status || {};
    const needsApproval = data.needs_approval_count || 0;

    const tbody = document.getElementById("tasksTableBody");
    tbody.innerHTML = "";

    if (tasks.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="px-2 py-3 text-center text-slate-500">No tasks yet.</td></tr>';
    } else {
      for (const t of tasks) {
        const row = document.createElement("tr");
        const statusClass = t.status === "done"
          ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/40"
          : "bg-slate-800/80 text-slate-200 border border-slate-600/70";

        const needsApprovalText = t.requires_approval ? "Yes" : "No";
        const approvedText = t.approved ? "Yes" : "No";

        row.innerHTML = `
          <td class="px-2 py-2 text-[10px] font-mono text-slate-500">${t.id ? t.id.slice(0,8) + "…" : ""}</td>
          <td class="px-2 py-2">${t.title}</td>
          <td class="px-2 py-2 text-xs text-sky-300">${t.area}</td>
          <td class="px-2 py-2 text-xs">${t.priority ?? ""}</td>
          <td class="px-2 py-2 text-xs text-amber-200">${t.owner}</td>
          <td class="px-2 py-2 text-xs">
            <span class="pill px-2 py-1 text-[10px] ${statusClass}">${t.status}</span>
          </td>
          <td class="px-2 py-2 text-xs">${needsApprovalText}</td>
          <td class="px-2 py-2 text-xs">${approvedText}</td>
          <td class="px-2 py-2 text-xs space-x-1">
            <button
              class="px-2 py-1 text-[10px] pill border border-emerald-500/60 text-emerald-200 hover:bg-emerald-500/20 ${t.requires_approval && !t.approved ? "" : "opacity-30 cursor-not-allowed"}"
              data-action="approve"
              data-id="${t.id}"
              ${t.requires_approval && !t.approved ? "" : "disabled"}
            >Approve</button>
            <button
              class="px-2 py-1 text-[10px] pill border border-sky-500/60 text-sky-200 hover:bg-sky-500/20 ${t.status !== "done" ? "" : "opacity-30 cursor-not-allowed"}"
              data-action="run"
              data-id="${t.id}"
              ${t.status !== "done" ? "" : "disabled"}
            >Run</button>
            ${t.status === "done" && t.result ? `
            <button
              class="px-2 py-1 text-[10px] pill border border-purple-500/60 text-purple-200 hover:bg-purple-500/20"
              data-action="view-result"
              data-id="${t.id}"
              data-result-raw="${encodeURIComponent(t.result || "")}"
              data-title-raw="${encodeURIComponent(t.title || "")}"
            >View</button>
            ` : ""}
          </td>
        `;
        tbody.appendChild(row);
      }
    }

    const total = tasks.length;
    const open = tasks.filter(t => t.status !== "done").length;
    document.getElementById("tasksSummary").textContent =
      `${total} total · ${open} open`;

    const badge = document.getElementById("tasksApprovalBadge");
    const badgeCount = document.getElementById("tasksApprovalCount");
    if (needsApproval > 0) {
      badge.classList.remove("hidden");
      badgeCount.textContent = needsApproval;
    } else {
      badge.classList.add("hidden");
    }

    // wire action buttons
    tbody.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async (ev) => {
        const id = ev.currentTarget.getAttribute("data-id");
        const action = ev.currentTarget.getAttribute("data-action");
        if (!id || !action) return;

        if (action === "approve") {
          await fetch("/api/tasks/" + id + "/approve", { method: "POST" });
          await fetchTasks();
        } else if (action === "run") {
          await fetch("/api/tasks/" + id + "/run", { method: "POST" });
          await fetchTasks();
        } else if (action === "view-result") {
          const resultRaw = ev.currentTarget.getAttribute("data-result-raw");
          const titleRaw = ev.currentTarget.getAttribute("data-title-raw");
          if (resultRaw && titleRaw) {
            const result = decodeURIComponent(resultRaw);
            const title = decodeURIComponent(titleRaw);
            document.getElementById("modalTaskTitle").textContent = title;
            document.getElementById("modalTaskResult").textContent = result;
            document.getElementById("resultModal").classList.remove("hidden");
          }
        }
      });
    });

    // Update area chart
    const ctxArea = document.getElementById("tasksAreaChart").getContext("2d");
    const labels = Object.keys(byArea);
    const values = Object.values(byArea);

    if (tasksAreaChart) tasksAreaChart.destroy();
    tasksAreaChart = new Chart(ctxArea, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data: values,
        }],
      },
      options: {
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#e5e7eb", font: { size: 11 } },
          },
        },
      },
    });
  }

  async function fetchVstaff() {
    const res = await fetch("/api/vstaff");
    const data = await res.json();

    const employees = data.employees || [];
    const tbody = document.getElementById("vstaffTableBody");
    tbody.innerHTML = "";

    if (employees.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="px-2 py-3 text-center text-slate-500">No virtual staff data available yet.</td></tr>';
      document.getElementById("vstaffSummary").textContent = "0 employees";
      return;
    }

    for (const e of employees) {
      const row = document.createElement("tr");
      const taskNames = (e.tasks || []).map(t => typeof t === "string" ? t : (t.title || t.task_title || "")).filter(Boolean);
      row.innerHTML = `
        <td class="px-2 py-2">${e.name || e.role || e.id}</td>
        <td class="px-2 py-2 text-xs text-sky-300">${e.role || "—"}</td>
        <td class="px-2 py-2 text-xs">${e.remaining_slots ?? "—"}</td>
        <td class="px-2 py-2 text-xs">${taskNames.length ? taskNames.join(", ") : "—"}</td>
      `;
      tbody.appendChild(row);
    }

    document.getElementById("vstaffSummary").textContent = `${employees.length} employees`;
  }

  async function fetchAll(showBusy = true) {
    if (isRunning && showBusy) return;
    try {
      if (showBusy) isRunning = true;
      await Promise.all([
        fetchSnapshot("today", "Today"),
        fetchSnapshot("yesterday", "Yesterday"),
        fetchTasks(),
        fetchVstaff(),
      ]);
    } finally {
      if (showBusy) isRunning = false;
    }
  }

  // Controls
  document.getElementById("btnRefresh").addEventListener("click", () => {
    countdown = refreshInterval;
    fetchAll();
  });

  document.getElementById("btnPlan").addEventListener("click", async () => {
    await fetch("/api/ceo/plan", { method: "POST" });
    await fetchAll();
  });

  document.getElementById("btnRunPending").addEventListener("click", async () => {
    await fetch("/api/ceo/run_pending", { method: "POST" });
    await fetchAll();
  });

  // Modal handlers
  document.getElementById("modalClose").addEventListener("click", () => {
    document.getElementById("resultModal").classList.add("hidden");
  });
  
  document.getElementById("resultModal").addEventListener("click", (e) => {
    if (e.target.id === "resultModal") {
      document.getElementById("resultModal").classList.add("hidden");
    }
  });

  // Initial load
  fetchAll();
  setInterval(updateCountdown, 1000);
</script>
</body>
</html>
    """
    return HTMLResponse(html)


# -------------------------------------------------------------------
# CLI runner (optional)
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic CEO Dashboard server")
    parser.add_argument(
        "--company",
        type=str,
        default=os.getenv("AGENTIC_CEO_COMPANY", DEFAULT_COMPANY_KEY),
        help="Company key from company_config.yaml (default from AGENTIC_CEO_COMPANY or config)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("AGENTIC_CEO_CONFIG", DEFAULT_CONFIG_PATH),
        help="Path to company_config.yaml (default from AGENTIC_CEO_CONFIG or repo default)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind (default 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind (default 8080)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (dev only)",
    )
    args = parser.parse_args()

    # Set env so get_brain() uses these
    os.environ["AGENTIC_CEO_COMPANY"] = args.company
    os.environ["AGENTIC_CEO_CONFIG"] = args.config

    # Ensure brain is initialized once with these settings
    get_brain()

    import uvicorn

    uvicorn.run("dashboard:app", host=args.host, port=args.port, reload=args.reload)