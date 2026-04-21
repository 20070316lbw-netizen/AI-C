# aic 阶段一 Issue 列表

> 按顺序喂给 Jules，每次给一个。
> 所有 issue 都应附上：「参考 DESIGN.md 对应章节，严格遵守依赖约定（只用 httpx + rich + 标准库）。」

---

## Issue #1 — 目录骨架 + pyproject.toml

**标题：** `[Stage 1] 初始化项目目录结构`

**内容：**

按照 DESIGN.md §3.1 创建完整的源码目录骨架：

```
aic/
├── pyproject.toml          # 已存在，不要修改
├── aic/
│   ├── __init__.py
│   ├── main.py             # 只写 argparse 骨架 + 调用 repl.start()
│   ├── repl.py             # 只写空的 start() 函数，打印 "aic ready"
│   ├── session.py          # 空模块，留 TODO
│   ├── config.py           # 空模块，留 TODO
│   ├── tui.py              # 空模块，留 TODO
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py         # 空模块，留 TODO
│   │   ├── claude.py       # 空模块，留 TODO
│   │   └── openai_compat.py# 空模块，留 TODO
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py        # 空模块，留 TODO
│   │   ├── extractor.py    # 空模块，留 TODO
│   │   └── types.py        # 空模块，留 TODO
│   ├── dream/
│   │   ├── __init__.py
│   │   ├── scheduler.py    # 空模块，留 TODO
│   │   ├── lock.py         # 空模块，留 TODO
│   │   ├── consolidator.py # 空模块，留 TODO
│   │   └── agent.py        # 空模块，留 TODO
│   └── mcp/
│       ├── __init__.py
│       ├── loader.py       # 空模块，留 TODO
│       ├── runner.py       # 空模块，留 TODO
│       └── registry.py     # 空模块，留 TODO
```

要求：
- `main.py` 用 argparse，支持 `--provider` / `--model` 两个可选参数
- `python -m aic` 可运行，打印一行 "aic ready" 后退出
- 所有空模块顶部写明该模块职责的 docstring

---

## Issue #2 — config.py：配置加载

**标题：** `[Stage 1] config.py — config.toml 加载与环境变量覆盖`

**内容：**

实现 `aic/config.py`，参考 DESIGN.md §5.3 和 §5.4。

功能：
1. 从 `~/.config/aic/config.toml` 读取配置（文件不存在时使用默认值，不报错）
2. 环境变量覆盖：`ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `AIC_PROVIDER`
3. 优先级：环境变量 > config.toml > 代码默认值
4. 暴露 `get_config() -> dict` 函数，返回合并后的完整配置

数据结构示例（返回值）：
```python
{
    "provider": "deepseek",
    "claude": {"api_key": "...", "model": "...", "base_url": "..."},
    "deepseek": {"api_key": "...", "model": "...", "base_url": "..."},
    "gemini": {"api_key": "...", "model": "...", "base_url": "..."},
    "dream": {"min_unprocessed": 20, "min_interval_h": 24, ...},
}
```

依赖：只用标准库 `tomllib`（Python 3.11+ 内置）+ `os`。

---

## Issue #3 — providers/base.py + openai_compat.py

**标题：** `[Stage 1] providers — BaseProvider 抽象类 + OpenAI 兼容实现`

**内容：**

参考 DESIGN.md §5.1 和 §5.2。

### base.py

```python
from abc import ABC, abstractmethod
from typing import Iterator

class BaseProvider(ABC):
    @abstractmethod
    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """流式返回 token，每次 yield 一个字符串片段。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...
```

### openai_compat.py

实现 `OpenAICompatProvider(BaseProvider)`：
- 用 `httpx` 发 POST 到 `{base_url}/chat/completions`
- 请求体：`{"model": ..., "messages": ..., "stream": true}`
- 解析 SSE 流：按行读，跳过非 `data:` 行，解析 JSON，提取 `choices[0].delta.content`
- `stream()` 方法 yield 每个 content 片段，遇到 `[DONE]` 停止
- 构造函数接收 `api_key`, `model`, `base_url`

只用 `httpx`，不引入 openai SDK。

---

## Issue #4 — providers/claude.py

**标题：** `[Stage 1] providers — Claude 原生 API 实现`

**内容：**

实现 `ClaudeProvider(BaseProvider)`，参考 DESIGN.md §5.2。

- POST 到 `https://api.anthropic.com/v1/messages`
- Headers：`x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`
- 请求体：`{"model": ..., "messages": ..., "max_tokens": 8096, "stream": true}`
- 解析 SSE 流：提取 `event: content_block_delta` + `delta.text`
- `stream()` yield 每个 text 片段

只用 `httpx`。

---

## Issue #5 — session.py：消息管理

**标题：** `[Stage 1] session.py — 消息历史与上下文文件管理`

**内容：**

实现 `Session` 类，参考 DESIGN.md §3.1。

```python
class Session:
    def __init__(self, config: dict): ...
    def add_user(self, content: str): ...
    def add_assistant(self, content: str): ...
    def add_context_file(self, path: str): ...   # 读文件，注入 system message
    def get_messages(self) -> list[dict]: ...     # 返回完整 messages 列表
    def list_context_files(self) -> list[str]: ...
    def clear(self): ...        # 清空历史，保留 context files
    def reset(self): ...        # 清空历史 + context files
    def session_id(self) -> str: ...   # UUID，本次会话唯一标识
```

- 启动时自动检测当前目录下 `.aic/CONTEXT.md`，存在则注入为 system message
- `add_context_file` 读取文件内容，追加到 system prompt（多文件用分隔线隔开）

---

## Issue #6 — tui.py：分栏 TUI 渲染

**标题：** `[Stage 1] tui.py — 左对话右 diff 分栏布局`

**内容：**

实现 `TUIRenderer` 类，参考 DESIGN.md §4。

**布局规则：**
- 终端宽度 >= 120 列：左右各50%，左对话右文件/diff
- 终端宽度 < 120 列：单列，只显示对话

**接口：**
```python
class TUIRenderer:
    def render_message(self, role: str, content: str): ...
    # role = "user" | "assistant" | "system"

    def render_stream_start(self): ...
    def render_stream_chunk(self, chunk: str): ...
    def render_stream_end(self): ...

    def render_file(self, filepath: str, content: str): ...
    # 右栏显示文件内容（语法高亮）

    def render_diff(self, filepath: str, before: str, after: str): ...
    # 右栏显示 unified diff（加减行高亮）

    def render_status(self, provider: str, model: str, tokens: int): ...
    # 底部状态栏

    def clear_right(self): ...
    # 清空右栏
```

**实现要点：**
- 用 `rich.layout.Layout` + `rich.live.Live`
- diff 用 `difflib.unified_diff` 生成
- 加行背景 `#1e3a1e`，减行背景 `#3a1e1e`
- 底部状态栏用 `rich.table.Table` 单行

只用 `rich` + 标准库。

---

## Issue #7 — repl.py：主对话循环

**标题：** `[Stage 1] repl.py — REPL 主循环 + slash 命令路由`

**内容：**

实现 `start(config: dict)` 函数，这是 aic 的主入口。参考 DESIGN.md §10（阶段一命令）。

**主循环：**
1. 初始化 `Session`、`TUIRenderer`、provider（根据 config 选择）
2. 显示欢迎信息 + 当前 provider/model
3. 循环读取用户输入（`input("> ")`），支持 Ctrl+D 退出
4. slash 命令路由（字典 dispatch）
5. 非 slash 输入：追加到 session，调用 `provider.stream()`，流式渲染到左栏

**阶段一 slash 命令：**

| 命令 | 行为 |
|------|------|
| `/add <file>` | `session.add_context_file(path)`，`tui.render_file(path, content)` |
| `/files` | 打印 `session.list_context_files()` |
| `/clear` | `session.clear()`，清空左栏显示 |
| `/reset` | `session.reset()`，清空左右栏 |
| `/model` | 打印当前 provider/model，提示用 `--provider` / `--model` 启动参数切换（交互式切换留阶段二） |
| `/status` | 打印 provider、model、session_id |
| `/tree` | 用 `os.walk` 打印当前目录树（忽略 `.git` / `__pycache__` / `.venv`） |
| `/help` | 打印命令列表 |
| `/exit` | 退出 |

**错误处理：**
- provider 请求失败：捕获异常，打印错误，不退出
- 未知 slash 命令：提示 `/help`

---

## Issue #8 — 集成测试 + .gitignore

**标题：** `[Stage 1] 集成：main.py 串联 + .gitignore + 冒烟测试`

**内容：**

1. **main.py** 完整实现：
   - `argparse`：`--provider`（默认从 config），`--model`（默认从 config）
   - 加载 config，覆盖 provider/model，调用 `repl.start(config)`

2. **.gitignore**：
```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
~/.aic/
.aic/
config.toml
```

3. **冒烟测试**（写在 `tests/test_smoke.py`）：
   - `test_config_defaults()`：`get_config()` 在无文件无环境变量时返回合理默认值
   - `test_openai_compat_stream()`：mock `httpx`，验证 SSE 解析正确 yield token
   - `test_session_add_and_clear()`：验证消息追加和清空逻辑

   用标准库 `unittest`，不引入 pytest（减少依赖）。

4. **验收标准**：
   - `python -m aic --provider deepseek` 启动不报错，显示欢迎信息
   - `/help` 输出所有命令
   - `/exit` 或 Ctrl+D 干净退出
