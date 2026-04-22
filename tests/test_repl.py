import unittest
from unittest.mock import patch, MagicMock
from aic.repl import start
from aic.session import Session
from aic.memory.store import MemoryStore
from aic.dream.scheduler import DreamScheduler
from aic.mcp.registry import MCPRegistry

class TestRepl(unittest.TestCase):
    @patch('builtins.print')
    @patch('builtins.input', side_effect=['/exit'])
    def test_start(self, mock_input, mock_print):
        # Provide a dummy config
        config = {
            "provider": "deepseek",
            "deepseek": {
                "api_key": "test_key",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com"
            }
        }
        mock_session = MagicMock(spec=Session)
        mock_session.poor_mode = False
        mock_session.poor_mode_reason = ""
        mock_store = MagicMock(spec=MemoryStore)
        mock_scheduler = MagicMock(spec=DreamScheduler)
        mock_registry = MagicMock(spec=MCPRegistry)

        with patch('aic.errors.console.print') as mock_console_print:
            start(config, mock_session, mock_store, mock_scheduler, mock_registry)
            # Verify it printed the ready message
            mock_console_print.assert_any_call("[bold green][✓] aic ready[/bold green]")
            mock_console_print.assert_any_call("[bold yellow][!] Exiting...[/bold yellow]")

if __name__ == '__main__':
    unittest.main()
