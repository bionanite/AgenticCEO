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
    priority: int = Field(ge=1, le=5, default=3)
    timeframe: str = "Q1"
    status: str = "active"
    metrics: List[Metric] = []


class CEOTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    objective_id: Optional[str] = None

    priority: int = Field(ge=1, le=5, default=3)
    area: str = "general"
    suggested_owner: str = "CEO-Agent"

    owner: str = "CEO-Agent"
    due_date: Optional[dt.date] = None
    status: str = "todo"  # todo | in-progress | done | blocked
    suggested_tool: Optional[str] = None
    tool_input: Dict[str, Any] = {}
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    requires_approval: bool = False
    approved: bool = False


class CEOEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    payload: Dict[str, Any] = {}
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class CEOState(BaseModel):
    date: dt.date = Field(default_factory=lambda: dt.datetime.utcnow().date())
    focus_theme: str = "Default focus"
    objectives: List[CEOObjective] = []
    tasks: List[CEOTask] = []
    notes: List[str] = []


# ============================================================
# 2. TOOL INTERFACE
# ============================================================

class Tool(Protocol):
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]]
    output_schema: Optional[Dict[str, Any]]

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


# ============================================================
# 3. MCP SERVER INTEGRATION
# ============================================================

class MCPClient(Protocol):
    """
    Minimal protocol for an MCP client.
    """

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        ...


class MCPTool:
    """Adapter to expose an MCP tool as a local Tool."""

    def __init__(
        self,
        name: str,
        description: str,
        mcp_tool_name: Optional[str],
        client: MCPClient,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self._target = mcp_tool_name or name
        self._client = client

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._client.call_tool(self._target, payload)
        except Exception as e:
            return {"ok": False, "error": str(e), "tool": self._target}


# ============================================================
# 4. BASE LOGGING TOOL (example)
# ============================================================

class LogTool:
    name = "log_tool"
    description = "Simple logging tool"

    input_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    def __init__(self, sink: Optional[List[str]] = None):
        self.sink = sink if sink is not None else []

    def run(self, payload: Dict[str, Any]):
        msg = payload.get("message", "")
        entry = f"[{dt.datetime.utcnow().isoformat()}] {msg}"
        self.sink.append(entry)
        return {"ok": True, "logged": entry}


# ============================================================
# 5. LLM PROTOCOL
# ============================================================

class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...

    def get_last_usage(self) -> Dict[str, int]:
        ...


# ============================================================
# 6. AGENTIC CEO CORE
# ============================================================

class AgenticCEO:

    def __init__(
        self,
        company: CompanyProfile,
        llm: LLMClient,
        tools: Optional[Dict[str, Tool]] = None,
        memory_engine: Optional[MemoryEngine] = None,
        mcp_client: Optional[MCPClient] = None,
        execution_mode: str = "auto",  # auto | approval | dry_run
    ):
        self.company = company
        self.llm = llm
        self.memory = memory_engine or MemoryEngine()
        self.tools = tools or {}
        self.state = CEOState(
            focus_theme=f"Grow {company.name} using the north star: {company.north_star_metric}"
        )
        self.mcp_client = mcp_client
        self.execution_mode = execution_mode

    # -------------------------
    # TOOL REGISTRATION
    # -------------------------

    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool

    def register_mcp_tool(
        self,
        name: str,
        description: str,
        mcp_tool_name: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ):
        if not self.mcp_client:
            raise ValueError("AgenticCEO has no MCP client configured.")

        self.tools[name] = MCPTool(
            name=name,
            description=description,
            mcp_tool_name=mcp_tool_name or name,
            client=self.mcp_client,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    # -------------------------
    # DAILY PLAN
    # -------------------------

    def plan_day(self) -> str:
        system_prompt = (
            "You are an Agentic CEO. Output a daily plan + tasks."
        )

        user_prompt = (
            f"Company: {self.company.name}\n"
            f"Industry: {self.company.industry}\n"
            f"Mission: {self.company.mission}\n"
            f"North Star: {self.company.north_star_metric}\n\n"
            "Output:\n"
            "PLAN:\n"
            "- item\n\n"
            "TASKS:\n"
            "1. [area, OWNER, P1] Title – description\n"
        )

        resp = self.llm.complete(system_prompt, user_prompt)

        try:
            usage = self.llm.get_last_usage()
            self.memory.record_token_usage("daily_plan", usage)
        except Exception as e:
            self.memory.record_decision(
                f"Token log error: {e}",
                {"source": "daily_plan"},
            )

        self.memory.record_decision(
            f"Daily plan for {self.state.date}:\n{resp}",
            {"type": "plan"},
        )

        new_tasks = self._parse_tasks(resp, CEOEvent(type="daily_plan", payload={}))
        self.state.tasks.extend(new_tasks)

        return resp

    # -------------------------
    # EVENT INGESTION
    # -------------------------

    def ingest_event(self, event: CEOEvent) -> str:
        system_prompt = (
            "You are an Agentic CEO. An event occurred. Output DECISION + TASKS."
        )

        user_prompt = (
            f"Event: {event.type}\nPayload: {event.payload}\n\n"
            "DECISION:\n- ...\n\nTASKS:\n"
            "1. [growth, CRO, P1] Title – desc\n"
        )

        resp = self.llm.complete(system_prompt, user_prompt)

        try:
            self.memory.record_token_usage("event_decision", self.llm.get_last_usage())
        except Exception:
            pass

        self.memory.record_event(event.type, event.payload)
        self.memory.record_decision(
            f"Event handled: {event.type}\n{resp}",
            {"type": "event"},
        )

        new_tasks = self._parse_tasks(resp, event)
        self.state.tasks.extend(new_tasks)

        return resp

    # -------------------------
    # TASK EXECUTION
    # -------------------------

    def run_task(self, task: CEOTask) -> Dict[str, Any]:
        task.updated_at = dt.datetime.utcnow()

        # Approval mode
        if self.execution_mode == "approval" and task.requires_approval and not task.approved:
            task.status = "blocked"
            self.memory.record_decision(
                f"Task blocked (needs approval): {task.title}",
                {"task_id": task.id},
            )
            return {"status": "blocked"}

        # Dry run
        if self.execution_mode == "dry_run":
            self.memory.record_decision(
                f"[DRY RUN] Would run task: {task.title}",
                {"task_id": task.id},
            )
            return {"status": "skipped"}

        # If tool exists → execute
        if task.suggested_tool and task.suggested_tool in self.tools:
            tool = self.tools[task.suggested_tool]
            payload = task.tool_input or {"message": task.description}

            try:
                result = tool.run(payload)
            except Exception as e:
                task.status = "blocked"
                self.memory.record_decision(
                    f"Tool failure {tool.name}: {e}",
                    {"task": task.id},
                )
                return {"status": "error", "error": str(e)}

            self.memory.record_tool_call(tool.name, payload, result)

            if not result.get("ok", True):
                task.status = "blocked"
                return {"status": "error", "result": result}

            task.status = "done"
            return {"status": "done", "result": result}

        # No tool → just log as manual completion
        task.status = "done"
        self.memory.record_decision(
            f"Manual task completed: {task.title}",
            {"task_id": task.id},
        )
        return {"status": "done"}

    def run_pending_tasks(self):
        results = []
        for t in self.state.tasks:
            if t.status in {"todo", "blocked", "in-progress"}:
                result = self.run_task(t)
                results.append({"task": t.title, "result": result})
        return results

    # -------------------------
    # REFLECTION
    # -------------------------

    def reflect(self):
        txt = self.memory.summarize_day(self.state.date)
        txt += f"- Tasks tracked: {len(self.state.tasks)}"
        self.memory.record_reflection(txt)
        return txt

    # -------------------------
    # TASK PARSER
    # -------------------------

    def _parse_tasks(self, text: str, event: CEOEvent) -> List[CEOTask]:
        lines = text.splitlines()
        tasks = []
        inside = False

        for line in lines:
            s = line.strip()

            if s.upper().startswith("TASKS"):
                inside = True
                continue
            if not inside:
                continue
            if not s or not s[0].isdigit() or "." not in s:
                continue

            content = s.split(".", 1)[1].strip()

            area = "general"
            owner = "CEO-Agent"
            priority = 3

            if content.startswith("[") and "]" in content:
                part = content[1:content.index("]")]
                content = content[content.index("]") + 1:].strip()
                meta = [p.strip() for p in part.split(",")]

                if len(meta) > 0:
                    area = meta[0].lower()
                if len(meta) > 1:
                    owner = meta[1]
                if len(meta) > 2 and meta[2].upper().startswith("P"):
                    try:
                        priority = int(meta[2][1:])
                    except:
                        priority = 3

            title = content
            desc = content
            if " – " in content:
                title, desc = content.split(" – ", 1)
            elif " - " in content:
                title, desc = content.split(" - ", 1)

            tool = "log_tool"
            tool_input = {"message": f"[From {event.type}] {desc}"}

            tasks.append(
                CEOTask(
                    title=title.strip(),
                    description=desc.strip(),
                    owner="Agentic CEO",
                    due_date=self.state.date,
                    suggested_tool=tool,
                    tool_input=tool_input,
                    area=area,
                    suggested_owner=owner,
                    priority=priority,
                )
            )

        return tasks


# ============================================================
# 7. DUMMY LLM (for testing)
# ============================================================

class DummyLLM:
    def __init__(self):
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self._usage = {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}
        return (
            "PLAN:\n"
            "- Example.\n\n"
            "TASKS:\n"
            "1. [growth, CRO, P1] Launch – do it.\n"
            "2. [ops, COO, P2] Fix – do it.\n"
        )

    def get_last_usage(self) -> Dict[str, int]:
        return self._usage


# ============================================================
# 8. INLINE DEMO
# ============================================================

if __name__ == "__main__":
    company = CompanyProfile(
        name="DemoCo",
        industry="Demo",
        vision="Test",
        mission="Test",
        north_star_metric="Demo Metric",
    )

    llm = DummyLLM()
    ceo = AgenticCEO(company=company, llm=llm)

    sink = []
    ceo.register_tool(LogTool(sink=sink))

    print("=== DAILY PLAN ===")
    print(ceo.plan_day())

    print("\n=== TASK EXECUTION ===")
    print(ceo.run_pending_tasks())

    print("\n=== LOG ===")
    for x in sink:
        print(x)