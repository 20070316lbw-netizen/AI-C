import unittest
from unittest.mock import patch, MagicMock
import sys

from aic.dream.__main__ import main

class TestDreamMain(unittest.TestCase):
    @patch('aic.dream.__main__.get_config')
    @patch('aic.dream.__main__.MemoryStore')
    @patch('aic.dream.__main__.DreamLock')
    @patch('aic.dream.__main__.Consolidator')
    @patch('aic.kairos.log_event')
    def test_main_success(self, mock_log_event, mock_consolidator_cls, mock_lock_cls, mock_store_cls, mock_get_config):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = True
        mock_consolidator = mock_consolidator_cls.return_value

        with patch('sys.argv', ['aic-dream', '--session', 'test_session']):
            main()

        mock_lock.acquire.assert_called_with('test_session')
        mock_log_event.assert_any_call('dream_start', 'test_session', {'force': False})
        mock_consolidator.run.assert_called_once()
        mock_log_event.assert_any_call('dream_done', 'test_session', {})
        mock_lock.release.assert_called_once()

    @patch('aic.dream.__main__.get_config')
    @patch('aic.dream.__main__.MemoryStore')
    @patch('aic.dream.__main__.DreamLock')
    @patch('aic.kairos.log_event')
    def test_main_lock_failed(self, mock_log_event, mock_lock_cls, mock_store_cls, mock_get_config):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = False

        with patch('sys.argv', ['aic-dream', '--session', 'test_session']):
            with self.assertRaises(SystemExit) as cm:
                main()

        self.assertEqual(cm.exception.code, 0)
        mock_log_event.assert_not_called()

    @patch('builtins.print')
    @patch('aic.dream.__main__.get_config')
    @patch('aic.dream.__main__.MemoryStore')
    @patch('aic.dream.__main__.DreamLock')
    @patch('aic.kairos.log_event')
    def test_main_lock_failed_force(self, mock_log_event, mock_lock_cls, mock_store_cls, mock_get_config, mock_print):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = False

        with patch('sys.argv', ['aic-dream', '--session', 'test_session', '--force']):
            with self.assertRaises(SystemExit) as cm:
                main()

        self.assertEqual(cm.exception.code, 0)
        mock_print.assert_called_with("Dream 正在运行中")
        mock_log_event.assert_not_called()

    @patch('aic.dream.__main__.get_config')
    @patch('aic.dream.__main__.MemoryStore')
    @patch('aic.dream.__main__.DreamLock')
    @patch('aic.dream.__main__.Consolidator')
    @patch('aic.kairos.log_event')
    def test_main_exception(self, mock_log_event, mock_consolidator_cls, mock_lock_cls, mock_store_cls, mock_get_config):
        mock_lock = mock_lock_cls.return_value
        mock_lock.acquire.return_value = True
        mock_consolidator = mock_consolidator_cls.return_value
        mock_consolidator.run.side_effect = ValueError("test error")

        with patch('sys.argv', ['aic-dream', '--session', 'test_session']):
            with self.assertRaises(ValueError):
                main()

        mock_log_event.assert_any_call('dream_start', 'test_session', {'force': False})

        # Check that dream_error was logged
        calls = mock_log_event.call_args_list
        error_call = [c for c in calls if c[0][0] == 'dream_error']
        self.assertEqual(len(error_call), 1)
        self.assertEqual(error_call[0][0][1], 'test_session')
        self.assertEqual(error_call[0][0][2]['error'], 'test error')
        self.assertIn('Traceback', error_call[0][0][2]['trace'])

        mock_lock.release.assert_called_once()

if __name__ == "__main__":
    unittest.main()
