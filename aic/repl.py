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

def start(config: dict):
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
