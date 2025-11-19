# company_brain.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
from pathlib import Path
import os
import json

from agentic_ceo import AgenticCEO, CompanyProfile, CEOEvent, LogTool
from memory_engine import MemoryEngine
from kpi_engine import KPIEngine, KPIThreshold
from tools_real import SlackTool, EmailTool, NotionTool
from agents import CROAgent, COOAgent, CTOAgent
from delegation_tools import CRODelegationTool, COODelegationTool, CTODelegationTool
from llm_openai import OpenAILLM, LLMClient

# Optional YAML support
try:
    import yaml
except ImportError:
    yaml = None

# Defaults (can be overridden via env)
DEFAULT_CONFIG_PATH = os.getenv("AGENTIC_CEO_CONFIG", "company_config.yaml")
DEFAULT_COMPANY_KEY = os.getenv("AGENTIC_CEO_COMPANY", "guardianfm")


# ----------------------------------------------------
# Helper: load CompanyProfile from JSON/YAML config
# ----------------------------------------------------

def load_company_profile_from_config(
    config_path: str,
    company_key: str,
) -> CompanyProfile:
    """
    Load a CompanyProfile from a JSON or YAML config file.

    Expected structure (YAML or JSON):

    companies:
      guardianfm:
        name: "GuardianFM Ltd"
        industry: "Security & Facilities Management"
        vision: "Be the most trusted, AI-first security partner in the UK."
        mission: "Protect people and property with smart, proactive security teams."
        north_star_metric: "Monthly Total Manned Hours Billable"
        primary_markets: ["United Kingdom"]
        products_or_services:
          - "Manned guarding"
          - "Mobile patrols"
          - "Key holding"
          - "Facilities management"
        team_size: 150
        website: "https://guardianfm.com"
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Company config file not found: {config_path}")

    if path.suffix.lower() in {".yml", ".yaml"}:
        if yaml is None:
            raise ImportError(
                "PyYAML is required to load YAML configs. Install with: pip install pyyaml"
            )
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Unsupported config file type: {path.suffix}")

    companies = data.get("companies", data)  # allow top-level or nested under 'companies'

    if company_key not in companies:
        raise KeyError(f"Company key '{company_key}' not found in config {config_path}")

    cfg = companies[company_key]

    return CompanyProfile(
        name=cfg["name"],
        industry=cfg["industry"],
        vision=cfg["vision"],
        mission=cfg["mission"],
        north_star_metric=cfg["north_star_metric"],
        primary_markets=cfg.get("primary_markets", []),
        products_or_services=cfg.get("products_or_services", []),
        team_size=cfg.get("team_size", 0),
        website=cfg.get("website"),
    )


# ----------------------------------------------------
# CompanyBrain core
# ----------------------------------------------------

class CompanyBrain:
    """
    High-level orchestrator:
    - Owns the Agentic CEO
    - Owns KPI engine
    - Owns functional agents (CRO, COO, CTO)
    - Registers real tools + delegation tools

    Construct with a CompanyProfile directly,
    or use `CompanyBrain.from_config(...)` factory.
    """

    def __init__(
        self,
        company_profile: CompanyProfile,
        llm: Optional[LLMClient] = None,
    ) -> None:
        # Shared LLM across CEO + functional agents
        self.llm: LLMClient = llm or OpenAILLM(model="gpt-4.1-mini", temperature=0.2)

        # Memory & CEO
        memory = MemoryEngine()
        self.ceo = AgenticCEO(company=company_profile, llm=self.llm, memory_engine=memory)

        # KPI Engine (you can also load thresholds from config later if you want)
        self.kpi_engine = KPIEngine(
            thresholds=[
                KPIThreshold(metric_name="MRR", min_value=150000, direction="good_high"),
                KPIThreshold(metric_name="ChurnRate", max_value=5.0, direction="good_low"),
            ]
        )

        # Functional Agents
        self.cro = CROAgent.create(llm=self.llm)
        self.coo = COOAgent.create(llm=self.llm)
        self.cto = CTOAgent.create(llm=self.llm)

        # Tools registry
        self.tools: Dict[str, Any] = {}
        self._register_tools()

    # -------- Factory: load from config file --------

    @classmethod
    def from_config(
        cls,
        config_path: Optional[str] = None,
        company_key: Optional[str] = None,
        llm: Optional[LLMClient] = None,
    ) -> "CompanyBrain":
        """
        Factory method to build a CompanyBrain from JSON/YAML config.

        - config_path: path to company_config.yaml / .json
        - company_key: key under 'companies:' (e.g. 'guardianfm')
        """
        cfg_path = config_path or DEFAULT_CONFIG_PATH
        key = company_key or DEFAULT_COMPANY_KEY
        profile = load_company_profile_from_config(cfg_path, key)
        return cls(company_profile=profile, llm=llm)

    # -------- Tools wiring --------

    def _register_tools(self) -> None:
        """
        Register all tools the CEO can call.
        """

        # Always-available logging tool
        log_sink: List[str] = []
        log_tool = LogTool(sink=log_sink)
        self.tools[log_tool.name] = log_tool
        self.ceo.register_tool(log_tool)

        # Optional external tools (only if env is configured)
        try:
            slack = SlackTool()
            self.tools[slack.name] = slack
            self.ceo.register_tool(slack)
        except Exception:
            pass

        try:
            email = EmailTool()
            self.tools[email.name] = email
            self.ceo.register_tool(email)
        except Exception:
            pass

        try:
            notion = NotionTool()
            self.tools[notion.name] = notion
            self.ceo.register_tool(notion)
        except Exception:
            pass

        # Delegation tools: wire CRO/COO/CTO into tools
        cro_tool = CRODelegationTool(self.cro)
        coo_tool = COODelegationTool(self.coo)
        cto_tool = CTODelegationTool(self.cto)

        self.tools[cro_tool.name] = cro_tool
        self.tools[coo_tool.name] = coo_tool
        self.tools[cto_tool.name] = cto_tool

        self.ceo.register_tool(cro_tool)
        self.ceo.register_tool(coo_tool)
        self.ceo.register_tool(cto_tool)

    # -------- High-level flows --------

    def daily_start(self) -> str:
        """
        Generate the daily operating plan from the Agentic CEO.
        """
        return self.ceo.plan_day()

    def ingest_event(self, event_type: str, payload: Dict[str, Any]) -> str:
        """
        Ingest an event into the Company Brain and let the CEO respond.
        """
        event = CEOEvent(type=event_type, payload=payload)
        return self.ceo.ingest_event(event)

    def record_kpi(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        """
        Record a KPI value, mirror it into long-term memory,
        and trigger CEO actions if thresholds are breached.
        """
        # 1) Record in KPI engine
        reading = self.kpi_engine.record_kpi(metric_name, value, unit, source)

        # 2) Mirror into CEO memory so reflections see KPI updates
        self.ceo.memory.record_kpi(
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=source,
        )

        # 3) Evaluate thresholds and trigger CEO events if needed
        alerts = self.kpi_engine.evaluate_alerts(reading)

        created_events: List[str] = []

        for alert in alerts:
            decision_text = (
                f"KPI Alert: {alert.metric_name} value {alert.value}. {alert.message}"
            )
            event_payload = {
                "metric_name": alert.metric_name,
                "value": alert.value,
                "message": alert.message,
            }
            resp = self.ingest_event("kpi_alert", event_payload)
            created_events.append(decision_text + "\n" + resp)

        return {
            "reading": reading.model_dump(),
            "alerts_triggered": len(alerts),
            "alert_decisions": created_events,
        }

    def run_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        Execute all tasks in CEO state that are not yet marked as done.
        """
        results: List[Dict[str, Any]] = []
        for t in self.ceo.state.tasks:
            if t.status != "done":
                res = self.ceo.run_task(t)
                results.append({"task": t.title, "result": res})
        return results

    def reflect(self) -> str:
        """
        Generate a reflection summary for today using CEO memory.
        """
        return self.ceo.reflect()

    # Optional: direct delegation helpers (for manual use)
    def delegate_to_cro(self, instruction: str, context: str = "") -> str:
        return self.cro.think(instruction, context)

    def delegate_to_coo(self, instruction: str, context: str = "") -> str:
        return self.coo.think(instruction, context)

    def delegate_to_cto(self, instruction: str, context: str = "") -> str:
        return self.cto.think(instruction, context)


# Convenience function for other modules (e.g. Slack server)
def create_default_brain() -> CompanyBrain:
    """
    Create a CompanyBrain using config path + company key from env or defaults.
    """
    return CompanyBrain.from_config()


if __name__ == "__main__":
    # Demo run using default config
    brain = create_default_brain()

    print("=== DAILY PLAN ===")
    print(brain.daily_start())

    print("\n=== KPI UPDATE (MRR) ===")
    kpi_res = brain.record_kpi("MRR", 140000, "GBP", "manual")
    print(kpi_res)

    print("\n=== RUN PENDING TASKS ===")
    print(brain.run_pending_tasks())

    print("\n=== REFLECTION ===")
    print(brain.reflect())