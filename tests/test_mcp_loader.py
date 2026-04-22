import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from aic.mcp.loader import MCPLoader
from aic.mcp.registry import MCPRegistry

class TestMCPLoader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "mcp.json"
        self.registry = MagicMock(spec=MCPRegistry)
        self.loader = MCPLoader(self.config_path, self.registry)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, data):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_missing_file(self):
        # mcp.json 不存在，静默返回 0
        count = self.loader.load()
        self.assertEqual(count, 0)
        self.registry.register.assert_not_called()

    @patch("builtins.print")
    def test_json_error(self, mock_print):
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("invalid json")

        count = self.loader.load()
        self.assertEqual(count, 0)
        mock_print.assert_called_once()
        self.assertIn("mcp.json 格式错误", mock_print.call_args[0][0])

    def test_normal_load(self):
        self.write_config({
            "mcpServers": {
                "server1": {
                    "command": "node",
                    "args": ["server1.js"],
                    "env": {"FOO": "bar"}
                },
                "server2": {
                    "command": "python3",
                    "args": ["server2.py"]
                }
            }
        })

        count = self.loader.load()
        self.assertEqual(count, 2)
        self.assertEqual(self.registry.register.call_count, 2)

    @patch("builtins.print")
    def test_register_exception(self, mock_print):
        self.write_config({
            "mcpServers": {
                "server1": {"command": "cmd1"},
                "server2": {"command": "cmd2"}
            }
        })

        # 使第一个调用抛出异常，第二个成功
        call_count = 0
        def side_effect(info):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("test error")
        self.registry.register.side_effect = side_effect

        count = self.loader.load()
        self.assertEqual(count, 1)  # 只有一个成功
        mock_print.assert_called_once()
        self.assertIn("启动失败: test error", mock_print.call_args[0][0])

    @patch("builtins.print")
    def test_sse_skip(self, mock_print):
        self.write_config({
            "mcpServers": {
                "server1": {"type": "sse", "command": "cmd"},
                "server2": {"command": "cmd2"}
            }
        })

        count = self.loader.load()
        self.assertEqual(count, 1)
        mock_print.assert_called_once()
        self.assertIn("SSE 暂不支持", mock_print.call_args[0][0])

    @patch.dict(os.environ, {"MY_VAR": "my_val"}, clear=True)
    def test_env_expand(self):
        self.write_config({
            "mcpServers": {
                "server1": {
                    "command": "cmd",
                    "env": {
                        "VAR1": "${MY_VAR}/path",
                        "VAR2": "${MISSING}/path",
                        "VAR3": "normal"
                    }
                }
            }
        })

        count = self.loader.load()
        self.assertEqual(count, 1)

        args = self.registry.register.call_args[0][0]
        self.assertEqual(args.env["VAR1"], "my_val/path")
        self.assertEqual(args.env["VAR2"], "${MISSING}/path")
        self.assertEqual(args.env["VAR3"], "normal")

if __name__ == "__main__":
    unittest.main()
