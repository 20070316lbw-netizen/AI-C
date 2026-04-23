"""
L2 Provider 层：DS / GPT / Gemini / Moonshot 等
"""
import json
from typing import Any, Iterator

import httpx

from .base import BaseProvider


class OpenAICompatProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "openai_compat"

    @property
    def model(self) -> str:
        return self._model

    def stream(self, messages: list[dict], **kwargs) -> Iterator[str | dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True}
        }

        # Tools integration for openai_compat stream
        if "tools" in kwargs and kwargs["tools"]:
            payload["tools"] = kwargs["tools"]

        url = f"{self._base_url}/chat/completions"

        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
                if response.status_code != 200:
                    error_text = response.read().decode("utf-8")
                    yield f"[错误] HTTP {response.status_code} — {error_text}"
                    return

                active_tools: dict[int, dict[str, str]] = {}

                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield delta["content"]
                                if "tool_calls" in delta and delta["tool_calls"]:
                                    for tc in delta["tool_calls"]:
                                        idx = tc.get("index", 0)
                                        if idx not in active_tools:
                                            active_tools[idx] = {
                                                "id": "",
                                                "name": "",
                                                "arguments": "",
                                            }

                                        if "id" in tc and tc["id"]:
                                            active_tools[idx]["id"] = tc["id"]

                                        if "function" in tc:
                                            if "name" in tc["function"] and tc["function"]["name"]:
                                                active_tools[idx]["name"] = tc["function"]["name"]
                                            if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                                active_tools[idx]["arguments"] += tc["function"]["arguments"]

                            if "usage" in data and data["usage"]:
                                yield {
                                    "type": "usage",
                                    "input_tokens": data["usage"].get("prompt_tokens", 0),
                                    "output_tokens": data["usage"].get("completion_tokens", 0)
                                }
                        except json.JSONDecodeError:
                            continue

                # Once stream completes, if we accumulated a tool call, yield it
                if active_tools:
                    tool_calls = [
                        {
                            "id": tool_data["id"],
                            "type": "function",
                            "function": {
                                "name": tool_data["name"],
                                "arguments": tool_data["arguments"],
                            },
                        }
                        for _, tool_data in sorted(active_tools.items())
                        if tool_data["name"]
                    ]
                    if tool_calls:
                        yield {
                            "type": "tool_calls",
                            "tool_calls": tool_calls,
                        }
        except Exception as e:
             yield f"[错误] 网络异常 — {str(e)}"
             return
