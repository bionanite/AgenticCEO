# llm_openai.py
from __future__ import annotations

import os
from typing import Protocol, Dict

from dotenv import load_dotenv
from openai import OpenAI

# Load API keys from .env
load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("OPENAI_API_KEY missing in .env")


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...

    def get_last_usage(self) -> Dict[str, int]:
        ...


class OpenAILLM:
    """
    OpenAI-backed model with token usage tracking.
    Loads OPENAI_API_KEY from .env automatically.
    """

    def __init__(self, model: str = "gpt-4.1-mini", temperature: float = 0.2):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.temperature = temperature
        self.last_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Track usage
        usage = response.usage
        if usage:
            self.last_usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }

        content = response.choices[0].message.content
        return content.strip() if content else ""

    def get_last_usage(self) -> Dict[str, int]:
        return self.last_usage