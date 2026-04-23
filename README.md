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
| L5 MCP 层 | `mcp/loader.py` + `runner.py` + `registry.py` | 工具调用沙箱 |
| L6 持久化 | `~/.aic/memory.db` + `.dream-lock` + `config.toml` | SQLite 记忆库，PID 锁，全局配置 |
| L7 Search 层 | `search/brave.py` + `search/ddg.py` + `search/tool.py` | 内置 Web 检索，Brave 优先降级 DDG |
| L8 Distill 层 | `distill/db.py` + `distill/pipeline.py` + `distill/primer.py` | 离线蒸馏，用户画像，Context Priming |
| L9 Event Bus 层 | `eventbus/server.py` + `eventbus/handlers/` | 系统事件感知，shell hook，Clash 监控 |

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
| DeepSeek | OpenAI 兼容 | 主力便宜模型，决策层 |
| Gemini | OpenAI 兼容 | Jules 使用 |
| Grok | OpenAI 兼容 | xAI API，coding/推理专项 |
| Step（阶跃星辰） | OpenAI 兼容 | 便宜，规划中作主理人模型 |
| 任意兼容 provider | OpenAI 兼容 | config.toml 配 base_url 即可 |

所有 provider 统一继承 `BaseProvider`，实现 `stream()` 接口，含 usage sentinel、status_code 检查和网络异常捕获。

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

[grok]
api_key  = "xai-..."
model    = "grok-3-fast"
base_url = "https://api.x.ai/v1"

[dream]
min_unprocessed = 20
min_interval_h  = 24
min_sessions    = 5
lock_timeout_h  = 1
model           = "deepseek-chat"

[search]
auto_search   = false
brave_api_key = ""
max_results   = 5

[pricing]
"claude-sonnet"  = [3.00, 15.00]
"claude-opus"    = [15.00, 75.00]
"deepseek-chat"  = [0.27, 1.10]
"grok-3-fast"    = [0.20, 0.40]

[distill]
gate2_hours             = 24
gate3_min_conversations = 10
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

### SQLite 表结构（sql1）

```sql
CREATE TABLE memories (
    id            TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    content       TEXT NOT NULL,
    weight        REAL DEFAULT 1.0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    source        TEXT,
    is_archived   INTEGER DEFAULT 0,
    superseded_by TEXT
);
```

### Poor Mode

`/poor` 命令切换，token 紧张时使用：
- 跳过 extractor，不提取记忆
- 跳过 dream 自动触发
- 跳过 distill pipeline（归档仍执行）
- 连续 3 次响应 output tokens > 2000 自动触发（TokenGuard）

---

## Dream 层

### 三道门控

| 门 | 条件 |
|----|------|
| 门1 数量门 | 未整理记忆条数 ≥ 20 |
| 门2 时间门 | 距上次 dream ≥ 24h 且历史会话数 ≥ 5 |
| 门3 锁门 | PID 锁不存在 / 持有者已死 / mtime 超过 1 小时 |

### 4 阶段整理

| 阶段 | 名称 | 操作 |
|------|------|------|
| Phase 1 | Orient 定位 | 查看现有条目，了解全貌 |
| Phase 2 | Gather 采集 | 过时记忆 → 新增条目 → 隐含信息 |
| Phase 3 | Merge 合并 | 合并新信号，软删除被推翻事实 |
| Phase 4 | Prune 修剪 | 低权重+高龄条目归档，每类控制数量 |

断点续传：`.dream-lock` 存储当前 Phase，崩溃重启后从断点继续。

---

## Distill 层（sql2）

离线蒸馏数据库 `~/.aic/distill.db`，与实时记忆库（sql1）完全分离。

### 核心功能

- **对话归档**：每次退出自动保存当前 session
- **质量筛选**：DeepSeek 对历史对话打分，高质量进 dataset pool
- **用户画像**：提取语言风格、决策模式、行为习惯
- **Skill 文档**：生成 `~/.aic/skills/*.md`，人工审阅后 `/skill confirm` 入库
- **Context Priming**：`/prime <query>` 检索历史经验注入当前上下文

### 三道门控

| 门 | 条件 |
|----|------|
| 门1 | 未分析 session 窗口 ≥ 5 |
| 门2 | 距上次 distill ≥ 24 小时 |
| 门3 | 未分析对话总数 ≥ 10 |

### 知识老化机制

- `tech_stack` 字段记录技术栈，迁移时批量标记旧对话为 deprecated
- 新 masterpiece 出现时，同标签旧对话 `quality_score × 0.5`
- `/supersede <old_id> <new_id>` 手动建立替代关系

---

## 安全边界

| 限制 | 数值 | 位置 |
|------|------|------|
| 单文件最大注入 | 500 KB | `session.py` |
| 总上下文最大 | 400 KB | `session.py` |
| 目录注入最大文件数 | 20 个 | `repl.py` |
| TUI 渲染最大行数 | 1000 行 | `tui.py` |
| TokenGuard 阈值 | 2000 output tokens | `session.py` |
| Auto Poor Mode | 连续 3 次超限 | `session.py` |

---

## Slash 命令

| 命令 | 功能 | 阶段 |
|------|------|------|
| `/add <file\|dir>` | 注入文件或目录（最多 20 文件 / 400KB） | 一 |
| `/files` | 查看已加载文件 | 一 |
| `/clear` | 清空对话历史 | 一 |
| `/reset` | 清空历史 + 上下文文件 | 一 |
| `/model [name]` | 显示或热切换 provider/model（历史保留） | 一/五 |
| `/status` | provider、model、session_id、poor_mode、token_guard、cost | 一/五 |
| `/tree` | 显示当前目录树 | 一 |
| `/poor` | 开关 Poor Mode | 二 |
| `/memory [type]` | 查看/搜索记忆 | 二 |
| `/forget <id>` | 软删除记忆条目 | 二 |
| `/log` | 查看今日 KAIROS 日志 | 二 |
| `/dream` | 手动触发 Dream 整理 | 三 |
| `/mcp` | 查看已注册 MCP server 和工具列表 | 四 |
| `/cost` | token 用量和费用估算 | 五 |
| `/search <query>` | 手动触发 Web Search，结果注入上下文 | 五 |
| `/index <dir>` | 索引目录建立代码检索器 | 五 |
| `/find <query>` | 检索相关代码片段注入上下文 | 五 |
| `/diag` | 诊断：线程数、内存、上下文大小、未处理记忆数 | 五 |
| `/skill` | 查看/确认/拒绝 skill 文档 | 六 |
| `/distill` | 手动触发 distill pipeline / 查看门控状态 | 六 |
| `/prime [query]` | 检索历史经验注入当前上下文 | 六 |
| `/supersede <old> <new>` | 手动标记旧对话被新对话替代 | 六 |
| `/help` | 显示帮助 | 一 |
| `/exit` | 退出 | 一 |

---

## 开发路线图

### 阶段一 ✅ 已完成

- [x] 目录骨架
- [x] config.py
- [x] BaseProvider + OpenAICompatProvider + ClaudeProvider
- [x] session.py（含双层 CONTEXT 注入）
- [x] tui.py（左对话右 diff 分栏）
- [x] repl.py 主循环 + slash 基础命令

### 阶段二 ✅ 已完成

- [x] `memory/types.py` + `memory/store.py`
- [x] `memory/extractor.py` — 每轮提取，Poor Mode 跳过
- [x] KAIROS 日志 + `/poor` `/memory` `/forget` `/log`

### 阶段三 ✅ 已完成

- [x] Dream 三道门控 + PID 锁 + 断点续传
- [x] Consolidator 4 阶段 + 受限子代理
- [x] `/dream` 命令

### 阶段四 ✅ 已完成

- [x] MCP loader / runner / registry
- [x] 沙箱临时会话，最多 10 轮工具调用
- [x] `/mcp` 命令

### 阶段五 ✅ 已完成

- [x] Web Search 内置（Brave API + DuckDuckGo 降级）
- [x] `/cost` token 统计 + 定价模糊匹配
- [x] TokenGuard 自动 Poor Mode
- [x] `/model` 热切换（历史保留）
- [x] `/index` + `/find` 本地代码检索
- [x] `/diag` 诊断命令
- [x] 安全边界（文件大小限制、TUI 截断、HTTP 400 不重试）
- [x] 统一错误格式（errors.py）

### 阶段六（规划中）

- [ ] Distill 层（sql2）：对话归档、用户画像、Skill 文档、Context Priming
- [ ] Event Bus：shell hook + Clash 监控 + inotify 文件监听
- [ ] 多模型 `@` 调用语法
- [ ] 子 Session 架构（DeepSeek 整理层）
- [ ] Discord 集成

### 阶段七（远期）

- 自举模式：修改 aic 自身时自动加载源码
- Langfuse 监控：token 消耗和任务链路追踪
- Step 模型深度集成：主理人角色

---

## 快速开始

```bash
git clone git@github.com:20070316lbw-netizen/AI-C.git
cd AI-C
uv venv .venv
source .venv/bin/activate
uv pip install -e .

# 配置
cp config.example.toml ~/.config/aic/config.toml
# 编辑填入 API key

# 启动
aic

# 在项目目录下启动（自动加载项目上下文）
cd ~/your-project
aic
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
- 所有 LLM 调用通过 `llm.complete()` 或 `provider.stream()`，不直接调 SDK

---

*— 内部使用，不开源 —*
