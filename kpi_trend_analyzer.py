"""
kpi_trend_analyzer.py

KPI Trend Analysis Module

Tracks KPI history over time and detects trends before thresholds are breached.
Enables proactive task generation based on declining trends.
"""

from __future__ import annotations

import os
import json
import datetime as dt
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class KPITrend:
    """Represents a trend analysis for a KPI."""
    metric_name: str
    current_value: float
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_strength: float  # -1.0 to 1.0 (negative = declining, positive = improving)
    days_analyzed: int
    moving_avg_7d: Optional[float]
    moving_avg_30d: Optional[float]
    rate_of_change: float  # % change per day
    projected_value_7d: Optional[float]  # Projected value in 7 days
    threshold_breach_risk: str  # "low", "medium", "high", "critical"
    recommendation: Optional[str]  # Suggested action


class KPITrendAnalyzer:
    """
    Analyzes KPI trends over time to detect problems before thresholds are breached.
    
    Features:
    - Tracks KPI history (7-day, 30-day moving averages)
    - Detects declining trends early
    - Projects future values
    - Calculates breach risk
    - Provides recommendations
    """
    
    def __init__(self, storage_dir: str = ".agentic_state"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self._kpi_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._load_history()
    
    def _get_history_file(self) -> str:
        """Get the filepath for KPI history storage."""
        return os.path.join(self.storage_dir, "kpi_history.json")
    
    def _load_history(self) -> None:
        """Load KPI history from disk."""
        history_file = self._get_history_file()
        if not os.path.exists(history_file):
            return
        
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._kpi_history = {k: v for k, v in data.items()}
        except Exception:
            self._kpi_history = defaultdict(list)
    
    def _save_history(self) -> None:
        """Save KPI history to disk."""
        history_file = self._get_history_file()
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self._kpi_history, f, indent=2, default=str)
        except Exception:
            pass  # Don't crash if save fails
    
    def record_kpi(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        timestamp: Optional[dt.datetime] = None,
    ) -> None:
        """
        Record a KPI reading for trend analysis.
        
        Args:
            metric_name: Name of the KPI
            value: Current value
            unit: Unit of measurement
            timestamp: When the reading was taken (defaults to now)
        """
        if timestamp is None:
            timestamp = dt.datetime.utcnow()
        
        entry = {
            "timestamp": timestamp.isoformat(),
            "value": value,
            "unit": unit,
        }
        
        self._kpi_history[metric_name].append(entry)
        
        # Keep only last 90 days of history to avoid unbounded growth
        cutoff_date = timestamp - dt.timedelta(days=90)
        self._kpi_history[metric_name] = [
            e for e in self._kpi_history[metric_name]
            if dt.datetime.fromisoformat(e["timestamp"]) >= cutoff_date
        ]
        
        self._save_history()
    
    def get_recent_readings(
        self,
        metric_name: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get recent KPI readings for a metric.
        
        Args:
            metric_name: Name of the KPI
            days: Number of days to look back
        
        Returns:
            List of readings sorted by timestamp (oldest first)
        """
        if metric_name not in self._kpi_history:
            return []
        
        cutoff_date = dt.datetime.utcnow() - dt.timedelta(days=days)
        readings = [
            e for e in self._kpi_history[metric_name]
            if dt.datetime.fromisoformat(e["timestamp"]) >= cutoff_date
        ]
        
        # Sort by timestamp
        readings.sort(key=lambda x: x["timestamp"])
        return readings
    
    def calculate_moving_average(
        self,
        readings: List[Dict[str, Any]],
        days: int,
    ) -> Optional[float]:
        """
        Calculate moving average for the last N days.
        
        Args:
            readings: List of KPI readings
            days: Number of days to average
        
        Returns:
            Moving average or None if insufficient data
        """
        if not readings:
            return None
        
        cutoff_date = dt.datetime.utcnow() - dt.timedelta(days=days)
        recent = [
            e for e in readings
            if dt.datetime.fromisoformat(e["timestamp"]) >= cutoff_date
        ]
        
        if len(recent) < 2:  # Need at least 2 readings
            return None
        
        values = [e["value"] for e in recent]
        return sum(values) / len(values)
    
    def analyze_trend(
        self,
        metric_name: str,
        threshold_min: Optional[float] = None,
        threshold_max: Optional[float] = None,
    ) -> Optional[KPITrend]:
        """
        Analyze trend for a KPI and detect if it's declining toward threshold.
        
        Args:
            metric_name: Name of the KPI
            threshold_min: Minimum threshold (if value goes below, alert)
            threshold_max: Maximum threshold (if value goes above, alert)
        
        Returns:
            KPITrend object or None if insufficient data
        """
        readings = self.get_recent_readings(metric_name, days=30)
        
        if len(readings) < 3:  # Need at least 3 readings for trend analysis
            return None
        
        # Get current value (most recent)
        current_value = readings[-1]["value"]
        
        # Calculate moving averages
        moving_avg_7d = self.calculate_moving_average(readings, days=7)
        moving_avg_30d = self.calculate_moving_average(readings, days=30)
        
        # Calculate rate of change (linear regression on recent values)
        recent_values = [e["value"] for e in readings[-7:]]  # Last 7 readings
        if len(recent_values) >= 2:
            # Simple linear regression slope
            x = list(range(len(recent_values)))
            n = len(recent_values)
            sum_x = sum(x)
            sum_y = sum(recent_values)
            sum_xy = sum(x[i] * recent_values[i] for i in range(n))
            sum_x2 = sum(x[i] * x[i] for i in range(n))
            
            if n * sum_x2 - sum_x * sum_x != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                # Convert to % change per day (relative to current value)
                if current_value != 0:
                    rate_of_change = (slope / current_value) * 100
                else:
                    rate_of_change = 0.0
            else:
                rate_of_change = 0.0
        else:
            rate_of_change = 0.0
        
        # Determine trend direction
        if moving_avg_7d is not None and moving_avg_30d is not None:
            if moving_avg_7d > moving_avg_30d * 1.02:  # 2% threshold
                trend_direction = "increasing"
                trend_strength = min(1.0, abs(rate_of_change) / 10.0)  # Normalize
            elif moving_avg_7d < moving_avg_30d * 0.98:
                trend_direction = "decreasing"
                trend_strength = -min(1.0, abs(rate_of_change) / 10.0)  # Negative for declining
            else:
                trend_direction = "stable"
                trend_strength = 0.0
        else:
            trend_direction = "stable"
            trend_strength = 0.0
        
        # Project future value (7 days ahead)
        if rate_of_change != 0 and current_value != 0:
            projected_value_7d = current_value * (1 + (rate_of_change / 100) * 7)
        else:
            projected_value_7d = current_value
        
        # Calculate breach risk
        threshold_breach_risk = "low"
        recommendation = None
        
        if threshold_min is not None:
            if current_value < threshold_min:
                threshold_breach_risk = "critical"
                recommendation = f"{metric_name} is currently below minimum threshold ({threshold_min}). Immediate action required."
            elif projected_value_7d < threshold_min:
                threshold_breach_risk = "high"
                recommendation = f"{metric_name} is declining and projected to breach minimum threshold ({threshold_min}) within 7 days. Proactive action recommended."
            elif trend_direction == "decreasing" and current_value < threshold_min * 1.1:  # Within 10% of threshold
                threshold_breach_risk = "medium"
                recommendation = f"{metric_name} is declining and approaching minimum threshold. Consider preventive measures."
        
        if threshold_max is not None:
            if current_value > threshold_max:
                threshold_breach_risk = "critical"
                recommendation = f"{metric_name} is currently above maximum threshold ({threshold_max}). Immediate action required."
            elif projected_value_7d > threshold_max:
                threshold_breach_risk = "high"
                recommendation = f"{metric_name} is increasing and projected to breach maximum threshold ({threshold_max}) within 7 days. Proactive action recommended."
            elif trend_direction == "increasing" and current_value > threshold_max * 0.9:  # Within 10% of threshold
                threshold_breach_risk = "medium"
                recommendation = f"{metric_name} is increasing and approaching maximum threshold. Consider preventive measures."
        
        return KPITrend(
            metric_name=metric_name,
            current_value=current_value,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            days_analyzed=len(readings),
            moving_avg_7d=moving_avg_7d,
            moving_avg_30d=moving_avg_30d,
            rate_of_change=rate_of_change,
            projected_value_7d=projected_value_7d,
            threshold_breach_risk=threshold_breach_risk,
            recommendation=recommendation,
        )
    
    def get_trends_for_all_kpis(
        self,
        kpi_thresholds: Dict[str, Dict[str, Optional[float]]],
    ) -> List[KPITrend]:
        """
        Analyze trends for all tracked KPIs.
        
        Args:
            kpi_thresholds: Dict mapping metric_name to {"min": value, "max": value}
        
        Returns:
            List of KPITrend objects
        """
        trends = []
        
        for metric_name, thresholds in kpi_thresholds.items():
            trend = self.analyze_trend(
                metric_name=metric_name,
                threshold_min=thresholds.get("min"),
                threshold_max=thresholds.get("max"),
            )
            if trend:
                trends.append(trend)
        
        return trends
    
    def get_proactive_recommendations(
        self,
        kpi_thresholds: Dict[str, Dict[str, Optional[float]]],
    ) -> List[str]:
        """
        Get proactive task recommendations based on KPI trends.
        
        Args:
            kpi_thresholds: Dict mapping metric_name to {"min": value, "max": value}
        
        Returns:
            List of recommendation strings for generating preventive tasks
        """
        trends = self.get_trends_for_all_kpis(kpi_thresholds)
        recommendations = []
        
        for trend in trends:
            if trend.threshold_breach_risk in ("medium", "high", "critical"):
                if trend.recommendation:
                    recommendations.append(trend.recommendation)
        
        return recommendations

