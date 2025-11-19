"""
agentic_ceo.py

Core Agentic CEO engine with:
- Master schema for Agentic CEO
- Tool interface + example LogTool
- LLM interface (pluggable)
- AgenticCEO class (plan → decide → act loop)
- Persistent MemoryEngine integration (ceo_memory.json)
"""

from __future__ import annotations

import uuid
import datetime as dt
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from memory_engine import MemoryEngine


# ============================================================
# 1. SCHEMAS (Master Agentic CEO schema)
# ============================================================

class Metric(BaseModel):
    name: str
    target_value: float
    current_value: float = 0.0
    unit: str = ""  # e.g. "USD", "users", "%"


class CompanyProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    industry: str
    vision: str
    mission: str
    north_star_metric: str
    primary_markets: List[str] = []
    products_or_services: List[str] = []
    team_size: int = 0
    website: Optional[str] = None


class CEOObjective(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    priority: int = Field(ge=1, le=5, default=3)  # 1 = highest
    timeframe: str = "Q1"  # e.g. "Q1", "90 days", "2025"
    status: str = "active"  # active | completed | on-hold
    metrics: List[Metric] = []


class CEOTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    objective_id: Optional[str] = None
    owner: str = "CEO-Agent"
    due_date: Optional[dt.date] = None
    status: str = "todo"  # todo | in-progress | done | blocked
    suggested_tool: Optional[str] = None
    tool_input: Dict[str, Any] = {}
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class CEOEvent(BaseModel):
    """Any external input the Agentic CEO reacts to (emails, metrics, meetings, Slack, KPI alerts)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # e.g. "daily_check_in", "kpi_alert", "slack_message"
    payload: Dict[str, Any] = {}
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class CEOState(BaseModel):
    date: dt.date = Field(default_factory=lambda: dt.datetime.utcnow().date())
    focus_theme: str = "Default focus"
    objectives: List[CEOObjective] = []
    tasks: List[CEOTask] = []
    notes: List[str] = []


# ============================================================
# 2. TOOL INTERFACE + EXAMPLE TOOL
# ============================================================

class Tool(Protocol):
    """Minimal protocol any tool must implement."""
    name: str
    description: str

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


class LogTool:
    """
    Example tool: just logs a message and returns it.
    In real systems this could be:
    - Slack notifier
    - Notion page writer
    - CRM updater
    - Email sender
    """

    name: str = "log_tool"
    description: str = "Log a message from the Agentic CEO for later review."

    def __init__(self, sink: Optional[List[str]] = None) -> None:
        self._sink = sink if sink is not None else []

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message", "")
        timestamp = dt.datetime.utcnow().isoformat()
        entry = f"[{timestamp}] {message}"
        self._sink.append(entry)
        return {"ok": True, "logged": entry}


# ============================================================
# 3. LLM INTERFACE (PLUGGABLE)
# ============================================================

class LLMClient(Protocol):
    """You can back this with OpenAI, Groq, local model, etc."""
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
    def get_last_usage(self) -> Dict[str, int]: ...


# ============================================================
# 4. AGENTIC CEO CORE (with persistent MemoryEngine)
# ============================================================

class AgenticCEO:
    """
    Core Agentic CEO engine.

    Responsibilities:
    - Keep track of company profile & CEO state
    - Plan the day (high-level priorities)
    - Turn events into tasks
    - Decide which tool to call for a given task
    - Log decisions, KPIs, token usage, reflections into a persistent MemoryEngine
    """

    def __init__(
        self,
        company: CompanyProfile,
        llm: LLMClient,
        tools: Optional[Dict[str, Tool]] = None,
        memory_engine: Optional[MemoryEngine] = None,
    ) -> None:
        self.company = company
        self.llm = llm
        self.tools: Dict[str, Tool] = tools or {}
        self.memory = memory_engine or MemoryEngine()
        self.state = CEOState(
            focus_theme=f"Grow {company.name} using the north star: {company.north_star_metric}"
        )

    # ------------------------
    # PUBLIC API
    # ------------------------

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def plan_day(self) -> str:
        """
        Ask the LLM for a daily plan based on company profile + current state.
        Also parse the TASKS section into CEOTask objects.
        """
        system_prompt = (
            "You are an Agentic CEO for a company. "
            "You think in clear, actionable steps, and you always align tasks "
            "with the company's north-star metric."
        )
        user_prompt = (
            f"Company: {self.company.name}\n"
            f"Industry: {self.company.industry}\n"
            f"Vision: {self.company.vision}\n"
            f"Mission: {self.company.mission}\n"
            f"North Star Metric: {self.company.north_star_metric}\n"
            f"Primary Markets: {', '.join(self.company.primary_markets)}\n"
            f"Products/Services: {', '.join(self.company.products_or_services)}\n\n"
            f"Today's date: {self.state.date}\n"
            f"Current focus: {self.state.focus_theme}\n\n"
            "Create a short daily operating plan and 3–5 concrete tasks.\n"
            "Format:\n"
            "PLAN:\n"
            "- ...\n\n"
            "TASKS:\n"
            "1. ...\n"
            "2. ...\n"
            "3. ...\n"
        )

        plan_text = self.llm.complete(system_prompt, user_prompt)

        # Token logging (if llm supports it)
        if hasattr(self.llm, "get_last_usage"):
            usage = self.llm.get_last_usage()
            self.memory.record_token_usage("daily_plan", usage)

        # Log decision
        self.memory.record_decision(
            text=f"Daily plan generated for {self.state.date}:\n{plan_text}",
            context={"type": "daily_plan"},
        )

        # Parse tasks from the plan as well
        fake_event = CEOEvent(type="daily_plan", payload={"source": "plan_day"})
        new_tasks = self._parse_tasks(plan_text, fake_event)
        self.state.tasks.extend(new_tasks)

        return plan_text

    def ingest_event(self, event: CEOEvent) -> str:
        """
        Turn an incoming event into one or more tasks & a CEO decision summary.
        """
        system_prompt = (
            "You are an Agentic CEO. An event has occurred. "
            "Decide what to do in 1–3 tasks that align with the company's north star."
        )
        user_prompt = (
            f"Company: {self.company.name}\n"
            f"North Star Metric: {self.company.north_star_metric}\n\n"
            f"Event type: {event.type}\n"
            f"Event payload: {event.payload}\n\n"
            "Respond with:\n"
            "DECISION:\n"
            "- short explanation\n\n"
            "TASKS:\n"
            "1. task title – short description\n"
            "2. ...\n"
        )

        response = self.llm.complete(system_prompt, user_prompt)

        # Token logging
        if hasattr(self.llm, "get_last_usage"):
            usage = self.llm.get_last_usage()
            self.memory.record_token_usage("event_decision", usage)

        # Log event + decision into long-term memory
        self.memory.record_event(event_type=event.type, payload=event.payload)
        self.memory.record_decision(
            text=f"Handled event {event.type}:\n{response}",
            context={"type": "event_decision", "event_type": event.type},
        )

        # Create tasks from numbered lines under 'TASKS:'
        new_tasks = self._parse_tasks(response, event)
        self.state.tasks.extend(new_tasks)

        return response

    def run_task(self, task: CEOTask) -> Dict[str, Any]:
        """
        Execute a task by invoking a tool (if suggested), otherwise just log it.
        Returns the tool result or a simple status dict.
        """
        task.updated_at = dt.datetime.utcnow()

        if task.suggested_tool and task.suggested_tool in self.tools:
            tool = self.tools[task.suggested_tool]
            payload = task.tool_input or {"message": task.description or task.title}
            result = tool.run(payload)

            self.memory.record_tool_call(
                tool_name=tool.name,
                payload=payload,
                result=result,
            )

            task.status = "done"
            return {"status": "done", "tool": tool.name, "result": result}

        # No tool, just mark as done and log
        self.memory.record_decision(
            text=f"Task completed manually: {task.title}",
            context={"type": "manual_task"},
        )
        task.status = "done"
        return {"status": "done", "tool": None, "result": {}}

    def reflect(self) -> str:
        """
        Reflection over what happened today, using MemoryEngine summary.
        """
        reflection_text = self.memory.summarize_day(self.state.date)
        reflection_text += (
            f"- Tasks currently tracked in CEO state: {len(self.state.tasks)}"
        )
        self.memory.record_reflection(reflection_text)
        return reflection_text

    # ------------------------
    # INTERNAL UTILITIES
    # ------------------------

    def _parse_tasks(
        self,
        text: str,
        event: CEOEvent,
    ) -> List[CEOTask]:
        """
        Parse numbered tasks from LLM response.

        Expected formats under a 'TASKS:' heading:
          1. Title – description
          2. Another task - something
        """
        lines = text.splitlines()
        in_tasks = False
        tasks: List[CEOTask] = []

        for line in lines:
            stripped = line.strip()

            # Start capturing once we hit 'TASKS:'
            if stripped.upper().startswith("TASKS"):
                in_tasks = True
                continue

            if not in_tasks or not stripped:
                continue

            # Detect lines like "1. Do something..."
            if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
                # Remove "1." prefix
                content = stripped[2:].strip()

                # Split on "–" (en dash) first, then "-" as fallback
                parts = content.split("–", 1)
                if len(parts) == 1:
                    parts = content.split("-", 1)

                title = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else title
                lower_title = title.lower()

                # Default routing: log_tool
                suggested_tool = "log_tool"
                message_text = desc

                # Route certain titles to Slack if tools exist
                if "message the team" in lower_title or "notify the team" in lower_title:
                    suggested_tool = "slack_tool"
                    tool_input = {"message": f"[Agentic CEO] {message_text}"}
                else:
                    tool_input = {
                        "message": f"[From event {event.type}] {message_text}"
                    }

                tasks.append(
                    CEOTask(
                        title=title,
                        description=desc,
                        owner="Agentic CEO",
                        due_date=self.state.date,
                        suggested_tool=suggested_tool,
                        tool_input=tool_input,
                    )
                )

        return tasks