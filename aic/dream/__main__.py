import argparse
import sys
from pathlib import Path

from aic.config import get_config
from aic.dream.consolidator import Consolidator
from aic.dream.lock import DreamLock
from aic.memory.store import MemoryStore


def main():
    parser = argparse.ArgumentParser(description="AIC Dream Background Process")
    parser.add_argument("--session", required=True, help="Session ID triggering the dream")
    parser.add_argument("--force", action="store_true", help="Force run synchronously (used for testing mostly)")
    args = parser.parse_args()

    config = get_config()
    store = MemoryStore()
    lock_path = Path("~/.aic/.dream-lock").expanduser()
    lock = DreamLock(lock_path)

    # In background mode, if we can't acquire the lock, we just exit silently
    if not lock.acquire(args.session):
        if args.force:
            print("Dream 正在运行中")
        sys.exit(0)

    from aic.kairos import log_event
    log_event("dream_start", args.session, {"force": args.force})

    try:
        consolidator = Consolidator(
            store=store,
            lock=lock,
            config=config,
            kairos_log=log_event,
            exclude_session_id=args.session
        )
        consolidator.run()
        log_event("dream_done", args.session, {})
    except Exception as e:
        import traceback
        log_event("dream_error", args.session, {"error": str(e), "trace": traceback.format_exc()})
        raise
    finally:
        lock.release()


if __name__ == "__main__":
    main()
