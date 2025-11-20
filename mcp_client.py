from __future__ import annotations

"""
mcp_client.py

Thin, optional MCP-style client you can plug into CompanyBrain / AgenticCEO.

This is deliberately simple:

- It defines a SimpleHTTPMCPClient that treats your MCP server as an HTTP JSON API.
- It matches the MCPClient protocol used inside agentic_ceo.AgenticCEO:
      call_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]

You can replace this with a proper Model Context Protocol client later
(e.g. using the official MCP Python SDK) as long as it implements the same
`call_tool` interface.
"""

import json
import os
from typing import Any, Dict, Optional
from urllib import request, error as urlerror

from agentic_ceo import MCPClient


class SimpleHTTPMCPClient:
    """
    Minimal HTTP-based MCP-style client.

    It expects a server that exposes tools via endpoints like:

        POST {base_url}/tools/{tool_name}
        Body: {"args": {...}}

    And returns a JSON object as response.

    Environment variables:
      - MCP_BASE_URL: base URL of your MCP server, e.g. "https://mcp.myserver.com"
      - MCP_API_KEY:  optional bearer token for auth
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or os.getenv("MCP_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("MCP_API_KEY")
        self.timeout = timeout

        if not self.base_url:
            raise ValueError(
                "SimpleHTTPMCPClient requires a base URL. "
                "Set MCP_BASE_URL env var or pass base_url explicitly."
            )

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a remote tool via HTTP.

        Returns a dict with at least:
          - ok: bool
          - tool: str
          - result / error
        """
        url = f"{self.base_url}/tools/{tool_name}"
        payload = {"args": args}

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(url, data=data, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    return {
                        "ok": False,
                        "tool": tool_name,
                        "error": "Invalid JSON response from MCP server",
                        "raw": body,
                    }

                # Normalize to our standard shape
                if isinstance(parsed, dict):
                    parsed.setdefault("ok", True)
                    parsed.setdefault("tool", tool_name)
                    return parsed

                return {
                    "ok": False,
                    "tool": tool_name,
                    "error": "MCP server returned non-dict JSON",
                    "raw": parsed,
                }

        except urlerror.HTTPError as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": f"HTTPError {e.code}: {e.reason}",
            }
        except urlerror.URLError as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": f"URLError: {e.reason}",
            }
        except Exception as e:
            return {
                "ok": False,
                "tool": tool_name,
                "error": f"Unexpected error: {e}",
            }


class NullMCPClient:
    """
    Safe placeholder: if you accidentally wire this in and call a tool,
    it will give a clear error instead of crashing the whole CEO.
    """

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": tool_name,
            "error": "NullMCPClient used — no real MCP server configured.",
        }


__all__ = ["SimpleHTTPMCPClient", "NullMCPClient"]