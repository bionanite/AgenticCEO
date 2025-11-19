from __future__ import annotations

import os
from typing import Dict, Any, List

import yaml
from dotenv import load_dotenv

from agentic_ceo import AgenticCEO, CompanyProfile, CEOEvent, LogTool
from memory_engine import MemoryEngine
from kpi_engine import KPIEngine, KPIThreshold
from llm_openai import OpenAILLM, LLMClient

# If you have these modules, they can be used for delegation.
# If not, the imports will be ignored and delegation methods will no-op.
try:
    from agents import CROAgent, COOAgent, CTOAgent  # type: ignore
    from delegation_tools import (  # type: ignore
        CRODelegationTool,
        COODelegationTool,
        CTODelegationTool,
    )
except Exception:  # pragma: no cover
    CROAgent = COOAgent = CTOAgent = None  # type: ignore
    CRODelegationTool = COODelegationTool = CTODelegationTool = None  # type: ignore

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
) -> (CompanyProfile, List[KPIThreshold]):
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
    High-level orchestrator around AgenticCEO + KPIEngine.

    - Loads company profile & KPIs from YAML
    - Holds the OpenAI LLM client
    - Exposes helpers: record_kpi, ingest_event, run_pending_tasks,
      snapshot, personal_briefing, delegation to CRO/COO/CTO agents.
    """

    def __init__(
        self,
        company_profile: CompanyProfile,
        llm: LLMClient,
        kpi_thresholds: List[KPIThreshold],
    ) -> None:
        self.memory = MemoryEngine()
        self.llm = llm

        # Core CEO + tools
        self.log_sink: List[str] = []
        log_tool = LogTool(sink=self.log_sink)

        tools = {"log_tool": log_tool}
        # If you implemented SlackTool/EmailTool/NotionTool you can add them here.

        self.ceo = AgenticCEO(
            company=company_profile,
            llm=llm,
            tools=tools,
            memory_engine=self.memory,
        )

        self.kpi_engine = KPIEngine()
        self.kpi_engine.register_many(kpi_thresholds)

        # Disable specialist functional agents unless fully configured
        self.cro_agent = None
        self.coo_agent = None
        self.cto_agent = None

    # ------------- Core wiring -------------

    def plan_day(self) -> str:
        return self.ceo.plan_day()

    def record_kpi(
        self, metric_name: str, value: float, unit: str, source: str = "manual"
    ) -> Dict[str, Any]:
        return self.kpi_engine.record_kpi(
            ceo=self.ceo,
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=source,
        )

    def ingest_event(self, event_type: str, payload: Dict[str, Any]) -> str:
        event = CEOEvent(type=event_type, payload=payload)
        return self.ceo.ingest_event(event)

    def run_pending_tasks(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for t in list(self.ceo.state.tasks):
            if t.status != "done":
                res = self.ceo.run_task(t)
                results.append({"task": t.title, "result": res})
        return results

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
        return self.cro_agent.run(instruction, context=context)  # type: ignore

    def delegate_to_coo(self, instruction: str, extra_context: str = "") -> str:
        if not self.coo_agent:
            return "COOAgent not configured."
        context = self._build_company_context() + "\n" + extra_context
        return self.coo_agent.run(instruction, context=context)  # type: ignore

    def delegate_to_cto(self, instruction: str, extra_context: str = "") -> str:
        if not self.cto_agent:
            return "CTOAgent not configured."
        context = self._build_company_context() + "\n" + extra_context
        return self.cto_agent.run(instruction, context=context)  # type: ignore

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

    # ------------- Factory -------------

    @classmethod
    def from_config(
        cls,
        config_path: str = DEFAULT_CONFIG_PATH,
        company_key: str = DEFAULT_COMPANY_KEY,
    ) -> "CompanyBrain":
        profile, kpis = load_company_profile_from_config(config_path, company_key)
        llm = OpenAILLM(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        return cls(company_profile=profile, llm=llm, kpi_thresholds=kpis)


# Convenience for other modules (e.g. Slack server)
def create_default_brain() -> CompanyBrain:
    return CompanyBrain.from_config()


# ------------------------------------------------------------
# Demo run
# ------------------------------------------------------------
if __name__ == "__main__":
    brain = create_default_brain()

    print("\n=== DAILY PLAN ===")
    plan = brain.plan_day()
    print(plan)

    # Example multi-KPI recording — adjust numbers as you like
    print("\n=== KPI UPDATES ===")
    sample_values = {
        "MRR": 140000.0,
        "MAU": 42000.0,
    }
    for metric, value in sample_values.items():
        kpi_res = brain.record_kpi(metric, value, "auto", "manual")
        print(f"\n>>> KPI: {metric}")
        print(kpi_res)

    print("\n=== RUN PENDING TASKS ===")
    results = brain.run_pending_tasks()
    print(results)

    print("\n=== SNAPSHOT ===")
    print(brain.snapshot())

    print("\n=== CEO PERSONAL BRIEFING ===")
    print(brain.personal_briefing())