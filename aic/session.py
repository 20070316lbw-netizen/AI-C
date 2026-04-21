"""
L1 会话层：messages 管理，context files 注入
"""
import os
import uuid
from pathlib import Path

class Session:
    def __init__(self, config: dict):
        self.config = config
        self._session_id = str(uuid.uuid4())
        self._messages: list[dict] = []
        self._context_files: list[str] = []

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
        """记录 context file 路径，如果不重复且存在则添加"""
        p = Path(path)
        if p.is_file():
            abs_path = str(p.absolute())
            if abs_path not in self._context_files:
                self._context_files.append(abs_path)

    def get_messages(self) -> list[dict]:
        """返回完整 messages 列表，首个是 system message (如果有上下文)"""
        system_parts = []

        if self._global_context:
            system_parts.append(self._global_context.strip())

        if self._project_context:
            system_parts.append(self._project_context.strip())

        for filepath in self._context_files:
            try:
                content = Path(filepath).read_text(encoding="utf-8")
                system_parts.append(f"--- File: {filepath} ---\n{content.strip()}")
            except Exception:
                pass

        messages = []
        if system_parts:
            system_content = "\n\n---\n\n".join(system_parts)
            messages.append({"role": "system", "content": system_content})

        messages.extend(self._messages)
        return messages

    def list_context_files(self) -> list[str]:
        return list(self._context_files)

    def clear(self):
        """清空历史，保留 context files"""
        self._messages.clear()

    def reset(self):
        """清空历史 + context files"""
        self._messages.clear()
        self._context_files.clear()

    def session_id(self) -> str:
        return self._session_id
