# virtual_staff_manager.py
from __future__ import annotations

import os
import json
import uuid
import datetime as dt
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

try:
    # Optional – only used if you pass a MemoryEngine instance
    from memory_engine import MemoryEngine
except ImportError:
    MemoryEngine = None  # type: ignore


# ------------------------------------------------------------
# Model: VirtualEmployee
# ------------------------------------------------------------

@dataclass
class VirtualEmployee:
    """
    Represents a persistent "virtual staff" member – an AI employee
    that owns certain KPIs / domains and can be delegated tasks.

    This is intentionally generic so we can reuse it across companies:
    - Sales SDR
    - Virtual CMO
    - Virtual PM
    - Virtual Ops Manager
    - etc.
    """

    id: str
    role: str
    title: str
    owner_kpi: Optional[str]
    department: Optional[str]
    skills: List[str]
    tools: List[str]
    max_daily_tasks: int
    created_at: str  # ISO timestamp
    active: bool = True
    notes: str = ""
    performance_score: float = 1.0  # 1.0 = baseline, >1 = strong, <1 = weak

    # Lightweight runtime stats (not strictly required but useful)
    tasks_assigned_today: int = 0

    @classmethod
    def create(
        cls,
        role: str,
        title: Optional[str] = None,
        owner_kpi: Optional[str] = None,
        department: Optional[str] = None,
        skills: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        max_daily_tasks: int = 15,
        notes: str = "",
    ) -> "VirtualEmployee":
        """Factory that fills in sensible defaults."""
        ve_id = str(uuid.uuid4())
        created_at = dt.datetime.utcnow().isoformat()

        if title is None:
            title = role

        guessed = guess_profile_for_role(role)
        skills = skills or guessed["skills"]
        tools = tools or guessed["tools"]
        department = department or guessed["department"]

        return cls(
            id=ve_id,
            role=role,
            title=title,
            owner_kpi=owner_kpi,
            department=department,
            skills=skills,
            tools=tools,
            max_daily_tasks=max_daily_tasks,
            created_at=created_at,
            active=True,
            notes=notes,
            performance_score=1.0,
            tasks_assigned_today=0,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VirtualEmployee":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------
# Heuristic role → skills / department / tools
# ------------------------------------------------------------

def guess_profile_for_role(role: str) -> Dict[str, Any]:
    """
    Very simple heuristic mapper so you don't have to define
    tools / skills manually every time.

    We can expand this over time with your real org structure.
    """
    r = role.lower()

    # Defaults
    department = "General"
    skills: List[str] = ["analysis", "reporting"]
    tools: List[str] = ["log_tool"]

    if any(k in r for k in ["sales", "sdr", "closer", "bdm", "growth"]):
        department = "Sales"
        skills = ["outbound", "inbound", "crm", "follow-ups", "pipeline-management"]
        tools = ["email", "slack", "crm", "log_tool"]

    elif any(k in r for k in ["marketing", "cmo", "brand", "performance"]):
        department = "Marketing"
        skills = ["funnel-design", "ads", "copywriting", "analysis"]
        tools = ["email", "slack", "ads_manager", "log_tool"]

    elif any(k in r for k in ["product", "pm", "roadmap"]):
        department = "Product"
        skills = ["roadmap", "spec-writing", "user-research", "prioritisation"]
        tools = ["notion", "slack", "log_tool"]

    elif any(k in r for k in ["ops", "operation", "coo", "support", "cx", "service"]):
        department = "Operations"
        skills = ["process-design", "sops", "qa", "incident-management"]
        tools = ["notion", "slack", "helpdesk", "log_tool"]

    elif any(k in r for k in ["cto", "engineering", "tech", "developer", "ai", "data"]):
        department = "Technology"
        skills = ["architecture", "backlog", "review", "experiments"]
        tools = ["slack", "notion", "github", "log_tool"]

    elif any(k in r for k in ["finance", "cfo", "accounts", "billing"]):
        department = "Finance"
        skills = ["cashflow", "invoicing", "forecasting"]
        tools = ["sheets", "email", "log_tool"]

    return {
        "department": department,
        "skills": skills,
        "tools": tools,
    }


# ------------------------------------------------------------
# Manager: VirtualStaffManager
# ------------------------------------------------------------

class VirtualStaffManager:
    """
    Manages a roster of VirtualEmployee objects for a given company.

    Responsibilities:
    - Load / save virtual staff to .agentic_state/<company_id>_virtual_staff.json
    - Create new virtual employees (auto or manual)
    - Find by role / KPI
    - Simple capacity checks so the Agentic CEO can decide when to spawn new staff

    This does NOT directly talk to the LLM; it only manages structure and persistence.
    If you pass a MemoryEngine, it will log "virtual hires" and capacity decisions.
    """

    def __init__(
        self,
        company_id: str,
        company_name: Optional[str] = None,
        storage_dir: str = ".agentic_state",
        memory: Optional["MemoryEngine"] = None,
    ) -> None:
        self.company_id = company_id
        self.company_name = company_name or company_id
        self.storage_dir = storage_dir
        self.memory = memory

        os.makedirs(self.storage_dir, exist_ok=True)
        self._state_path = os.path.join(self.storage_dir, f"{self.company_id}_virtual_staff.json")

        self._employees: List[VirtualEmployee] = []
        self._load_state()

    # ----------------- Persistence -----------------

    def _load_state(self) -> None:
        if not os.path.exists(self._state_path):
            self._employees = []
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            self._employees = []
            return

        emps = []
        for item in raw.get("employees", []):
            try:
                emps.append(VirtualEmployee.from_dict(item))
            except Exception:
                # Skip broken entries but don't crash
                continue
        self._employees = emps

    def _save_state(self) -> None:
        payload = {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "saved_at": dt.datetime.utcnow().isoformat(),
            "employees": [e.to_dict() for e in self._employees],
        }
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    # ----------------- Helpers -----------------

    @property
    def employees(self) -> List[VirtualEmployee]:
        return list(self._employees)

    def list_active(self) -> List[VirtualEmployee]:
        return [e for e in self._employees if e.active]

    def find_by_role(self, role_substring: str, active_only: bool = True) -> List[VirtualEmployee]:
        role_substring = role_substring.lower()
        emps = self.list_active() if active_only else self._employees
        return [e for e in emps if role_substring in e.role.lower() or role_substring in e.title.lower()]

    def find_by_kpi(self, kpi_name: str) -> List[VirtualEmployee]:
        name = kpi_name.lower()
        return [e for e in self._employees if (e.owner_kpi or "").lower() == name and e.active]

    # ----------------- Creation -----------------

    def create_virtual_employee(
        self,
        role: str,
        title: Optional[str] = None,
        owner_kpi: Optional[str] = None,
        department: Optional[str] = None,
        skills: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        max_daily_tasks: int = 15,
        notes: str = "",
        log_reason: Optional[str] = None,
    ) -> VirtualEmployee:
        """
        Manually create a new virtual employee and persist to disk.
        """
        ve = VirtualEmployee.create(
            role=role,
            title=title,
            owner_kpi=owner_kpi,
            department=department,
            skills=skills,
            tools=tools,
            max_daily_tasks=max_daily_tasks,
            notes=notes,
        )
        self._employees.append(ve)
        self._save_state()

        # Optional memory logging
        if self.memory is not None:
            try:
                self.memory.record_tool_call(
                    tool_name="virtual_staff_manager",
                    payload={
                        "action": "create_virtual_employee",
                        "company_id": self.company_id,
                        "role": role,
                        "owner_kpi": owner_kpi,
                        "reason": log_reason,
                    },
                    result={"employee_id": ve.id, "title": ve.title},
                )
            except Exception:
                # Don't let memory failures break the run
                pass

        return ve

    # ----------------- Capacity & Gaps -----------------

    def _estimate_capacity_for_role(self, role: str) -> Dict[str, Any]:
        """
        Very simple capacity model: how many virtual staff exist for this role,
        and how many tasks per day they can handle collectively.
        """
        emps = self.find_by_role(role_substring=role, active_only=True)
        total_slots = sum(max(0, e.max_daily_tasks - e.tasks_assigned_today) for e in emps)
        return {
            "count": len(emps),
            "remaining_task_slots": total_slots,
        }

    def ensure_capacity_for_role(
        self,
        role: str,
        owner_kpi: Optional[str] = None,
        min_task_slots: int = 10,
        notes: str = "",
        log_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensure there is enough virtual staff capacity for a given role.

        If existing virtual employees for this role have fewer than `min_task_slots`
        remaining today, we auto-create a new VirtualEmployee.

        Returns a dict:
        {
            "created": bool,
            "employee": VirtualEmployee,
            "capacity_before": {...},
            "capacity_after": {...},
        }
        """
        before = self._estimate_capacity_for_role(role)
        created = False
        ve: Optional[VirtualEmployee] = None

        if before["remaining_task_slots"] < min_task_slots:
            ve = self.create_virtual_employee(
                role=role,
                owner_kpi=owner_kpi,
                max_daily_tasks=min_task_slots,
                notes=notes,
                log_reason=log_reason or f"Auto-created due to low capacity for role '{role}'",
            )
            created = True
        else:
            # We still return one of the existing employees (first) for convenience
            existing = self.find_by_role(role, active_only=True)
            ve = existing[0] if existing else None

        after = self._estimate_capacity_for_role(role)

        return {
            "created": created,
            "employee": ve,
            "capacity_before": before,
            "capacity_after": after,
        }

    # ----------------- Task assignment (lightweight) -----------------

    def assign_task_to_virtual_employee(
        self,
        employee_id: str,
        task_title: str,
        task_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[VirtualEmployee]:
        """
        Marks a task as assigned to a given virtual employee and bumps today's counter.

        In your higher-level orchestration, you can call this whenever you
        route a task to a virtual role (e.g. "Virtual SDR", "Virtual CMO").

        This doesn't execute the task – it just tracks capacity & logs to memory.
        """
        emp = next((e for e in self._employees if e.id == employee_id and e.active), None)
        if emp is None:
            return None

        emp.tasks_assigned_today += 1
        self._save_state()

        if self.memory is not None:
            try:
                self.memory.record_tool_call(
                    tool_name="virtual_staff_manager",
                    payload={
                        "action": "assign_task",
                        "company_id": self.company_id,
                        "employee_id": emp.id,
                        "role": emp.role,
                        "task_title": task_title,
                        "task_payload": task_payload or {},
                    },
                    result={"tasks_assigned_today": emp.tasks_assigned_today},
                )
            except Exception:
                pass

        return emp

    def reset_daily_task_counters(self) -> None:
        """
        Simple helper you can call once per UTC day in your main cron/runner.
        """
        for e in self._employees:
            e.tasks_assigned_today = 0
        self._save_state()

    def summarize(self) -> Dict[str, Any]:
        """
        Return a summary of virtual employees for dashboard/API consumption.
        
        Returns:
            {
                "employees": [
                    {
                        "id": str,
                        "name": str,  # title or role
                        "role": str,
                        "department": str | None,
                        "remaining_slots": int,
                        "tasks_assigned_today": int,
                        "max_daily_tasks": int,
                    },
                    ...
                ],
                "total_employees": int,
                "active_employees": int,
            }
        """
        active = self.list_active()
        employees_list = []
        
        for e in active:
            remaining = max(0, e.max_daily_tasks - e.tasks_assigned_today)
            employees_list.append({
                "id": e.id,
                "name": e.title or e.role,
                "role": e.role,
                "department": e.department,
                "remaining_slots": remaining,
                "tasks_assigned_today": e.tasks_assigned_today,
                "max_daily_tasks": e.max_daily_tasks,
            })
        
        return {
            "employees": employees_list,
            "total_employees": len(self._employees),
            "active_employees": len(active),
        }


# ------------------------------------------------------------
# Helper: VirtualEmployeeDashboard
# ------------------------------------------------------------

@dataclass
class VirtualEmployeeDashboard:
    """
    Lightweight snapshot of the current virtual org.

    You can use this from CompanyBrain or a CLI / API to quickly
    inspect how many virtual staff you have, where they sit, and
    how much capacity is left today.
    """

    total_employees: int
    active_employees: int
    by_department: Dict[str, int]
    by_role: Dict[str, int]
    total_remaining_task_slots: int
    per_role_capacity: Dict[str, Dict[str, Any]]

    @classmethod
    def from_manager(cls, manager: "VirtualStaffManager") -> "VirtualEmployeeDashboard":
        emps = manager.employees
        active = [e for e in emps if e.active]

        by_department: Dict[str, int] = {}
        by_role: Dict[str, int] = {}
        per_role_capacity: Dict[str, Dict[str, Any]] = {}

        total_remaining = 0

        for e in active:
            dept = e.department or "Unknown"
            by_department[dept] = by_department.get(dept, 0) + 1

            by_role[e.role] = by_role.get(e.role, 0) + 1

        # For capacity, re-use the private estimator per unique role
        seen_roles = set()
        for e in active:
            if e.role in seen_roles:
                continue
            seen_roles.add(e.role)
            cap = manager._estimate_capacity_for_role(e.role)
            per_role_capacity[e.role] = cap
            total_remaining += cap.get("remaining_task_slots", 0)

        return cls(
            total_employees=len(emps),
            active_employees=len(active),
            by_department=by_department,
            by_role=by_role,
            total_remaining_task_slots=total_remaining,
            per_role_capacity=per_role_capacity,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_employees": self.total_employees,
            "active_employees": self.active_employees,
            "by_department": self.by_department,
            "by_role": self.by_role,
            "total_remaining_task_slots": self.total_remaining_task_slots,
            "per_role_capacity": self.per_role_capacity,
        }

    def to_markdown(self) -> str:
        """
        Human-readable dashboard view (nice for CLI logs or Slack messages).
        """
        lines: List[str] = []
        lines.append("### Virtual Staff Dashboard")
        lines.append(f"- Total employees: {self.total_employees}")
        lines.append(f"- Active employees: {self.active_employees}")
        lines.append(f"- Total remaining task slots today: {self.total_remaining_task_slots}")
        lines.append("")
        lines.append("**By department:**")
        for dept, count in sorted(self.by_department.items()):
            lines.append(f"- {dept}: {count}")

        lines.append("")
        lines.append("**By role (with remaining capacity):**")
        for role, cap in self.per_role_capacity.items():
            remaining = cap.get("remaining_task_slots", 0)
            count = cap.get("count", 0)
            lines.append(f"- {role}: {count} active, {remaining} remaining slots")

        return "\n".join(lines)