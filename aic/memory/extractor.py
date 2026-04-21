import concurrent.futures
import datetime
import hashlib
import json
import os
import time
from typing import Any

import httpx

from aic.memory.store import MemoryStore
from aic.memory.types import Memory
from aic.providers.base import BaseProvider


class MemoryExtractor:
    SYSTEM_PROMPT = (
        "你是记忆提取器。分析以下对话，提取值得长期记住的信息。\n"
        "只提取明确表达的事实，不推断，不臆测。\n"
        "输出 JSON 数组，每项包含 {\"type\", \"content\"}。\n"
        "type 只能是: user / feedback / project / reference\n"
        "如果没有值得提取的内容，返回空数组 []。\n"
        "不要输出任何其他内容，不要 Markdown 代码块。"
    )

    def __init__(self, provider: BaseProvider, store: MemoryStore, session_id: str):
        self.provider = provider
        self.store = store
        self.session_id = session_id
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False)

    def _write_log(self, event: str, payload: dict[str, Any]) -> None:
        now = datetime.datetime.now()
        log_dir = os.path.expanduser("~/.aic/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{now.strftime('%Y-%m-%d')}.jsonl")

        log_entry = {
            "ts": time.time(),
            "event": event,
            "session_id": self.session_id,
            "payload": payload
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            newline_idx = text.find("\n")
            if newline_idx != -1:
                text = text[newline_idx + 1:]
            last_ticks = text.rfind("```")
            if last_ticks != -1:
                text = text[:last_ticks]
        return text.strip()

    def _complete(self, user_msg: str, assistant_msg: str) -> str:
        provider_name = self.provider.name
        api_key = getattr(self.provider, "_api_key", "")
        model = self.provider.model
        base_url = getattr(self.provider, "_base_url", "")

        user_content = f"User: {user_msg}\nAssistant: {assistant_msg}"

        if provider_name == "claude":
            url = f"{base_url}/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "system": self.SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
                "max_tokens": 1024,
                "stream": False,
            }
            resp = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

        elif provider_name == "openai_compat":
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                "stream": False,
            }
            resp = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def _extract(self, user_msg: str, assistant_msg: str) -> None:
        response_text = ""
        try:
            response_text = self._complete(user_msg, assistant_msg)
            cleaned = self.clean_json_response(response_text)
            items = json.loads(cleaned)

            if not isinstance(items, list):
                items = []

            added_count = 0
            added_types = []

            for item in items:
                if not isinstance(item, dict):
                    continue

                content = item.get("content", "")
                type_str = item.get("type", "user")

                if not content:
                    continue

                content = str(content)[:500]
                content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]

                if self.store.get(content_hash):
                    continue

                type_str = str(type_str).lower()
                if type_str not in ("user", "feedback", "project", "reference"):
                    type_str = "user"

                mem = Memory(
                    id=content_hash,
                    content=content,
                    type=type_str,
                    source="extractor",
                    session_id=self.session_id
                )
                self.store.add(mem)
                added_count += 1
                added_types.append(type_str)

            self._write_log("memory_extracted", {
                "count": added_count,
                "types": added_types
            })

        except Exception as e:
            self._write_log("extractor_error", {
                "error": str(e),
                "raw": response_text[:200]
            })

    def extract_async(self, user_msg: str, assistant_msg: str) -> None:
        future = self.executor.submit(self._extract, user_msg, assistant_msg)

        def done_callback(f: concurrent.futures.Future) -> None:
            try:
                f.result()
            except Exception as e:
                self._write_log("extractor_error", {
                    "error": f"Thread error: {str(e)}",
                    "raw": ""
                })

        future.add_done_callback(done_callback)
