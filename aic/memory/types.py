from dataclasses import dataclass, field
from typing import Literal, Optional
import time
import uuid

MemoryType = Literal["user", "feedback", "project", "reference"]

@dataclass
class Memory:
    content: str
    type: MemoryType
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    source: Optional[str] = None        # 来源标记，如 "extractor" / "dream"
    session_id: Optional[str] = None    # 产生记忆的 session id，用于 debug
    is_archived: int = 0                # 软删除，不硬删
    is_processed: int = 0               # Dream 门控用，是否已被 dream 整理
    superseded_by: Optional[str] = None # 指向替代条目的 id
    meta: Optional[str] = None          # JSON 扩展字段，供 Dream 写入合并来源等
    version: int = 1                    # schema 版本，供未来迁移用
