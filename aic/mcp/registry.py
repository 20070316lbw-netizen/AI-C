"""
L5 MCP 层：registry
管理 MCP server 进程生命周期、JSON-RPC 通信、工具元数据注册。是 MCP 层核心状态持有者。
"""

import os
import re
import json
import subprocess
import threading
import queue
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from aic.kairos import log_event

@dataclass
class ServerInfo:
    name: str
    type: str                        # "stdio" | "sse"（sse 暂不实现）
    command: list[str]               # stdio 专用
    env: dict[str, str]              # 已展开的环境变量
    process: subprocess.Popen | None = None
    tools: list[dict] = field(default_factory=list)
    # tools 格式：[{"name": str, "description": str, "input_schema": dict}]

@dataclass
class ToolInfo:
    name: str           # 全局唯一，格式 "server_name.tool_name"
    server_name: str
    description: str
    input_schema: dict

class MCPRegistry:
    def __init__(self):
        self.servers: Dict[str, ServerInfo] = {}
        self.tools: Dict[str, ToolInfo] = {}
        self._request_id = 0
        self._queues: Dict[subprocess.Popen, Dict[int, queue.Queue]] = {}
        self._reader_threads: Dict[subprocess.Popen, threading.Thread] = {}
        self._lock = threading.Lock()

    def _expand_env(self, env: dict[str, str]) -> dict[str, str]:
        expanded = {}
        for k, v in env.items():
            def repl(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            expanded[k] = re.sub(r'\$\{([^}]+)\}', repl, v)
        return expanded

    def _start_process(self, server_info: ServerInfo) -> subprocess.Popen:
        process = subprocess.Popen(
            server_info.command,
            env=server_info.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            start_new_session=False
        )
        return process

    def _reader_daemon(self, process: subprocess.Popen):
        while True:
            try:
                line = process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode('utf-8'))
                    if "id" in msg:
                        msg_id = msg["id"]
                        with self._lock:
                            if process in self._queues and msg_id in self._queues[process]:
                                self._queues[process][msg_id].put(msg)
                except json.JSONDecodeError:
                    continue
            except Exception:
                break

        with self._lock:
            if process in self._queues:
                for q in self._queues[process].values():
                    q.put({"error": {"message": "Process terminated"}})
                del self._queues[process]
            if process in self._reader_threads:
                del self._reader_threads[process]

    def _send_request(self, process: subprocess.Popen, method: str, params: dict) -> dict:
        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            if process not in self._queues:
                self._queues[process] = {}
            q = queue.Queue()
            self._queues[process][req_id] = q

        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }

        try:
            req_bytes = json.dumps(req).encode('utf-8') + b'\n'
            process.stdin.write(req_bytes)
            process.stdin.flush()
        except Exception as e:
            with self._lock:
                del self._queues[process][req_id]
            return {"error": {"message": str(e)}}

        try:
            resp = q.get(timeout=10)
        except queue.Empty:
            resp = {"error": "timeout"}

        with self._lock:
            if process in self._queues and req_id in self._queues[process]:
                del self._queues[process][req_id]

        return resp

    def register(self, server_info: ServerInfo) -> None:
        try:
            server_info.env = self._expand_env(server_info.env)
            if server_info.type == "stdio":
                process = self._start_process(server_info)
                server_info.process = process

                thread = threading.Thread(target=self._reader_daemon, args=(process,), daemon=True)
                with self._lock:
                    self._reader_threads[process] = thread
                thread.start()

                init_resp = self._send_request(process, "initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "aic", "version": "1.0.0"}
                })

                if "error" in init_resp:
                    log_event("mcp_register_error", "global", {"server": server_info.name, "error": init_resp["error"]})
                    return

                self._send_request(process, "notifications/initialized", {})

                tools_resp = self._send_request(process, "tools/list", {})
                if "result" in tools_resp and "tools" in tools_resp["result"]:
                    tools = tools_resp["result"]["tools"]
                    for tool in tools:
                        name = tool.get("name", "")
                        desc = tool.get("description", "")
                        schema = tool.get("inputSchema", {})

                        tool_info = ToolInfo(
                            name=f"{server_info.name}.{name}",
                            server_name=server_info.name,
                            description=desc,
                            input_schema=schema
                        )
                        server_info.tools.append({
                            "name": name,
                            "description": desc,
                            "input_schema": schema
                        })
                        self.tools[tool_info.name] = tool_info

                self.servers[server_info.name] = server_info

        except Exception as e:
            log_event("mcp_register_error", "global", {"server": server_info.name, "error": str(e)})

    def unregister(self, server_name: str) -> None:
        if server_name in self.servers:
            server_info = self.servers[server_name]
            if server_info.process:
                try:
                    process = server_info.process
                    self._send_request(process, "shutdown", {})
                    process.terminate()
                    process.wait(timeout=2)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

            tools_to_remove = []
            for tool_name, tool_info in self.tools.items():
                if tool_info.server_name == server_name:
                    tools_to_remove.append(tool_name)
            for tool_name in tools_to_remove:
                del self.tools[tool_name]

            del self.servers[server_name]

    def get_tool(self, tool_name: str) -> ToolInfo | None:
        if "." in tool_name:
            return self.tools.get(tool_name)

        matches = [t for t in self.tools.values() if t.name.endswith(f".{tool_name}")]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            return None
        return None

    def list_tools(self) -> list[ToolInfo]:
        return list(self.tools.values())

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            if "." not in tool_name:
                matches = [t for t in self.tools.values() if t.name.endswith(f".{tool_name}")]
                if len(matches) > 1:
                    conflicts = ", ".join([t.name for t in matches])
                    return f"工具名 '{tool_name}' 在多个 server 中存在冲突 ({conflicts})，请使用完整格式 server_name.tool_name 重试。"
                elif len(matches) == 0:
                    return f"Tool {tool_name} not found"
                tool_info = matches[0]
            else:
                tool_info = self.tools.get(tool_name)
                if not tool_info:
                    return f"Tool {tool_name} not found"

            server_info = self.servers.get(tool_info.server_name)
            if not server_info or not server_info.process:
                return f"Server {tool_info.server_name} not available"

            real_tool_name = tool_info.name.split(".", 1)[1]

            resp = self._send_request(server_info.process, "tools/call", {
                "name": real_tool_name,
                "arguments": arguments
            })

            if "error" in resp:
                return json.dumps(resp["error"])
            elif "result" in resp:
                if "content" in resp["result"]:
                    content = resp["result"]["content"]
                    if isinstance(content, list):
                        return "\n".join([c.get("text", "") for c in content if c.get("type") == "text"])
                    return str(content)
                return json.dumps(resp["result"])

            return str(resp)
        except Exception as e:
            return f"调用工具 '{tool_name}' 时发生异常: {str(e)}"

    def shutdown_all(self) -> None:
        server_names = list(self.servers.keys())
        for name in server_names:
            self.unregister(name)
        self.servers.clear()
        self.tools.clear()
