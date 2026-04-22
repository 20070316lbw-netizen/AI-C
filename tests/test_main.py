import unittest
from unittest.mock import patch, MagicMock
from aic.main import main
from aic import config

class TestMain(unittest.TestCase):
    def setUp(self):
        config._get_raw_config.cache_clear()

    @patch('sys.argv', ['aic'])
    @patch('aic.main.config.get_config')
    @patch('aic.main.Session')
    @patch('aic.main.MemoryStore')
    @patch('aic.main.DreamLock')
    @patch('aic.main.DreamScheduler')
    @patch('aic.main.MCPRegistry')
    @patch('aic.main.MCPLoader')
    @patch('aic.main.repl.start')
    @patch('aic.main.atexit.register')
    def test_main_default_args(self, mock_atexit, mock_start, mock_mcp_loader, mock_mcp_registry,
                               mock_scheduler, mock_lock, mock_store, mock_session, mock_get_config):
        mock_get_config.return_value = {"provider": "deepseek"}
        mock_loader_instance = mock_mcp_loader.return_value
        mock_loader_instance.load.return_value = 0

        main()

        mock_get_config.assert_called_once()
        mock_session.assert_called_once()
        mock_store.assert_called_once()
        mock_lock.assert_called_once()
        mock_scheduler.assert_called_once()
        mock_mcp_registry.assert_called_once()
        mock_mcp_loader.assert_called_once()
        mock_loader_instance.load.assert_called_once()
        mock_atexit.assert_called_once()
        mock_start.assert_called_once()

    @patch('sys.argv', ['aic', '--provider', 'claude', '--model', 'claude-3-sonnet'])
    @patch('aic.main.config.get_config')
    @patch('aic.main.Session')
    @patch('aic.main.MemoryStore')
    @patch('aic.main.DreamLock')
    @patch('aic.main.DreamScheduler')
    @patch('aic.main.MCPRegistry')
    @patch('aic.main.MCPLoader')
    @patch('aic.main.repl.start')
    @patch('aic.main.atexit.register')
    def test_main_with_provider_and_model_args(self, mock_atexit, mock_start, mock_mcp_loader, mock_mcp_registry,
                               mock_scheduler, mock_lock, mock_store, mock_session, mock_get_config):

        mock_cfg = {"provider": "deepseek", "claude": {}}
        mock_get_config.return_value = mock_cfg
        mock_loader_instance = mock_mcp_loader.return_value
        mock_loader_instance.load.return_value = 1

        with patch('builtins.print') as mock_print:
            main()

        self.assertEqual(mock_cfg["provider"], "claude")
        self.assertEqual(mock_cfg["claude"]["model"], "claude-3-sonnet")
        mock_print.assert_called_with("[MCP] 已加载 1 个 server")

    @patch('sys.argv', ['aic', '--model', 'o1'])
    @patch('aic.main.config.get_config')
    @patch('aic.main.Session')
    @patch('aic.main.MemoryStore')
    @patch('aic.main.DreamLock')
    @patch('aic.main.DreamScheduler')
    @patch('aic.main.MCPRegistry')
    @patch('aic.main.MCPLoader')
    @patch('aic.main.repl.start')
    @patch('aic.main.atexit.register')
    def test_main_with_only_model_arg_no_provider_in_cfg(self, mock_atexit, mock_start, mock_mcp_loader, mock_mcp_registry,
                               mock_scheduler, mock_lock, mock_store, mock_session, mock_get_config):

        mock_cfg = {"provider": "openai"}
        mock_get_config.return_value = mock_cfg
        mock_loader_instance = mock_mcp_loader.return_value
        mock_loader_instance.load.return_value = 0

        with patch('builtins.print') as mock_print:
            main()

        self.assertEqual(mock_cfg["provider"], "openai")
        self.assertEqual(mock_cfg["openai"]["model"], "o1")
        mock_print.assert_not_called()

if __name__ == '__main__':
    unittest.main()
