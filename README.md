# aic — AI Coding Assistant

> 个人使用的命令行 AI 编程助手，直连主流 LLM API，无服务器依赖，无 Electron。

---

## 特性

- 直连 API（Claude / DeepSeek / Gemini / GPT），不依赖任何第三方 CLI 框架
- 分栏 TUI：左侧对话，右侧文件变更 diff（`rich` 实现）
- Memory 体系：SQLite 持久化，四类记忆分类
- Dream 整理：三道门控自动触发，4 阶段 prompt 整理记忆
- Agent prompt 文件驱动，存放于 `.aic/agents/`，不硬编码
- Poor Mode：token 紧张时关闭记忆提取

## 项目状态

🚧 **阶段一开发中** — Provider 抽象 + 基础 REPL

## 架构层级

```
L0 main.py          argparse 入口
L1 repl / session   对话循环、slash 命令、消息管理
L2 providers        流式接口抽象，多 provider 路由
L3 memory           SQLite 存储，记忆提取与分类
L4 dream            三道门控，4 阶段自动整理
L5 mcp              工具调用（后期）
L6 持久化           ~/.aic/memory.db + config.toml
```

## 快速开始

```bash
# 安装（uv 推荐）
uv pip install -e .

# 配置
cp config.example.toml ~/.config/aic/config.toml
# 编辑填入 API key

# 启动
aic
```

## 配置示例

见 `config.example.toml`

## 开发路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| 阶段一 | Provider 抽象 + REPL + TUI 分栏 | 🚧 进行中 |
| 阶段二 | Memory 全套 + KAIROS 日志 + Poor Mode | ⏳ 待开始 |
| 阶段三 | Dream 三道门 + 受限子代理 | ⏳ 待开始 |
| 阶段四 | MCP loader/runner | ⏳ 待开始 |
| 阶段五 | Web Search + /cost 统计 | ⏳ 待开始 |

## 依赖

- `httpx` — HTTP 客户端（流式支持）
- `rich` — TUI 渲染
- `sqlite3` — 标准库，memory 层
- Python 3.12+

---

*内部使用，不开源。*
