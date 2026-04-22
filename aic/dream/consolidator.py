"""
L4 Dream 层：4阶段 prompt 构建 + 调用子代理
"""
import json
import traceback
from dataclasses import dataclass
from datetime import date
from typing import Callable

from aic.dream.agent import DreamAgent
from aic.llm import complete

# 模拟 llm.py 中应该存在的异常（若不存在不报错，直接作为基类异常捕获）
try:
    from aic.llm import LLMTimeoutError
except ImportError:
    class LLMTimeoutError(Exception):
        pass

@dataclass
class DreamResult:
    merged: int = 0
    archived: int = 0
    added: int = 0
    conflicts_resolved: int = 0

class Consolidator:
    def __init__(self, store, lock, config, kairos_log: Callable, exclude_session_id=None):
        self.store = store
        self.lock = lock
        self.config = config
        self.kairos_log = kairos_log
        self.exclude_session_id = exclude_session_id

        self.agent = DreamAgent(store)
        self._result = DreamResult()
        self._unprocessed_mems = []

    def run(self) -> DreamResult:
        state = self.lock.get_state()
        self._orient_result = state.get("orient_data") or {}  # 断点续传恢复
        start_phase = state.get("phase", 0) + 1

        try:
            # Prepare unprocessed memories
            if start_phase <= 2:
                self._unprocessed_mems = self.store.list_unprocessed(self.exclude_session_id)
                if not self._unprocessed_mems and start_phase == 1:
                    return self._result

            for phase in range(start_phase, 5):
                self._run_phase(phase)

        except Exception as e:
            self.kairos_log("dream_error", state.get("session_id", ""), {"error": str(e), "trace": traceback.format_exc()})
            if isinstance(e, LLMTimeoutError):
                raise

        return self._result

    def _run_phase(self, phase: int):
        session_id = self.lock.get_state().get("session_id", "")
        self.kairos_log("dream_phase_start", session_id, {"phase": phase})
        try:
            if phase == 1:
                self._phase1()
            elif phase == 2:
                self._phase2()
            elif phase == 3:
                self._phase3()
            elif phase == 4:
                self._phase4()
            self.kairos_log("dream_phase_done", session_id, {"phase": phase})
        except LLMTimeoutError as e:
            self.kairos_log("dream_phase_timeout", session_id, {"phase": phase, "error": str(e)})
            raise

    def _get_provider_config(self) -> tuple[str, dict]:
        provider = self.config.get("dream", {}).get("provider") or self.config.get("provider", "claude")
        model = self.config.get("dream", {}).get("model") or self.config.get(provider, {}).get("model", "")

        provider_config = self.config.get(provider, {}).copy()
        provider_config["model"] = model
        return provider, provider_config

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            newline_idx = text.find("\n")
            if newline_idx != -1:
                text = text[newline_idx + 1:]
            last_ticks = text.rfind("```")
            if last_ticks != -1:
                text = text[:last_ticks]
        return text.strip()

    def _phase1(self):
        system = (
            "You are an expert memory consolidation system. Analyze the provided memories and output ONLY a JSON object.\n"
            "The JSON must have the following keys:\n"
            '1. "summary": string, an overall summary.\n'
            '2. "patterns": array of strings, patterns observed.\n'
            '3. "conflicts": array of strings, describing conflicts like "memory_id_a vs memory_id_b".\n'
        )
        mem_text = "\n".join([f"ID: {m.id} | Type: {m.type} | Content: {m.content}" for m in self._unprocessed_mems])
        prompt = f"Unprocessed Memories:\n{mem_text}"

        provider, provider_config = self._get_provider_config()
        res = complete(prompt, provider, provider_config, system)

        try:
            cleaned = self._clean_json_response(res["content"])
            self._orient_result = json.loads(cleaned)
        except json.JSONDecodeError:
            self._orient_result = {"summary": "", "patterns": [], "conflicts": []}

        if not isinstance(self._orient_result.get("conflicts"), list):
            self._orient_result["conflicts"] = []

        self.lock.update_state(phase=1, orient_data=self._orient_result)

    def _execute_tool_calls(self, tool_calls, turns=0) -> list[str]:
        responses = []
        for call in tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})

            if name == "add_memory":
                mem_id = self.agent.add_memory(
                    content=args.get("content", ""),
                    type=args.get("type", "user"),
                    meta={"merged_from": args.get("merged_from", [])} if args.get("merged_from") else None
                )
                self._result.added += 1
                responses.append(f"Tool {name} succeeded. Added memory with ID: {mem_id}")

            elif name == "read_memory":
                mem = self.agent.read_memory(args.get("id"))
                if mem:
                    responses.append(f"Tool {name} result: {json.dumps(mem, ensure_ascii=False)}")
                else:
                    responses.append(f"Tool {name} result: Memory not found.")

            elif name == "soft_delete_memory":
                success = self.agent.soft_delete_memory(args.get("id"), args.get("superseded_by"))
                responses.append(f"Tool {name} result: {'Success' if success else 'Failed'}")

        return responses

    def _phase2(self):
        system = (
            "You are Phase 2 Gather. Use tools to supplement information or split mixed memories.\n"
            "You can call `add_memory` or `read_memory`. Do NOT loop endlessly. Complete your task within 3 turns.\n"
        )
        mem_text = "\n".join([f"ID: {m.id} | Type: {m.type} | Content: {m.content}" for m in self._unprocessed_mems])
        orient_text = json.dumps(self._orient_result, ensure_ascii=False)
        prompt = f"Orient Result: {orient_text}\nMemories:\n{mem_text}\n\nAnalyze and use tools if needed."

        provider, provider_config = self._get_provider_config()
        tools = [t for t in self.agent.TOOL_SCHEMA if t["name"] in ["add_memory", "read_memory"]]

        for turn in range(3):
            res = complete(prompt, provider, provider_config, system, tools=tools)
            tool_calls = res.get("tool_calls", [])
            if not tool_calls:
                break

            tool_results = self._execute_tool_calls(tool_calls, turn)
            prompt += f"\nAssistant called tools.\nTool Results: {tool_results}\nProceed."

        self.lock.update_state(phase=2, orient_data=self._orient_result)

    def _phase3(self):
        conflicts = self._orient_result.get("conflicts", [])
        for conflict in conflicts:
            self._resolve_conflict(conflict)
        self.lock.update_state(phase=3, orient_data=self._orient_result)

    def _resolve_conflict(self, conflict: str):
        today = date.today().isoformat()
        system = (
            f"You are Phase 3 Merge. Resolve this conflict using tools (`soft_delete_memory`, `add_memory`).\n"
            f"Today is {today}. Keep the most up-to-date facts, add a new memory with the merged facts, "
            f"and soft_delete the old conflicting ones. Max 3 turns.\n"
        )

        # Extrapolate IDs from conflict string heuristically for context
        import re
        ids = set(re.findall(r'[a-f0-9]{8}', conflict.lower()))
        mems_context = []
        for mem_id in ids:
            mem = self.agent.read_memory(mem_id)
            if mem:
                mems_context.append(f"ID: {mem['id']} | Content: {mem['content']}")

        prompt = f"Conflict: {conflict}\nContext Memories:\n" + "\n".join(mems_context)

        provider, provider_config = self._get_provider_config()
        tools = [t for t in self.agent.TOOL_SCHEMA if t["name"] in ["add_memory", "soft_delete_memory"]]

        for turn in range(3):
            res = complete(prompt, provider, provider_config, system, tools=tools)
            tool_calls = res.get("tool_calls", [])
            if not tool_calls:
                break

            tool_results = self._execute_tool_calls(tool_calls, turn)
            prompt += f"\nAssistant called tools.\nTool Results: {tool_results}\nProceed."

        self._result.conflicts_resolved += 1

    def _phase4(self):
        max_per_type = self.config.get("dream", {}).get("max_memories_per_type", 100)

        for mem_type in ["user", "feedback", "project", "reference"]:
            memories = self.store.list_by_type(mem_type, order_by="weight ASC, updated_at ASC")
            if len(memories) > max_per_type:
                excess = memories[max_per_type:]
                for m in excess:
                    self.store.archive(m.id)
                    self._result.archived += 1

        mems_to_mark = self.store.list_unprocessed(self.exclude_session_id)
        if mems_to_mark:
            ids_to_mark = [m.id for m in mems_to_mark]
            self.store.mark_processed(ids_to_mark)

        self.lock.update_state(phase=4, orient_data=self._orient_result)
