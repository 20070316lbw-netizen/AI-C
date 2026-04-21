# aic — AI Coding Assistant 完整设计文档

> 内部文档 · 不开源 · 2026

---

## 1. 项目概述

aic 是一个命令行 AI 编程助手，直连主流 LLM API，无服务器依赖，无 electron，无代理问题。

**核心原则：**

- 直连 API，不依赖任何第三方 CLI 框架（Antigravity、OpenCode 等）
- 模块分层，每层职责单一，后期可独立替换
- Agent prompt 文件驱动，存放在 `.aic/agents/`，不硬编码在源码里
- 记忆体系 + Dream 整理机制，借鉴 Claude Code 泄露源码（2026-03-31）架构
- 本项目仅供个人使用，不开源，直到有服务器需求再考虑

---

## 2. 架构分层

整体分为 7 层，从上到下依赖，下层对上层透明：

| 层级 | 模块 | 职责 |
|------|------|------|
| L0 入口层 | `main.py` | argparse，参数解析，调起 repl |
| L1 会话层 | `repl.py` / `session.py` / `config.py` | 对话循环、slash 命令、消息管理、配置 |
| L2 Provider 层 | `providers/base.py` + `claude.py` + `openai_compat.py` | 抽象流式接口，多 provider 路由 |
| L3 Memory 层 | `memory/store.py` + `extractor.py` + `types.py` | SQLite 存储，每轮提取，记忆分类 |
| L4 Dream 层 | `dream/scheduler.py` + `lock.py` + `consolidator.py` + `agent.py` | 三道门控，4 阶段整理，受限子代理 |
| L5 MCP 层 | `mcp/loader.py` + `runner.py` + `registry.py` | 工具调用循环，server 注册（后期） |
| L6 持久化 | `~/.aic/memory.db` + `.dream-lock` + `config.toml` | SQLite 记忆库，PID 锁，全局配置 |

---

## 3. 目录结构

### 3.1 源码目录

```
aic/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── config.example.toml
├── aic/
│   ├── __init__.py
│   ├── main.py                # L0 入口，argparse
│   ├── repl.py                # L1 对话循环，slash 命令路由
│   ├── session.py             # L1 messages 管理，context files 注入
│   ├── config.py              # L1 config.toml 加载/保存，env 覆盖
│   ├── tui.py                 # L1 TUI 渲染层（分栏布局）
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py            # 抽象类 BaseProvider，stream() 接口
│   │   ├── claude.py          # Anthropic 原生 API
│   │   └── openai_compat.py   # DS / GPT / Gemini / Moonshot 等
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py           # SQLite CRUD，weight/age 字段
│   │   ├── extractor.py       # 每轮对话结束后提取记忆片段
│   │   └── types.py           # MemoryType: user/feedback/project/reference
│   ├── dream/
│   │   ├── __init__.py
│   │   ├── scheduler.py       # 三道门控 + executeAutoDream()
│   │   ├── lock.py            # .dream-lock PID锁，mtime回滚
│   │   ├── consolidator.py    # 4阶段 prompt 构建 + 调用子代理
│   │   └── agent.py           # 受限子代理，只读工具+只写memory/
│   └── mcp/                   # 后期加
│       ├── __init__.py
│       ├── loader.py
│       ├── runner.py
│       └── registry.py
```

### 3.2 项目级配置目录（`.aic/`）

放在每个使用 aic 的项目根目录下，加入 `.gitignore`：

```
.aic/
├── CONTEXT.md           # 项目指令，启动时自动注入上下文
├── mcp.json             # 本项目的 MCP server 列表
└── agents/
    ├── dream.md         # /dream 手动入口（hidden: false）
    └── consolidator.md  # dream 子代理（hidden: true，工具受限）
```

### 3.3 全局数据目录（`~/.aic/`）

```
~/.aic/
├── memory.db        # SQLite，所有记忆条目
├── .dream-lock      # PID 锁文件，mtime = lastDreamAt
└── logs/
    └── YYYY/MM/
        └── YYYY-MM-DD.md
```

---

## 4. TUI 分栏设计

### 4.1 布局

```
┌─────────────────────────┬──────────────────────────┐
│  💬 对话                │  📄 文件变更              │
│                         │                           │
│ > /add main.py          │  main.py                  │
│ aic: 已加载 main.py     │  @@ -12,4 +12,6 @@        │
│                         │   def run():              │
│ > 帮我加初始化逻辑      │ +     init_memory()       │
│ aic: 建议在 run() 里    │ +     load_config()       │
│ 加这两行...             │       start_repl()        │
│                         │                           │
│                         │  ✓ 2 additions            │
└─────────────────────────┴──────────────────────────┘
  [provider: deepseek]  [model: deepseek-chat]  [tokens: 1,204]
```

### 4.2 触发规则

- **无文件加载时**：全宽显示对话，不渲染右栏
- **`/add <file>` 后**：右栏显示文件内容（语法高亮）
- **模型回复含代码块时**：右栏渲染 diff（before = 原文件，after = 模型建议）
- **终端宽度 < 120 列**：自动退化为单列模式

### 4.3 实现要点

- 使用 `rich.layout.Layout` + `rich.live.Live` 实现动态刷新
- diff 用 `difflib.unified_diff` 生成，再用 `rich.syntax.Syntax` 渲染高亮
- 加减行背景色：`+` 绿色（`#1e3a1e`），`-` 红色（`#3a1e1e`）
- 底部状态栏：`rich.table.Table` 单行，显示 provider / model / token 用量

---

## 5. Provider 层

### 5.1 设计原则

所有 provider 继承 `BaseProvider`，实现统一的 `stream()` 接口。repl 层只调用接口，不感知底层实现。新增 provider 只需新增文件或在 `config.toml` 里配 `base_url`，不改上层代码。

### 5.2 支持的 Provider

| Provider | 文件 | 接口类型 | 备注 |
|----------|------|----------|------|
| Claude | `claude.py` | Anthropic 原生 API | `x-api-key` header，`anthropic-version` |
| DeepSeek | `openai_compat.py` | OpenAI 兼容 | `base_url = api.deepseek.com` |
| GPT / o 系列 | `openai_compat.py` | OpenAI 兼容 | `base_url = api.openai.com` |
| Gemini | `openai_compat.py` | OpenAI 兼容 | `base_url = generativelanguage.googleapis.com` |
| Moonshot 等 | `openai_compat.py` | OpenAI 兼容 | `config.toml` 里配 `base_url` 即可 |

### 5.3 配置格式（`~/.config/aic/config.toml`）

```toml
provider = "deepseek"   # 默认 provider

[claude]
api_key  = "sk-ant-..."
model    = "claude-sonnet-4-20250514"
base_url = "https://api.anthropic.com"

[deepseek]
api_key  = "sk-..."
model    = "deepseek-chat"
base_url = "https://api.deepseek.com"

[gemini]
api_key  = "..."
model    = "gemini-2.5-pro"
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"

[custom]
api_key  = "..."
model    = "model-name"
base_url = "https://your-provider.com"
```

### 5.4 环境变量覆盖

```
ANTHROPIC_API_KEY   → claude.api_key
DEEPSEEK_API_KEY    → deepseek.api_key
GEMINI_API_KEY      → gemini.api_key
AIC_PROVIDER        → provider
```

优先级：环境变量 > `config.toml` > 代码默认值

---

## 6. Memory 层

### 6.1 记忆类型（MemoryType）

| 类型 | 用途 | 示例 |
|------|------|------|
| `user` | 用户角色、偏好、习惯 | 用户偏好中文交流；用 uv 管理环境 |
| `feedback` | 工作方式指导 | 不要生成测试桩；代码审查要完整 |
| `project` | 项目上下文（非代码可推导） | 合并冻结从3月开始；认证是合规需求 |
| `reference` | 外部系统指针 | DeepSeek 文档地址；Linear 项目 ID |

**不保存：** 代码模式、架构、文件路径（可从代码推导）；Git 历史；调试方案。

### 6.2 SQLite 表结构

```sql
CREATE TABLE memories (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    content    TEXT NOT NULL,
    weight     REAL DEFAULT 1.0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    source     TEXT
);
```

### 6.3 Poor Mode

`/poor` 命令切换：
- 跳过 extractor，不提取记忆
- 跳过 dream auto 触发
- Web Search 不受影响

---

## 7. Dream 层

### 7.1 三道门控

| 门 | 条件 |
|----|------|
| 门1 | `memory.db` 未整理条数 >= 20（可配置） |
| 门2 | 距上次 dream >= 24h 且历史会话数 >= 5 |
| 门3 | PID 锁不存在 / 持有者已死 / mtime 超过1小时 |

### 7.2 4 阶段整理

| 阶段 | 名称 | 操作 |
|------|------|------|
| Phase 1 | Orient 定位 | 查看现有条目，了解全貌，避免重复 |
| Phase 2 | Gather 采集 | 过时记忆 → 新增条目 → 隐含信息 |
| Phase 3 | Merge 合并 | 合并新信号，相对日期转绝对，删推翻事实 |
| Phase 4 | Prune 修剪 | 低权重+高龄条目删除，每类控制数量 |

### 7.3 受限子代理

工具白名单：`read_memory`, `list_memories`, `write_memory`, `delete_memory`

禁止：shell 命令、memory/ 以外文件读写、网络请求。

建议 model：`deepseek-chat` 或 `claude-haiku`（省钱）。

---

## 8. Agent Prompt 文件格式

```markdown
---
mode: subagent
hidden: true
model: deepseek-chat
tools:
  "*": false
  "read_memory": true
  "write_memory": true
---

（prompt 正文）
```

---

## 9. Slash 命令全览

| 命令 | 功能 | 阶段 |
|------|------|------|
| `/add <file>` | 注入文件到上下文 | 一 |
| `/files` | 查看已加载文件 | 一 |
| `/clear` | 清空对话历史 | 一 |
| `/reset` | 清空历史 + 上下文文件 | 一 |
| `/model` | 交互式切换 provider/model | 一 |
| `/status` | 当前 provider 和 model | 一 |
| `/tree` | 显示当前目录树 | 一 |
| `/poor` | 开关 Poor Mode | 二 |
| `/memory [type]` | 查看/搜索记忆 | 二 |
| `/forget <id>` | 删除记忆条目 | 二 |
| `/log` | 查看今日 KAIROS 日志 | 二 |
| `/dream` | 手动触发 Dream 整理 | 三 |
| `/cost` | token 用量和费用估算 | 五 |
| `/help` | 显示帮助 | 一 |
| `/exit` | 退出 | 一 |

---

## 10. 开发路线图

| 阶段 | 内容 | 关键产出 |
|------|------|----------|
| 阶段一 | Provider 抽象；session/config 拆分；TUI 分栏；`.aic/CONTEXT.md` 注入；slash 基础命令 | 可用的多 provider CLI |
| 阶段二 | memory 全套；KAIROS 日志；Poor Mode | 记忆体系可用 |
| 阶段三 | Dream 三道门；lock；consolidator；受限子代理 | 自动整理记忆 |
| 阶段四 | MCP loader/runner/registry | 可接任意 MCP server |
| 阶段五 | Web Search；`/cost` 统计；体验打磨 | 功能完整 |

---

## 11. 开发约定

- 核心依赖只有 `httpx` + `rich`，不引入 anthropic SDK
- memory 层只用 `sqlite3`（标准库），不引入 SQLAlchemy
- dream agent 调用复用 providers 层

---

*— end of document —*
