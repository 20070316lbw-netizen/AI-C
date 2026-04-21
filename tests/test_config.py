import unittest
from unittest.mock import patch, mock_open
import os
from pathlib import Path

from aic.config import get_config, DEFAULT_CONFIG, _get_raw_config

class TestConfig(unittest.TestCase):
    def setUp(self):
        # Clear environment variables to avoid test contamination
        self.env_patcher = patch.dict(os.environ, clear=True)
        self.env_patcher.start()
        # Clear config cache
        _get_raw_config.cache_clear()

    def tearDown(self):
        self.env_patcher.stop()

    @patch('pathlib.Path.is_file', return_value=False)
    def test_default_config(self, mock_is_file):
        """Test that default config is returned when no config.toml exists and no env vars are set."""
        config = get_config()
        self.assertEqual(config, DEFAULT_CONFIG)

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data=b'provider = "claude"\n[claude]\napi_key = "toml_key"\n')
    def test_toml_loading(self, mock_file, mock_is_file):
        """Test that config.toml overrides default config."""
        config = get_config()
        self.assertEqual(config["provider"], "claude")
        self.assertEqual(config["claude"]["api_key"], "toml_key")
        # Ensure deep merging works (other claude fields remain)
        self.assertEqual(config["claude"]["model"], DEFAULT_CONFIG["claude"]["model"])
        self.assertEqual(config["deepseek"]["api_key"], "")

    @patch('pathlib.Path.is_file', return_value=False)
    def test_env_overrides(self, mock_is_file):
        """Test that environment variables override defaults."""
        os.environ["AIC_PROVIDER"] = "gemini"
        os.environ["ANTHROPIC_API_KEY"] = "env_claude_key"
        os.environ["DEEPSEEK_API_KEY"] = "env_ds_key"
        os.environ["GEMINI_API_KEY"] = "env_gemini_key"

        config = get_config()
        self.assertEqual(config["provider"], "gemini")
        self.assertEqual(config["claude"]["api_key"], "env_claude_key")
        self.assertEqual(config["deepseek"]["api_key"], "env_ds_key")
        self.assertEqual(config["gemini"]["api_key"], "env_gemini_key")

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data=b'provider = "claude"\n[deepseek]\napi_key = "toml_ds_key"\n')
    def test_precedence(self, mock_file, mock_is_file):
        """Test that env vars override TOML, which overrides defaults."""
        os.environ["AIC_PROVIDER"] = "gemini"
        os.environ["DEEPSEEK_API_KEY"] = "env_ds_key"

        config = get_config()
        # Env > TOML > Default
        self.assertEqual(config["provider"], "gemini") # Env overrides TOML
        self.assertEqual(config["deepseek"]["api_key"], "env_ds_key") # Env overrides TOML
        self.assertEqual(config["claude"]["model"], DEFAULT_CONFIG["claude"]["model"]) # Default retained

if __name__ == '__main__':
    unittest.main()
