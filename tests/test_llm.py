import unittest
from unittest.mock import patch, MagicMock
import httpx
from aic.llm import complete, LLMTimeoutError

class TestLLM(unittest.TestCase):
    @patch('httpx.post')
    def test_complete_timeout(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        with self.assertRaises(LLMTimeoutError):
            complete(
                prompt="Hello",
                provider="claude",
                config={"api_key": "test", "model": "test", "base_url": "test"}
            )

    @patch('httpx.post')
    def test_complete_claude_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [
                {"type": "text", "text": "Hi there"}
            ]
        }
        mock_post.return_value = mock_resp

        res = complete(
            prompt="Hello",
            provider="claude",
            config={"api_key": "test", "model": "test", "base_url": "test"}
        )
        self.assertEqual(res["content"], "Hi there")

    @patch('httpx.post')
    def test_complete_openai_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Hi there",
                        "tool_calls": []
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = complete(
            prompt="Hello",
            provider="openai_compat",
            config={"api_key": "test", "model": "test", "base_url": "test"}
        )
        self.assertEqual(res["content"], "Hi there")

if __name__ == '__main__':
    unittest.main()
