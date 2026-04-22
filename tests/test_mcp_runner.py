import unittest
from unittest.mock import MagicMock
from aic.mcp.runner import SandboxSession
from aic.mcp.registry import MCPRegistry, ToolInfo

class TestSandboxSession(unittest.TestCase):
    def setUp(self):
        self.registry = MagicMock(spec=MCPRegistry)
        self.complete_fn = MagicMock()
        self.provider = "test_provider"
        self.provider_config = {}

        # 默认 mock list_tools 有返回值，以进入常规测试循环
        tool_info = ToolInfo(
            name="test_server.test_tool",
            server_name="test_server",
            description="Test Tool",
            input_schema={"type": "function", "function": {"name": "test_tool"}}
        )
        self.registry.list_tools.return_value = [tool_info]

        self.session = SandboxSession(
            registry=self.registry,
            complete_fn=self.complete_fn,
            provider=self.provider,
            provider_config=self.provider_config,
            max_tool_turns=3,
        )

    def test_no_tools_available(self):
        """测试没有注册工具时，直接发起一次不带 tools 的调用并返回结果"""
        self.registry.list_tools.return_value = []
        self.complete_fn.return_value = {"content": "没有工具，直接回答"}

        result = self.session.run("测试任务")

        self.assertEqual(result, "没有工具，直接回答")
        self.complete_fn.assert_called_once()
        _, kwargs = self.complete_fn.call_args
        self.assertIsNone(kwargs.get("tools"))

    def test_no_tool_calls_in_response(self):
        """测试第一轮就没有工具调用，直接返回文本"""
        self.complete_fn.return_value = {"content": "最终答案"}

        result = self.session.run("测试任务")

        self.assertEqual(result, "最终答案")
        self.complete_fn.assert_called_once()

    def test_multi_turn_tool_calls(self):
        """测试多轮工具调用后结束"""
        # 第一轮：有工具调用
        # 第二轮：无工具调用
        self.complete_fn.side_effect = [
            {"content": "我想调用工具", "tool_calls": [{"name": "test_tool", "arguments": {}}]},
            {"content": "工具调用完成，最终答案是X", "tool_calls": []}
        ]
        self.registry.call_tool.return_value = "工具执行结果"

        result = self.session.run("测试任务")

        self.assertEqual(result, "工具调用完成，最终答案是X")
        self.assertEqual(self.complete_fn.call_count, 2)
        self.registry.call_tool.assert_called_once_with("test_tool", {})

    def test_max_tool_turns_force_summary(self):
        """测试达到最大轮次时，触发 _force_summary"""
        # max_tool_turns 是 3
        self.complete_fn.side_effect = [
            {"content": "调用1", "tool_calls": [{"name": "test_tool"}]},
            {"content": "调用2", "tool_calls": [{"name": "test_tool"}]},
            {"content": "调用3", "tool_calls": [{"name": "test_tool"}]},
            {"content": "强制汇总答案", "tool_calls": []}  # 这是 _force_summary 的返回值
        ]
        self.registry.call_tool.return_value = "工具结果"

        result = self.session.run("测试任务")

        self.assertEqual(result, "强制汇总答案")
        # 3次普通调用 + 1次强制汇总
        self.assertEqual(self.complete_fn.call_count, 4)

        # 验证强制汇总的调用没有带 tools
        last_call_kwargs = self.complete_fn.call_args_list[-1].kwargs
        self.assertIsNone(last_call_kwargs.get("tools"))

    def test_complete_fn_exception_caught(self):
        """测试 complete_fn 抛异常被捕获，并作为工具结果继续执行"""
        self.complete_fn.side_effect = [
            Exception("API Timeout"),
            {"content": "错误已恢复，答案是Y", "tool_calls": []}
        ]

        result = self.session.run("测试任务")

        self.assertEqual(result, "错误已恢复，答案是Y")
        self.assertEqual(self.complete_fn.call_count, 2)

    def test_registry_call_tool_exception_caught(self):
        """测试 call_tool 抛出异常时不中断流程"""
        self.complete_fn.side_effect = [
            {"content": "尝试调用", "tool_calls": [{"name": "bad_tool"}]},
            {"content": "工具报错了，但我可以继续回答", "tool_calls": []}
        ]
        self.registry.call_tool.side_effect = Exception("Tool Execution Failed")

        result = self.session.run("测试任务")

        self.assertEqual(result, "工具报错了，但我可以继续回答")
        self.assertEqual(self.complete_fn.call_count, 2)
        self.registry.call_tool.assert_called_once()

    def test_messages_isolation(self):
        """验证 run 方法不会修改外部状态"""
        # 我们很难直接测试它不修改外部变量（因为没有传入外部列表）
        # 但是我们可以测试 complete_fn 收到的 prompt 是否正确地包含了历史。
        self.complete_fn.side_effect = [
            {"content": "", "tool_calls": [{"name": "test_tool", "arguments": {}}]},
            {"content": "Done", "tool_calls": []}
        ]
        self.registry.call_tool.return_value = "Result"

        self.session.run("My Task")

        import json

        # 第一轮 prompt 应该只有 user message
        first_call_prompt = self.complete_fn.call_args_list[0].kwargs["prompt"]
        first_msgs = json.loads(first_call_prompt)
        self.assertEqual(len(first_msgs), 1)
        self.assertEqual(first_msgs[0]["content"], "My Task")

        # 第二轮 prompt 应该包含了前面的 user -> tool -> next user prompt
        second_call_prompt = self.complete_fn.call_args_list[1].kwargs["prompt"]
        second_msgs = json.loads(second_call_prompt)
        self.assertEqual(len(second_msgs), 3)
        self.assertEqual(second_msgs[0]["content"], "My Task")
        self.assertEqual(second_msgs[1]["role"], "tool")
        self.assertEqual(second_msgs[1]["content"], "Result")
        self.assertEqual(second_msgs[2]["content"], "请根据以上工具返回结果，继续完成任务。")

if __name__ == "__main__":
    unittest.main()
