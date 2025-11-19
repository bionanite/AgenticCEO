# kpi_engine.py
from __future__ import annotations

import datetime as dt
from typing import Dict, Any, List, Optional

from pydantic import BaseModel


class KPIThreshold(BaseModel):
    metric_name: str
    min_value: Optional[float] = None  # e.g. MRR must be >= X
    max_value: Optional[float] = None  # e.g. churn % must be <= Y
    direction: str = "good_high"  # "good_high" or "good_low"


class KPIReading(BaseModel):
    timestamp: str
    metric_name: str
    value: float
    unit: str = ""
    source: str = ""


class KPIAlert(BaseModel):
    metric_name: str
    value: float
    threshold: KPIThreshold
    message: str
    severity: str = "warning"  # or "critical"


class KPIEngine:
    """
    Tracks KPIs, evaluates thresholds, and emits alerts.
    """

    def __init__(self, thresholds: Optional[List[KPIThreshold]] = None) -> None:
        self.thresholds: Dict[str, KPIThreshold] = {
            t.metric_name: t for t in (thresholds or [])
        }
        self.readings: List[KPIReading] = []

    def _now_iso(self) -> str:
        return dt.datetime.utcnow().isoformat()

    def set_threshold(self, threshold: KPIThreshold) -> None:
        self.thresholds[threshold.metric_name] = threshold

    def record_kpi(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        source: str = "",
    ) -> KPIReading:
        reading = KPIReading(
            timestamp=self._now_iso(),
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=source,
        )
        self.readings.append(reading)
        return reading

    def evaluate_alerts(self, reading: KPIReading) -> List[KPIAlert]:
        alerts: List[KPIAlert] = []
        th = self.thresholds.get(reading.metric_name)
        if not th:
            return alerts

        triggered = False
        msg_parts = []

        if th.min_value is not None and reading.value < th.min_value:
            triggered = True
            msg_parts.append(
                f"value {reading.value} is below minimum {th.min_value}"
            )

        if th.max_value is not None and reading.value > th.max_value:
            triggered = True
            msg_parts.append(
                f"value {reading.value} is above maximum {th.max_value}"
            )

        if not triggered:
            return alerts

        message = f"KPI {reading.metric_name} out of range: " + "; ".join(msg_parts)
        alerts.append(
            KPIAlert(
                metric_name=reading.metric_name,
                value=reading.value,
                threshold=th,
                message=message,
                severity="critical",
            )
        )
        return alerts