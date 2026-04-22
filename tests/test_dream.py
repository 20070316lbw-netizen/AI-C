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

    def test_last_dream_ts_errors(self):
        # 1. Missing log dir
        with patch("os.path.exists", side_effect=lambda path: False if path == self.log_dir else os.path.exists(path)):
            self.assertIsNone(self.scheduler._last_dream_ts())

        # 2. File with empty line and invalid JSON
        today = datetime.today()
        date_str = today.strftime("%Y-%m-%d")
        log_path = os.path.join(self.log_dir, f"{date_str}.jsonl")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n")  # Empty line
            f.write("invalid json {]\n")  # JSON decode error
            f.write('{"event": "dream_done", "ts": 12345.0}\n')

        self.assertEqual(self.scheduler._last_dream_ts(), 12345.0)

        # 3. File reading exception
        with patch("builtins.open", side_effect=Exception("Read error")):
            # Should catch the exception and return None since no valid lines were read
            self.assertIsNone(self.scheduler._last_dream_ts())

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

    def test_should_run_permission_error(self):
        self.store.count_unprocessed.return_value = 15
        self.lock.acquire("another_session")

        with patch('os.kill') as mock_kill:
            mock_kill.side_effect = PermissionError()

            # Not stale -> should not run
            with patch.object(self.lock, 'is_stale', return_value=False):
                self.assertFalse(self.scheduler.should_run())

            # Stale -> should run
            with patch.object(self.lock, 'is_stale', return_value=True):
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

    @patch("subprocess.Popen")
    def test_run_force_false_skipped(self, mock_popen):
        # Fail should_run (Gate 1)
        self.store.count_unprocessed.return_value = 5

        self.scheduler.run(force=False)

        mock_popen.assert_not_called()
        self.kairos_log.assert_called_once_with("dream_skipped", self.session_id, {"reason": "gate_check_failed"})

    @patch("aic.dream.scheduler.Consolidator")
    def test_run_force_true(self, MockConsolidator):
        mock_consolidator = MockConsolidator.return_value
        mock_consolidator.run.return_value = DreamResult(merged=5, archived=8, added=2, conflicts_resolved=3)

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
    def test_run_tracking_log(self, MockConsolidator):
        mock_consolidator = MockConsolidator.return_value
        mock_consolidator.run.return_value = DreamResult(merged=5, archived=8, added=2, conflicts_resolved=3)

        # We just invoke tracking_log manually after the run call to verify the branches.

        # Bypass gates
        self.store.count_unprocessed.return_value = 0

        self.scheduler.run(force=True)

        # Get the tracking_log function passed to Consolidator
        kwargs = MockConsolidator.call_args[1]
        tracking_log = kwargs['kairos_log']

        # Simulate phase start logs
        for phase in [1, 2, 3, 4]:
            tracking_log("dream_phase_start", self.session_id, {"phase": phase})

        # Simulate phase done logs
        with patch.object(self.lock, 'get_state', return_value={"orient_data": {"conflicts": ["c1", "c2"]}}):
            tracking_log("dream_phase_done", self.session_id, {"phase": 1})

        for phase in [2, 3]:
            tracking_log("dream_phase_done", self.session_id, {"phase": phase})

        # Verify kairos_log was called for all these tracking logs
        # 1 start + 1 done + 4 phase start + 3 phase done = 9 total
        self.assertEqual(self.kairos_log.call_count, 9)

    @patch("aic.dream.scheduler.Consolidator")
    def test_run_exception(self, MockConsolidator):
        mock_consolidator = MockConsolidator.return_value
        mock_consolidator.run.side_effect = Exception("Test Consolidator Error")

        # Bypass gates
        self.store.count_unprocessed.return_value = 0

        # Run and check that the exception propagates
        with self.assertRaises(Exception) as context:
            self.scheduler.run(force=True)

        self.assertEqual(str(context.exception), "Test Consolidator Error")

        # Verify kairos_log was called with dream_error
        self.kairos_log.assert_any_call("dream_error", self.session_id, {"error": "Test Consolidator Error"})

        # Lock should be released via finally block
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

from aic.memory.types import Memory

class TestDreamAgent(unittest.TestCase):
    def setUp(self):
        self.store = MagicMock()
        from aic.dream.agent import DreamAgent
        self.agent = DreamAgent(self.store, "test")

    def test_read_memory(self):
        # Test not found
        self.store.get.return_value = None
        self.assertIsNone(self.agent.read_memory("missing_id"))

        # Test found
        mock_mem = Memory(id="test_id", content="test content", type="user")
        self.store.get.return_value = mock_mem

        result = self.agent.read_memory("test_id")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "test_id")
        self.assertEqual(result["content"], "test content")
        self.assertEqual(result["type"], "user")

    def test_list_memories(self):
        # Test empty list
        self.store.list_by_type.return_value = []
        self.assertEqual(self.agent.list_memories("user"), [])

        # Test list with limit
        mock_mems = [
            Memory(id=f"id_{i}", content=f"content {i}", type="user")
            for i in range(5)
        ]
        self.store.list_by_type.return_value = mock_mems

        # limit = 2
        result_limited = self.agent.list_memories("user", limit=2)
        self.assertEqual(len(result_limited), 2)
        self.assertEqual(result_limited[0]["id"], "id_0")
        self.assertEqual(result_limited[1]["id"], "id_1")

        # limit = 10 (more than available)
        result_all = self.agent.list_memories("user", limit=10)
        self.assertEqual(len(result_all), 5)

    def test_add_memory_dedup(self):
        # mock existing
        mock_mem = MagicMock()
        mock_mem.id = "mock_hash"
        self.store.get.return_value = mock_mem

        mem_id = self.agent.add_memory("test content", "user")
        self.assertEqual(mem_id, "mock_hash")
        self.store.add.assert_not_called()

    def test_soft_delete_memory(self):
        # Mock target doesn't exist
        self.store.get.side_effect = lambda id: None
        self.assertFalse(self.agent.soft_delete_memory("a", "b"))

        # Mock valid soft delete
        mock_target = MagicMock()
        mock_mem = MagicMock()
        mock_mem.is_archived = False
        self.store.get.side_effect = lambda id: mock_target if id == "b" else mock_mem

        self.assertTrue(self.agent.soft_delete_memory("a", "b"))
        self.store.soft_delete.assert_called_with("a", "b")

class TestConsolidator(unittest.TestCase):
    def setUp(self):
        self.store = MagicMock()
        self.lock = MagicMock()
        self.config = {"provider": "claude", "claude": {"model": "test"}, "dream": {"max_memories_per_type": 1}}
        self.kairos_log = MagicMock()
        from aic.dream.consolidator import Consolidator
        self.consolidator = Consolidator(self.store, self.lock, self.config, self.kairos_log)

    @patch('aic.dream.consolidator.complete')
    def test_phase_execution_and_resume(self, mock_complete):
        # start from phase 2
        self.lock.get_state.return_value = {"phase": 1, "orient_data": {"summary": "test", "conflicts": []}}

        mock_complete.return_value = {"content": "", "tool_calls": []}

        res = self.consolidator.run()

        # lock should have updated states for phases 2, 3, 4
        self.lock.update_state.assert_any_call(phase=2, orient_data=self.consolidator._orient_result)
        self.lock.update_state.assert_any_call(phase=3, orient_data=self.consolidator._orient_result)
        self.lock.update_state.assert_any_call(phase=4, orient_data=self.consolidator._orient_result)

    def test_phase4_archiving(self):
        self.lock.get_state.return_value = {"phase": 3, "orient_data": {}}

        mock_mem1 = MagicMock()
        mock_mem1.id = "id1"
        mock_mem2 = MagicMock()
        mock_mem2.id = "id2"

        # return excess for user
        def mock_list_by_type(t, order_by=None):
            if t == "user": return [mock_mem1, mock_mem2]
            return []
        self.store.list_by_type.side_effect = mock_list_by_type

        self.consolidator.run()

        # max is 1, so excess should be archived
        self.store.archive_many.assert_called_with(["id2"])
