"""
Agentic CEO – Real-Time Control Dashboard

FastAPI app that shows:
- Snapshot metrics parsed from CEO memory (today + previous day)
- Company context
- Open tasks table with approval actions
- Buttons to plan day & run pending tasks
- Virtual employees + which tasks are assigned to whom

Run (basic):
    uvicorn dashboard:app --reload --port 8080

Or with company:
    AGENTIC_CEO_COMPANY=next_ecosystem uvicorn dashboard:app --reload --port 8080
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from company_brain import create_default_brain

# -------------------------------------------------------------------
# Instantiate brain once per process
# -------------------------------------------------------------------

brain = create_default_brain()

app = FastAPI(title="Agentic CEO Dashboard")

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
    to extract useful numeric metrics for charts / cards.

    Defensive: will not crash if format changes and will keep defaults.
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
                # Keep default value if parsing fails
                pass

    return metrics


def build_task_payload() -> Dict[str, Any]:
    """
    Build JSON-safe tasks + simple aggregations for charts.
    Uses current CEO state tasks.
    """
    state = getattr(brain, "ceo", None)
    tasks: List[Dict[str, Any]] = []

    if state is None or not getattr(state, "state", None):
        return {"tasks": [], "by_area": {}, "by_status": {}}

    ceo_state = state.state
    ceo_tasks: List[Any] = getattr(ceo_state, "tasks", []) or []

    for t in ceo_tasks:
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
            }
        )

    by_area = Counter(task["area"] for task in tasks)
    by_status = Counter(task["status"] for task in tasks)

    return {
        "tasks": tasks,
        "by_area": dict(by_area),
        "by_status": dict(by_status),
    }


def get_snapshot_for_offset(day_offset: int = 0) -> str:
    """
    Get snapshot or memory summary for a given day offset relative to CEO state date.

    day_offset:
        0  -> today (uses CompanyBrain.snapshot(), includes metrics + open tasks)
       -1  -> previous day reflection from MemoryEngine
       -n  -> n days ago (if memory exists)
    """
    if day_offset == 0:
        return brain.snapshot()

    # Try to compute base date from CEO state
    ceo_state = getattr(brain.ceo, "state", None)
    base_date_str: Optional[str] = getattr(ceo_state, "date", None)

    if not base_date_str:
        # Fallback: just use snapshot; better than nothing
        return brain.snapshot()

    try:
        base = date.fromisoformat(base_date_str)
    except Exception:
        return brain.snapshot()

    target = base + timedelta(days=day_offset)
    # Use MemoryEngine directly for that date
    return brain.ceo.memory.summarize_day(target.isoformat())


# -------------------------------------------------------------------
# API endpoints – used by the frontend JS
# -------------------------------------------------------------------


@app.get("/api/snapshot")
def api_snapshot(day_offset: int = Query(0)) -> JSONResponse:
    """
    Get snapshot + metrics for today (day_offset=0) or previous days (e.g. -1).
    """
    snap_text = get_snapshot_for_offset(day_offset)
    metrics = parse_snapshot(snap_text)

    company = getattr(brain, "company_profile", None)
    if company is None:
        company_info = {}
    else:
        company_info = {
            "id": getattr(brain, "company_id", company.name),
            "name": company.name,
            "industry": company.industry,
            "vision": company.vision,
            "mission": company.mission,
            "north_star_metric": company.north_star_metric,
            "primary_markets": getattr(company, "primary_markets", []) or [],
            "products_or_services": getattr(company, "products_or_services", []) or [],
        }

    return JSONResponse(
        {
            "snapshot_text": snap_text,
            "metrics": metrics,
            "company": company_info,
            "day_offset": day_offset,
        }
    )


@app.get("/api/tasks")
def api_tasks() -> JSONResponse:
    payload = build_task_payload()
    return JSONResponse(payload)


@app.get("/api/tasks/requiring_approval")
def api_tasks_requiring_approval() -> JSONResponse:
    """
    Return tasks that have requires_approval=True and are not yet approved/done.
    """
    tasks = []
    for t in brain.get_tasks_requiring_approval():
        tasks.append(
            {
                "id": getattr(t, "id", ""),
                "title": getattr(t, "title", ""),
                "area": getattr(t, "area", "") or "unspecified",
                "priority": getattr(t, "priority", None),
                "owner": getattr(t, "suggested_owner", "") or "",
                "status": getattr(t, "status", "") or "unknown",
                "requires_approval": True,
                "approved": bool(getattr(t, "approved", False)),
            }
        )
    return JSONResponse({"tasks": tasks})


@app.post("/api/tasks/approve")
async def api_approve_task(request: Request) -> JSONResponse:
    """
    Approve a task so it can run in approval mode.
    Body: { "task_id": "..." }
    """
    data = await request.json()
    task_id = data.get("task_id")
    if not task_id:
        return JSONResponse({"ok": False, "error": "task_id is required"}, status_code=400)

    ok = brain.approve_task(task_id)
    return JSONResponse({"ok": ok, "task_id": task_id})


@app.post("/api/tasks/run")
def api_run_tasks() -> JSONResponse:
    """
    Run all pending tasks via CompanyBrain.run_pending_tasks().
    """
    results = brain.run_pending_tasks()
    return JSONResponse({"ok": True, "results": results})


@app.post("/api/plan")
def api_plan_day() -> JSONResponse:
    """
    Ask Agentic CEO to plan the day (generate tasks, stored in ceo.state.tasks).
    """
    text = brain.plan_day()
    # Also refresh task payload
    tasks_payload = build_task_payload()
    return JSONResponse({"ok": True, "plan_text": text, "tasks": tasks_payload})


@app.get("/api/state")
def api_state() -> JSONResponse:
    """
    Full structured state from CompanyBrain.get_dashboard_state():
        - company, snapshot, tasks, vstaff, kpis
    """
    state = brain.get_dashboard_state()
    return JSONResponse(state)


# -------------------------------------------------------------------
# HTML dashboard – Tailwind + Chart.js, auto-refresh every 10s
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
        class="pill px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-sm font-medium shadow-md shadow-emerald-500/30"
        onclick="planDay()"
      >
        Plan Day
      </button>

      <button
        class="pill px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 text-sm font-medium shadow-md shadow-sky-500/30"
        onclick="runPendingTasks()"
      >
        Run Pending Tasks
      </button>

      <button
        class="pill px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 text-sm font-medium border border-slate-600"
        onclick="fetchAll()"
      >
        Refresh Now
      </button>

      <span class="pill px-3 py-2 text-xs font-mono bg-slate-900/80 border border-slate-700 text-slate-300">
        Auto-refresh: <span id="refreshCountdown">10</span>s
      </span>
    </div>
  </header>

  <!-- Top Grid: Snapshot (today + previous) + Company -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
    <!-- Snapshot Today -->
    <div class="card p-4 md:p-6 space-y-3 lg:col-span-2">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold text-slate-100">Snapshot – Today</h2>
        <span id="snapshotDate" class="text-xs text-slate-400 font-mono">—</span>
      </div>

      <pre id="snapshotText" class="mt-2 text-xs md:text-sm text-slate-300 bg-slate-900/70 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
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

    <!-- Company & Previous Day -->
    <div class="space-y-4">
      <!-- Company -->
      <div class="card p-4 md:p-6 space-y-3">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-lg font-semibold text-slate-100">Company</h2>
          <span id="companyId" class="text-xs font-mono text-slate-400"></span>
        </div>

        <div class="space-y-2 text-sm">
          <div>
            <p class="text-slate-400 text-xs uppercase tracking-wide">Name</p>
            <p id="companyName" class="text-slate-100 font-medium">—</p>
          </div>
          <div>
            <p class="text-slate-400 text-xs uppercase tracking-wide">Industry</p>
            <p id="companyIndustry" class="text-slate-100">—</p>
          </div>
          <div>
            <p class="text-slate-400 text-xs uppercase tracking-wide">North Star Metric</p>
            <p id="companyNorthStar" class="text-emerald-300 font-medium">—</p>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <p class="text-slate-400 text-xs uppercase tracking-wide">Markets</p>
              <p id="companyMarkets" class="text-slate-100 text-xs">—</p>
            </div>
            <div>
              <p class="text-slate-400 text-xs uppercase tracking-wide">Products / Apps</p>
              <p id="companyProducts" class="text-slate-100 text-xs">—</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Previous Day Summary -->
      <div class="card p-3 md:p-4 space-y-2">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-100">Previous Day Summary</h2>
          <span id="prevSnapshotDate" class="text-[11px] text-slate-400 font-mono">—</span>
        </div>
        <pre id="prevSnapshotText" class="text-[11px] text-slate-300 bg-slate-900/70 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap max-h-40">
Loading…
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
      <h2 class="text-lg font-semibold text-slate-100">Tasks</h2>
      <span id="tasksSummary" class="text-xs text-slate-400">Loading…</span>
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

  <!-- Virtual Employees & Allocations -->
  <section class="card p-4 md:p-6 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-100">Virtual Employees & Allocated Tasks</h2>
      <span id="vstaffSummary" class="text-xs text-slate-400">Loading…</span>
    </div>

    <div id="vstaffContainer" class="space-y-3 text-xs md:text-sm">
      <p class="text-slate-500 text-xs">Loading virtual staff state…</p>
    </div>
  </section>
</div>

<script>
  let metricsChart = null;
  let tasksAreaChart = null;
  let refreshInterval = 10;
  let countdown = refreshInterval;

  function updateCountdown() {
    const el = document.getElementById("refreshCountdown");
    if (!el) return;
    countdown -= 1;
    if (countdown <= 0) {
      countdown = refreshInterval;
      fetchAll();
    }
    el.textContent = countdown;
  }

  async function fetchSnapshotToday() {
    const res = await fetch("/api/snapshot?day_offset=0");
    const data = await res.json();

    const snapText = data.snapshot_text || "";
    document.getElementById("snapshotText").textContent = snapText.trim() || "No snapshot yet.";

    const m = data.metrics || {};
    document.getElementById("snapshotDate").textContent = m.date || "";
    document.getElementById("metricDecisions").textContent = m.decisions_made ?? 0;
    document.getElementById("metricTools").textContent = m.tool_calls ?? 0;
    document.getElementById("metricLLM").textContent = m.llm_calls ?? 0;
    document.getElementById("metricTokens").textContent = m.tokens_used ?? 0;

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
    } else if (company.name) {
      sub.textContent = company.name;
    }

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
            ticks: {
              color: "#e5e7eb",
              font: { size: 11 },
            },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: "#9ca3af",
              font: { size: 10 },
            },
            grid: {
              color: "rgba(55,65,81,0.5)",
            },
          },
        },
        plugins: {
          legend: {
            labels: { color: "#e5e7eb" },
          },
        },
      },
    });
  }

  async function fetchSnapshotPreviousDay() {
    const res = await fetch("/api/snapshot?day_offset=-1");
    const data = await res.json();
    const snapText = data.snapshot_text || "";
    const m = data.metrics || {};

    document.getElementById("prevSnapshotText").textContent = snapText.trim() || "No previous day summary.";
    document.getElementById("prevSnapshotDate").textContent = m.date || "";
  }

  async function fetchTasks() {
    const res = await fetch("/api/tasks");
    const data = await res.json();

    const tasks = data.tasks || [];
    const byArea = data.by_area || {};
    const byStatus = data.by_status || {};

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

        const approveButton = (t.requires_approval && !t.approved)
          ? `<button class="pill px-2 py-1 bg-emerald-500/80 hover:bg-emerald-400 text-slate-950 text-[10px] font-semibold"
                     onclick="approveTask('${t.id}')">
               Approve
             </button>`
          : `<span class="text-[10px] text-slate-500">—</span>`;

        row.innerHTML = `
          <td class="px-2 py-2 text-[10px] font-mono text-slate-500">${t.id ? t.id.slice(0,8) + "…" : ""}</td>
          <td class="px-2 py-2">${t.title}</td>
          <td class="px-2 py-2 text-xs text-sky-300">${t.area}</td>
          <td class="px-2 py-2 text-xs">${t.priority ?? ""}</td>
          <td class="px-2 py-2 text-xs text-amber-200">${t.owner}</td>
          <td class="px-2 py-2 text-xs">
            <span class="pill px-2 py-1 text-[10px] ${statusClass}">${t.status}</span>
          </td>
          <td class="px-2 py-2 text-xs">${t.requires_approval ? "Yes" : "No"}</td>
          <td class="px-2 py-2 text-xs">${t.approved ? "Yes" : "No"}</td>
          <td class="px-2 py-2 text-xs">${approveButton}</td>
        `;
        tbody.appendChild(row);
      }
    }

    const total = tasks.length;
    const open = tasks.filter(t => t.status !== "done").length;
    document.getElementById("tasksSummary").textContent =
      `${total} total · ${open} open`;

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

  async function fetchVStaff() {
    const res = await fetch("/api/state");
    const data = await res.json();
    const vstaff = data.vstaff || null;

    const container = document.getElementById("vstaffContainer");
    const summary = document.getElementById("vstaffSummary");

    if (!vstaff) {
      container.innerHTML = '<p class="text-slate-500 text-xs">No virtual staff data available yet.</p>';
      summary.textContent = "0 employees";
      return;
    }

    // Try to interpret common structure: { employees: [...] }
    const employees = Array.isArray(vstaff.employees) ? vstaff.employees : vstaff.employees || vstaff.emps || null;

    if (employees && Array.isArray(employees)) {
      summary.textContent = `${employees.length} employees`;
      container.innerHTML = "";
      for (const emp of employees) {
        const tasks = emp.tasks || emp.assigned_tasks || [];
        const role = emp.role || emp.title || "—";
        const cap = emp.capacity || emp.remaining_task_slots || emp.capacity_summary || null;

        const capText = (cap && typeof cap === "object")
          ? (cap.remaining_task_slots !== undefined
               ? `${cap.remaining_task_slots} slots`
               : JSON.stringify(cap))
          : (typeof cap === "number" ? `${cap} slots` : "—");

        const card = document.createElement("div");
        card.className = "border border-slate-700/70 rounded-lg p-3 bg-slate-900/60 space-y-2";

        let tasksHtml = "";
        if (tasks && tasks.length > 0) {
          tasksHtml = '<ul class="space-y-1 text-[11px]">';
          for (const t of tasks) {
            const tt = t.title || t.task_title || "Task";
            const ts = t.status || "unknown";
            tasksHtml += `<li class="flex items-center justify-between gap-2">
                <span class="truncate">${tt}</span>
                <span class="pill px-2 py-0.5 bg-slate-800 text-[10px]">${ts}</span>
              </li>`;
          }
          tasksHtml += "</ul>";
        } else {
          tasksHtml = '<p class="text-[11px] text-slate-500">No tasks assigned.</p>';
        }

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-slate-400 uppercase tracking-wide">Role</p>
              <p class="text-sm text-slate-100 font-medium">${role}</p>
            </div>
            <div class="text-right">
              <p class="text-xs text-slate-400 uppercase tracking-wide">Employee ID</p>
              <p class="text-[11px] font-mono text-slate-300">${emp.id || "—"}</p>
              <p class="text-[11px] text-slate-400 mt-1">Capacity: ${capText}</p>
            </div>
          </div>
          <div class="mt-2">
            <p class="text-[11px] text-slate-400 mb-1">Allocated Tasks</p>
            ${tasksHtml}
          </div>
        `;
        container.appendChild(card);
      }
    } else {
      // Fallback: show raw JSON
      summary.textContent = "Custom vstaff structure";
      container.innerHTML = `
        <p class="text-[11px] text-slate-400 mb-1">Raw vstaff payload:</p>
        <pre class="text-[11px] bg-slate-900/70 rounded-lg p-2 overflow-x-auto">${JSON.stringify(vstaff, null, 2)}</pre>
      `;
    }
  }

  async function planDay() {
    try {
      const res = await fetch("/api/plan", { method: "POST" });
      const data = await res.json();
      if (!data.ok) {
        alert("Plan day failed.");
        return;
      }
      alert("Day planned. New tasks generated.");
      await fetchTasks();
      await fetchSnapshotToday();
    } catch (e) {
      console.error(e);
      alert("Error planning day.");
    }
  }

  async function runPendingTasks() {
    try {
      const res = await fetch("/api/tasks/run", { method: "POST" });
      const data = await res.json();
      if (!data.ok) {
        alert("Run tasks failed.");
        return;
      }
      const count = (data.results || []).length;
      alert("Run complete: " + count + " tasks processed.");
      await fetchTasks();
      await fetchSnapshotToday();
      await fetchVStaff();
    } catch (e) {
      console.error(e);
      alert("Error running tasks.");
    }
  }

  async function approveTask(taskId) {
    if (!taskId) return;
    const confirmApprove = confirm("Approve task " + taskId.slice(0,8) + "… ?");
    if (!confirmApprove) return;

    try {
      const res = await fetch("/api/tasks/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId }),
      });
      const data = await res.json();
      if (!data.ok) {
        alert("Failed to approve task.");
        return;
      }
      alert("Task approved.");
      await fetchTasks();
      await fetchSnapshotToday();
    } catch (e) {
      console.error(e);
      alert("Error approving task.");
    }
  }

  async function fetchAll() {
    await Promise.all([
      fetchSnapshotToday(),
      fetchSnapshotPreviousDay(),
      fetchTasks(),
      fetchVStaff(),
    ]);
  }

  // Initial load
  fetchAll();
  setInterval(updateCountdown, 1000);
</script>
</body>
</html>
    """
    return HTMLResponse(html)