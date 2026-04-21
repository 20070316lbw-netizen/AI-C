import unittest
from unittest.mock import patch, MagicMock

from aic.providers.base import BaseProvider
from aic.providers.claude import ClaudeProvider
from aic.providers.openai_compat import OpenAICompatProvider

class TestBaseProvider(unittest.TestCase):
    def test_cannot_instantiate_base_provider(self):
        with self.assertRaises(TypeError):
            BaseProvider()

class TestOpenAICompatProvider(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com"
        )
        self.messages = [{"role": "user", "content": "hi"}]

    def test_properties(self):
        self.assertEqual(self.provider.name, "openai_compat")
        self.assertEqual(self.provider.model, "test-model")

    @patch("httpx.stream")
    def test_stream_success(self, mock_stream):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            '',
            'data: {"choices":[{"delta":{"content":" world"}}]}',
            'data: [DONE]',
            ''
        ]

        # Configure the context manager mock
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the results
        self.assertEqual(result, ["Hello", " world"])

        # Verify the httpx.stream call
        mock_stream.assert_called_once_with(
            "POST",
            "https://api.test.com/chat/completions",
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            json={
                "model": "test-model",
                "messages": self.messages,
                "stream": True,
            },
            timeout=60.0
        )

    @patch("httpx.stream")
    def test_stream_http_error(self, mock_stream):
        # Setup mock response for HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.read.return_value = b'{"error": {"message": "rate limit exceeded"}}'

        # Configure the context manager mock
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the result is the formatted error
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] HTTP 429 — {"error": {"message": "rate limit exceeded"}}')

    @patch("httpx.stream")
    def test_stream_network_error(self, mock_stream):
        # Setup mock to raise an exception
        mock_stream.side_effect = Exception("Connection refused")

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the result is the formatted error
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] 网络异常 — Connection refused')


class TestClaudeProvider(unittest.TestCase):
    def setUp(self):
        self.provider = ClaudeProvider(
            api_key="test-key",
            model="test-model"
        )
        self.messages = [{"role": "user", "content": "hi"}]

    def test_properties(self):
        self.assertEqual(self.provider.name, "claude")
        self.assertEqual(self.provider.model, "test-model")

    @patch("httpx.stream")
    def test_stream_success(self, mock_stream):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            'event: message_start',
            'data: {"type": "message_start", "message": {}}',
            '',
            'event: content_block_delta',
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}',
            '',
            'event: content_block_delta',
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " Claude"}}',
            '',
            'event: message_stop',
            'data: {"type": "message_stop"}',
            ''
        ]

        # Configure the context manager mock
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the results
        self.assertEqual(result, ["Hello", " Claude"])

        # Verify the httpx.stream call
        mock_stream.assert_called_once_with(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": "test-key",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "test-model",
                "messages": self.messages,
                "max_tokens": 8096,
                "stream": True,
            },
            timeout=60.0
        )

    @patch("httpx.stream")
    def test_stream_http_error(self, mock_stream):
        # Setup mock response for HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.read.return_value = b'{"error": {"message": "invalid api key"}}'

        # Configure the context manager mock
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the result is the formatted error
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] HTTP 401 — {"error": {"message": "invalid api key"}}')

    @patch("httpx.stream")
    def test_stream_network_error(self, mock_stream):
        # Setup mock to raise an exception
        mock_stream.side_effect = Exception("Connection refused")

        # Consume the generator
        result = list(self.provider.stream(self.messages))

        # Verify the result is the formatted error
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], '[错误] 网络异常 — Connection refused')

if __name__ == '__main__':
    unittest.main()
