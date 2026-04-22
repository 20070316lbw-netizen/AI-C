"""
L1 会话层：messages 管理，context files 注入
"""
import os
import uuid
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List

# Import for warnings
from aic.errors import print_warning

# Safety limits for context injection
MAX_SINGLE_FILE_CHARS = 500 * 1024  # 500KB per file
MAX_TOTAL_CONTEXT_CHARS = 400 * 1024  # 400KB total across all files

@dataclass
class TurnUsage:
    turn: int
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    timestamp: float

class UsageAccumulator:
    def __init__(self):
        self.turns: List[TurnUsage] = []

    def record(self, input_tokens: int, output_tokens: int, provider: str, model: str) -> None:
        self.turns.append(
            TurnUsage(
                turn=len(self.turns) + 1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider=provider,
                model=model,
                timestamp=time.time()
            )
        )

    def total_input(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    def total_output(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    def total_cost_usd(self, pricing: dict) -> float:
        total = 0.0
        for t in self.turns:
            cost_info = None
            for key, (in_price, out_price) in pricing.items():
                if key in t.model:
                    cost_info = (in_price, out_price)
                    break

            if cost_info:
                in_price, out_price = cost_info
                # price is per 1M tokens
                total += (t.input_tokens / 1_000_000.0) * in_price
                total += (t.output_tokens / 1_000_000.0) * out_price
        return total

    def last_output_tokens(self) -> int:
        if not self.turns:
            return 0
        return self.turns[-1].output_tokens

class TokenGuard:
    def __init__(self, spike_threshold=2000, consecutive_limit=3):
        self.spike_threshold = spike_threshold
        self.consecutive_limit = consecutive_limit
        self._spike_count = 0

    def record(self, output_tokens: int) -> bool:
        """Returns True if Poor Mode should be auto-activated"""
        if output_tokens >= self.spike_threshold:
            self._spike_count += 1
        else:
            self._spike_count = 0

        return self._spike_count >= self.consecutive_limit

    @property
    def spike_count(self) -> int:
        return self._spike_count

class Session:
    def __init__(self, config: dict):
        self.config = config
        self._session_id = str(uuid.uuid4())
        self._messages: list[dict] = []
        self._context_files: list[str] = []
        self._file_cache: dict[str, tuple[float, str]] = {}
        self.poor_mode: bool = False
        self.poor_mode_reason: str = ""

        self.accumulator = UsageAccumulator()
        self.token_guard = TokenGuard()

        # Total characters of injected context files
        self._total_context_chars = 0

        self._global_context = ""
        self._project_context = ""

        # Load global context
        global_ctx_path = Path("~/.aic/GLOBAL_CONTEXT.md").expanduser()
        if global_ctx_path.is_file():
            try:
                self._global_context = global_ctx_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # Load project context
        project_ctx_path = Path(".aic/CONTEXT.md")
        if project_ctx_path.is_file():
            try:
                self._project_context = project_ctx_path.read_text(encoding="utf-8")
            except Exception:
                pass

    def add_user(self, content: str):
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self._messages.append({"role": "assistant", "content": content})

    def add_context_file(self, path: str):
        """记录 context file 路径，如果不重复且存在则添加，并执行大小限制检查"""
        p = Path(path)
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
            except Exception as e:
                print_warning(f"Failed to read file for context: {path} - {e}")
                return
            # Single file size limit
            if len(content) > MAX_SINGLE_FILE_CHARS:
                print_warning(f"Skipped (too large): {path}")
                return
            # Total context size limit
            if getattr(self, "_total_context_chars", 0) + len(content) > MAX_TOTAL_CONTEXT_CHARS:
                print_warning(f"Context budget full. Cannot add: {path}")
                return
            abs_path = str(p.absolute())
            if abs_path not in self._context_files:
                self._context_files.append(abs_path)
                # Update total counter
                self._total_context_chars += len(content)
                # Cache the initial read content
                self._file_cache[abs_path] = (p.stat().st_mtime, content)

    def get_system(self) -> str:
        system_parts = []
        if self._global_context:
            system_parts.append(self._global_context.strip())

        if self._project_context:
            system_parts.append(self._project_context.strip())

        for filepath in self._context_files:
            try:
                p = Path(filepath)
                mtime = p.stat().st_mtime
                if filepath in self._file_cache and self._file_cache[filepath][0] == mtime:
                    content = self._file_cache[filepath][1]
                else:
                    content = p.read_text(encoding="utf-8")
                    self._file_cache[filepath] = (mtime, content)
                system_parts.append(f"--- File: {filepath} ---\n{content.strip()}")
            except Exception:
                pass

        if system_parts:
            return "\n\n---\n\n".join(system_parts)
        return ""

    def get_messages(self) -> list[dict]:
        """返回完整 messages 列表，首个是 system message (如果有上下文)"""
        system_content = self.get_system()

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})

        messages.extend(self._messages)
        return messages

    def list_context_files(self) -> list[str]:
        return list(self._context_files)

    def clear(self):
        """清空历史，保留 context files"""
        self._messages.clear()
        # Reset total context counter (files stay loaded)
        self._total_context_chars = 0

    def reset(self):
        """清空历史 + context files"""
        self._messages.clear()
        self._context_files.clear()
        self._file_cache.clear()
        # Reset total context counter
        self._total_context_chars = 0

    def session_id(self) -> str:
        return self._session_id

    def activate_poor_mode(self, reason: str = ""):
        self.poor_mode = True
        self.poor_mode_reason = reason
