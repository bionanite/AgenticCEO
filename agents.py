"""
agents.py

Functional agents for different executive roles:
- CROAgent  (Chief Revenue Officer / Growth)
- COOAgent  (Chief Operating Officer / Ops & CX)
- CTOAgent  (Chief Technology Officer / Product & Tech)

Each agent:
- Wraps the same LLM client you use for the Agentic CEO.
- Adds a role-specific system prompt.
- Exposes `run(instruction, context="") -> str`.

Note: This file intentionally does NOT use Pydantic to avoid schema issues
with custom Protocol types like LLMClient. It uses simple dataclasses instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from llm_openai import LLMClient  # your existing LLM client interface


@dataclass
class FunctionalAgent:
    """
    Generic functional agent around an LLM.

    You give it:
    - name          (e.g. "CRO Agent")
    - role          (e.g. "Chief Revenue Officer")
    - system_prompt (personality + mandate)
    - llm           (shared OpenAILLM client)
    """

    name: str
    role: str
    system_prompt: str
    llm: LLMClient

    async def run(self, instruction: str, context: str = "") -> str:
        """
        Execute a domain-specific instruction with optional company context.
        Returns the LLM's response as a string.
        """
        system = self.system_prompt
        user = (
            f"Role: {self.role}\n"
            f"Agent Name: {self.name}\n\n"
            f"Business Context:\n{context}\n\n"
            f"Instruction:\n{instruction}\n\n"
            "Respond with a clear, structured answer including:\n"
            "- Diagnosis (what's going on)\n"
            "- 3–5 concrete actions\n"
            "- Any risks or dependencies\n"
        )
        if hasattr(self.llm, "acomplete"):
            return await self.llm.acomplete(system, user)
        else:
            return self.llm.complete(system, user)


class CROAgent(FunctionalAgent):
    """
    Chief Revenue Officer / Growth Agent:
    - Owns MRR, MAU, funnels, CAC/LTV, pricing, GTM.
    """

    @staticmethod
    def create(llm: LLMClient) -> "CROAgent":
        return CROAgent(
            name="CRO Agent",
            role="Chief Revenue Officer",
            system_prompt=(
                "You are the Chief Revenue Officer (CRO) for a fast-moving AI company. "
                "You think in terms of MAU, MRR, funnels, retention, activation, CAC/LTV, "
                "pricing, packaging, GTM and growth loops. "
                "You are practical and numbers-driven, but you explain clearly enough that "
                "a small team can execute without confusion."
            ),
            llm=llm,
        )


class COOAgent(FunctionalAgent):
    """
    Chief Operating Officer / Ops & Customer Experience:
    - Owns operations, SLAs, staffing, service quality, CX, NPS.
    """

    @staticmethod
    def create(llm: LLMClient) -> "COOAgent":
        return COOAgent(
            name="COO Agent",
            role="Chief Operating Officer",
            system_prompt=(
                "You are the Chief Operating Officer (COO). "
                "You own operations, delivery, service quality, SLAs, staffing, and "
                "customer experience. You turn strategy into playbooks, processes, KPIs "
                "and daily execution routines. You are concrete: who does what, by when, "
                "in which system."
            ),
            llm=llm,
        )


class CTOAgent(FunctionalAgent):
    """
    Chief Technology Officer / Product & Tech:
    - Owns product roadmap, architecture, AI, reliability, velocity.
    """

    @staticmethod
    def create(llm: LLMClient) -> "CTOAgent":
        return CTOAgent(
            name="CTO Agent",
            role="Chief Technology Officer",
            system_prompt=(
                "You are the Chief Technology Officer (CTO) and Head of Product. "
                "You own product strategy, technical architecture, AI systems, reliability, "
                "and developer velocity. You think in terms of user impact, complexity, "
                "and time-to-value. You propose lean, high-impact changes, not giant rewrites."
            ),
            llm=llm,
        )