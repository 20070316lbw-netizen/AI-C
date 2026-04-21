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
import aic.kairos as kairos

def start(config: dict):
    store = MemoryStore()
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

    session = Session(config)
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

            elif cmd == "/help":
                print("Available commands:")
                print("  /add <file> - Add a file to the context")
                print("  /files      - List loaded context files")
                print("  /clear      - Clear conversation history")
                print("  /reset      - Clear history and context files")
                print("  /model      - Show current provider and model")
                print("  /status     - Show status information")
                print("  /tree       - Print directory tree")
                print("  /help       - Show this help message")
                print("  /exit       - Exit aic")

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
                    table = Table(show_header=True, header_style="bold cyan")
                    table.add_column("时间")
                    table.add_column("event")
                    table.add_column("payload 摘要")

                    for log in reversed(logs):
                        time_str = log.get("time", "")
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

        tui.start()
        tui.render_stream_start()

        try:
            for chunk in provider.stream(session.get_messages()):
                tui.render_stream_chunk(chunk)
        except Exception as e:
            # Catching generic errors; provider network errors are often caught within stream() and yield text
            tui.render_stream_chunk(f"\n[错误] 流式请求异常: {str(e)}")

        content = tui.stream_content
        tui.render_stream_end()
        tui.stop()

        session.add_assistant(content)
