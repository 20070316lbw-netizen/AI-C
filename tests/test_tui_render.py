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

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
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

            # Verify _update_layout was called
            mock_update_layout.assert_called_once()

    def test_render_status_with_large_tokens(self):
        """Test that tokens are correctly formatted with commas for large numbers."""
        provider = "anthropic"
        model = "claude-3"
        tokens = 1234567

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_status(provider, model, tokens)

            table_instance = self.MockTable.return_value
            table_instance.add_row.assert_called_once_with(
                "[dim][provider: anthropic][/dim]",
                "[dim][model: claude-3][/dim]",
                "[dim][tokens: 1,234,567][/dim]"
            )

            # Verify _update_layout was called
            mock_update_layout.assert_called_once()

    def test_clear_right(self):
        """Test that clear_right correctly resets the right_renderable property and updates layout."""
        # Setup an initial renderable state
        self.renderer.right_renderable = MagicMock()

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.clear_right()

            # Verify right_renderable is None
            self.assertIsNone(self.renderer.right_renderable)

            # Verify _update_layout was called
            mock_update_layout.assert_called_once()

    def test_render_message(self):
        """Test that render_message appends to messages and updates layout."""
        self.assertEqual(len(self.renderer.messages), 0)

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_message("user", "Hello World")

            self.assertEqual(len(self.renderer.messages), 1)
            self.assertEqual(self.renderer.messages[0], {"role": "user", "content": "Hello World"})
            mock_update_layout.assert_called_once()

    def test_render_stream_start(self):
        """Test render_stream_start initializes state and updates layout."""
        self.renderer.streaming = False
        self.renderer.stream_content = "some old content"

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_stream_start()

            self.assertTrue(self.renderer.streaming)
            self.assertEqual(self.renderer.stream_content, "")
            mock_update_layout.assert_called_once()

    def test_render_stream_chunk(self):
        """Test render_stream_chunk appends to stream_content and updates layout."""
        self.renderer.streaming = True
        self.renderer.stream_content = "Hello"

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_stream_chunk(" World")

            self.assertEqual(self.renderer.stream_content, "Hello World")
            mock_update_layout.assert_called_once()

    def test_render_stream_end(self):
        """Test render_stream_end updates state, appends message and updates layout."""
        self.renderer.streaming = True
        self.renderer.stream_content = "Hello World"
        self.assertEqual(len(self.renderer.messages), 0)

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_stream_end()

            self.assertFalse(self.renderer.streaming)
            self.assertEqual(self.renderer.stream_content, "")
            self.assertEqual(len(self.renderer.messages), 1)
            self.assertEqual(self.renderer.messages[0], {"role": "assistant", "content": "Hello World"})
            mock_update_layout.assert_called_once()

if __name__ == '__main__':
    unittest.main()
