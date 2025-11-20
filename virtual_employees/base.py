
from __future__ import annotations

from typing import Dict, Any, Optional

from pydantic import BaseModel

from agentic_ceo import CEOTask, LLMClient
from memory_engine import MemoryEngine


class VirtualEmployeeConfig(BaseModel):
    """
    Configuration schema for a reusable virtual employee role.

    This lets you define roles as data (YAML/JSON) instead of hard‑coding
    new Python classes for every job title.
    """
    role_id: str                 # "social_media_manager"
    title: str                   # "Social Media Manager"
    department: str              # "Marketing"
    seniority: str = "IC"        # "IC", "Manager", "Head", etc.
    description: str
    core_responsibilities: str   # multiline bullet-style text
    style_guidelines: str        # how they talk / output
    kpi_focus: str               # "engagement, CTR, followers"
    default_channels: list[str] = []  # optional list of channels / domains


class BaseVirtualEmployee:
    """
    Generic LLM-powered virtual employee.

    Behaviour is controlled entirely by VirtualEmployeeConfig, so you can
    add new roles just by dropping a YAML file in role_configs/.
    """

    def __init__(
        self,
        config: VirtualEmployeeConfig,
        llm: LLMClient,
        company_context: str,
        memory: Optional[MemoryEngine] = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.company_context = company_context
        self.memory = memory

    @property
    def role_id(self) -> str:
        return self.config.role_id

    @property
    def title(self) -> str:
        return self.config.title

    def run_task(self, task: CEOTask) -> str:
        """
        Take a CEOTask and "do the work" for it using the LLM.

        The same logic works for all roles – only the config changes.
        """
        system_prompt = (
            f"You are a virtual employee acting as: {self.config.title}\n"
            f"Department: {self.config.department}\n"
            f"Seniority: {self.config.seniority}\n\n"
            f"Role description:\n{self.config.description}\n\n"
            f"Core responsibilities:\n{self.config.core_responsibilities}\n\n"
            f"Output/style guidelines:\n{self.config.style_guidelines}\n\n"
            f"Primary KPIs you care about: {self.config.kpi_focus}\n\n"
            "You work for the following company:\n"
            f"{self.company_context}\n\n"
            "You must produce concrete, high-quality outputs (emails, plans, copy, "
            "scripts, checklists, SOPs, etc.) rather than abstract advice. "
            "Where helpful, structure output with headings and bullet points."
        )

        user_prompt = (
            f"Task Title: {task.title}\n"
            f"Task Description: {task.description}\n"
            f"Area: {task.area}\n"
            f"Suggested Owner: {task.suggested_owner}\n"
            f"Priority: P{task.priority}\n\n"
            "Do the work for this task. If it is too large to fully complete, "
            "produce the most valuable draft, plan, or artefact that moves it "
            "meaningfully forward today."
        )

        result = self.llm.complete(system_prompt, user_prompt)

        # Optional memory logging
        if self.memory is not None:
            try:
                usage = self.llm.get_last_usage()
            except Exception:
                usage = {}

            self.memory.record_tool_call(
                tool_name=self.config.role_id,
                payload={
                    "task_id": task.id,
                    "task_title": task.title,
                    "task_description": task.description,
                    "area": task.area,
                    "suggested_owner": task.suggested_owner,
                },
                result={
                    "output": result,
                    "usage": usage,
                },
            )

        return result
