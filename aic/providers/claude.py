"""
L2 Provider 层：Anthropic 原生 API
"""
import json
from typing import Iterator

import httpx

from .base import BaseProvider


class ClaudeProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com"):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 8096,
            "stream": True,
        }

        if "tools" in kwargs and kwargs["tools"]:
            payload["tools"] = kwargs["tools"]

        if "system" in kwargs and kwargs["system"]:
            payload["system"] = kwargs["system"]

        url = f"{self._base_url}/v1/messages"

        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
                if response.status_code != 200:
                    error_text = response.read().decode("utf-8")
                    yield f"[错误] HTTP {response.status_code} — {error_text}"
                    return

                current_event = None
                input_tokens = 0
                output_tokens = 0
                tool_calls = []

                for line in response.iter_lines():
                    if not line:
                        continue

                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)

                            if current_event == "message_start":
                                usage = data.get("message", {}).get("usage", {})
                                input_tokens += usage.get("input_tokens", 0)
                                output_tokens += usage.get("output_tokens", 0)
                            elif current_event == "message_delta":
                                usage = data.get("usage", {})
                                output_tokens += usage.get("output_tokens", 0)
                            elif current_event == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta" and "text" in delta:
                                    yield delta["text"]
                        except json.JSONDecodeError:
                            continue

                # After loop ends, yield usage
                yield {
                    "type": "usage",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                }

        except Exception as e:
            yield f"[错误] 网络异常 — {str(e)}"
            return
