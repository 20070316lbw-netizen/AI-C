import unittest
from unittest.mock import MagicMock, patch
import sys

# Define mocks globally so they persist for the lifetime of the module
MOCK_RICH = MagicMock()
MOCK_CONSOLE = MagicMock()
MOCK_LAYOUT = MagicMock()
MOCK_LIVE = MagicMock()
MOCK_PANEL = MagicMock()
MOCK_TEXT = MagicMock()
MOCK_SYNTAX = MagicMock()
MOCK_TABLE = MagicMock()

class TestTUIRenderStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Apply sys.modules patches
        cls.patcher = patch.dict(sys.modules, {
            "rich": MOCK_RICH,
            "rich.console": MOCK_CONSOLE,
            "rich.layout": MOCK_LAYOUT,
            "rich.live": MOCK_LIVE,
            "rich.panel": MOCK_PANEL,
            "rich.text": MOCK_TEXT,
            "rich.syntax": MOCK_SYNTAX,
            "rich.table": MOCK_TABLE,
        })
        cls.patcher.start()

        # Now it is safe to import TUIRenderer
        global TUIRenderer, Table, Layout, Console
        from aic.tui import TUIRenderer, Table, Layout, Console

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        # Patch the classes directly in the aic.tui module for each test
        self.table_patcher = patch('aic.tui.Table')
        self.layout_patcher = patch('aic.tui.Layout')
        self.console_patcher = patch('aic.tui.Console')
        self.panel_patcher = patch('aic.tui.Panel')
        self.text_patcher = patch('aic.tui.Text')

        self.MockTable = self.table_patcher.start()
        self.MockLayout = self.layout_patcher.start()
        self.MockConsole = self.console_patcher.start()
        self.MockPanel = self.panel_patcher.start()
        self.MockText = self.text_patcher.start()

        # Setup console mock
        self.mock_console_instance = self.MockConsole.return_value
        self.mock_console_instance.width = 80

        # Setup layout mock
        self.mock_layout_instance = self.MockLayout.return_value
        self.mock_layout_instance.__getitem__.return_value = MagicMock()

        self.renderer = TUIRenderer()

    def tearDown(self):
        self.table_patcher.stop()
        self.layout_patcher.stop()
        self.console_patcher.stop()
        self.panel_patcher.stop()
        self.text_patcher.stop()

    def test_render_status_updates_renderable(self):
        """Test that render_status correctly creates a Table and updates status_renderable."""
        provider = "openai"
        model = "gpt-4"
        tokens = 1500

        self.renderer.render_status(provider, model, tokens)

        # Verify Table was initialized with specific style parameters
        self.MockTable.assert_called_once_with(
            show_header=False, show_edge=False, box=None, padding=(0, 2)
        )

        # Get the mocked Table instance
        table_instance = self.MockTable.return_value

        # Verify add_row was called with correctly formatted strings
        table_instance.add_row.assert_called_once_with(
            "[dim][provider: openai][/dim]",
            "[dim][model: gpt-4][/dim]",
            "[dim][tokens: 1,500][/dim]"
        )

        # Verify the renderer's status_renderable property was updated
        self.assertEqual(self.renderer.status_renderable, table_instance)

    def test_render_status_with_large_tokens(self):
        """Test that tokens are correctly formatted with commas for large numbers."""
        provider = "anthropic"
        model = "claude-3"
        tokens = 1234567

        self.renderer.render_status(provider, model, tokens)

        table_instance = self.MockTable.return_value
        table_instance.add_row.assert_called_once_with(
            "[dim][provider: anthropic][/dim]",
            "[dim][model: claude-3][/dim]",
            "[dim][tokens: 1,234,567][/dim]"
        )

    @patch('difflib.unified_diff')
    def test_render_diff(self, mock_unified_diff):
        """Test that render_diff correctly formats unified diff output."""
        mock_unified_diff.return_value = [
            "--- before.py\n",
            "+++ after.py\n",
            "@@ -1,3 +1,3 @@\n",
            " line 1\n",
            "-line 2\n",
            "+line 3\n"
        ]

        self.renderer.render_diff("test.py", "line 1\nline 2", "line 1\nline 3")

        self.MockConsole.return_value.width = 80

        # Verify right_renderable was updated to a Panel with formatted Text
        self.assertTrue(self.renderer.right_renderable is not None)
        self.MockPanel.assert_any_call(self.MockText.return_value, title="Diff: test.py", border_style="yellow")

        # Verify Text object received the right styling commands based on lines
        mock_text = self.MockText.return_value
        mock_text.append.assert_any_call("--- before.py\n", style="bold")
        mock_text.append.assert_any_call("+++ after.py\n", style="bold")
        mock_text.append.assert_any_call("@@ -1,3 +1,3 @@\n", style="cyan")
        mock_text.append.assert_any_call(" line 1\n")
        mock_text.append.assert_any_call("-line 2\n", style="on #3a1e1e")
        mock_text.append.assert_any_call("+line 3\n", style="on #1e3a1e")
        mock_text.append.assert_any_call("\n✓ 1 additions, 1 deletions", style="dim")

    def test_clear_right(self):
        """Test that clear_right sets right_renderable to None."""
        self.renderer.right_renderable = "Some renderable"
        self.renderer.clear_right()
        self.assertIsNone(self.renderer.right_renderable)

if __name__ == '__main__':
    unittest.main()
