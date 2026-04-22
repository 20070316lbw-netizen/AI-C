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

class TestTUIRenderStream(unittest.TestCase):
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
        global TUIRenderer
        from aic.tui import TUIRenderer

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        # Patch the classes directly in the aic.tui module for each test
        self.layout_patcher = patch('aic.tui.Layout')
        self.console_patcher = patch('aic.tui.Console')

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
        self.layout_patcher.stop()
        self.console_patcher.stop()

    def test_render_stream_start(self):
        """Test that render_stream_start initializes streaming state and updates layout."""
        self.renderer.streaming = False
        self.renderer.stream_content = "previous content"

        with patch.object(self.renderer, '_update_layout') as mock_update_layout:
            self.renderer.render_stream_start()

            self.assertTrue(self.renderer.streaming)
            self.assertEqual(self.renderer.stream_content, "")
            mock_update_layout.assert_called_once()

if __name__ == '__main__':
    unittest.main()
