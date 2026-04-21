import os
import unittest
from unittest.mock import patch, MagicMock

from aic.config import get_config, _get_raw_config, DEFAULT_CONFIG
from aic.session import Session
from aic.providers.openai_compat import OpenAICompatProvider


class TestSmoke(unittest.TestCase):
    def setUp(self):
        # Clear lru_cache to ensure isolation
        _get_raw_config.cache_clear()

    @patch("os.environ", {})
    @patch("pathlib.Path.is_file", return_value=False)
    def test_config_defaults(self, mock_is_file):
        config = get_config()
        self.assertEqual(config["provider"], "deepseek")
        self.assertEqual(config["deepseek"]["model"], "deepseek-chat")
        self.assertEqual(config["claude"]["model"], "claude-sonnet-4-20250514")

    @patch("httpx.stream")
    def test_openai_compat_stream(self, mock_stream):
        provider = OpenAICompatProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com"
        )
        messages = [{"role": "user", "content": "hi"}]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            '',
            'data: {"choices":[{"delta":{"content":" world"}}]}',
            'data: [DONE]',
            ''
        ]

        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        result = list(provider.stream(messages))
        self.assertEqual(result, ["Hello", " world"])

    def test_session_add_and_clear(self):
        config = get_config()
        session = Session(config)

        session.add_user("hello")
        session.add_assistant("hi there")

        messages = session.get_messages()
        # Ensure context loading doesn't break basic message logic
        user_msgs = [m for m in messages if m["role"] == "user"]
        ast_msgs = [m for m in messages if m["role"] == "assistant"]

        self.assertEqual(len(user_msgs), 1)
        self.assertEqual(user_msgs[0]["content"], "hello")
        self.assertEqual(len(ast_msgs), 1)
        self.assertEqual(ast_msgs[0]["content"], "hi there")

        session.clear()

        cleared_msgs = session.get_messages()
        self.assertEqual(len([m for m in cleared_msgs if m["role"] in ["user", "assistant"]]), 0)

    @patch("httpx.stream")
    def test_stream_http_error(self, mock_stream):
        provider = OpenAICompatProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com"
        )
        messages = [{"role": "user", "content": "hi"}]

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.read.return_value = b'Internal Server Error'

        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        result = list(provider.stream(messages))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] HTTP 500 — Internal Server Error')

    @patch("httpx.stream")
    def test_stream_network_error(self, mock_stream):
        provider = OpenAICompatProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com"
        )
        messages = [{"role": "user", "content": "hi"}]

        mock_stream.side_effect = Exception("Connection reset by peer")

        result = list(provider.stream(messages))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] 网络异常 — Connection reset by peer')


if __name__ == '__main__':
    unittest.main()
