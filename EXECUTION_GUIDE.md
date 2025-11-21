# Agentic CEO - Execution Guide

This system can be executed in 5 different ways depending on your needs (interactive, automated, visual, API-driven, or chat-integrated).

## 1. Interactive CLI (Command Line Interface)
Best for: Manual control, testing, and exploring the system.

**Command:**
```bash
python ceo_cli.py --company guardianfm
```

**Options:**
- `--company`: Company key (e.g. `guardianfm`, `next_ecosystem`)
- `--mode`: `auto` | `approval` | `dry_run`

**Interactive Commands:**
- `plan`: Generate a daily plan
- `tasks`: Show the task tree
- `run`: Execute all pending tasks (uses Virtual Employees & C-suite agents)
- `snapshot`: View current state summary
- `brief`: Get a personal briefing for the human CEO

---

## 2. Autonomous Runner
Best for: Scheduled jobs (cron), daily automation, and reporting.

**Command:**
```bash
python ceo_auto.py --company guardianfm
```

**With Notifications:**
```bash
python ceo_auto.py --company guardianfm --notify --notify-channels slack,email
```

**What it does:**
1. Generates a daily plan
2. Executes high-priority tasks
3. Generates a snapshot & briefing
4. (Optional) Sends reports via Slack/Email

---

## 3. Real-Time Dashboard
Best for: Visual monitoring of KPIs, tasks, and system load.

**Command:**
```bash
python dashboard.py --company guardianfm --port 8080
```

**Access:** Open `http://localhost:8080` in your browser.
**Features:**
- Live task tracking (status, owner, approval)
- System load metrics
- Company context display

---

## 4. REST API Server
Best for: Integrating with other apps, frontends, or n8n workflows.

**Command:**
```bash
uvicorn main:app --reload --port 8000
```

**Endpoints:**
- `POST /plan_day`
- `POST /ingest_event`
- `POST /run_pending_tasks`
- `GET /state`

---

## 5. Slack Events Server
Best for: Chat-based interaction and team collaboration.

**Command:**
```bash
python slack_events_server.py
```

**Features:**
- Listens for messages in connected channels
- Direct agent commands: `cro: increase sales`, `cto: fix bug`
- General messages are ingested as events by the CEO

---

## Environment Setup
Ensure your `.env` file is configured with necessary keys:
- `OPENAI_API_KEY`
- `AGENTIC_CEO_COMPANY` (default company)
- `SLACK_BOT_TOKEN` (for Slack mode)

