"""
L1 会话层：TUI 渲染层（分栏布局）
"""
import difflib
from typing import Optional, List, Dict
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.table import Table

class TUIRenderer:
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.messages: List[Dict[str, str]] = []

        self.streaming = False
        self.stream_content = ""

        self.right_renderable: Optional[RenderableType] = None
        self.status_renderable: Optional[RenderableType] = None

        self.live: Optional[Live] = None

        self._init_layout()

    def _init_layout(self):
        self.layout.split_column(
            Layout(name="main", ratio=1),
            Layout(name="status", size=1)
        )
        self.layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right", visible=False)
        )

    def _build_left_panel(self) -> RenderableType:
        text = Text()
        for msg in self.messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                text.append(f"> {content}\n\n", style="bold green")
            elif role == "assistant":
                text.append(f"aic: {content}\n\n", style="white")
            elif role == "system":
                text.append(f"[system] {content}\n\n", style="dim")

        if self.streaming:
            text.append(f"aic: {self.stream_content}", style="white")

        return Panel(text, title="对话", border_style="blue")

    def _update_layout(self):
        width = self.console.width

        # Check if code block is incomplete
        in_code_block = False
        if self.streaming:
            # Simple check for odd number of triple backticks
            backtick_count = self.stream_content.count("```")
            in_code_block = (backtick_count % 2) != 0

        # Decide what to show on right side
        current_right = self.right_renderable
        if in_code_block:
            current_right = Panel("⏳ 等待代码块...", title="文件变更", border_style="yellow")

        # Update visibility
        if width < 120 or current_right is None:
            self.layout["main"]["right"].visible = False
            self.layout["main"]["left"].ratio = 1
        else:
            self.layout["main"]["right"].visible = True
            self.layout["main"]["right"].update(current_right)
            self.layout["main"]["left"].ratio = 1
            self.layout["main"]["right"].ratio = 1

        self.layout["main"]["left"].update(self._build_left_panel())

        if self.status_renderable:
            self.layout["status"].update(self.status_renderable)
        else:
            self.layout["status"].update(Text(""))

        if self.live:
            self.live.refresh()

    def start(self):
        self.live = Live(self.layout, console=self.console, refresh_per_second=10)
        self.live.start()

    def stop(self):
        if self.live:
            self.live.stop()
            self.live = None

    def render_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self._update_layout()

    def render_stream_start(self):
        self.streaming = True
        self.stream_content = ""
        self._update_layout()

    def render_stream_chunk(self, chunk: str):
        self.stream_content += chunk
        self._update_layout()

    def render_stream_end(self):
        self.streaming = False
        self.messages.append({"role": "assistant", "content": self.stream_content})
        self.stream_content = ""
        self._update_layout()

    def render_file(self, filepath: str, content: str):
        syntax = Syntax(content, filepath.split('.')[-1] if '.' in filepath else 'text', theme="monokai", line_numbers=True)
        self.right_renderable = Panel(syntax, title=filepath, border_style="green")
        self._update_layout()

    def render_diff(self, filepath: str, before: str, after: str):
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff = list(difflib.unified_diff(before_lines, after_lines, fromfile=filepath, tofile=filepath))

        diff_text = Text()
        additions = 0
        deletions = 0

        for line in diff:
            if line.startswith('---') or line.startswith('+++'):
                diff_text.append(line, style="bold")
            elif line.startswith('@@'):
                diff_text.append(line, style="cyan")
            elif line.startswith('+'):
                diff_text.append(line, style="on #1e3a1e")
                additions += 1
            elif line.startswith('-'):
                diff_text.append(line, style="on #3a1e1e")
                deletions += 1
            else:
                diff_text.append(line)

        diff_text.append(f"\n✓ {additions} additions, {deletions} deletions", style="dim")

        self.right_renderable = Panel(diff_text, title=f"Diff: {filepath}", border_style="yellow")
        self._update_layout()

    def render_status(self, provider: str, model: str, tokens: int):
        table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        table.add_row(
            f"[dim][provider: {provider}][/dim]",
            f"[dim][model: {model}][/dim]",
            f"[dim][tokens: {tokens:,}][/dim]"
        )
        self.status_renderable = table
        self._update_layout()

    def clear_right(self):
        self.right_renderable = None
        self._update_layout()
