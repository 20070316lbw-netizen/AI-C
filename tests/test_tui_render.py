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

class TestTUIRenderer(unittest.TestCase):
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

        self.MockTable = self.table_patcher.start()
        self.MockLayout = self.layout_patcher.start()
        self.MockConsole = self.console_patcher.start()

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


    @patch('aic.tui.Syntax')
    @patch('aic.tui.Panel')
    @patch('aic.errors.print_warning')
    def test_render_file(self, mock_print_warning, mock_panel, mock_syntax):
        """Test that render_file creates a Syntax and Panel correctly."""
        filepath = "test.py"
        content = "print('hello')\n" * 5

        self.renderer.render_file(filepath, content)

        mock_syntax.assert_called_once_with(content, 'py', theme="monokai", line_numbers=True)
        mock_panel.assert_any_call(mock_syntax.return_value, title=filepath, border_style="green")
        self.assertEqual(self.renderer.right_renderable, mock_panel.return_value)
        mock_print_warning.assert_not_called()

    @patch('aic.tui.Syntax')
    @patch('aic.tui.Panel')
    @patch('aic.errors.print_warning')
    def test_render_file_truncates_large_files(self, mock_print_warning, mock_panel, mock_syntax):
        """Test that render_file truncates files over 1000 lines."""
        filepath = "large.txt"
        content = "line\n" * 1005

        self.renderer.render_file(filepath, content)

        # Should be truncated to 1000 lines
        expected_content = "\n".join(["line"] * 1000)
        mock_syntax.assert_called_once_with(expected_content, 'txt', theme="monokai", line_numbers=True)
        self.assertEqual(self.renderer.right_renderable, mock_panel.return_value)
        mock_print_warning.assert_called_once_with(f"Display truncated at 1000 lines for {filepath} (full content still in context)")

    @patch('aic.tui.Text')
    @patch('aic.tui.Panel')
    @patch('difflib.unified_diff')
    def test_render_diff(self, mock_diff, mock_panel, mock_text):
        """Test that render_diff correctly parses difflib output and formats it using Text."""
        filepath = "changed.py"
        before = "a\nb\n"
        after = "a\nc\n"

        # Mock unified_diff output
        mock_diff.return_value = [
            "--- changed.py\n",
            "+++ changed.py\n",
            "@@ -1,2 +1,2 @@\n",
            " a\n",
            "-b\n",
            "+c\n"
        ]

        text_instance = mock_text.return_value

        self.renderer.render_diff(filepath, before, after)

        mock_diff.assert_called_once_with(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=filepath,
            tofile=filepath
        )

        # Verify styles were applied based on diff line prefixes
        text_instance.append.assert_any_call("--- changed.py\n", style="bold")
        text_instance.append.assert_any_call("+++ changed.py\n", style="bold")
        text_instance.append.assert_any_call("@@ -1,2 +1,2 @@\n", style="cyan")
        text_instance.append.assert_any_call(" a\n")
        text_instance.append.assert_any_call("-b\n", style="on #3a1e1e")
        text_instance.append.assert_any_call("+c\n", style="on #1e3a1e")

        # Verify summary line
        text_instance.append.assert_any_call("\n✓ 1 additions, 1 deletions", style="dim")

        mock_panel.assert_any_call(text_instance, title=f"Diff: {filepath}", border_style="yellow")
        self.assertEqual(self.renderer.right_renderable, mock_panel.return_value)

    def test_clear_right(self):
        """Test that clear_right sets right_renderable to None."""
        self.renderer.right_renderable = "Something"
        self.renderer.clear_right()
        self.assertIsNone(self.renderer.right_renderable)

if __name__ == '__main__':
    unittest.main()
