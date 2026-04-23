"""
L5 MCP 层：runner
实现沙箱临时会话，在独立子上下文内完成多轮工具调用。
"""

import json
from typing import Callable
from aic.mcp.registry import MCPRegistry

class SandboxSession:
    def __init__(
        self,
        registry: MCPRegistry,
        complete_fn: Callable,
        provider: str,
        provider_config: dict,
        max_tool_turns: int = 10,
    ):
        self.registry = registry
        self.complete_fn = complete_fn
        self.provider = provider
        self.provider_config = provider_config
        self.max_tool_turns = max_tool_turns

    def run(self, task: str) -> str:
        """
        task：主对话传入的任务描述（自然语言字符串）。
        返回：纯文字结果摘要，调用方可直接注入主对话。
        临时 messages 的生命周期严格限制在此方法内部，不外泄。
        """
        tools_info = self.registry.list_tools()
        if not tools_info:
            # 当没有工具可用时，直接走单轮调用
            try:
                response = self.complete_fn(
                    prompt=task,
                    provider=self.provider,
                    config=self.provider_config,
                    system="你是一个工具执行助手。只在必要时调用工具。任务完成后直接给出结论，不要重复调用。",
                    tools=None,
                )
                return response.get("content", "（无回复）")
            except Exception as e:
                return f"（LLM调用失败：{str(e)}）"

        tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools_info]
        tool_descriptions = "\n".join(
            f"{t.name}: {t.description}"
            for t in tools_info
        )

        system = (
            "你是一个工具执行助手。你有以下工具可用：\n"
            f"{tool_descriptions}\n"
            "只在必要时调用工具。任务完成后直接给出结论，不要重复调用。"
        )

        # 临时 messages，生命周期限于本方法
        messages = [{"role": "user", "content": task}]
        turn = 0

        while turn < self.max_tool_turns:
            try:
                response = self.complete_fn(
                    prompt=json.dumps(messages, ensure_ascii=False),
                    provider=self.provider,
                    config=self.provider_config,
                    system=system,
                    tools=tools,
                )
            except Exception as e:
                # complete_fn 抛异常：异常被捕获，作为 tool_result 注入临时 messages，继续循环
                messages.append({
                    "role": "tool",
                    "name": "complete_fn_error",
                    "content": f"LLM Error: {str(e)}"
                })
                messages.append({
                    "role": "user",
                    "content": "请根据以上工具返回结果，继续完成任务。"
                })
                turn += 1
                continue

            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # 无工具调用，拿到最终文字回复，退出循环
                return response.get("content", "（无回复）")

            # 执行工具调用，将结果追加到临时 messages
            for call in tool_calls:
                try:
                    result = self.registry.call_tool(
                        call["name"], call.get("arguments", {})
                    )
                except Exception as e:
                    result = f"Tool Error: {str(e)}"

                messages.append({
                    "role": "tool",
                    "name": call["name"],
                    "content": str(result),
                })

            # 将工具结果汇入下一轮 prompt
            messages.append({
                "role": "user",
                "content": "请根据以上工具返回结果，继续完成任务。"
            })
            turn += 1

        # 达到上限，强制汇总
        return self._force_summary(messages, system)

    def _force_summary(self, messages: list, system: str) -> str:
        """超出轮次上限时，不带 tools 发送一次额外 LLM 调用，强制汇总。"""
        context_str = json.dumps(messages, ensure_ascii=False)
        try:
            response = self.complete_fn(
                prompt=(
                    f"对话上下文：\n{context_str}\n\n"
                    "你已达到工具调用上限。请根据目前已获取的信息，"
                    "给出尽可能完整的最终回答，不要再调用任何工具。"
                ),
                provider=self.provider,
                config=self.provider_config,
                system=system,
                tools=None,   # 强制不带工具
            )
            return response.get("content", "（达到工具调用上限，无法汇总）")
        except Exception:
            return "（达到工具调用上限，无法汇总）"
