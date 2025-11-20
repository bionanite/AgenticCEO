#!/usr/bin/env python3
"""
ceo_notifications.py

Thin wrapper around MCP tools (and env vars) to send
morning / auto-run briefings to Slack and Email.

Design goals:
- Optional: if MCP is not configured, it just prints a warning and continues.
- Small, dependency-free, and safe to import anywhere.
- Clear contracts for MCP tools so you can implement them in your MCP server.

Expected MCP tools (you can rename via env):
- Slack tool  : MCP_SLACK_TOOL   (default: "slack.post_message")
- Email tool  : MCP_EMAIL_TOOL   (default: "email.send_message")
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

# MCP client is optional – if missing, notifications just no-op with a log.
try:
    from mcp_client import MCPClient  # type: ignore[attr-defined]
except Exception:  # ImportError, AttributeError, etc.
    MCPClient = None  # type: ignore[assignment]


class NotificationRouter:
    """
    High-level helper to send briefings via MCP-backed Slack / Email tools.

    Usage:
        router = NotificationRouter()
        router.send_briefings(
            company_id="next_ecosystem",
            company_name="Next Ecosystem",
            snapshot_text=snapshot,
            brief_text=brief,
            channels=["slack", "email"],
        )
    """

    def __init__(self) -> None:
        # MCP base URL is handled inside MCPClient.from_env(), if present.
        self.mcp: Optional[Any] = None
        if MCPClient is not None:
            try:
                self.mcp = MCPClient.from_env()
            except Exception as e:
                print(f"[NotificationRouter] MCPClient.from_env() failed: {e}")
                self.mcp = None
        else:
            print("[NotificationRouter] MCPClient not available; MCP notifications disabled.")

        # Tool names can be adjusted via env to match your MCP toolpack.
        self.slack_tool_name = os.getenv("MCP_SLACK_TOOL", "slack.post_message")
        self.email_tool_name = os.getenv("MCP_EMAIL_TOOL", "email.send_message")

        # Default channels / recipients (override per call if needed)
        self.default_slack_channel = os.getenv("AGENTIC_SLACK_CHANNEL", "#agentic-ceo")
        self.default_email_to = os.getenv("AGENTIC_CEO_EMAIL_TO")
        self.default_email_from = os.getenv("AGENTIC_CEO_EMAIL_FROM", "agentic-ceo@system.local")

    # ------------ Internal helper ------------

    def _call_mcp_tool(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        if not self.mcp:
            print(f"[NotificationRouter] MCP client not configured; skipping tool '{tool_name}'.")
            return None
        try:
            return self.mcp.call_tool(tool_name, args)  # type: ignore[union-attr]
        except Exception as e:
            print(f"[NotificationRouter] Error calling MCP tool '{tool_name}': {e}")
            return None

    def _build_briefing_block(
        self,
        company_id: str,
        company_name: str,
        snapshot_text: str,
        brief_text: str,
    ) -> str:
        """
        Small formatter so Slack and Email get the same content.
        """
        header = f"Agentic CEO Morning Briefing — {company_name} ({company_id})"
        sep = "-" * len(header)
        return (
            f"{header}\n"
            f"{sep}\n\n"
            "SNAPSHOT\n"
            "--------\n"
            f"{snapshot_text.strip()}\n\n"
            "CEO PERSONAL BRIEFING (3 ACTIONS)\n"
            "----------------------------------\n"
            f"{brief_text.strip()}\n"
        )

    # ------------ Public API ------------

    def send_slack_brief(
        self,
        company_id: str,
        company_name: str,
        snapshot_text: str,
        brief_text: str,
        channel: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Call MCP Slack tool with a simple contract:

        Tool: self.slack_tool_name  (default "slack.post_message")
        Args: { "channel": str, "text": str }
        """
        channel = channel or self.default_slack_channel
        if not channel:
            print("[NotificationRouter] No Slack channel configured; skipping Slack notification.")
            return None

        text = self._build_briefing_block(company_id, company_name, snapshot_text, brief_text)
        payload = {"channel": channel, "text": text}
        print(f"[NotificationRouter] Sending Slack briefing via '{self.slack_tool_name}' to {channel}...")
        return self._call_mcp_tool(self.slack_tool_name, payload)

    def send_email_brief(
        self,
        company_id: str,
        company_name: str,
        snapshot_text: str,
        brief_text: str,
        to_email: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Call MCP Email tool with a simple contract:

        Tool: self.email_tool_name  (default "email.send_message")
        Args: {
          "to": str,
          "subject": str,
          "body": str,
          "from": Optional[str]
        }

        You can adapt your MCP email tool to accept this shape,
        or tweak this wrapper to match your implementation.
        """
        to_email = to_email or self.default_email_to
        if not to_email:
            print("[NotificationRouter] No AGENTIC_CEO_EMAIL_TO configured; skipping email notification.")
            return None

        subject = subject or f"Agentic CEO Morning Briefing — {company_name} ({company_id})"
        body = self._build_briefing_block(company_id, company_name, snapshot_text, brief_text)

        payload = {
            "to": to_email,
            "subject": subject,
            "body": body,
            "from": self.default_email_from,
        }
        print(f"[NotificationRouter] Sending email briefing via '{self.email_tool_name}' to {to_email}...")
        return self._call_mcp_tool(self.email_tool_name, payload)

    def send_briefings(
        self,
        company_id: str,
        company_name: str,
        snapshot_text: str,
        brief_text: str,
        channels: Optional[list[str]] = None,
    ) -> None:
        """
        High-level helper to fan-out to multiple channels.

        channels example: ["slack", "email"]
        """
        channels = channels or []
        channels = [c.lower().strip() for c in channels if c.strip()]

        if not channels:
            print("[NotificationRouter] No notification channels requested; nothing to send.")
            return

        if "slack" in channels:
            self.send_slack_brief(
                company_id=company_id,
                company_name=company_name,
                snapshot_text=snapshot_text,
                brief_text=brief_text,
            )

        if "email" in channels:
            self.send_email_brief(
                company_id=company_id,
                company_name=company_name,
                snapshot_text=snapshot_text,
                brief_text=brief_text,
            )