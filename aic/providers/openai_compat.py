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
        }

        url = f"{self._base_url}/chat/completions"

        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
                if response.status_code != 200:
                    error_text = response.read().decode("utf-8")
                    yield f"[错误] HTTP {response.status_code} — {error_text}"
                    return

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
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
             yield f"[错误] 网络异常 — {str(e)}"
             return
