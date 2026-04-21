import json
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx

from aic.memory.extractor import MemoryExtractor
from aic.memory.store import MemoryStore
from aic.providers.claude import ClaudeProvider
from aic.providers.openai_compat import OpenAICompatProvider

class TestMemoryExtractor(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")
        self.provider = OpenAICompatProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com"
        )
        self.session_id = "test-session"
        self.extractor = MemoryExtractor(self.provider, self.store, self.session_id)

    def tearDown(self):
        self.extractor.shutdown()
        # Clean up possible logs created during tests
        log_dir = os.path.expanduser("~/.aic/logs")
        if os.path.exists(log_dir):
            for file in os.listdir(log_dir):
                try:
                    os.remove(os.path.join(log_dir, file))
                except Exception:
                    pass

    def test_clean_json_response(self):
        # Raw json
        raw = '[{"type": "user", "content": "hi"}]'
        self.assertEqual(self.extractor.clean_json_response(raw), raw)

        # Markdown wrapped
        wrapped = '```json\n[{"type": "user", "content": "hi"}]\n```'
        self.assertEqual(self.extractor.clean_json_response(wrapped), '[{"type": "user", "content": "hi"}]')

        # Markdown wrapped without language
        wrapped_no_lang = '```\n[{"type": "user", "content": "hi"}]\n```'
        self.assertEqual(self.extractor.clean_json_response(wrapped_no_lang), '[{"type": "user", "content": "hi"}]')

        # With leading/trailing spaces
        spaces = '   ```json\n[{"type": "user", "content": "hi"}]\n```   '
        self.assertEqual(self.extractor.clean_json_response(spaces), '[{"type": "user", "content": "hi"}]')

    @patch("httpx.post")
    def test_extract_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": '[{"type": "user", "content": "test fact"}]'}
            }]
        }
        mock_post.return_value = mock_resp

        self.extractor._extract("hello", "hi")

        memories = self.store.list()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "test fact")
        self.assertEqual(memories[0].type, "user")
        self.assertEqual(memories[0].source, "extractor")
        self.assertEqual(memories[0].session_id, "test-session")

    @patch("httpx.post")
    def test_extract_deduplication(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": '[{"type": "user", "content": "duplicate fact"}]'}
            }]
        }
        mock_post.return_value = mock_resp

        # Call twice
        self.extractor._extract("hello", "hi")
        self.extractor._extract("hello", "hi")

        # Store should only have 1 item
        memories = self.store.list()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "duplicate fact")

    @patch("httpx.post")
    def test_extract_type_downgrade(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": '[{"type": "UnknownType", "content": "some fact"}, {"type": "Project", "content": "project fact"}]'}
            }]
        }
        mock_post.return_value = mock_resp

        self.extractor._extract("hello", "hi")

        memories = self.store.list()
        self.assertEqual(len(memories), 2)

        types = {m.content: m.type for m in memories}
        self.assertEqual(types["some fact"], "user")  # Downgraded from unknown
        self.assertEqual(types["project fact"], "project") # Lowercased

    @patch("httpx.post")
    def test_extract_empty_array(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": '[]'}
            }]
        }
        mock_post.return_value = mock_resp

        self.extractor._extract("hello", "hi")

        memories = self.store.list()
        self.assertEqual(len(memories), 0)

    @patch("httpx.post")
    def test_extract_malformed_json_logs_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": 'not json'}
            }]
        }
        mock_post.return_value = mock_resp

        with patch.object(self.extractor, "_write_log") as mock_log:
            self.extractor._extract("hello", "hi")

            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            self.assertEqual(args[0], "extractor_error")
            self.assertTrue("error" in args[1])
            self.assertEqual(args[1]["raw"], "not json")

    @patch("httpx.post")
    def test_claude_provider(self, mock_post):
        claude_provider = ClaudeProvider(api_key="test", model="claude-test")
        extractor = MemoryExtractor(claude_provider, self.store, "test-session")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [{
                "text": '[{"type": "user", "content": "claude fact"}]'
            }]
        }
        mock_post.return_value = mock_resp

        extractor._extract("hello", "hi")

        memories = self.store.list()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "claude fact")

        extractor.shutdown()

    @patch("httpx.post")
    def test_content_truncation(self, mock_post):
        long_content = "A" * 600
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": json.dumps([{"type": "user", "content": long_content}])}
            }]
        }
        mock_post.return_value = mock_resp

        self.extractor._extract("hello", "hi")

        memories = self.store.list()
        self.assertEqual(len(memories), 1)
        self.assertEqual(len(memories[0].content), 500)
        self.assertEqual(memories[0].content, "A" * 500)

if __name__ == '__main__':
    unittest.main()
