# memory_engine.py
from __future__ import annotations

import json
import os
import datetime as dt
from typing import Dict, Any


class MemoryEngine:
    """
    Lightweight JSON memory store with:
    - decisions
    - events
    - tool calls
    - reflections
    - KPI updates
    - token usage (for LLM cost/usage tracking)
    """

    def __init__(self, filename: str = "ceo_memory.json"):
        self.filename = filename
        self._memory = self._load()

    # ----------------- Internal helpers -----------------

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        with open(self.filename, "w") as f:
            json.dump(self._memory, f, indent=2)

    # ----------------- Recording functions -----------------

    def record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "type": event_type,
            "payload": payload,
        }
        self._memory.setdefault("events", []).append(entry)
        self._save()

    def record_decision(self, text: str, context: Dict[str, Any]) -> None:
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "text": text,
            "context": context,
        }
        self._memory.setdefault("decisions", []).append(entry)
        self._save()

    def record_tool_call(
        self,
        tool_name: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "tool": tool_name,
            "payload": payload,
            "result": result,
        }
        self._memory.setdefault("tool_calls", []).append(entry)
        self._save()

    def record_reflection(self, text: str) -> None:
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "text": text,
        }
        self._memory.setdefault("reflections", []).append(entry)
        self._save()

    def record_kpi(
        self,
        metric_name: str,
        value: float,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Store KPI readings so we can summarise them in daily reflection.
        """
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "metric_name": metric_name,
            "value": value,
            "metadata": metadata or {},
        }
        self._memory.setdefault("kpis", []).append(entry)
        self._save()

    def record_token_usage(self, stage: str, usage: Dict[str, int]) -> None:
        """
        Track LLM token usage for each call (e.g. daily_plan, kpi_alert, etc.).
        """
        entry = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "stage": stage,
            "usage": usage,
        }
        self._memory.setdefault("token_usage", []).append(entry)
        self._save()

    # ----------------- Daily summary -----------------

    def summarize_day(self, date: dt.date) -> str:
        decisions = self._memory.get("decisions", [])
        tool_calls = self._memory.get("tool_calls", [])
        events = self._memory.get("events", [])
        kpis = self._memory.get("kpis", [])
        token_usage = self._memory.get("token_usage", [])

        total_tokens = sum(
            entry["usage"].get("total_tokens", 0) for entry in token_usage
        )
        llm_calls = len(token_usage)

        return (
            f"Reflection for {date}:\n"
            f"- Decisions made: {len(decisions)}\n"
            f"- Tool calls executed: {len(tool_calls)}\n"
            f"- KPI updates recorded: {len(kpis)}\n"
            f"- Events processed: {len(events)}\n"
            f"- LLM calls today: {llm_calls}\n"
            f"- Total tokens used today: {total_tokens}\n"
        )