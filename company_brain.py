from __future__ import annotations

import os
from typing import Dict, Any, List, Optional, Tuple

import yaml
from dotenv import load_dotenv

from agentic_ceo import AgenticCEO, CompanyProfile, CEOEvent, LogTool
from memory_engine import MemoryEngine
from kpi_engine import KPIEngine, KPIThreshold
from llm_openai import OpenAILLM, LLMClient
from agents import CROAgent, COOAgent, CTOAgent
from virtual_staff_manager import VirtualStaffManager
from task_manager import TaskManager

load_dotenv()

DEFAULT_CONFIG_PATH = os.getenv("AGENTIC_CEO_CONFIG", "company_config.yaml")
DEFAULT_COMPANY_KEY = os.getenv("AGENTIC_CEO_COMPANY", "next_ecosystem")


# ------------------------------------------------------------
# Config loading
# ------------------------------------------------------------

def load_company_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_company_profile_from_config(
    config_path: str,
    company_key: str,
) -> Tuple[CompanyProfile, List[KPIThreshold]]:
    cfg = load_company_config(config_path)
    companies = cfg.get("companies", {})
    if company_key not in companies:
        raise KeyError(f"Company key '{company_key}' not found in config {config_path}")

    c = companies[company_key]

    profile = CompanyProfile(
        name=c["name"],
        industry=c.get("industry", ""),
        vision=c.get("vision", ""),
        mission=c.get("mission", ""),
        north_star_metric=c.get("north_star_metric", ""),
        primary_markets=c.get("primary_markets", []) or [],
        products_or_services=c.get("products_or_services", []) or [],
        team_size=c.get("team_size", 0),
        website=c.get("website"),
    )

    kpi_cfgs = c.get("kpis", []) or []
    thresholds: List[KPIThreshold] = []
    for k in kpi_cfgs:
        thresholds.append(
            KPIThreshold(
                name=k["name"],
                min_value=k.get("min"),
                max_value=k.get("max"),
                unit=k.get("unit", ""),
            )
        )

    return profile, thresholds


# ------------------------------------------------------------
# CompanyBrain
# ------------------------------------------------------------

class CompanyBrain:
    """
    High-level orchestrator around AgenticCEO + KPIEngine + functional agents (CRO/COO/CTO)
    + VirtualStaffManager (autonomous virtual org) + TaskManager (task tree + reviews).

    - Loads company profile & KPIs from YAML
    - Holds the OpenAI LLM client
    - Exposes helpers: record_kpi, ingest_event, run_pending_tasks,
      snapshot, personal_briefing, delegation to CRO/COO/CTO
    - Auto-spawns virtual employees when KPIs are under stress
    - Routes tasks to human-like specialist agents + virtual staff
    - Maintains parent/child tasks + delegate reviews via TaskManager
    """

    def __init__(
        self,
        company_profile: CompanyProfile,
        llm: LLMClient,
        kpi_thresholds: List[KPIThreshold],
        company_id: Optional[str] = None,
    ) -> None:
        # Core shared memory
        self.memory = MemoryEngine()
        self.llm = llm

        # Remember company profile & id for external access
        self.company_profile = company_profile
        self.company_id = company_id or company_profile.name

        # Core CEO + tools
        self.log_sink: List[str] = []
        log_tool = LogTool(sink=self.log_sink)

        tools = {"log_tool": log_tool}
        # If/when you add Slack/Email/Notion tools, register them here.

        self.ceo = AgenticCEO(
            company=company_profile,
            llm=llm,
            tools=tools,
            memory_engine=self.memory,
        )

        # KPI engine
        self.kpi_engine = KPIEngine()
        self.kpi_engine.register_many(kpi_thresholds)

        # Specialist agents (CRO / COO / CTO)
        self.cro_agent: Optional[CROAgent] = CROAgent.create(llm)
        self.coo_agent: Optional[COOAgent] = COOAgent.create(llm)
        self.cto_agent: Optional[CTOAgent] = CTOAgent.create(llm)

        # Virtual Staff Manager (auto “virtual hiring” + capacity tracking)
        self.virtual_staff = VirtualStaffManager(
            company_id=self.company_id,
            company_name=self.company_profile.name,
            storage_dir=os.getenv("AGENTIC_STATE_DIR", ".agentic_state"),
            memory=self.memory,
        )

        # TaskManager (parent/child tasks, delegation reviews, tree view)
        self.task_manager = TaskManager(
            state=self.ceo.state,
            memory=self.memory,
            company_id=self.company_id,
            storage_dir=os.getenv("AGENTIC_STATE_DIR", ".agentic_state"),
        )

    # ------------- Core wiring -------------

    def plan_day(self) -> str:
        """
        Ask the AgenticCEO for a daily plan.
        Tasks are stored inside self.ceo.state.tasks.
        """
        return self.ceo.plan_day()

    def record_kpi(
        self,
        metric_name: str,
        value: float,
        unit: str,
        source: str = "manual",
    ) -> Dict[str, Any]:
        """
        Record a KPI reading, trigger KPIEngine logic, and then:
        - If alerts fired, auto-adjust the virtual org (virtual hires where needed).
        """
        result = self.kpi_engine.record_kpi(
            ceo=self.ceo,
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=source,
        )

        # If KPI is out of range, auto-consider virtual hires
        try:
            alerts = result.get("alerts_triggered", 0)
            if alerts and alerts > 0:
                self._auto_virtual_reorg_on_kpi(metric_name, result)
        except Exception:
            # Never let auto-hire logic crash KPI recording
            pass

        return result

    def ingest_event(self, event_type: str, payload: Dict[str, Any]) -> str:
        """
        Wrapper around AgenticCEO.ingest_event.
        """
        event = CEOEvent(type=event_type, payload=payload)
        return self.ceo.ingest_event(event)

    # ------------- Delegation helpers -------------

    def _build_company_context(self) -> str:
        company = self.ceo.company
        markets = ", ".join(company.primary_markets) or "N/A"
        products = ", ".join(company.products_or_services) or "N/A"
        return (
            f"You are advising for {company.name}, operating in the {company.industry} industry. "
            f"The company's vision is: {company.vision}. "
            f"The mission is: {company.mission}. "
            f"The north-star metric is: {company.north_star_metric}. "
            f"Primary markets: {markets}. "
            f"Key products/services: {products}."
        )

    def delegate_to_cro(self, instruction: str, extra_context: str = "") -> str:
        if not self.cro_agent:
            return "CROAgent not configured."
        context = self._build_company_context() + "\n" + extra_context
        return self.cro_agent.run(instruction, context=context)

    def delegate_to_coo(self, instruction: str, extra_context: str = "") -> str:
        if not self.coo_agent:
            return "COOAgent not configured."
        context = self._build_company_context() + "\n" + extra_context
        return self.coo_agent.run(instruction, context=context)

    def delegate_to_cto(self, instruction: str, extra_context: str = "") -> str:
        if not self.cto_agent:
            return "CTOAgent not configured."
        context = self._build_company_context() + "\n" + extra_context
        return self.cto_agent.run(instruction, context=context)

    # ------------- Agent routing for tasks -------------

    def _maybe_delegate_task_to_agent(self, task) -> Optional[Dict[str, Any]]:
        """
        Decide if a task should go to CRO/COO/CTO based on its area and route it.
        Returns a result dict if delegated, otherwise None.
        """
        area = (task.area or "").lower()
        desc = task.description or task.title

        # Map area -> agent
        agent_name = None
        responder = None

        # Revenue / growth / marketing → CRO
        if any(key in area for key in ["revenue", "growth", "mrr", "mau", "marketing", "sales"]):
            agent_name = "CROAgent"
            responder = self.delegate_to_cro

        # Operations / CX / customer success → COO
        elif any(key in area for key in ["ops", "operations", "cx", "customer success", "service", "support"]):
            agent_name = "COOAgent"
            responder = self.delegate_to_coo

        # Product / tech / engineering / data → CTO
        elif any(key in area for key in ["product", "tech", "engineering", "data", "ai"]):
            agent_name = "CTOAgent"
            responder = self.delegate_to_cto

        if not responder:
            return None

        # Call the agent with context + instruction
        context = f"Task Title: {task.title}\nSuggested Owner: {task.suggested_owner}\nPriority: P{task.priority}"
        answer = responder(desc, extra_context=context)

        # Log into memory as a 'tool' call for traceability
        self.ceo.memory.record_tool_call(
            tool_name=agent_name,
            payload={"task_title": task.title, "area": task.area, "description": desc},
            result={"answer": answer},
        )

        task.status = "done"

        return {"status": "done", "tool": agent_name, "result": answer}

    def _maybe_route_task_to_virtual_staff(self, task) -> Optional[Dict[str, Any]]:
        """
        If the task's suggested_owner looks like a virtual role
        (e.g. 'Virtual SDR', 'Virtual Social Media Manager'),
        ensure capacity and mark the task as assigned to a virtual employee.
        """
        owner = (task.suggested_owner or "").strip()

        if not owner:
            return None

        owner_lower = owner.lower()

        # Heuristic: anything that starts with 'virtual ' or contains 'virtual'
        if "virtual" not in owner_lower:
            return None

        # Ensure capacity for that role (auto-hire if needed)
        reason = f"Auto-assigned for task '{task.title}'"
        cap_res = self.virtual_staff.ensure_capacity_for_role(
            role=owner,
            owner_kpi=None,
            min_task_slots=10,
            notes=f"Auto-created/used for task: {task.title}",
            log_reason=reason,
        )

        ve = cap_res.get("employee")
        if ve is None:
            return None

        # Mark the task as assigned in the manager
        self.virtual_staff.assign_task_to_virtual_employee(
            employee_id=ve.id,
            task_title=task.title,
            task_payload={"area": task.area, "priority": task.priority},
        )

        # Still let the CEO run the task (e.g. using log_tool or future tools)
        run_res = self.ceo.run_task(task)

        return {
            "status": "done",
            "virtual_employee_id": ve.id,
            "virtual_role": ve.role,
            "capacity_before": cap_res.get("capacity_before"),
            "capacity_after": cap_res.get("capacity_after"),
            "ceo_result": run_res,
        }

    def run_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        Run all not-done tasks.

        Order:
        - Try to route to CRO/COO/CTO based on area.
        - Then try to route to Virtual Staff based on suggested_owner.
        - If no mapping, fall back to AgenticCEO.run_task() (log_tool/manual).
        """
        results: List[Dict[str, Any]] = []

        for t in list(self.ceo.state.tasks):
            if t.status != "done":
                # 1) CRO / COO / CTO delegation
                delegated = self._maybe_delegate_task_to_agent(t)
                if delegated is not None:
                    results.append({"task": t.title, "result": delegated})
                    continue

                # 2) Virtual staff routing based on suggested_owner
                v_res = self._maybe_route_task_to_virtual_staff(t)
                if v_res is not None:
                    results.append({"task": t.title, "result": v_res})
                    continue

                # 3) Fallback: CEO's own tool routing (log_tool, etc.)
                res = self.ceo.run_task(t)
                results.append({"task": t.title, "result": res})

        return results

    # ------------- Virtual staff helpers -------------

    def ensure_virtual_capacity(
        self,
        role: str,
        owner_kpi: Optional[str] = None,
        min_task_slots: int = 10,
        notes: str = "",
        log_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Public helper: ensure there is enough virtual capacity for a given role.

        Example:
            brain.ensure_virtual_capacity(
                role="Virtual SDR",
                owner_kpi="Monthly Closed Deals",
                min_task_slots=20,
                notes="Auto-hired SDRs because Monthly Closed Deals is below target.",
            )
        """
        return self.virtual_staff.ensure_capacity_for_role(
            role=role,
            owner_kpi=owner_kpi,
            min_task_slots=min_task_slots,
            notes=notes,
            log_reason=log_reason,
        )

    def assign_task_to_virtual_staff(
        self,
        employee_id: str,
        task_title: str,
        task_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Public helper: mark a task as assigned to a given virtual employee.
        """
        return self.virtual_staff.assign_task_to_virtual_employee(
            employee_id=employee_id,
            task_title=task_title,
            task_payload=task_payload or {},
        )

    # ------------- Task manager helpers -------------

    def create_subtask(
        self,
        parent_task_id: str,
        title: str,
        description: str,
        area: Optional[str] = None,
        suggested_owner: Optional[str] = None,
        priority: Optional[int] = None,
    ):
        """
        Thin wrapper around TaskManager.create_subtask().
        """
        return self.task_manager.create_subtask(
            parent_task_id=parent_task_id,
            title=title,
            description=description,
            area=area,
            suggested_owner=suggested_owner,
            priority=priority,
        )

    def mark_task_done_by_delegate(
        self,
        task_id: str,
        delegate_name: str,
        notes: str = "",
    ):
        """
        Thin wrapper around TaskManager.mark_task_done_by_delegate().
        """
        return self.task_manager.mark_task_done_by_delegate(
            task_id=task_id,
            delegate_name=delegate_name,
            notes=notes,
        )

    def review_task(
        self,
        task_id: str,
        approved: bool,
        reviewed_by: str,
        comments: str = "",
    ):
        """
        Thin wrapper around TaskManager.review_task().
        """
        return self.task_manager.review_task(
            task_id=task_id,
            approved=approved,
            reviewed_by=reviewed_by,
            comments=comments,
        )

    def open_task_tree(self) -> str:
        """
        Pretty-printed open task tree (for CLI, debugging, dashboards).
        """
        return self.task_manager.format_open_task_tree()

    # ------------- Higher-level views -------------

    def snapshot(self) -> str:
        """
        Compact dashboard-style summary using MemoryEngine + current state.
        """
        base = self.ceo.memory.summarize_day(self.ceo.state.date)
        open_tasks = len([t for t in self.ceo.state.tasks if t.status != "done"])
        base += f"- Open tasks (not done): {open_tasks}\n"
        return base

    def personal_briefing(self) -> str:
        """
        Chief-of-Staff style: what should the human CEO (Sheraz) personally do today?
        Focus on 3 concrete, real-world actions – not stats about decisions/events.
        """
        summary = self.ceo.memory.summarize_day(self.ceo.state.date)

        system_prompt = (
            "You are the Chief of Staff to a very busy founder/CEO.\n"
            "You ONLY suggest concrete, real-world actions (calls, approvals, reviews,\n"
            "recording a video, meeting key people, making one strategic decision, etc.).\n"
            "You DO NOT tell them to 'review decisions' or 'analyze events' generically.\n"
            "You focus on leverage: things only the CEO can do, not the team.\n"
            "Be concise and practical."
        )

        user_prompt = (
            f"Company: {self.ceo.company.name}\n"
            f"North Star Metric: {self.ceo.company.north_star_metric}\n\n"
            f"Here is what the Agentic CEO has planned and done today (including KPI alerts and tasks):\n"
            f"{summary}\n\n"
            "From this, infer what is happening in the business and propose the 3 highest-leverage\n"
            "actions the human CEO should personally take TODAY.\n"
            "Make them specific and actionable, for example:\n"
            "1. Record a 3-minute Loom for the growth team explaining X.\n"
            "2. Call our top partner Y to unblock Z.\n"
            "3. Approve the experiment on A/B pricing for NextChat onboarding.\n\n"
            "Now output ONLY the 3 actions in this format:\n"
            "1. ...\n2. ...\n3. ..."
        )

        text = self.llm.complete(system_prompt, user_prompt)
        return text

    # ------------- Internal: auto virtual org from KPIs -------------

    def _auto_virtual_reorg_on_kpi(
        self,
        metric_name: str,
        kpi_result: Dict[str, Any],
    ) -> None:
        """
        When a KPI is out of range, auto-create/scale virtual staff for the relevant domain.

        This is deliberately opinionated but simple. You can expand the mapping over time.
        """
        name_lower = metric_name.lower()
        alerts = kpi_result.get("alerts_triggered", 0)
        decisions = kpi_result.get("alert_decisions", [])
        decision_text = "\n\n".join(decisions) if isinstance(decisions, list) else str(decisions)

        roles_to_ensure: List[Dict[str, Any]] = []

        # --- Growth / Revenue style KPIs ---
        if "mrr" in name_lower or "online revenue" in name_lower or "monthly revenue" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Growth Marketer",
                    "owner_kpi": metric_name,
                    "min_slots": 20,
                    "notes": f"Auto-created due to {metric_name} alert.",
                }
            )

        if "mau" in name_lower or "weekly active users" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Growth PM",
                    "owner_kpi": metric_name,
                    "min_slots": 15,
                    "notes": f"Focus on activation and engagement for {metric_name}.",
                }
            )

        if "closed deals" in name_lower or "gmv" in name_lower or "lead-to-client" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual SDR",
                    "owner_kpi": metric_name,
                    "min_slots": 25,
                    "notes": f"Increase pipeline and follow-ups because {metric_name} is below target.",
                }
            )
            roles_to_ensure.append(
                {
                    "role": "Virtual Sales Closer",
                    "owner_kpi": metric_name,
                    "min_slots": 15,
                    "notes": f"Improve closing rate because {metric_name} is below target.",
                }
            )

        if "manned hours" in name_lower or "placements" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Scheduler",
                    "owner_kpi": metric_name,
                    "min_slots": 20,
                    "notes": f"Optimize rota / staffing for {metric_name}.",
                }
            )

        # --- Retention / Support style KPIs ---
        if "retention" in name_lower or "repeat purchase" in name_lower or "churn" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Customer Success Manager",
                    "owner_kpi": metric_name,
                    "min_slots": 15,
                    "notes": f"Retention-focused virtual staff, triggered by {metric_name} alert.",
                }
            )

        if "on-time delivery" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Operations Coordinator",
                    "owner_kpi": metric_name,
                    "min_slots": 10,
                    "notes": f"Improve logistics and delivery performance for {metric_name}.",
                }
            )

        # --- R&D / Cost / R&D budget ---
        if "prototype milestones" in name_lower or "trl" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual R&D Project Manager",
                    "owner_kpi": metric_name,
                    "min_slots": 10,
                    "notes": f"Coordinate R&D milestones due to {metric_name} alert.",
                }
            )

        if "cost per unit" in name_lower or "r&d spend vs budget" in name_lower:
            roles_to_ensure.append(
                {
                    "role": "Virtual Cost Controller",
                    "owner_kpi": metric_name,
                    "min_slots": 8,
                    "notes": f"Control manufacturing / R&D costs due to {metric_name} alert.",
                }
            )

        if not roles_to_ensure:
            # Nothing mapped for this KPI – do nothing.
            return

        hires_summaries: List[str] = []
        for r in roles_to_ensure:
            try:
                cap_res = self.virtual_staff.ensure_capacity_for_role(
                    role=r["role"],
                    owner_kpi=r["owner_kpi"],
                    min_task_slots=r["min_slots"],
                    notes=r["notes"],
                    log_reason=f"KPI '{metric_name}' out of range. Decisions:\n{decision_text}",
                )
                created = cap_res.get("created", False)
                ve = cap_res.get("employee")
                if ve:
                    status = "HIRED" if created else "REUSED"
                    hires_summaries.append(
                        f"{status} virtual staff: {ve.role} (id={ve.id}) "
                        f"for KPI '{metric_name}' with min_slots={r['min_slots']}"
                    )
            except Exception:
                # Never allow failures here to crash KPI handling
                continue

        if hires_summaries:
            summary_text = "\n".join(hires_summaries)
            try:
                self.memory.record_decision(
                    text=f"[Virtual Org Adjustment] KPI '{metric_name}' out of range.\n"
                         f"Auto-virtual-org actions:\n{summary_text}",
                    context={"type": "virtual_org_adjustment", "metric_name": metric_name},
                )
            except Exception:
                pass

    # ------------- Factory -------------

    @classmethod
    def from_config(
        cls,
        config_path: str = DEFAULT_CONFIG_PATH,
        company_key: str = DEFAULT_COMPANY_KEY,
    ) -> "CompanyBrain":
        profile, kpis = load_company_profile_from_config(config_path, company_key)
        llm = OpenAILLM(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        return cls(
            company_profile=profile,
            llm=llm,
            kpi_thresholds=kpis,
            company_id=company_key,
        )


# Convenience for other modules (e.g. Slack server later)
def create_default_brain() -> CompanyBrain:
    return CompanyBrain.from_config()
