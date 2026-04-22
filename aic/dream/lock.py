import json
import os
import time
from pathlib import Path
from typing import Any, Dict


class DreamLock:
    def __init__(self, lock_path: Path, lock_timeout_h: float = 2.0):
        self.lock_path = lock_path
        self.lock_timeout_h = lock_timeout_h

    def get_state(self) -> Dict[str, Any]:
        """读取并返回完整 JSON，文件不存在返回 {}"""
        if not self.lock_path.exists():
            return {}
        try:
            content = self.lock_path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            return {}

    def is_stale(self) -> bool:
        """用 started_at 字段判断，而非 mtime"""
        state = self.get_state()
        if not state:
            return False
        started_at = state.get("started_at", time.time())
        return time.time() - started_at > self.lock_timeout_h * 3600

    def acquire(self, session_id: str) -> bool:
        """
        锁不存在 → 直接写入，返回 True
        锁存在 → 检查三种失效条件，任一满足则覆盖写入，返回 True
        锁存在且持有者活跃 → 返回 False
        """
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8")
                state = json.loads(content)
                pid = state.get("pid")

                can_acquire = False

                if pid is None:
                    # corrupted lock
                    can_acquire = True
                else:
                    # check process
                    try:
                        os.kill(pid, 0)
                        # Process exists, now check if stale
                        if self.is_stale():
                            can_acquire = True
                    except ProcessLookupError:
                        # Process doesn't exist anymore
                        can_acquire = True
                    except PermissionError:
                        # Process exists but we don't have permission to signal it
                        if self.is_stale():
                            can_acquire = True

            except Exception:
                # corrupted lock file
                can_acquire = True

            if not can_acquire:
                return False

        # Acquire lock
        state = {
            "pid": os.getpid(),
            "phase": 0,
            "started_at": time.time(),
            "session_id": session_id,
            "orient_data": {}
        }
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(json.dumps(state), encoding="utf-8")
        return True

    def release(self) -> None:
        """删除锁文件，忽略 FileNotFoundError"""
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def update_state(self, phase: int, orient_data: dict = None) -> None:
        """读取当前内容 → 更新 phase 和 orient_data → 写回"""
        if not self.lock_path.exists():
            raise RuntimeError("Cannot update state: lock file does not exist")

        state = self.get_state()
        if not state:
            raise RuntimeError("Cannot update state: lock file is corrupted or empty")

        state["phase"] = phase
        if orient_data is not None:
            state["orient_data"] = orient_data

        self.lock_path.write_text(json.dumps(state), encoding="utf-8")
