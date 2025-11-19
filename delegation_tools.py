# delegation_tools.py
from __future__ import annotations

from typing import Dict, Any

from agents import CROAgent, COOAgent, CTOAgent


class CRODelegationTool:
    """
    Tool wrapper around the CROAgent.
    The CEO can call this via suggested_tool="delegate_cro".
    """
    name: str = "delegate_cro"
    description: str = "Ask the CRO agent to design a revenue / MRR / sales strategy."

    def __init__(self, cro: CROAgent) -> None:
        self.cro = cro

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instruction = payload.get("instruction") or payload.get("message") or ""
        context = payload.get("context", "")
        plan = self.cro.think(instruction, context)
        return {
            "ok": True,
            "role": self.cro.role,
            "instruction": instruction,
            "plan": plan,
        }


class COODelegationTool:
    """
    Tool wrapper around the COOAgent.
    """
    name: str = "delegate_coo"
    description: str = "Ask the COO agent to design an operations / efficiency / SLA plan."

    def __init__(self, coo: COOAgent) -> None:
        self.coo = coo

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instruction = payload.get("instruction") or payload.get("message") or ""
        context = payload.get("context", "")
        plan = self.coo.think(instruction, context)
        return {
            "ok": True,
            "role": self.coo.role,
            "instruction": instruction,
            "plan": plan,
        }


class CTODelegationTool:
    """
    Tool wrapper around the CTOAgent.
    """
    name: str = "delegate_cto"
    description: str = "Ask the CTO agent to design a technical / AI / product roadmap."

    def __init__(self, cto: CTOAgent) -> None:
        self.cto = cto

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instruction = payload.get("instruction") or payload.get("message") or ""
        context = payload.get("context", "")
        plan = self.cto.think(instruction, context)
        return {
            "ok": True,
            "role": self.cto.role,
            "instruction": instruction,
            "plan": plan,
        }