"""
L4 Dream 层：受限子代理，只读工具+只写memory/
"""
import hashlib
from dataclasses import asdict

from aic.memory.store import MemoryStore
from aic.memory.types import Memory

class DreamAgent:
    TOOL_SCHEMA = [
        {
            "name": "read_memory",
            "description": "Read the full content of a memory by its ID",
            "input_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The ID of the memory to read"}
                },
                "required": ["id"]
            }
        },
        {
            "name": "add_memory",
            "description": "Add a new memory or combined memory",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The full content of the memory to add"},
                    "type": {"type": "string", "description": "The type of memory (user, feedback, project, reference)"},
                    "merged_from": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of memory IDs this memory was merged from"
                    }
                },
                "required": ["content", "type"]
            }
        },
        {
            "name": "soft_delete_memory",
            "description": "Soft delete an old memory that is being superseded or is a conflict",
            "input_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The ID of the memory to soft delete"},
                    "superseded_by": {"type": "string", "description": "The ID of the new memory that supersedes this one"}
                },
                "required": ["id", "superseded_by"]
            }
        }
    ]

    def __init__(self, store: MemoryStore, session_id: str = "dream"):
        self.store = store
        self.session_id = session_id

    # 只读
    def read_memory(self, id: str) -> dict | None:
        mem = self.store.get(id)
        if not mem:
            return None
        return asdict(mem)

    def list_memories(self, type: str, limit: int = 50) -> list[dict]:
        mems = self.store.list_by_type(type)
        # return up to limit
        return [asdict(m) for m in mems[:limit]]

    # 只写（含幂等保护）
    def add_memory(self, content: str, type: str, merged_from: list[str] | None = None) -> str:
        content = str(content)[:500]
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]

        # 已存在则返回已有 id，不重复写入
        existing = self.store.get(content_hash)
        if existing:
            return existing.id

        import json
        meta = {"merged_from": merged_from} if merged_from else None
        meta_str = json.dumps(meta, ensure_ascii=False) if meta else None

        mem = Memory(
            id=content_hash,
            content=content,
            type=type,
            source="dream",
            session_id=self.session_id,
            meta=meta_str
        )
        self.store.add(mem)
        return content_hash

    def soft_delete_memory(self, id: str, superseded_by: str) -> bool:
        # superseded_by 必须是已存在的 id，否则拒绝
        target = self.store.get(superseded_by)
        if not target:
            return False

        mem = self.store.get(id)
        if not mem:
            return False

        # 目标已软删除时幂等返回 True
        if mem.is_archived and mem.superseded_by == superseded_by:
            return True

        try:
            self.store.soft_delete(id, superseded_by)
            return True
        except ValueError:
            return False
