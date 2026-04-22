"""
L5 MCP 层：loader
"""
import os
import re
import json
from pathlib import Path
from aic.mcp.registry import MCPRegistry, ServerInfo

class MCPLoader:
    def __init__(self, config_path: Path, registry: MCPRegistry):
        self.config_path = config_path
        self.registry = registry

    def _expand_env(self, env: dict) -> dict:
        result = {}
        for k, v in env.items():
            if not isinstance(v, str):
                v = str(v)
            def replacer(m):
                var = m.group(1)
                return os.environ.get(var, m.group(0))  # 不存在则保留 ${VAR}
            result[k] = re.sub(r'\$\{([^}]+)\}', replacer, v)
        return result

    def load(self) -> int:
        """
        读取并解析 mcp.json，注册所有 server。
        - 文件不存在：静默返回 0
        - JSON 解析失败：打印 [MCP] mcp.json 格式错误: {e}，返回 0
        - 单个 server 注册失败：打印 [MCP] server '{name}' 启动失败: {e}，跳过，继续
        - type == "sse"：打印 [MCP] server '{name}': SSE 暂不支持，已跳过，跳过
        返回成功注册的 server 数量。
        """
        if not self.config_path.exists():
            return 0

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[MCP] mcp.json 格式错误: {e}")
            return 0

        servers = data.get("mcpServers", {})
        success_count = 0

        for name, config in servers.items():
            server_type = config.get("type", "stdio")
            if server_type == "sse":
                print(f"[MCP] server '{name}': SSE 暂不支持，已跳过")
                continue

            command = config.get("command")
            if not command:
                print(f"[MCP] server '{name}' 启动失败: missing command")
                continue

            args = config.get("args", [])
            cmd_list = [command] + args

            env = config.get("env", {})
            env = self._expand_env(env)

            server_info = ServerInfo(
                name=name,
                type=server_type,
                command=cmd_list,
                env=env
            )

            try:
                self.registry.register(server_info)
                success_count += 1
            except Exception as e:
                print(f"[MCP] server '{name}' 启动失败: {e}")

        return success_count

