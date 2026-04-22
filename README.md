# aic — AI Coding Assistant

> 个人使用的命令行 AI 编程助手，直连主流 LLM API，无服务器依赖，无 Electron，无代理问题。
> 内部使用，不开源。2026

---

## 项目定位

aic 的本质是一个**轻量化、私有、具备长程记忆**的 AI 编程辅助器，目标是复刻并优化类似 Claude Code 的工程实践，同时保持极简依赖（核心只有 `httpx` + `rich` + 标准库）。

---

## 架构分层

| 层级 | 模块 | 职责 |
|------|------|------|
| L0 入口层 | `main.py` | argparse，参数解析，调起 repl |
| L1 会话层 | `repl.py` / `session.py` / `config.py` / `tui.py` | 对话循环、slash 命令、消息管理、分栏渲染 |
| L2 Provider 层 | `providers/base.py` + `claude.py` + `openai_compat.py` | 抽象流式接口，多 provider 路由 |
| L3 Memory 层 | `memory/store.py` + `extractor.py` + `types.py` | SQLite 存储，每轮提取，记忆分类 |
| L4 Dream 层 | `dream/scheduler.py` + `lock.py` + `consolidator.py` + `agent.py` | 三道门控，4 阶段整理，受限子代理 |
| L5 MCP 层 | `mcp/loader.py` + `runner.py` + `registry.py` | 工具调用（后期） |
| L6 持久化 | `~/.aic/memory.db` + `.dream-lock` + `config.toml` | SQLite 记忆库，PID 锁，全局配置 |

---

## TUI 分栏设计

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

- 终端宽度 ≥ 120 列：左右各 50% 分栏
- 终端宽度 < 120 列：自动退化为单列
- 无文件加载时：全宽显示对话
- 代码块未闭合前右栏显示占位符，闭合后触发 diff 渲染

---

## Provider 支持

| Provider | 接口类型 | 备注 |
|----------|----------|------|
| Claude | Anthropic 原生 API | `x-api-key` header |
| DeepSeek | OpenAI 兼容 | 主力便宜模型 |
| Gemini | OpenAI 兼容 | Jules 使用 |
| GPT / o 系列 | OpenAI 兼容 | 按需使用 |
| Step（阶跃星辰） | OpenAI 兼容 | 便宜，agent 微调，后续考虑 |
| 任意兼容 provider | OpenAI 兼容 | config.toml 配 base_url 即可 |

所有 provider 统一继承 `BaseProvider`，实现 `stream()` 接口，含 status_code 检查和网络异常捕获。

---

## 配置

```toml
# ~/.config/aic/config.toml
provider = "deepseek"

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

[dream]
min_unprocessed = 20
min_interval_h  = 24
min_sessions    = 5
lock_timeout_h  = 1
model           = "deepseek-chat"
```

环境变量优先级：`ENV > config.toml > 默认值`

---

## 上下文注入（双层）

- **全局级**：`~/.aic/GLOBAL_CONTEXT.md` — 编程习惯、偏好，所有项目生效
- **项目级**：`.aic/CONTEXT.md` — 当前项目特定指令，覆盖全局

注入顺序：全局在前，项目在后。

---

## Memory 层

### 记忆类型

| 类型 | 示例 |
|------|------|
| `user` | 偏好中文交流；用 uv 管理环境 |
| `feedback` | 不要生成测试桩；必须加 type hints |
| `project` | 合并冻结从3月开始；认证是合规需求 |
| `reference` | DeepSeek 文档地址；Linear 项目 ID |

### SQLite 表结构

```sql
CREATE TABLE memories (
    id            TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    content       TEXT NOT NULL,
    weight        REAL DEFAULT 1.0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    source        TEXT,
    is_archived   INTEGER DEFAULT 0,    -- 软删除，不硬删
    superseded_by TEXT                  -- 指向替代条目的 id
);
```

### Poor Mode

`/poor` 命令切换，token 紧张时使用：
- 跳过 extractor，不提取记忆
- 跳过 dream 自动触发
- Web Search 不受影响

---

## Dream 层

### 三道门控

| 门 | 条件 |
|----|------|
| 门1 数量门 | 未整理记忆条数 ≥ 20 |
| 门2 时间门 | 距上次 dream ≥ 24h 且历史会话数 ≥ 5 |
| 门3 锁门 | PID 锁不存在 / 持有者已死 / mtime 超过1小时 |

### 4 阶段整理

| 阶段 | 名称 | 操作 |
|------|------|------|
| Phase 1 | Orient 定位 | 查看现有条目，了解全貌 |
| Phase 2 | Gather 采集 | 过时记忆 → 新增条目 → 隐含信息 |
| Phase 3 | Merge 合并 | 合并新信号，相对日期转绝对，软删除被推翻事实 |
| Phase 4 | Prune 修剪 | 低权重+高龄条目归档，每类控制数量 |

### 断点续传

`.dream-lock` 存储 JSON 格式任务状态，记录当前执行到 Phase 几，崩溃重启后从断点继续，不重复消耗 token。

---

## Slash 命令

| 命令 | 功能 | 阶段 |
|------|------|------|
| `/add <file>` | 注入文件到上下文（自动检测二进制拒绝加载） | 一 |
| `/files` | 查看已加载文件 | 一 |
| `/clear` | 清空对话历史 | 一 |
| `/reset` | 清空历史 + 上下文文件 | 一 |
| `/model` | 切换 provider/model | 一 |
| `/status` | 当前 provider、model、session_id | 一 |
| `/tree` | 显示当前目录树 | 一 |
| `/poor` | 开关 Poor Mode | 二 |
| `/memory [type]` | 查看/搜索记忆 | 二 |
| `/forget <id>` | 软删除记忆条目 | 二 |
| `/log` | 查看今日 KAIROS 日志 | 二 |
| `/dream` | 手动触发 Dream 整理 | 三 |
| `/cost` | token 用量和费用估算 | 五 |
| `/help` | 显示帮助 | 一 |
| `/exit` | 退出 | 一 |

---

## 开发路线图

### 阶段一 ✅ 已完成

- [x] 目录骨架
- [x] config.py
- [x] BaseProvider + OpenAICompatProvider
- [x] ClaudeProvider
- [x] session.py（含双层 CONTEXT 注入）
- [x] tui.py（左对话右 diff 分栏）
- [x] repl.py 主循环 + slash 基础命令
- [x] 集成测试 + .gitignore（#8 进行中）

### 阶段二 ✅ 已完成

并行三个 issue：
- [x] **#9** `memory/types.py` + `memory/store.py` — SQLite 建表，软删除字段
- [x] **#10** `memory/extractor.py` — 每轮提取，Poor Mode 跳过
- [x] **#11** KAIROS 日志 + `/poor` `/memory` `/forget` `/log` 命令

### 阶段三 ✅ 已完成，正在验收

- [x] Dream 三道门控 + PID 锁 + 断点续传
- [x] Consolidator 4 阶段 + 受限子代理
- [x] `/dream` 命令

### 阶段四

- MCP loader/runner/registry
- `.aic/mcp.json` 配置格式

### 阶段五

- Web Search 内置工具（Brave API 优先，降级 DuckDuckGo）
- `/cost` token 统计
- 体验打磨

### 阶段六（远期）

- **多 Agent 协作**：参考 OpenClaw 架构，针对安全性做调整，开源社区已有多个参考实现
- **Discord 集成**：为 agent 创建 Discord 账号，通过 Discord 服务器传递信号，实现远程任务触发和结果推送
- **Step 模型深度集成**：阶跃星辰 agent 微调版本，适合后台 Dream 子代理（价格优势 + agent 能力）
- **Langfuse 监控**：agent 可观测性，追踪 token 消耗和任务链路
- **自举模式**：对 aic 自身进行修改时，自动加载源码作为上下文

---

## 快速开始

```bash
git clone https://github.com/你的用户名/AI-C.git aic
cd aic
uv venv
uv pip install -e .

# 配置
cp config.example.toml ~/.config/aic/config.toml
# 编辑填入 API key

# 启动
aic
# 或
python -m aic
```

---

## 依赖约定

- `httpx` — HTTP 客户端，流式支持
- `rich` — TUI 渲染
- `sqlite3` — 标准库，memory 层
- Python 3.12+
- **严禁**引入 `openai` 或 `anthropic` SDK

---

## 开发约定

- providers 层：mock `httpx` 的 stream 响应做单元测试
- memory 层：用 `:memory:` SQLite 跑单元测试
- dream 层：mock lock 文件和子代理调用
- 测试统一用标准库 `unittest`，不引入 pytest

---

*— 内部使用，不开源 —*
