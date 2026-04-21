import unittest
from unittest.mock import patch
from aic.repl import start

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
        start(config)
        # Verify it printed the ready message
        mock_print.assert_any_call("aic ready")
        mock_print.assert_any_call("Exiting...")

if __name__ == '__main__':
    unittest.main()
