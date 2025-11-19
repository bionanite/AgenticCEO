"""
kpi_engine.py

Multi-KPI monitoring engine.

- Define KPIThresholds per company (min/max, unit).
- Record KPI readings and store them via MemoryEngine.
- Trigger Agentic CEO decisions when out-of-range.
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, Optional, Any, List

from pydantic import BaseModel, Field

from agentic_ceo import AgenticCEO, CEOEvent


class KPIThreshold(BaseModel):
    name: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: str = ""


class KPIEngine(BaseModel):
    """
    Holds KPI thresholds and checks readings against them.
    """

    thresholds: Dict[str, KPIThreshold] = Field(default_factory=dict)

    def register_threshold(self, threshold: KPIThreshold) -> None:
        self.thresholds[threshold.name] = threshold

    def register_many(self, thresholds: List[KPIThreshold]) -> None:
        for t in thresholds:
            self.register_threshold(t)

    def record_kpi(
        self,
        ceo: AgenticCEO,
        metric_name: str,
        value: float,
        unit: str,
        source: str = "manual",
    ) -> Dict[str, Any]:
        """
        Store a KPI reading in memory and, if out of range, trigger an event-driven CEO decision.

        Returns:
            {
              "reading": {...},
              "alerts_triggered": int,
              "alert_decisions": [str, ...]
            }
        """
        timestamp = dt.datetime.utcnow()
        reading = {
            "timestamp": timestamp.isoformat(),
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
            "source": source,
        }

        # Store KPI in memory correctly using metadata dict
        ceo.memory.record_kpi(
            metric_name,
            value,
            metadata={
                "unit": unit,
                "source": source,
                "timestamp": timestamp.isoformat(),
            },
        )

        threshold = self.thresholds.get(metric_name)
        if not threshold:
            return {
                "reading": reading,
                "alerts_triggered": 0,
                "alert_decisions": [],
            }

        messages: List[str] = []
        out_of_range = False

        if threshold.min_value is not None and value < threshold.min_value:
            messages.append(
                f"KPI {metric_name} out of range: value {value} is below minimum {threshold.min_value}"
            )
            out_of_range = True

        if threshold.max_value is not None and value > threshold.max_value:
            messages.append(
                f"KPI {metric_name} out of range: value {value} is above maximum {threshold.max_value}"
            )
            out_of_range = True

        alert_decisions: List[str] = []

        if out_of_range:
            # Build a KPI alert event and let the CEO decide what to do
            reason = " ".join(messages)
            event_payload = {
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "reason": reason,
                "timestamp": timestamp.isoformat(),
            }
            event = CEOEvent(type="kpi_alert", payload=event_payload)

            decision = ceo.ingest_event(event)
            alert_decisions.append(
                f"KPI Alert: {metric_name} value {value}. {reason}\n{decision}"
            )

        return {
            "reading": reading,
            "alerts_triggered": len(alert_decisions),
            "alert_decisions": alert_decisions,
        }