# agents.py
from __future__ import annotations

from typing import Dict, Any

from llm_openai import LLMClient


class FunctionalAgent:
    """
    Lightweight functional agent base class (no Pydantic).
    Handles:
    - role-specific system prompt
    - shared LLM client
    - optional tools registry
    """

    def __init__(self, name: str, role: str, system_prompt: str, llm: LLMClient) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm
        self.tools: Dict[str, Any] = {}

    def register_tool(self, name: str, tool: Any) -> None:
        self.tools[name] = tool

    def think(self, instruction: str, context: str = "") -> str:
        """
        Ask the functional agent to reason about something within its domain.
        """
        user_prompt = (
            f"Instruction:\n{instruction}\n\n"
            f"Context:\n{context}"
        )
        return self.llm.complete(self.system_prompt, user_prompt)


class CROAgent(FunctionalAgent):
    @classmethod
    def create(cls, llm: LLMClient) -> "CROAgent":
        return cls(
            name="CRO Agent",
            role="Chief Revenue Officer",
            llm=llm,
            system_prompt=(
                "You are an AI Chief Revenue Officer for a B2B services company. "
                "You focus on revenue growth, MRR, churn, sales pipeline, account expansion, "
                "and pricing strategies. Always propose concrete, measurable actions."
            ),
        )


class COOAgent(FunctionalAgent):
    @classmethod
    def create(cls, llm: LLMClient) -> "COOAgent":
        return cls(
            name="COO Agent",
            role="Chief Operating Officer",
            llm=llm,
            system_prompt=(
                "You are an AI COO. You optimize operations, service delivery, SLAs, "
                "workforce scheduling, and incident reduction. Be pragmatic and process-driven."
            ),
        )


class CTOAgent(FunctionalAgent):
    @classmethod
    def create(cls, llm: LLMClient) -> "CTOAgent":
        return cls(
            name="CTO Agent",
            role="Chief Technology Officer",
            llm=llm,
            system_prompt=(
                "You are an AI CTO. You design the technology roadmap, integrations, AI systems, "
                "and reliability strategy. Think in architectures, tradeoffs, and implementation steps."
            ),
        )