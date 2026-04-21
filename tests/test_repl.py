import unittest
from unittest.mock import patch
from aic.repl import start

class TestRepl(unittest.TestCase):
    @patch('builtins.print')
    def test_start(self, mock_print):
        start()
        mock_print.assert_called_once_with("aic ready")

if __name__ == '__main__':
    unittest.main()
