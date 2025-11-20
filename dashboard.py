from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from company_brain import CompanyBrain, DEFAULT_CONFIG_PATH, DEFAULT_COMPANY_KEY

# --------------------------------------------------------------------
# Boot the brain once for the dashboard process
# --------------------------------------------------------------------

EXECUTION_MODE = os.getenv("AGENTIC_CEO_EXECUTION_MODE", "auto")

brain = CompanyBrain.from_config(
    config_path=DEFAULT_CONFIG_PATH,
    company_key=DEFAULT_COMPANY_KEY,
    execution_mode=EXECUTION_MODE,
)

app = FastAPI(title="Agentic CEO – Real-Time Dashboard")


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def render_html_dashboard(state: Dict[str, Any]) -> str:
    company = state["company"]
    tasks = state["tasks"]
    snapshot = state["snapshot"]

    def esc(s: Any) -> str:
        return (str(s) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows_html = []
    for t in tasks:
        rows_html.append(
            f"""
            <tr>
              <td>{esc(t.get("id") or "")}</td>
              <td>{esc(t.get("title") or "")}</td>
              <td>{esc(t.get("area") or "")}</td>
              <td>{esc(t.get("priority") or "")}</td>
              <td>{esc(t.get("suggested_owner") or "")}</td>
              <td>{esc(t.get("status") or "")}</td>
              <td>{'✔️' if t.get('requires_approval') else ''}</td>
              <td>{'✔️' if t.get('approved') else ''}</td>
            </tr>
            """
        )

    tasks_table = "\n".join(rows_html) or "<tr><td colspan='8'>No tasks yet.</td></tr>"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Agentic CEO Dashboard – {esc(company.get('name'))}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <!-- Auto-refresh every 10 seconds for 'real-time' feel -->
  <meta http-equiv="refresh" content="10" />
  <style>
    body {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #070b12;
      color: #f3f4f6;
      margin: 0;
      padding: 0;
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px 0;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .card {{
      background: radial-gradient(circle at top left, #111827, #020617);
      border-radius: 18px;
      padding: 16px 18px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.8);
    }}
    .card small {{
      color: #9ca3af;
      font-size: 12px;
    }}
    .muted {{
      color: #9ca3af;
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.5;
      background: #020617;
      border-radius: 12px;
      padding: 12px;
      border: 1px solid rgba(31, 41, 55, 0.9);
      max-height: 320px;
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid rgba(31, 41, 55, 0.8);
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #9ca3af;
      background: #020617;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    tr:nth-child(even) td {{
      background: rgba(15, 23, 42, 0.6);
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      border: 1px solid rgba(148, 163, 184, 0.5);
      color: #e5e7eb;
      gap: 6px;
      background: rgba(15, 23, 42, 0.7);
    }}
    .pill-dot {{
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: #22c55e;
      box-shadow: 0 0 8px rgba(34, 197, 94, 0.8);
    }}
    .btn-row {{
      display: flex;
      gap: 10px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 14px;
      border-radius: 999px;
      border: 1px solid rgba(56, 189, 248, 0.6);
      background: linear-gradient(135deg, #0f172a, #020617);
      color: #e0f2fe;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
    }}
    .btn span.icon {{
      font-size: 14px;
    }}
    .pill-warning .pill-dot {{
      background: #f97316;
      box-shadow: 0 0 8px rgba(249, 115, 22, 0.8);
    }}
  </style>
</head>
<body>
  <div class="page">
    <div style="display:flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap;">
      <div>
        <h1>Agentic CEO – {esc(company.get("name"))}</h1>
        <div class="muted">
          {esc(company.get("industry") or "Industry N/A")} · North Star: {esc(company.get("north_star_metric") or "N/A")}
        </div>
      </div>
      <div class="pill">
        <span class="pill-dot"></span>
        <span>Execution Mode: {esc(EXECUTION_MODE.upper())}</span>
      </div>
    </div>

    <div class="btn-row">
      <a href="/plan-and-run" class="btn">
        <span class="icon">⚡️</span>
        <span>Plan + Run Pending Tasks Now</span>
      </a>
      <a href="/api/state" class="btn">
        <span class="icon">🧠</span>
        <span>Raw JSON State</span>
      </a>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Snapshot</h2>
        <small>Summarized from CEO memory for today</small>
        <pre>{esc(snapshot)}</pre>
      </div>
      <div class="card">
        <h2>Company</h2>
        <small>Context</small>
        <p class="muted">
          ID: <strong>{esc(company.get("id"))}</strong><br />
          Markets: {esc(", ".join(company.get("primary_markets") or []) or "N/A")}
        </p>
        <p class="muted">
          This dashboard auto-refreshes every 10s and reads directly from the Agentic CEO brain running in this process.
        </p>
      </div>
    </div>

    <div class="card" style="margin-top: 10px;">
      <h2>Open Tasks</h2>
      <small>From CEO state (including delegated + virtual staff)</small>
      <div style="max-height: 420px; overflow: auto; margin-top: 8px;">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Area</th>
              <th>Priority</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Needs Approval</th>
              <th>Approved</th>
            </tr>
          </thead>
          <tbody>
            {tasks_table}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>
"""
    return html


# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(_: Request) -> HTMLResponse:
    state = brain.get_dashboard_state()
    html = render_html_dashboard(state)
    return HTMLResponse(content=html)


@app.get("/api/state", response_class=JSONResponse)
def api_state() -> JSONResponse:
    state = brain.get_dashboard_state()
    return JSONResponse(content=state)


@app.get("/plan-and-run")
def plan_and_run() -> RedirectResponse:
    """
    Trigger a fresh daily plan and run all pending tasks,
    then bounce back to the dashboard.
    """
    try:
        brain.plan_day()
        brain.run_pending_tasks()
    except Exception as e:
        # In a real system you'd log this; for now we just ignore for UI.
        print(f"[dashboard] Error in plan_and_run: {e!r}")
    return RedirectResponse(url="/", status_code=303)


# --------------------------------------------------------------------
# Local dev entrypoint
# --------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dashboard:app", host="0.0.0.0", port=8000, reload=True)