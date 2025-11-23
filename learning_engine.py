"""
learning_engine.py

Learning System Module

Assesses task result quality, tracks success patterns, and optimizes routing.
Enables the system to learn from results and improve over time.
"""

from __future__ import annotations

import os
import json
import datetime as dt
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class TaskQualityScore:
    """Quality assessment for a completed task."""
    task_id: str
    task_title: str
    executor_type: str  # "BaseVirtualEmployee", "CROAgent", "COOAgent", "CTOAgent", "CEO"
    executor_role: Optional[str]  # Role ID or agent name
    quality_score: float  # 1-10
    quality_reason: str  # Why this score was assigned
    timestamp: str
    task_area: str
    task_priority: int


@dataclass
class SuccessPattern:
    """Pattern of successful task execution."""
    executor_type: str
    executor_role: Optional[str]
    task_area: str
    success_rate: float  # 0.0 to 1.0
    avg_quality_score: float
    total_tasks: int
    successful_tasks: int


class LearningEngine:
    """
    Learns from task execution results to optimize future performance.
    
    Features:
    - Quality assessment of task results (LLM-based scoring)
    - Success pattern tracking per executor/role/area
    - Routing optimization recommendations
    - Performance metrics storage
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        storage_dir: str = ".agentic_state",
    ):
        self.llm_client = llm_client
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self._quality_scores: List[TaskQualityScore] = []
        self._success_patterns: Dict[str, SuccessPattern] = {}
        self._load_data()
    
    def _get_data_file(self) -> str:
        """Get the filepath for learning data storage."""
        return os.path.join(self.storage_dir, "learning_data.json")
    
    def _load_data(self) -> None:
        """Load learning data from disk."""
        data_file = self._get_data_file()
        if not os.path.exists(data_file):
            return
        
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Load quality scores
                self._quality_scores = [
                    TaskQualityScore(**score) for score in data.get("quality_scores", [])
                ]
                # Load success patterns
                patterns = data.get("success_patterns", {})
                self._success_patterns = {
                    k: SuccessPattern(**v) for k, v in patterns.items()
                }
        except Exception:
            self._quality_scores = []
            self._success_patterns = {}
    
    def _save_data(self) -> None:
        """Save learning data to disk."""
        data_file = self._get_data_file()
        try:
            data = {
                "quality_scores": [asdict(score) for score in self._quality_scores],
                "success_patterns": {
                    k: asdict(v) for k, v in self._success_patterns.items()
                },
                "last_updated": dt.datetime.utcnow().isoformat(),
            }
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            pass  # Don't crash if save fails
    
    async def assess_task_quality(
        self,
        task_id: str,
        task_title: str,
        task_description: str,
        task_result: str,
        executor_type: str,
        executor_role: Optional[str] = None,
        task_area: str = "general",
        task_priority: int = 3,
    ) -> TaskQualityScore:
        """
        Assess the quality of a completed task result using LLM.
        
        Args:
            task_id: Task identifier
            task_title: Task title
            task_description: Task description
            task_result: The actual output/work product from task execution
            executor_type: Type of executor (BaseVirtualEmployee, CROAgent, etc.)
            executor_role: Role ID or agent name
            task_area: Task area (growth, ops, product, etc.)
            task_priority: Task priority (1-5)
        
        Returns:
            TaskQualityScore object with quality assessment
        """
        if not self.llm_client:
            # If no LLM client, assign default score
            quality_score = 7.0
            quality_reason = "No LLM client available for quality assessment"
        else:
            # Use LLM to assess quality
            system_prompt = (
                "You are a quality assessor for task execution results.\n"
                "Rate the quality of the task output on a scale of 1-10, where:\n"
                "1-3: Poor (incomplete, irrelevant, or low value)\n"
                "4-6: Adequate (meets basic requirements but lacks depth)\n"
                "7-8: Good (thorough, relevant, adds value)\n"
                "9-10: Excellent (exceptional quality, exceeds expectations)\n\n"
                "Consider:\n"
                "- Completeness: Does it fully address the task?\n"
                "- Relevance: Is it aligned with the task requirements?\n"
                "- Value: Does it provide actionable insights or deliverables?\n"
                "- Clarity: Is it well-structured and understandable?\n"
                "- Depth: Does it go beyond surface-level responses?\n\n"
                "Respond with ONLY a JSON object:\n"
                '{"score": <number 1-10>, "reason": "<brief explanation>"}'
            )
            
            user_prompt = (
                f"Task Title: {task_title}\n"
                f"Task Description: {task_description}\n"
                f"Task Area: {task_area}\n"
                f"Priority: P{task_priority}\n\n"
                f"Task Result:\n{task_result}\n\n"
                "Assess the quality of this task result."
            )
            
            try:
                if hasattr(self.llm_client, "acomplete"):
                    response = await self.llm_client.acomplete(system_prompt, user_prompt)
                else:
                    response = self.llm_client.complete(system_prompt, user_prompt)
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{[^}]+\}', response)
                if json_match:
                    import json as json_lib
                    assessment = json_lib.loads(json_match.group())
                    quality_score = float(assessment.get("score", 7.0))
                    quality_reason = assessment.get("reason", "Assessed by LLM")
                else:
                    # Fallback: try to extract number
                    score_match = re.search(r'"score":\s*(\d+(?:\.\d+)?)', response)
                    if score_match:
                        quality_score = float(score_match.group(1))
                    else:
                        quality_score = 7.0
                    quality_reason = response[:200] if response else "LLM assessment"
            except Exception as e:
                quality_score = 7.0
                quality_reason = f"Assessment error: {e}"
        
        score = TaskQualityScore(
            task_id=task_id,
            task_title=task_title,
            executor_type=executor_type,
            executor_role=executor_role,
            quality_score=quality_score,
            quality_reason=quality_reason,
            timestamp=dt.datetime.utcnow().isoformat(),
            task_area=task_area,
            task_priority=task_priority,
        )
        
        self._quality_scores.append(score)
        self._update_success_patterns(score)
        self._save_data()
        
        return score
    
    def _update_success_patterns(self, score: TaskQualityScore) -> None:
        """Update success patterns based on new quality score."""
        # Consider score >= 7 as successful
        is_successful = score.quality_score >= 7.0
        
        # Create pattern key: executor_type:executor_role:task_area
        pattern_key = f"{score.executor_type}:{score.executor_role or 'none'}:{score.task_area}"
        
        if pattern_key not in self._success_patterns:
            self._success_patterns[pattern_key] = SuccessPattern(
                executor_type=score.executor_type,
                executor_role=score.executor_role,
                task_area=score.task_area,
                success_rate=0.0,
                avg_quality_score=0.0,
                total_tasks=0,
                successful_tasks=0,
            )
        
        pattern = self._success_patterns[pattern_key]
        pattern.total_tasks += 1
        if is_successful:
            pattern.successful_tasks += 1
        
        # Recalculate metrics
        pattern.success_rate = pattern.successful_tasks / pattern.total_tasks if pattern.total_tasks > 0 else 0.0
        
        # Calculate average quality score for this pattern
        pattern_scores = [
            s.quality_score for s in self._quality_scores
            if s.executor_type == score.executor_type
            and s.executor_role == score.executor_role
            and s.task_area == score.task_area
        ]
        pattern.avg_quality_score = sum(pattern_scores) / len(pattern_scores) if pattern_scores else 0.0
    
    def get_best_executor_for_task(
        self,
        task_area: str,
        executor_options: List[Tuple[str, Optional[str]]],
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Recommend the best executor for a task based on historical success.
        
        Args:
            task_area: Area of the task (growth, ops, product, etc.)
            executor_options: List of (executor_type, executor_role) tuples
        
        Returns:
            Best (executor_type, executor_role) tuple or None
        """
        if not executor_options:
            return None
        
        best_option = None
        best_score = 0.0
        
        for executor_type, executor_role in executor_options:
            pattern_key = f"{executor_type}:{executor_role or 'none'}:{task_area}"
            pattern = self._success_patterns.get(pattern_key)
            
            if pattern:
                # Score = success_rate * avg_quality_score / 10
                # This gives weight to both success rate and quality
                score = pattern.success_rate * (pattern.avg_quality_score / 10.0)
            else:
                # No history, use default score
                score = 0.5  # Neutral score for unknown patterns
        
            if score > best_score:
                best_score = score
                best_option = (executor_type, executor_role)
        
        return best_option
    
    def get_executor_performance(
        self,
        executor_type: str,
        executor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get performance metrics for an executor.
        
        Returns:
            Dict with success_rate, avg_quality_score, total_tasks, etc.
        """
        # Filter patterns for this executor
        relevant_patterns = [
            p for k, p in self._success_patterns.items()
            if p.executor_type == executor_type
            and p.executor_role == executor_role
        ]
        
        if not relevant_patterns:
            return {
                "success_rate": 0.0,
                "avg_quality_score": 0.0,
                "total_tasks": 0,
                "successful_tasks": 0,
            }
        
        # Aggregate across all task areas
        total_tasks = sum(p.total_tasks for p in relevant_patterns)
        successful_tasks = sum(p.successful_tasks for p in relevant_patterns)
        success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.0
        
        # Weighted average quality score
        weighted_sum = sum(p.avg_quality_score * p.total_tasks for p in relevant_patterns)
        avg_quality_score = weighted_sum / total_tasks if total_tasks > 0 else 0.0
        
        return {
            "success_rate": success_rate,
            "avg_quality_score": avg_quality_score,
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "by_area": {
                p.task_area: {
                    "success_rate": p.success_rate,
                    "avg_quality_score": p.avg_quality_score,
                    "total_tasks": p.total_tasks,
                }
                for p in relevant_patterns
            },
        }
    
    def get_all_patterns(self) -> List[SuccessPattern]:
        """Get all success patterns."""
        return list(self._success_patterns.values())
    
    def get_recent_quality_scores(self, limit: int = 50) -> List[TaskQualityScore]:
        """Get recent quality scores."""
        return self._quality_scores[-limit:]

