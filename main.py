from typing import Dict, Any, List

from fastapi import FastAPI
from pydantic import BaseModel

from env_loader import load_env

from agentic_ceo import (
    AgenticCEO,
    CompanyProfile,
    CEOEvent,
    LogTool,
)
from llm_openai import OpenAILLM

load_env()


app = FastAPI(title="Agentic CEO API")

# --- Init global CEO instance ---

company = CompanyProfile(
    name="GuardianFM Ltd",
    industry="Security & Facilities Management",
    vision="Be the most trusted, AI-first security partner in the UK.",
    mission="Protect people and property with smart, proactive security teams.",
    north_star_metric="Monthly Recurring Revenue (MRR)",
    primary_markets=["United Kingdom"],
    products_or_services=[
        "Manned guarding",
        "Mobile patrols",
        "Key holding",
        "Facilities management",
    ],
    team_size=150,
    website="https://guardianfm.com",
)

llm = OpenAILLM()
ceo = AgenticCEO(company=company, llm=llm)

log_sink: List[str] = []
ceo.register_tool(LogTool(sink=log_sink))


# --- Request models ---


class EventIn(BaseModel):
    type: str
    payload: Dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "company": ceo.company.name}


@app.post("/plan_day")
def plan_day():
    plan = ceo.plan_day()
    return {"plan": plan, "date": str(ceo.state.date)}


@app.post("/ingest_event")
def ingest_event(event: EventIn):
    ceo_event = CEOEvent(type=event.type, payload=event.payload)
    decision = ceo.ingest_event(ceo_event)
    return {
        "decision": decision,
        "tasks_created": [t.title for t in ceo.state.tasks],
    }


@app.post("/run_pending_tasks")
async def run_pending_tasks():
    results = []
    tasks_to_run = [t for t in ceo.state.tasks if t.status != "done"]
    
    if not tasks_to_run:
        return {"results": []}

    # Use asyncio.gather to run tasks concurrently
    # Note: This is a simplified direct call to ceo.run_task, bypassing CompanyBrain routing
    # Ideally, main.py should use CompanyBrain, but it uses AgenticCEO directly.
    # We'll stick to direct parallel execution here.
    
    async def run_single(t):
        res = await ceo.run_task(t)
        return {"task": t.title, "result": res}

    results = await asyncio.gather(*[run_single(t) for t in tasks_to_run])
    return {"results": results}


@app.get("/state")
def get_state():
    return {
        "date": str(ceo.state.date),
        "focus_theme": ceo.state.focus_theme,
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_date": str(t.due_date),
            }
            for t in ceo.state.tasks
        ],
    }


@app.get("/logs")
def get_logs():
    return {"log_tool_output": log_sink}

