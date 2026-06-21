# OpenHarness 整体架构总览

> **项目**: OpenHarness v0.1.9 — 开源 AI Agent CLI 编程助手  
> **语言**: Python >= 3.10  
> **CLI 框架**: Typer (基于 Click)  
> **构建系统**: Hatchling + uv  
> **核心概念**: "The model is the agent. The code is the harness."

---

## 1. 什么是 Agent Harness？

在 AI Agent 系统中，**大模型（LLM）只提供"智能"**，而 **Harness（挽具/马具）提供"手脚、眼睛、记忆、安全边界"**。形象地说：

- 🧠 **模型** = 大脑（决策、推理）
- 🔧 **Harness** = 身体（执行工具、读写文件、网络访问、权限控制）

Harness 公式：

```
Harness = Tools（工具） + Knowledge（知识/Skills） + Observation（观察） + Action（行动） + Permissions（权限）
```

所以这个项目的本质是：**用 Python 构建一个完整的 Agent 基础设施，把 LLM 包起来，让它能在本地真正干活——读代码、写文件、执行命令、管理任务、协调多 Agent 协作。**

---

## 2. 项目顶层目录结构

```
OpenHarness/
├── src/openharness/          # 🔑 核心代码（全部 Python）
│   ├── cli.py                #   CLI 入口——所有参数定义、子命令、启动逻辑
│   ├── __main__.py            #   `python -m openharness` 入口
│   ├── engine/                # 🧠 Agent Loop 引擎——核心循环
│   │   ├── query_engine.py    #    查询引擎：管理对话历史 + 工具感知循环
│   │   ├── query.py           #    单次查询编排
│   │   ├── messages.py        #    对话消息模型
│   │   ├── stream_events.py   #    流式事件定义
│   │   └── cost_tracker.py    #    Token 成本追踪
│   ├── tools/                 # 🔧 43+ 个工具
│   │   ├── base.py            #    工具基类 + ToolRegistry
│   │   ├── bash_tool.py       #    Shell 执行
│   │   ├── file_read_tool.py  #    文件读取
│   │   ├── file_write_tool.py #    文件写入
│   │   ├── file_edit_tool.py  #    精确字符串替换
│   │   ├── glob_tool.py       #    文件模式匹配
│   │   ├── grep_tool.py       #    正则内容搜索
│   │   ├── web_fetch_tool.py  #    URL 抓取
│   │   ├── web_search_tool.py #    网页搜索
│   │   ├── agent_tool.py      #    子 Agent 调度
│   │   ├── task_*.py          #    任务管理系列
│   │   ├── team_*.py          #    团队管理
│   │   ├── cron_*.py          #    定时任务系列
│   │   └── ...                #    还有 30+ 个工具
│   ├── permissions/           # 🛡️ 权限系统
│   │   ├── checker.py         #    权限检查器
│   │   └── modes.py           #    权限模式（default/plan/full_auto）
│   ├── hooks/                 # ⚡ 生命周期钩子
│   │   ├── PreToolUse         #    工具执行前
│   │   └── PostToolUse        #    工具执行后
│   ├── commands/              # 💬 54 个斜杠命令
│   │   └── registry.py        #    命令注册表
│   ├── skills/                # 📚 技能系统（按需加载 .md 知识）
│   │   └── loader.py          #    技能加载器
│   ├── plugins/               # 🔌 插件系统
│   ├── mcp/                   # 🌐 MCP 协议客户端
│   ├── memory/                # 🧠 持久化记忆（MEMORY.md）
│   ├── prompts/               # 📝 系统提示词组装
│   ├── config/                # ⚙️ 多层配置
│   │   ├── settings.py        #    Settings 模型（Pydantic）
│   │   └── paths.py           #    路径管理
│   ├── tasks/                 # 📋 后台任务生命周期
│   ├── coordinator/           # 🤝 多 Agent 协调
│   ├── swarm/                 # 🐝 多 Agent 协作团队
│   ├── sandbox/               # 📦 沙箱安全
│   ├── api/                   # 🌐 API 客户端
│   │   ├── client.py          #    流式 API 接口
│   │   └── provider.py        #    Provider 检测
│   ├── auth/                  # 🔐 认证系统
│   │   ├── manager.py         #    认证管理器
│   │   ├── flows.py           #    登录流程
│   │   └── storage.py         #    凭证存储
│   ├── ui/                    # 🖥️ 终端 UI
│   │   ├── app.py             #    UI 入口（run_repl / run_print_mode）
│   │   ├── input.py           #    用户输入处理
│   │   ├── backend_host.py    #    React TUI 后端
│   │   ├── react_launcher.py  #    React/Ink TUI 启动器
│   │   └── runtime.py         #    运行时构建
│   ├── services/              # 🕐 后台服务
│   │   ├── cron.py            #    Cron 任务管理
│   │   ├── cron_scheduler.py  #    Cron 调度守护进程
│   │   └── session_storage.py #    会话持久化
│   └── utils/                 # 🛠️ 工具函数
├── frontend/terminal/         # React/Ink 终端前端（TypeScript）
├── ohmo/                      # 🧑‍💼 个人 AI 助手应用（Feishu/Slack/Telegram/Discord）
├── tests/                     # 测试（114+ 单元测试）
├── autopilot-dashboard/       # Autopilot 看板（React）
├── docs/                      # 文档
├── pyproject.toml             # 项目配置
└── .venv/                     # 虚拟环境
```

---

## 3. 系统分层架构

```
┌──────────────────────────────────────────────────────┐
│                   用户交互层 (UI Layer)                  │
│  CLI (typer)  ·  React TUI (Ink)  ·  ohmo Gateway    │
│  oh setup / oh -p / oh --dry-run / ohmo gateway run  │
├──────────────────────────────────────────────────────┤
│                   编排层 (Orchestration)                │
│  QueryEngine  ·  PermissionChecker  ·  HookExecutor   │
│  Coordinator  ·  Swarm  ·  TaskManager               │
├──────────────────────────────────────────────────────┤
│                   能力层 (Capabilities)                 │
│  43+ Tools  ·  54+ Commands  ·  Skills  ·  Plugins   │
│  MCP Client  ·  Memory  ·  Cron Scheduler            │
├──────────────────────────────────────────────────────┤
│                   基础设施层 (Infrastructure)            │
│  Config/Settings  ·  Auth  ·  API Client  ·  Paths   │
│  File I/O  ·  Shell  ·  Web  ·  Sandbox              │
└──────────────────────────────────────────────────────┘
```

---

## 4. 启动流程概要

```
用户在终端输入 `oh`
  │
  ▼
cli.py: main() 回调被触发
  │
  ├─→ [subcommand 模式] 直接分派到 mcp/plugin/auth/provider/config/cron/autopilot 子命令
  │
  └─→ [默认模式] 没有子命令 → 走到 main() 函数体
        │
        ├─→ --dry-run → _build_dry_run_preview() → 打印预览 → 退出
        │
        ├─→ --continue / --resume → 加载历史会话 → run_repl()
        │
        ├─→ --print / -p → run_print_mode() 非交互单次问答
        │
        ├─→ --task-worker → run_task_worker() 后台 Agent worker
        │
        └─→ 默认 → run_repl() 启动 React/Ink 交互式 TUI
              │
              └─→ launch_react_tui()
                    │
                    └─→ backend_host 启动 → QueryEngine 创建
                          │
                          └─→ Agent Loop 开始运行
```

---

## 5. 核心设计模式

### 5.1 依赖注入与构建器模式

系统通过 `build_runtime()` 集中构建所有依赖：

```python
# cli.py 调用 → ui/app.py 调用 → ui/runtime.py
runtime = build_runtime(
    cwd, model, max_turns, base_url, system_prompt,
    api_key, api_format, permission_mode, ...
)
# 返回包含: QueryEngine, PermissionChecker, HookExecutor, ToolRegistry...
```

### 5.2 策略模式 —— Provider 系统

不同 LLM 后端（Anthropic / OpenAI / Copilot / Codex）都实现 `SupportsStreamingMessages` 接口，通过 Provider Profile 机制在运行时切换。

### 5.3 观察者模式 —— Hook 系统

`PreToolUse` / `PostToolUse` 钩子允许插件在工具执行前后插入逻辑，类似中间件。

### 5.4 命令模式 —— 斜杠命令系统

所有 `/help`、`/commit`、`/plan` 等斜杠命令都是注册到 CommandRegistry 的命令对象，支持插件扩展。

---

> 下一篇：`01-CLI入口与参数组织.md` — 详细解析 cli.py 的参数定义方式与执行流程
