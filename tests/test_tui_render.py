import unittest
from unittest.mock import MagicMock, patch, call
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
        global TUIRenderer, Table, Layout, Console, Panel, Text, Syntax
        from aic.tui import TUIRenderer, Table, Layout, Console, Panel, Text, Syntax

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
        self.syntax_patcher = patch('aic.tui.Syntax')

        self.MockTable = self.table_patcher.start()
        self.MockLayout = self.layout_patcher.start()
        self.MockConsole = self.console_patcher.start()
        self.MockPanel = self.panel_patcher.start()
        self.MockText = self.text_patcher.start()
        self.MockSyntax = self.syntax_patcher.start()

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
        self.syntax_patcher.stop()

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

    def test_render_message(self):
        """Test that render_message correctly appends the message and updates layout."""
        self.renderer.render_message("user", "Hello")
        self.assertEqual(len(self.renderer.messages), 1)
        self.assertEqual(self.renderer.messages[0], {"role": "user", "content": "Hello"})

        # Verify update layout logic (left panel built)
        # We can't strictly check the exact rendering but we know _update_layout is called
        # if left panel update is attempted.
        self.mock_layout_instance.__getitem__.assert_called()

    def test_clear_right(self):
        """Test clear_right sets right_renderable to None."""
        self.renderer.right_renderable = "Something"
        self.renderer.clear_right()
        self.assertIsNone(self.renderer.right_renderable)

    def test_render_file_normal(self):
        """Test render_file with a normal sized file."""
        filepath = "test.py"
        content = "print('hello')"

        self.renderer.render_file(filepath, content)

        self.MockSyntax.assert_any_call(
            content, 'py', theme="monokai", line_numbers=True
        )
        self.MockPanel.assert_any_call(
            self.MockSyntax.return_value, title=filepath, border_style="green"
        )
        self.assertEqual(self.renderer.right_renderable, self.MockPanel.return_value)

    @patch('aic.errors.print_warning')
    def test_render_file_truncated(self, mock_print_warning):
        """Test render_file with a file larger than 1000 lines."""
        filepath = "large.txt"
        lines = [f"line {i}" for i in range(1005)]
        content = "\n".join(lines)

        self.renderer.render_file(filepath, content)

        truncated_content = "\n".join(lines[:1000])
        self.MockSyntax.assert_any_call(
            truncated_content, 'txt', theme="monokai", line_numbers=True
        )
        mock_print_warning.assert_called_once()
        self.assertIn("truncated", mock_print_warning.call_args[0][0])

    def test_render_diff(self):
        """Test render_diff correctly processes unified diff lines."""
        filepath = "test.py"
        before = "line1\nline2\n"
        after = "line1\nline3\n"

        mock_text_instance = self.MockText.return_value

        self.renderer.render_diff(filepath, before, after)

        self.MockPanel.assert_any_call(
            mock_text_instance, title=f"Diff: {filepath}", border_style="yellow"
        )
        self.assertEqual(self.renderer.right_renderable, self.MockPanel.return_value)

        # We can inspect the calls to text.append to check styling logic
        # unified_diff output looks roughly like:
        # --- test.py
        # +++ test.py
        # @@ -1,2 +1,2 @@
        #  line1
        # -line2
        # +line3

        append_calls = mock_text_instance.append.call_args_list

        # Verify additions/deletions counts are correctly appended at the end
        last_call = append_calls[-1]
        self.assertEqual(last_call[0][0], "\n✓ 1 additions, 1 deletions")
        self.assertEqual(last_call[1]["style"], "dim")

if __name__ == '__main__':
    unittest.main()
