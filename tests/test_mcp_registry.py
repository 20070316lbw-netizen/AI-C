import unittest
import os
import tempfile
import subprocess
import json
from unittest.mock import patch, MagicMock
from aic.mcp.registry import MCPRegistry, ServerInfo, ToolInfo

class TestMCPRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.registry = MCPRegistry()

    def tearDown(self):
        self.registry.shutdown_all()

    @patch.dict(os.environ, {"MY_VAR": "my_value"}, clear=True)
    def test_expand_env(self):
        env = {
            "VAR1": "${MY_VAR}/path",
            "VAR2": "${MISSING_VAR}/path",
            "VAR3": "normal"
        }
        expanded = self.registry._expand_env(env)
        self.assertEqual(expanded["VAR1"], "my_value/path")
        self.assertEqual(expanded["VAR2"], "${MISSING_VAR}/path")
        self.assertEqual(expanded["VAR3"], "normal")

    @patch("subprocess.Popen")
    def test_start_process_stderr_devnull(self, mock_popen):
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        server_info = ServerInfo(
            name="test_server",
            type="stdio",
            command=["dummy_command"],
            env={}
        )

        process = self.registry._start_process(server_info)

        mock_popen.assert_called_once()
        _, kwargs = mock_popen.call_args
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdin"], subprocess.PIPE)
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(kwargs["text"], False)
        self.assertEqual(kwargs["start_new_session"], False)

    @patch("aic.mcp.registry.MCPRegistry._start_process")
    @patch("aic.mcp.registry.MCPRegistry._send_request")
    @patch("threading.Thread")
    def test_register_success(self, mock_thread, mock_send_request, mock_start_process):
        mock_process = MagicMock()
        mock_start_process.return_value = mock_process

        def side_effect_send_request(process, method, params):
            if method == "initialize":
                return {"result": {}}
            elif method == "tools/list":
                return {"result": {"tools": [
                    {"name": "tool1", "description": "desc1", "inputSchema": {}}
                ]}}
            return {}

        mock_send_request.side_effect = side_effect_send_request

        server_info = ServerInfo(
            name="server1",
            type="stdio",
            command=["test"],
            env={}
        )

        self.registry.register(server_info)

        self.assertIn("server1", self.registry.servers)
        self.assertIn("server1.tool1", self.registry.tools)
        tool = self.registry.tools["server1.tool1"]
        self.assertEqual(tool.name, "server1.tool1")
        self.assertEqual(tool.server_name, "server1")
        self.assertEqual(tool.description, "desc1")
        self.assertEqual(len(server_info.tools), 1)

    @patch("aic.mcp.registry.MCPRegistry._start_process")
    def test_register_exception_caught(self, mock_start_process):
        mock_start_process.side_effect = Exception("Failed to start")

        server_info = ServerInfo(
            name="fail_server",
            type="stdio",
            command=["test"],
            env={}
        )

        # This should not raise an exception
        self.registry.register(server_info)

        self.assertNotIn("fail_server", self.registry.servers)

    def test_get_tool(self):
        tool1 = ToolInfo(name="srv1.read", server_name="srv1", description="", input_schema={})
        tool2 = ToolInfo(name="srv2.read", server_name="srv2", description="", input_schema={})
        tool3 = ToolInfo(name="srv1.write", server_name="srv1", description="", input_schema={})

        self.registry.tools = {
            "srv1.read": tool1,
            "srv2.read": tool2,
            "srv1.write": tool3
        }

        # Full name
        self.assertEqual(self.registry.get_tool("srv1.read"), tool1)
        self.assertEqual(self.registry.get_tool("srv2.read"), tool2)

        # Bare name unique
        self.assertEqual(self.registry.get_tool("write"), tool3)

        # Bare name conflict
        self.assertIsNone(self.registry.get_tool("read"))

    @patch("aic.mcp.registry.MCPRegistry._send_request")
    def test_call_tool(self, mock_send_request):
        mock_process = MagicMock()
        server_info = ServerInfo(name="srv1", type="stdio", command=[], env={}, process=mock_process)
        self.registry.servers["srv1"] = server_info

        tool = ToolInfo(name="srv1.read", server_name="srv1", description="", input_schema={})
        self.registry.tools["srv1.read"] = tool

        mock_send_request.return_value = {"result": {"content": [{"type": "text", "text": "file content"}]}}

        result = self.registry.call_tool("srv1.read", {"path": "test.txt"})
        self.assertEqual(result, "file content")

        mock_send_request.assert_called_once_with(mock_process, "tools/call", {"name": "read", "arguments": {"path": "test.txt"}})

    def test_call_tool_conflict(self):
        tool1 = ToolInfo(name="srv1.read", server_name="srv1", description="", input_schema={})
        tool2 = ToolInfo(name="srv2.read", server_name="srv2", description="", input_schema={})

        self.registry.tools = {
            "srv1.read": tool1,
            "srv2.read": tool2
        }

        # Both bare name conflict
        result = self.registry.call_tool("read", {})
        self.assertTrue("冲突" in result)
        self.assertTrue("srv1.read" in result)
        self.assertTrue("srv2.read" in result)

    def test_call_tool_missing_server(self):
        tool = ToolInfo(name="srv1.read", server_name="srv1", description="", input_schema={})
        self.registry.tools["srv1.read"] = tool

        # srv1 is missing in servers
        result = self.registry.call_tool("srv1.read", {})
        self.assertEqual(result, "Server srv1 not available")

if __name__ == "__main__":
    unittest.main()
