"""
L4 Dream 层：三道门控 + executeAutoDream()
"""
import glob
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from aic.dream.consolidator import Consolidator, DreamResult
from aic.dream.lock import DreamLock
from aic.memory.store import MemoryStore

class DreamScheduler:
    def __init__(
        self,
        store: MemoryStore,
        lock: DreamLock,
        config: dict,
        session_id: str,
        kairos_log: Callable,
    ):
        self.store = store
        self.lock = lock
        self.config = config
        self.session_id = session_id
        self.kairos_log = kairos_log

    def _last_dream_ts(self) -> Optional[float]:
        """
        Reads ~/.aic/logs/ from the past 7 days.
        Finds the latest timestamp where event == "dream_done".
        Returns None if not found.
        """
        log_dir = os.path.expanduser("~/.aic/logs")
        if not os.path.exists(log_dir):
            return None

        today = datetime.today()
        latest_ts = None

        # Check logs for the past 7 days starting from today down to 6 days ago
        for i in range(7):
            d = today - timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            log_path = os.path.join(log_dir, f"{date_str}.jsonl")
            if os.path.exists(log_path):
                # Read file backwards? Nah, file shouldn't be huge, let's just parse
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                entry = json.loads(line)
                                if entry.get("event") == "dream_done" or entry.get("event_type") == "dream_done":
                                    ts = entry.get("ts")
                                    if ts is not None:
                                        if latest_ts is None or ts > latest_ts:
                                            latest_ts = ts
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass

        return latest_ts

    def should_run(self) -> bool:
        dream_config = self.config.get("dream", {})
        min_unprocessed = dream_config.get("min_unprocessed", 10)
        min_interval_h = dream_config.get("min_interval_h", 12.0)
        min_sessions = dream_config.get("min_sessions", 3)

        # Gate 1: Unprocessed memories
        if self.store.count_unprocessed() < min_unprocessed:
            return False

        # Gate 2: Time interval or Distinct sessions
        last_dream_ts = self._last_dream_ts()
        if last_dream_ts is not None:
            hours_since_last_dream = (time.time() - last_dream_ts) / 3600.0
            if hours_since_last_dream < min_interval_h or self.store.count_distinct_sessions() < min_sessions:
                return False

        # Gate 3: Lock existence/staleness (read-only check)
        # Process existence check handles read-only part. Should run if it can be acquired.
        # But we do not acquire it here!
        state = self.lock.get_state()
        if state:
            pid = state.get("pid")
            if pid is not None:
                try:
                    os.kill(pid, 0)
                    if not self.lock.is_stale():
                        return False # Lock exists, process alive, not stale
                except ProcessLookupError:
                    pass # Process dead, lock stale
                except PermissionError:
                    if not self.lock.is_stale():
                        return False # Process alive, we don't have permission, but not stale yet
        return True

    def run(self, force: bool = False) -> None:
        if not force:
            if not self.should_run():
                self.kairos_log("dream_skipped", self.session_id, {"reason": "gate_check_failed"})
                return

            # Subprocess
            subprocess.Popen(
                ["aic-dream", "--session", self.session_id],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        # Force = True
        if not self.lock.acquire(self.session_id):
            print("Dream 正在运行中")
            return

        self.kairos_log("dream_start", self.session_id, {"force": True})

        print("🌙 Dream 触发原因：force=True")
        print(f"📦 未处理记忆：{self.store.count_unprocessed()} 条")

        try:
            def tracking_log(event: str, sid: str, payload: dict):
                self.kairos_log(event, sid, payload)
                phase = payload.get("phase")
                if event == "dream_phase_start":
                    if phase == 1:
                        print("🔄 Phase 1/4 — Orient...")
                    elif phase == 2:
                        print("🔄 Phase 2/4 — Gather...")
                    elif phase == 3:
                        print("🔄 Phase 3/4 — Merge...")
                    elif phase == 4:
                        print("🔄 Phase 4/4 — Prune...")
                elif event == "dream_phase_done":
                    if phase == 1:
                        state = self.lock.get_state()
                        conflicts = state.get("orient_data", {}).get("conflicts", [])
                        print(f"✅ Phase 1 完成，发现 {len(conflicts)} 个冲突")
                    elif phase == 2:
                        print("✅ Phase 2 完成")
                    elif phase == 3:
                        print("✅ Phase 3 完成")

            consolidator = Consolidator(
                store=self.store,
                lock=self.lock,
                config=self.config,
                kairos_log=tracking_log,
                exclude_session_id=self.session_id
            )
            result = consolidator.run()

            print(f"✅ Dream 完成 | 合并 {result.merged} 条 · 归档 {result.archived} 条 · 新增 {result.added} 条 · 冲突解决 {result.conflicts_resolved} 个")

        except Exception as e:
            self.kairos_log("dream_error", self.session_id, {"error": str(e)})
            raise
        finally:
            self.lock.release()

        self.kairos_log("dream_done", self.session_id, {})
