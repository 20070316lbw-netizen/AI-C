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

    def test_render_status_calls_update_layout(self):
        """Test that render_status calls _update_layout."""
        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_status("openai", "gpt-4", 1500)
            mock_update_layout.assert_called_once()

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

    def test_clear_right(self):
        """Test that clear_right sets right_renderable to None and updates layout."""
        self.renderer.right_renderable = "some_renderable"
        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.clear_right()
            self.assertIsNone(self.renderer.right_renderable)
            mock_update_layout.assert_called_once()

    def test_render_diff(self):
        """Test that render_diff computes diff properly, sets right_renderable and updates layout."""
        # Provide sample code to diff
        before = "line1\nline2\nline3\n"
        after = "line1\nline2 changed\nline3\nline4\n"
        filepath = "test.py"

        with patch.object(self.renderer, '_update_layout') as mock_update_layout, \
             patch('aic.tui.Panel') as mock_panel, \
             patch('aic.tui.Text') as mock_text_cls:

            mock_text_instance = mock_text_cls.return_value
            self.renderer.render_diff(filepath, before, after)

            # Text was created and appends were called
            mock_text_cls.assert_called_once()

            # additions=2 (line2 changed, line4), deletions=1 (line2)
            mock_text_instance.append.assert_any_call("\n✓ 2 additions, 1 deletions", style="dim")

            # Panel was created with the text and assigned to right_renderable
            mock_panel.assert_called_once_with(mock_text_instance, title="Diff: test.py", border_style="yellow")
            self.assertEqual(self.renderer.right_renderable, mock_panel.return_value)

            # Layout was updated
            mock_update_layout.assert_called_once()

if __name__ == '__main__':
    unittest.main()
