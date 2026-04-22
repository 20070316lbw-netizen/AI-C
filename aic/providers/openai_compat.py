"""
L2 Provider 层：DS / GPT / Gemini / Moonshot 等
"""
import json
from typing import Iterator

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

    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
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

                tool_call_id = ""
                tool_name = ""
                arguments_buffer = ""

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
                                    tc = delta["tool_calls"][0]
                                    if "id" in tc and tc["id"]:
                                        tool_call_id = tc["id"]
                                    if "function" in tc:
                                        if "name" in tc["function"] and tc["function"]["name"]:
                                            tool_name = tc["function"]["name"]
                                        if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                            arguments_buffer += tc["function"]["arguments"]

                            if "usage" in data and data["usage"]:
                                yield {
                                    "type": "usage",
                                    "input_tokens": data["usage"].get("prompt_tokens", 0),
                                    "output_tokens": data["usage"].get("completion_tokens", 0)
                                }
                        except json.JSONDecodeError:
                            continue

                # Once stream completes, if we accumulated a tool call, yield it
                if tool_name:
                    yield {
                        "type": "tool_calls",
                        "tool_calls": [{
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": arguments_buffer
                            }
                        }]
                    }
        except Exception as e:
             yield f"[错误] 网络异常 — {str(e)}"
             return
