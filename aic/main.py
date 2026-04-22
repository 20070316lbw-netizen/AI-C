"""
L0 入口层：argparse，参数解析，调起 repl
"""

import argparse
from pathlib import Path
from aic import repl
from aic import config
import aic.kairos as kairos
from aic.session import Session
from aic.memory.store import MemoryStore
from aic.dream.lock import DreamLock
from aic.dream.scheduler import DreamScheduler

def main():
    parser = argparse.ArgumentParser(description="aic — AI Coding Assistant")
    parser.add_argument("--provider", type=str, help="LLM Provider to use (e.g., deepseek, claude)")
    parser.add_argument("--model", type=str, help="Model name to use")
    args = parser.parse_args()

    cfg = config.get_config()

    if args.provider:
        cfg["provider"] = args.provider

    if args.model:
        provider_name = cfg.get("provider", "deepseek")
        if provider_name not in cfg:
            cfg[provider_name] = {}
        cfg[provider_name]["model"] = args.model

    # 初始化顺序：store → lock → scheduler
    session = Session(cfg)
    store = MemoryStore()
    lock = DreamLock(Path("~/.aic/.dream-lock").expanduser())
    scheduler = DreamScheduler(store, lock, cfg, session.session_id(), kairos.log_event)

    repl.start(cfg, session, store, scheduler)

if __name__ == "__main__":
    main()
