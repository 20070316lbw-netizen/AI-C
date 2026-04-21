import json
import os
import time
from datetime import date
from typing import List, Dict

def log_event(event: str, session_id: str, payload: Dict) -> None:
    """追加写入 ~/.aic/logs/YYYY-MM-DD.jsonl，失败静默。"""
    try:
        date_str = date.today().strftime("%Y-%m-%d")

        log_dir = os.path.expanduser("~/.aic/logs")
        os.makedirs(log_dir, exist_ok=True)

        log_path = os.path.join(log_dir, f"{date_str}.jsonl")

        log_entry = {
            "ts": time.time(),
            "event": event,
            "session_id": session_id,
            "payload": payload
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def read_today() -> List[Dict]:
    """读取今日日志，返回事件列表，文件不存在返回 []。"""
    try:
        date_str = date.today().strftime("%Y-%m-%d")
        log_path = os.path.expanduser(f"~/.aic/logs/{date_str}.jsonl")

        if not os.path.exists(log_path):
            return []

        logs = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return logs
    except Exception:
        return []
