import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from aic.dream.consolidator import DreamResult
from aic.dream.lock import DreamLock
from aic.dream.scheduler import DreamScheduler


class TestDreamScheduler(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.lock_path = Path(self.test_dir) / ".dream-lock"
        self.session_id = "test_session_123"
        self.config = {
            "dream": {
                "min_unprocessed": 10,
                "min_interval_h": 12.0,
                "min_sessions": 3
            }
        }
        self.store = MagicMock()
        self.lock = DreamLock(self.lock_path)
        self.kairos_log = MagicMock()
        self.scheduler = DreamScheduler(
            store=self.store,
            lock=self.lock,
            config=self.config,
            session_id=self.session_id,
            kairos_log=self.kairos_log
        )

        # Mock os.path.expanduser to return our temp dir for logs
        self.log_dir = os.path.join(self.test_dir, "logs")
        os.makedirs(self.log_dir)
        self.expanduser_patcher = patch("os.path.expanduser")
        self.mock_expanduser = self.expanduser_patcher.start()
        self.mock_expanduser.side_effect = lambda x: self.log_dir if x == "~/.aic/logs" else x

    def tearDown(self):
        self.expanduser_patcher.stop()
        shutil.rmtree(self.test_dir)

    def _create_log(self, days_ago: int, event: str):
        d = datetime.today() - timedelta(days=days_ago)
        date_str = d.strftime("%Y-%m-%d")
        log_path = os.path.join(self.log_dir, f"{date_str}.jsonl")
        ts = time.time() - (days_ago * 86400)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "event": event}) + "\n")
        return ts

    def test_gate1_unprocessed(self):
        # Fail Gate 1
        self.store.count_unprocessed.return_value = 5
        self.assertFalse(self.scheduler.should_run())

        # Pass Gate 1, but fail Gate 2
        self.store.count_unprocessed.return_value = 15
        self._create_log(0, "dream_done") # ran today
        self.store.count_distinct_sessions.return_value = 1
        self.assertFalse(self.scheduler.should_run())

    def test_gate2_time_interval(self):
        self.store.count_unprocessed.return_value = 15
        self.store.count_distinct_sessions.return_value = 4

        # Last dream was 1 day ago (> 12h)
        self._create_log(1, "dream_done")
        self.assertTrue(self.scheduler.should_run())

    def test_gate2_distinct_sessions(self):
        self.store.count_unprocessed.return_value = 15

        # Last dream was today (< 12h), but wait, the condition is hours >= 12 AND sessions >= 3.
        # Wait, the prompt says "距上次 dream >= min_interval_h 小时 AND store.count_distinct_sessions() >= min_sessions"
        # So to pass Gate 2, BOTH must be true.
        # If last dream was today (< 12h), it should fail regardless of distinct sessions.
        self._create_log(0, "dream_done")

        self.store.count_distinct_sessions.return_value = 4 # >= 3 sessions
        self.assertFalse(self.scheduler.should_run()) # fails because < 12h

        # Now make time condition pass (> 12h)
        # Note: _create_log creates another log file, but the scheduler looks for the latest.
        # Since we already created a log for today (0 days ago), the last dream is STILL today.
        # So we need to reset the logs to test properly.
        # We can just change the mock instead of files.
        with patch.object(self.scheduler, "_last_dream_ts") as mock_last:
            # 1 day ago
            mock_last.return_value = time.time() - 86400
            self.store.count_distinct_sessions.return_value = 2 # fails sessions
            self.assertFalse(self.scheduler.should_run())

            self.store.count_distinct_sessions.return_value = 4 # passes sessions
            self.assertTrue(self.scheduler.should_run())

    def test_gate3_lock(self):
        self.store.count_unprocessed.return_value = 15
        # No logs -> passes gate 2

        # Gate 3 should pass when lock doesn't exist
        self.assertTrue(self.scheduler.should_run())

        # Gate 3 should fail if lock is active
        self.lock.acquire("another_session")
        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None # Process alive
            self.assertFalse(self.scheduler.should_run())

            # Process dead -> should pass
            mock_kill.side_effect = ProcessLookupError()
            self.assertTrue(self.scheduler.should_run())

    @patch("subprocess.Popen")
    def test_run_force_false(self, mock_popen):
        self.store.count_unprocessed.return_value = 15

        # Should run
        self.scheduler.run(force=False)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["aic-dream", "--session", self.session_id])
        self.assertTrue(kwargs["start_new_session"])

    @patch("aic.dream.scheduler.Consolidator")
    def test_run_force_true(self, MockConsolidator):
        mock_consolidator = MockConsolidator.return_value
        mock_consolidator.run.return_value = DreamResult(merged_count=5, archived_count=8, added_count=2, resolved_conflicts=3)

        self.store.count_unprocessed.return_value = 34

        # Bypass gates
        self.store.count_unprocessed.return_value = 0 # would fail gate 1 normally

        self.scheduler.run(force=True)

        self.kairos_log.assert_any_call("dream_start", self.session_id, {"force": True})
        self.kairos_log.assert_any_call("dream_done", self.session_id, {})
        mock_consolidator.run.assert_called_once()

        # Lock should be released
        self.assertFalse(self.lock_path.exists())

    @patch("aic.dream.scheduler.Consolidator")
    def test_run_force_true_lock_failed(self, MockConsolidator):
        # Acquire lock first
        self.lock.acquire("another_session")

        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None # Alive

            self.scheduler.run(force=True)

            MockConsolidator.return_value.run.assert_not_called()
            self.kairos_log.assert_not_called()

if __name__ == "__main__":
    unittest.main()
