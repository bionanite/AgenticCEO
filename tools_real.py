# tools_real.py
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

import requests

from agentic_ceo import Tool


class SlackTool:
    """
    Sends a message to a Slack channel via Incoming Webhook.
    Set SLACK_WEBHOOK_URL in env.
    """

    name: str = "slack_tool"
    description: str = "Send a message to a Slack channel."

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            raise RuntimeError("SLACK_WEBHOOK_URL not set")

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message", "")
        resp = requests.post(self.webhook_url, json={"text": message})
        return {"ok": resp.ok, "status_code": resp.status_code, "text": resp.text}


class EmailTool:
    """
    Very simple SMTP email sender.
    Env vars:
      EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_FROM
    """

    name: str = "email_tool"
    description: str = "Send an email to a recipient."

    def __init__(self) -> None:
        self.host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("EMAIL_PORT", "587"))
        self.user = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASS")
        self.sender = os.getenv("EMAIL_FROM", self.user)

        if not (self.user and self.password and self.sender):
            raise RuntimeError("Email env vars not configured")

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        to = payload.get("to")
        subject = payload.get("subject", "Agentic CEO Message")
        body = payload.get("message", "")

        if not to:
            return {"ok": False, "error": "Missing 'to' in payload"}

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = to

        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.user, self.password)
            server.send_message(msg)

        return {"ok": True, "to": to, "subject": subject}


class NotionTool:
    """
    Create a simple page in Notion.
    Env vars:
      NOTION_API_KEY, NOTION_DATABASE_ID
    """

    name: str = "notion_tool"
    description: str = "Create a Notion page with a title and content."

    def __init__(self) -> None:
        self.api_key = os.getenv("NOTION_API_KEY")
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        if not (self.api_key and self.database_id):
            raise RuntimeError("NOTION_API_KEY or NOTION_DATABASE_ID not set")

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        title = payload.get("title", "Agentic CEO Note")
        content = payload.get("content", "")

        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": title}}],
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": content}}],
                    },
                }
            ],
        }

        resp = requests.post(url, headers=headers, json=data)
        return {"ok": resp.ok, "status_code": resp.status_code, "text": resp.text}