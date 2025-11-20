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
    """
    Rich task model so the CEO can actually delegate and reason about work.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    objective_id: Optional[str] = None

    # NEW FIELDS
    priority: int = Field(ge=1, le=5, default=3)  # 1 = highest leverage
    area: str = "general"                         # growth | ops | product | finance | ...
    suggested_owner: str = "CEO-Agent"           # CEO-Agent | CRO | COO | CTO | Marketing Lead | ...

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

        IMPORTANT: Tasks must follow the bracketed meta format so they can be routed:
          1. [growth, Virtual Growth Marketer, P1] Title – description
        """
        system_prompt = (
            "You are an Agentic CEO for a company. "
            "You think in clear, actionable steps, and you always align tasks "
            "with the company's north-star metric.\n\n"
            "When you output tasks, you MUST use this exact format so they can be parsed:\n"
            "TASKS:\n"
            "1. [area, OWNER, P1] Title – description\n"
            "2. [area, OWNER, P2] Title – description\n"
            "Where:\n"
            "- area = growth | marketing | sales | ops | product | finance | cx | data | tech, etc.\n"
            "- OWNER can be a human role (Head of Sales, COO) or a virtual role "
            "like 'Virtual Growth Marketer', 'Virtual SDR', 'Virtual Customer Success Manager'.\n"
            "- P1..P5 = priority (P1 highest).\n"
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
            "1. [area, OWNER, P1] Title – description\n"
            "2. [area, OWNER, P2] Title – description\n"
            "3. [area, OWNER, P3] Title – description\n"
        )

        plan_text = self.llm.complete(system_prompt, user_prompt)

        # Token logging (if llm supports it)
        try:
            usage = self.llm.get_last_usage()
            self.memory.record_token_usage("daily_plan", usage)
        except Exception:
            pass

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
            "Decide what to do in 1–3 tasks that align with the company's north star.\n\n"
            "When you output tasks, you MUST use this exact format so they can be parsed:\n"
            "TASKS:\n"
            "1. [area, OWNER, P1] Title – description\n"
            "2. [area, OWNER, P2] Title – description\n"
            "3. [area, OWNER, P3] Title – description\n"
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
            "1. [area, OWNER, P1] task title – short description\n"
            "2. [area, OWNER, P2] task title – short description\n"
            "3. [area, OWNER, P3] task title – short description\n"
        )

        response = self.llm.complete(system_prompt, user_prompt)

        # Token logging
        try:
            usage = self.llm.get_last_usage()
            self.memory.record_token_usage("event_decision", usage)
        except Exception:
            pass

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

          1. [area, OWNER, P1] Do something important – description
          2. [growth, Virtual SDR, P1] Run campaign – description

        Also handles cases where the metadata is at the END of the line:
          1. Do something important – description [area, OWNER, P1]

        - Optional metadata in [...] gives area, suggested_owner, priority.
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

                # ---------- Optional [area, OWNER, P1] metadata ----------
                area = "general"
                suggested_owner = "CEO-Agent"
                priority = 3

                # Case 1: metadata at the start: "[area, OWNER, P1] Title – desc"
                if content.startswith("["):
                    closing = content.find("]")
                    if closing != -1:
                        meta_block = content[1:closing]
                        content = content[closing + 1 :].strip()
                        meta_parts = [p.strip() for p in meta_block.split(",")]

                        if len(meta_parts) >= 1 and meta_parts[0]:
                            area = meta_parts[0].lower()

                        if len(meta_parts) >= 2 and meta_parts[1]:
                            suggested_owner = meta_parts[1]

                        if len(meta_parts) >= 3 and meta_parts[2]:
                            pr = meta_parts[2].upper()
                            if pr.startswith("P"):
                                try:
                                    priority = int(pr[1:])
                                except ValueError:
                                    priority = 3
                else:
                    # Case 2: metadata at the END: "Title – desc [area, OWNER, P1]"
                    if content.endswith("]") and "[" in content:
                        last_open = content.rfind("[")
                        if last_open != -1 and last_open < len(content) - 1:
                            meta_block = content[last_open + 1 : -1]
                            content = content[:last_open].strip()
                            meta_parts = [p.strip() for p in meta_block.split(",")]

                            if len(meta_parts) >= 1 and meta_parts[0]:
                                area = meta_parts[0].lower()

                            if len(meta_parts) >= 2 and meta_parts[1]:
                                suggested_owner = meta_parts[1]

                            if len(meta_parts) >= 3 and meta_parts[2]:
                                pr = meta_parts[2].upper()
                                if pr.startswith("P"):
                                    try:
                                        priority = int(pr[1:])
                                    except ValueError:
                                        priority = 3

                # ---------- Split title / description ----------
                # Prefer en dash or " - " with spaces; avoid splitting on hyphens inside words.
                title = content
                desc = content

                if " – " in content:
                    parts = content.split(" – ", 1)
                    title = parts[0].strip()
                    desc = parts[1].strip()
                elif " - " in content:
                    parts = content.split(" - ", 1)
                    title = parts[0].strip()
                    desc = parts[1].strip()
                else:
                    # No clear separator; keep full content as title & desc
                    title = content.strip()
                    desc = title

                lower_title = title.lower()

                # Default routing: log_tool
                suggested_tool = "log_tool"
                message_text = desc

                # Route certain titles to Slack if such a tool exists
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
                        area=area,
                        suggested_owner=suggested_owner,
                        priority=priority,
                    )
                )

        return tasks


# Optional: simple dummy LLM for standalone testing of this file.
class DummyLLM:
    def __init__(self) -> None:
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self._usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        return (
            "PLAN:\n"
            "- Example plan.\n\n"
            "TASKS:\n"
            "1. [growth, CRO, P1] Launch campaign – Do a thing.\n"
            "2. [ops, COO, P2] Fix process – Another thing.\n"
        )

    def get_last_usage(self) -> Dict[str, int]:
        return self._usage


if __name__ == "__main__":
    # Minimal demo if you run `python agentic_ceo.py` directly
    company = CompanyProfile(
        name="DemoCo",
        industry="Demo",
        vision="Test",
        mission="Test",
        north_star_metric="Demo Metric",
    )
    llm = DummyLLM()
    ceo = AgenticCEO(company=company, llm=llm)
    log_sink: List[str] = []
    ceo.register_tool(LogTool(sink=log_sink))

    print("=== DAILY PLAN ===")
    plan = ceo.plan_day()
    print(plan)

    print("\n=== RUN TASKS ===")
    for t in list(ceo.state.tasks):
        if t.status != "done":
            print(ceo.run_task(t))

    print("\n=== LOG SINK ===")
    for line in log_sink:
        print(line)