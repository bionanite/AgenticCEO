# task_manager.py
from __future__ import annotations

import os
import json
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple

from agentic_ceo import CEOTask, CEOState
from memory_engine import MemoryEngine


class TaskManager:
    """
    Lightweight task orchestration layer on top of CEOState.tasks.

    Responsibilities:
    - Keep a small JSON metadata file with:
        - parent → children relationships
        - review status per task (awaiting / approved / rejected)
    - Provide helpers for:
        - creating subtasks
        - marking tasks done by a delegate
        - reviewing tasks and auto-closing parents
        - dumping an open-task tree for CLI / debugging

    NOTE:
    - We deliberately do NOT modify the CEOTask schema.
    - All "extra" structure lives here in a small meta JSON.
    """

    def __init__(
        self,
        state: CEOState,
        memory: MemoryEngine,
        company_id: str = "default",
        storage_dir: str = ".agentic_state",
    ) -> None:
        self.state = state
        self.memory = memory
        self.company_id = company_id
        self.storage_dir = storage_dir

        os.makedirs(self.storage_dir, exist_ok=True)
        self._meta_path = os.path.join(self.storage_dir, f"{self.company_id}_tasks_meta.json")
        self._meta: Dict[str, Any] = self._load_meta()

        # Shape:
        # {
        #   "links": { parent_id: [child_id, ...], ... },
        #   "reviews": { task_id: { "status": "awaiting|approved|rejected|none",
        #                           "reviewed_by": str,
        #                           "comments": str,
        #                           "timestamp": str }, ... }
        # }

        self._meta.setdefault("links", {})
        self._meta.setdefault("reviews", {})

    # ------------------------------------------------------------------
    # Internal persistence
    # ------------------------------------------------------------------

    def _load_meta(self) -> Dict[str, Any]:
        if not os.path.exists(self._meta_path):
            return {}
        try:
            with open(self._meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_meta(self) -> None:
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Basic helpers
    # ------------------------------------------------------------------

    def _find_task(self, task_id: str) -> Optional[CEOTask]:
        for t in self.state.tasks:
            if t.id == task_id:
                return t
        return None

    def _get_children_ids(self, parent_id: str) -> List[str]:
        return list(self._meta.get("links", {}).get(parent_id, []))

    def _get_parent_id(self, child_id: str) -> Optional[str]:
        links: Dict[str, List[str]] = self._meta.get("links", {})
        for parent, children in links.items():
            if child_id in children:
                return parent
        return None

    def _set_review(
        self,
        task_id: str,
        status: str,
        reviewed_by: Optional[str] = None,
        comments: str = "",
    ) -> None:
        self._meta.setdefault("reviews", {})
        self._meta["reviews"][task_id] = {
            "status": status,
            "reviewed_by": reviewed_by or "",
            "comments": comments,
            "timestamp": dt.datetime.utcnow().isoformat(),
        }
        self._save_meta()

    def get_review_status(self, task_id: str) -> str:
        return self._meta.get("reviews", {}).get(task_id, {}).get("status", "none")

    # ------------------------------------------------------------------
    # Public API: Subtasks / delegation / review
    # ------------------------------------------------------------------

    def create_subtask(
        self,
        parent_task_id: str,
        title: str,
        description: str,
        area: Optional[str] = None,
        suggested_owner: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> CEOTask:
        """
        Create a subtask under a parent task and attach it to the CEO state.

        Does NOT hit the LLM; it's purely structural.
        """
        parent = self._find_task(parent_task_id)
        if parent is None:
            raise ValueError(f"Parent task {parent_task_id} not found")

        sub = CEOTask(
            title=title,
            description=description,
            area=area or parent.area,
            suggested_owner=suggested_owner or parent.suggested_owner,
            priority=priority or parent.priority,
            owner="Agentic CEO",
            due_date=self.state.date,
        )

        # Append to CEO state
        self.state.tasks.append(sub)

        # Update links
        links: Dict[str, List[str]] = self._meta.setdefault("links", {})
        children = links.setdefault(parent_task_id, [])
        children.append(sub.id)
        self._save_meta()

        # Log in memory
        self.memory.record_decision(
            text=f"Subtask created: '{sub.title}' under parent '{parent.title}'",
            context={
                "type": "subtask_created",
                "parent_id": parent_task_id,
                "subtask_id": sub.id,
            },
        )

        return sub

    def mark_task_done_by_delegate(
        self,
        task_id: str,
        delegate_name: str,
        notes: str = "",
    ) -> Optional[CEOTask]:
        """
        Mark a task as done by a delegate (human or virtual).

        This:
        - sets task.status = "done"
        - sets task.owner   = delegate_name
        - logs into MemoryEngine
        - sets review status to 'awaiting'
        - tries to auto-close parent chain if all children are done & approved
        """
        task = self._find_task(task_id)
        if task is None:
            return None

        task.status = "done"
        task.owner = delegate_name
        task.updated_at = dt.datetime.utcnow()

        self._set_review(task_id, status="awaiting")

        self.memory.record_decision(
            text=f"Task '{task.title}' marked done by delegate {delegate_name}. Awaiting review.",
            context={
                "type": "task_completed_by_delegate",
                "task_id": task.id,
                "delegate": delegate_name,
                "notes": notes,
            },
        )

        # Try to auto-close parent(s)
        parent_id = self._get_parent_id(task.id)
        if parent_id:
            self._maybe_auto_close_parent_chain(parent_id)

        return task

    def review_task(
        self,
        task_id: str,
        approved: bool,
        reviewed_by: str,
        comments: str = "",
    ) -> Optional[CEOTask]:
        """
        Approve or reject a completed task.

        If approved:
        - review status → 'approved'
        - maybe auto-close parent(s) if all children are done + approved

        If rejected:
        - review status → 'rejected'
        - parent is NOT auto-closed (and may get new subtasks)
        """
        task = self._find_task(task_id)
        if task is None:
            return None

        status = "approved" if approved else "rejected"
        self._set_review(task_id, status=status, reviewed_by=reviewed_by, comments=comments)

        self.memory.record_decision(
            text=f"Task review: '{task.title}' -> {status.upper()} by {reviewed_by}",
            context={
                "type": "task_review",
                "task_id": task.id,
                "approved": approved,
                "reviewed_by": reviewed_by,
                "comments": comments,
            },
        )

        if approved:
            parent_id = self._get_parent_id(task.id)
            if parent_id:
                self._maybe_auto_close_parent_chain(parent_id)

        return task

    # ------------------------------------------------------------------
    # Internal: auto-close parent chain
    # ------------------------------------------------------------------

    def _maybe_auto_close_parent_chain(self, parent_id: str) -> None:
        """
        If all children of parent are done AND approved, mark parent done.
        Then recurse up the chain.

        We keep this logic very small and opinionated.
        """
        parent = self._find_task(parent_id)
        if parent is None:
            return

        children_ids = self._get_children_ids(parent_id)
        if not children_ids:
            return

        # Fetch child tasks
        children_tasks: List[CEOTask] = []
        for cid in children_ids:
            t = self._find_task(cid)
            if t is not None:
                children_tasks.append(t)

        if not children_tasks:
            return

        # All children must be done AND approved
        for child in children_tasks:
            if child.status != "done":
                return
            if self.get_review_status(child.id) != "approved":
                return

        # If we reach here, parent can be auto-closed
        parent.status = "done"
        parent.updated_at = dt.datetime.utcnow()

        self.memory.record_decision(
            text=f"Parent task '{parent.title}' auto-closed (all children done & approved).",
            context={
                "type": "parent_task_auto_closed",
                "parent_id": parent.id,
            },
        )

        # Recurse upwards
        grandparent_id = self._get_parent_id(parent.id)
        if grandparent_id:
            self._maybe_auto_close_parent_chain(grandparent_id)

    # ------------------------------------------------------------------
    # Task tree inspection
    # ------------------------------------------------------------------

    def get_open_task_tree(self) -> List[Dict[str, Any]]:
        """
        Return a nested dict structure representing open tasks and their children.

        Shape:
        [
          {
            "task": CEOTask,
            "review_status": "none|awaiting|approved|rejected",
            "children": [ ... same shape ... ]
          },
          ...
        ]
        """
        # Build quick lookup
        tasks_by_id: Dict[str, CEOTask] = {t.id: t for t in self.state.tasks}

        links: Dict[str, List[str]] = self._meta.get("links", {})

        # Identify all child IDs
        all_child_ids = {cid for children in links.values() for cid in children}

        # Root candidates = tasks that are not children of anyone
        root_ids = [tid for tid in tasks_by_id.keys() if tid not in all_child_ids]

        def build_node(task_id: str) -> Optional[Dict[str, Any]]:
            t = tasks_by_id.get(task_id)
            if t is None:
                return None

            # Only show in tree if not done
            if t.status == "done":
                return None

            children_nodes: List[Dict[str, Any]] = []
            for cid in links.get(task_id, []):
                child_node = build_node(cid)
                if child_node is not None:
                    children_nodes.append(child_node)

            return {
                "task": t,
                "review_status": self.get_review_status(task_id),
                "children": children_nodes,
            }

        tree: List[Dict[str, Any]] = []
        for rid in root_ids:
            node = build_node(rid)
            if node is not None:
                tree.append(node)

        return tree

    def format_open_task_tree(self) -> str:
        """
        Pretty-print the open task tree into a readable text block
        (for CLI: `ceo_cli.py tasks` / `ceo_cli.py vstaff` etc).
        """

        tree = self.get_open_task_tree()
        if not tree:
            return "No open tasks.\n"

        lines: List[str] = []

        def walk(node: Dict[str, Any], depth: int = 0) -> None:
            t: CEOTask = node["task"]
            review_status: str = node["review_status"]
            indent = "  " * depth
            owner = t.suggested_owner or t.owner or "Unassigned"
            lines.append(
                f"{indent}- [{t.area}, {owner}, P{t.priority}] {t.title} "
                f"(status={t.status}, review={review_status})"
            )
            for child in node.get("children", []):
                walk(child, depth + 1)

        for root in tree:
            walk(root, depth=0)

        return "\n".join(lines) + "\n"