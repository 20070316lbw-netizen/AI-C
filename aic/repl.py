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
from aic.errors import print_error, print_warning, print_ok

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

    print_ok("aic ready")
    print_ok(f"Provider: {provider.name}, Model: {provider.model}")

    while True:
        try:
            if session.poor_mode and session.poor_mode_reason == "token_guard":
                from rich.console import Console
                Console().print("[bold red][POOR MODE AUTO-LOCKED][/bold red]", end=" ")
                user_input = input("")
            elif session.poor_mode:
                from rich.console import Console
                Console().print("[yellow][POOR MODE][/yellow]", end=" ")
                user_input = input("")
            else:
                user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print_warning("\nExiting...")
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0]

            if cmd == "/add":
                if len(parts) < 2:
                    print_error("Usage: /add <file>")
                    continue
                filepath = parts[1]
                p = Path(filepath)

                if p.is_dir():
                    added = 0
                    skipped = 0
                    for child in sorted(p.rglob("*")):
                        if not child.is_file():
                            continue
                        # Skip hidden files and common noise directories
                        if any(part.startswith(".") for part in child.parts):
                            continue
                        if any(part in ("__pycache__", "node_modules", ".venv", ".git") for part in child.parts):
                            continue
                        # Skip binary files
                        try:
                            header = child.read_bytes()[:1024]
                            if b'\0' in header:
                                skipped += 1
                                continue
                            content = child.read_text(encoding="utf-8")
                            session.add_context_file(str(child))
                            added += 1
                        except Exception:
                            skipped += 1
                            continue
                        # Hard cap: stop at 20 files to prevent token overflow
                        if added >= 20:
                            print_warning(f"File limit reached (20). Use /add on subdirectories for more.")
                            break
                    print_ok(f"Added {added} files from {filepath}" + (f" ({skipped} skipped)" if skipped else ""))
                    continue

                if not p.is_file():
                    print_error(f"File not found: {filepath}")
                    continue

                # Check for binary file
                try:
                    with open(filepath, 'rb') as f:
                        header = f.read(1024)
                        if b'\0' in header:
                            print_error(f"Cannot add binary file: {filepath}")
                            continue
                except Exception as e:
                    print_error(f"Error reading file {filepath}: {e}")
                    continue

                try:
                    content = p.read_text(encoding="utf-8")
                    session.add_context_file(filepath)
                    tui.render_file(filepath, content)
                    print_ok(f"Added {filepath}")
                except Exception as e:
                    print_error(f"Error reading text from {filepath}: {e}")

            elif cmd == "/files":
                files = session.list_context_files()
                if not files:
                    print_warning("No files loaded.")
                else:
                    for f in files:
                        print(f)

            elif cmd == "/clear":
                session.clear()
                tui.messages.clear()
                tui._update_layout()
                print_ok("Session cleared (context files kept).")

            elif cmd == "/reset":
                session.reset()
                tui.messages.clear()
                tui.clear_right()
                print_ok("Session and context files reset.")

            elif cmd == "/model":
                if len(parts) < 2:
                    print_ok(f"Current Provider: {provider.name}")
                    print_ok(f"Current Model: {provider.model}")
                else:
                    target = parts[1].lower()
                    # Determine provider matching the target substring
                    matching_providers = []
                    for k in config.keys():
                        if isinstance(config[k], dict) and "api_key" in config[k]:
                            if target in k or target in config[k].get("model", ""):
                                matching_providers.append(k)

                    if not matching_providers:
                        print_error(f"No matching provider/model found for '{target}' in config.toml.")
                    elif len(matching_providers) > 1:
                        print_error(f"Ambiguous match for '{target}'. Candidates: {', '.join(matching_providers)}")
                    else:
                        new_provider_name = matching_providers[0]
                        new_provider_config = config[new_provider_name]

                        if new_provider_name == "claude":
                            provider = ClaudeProvider(
                                api_key=new_provider_config.get("api_key", ""),
                                model=new_provider_config.get("model", "claude-sonnet-4-20250514"),
                                base_url=new_provider_config.get("base_url", "https://api.anthropic.com")
                            )
                        else:
                            provider = OpenAICompatProvider(
                                api_key=new_provider_config.get("api_key", ""),
                                model=new_provider_config.get("model", ""),
                                base_url=new_provider_config.get("base_url", "")
                            )

                        provider_name = new_provider_name
                        provider_config = new_provider_config
                        print_ok(f"Switched to {provider.name} / {provider.model}. History preserved.")

            elif cmd == "/status":
                print_ok(f"Provider: {provider.name}")
                print_ok(f"Model: {provider.model}")
                print_ok(f"Session ID: {session.session_id()}")

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
                from rich.table import Table
                from rich.console import Console

                table = Table(title="Session Token Usage")
                table.add_column("Turn", justify="right", style="cyan", no_wrap=True)
                table.add_column("Input", justify="right", style="magenta")
                table.add_column("Output", justify="right", style="green")
                table.add_column("Model", style="blue")

                for t in session.accumulator.turns:
                    table.add_row(
                        str(t.turn),
                        f"{t.input_tokens:,}",
                        f"{t.output_tokens:,}",
                        t.model
                    )

                total_in = session.accumulator.total_input()
                total_out = session.accumulator.total_output()
                pricing = config.get("pricing", {})
                cost = session.accumulator.total_cost_usd(pricing)

                table.add_section()
                table.add_row("Total", f"{total_in:,}", f"{total_out:,}", "")
                table.add_row("Cost", "", f"~${cost:.4f}", "")

                Console().print(table)
                print_ok(f"Poor Mode: {'ON' if session.poor_mode else 'OFF'}  |  Token Guard: {session.token_guard.spike_count}/{session.token_guard.consecutive_limit} spikes")

            elif cmd == "/search":
                if len(parts) < 2:
                    print_error("Usage: /search <query>")
                    continue
                query = parts[1]
                from aic.search.tool import WebSearchTool
                search_tool = WebSearchTool(config)
                results = search_tool.search(query)
                formatted = search_tool.format_for_context(results)

                # Log search to KAIROS
                import aic.kairos as kairos
                kairos.log_event("search", session.session_id(), {
                    "query": query,
                    "provider": "brave" if config.get("search", {}).get("brave_api_key") else "ddg",
                    "result_count": len(results),
                    "trigger": "manual",
                    "latency_ms": 0 # Not tracked for manual here for simplicity
                })

                from rich.markdown import Markdown
                from rich.console import Console
                Console().print(Markdown(formatted))

                # Inject into context as system
                session._messages.append({
                    "role": "system",
                    "content": formatted
                })
                print_ok("Search results injected into current context.")

            elif cmd == "/help":
                print("Available commands:")
                print("  /add <file|dir> - Add a file or directory (max 20 files) to the context")
                print("  /files      - List loaded context files")
                print("  /clear      - Clear conversation history")
                print("  /reset      - Clear history and context files")
                print("  /model      - Show current provider and model")
                print("  /model <x>  - Switch provider/model mid-session")
                print("  /status     - Show status information")
                print("  /tree       - Print directory tree")
                print("  /mcp        - 查看已注册的 MCP server 和工具列表")
                print("  /dream      - 手动触发 Dream 整理（前台同步，显示进度）")
                print("  /search <q> - Search the web immediately")
                print("  /cost       - 查看本次会话消耗")
                print("  /poor       - Toggle Poor Mode")
                print("  /help       - Show this help message")
                print("  /exit       - Exit aic")

            elif cmd == "/mcp":
                tools = registry.list_tools()
                if not tools:
                    print_warning("未注册任何 MCP server。可在 .aic/mcp.json 中配置。")
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
                    print_ok("POOR MODE: ON")
                else:
                    from rich import print as rprint
                    print_warning("POOR MODE: OFF")
                kairos.log_event("poor_toggled", session.session_id(), {"enabled": session.poor_mode})

            elif cmd == "/memory":
                mem_type = parts[1] if len(parts) > 1 else None
                # Support user/feedback/project/reference type check
                if mem_type and mem_type not in ["user", "feedback", "project", "reference"]:
                    print_error(f"Unknown memory type: {mem_type}")
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
                    print_error("Usage: /forget <id>")
                    continue
                target_id = parts[1]
                if len(target_id) < 4:
                    print_error("id 至少需要 4 位")
                    continue

                matches = store.prefix_match(target_id)
                if len(matches) == 0:
                    print_error("未找到匹配的记忆")
                elif len(matches) > 1:
                    for m in matches:
                        print(f"- {m.id}")
                    print_error("前缀冲突，请输入更长的 id")
                else:
                    match = matches[0]
                    from rich.prompt import Confirm
                    content_trunc = match.content[:40]
                    if Confirm.ask(f"确认软删除 {match.id}: {content_trunc}？"):
                        store.soft_delete(match.id)
                        kairos.log_event("memory_forgotten", session.session_id(), {"id": match.id})
                        print_ok("已删除")
                    else:
                        print_warning("已取消")

            elif cmd == "/log":
                logs = kairos.read_today()
                if not logs:
                    print_warning("今日暂无 KAIROS 日志")
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
                print_warning("Exiting...")
                break
            else:
                print_error(f"Unknown command: {cmd}, type /help")
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
            # 原有流式路径（无工具注册 or poor_mode），引入 Auto-Search 重入逻辑
            search_config = config.get("search", {})
            auto_search_enabled = search_config.get("auto_search", False)

            from aic.search.tool import WebSearchTool, SEARCH_TOOL_SCHEMA
            search_tool = WebSearchTool(config)

            tui.start()

            search_loops = 0
            MAX_SEARCH_LOOPS = 3

            while True:
                tui.render_stream_start()

                tools_param = []
                if auto_search_enabled and not session.poor_mode:
                    tools_param.append(SEARCH_TOOL_SCHEMA)

                stream_messages = session.get_messages()
                tool_calls_detected = None

                try:
                    for chunk in provider.stream(stream_messages, tools=tools_param, system=session.get_system()):
                        if isinstance(chunk, dict):
                            if chunk.get("type") == "usage":
                                session.accumulator.record(
                                    input_tokens=chunk.get("input_tokens", 0),
                                    output_tokens=chunk.get("output_tokens", 0),
                                    provider=provider.name,
                                    model=provider.model
                                )
                                if session.token_guard.record(chunk.get("output_tokens", 0)):
                                    if not session.poor_mode:
                                        session.activate_poor_mode(reason="token_guard")
                                        from rich.console import Console
                                        Console().print("\n[bold red][!] Token spike detected (3 consecutive responses > 2000 tokens). Poor Mode auto-activated.[/bold red]")
                            elif chunk.get("type") == "tool_calls":
                                tool_calls_detected = chunk.get("tool_calls", [])
                                # 流式检测到 tool_calls 时停止输出
                                tui.streaming = False
                            continue

                        if not tool_calls_detected:
                            tui.render_stream_chunk(chunk)
                except Exception as e:
                    tui.render_stream_chunk(f"\n[错误] 流式请求异常: {str(e)}")
                    break

                final_content = tui.stream_content
                tui.render_stream_end()

                if tool_calls_detected:
                    search_loops += 1
                    if search_loops > MAX_SEARCH_LOOPS:
                        tui.render_stream_chunk("\n[!] Search loop limit reached.")
                        break

                    call = tool_calls_detected[0]
                    # Format standard open-compat or claude tool call shape
                    func = call.get("function", {})
                    name = func.get("name")
                    try:
                        import json
                        args = json.loads(func.get("arguments", "{}"))
                    except:
                        args = {}

                    if name != "web_search":
                        tool_result = f"Error: Tool {name} not allowed."
                    else:
                        query = args.get("query", "")
                        results = search_tool.search(query)
                        tool_result = search_tool.format_for_context(results)

                        import aic.kairos as kairos
                        kairos.log_event("search", session.session_id(), {
                            "query": query,
                            "provider": "brave" if config.get("search", {}).get("brave_api_key") else "ddg",
                            "result_count": len(results),
                            "trigger": "auto",
                            "latency_ms": 0
                        })

                    session._messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id", "call_search"),
                        "content": tool_result
                    })

                    # Continue the while True loop with the new context
                    tui.stream_content = ""
                    continue
                else:
                    break

            tui.stop()

        session.add_assistant(final_content)

        # turn_completed event
        import aic.kairos as kairos

        last_turn = session.accumulator.turns[-1] if session.accumulator.turns else None

        kairos.log_event("turn_completed", session.session_id(), {
            "turn": len(session.accumulator.turns),
            "input_tokens": last_turn.input_tokens if last_turn else 0,
            "output_tokens": last_turn.output_tokens if last_turn else 0,
            "provider": provider.name,
            "model": provider.model,
            "poor_mode": session.poor_mode
        })

        if not session.poor_mode:
            scheduler.run(force=False)
