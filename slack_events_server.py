# slack_events_server.py
from __future__ import annotations

import os
import hmac
import hashlib
import time
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slack_sdk.web import WebClient

from company_brain import create_default_brain

# ----------------------------------------------------
# Load environment variables
# ----------------------------------------------------
load_dotenv()

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

if not SLACK_SIGNING_SECRET:
    raise EnvironmentError("SLACK_SIGNING_SECRET missing in .env")
if not SLACK_BOT_TOKEN:
    raise EnvironmentError("SLACK_BOT_TOKEN missing in .env")

# Slack client for posting replies
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# Shared CompanyBrain instance (Next Ecosystem selected via config/env)
brain = create_default_brain()

app = FastAPI(title="AgenticCEO Slack Events Server")


# ----------------------------------------------------
# Helper: verify Slack signature
# ----------------------------------------------------
def verify_slack_request(request: Request, body: bytes) -> None:
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    slack_signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not slack_signature:
        raise HTTPException(status_code=400, detail="Missing Slack headers")

    # Protect against replay attacks (5 minute window)
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_signature = (
        "v0="
        + hmac.new(
            SLACK_SIGNING_SECRET.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(my_signature, slack_signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")


# ----------------------------------------------------
# Helper: send message back to Slack
# ----------------------------------------------------
def send_slack_message(channel: str, text: str) -> Dict[str, Any]:
    try:
        resp = slack_client.chat_postMessage(channel=channel, text=text)
        return {"ok": resp["ok"], "ts": resp.get("ts"), "channel": channel}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------
# Helper: dynamic company context (Next Ecosystem, GuardianFM, etc.)
# ----------------------------------------------------
def build_company_context() -> str:
    """
    Build a generic context string from whatever company
    is configured inside CompanyBrain / AgenticCEO.
    This makes the system reusable for ANY company.
    """
    company = brain.ceo.company
    markets = ", ".join(company.primary_markets) if company.primary_markets else "N/A"
    products = (
        ", ".join(company.products_or_services)
        if company.products_or_services
        else "N/A"
    )

    return (
        f"You are advising for {company.name}, operating in the {company.industry} industry. "
        f"The company's vision is: {company.vision}. "
        f"The mission is: {company.mission}. "
        f"The north-star metric is: {company.north_star_metric}. "
        f"Primary markets: {markets}. "
        f"Key products/services: {products}."
    )


# ----------------------------------------------------
# Routes
# ----------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "service": "AgenticCEO Slack Events Server"}


@app.post("/slack/events")
async def slack_events(request: Request):
    raw_body = await request.body()
    verify_slack_request(request, raw_body)

    data = await request.json()

    # URL verification challenge from Slack
    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data.get("challenge")})

    if data.get("type") != "event_callback":
        return JSONResponse(content={"ok": True})

    event = data.get("event", {})
    event_type = event.get("type")

    # Ignore bot messages (including our own)
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return JSONResponse(content={"ok": True})

    # Only handle message events
    if event_type != "message":
        return JSONResponse(content={"ok": True})

    text: str = event.get("text", "") or ""
    channel: str = event.get("channel", "")
    user: str = event.get("user", "")

    lower = text.strip().lower()
    company_context = build_company_context()

    # ------------------------------------------------
    # Pattern A: CRO/COO/CTO direct commands
    # CRO: ..., COO: ..., CTO: ...
    # ------------------------------------------------
    if lower.startswith("cro:"):
        instruction = text.split(":", 1)[1].strip()
        plan = brain.delegate_to_cro(instruction, company_context)
        reply = f"🧠 *CRO Agent Response:*\n{plan}"
        send_slack_message(channel, reply)
        return JSONResponse(content={"ok": True})

    if lower.startswith("coo:"):
        instruction = text.split(":", 1)[1].strip()
        plan = brain.delegate_to_coo(instruction, company_context)
        reply = f"🧠 *COO Agent Response:*\n{plan}"
        send_slack_message(channel, reply)
        return JSONResponse(content={"ok": True})

    if lower.startswith("cto:"):
        instruction = text.split(":", 1)[1].strip()
        plan = brain.delegate_to_cto(instruction, company_context)
        reply = f"🧠 *CTO Agent Response:*\n{plan}"
        send_slack_message(channel, reply)
        return JSONResponse(content={"ok": True})

    # ------------------------------------------------
    # Pattern B: General team message → CEO event
    # ------------------------------------------------
    payload = {
        "channel": channel,
        "user": user,
        "text": text,
        "source": "slack",
    }

    # Let the Agentic CEO process this as an event
    decision = brain.ingest_event("slack_message", payload)
    results = brain.run_pending_tasks()

    # Build a human-readable reply
    lines = ["🧠 *Agentic CEO has processed your message.*"]

    if decision:
        lines.append("*Decision & Tasks:*")
        lines.append(f"```{decision}```")

    if results:
        lines.append("*Actions taken:*")
        for r in results:
            status = r["result"].get("status")
            tool = r["result"].get("tool")
            if tool:
                lines.append(f"- {r['task']} (status: {status}, via {tool})")
            else:
                lines.append(f"- {r['task']} (status: {status})")

    reply_text = "\n".join(lines)
    send_slack_message(channel, reply_text)

    return JSONResponse(content={"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("slack_events_server:app", host="0.0.0.0", port=8000, reload=True)