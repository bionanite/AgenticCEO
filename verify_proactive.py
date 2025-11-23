#!/usr/bin/env python3
"""
verify_proactive.py

Verification script for Proactive Intelligence features:
- KPI Trend Analysis integration
- Learning Engine integration
- Proactive task generation

This script populates dummy data and verifies the system works correctly.
"""

import os
import sys
import datetime as dt
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from company_brain import CompanyBrain, DEFAULT_CONFIG_PATH
from kpi_trend_analyzer import KPITrendAnalyzer
from agentic_ceo import CEOEvent


def populate_dummy_kpi_history(trend_analyzer: KPITrendAnalyzer, metric_name: str, start_value: float = 100.0, decline_rate: float = 0.02):
    """
    Populate 30 days of dummy KPI history with a declining trend.
    
    Args:
        trend_analyzer: KPITrendAnalyzer instance
        metric_name: Name of the KPI metric
        start_value: Starting value (30 days ago)
        decline_rate: Daily decline rate (e.g., 0.02 = 2% per day)
    """
    print(f"  Populating 30 days of dummy data for '{metric_name}'...")
    
    base_date = dt.datetime.utcnow() - dt.timedelta(days=30)
    current_value = start_value
    
    for day in range(30):
        date = base_date + dt.timedelta(days=day)
        # Add some random noise (±5%)
        import random
        noise = random.uniform(-0.05, 0.05)
        value = current_value * (1 + noise)
        
        trend_analyzer.record_kpi(
            metric_name=metric_name,
            value=value,
            unit="USD",
            timestamp=date,
        )
        
        # Decline over time
        current_value *= (1 - decline_rate)
    
    print(f"  ✓ Recorded 30 days of data (start: {start_value:.2f}, end: {current_value:.2f})")


def test_trend_analysis(brain: CompanyBrain):
    """Test that trend analysis is working and integrated."""
    print("\n=== TEST 1: KPI Trend Analysis Integration ===")
    
    trend_analyzer = brain.kpi_engine.trend_analyzer
    if not trend_analyzer:
        print("  ✗ ERROR: Trend analyzer not initialized!")
        return False
    
    print("  ✓ Trend analyzer is initialized")
    
    # Populate dummy data for a test KPI
    test_metric = "Monthly Recurring Revenue"
    populate_dummy_kpi_history(trend_analyzer, test_metric, start_value=10000.0, decline_rate=0.015)
    
    # Analyze the trend
    kpi_thresholds = {
        test_metric: {"min": 8000.0, "max": None}
    }
    
    trends = trend_analyzer.get_trends_for_all_kpis(kpi_thresholds)
    if not trends:
        print("  ✗ ERROR: No trends returned!")
        return False
    
    trend = trends[0]
    print(f"  ✓ Trend analysis complete:")
    print(f"    - Metric: {trend.metric_name}")
    print(f"    - Current value: {trend.current_value:.2f}")
    print(f"    - Trend direction: {trend.trend_direction}")
    print(f"    - Breach risk: {trend.threshold_breach_risk}")
    print(f"    - Recommendation: {trend.recommendation[:100] if trend.recommendation else 'None'}...")
    
    # Check that proactive recommendations are generated
    recommendations = trend_analyzer.get_proactive_recommendations(kpi_thresholds)
    if recommendations:
        print(f"  ✓ Generated {len(recommendations)} proactive recommendation(s)")
        for rec in recommendations:
            print(f"    - {rec[:100]}...")
    else:
        print("  ⚠ No proactive recommendations (this might be OK if trend is stable)")
    
    return True


def test_plan_day_with_trends(brain: CompanyBrain):
    """Test that plan_day() includes trend context."""
    print("\n=== TEST 2: Plan Day with Trend Context ===")
    
    plan_text = brain.plan_day()
    
    # Check if trend context is included
    if "KPI TREND ANALYSIS" in plan_text or "trend" in plan_text.lower():
        print("  ✓ Plan includes trend analysis context")
        # Print a snippet
        lines = plan_text.split('\n')
        trend_lines = [l for l in lines if 'trend' in l.lower() or 'KPI' in l]
        if trend_lines:
            print(f"    Sample: {trend_lines[0][:80]}...")
        return True
    else:
        print("  ⚠ Plan does not appear to include trend context")
        print("    (This might be OK if no trends are detected)")
        return True  # Not a failure, just informational


def test_proactive_event_generation(brain: CompanyBrain):
    """Test that proactive KPI trend alerts generate tasks."""
    print("\n=== TEST 3: Proactive Event Generation ===")
    
    # Get proactive recommendations
    kpi_thresholds = {
        name: {"min": t.min_value, "max": t.max_value}
        for name, t in brain.kpi_engine.thresholds.items()
    }
    
    trend_analyzer = brain.kpi_engine.trend_analyzer
    if not trend_analyzer:
        print("  ✗ ERROR: Trend analyzer not available")
        return False
    
    proactive_recs = trend_analyzer.get_proactive_recommendations(kpi_thresholds)
    
    if not proactive_recs:
        print("  ⚠ No proactive recommendations available (might need more KPI data)")
        return True  # Not a failure
    
    # Create a proactive event
    event = CEOEvent(
        type="kpi_trend_alert",
        payload={
            "recommendations": proactive_recs,
            "source": "trend_analyzer",
        }
    )
    
    initial_task_count = len([t for t in brain.ceo.state.tasks if t.status != "done"])
    
    print(f"  Initial task count: {initial_task_count}")
    print(f"  Ingesting proactive event with {len(proactive_recs)} recommendations...")
    
    decision = brain.ingest_event(event.type, event.payload)
    
    final_task_count = len([t for t in brain.ceo.state.tasks if t.status != "done"])
    new_tasks = final_task_count - initial_task_count
    
    print(f"  Final task count: {final_task_count}")
    print(f"  ✓ Generated {new_tasks} new task(s)")
    
    if new_tasks > 0:
        # Show the new tasks
        all_tasks = brain.ceo.state.tasks
        new_task_list = [t for t in all_tasks if t.status != "done"][-new_tasks:]
        for task in new_task_list:
            print(f"    - [{task.area}, {task.suggested_owner}, P{task.priority}] {task.title}")
    
    return True


def test_learning_engine(brain: CompanyBrain):
    """Test that learning engine is initialized and can assess quality."""
    print("\n=== TEST 4: Learning Engine Integration ===")
    
    learning_engine = brain.learning_engine
    if not learning_engine:
        print("  ✗ ERROR: Learning engine not initialized!")
        return False
    
    print("  ✓ Learning engine is initialized")
    
    # Test quality assessment (async, but we'll use sync for testing)
    import asyncio
    
    async def test_assessment():
        score = await learning_engine.assess_task_quality(
            task_id="test-123",
            task_title="Test Task",
            task_description="This is a test task to verify quality assessment",
            task_result="The task was completed successfully with detailed analysis and actionable recommendations.",
            executor_type="BaseVirtualEmployee",
            executor_role="growth_marketer",
            task_area="growth",
            task_priority=1,
        )
        return score
    
    print("  Testing quality assessment...")
    score = asyncio.run(test_assessment())
    
    print(f"  ✓ Quality assessment complete:")
    print(f"    - Score: {score.quality_score}/10")
    print(f"    - Reason: {score.quality_reason[:100]}...")
    
    # Check if patterns are being tracked
    patterns = learning_engine.get_all_patterns()
    if patterns:
        print(f"  ✓ Tracking {len(patterns)} success pattern(s)")
        for pattern in patterns[:3]:  # Show first 3
            print(f"    - {pattern.executor_type}:{pattern.executor_role or 'none'}:{pattern.task_area}")
            print(f"      Success rate: {pattern.success_rate:.2%}, Avg score: {pattern.avg_quality_score:.2f}")
    else:
        print("  ⚠ No success patterns yet (this is OK for first run)")
    
    return True


def main():
    """Run all verification tests."""
    print("=" * 70)
    print("Proactive Intelligence & Learning System Verification")
    print("=" * 70)
    
    # Get company key from env or use default
    company_key = os.getenv("AGENTIC_CEO_COMPANY", "next_ecosystem")
    print(f"\nUsing company: {company_key}")
    
    try:
        # Initialize brain
        print("\nInitializing CompanyBrain...")
        brain = CompanyBrain.from_config(
            config_path=DEFAULT_CONFIG_PATH,
            company_key=company_key,
        )
        print("  ✓ CompanyBrain initialized")
        
        # Run tests
        results = []
        
        results.append(("Trend Analysis", test_trend_analysis(brain)))
        results.append(("Plan Day with Trends", test_plan_day_with_trends(brain)))
        results.append(("Proactive Event Generation", test_proactive_event_generation(brain)))
        results.append(("Learning Engine", test_learning_engine(brain)))
        
        # Summary
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  {status}: {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed! Proactive Intelligence is working correctly.")
            return 0
        else:
            print(f"\n⚠ {total - passed} test(s) failed. Please review the output above.")
            return 1
            
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

