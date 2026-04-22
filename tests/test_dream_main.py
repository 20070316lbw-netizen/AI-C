import unittest
from unittest.mock import patch, MagicMock
import sys

from aic.dream.__main__ import main

class TestDreamMain(unittest.TestCase):
    @patch("aic.dream.__main__.get_config")
    @patch("aic.dream.__main__.MemoryStore")
    @patch("aic.dream.__main__.DreamLock")
    @patch("sys.exit")
    def test_lock_acquire_fails_no_force(self, mock_exit, mock_lock_cls, mock_store_cls, mock_get_config):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = False

        test_args = ["aic-dream", "--session", "test_session"]
        with patch.object(sys, "argv", test_args):
            main()

        mock_lock.acquire.assert_called_once_with("test_session")
        mock_exit.assert_called_once_with(0)

    @patch("builtins.print")
    @patch("aic.dream.__main__.get_config")
    @patch("aic.dream.__main__.MemoryStore")
    @patch("aic.dream.__main__.DreamLock")
    @patch("sys.exit")
    def test_lock_acquire_fails_with_force(self, mock_exit, mock_lock_cls, mock_store_cls, mock_get_config, mock_print):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = False

        test_args = ["aic-dream", "--session", "test_session", "--force"]
        with patch.object(sys, "argv", test_args):
            main()

        mock_lock.acquire.assert_called_once_with("test_session")
        mock_print.assert_called_once_with("Dream 正在运行中")
        mock_exit.assert_called_once_with(0)

    @patch("aic.dream.__main__.Consolidator")
    @patch("aic.kairos.log_event")
    @patch("aic.dream.__main__.get_config")
    @patch("aic.dream.__main__.MemoryStore")
    @patch("aic.dream.__main__.DreamLock")
    def test_successful_run(self, mock_lock_cls, mock_store_cls, mock_get_config, mock_log_event, mock_consolidator_cls):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = True

        mock_consolidator = mock_consolidator_cls.return_value

        test_args = ["aic-dream", "--session", "test_session", "--force"]
        with patch.object(sys, "argv", test_args):
            main()

        mock_lock.acquire.assert_called_once_with("test_session")
        mock_log_event.assert_any_call("dream_start", "test_session", {"force": True})

        mock_consolidator_cls.assert_called_once_with(
            store=mock_store_cls.return_value,
            lock=mock_lock,
            config=mock_get_config.return_value,
            kairos_log=mock_log_event,
            exclude_session_id="test_session"
        )
        mock_consolidator.run.assert_called_once()

        mock_log_event.assert_any_call("dream_done", "test_session", {})
        mock_lock.release.assert_called_once()

    @patch("aic.dream.__main__.Consolidator")
    @patch("aic.kairos.log_event")
    @patch("aic.dream.__main__.get_config")
    @patch("aic.dream.__main__.MemoryStore")
    @patch("aic.dream.__main__.DreamLock")
    def test_exception_in_run(self, mock_lock_cls, mock_store_cls, mock_get_config, mock_log_event, mock_consolidator_cls):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = True

        mock_consolidator = mock_consolidator_cls.return_value
        mock_consolidator.run.side_effect = ValueError("Test error")

        test_args = ["aic-dream", "--session", "test_session"]
        with patch.object(sys, "argv", test_args):
            with self.assertRaises(ValueError):
                main()

        mock_lock.acquire.assert_called_once_with("test_session")
        mock_log_event.assert_any_call("dream_start", "test_session", {"force": False})

        # Check if dream_error was logged
        error_log_call = [call for call in mock_log_event.call_args_list if call.args[0] == "dream_error"]
        self.assertEqual(len(error_log_call), 1)
        self.assertEqual(error_log_call[0].args[1], "test_session")
        self.assertEqual(error_log_call[0].args[2]["error"], "Test error")
        self.assertIn("Traceback", error_log_call[0].args[2]["trace"])

        # Ensure lock is still released
        mock_lock.release.assert_called_once()

if __name__ == "__main__":
    unittest.main()
