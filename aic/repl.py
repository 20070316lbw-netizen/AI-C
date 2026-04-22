"""
L1 会话层：对话循环、slash 命令路由
"""
import os
import sys
from pathlib import Path

from aic.session import Session
from aic.tui import TUIRenderer
from aic.providers.claude import ClaudeProvider
from aic.providers.openai_compat import OpenAICompatProvider
from aic.memory.store import MemoryStore
from aic.dream.scheduler import DreamScheduler
import aic.kairos as kairos
from aic.mcp.registry import MCPRegistry
from aic.mcp.runner import SandboxSession
from aic.llm import complete
from dataclasses import asdict

def start(config: dict, session: Session, store: MemoryStore, scheduler: DreamScheduler, registry: MCPRegistry):
    provider_name = config.get("provider", "deepseek")
    provider_config = config.get(provider_name, {})

    if provider_name == "claude":
        provider = ClaudeProvider(
            api_key=provider_config.get("api_key", ""),
            model=provider_config.get("model", "claude-sonnet-4-20250514"),
            base_url=provider_config.get("base_url", "https://api.anthropic.com")
        )
    else:
        provider = OpenAICompatProvider(
            api_key=provider_config.get("api_key", ""),
            model=provider_config.get("model", ""),
            base_url=provider_config.get("base_url", "")
        )

    tui = TUIRenderer()

    print("aic ready")
    print(f"Provider: {provider.name}, Model: {provider.model}")

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0]

            if cmd == "/add":
                if len(parts) < 2:
                    print("Usage: /add <file>")
                    continue
                filepath = parts[1]
                p = Path(filepath)
                if not p.is_file():
                    print(f"File not found: {filepath}")
                    continue

                # Check for binary file
                try:
                    with open(filepath, 'rb') as f:
                        header = f.read(1024)
                        if b'\0' in header:
                            print(f"Cannot add binary file: {filepath}")
                            continue
                except Exception as e:
                    print(f"Error reading file {filepath}: {e}")
                    continue

                try:
                    content = p.read_text(encoding="utf-8")
                    session.add_context_file(filepath)
                    tui.render_file(filepath, content)
                    print(f"Added {filepath}")
                except Exception as e:
                    print(f"Error reading text from {filepath}: {e}")

            elif cmd == "/files":
                files = session.list_context_files()
                if not files:
                    print("No files loaded.")
                else:
                    for f in files:
                        print(f)

            elif cmd == "/clear":
                session.clear()
                tui.messages.clear()
                tui._update_layout()
                print("Session cleared (context files kept).")

            elif cmd == "/reset":
                session.reset()
                tui.messages.clear()
                tui.clear_right()
                print("Session and context files reset.")

            elif cmd == "/model":
                print(f"Current Provider: {provider.name}")
                print(f"Current Model: {provider.model}")
                print("Hint: Use --provider / --model startup arguments to switch (interactive switch in phase 2).")

            elif cmd == "/status":
                print(f"Provider: {provider.name}")
                print(f"Model: {provider.model}")
                print(f"Session ID: {session.session_id()}")

            elif cmd == "/tree":
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv")]
                    level = root.replace(".", "").count(os.sep)
                    indent = " " * 4 * (level)
                    print(f"{indent}{os.path.basename(root)}/")
                    subindent = " " * 4 * (level + 1)
                    for f in files:
                        print(f"{subindent}{f}")

            elif cmd == "/dream":
                scheduler.run(force=True)

            elif cmd == "/cost":
                print("暂未实现")

            elif cmd == "/help":
                print("Available commands:")
                print("  /add <file> - Add a file to the context")
                print("  /files      - List loaded context files")
                print("  /clear      - Clear conversation history")
                print("  /reset      - Clear history and context files")
                print("  /model      - Show current provider and model")
                print("  /status     - Show status information")
                print("  /tree       - Print directory tree")
                print("  /mcp        - 查看已注册的 MCP server 和工具列表")
                print("  /dream      - 手动触发 Dream 整理（前台同步，显示进度）")
                print("  /cost       - 查看本次会话消耗（暂未实现）")
                print("  /help       - Show this help message")
                print("  /exit       - Exit aic")

            elif cmd == "/mcp":
                tools = registry.list_tools()
                if not tools:
                    print("未注册任何 MCP server。可在 .aic/mcp.json 中配置。")
                else:
                    servers = {}
                    for t in tools:
                        if t.server_name not in servers:
                            servers[t.server_name] = []
                        servers[t.server_name].append(t)

                    for server_name, server_tools in servers.items():
                        s_info = registry.servers.get(server_name)
                        s_type = s_info.type if s_info else "unknown"
                        print(f"  {server_name} ({s_type}) — {len(server_tools)} 个工具")
                        for t in server_tools:
                            print(f"    • {t.name:<24} {t.description}")

            elif cmd == "/poor":
                session.poor_mode = not session.poor_mode
                if session.poor_mode:
                    from rich import print as rprint
                    rprint("[bold green]POOR MODE: ON[/bold green]")
                else:
                    from rich import print as rprint
                    rprint("[bold yellow]POOR MODE: OFF[/bold yellow]")
                kairos.log_event("poor_toggled", session.session_id(), {"enabled": session.poor_mode})

            elif cmd == "/memory":
                mem_type = parts[1] if len(parts) > 1 else None
                # Support user/feedback/project/reference type check
                if mem_type and mem_type not in ["user", "feedback", "project", "reference"]:
                    print(f"Unknown memory type: {mem_type}")
                    continue

                mems = store.list(type=mem_type, include_archived=False)
                from rich.table import Table
                from rich.console import Console
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("id")
                table.add_column("type")
                table.add_column("weight")
                table.add_column("processed")
                table.add_column("content")

                for m in mems:
                    content_trunc = m.content[:60] + ("..." if len(m.content) > 60 else "")
                    table.add_row(
                        m.id[:8],
                        m.type,
                        f"{m.weight:.1f}",
                        "Yes" if m.is_processed else "No",
                        content_trunc
                    )
                Console().print(table)
                print(f"共 {len(mems)} 条")

            elif cmd == "/forget":
                if len(parts) < 2:
                    print("Usage: /forget <id>")
                    continue
                target_id = parts[1]
                if len(target_id) < 4:
                    print("id 至少需要 4 位")
                    continue

                matches = store.prefix_match(target_id)
                if len(matches) == 0:
                    print("未找到匹配的记忆")
                elif len(matches) > 1:
                    for m in matches:
                        print(f"- {m.id}")
                    print("前缀冲突，请输入更长的 id")
                else:
                    match = matches[0]
                    from rich.prompt import Confirm
                    content_trunc = match.content[:40]
                    if Confirm.ask(f"确认软删除 {match.id}: {content_trunc}？"):
                        store.soft_delete(match.id)
                        kairos.log_event("memory_forgotten", session.session_id(), {"id": match.id})
                        print("已删除")
                    else:
                        print("已取消")

            elif cmd == "/log":
                logs = kairos.read_today()
                if not logs:
                    print("今日暂无 KAIROS 日志")
                else:
                    from rich.table import Table
                    from rich.console import Console
                    import datetime
                    table = Table(show_header=True, header_style="bold cyan")
                    table.add_column("时间")
                    table.add_column("event")
                    table.add_column("payload 摘要")

                    for log in reversed(logs):
                        ts = log.get("ts", 0)
                        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
                        event = log.get("event", "")
                        payload = log.get("payload", {})

                        import json
                        payload_str = json.dumps(payload, ensure_ascii=False)
                        if len(payload_str) > 80:
                            payload_str = payload_str[:80] + "..."

                        table.add_row(time_str, event, payload_str)
                    Console().print(table)

            elif cmd == "/exit":
                print("Exiting...")
                break
            else:
                print(f"Unknown command: {cmd}, type /help")
            continue

        # Non-slash input processing
        session.add_user(user_input)
        tui.render_message("user", user_input)
        tui.render_status(provider.name, provider.model, 0)

        # 有工具注册时，改为非流式调用以便检测 tool_calls
        if registry.list_tools() and not session.poor_mode:
            try:
                response = complete(
                    prompt=user_input,
                    provider=provider_name,
                    config=provider_config,
                    system=session.get_system(),
                    tools=[asdict(t) for t in registry.list_tools()],
                )
                if response.get("tool_calls"):
                    sandbox = SandboxSession(
                        registry=registry,
                        complete_fn=complete,
                        provider=provider_name,
                        provider_config=provider_config,
                        max_tool_turns=config.get("mcp", {}).get("max_tool_turns", 10),
                    )
                    final_content = sandbox.run(task=user_input)
                else:
                    final_content = response.get("content", "")
            except Exception as e:
                final_content = f"\n[错误] 请求异常: {str(e)}"

            tui.render_message("assistant", final_content)
        else:
            # 原有流式路径（无工具注册 or poor_mode）
            tui.start()
            tui.render_stream_start()

            try:
                for chunk in provider.stream(session.get_messages()):
                    tui.render_stream_chunk(chunk)
            except Exception as e:
                # Catching generic errors; provider network errors are often caught within stream() and yield text
                tui.render_stream_chunk(f"\n[错误] 流式请求异常: {str(e)}")

            final_content = tui.stream_content
            tui.render_stream_end()
            tui.stop()

        session.add_assistant(final_content)

        if not session.poor_mode:
            scheduler.run(force=False)
