# CLI 入口与参数组织 —— 深度源码解析

> **文件**: `src/openharness/cli.py` (2552 行)  
> **框架**: Typer (基于 Click 的现代 CLI 框架)  
> **版本**: 0.1.9

---

## 1. Typer 基础概念

OpenHarness 使用 **Typer** 框架构建 CLI。理解 Typer 的几个核心概念：

### 1.1 Typer 实例 = 命令组

```python
# cli.py 第 751-760 行
app = typer.Typer(
    name="openharness",
    help="Oh my Harness! An AI-powered coding assistant.\n\n"
         "Starts an interactive session by default, use -p/--print for non-interactive output.",
    add_completion=False,        # 不生成 shell 自动补全
    rich_markup_mode="rich",     # 支持 Rich 终端标记
    invoke_without_command=True, # ⭐ 关键：不指定子命令时执行默认回调
)

# 子 Typer 实例 —— 每个对应一组子命令
mcp_app = typer.Typer(name="mcp", help="Manage MCP servers")
plugin_app = typer.Typer(name="plugin", help="Manage plugins")
auth_app = typer.Typer(name="auth", help="Manage authentication")
provider_app = typer.Typer(name="provider", help="Manage provider profiles")
config_app = typer.Typer(name="config", help="Show or update settings")
cron_app = typer.Typer(name="cron", help="Manage cron scheduler and jobs")
autopilot_app = typer.Typer(name="autopilot", help="Manage repo autopilot")
```

**原理**：每个 `typer.Typer()` 相当于一个"命令路由器"。`app` 是根路由器，通过 `app.add_typer()` 把子路由器挂载上去，形成命令树的嵌套结构。

### 1.2 子命令挂载

```python
# cli.py 第 775-781 行
app.add_typer(mcp_app)       # app 下挂 mcp
app.add_typer(plugin_app)     # app 下挂 plugin
app.add_typer(auth_app)       # app 下挂 auth
app.add_typer(provider_app)   # app 下挂 provider
app.add_typer(config_app)     # app 下挂 config
app.add_typer(cron_app)       # app 下挂 cron
app.add_typer(autopilot_app)  # app 下挂 autopilot
```

挂载后用户可以用 `oh mcp list`、`oh auth login`、`oh provider use xxx` 等形式调用。

---

## 2. 参数分类体系

OpenHarness 的 CLI 参数按功能面板（rich_help_panel）分为 **6 大类**：

```
oh [OPTIONS] COMMAND [ARGS]

+- Options -------------------------------------------------------------------+
| --version  -v        Show version and exit                                  |
+-----------------------------------------------------------------------------+
+- Session -------------------------------------------------------------------+
| --continue  -c       Continue the most recent conversation                  |
| --resume    -r TEXT  Resume a conversation by session ID, or open picker    |
| --name      -n TEXT  Set a display name for this session                    |
+-----------------------------------------------------------------------------+
+- Model & Effort ------------------------------------------------------------+
| --model      -m  TEXT   Model alias (e.g. 'sonnet', 'opus') or full model ID |
| --effort          TEXT   Effort level (low, medium, high, xhigh/max)         |
| --verbose               Override verbose mode setting from config            |
| --max-turns   INTEGER   Maximum number of agentic turns                      |
+-----------------------------------------------------------------------------+
+- Output --------------------------------------------------------------------+
| --print       -p  TEXT  Print response and exit. Pass your prompt as value  |
| --output-format   TEXT  Output format: text (default), json, or stream-json |
| --dry-run                Preview resolved runtime config without execution  |
+-----------------------------------------------------------------------------+
+- Permissions ---------------------------------------------------------------+
| --permission-mode              TEXT   default, plan, or full_auto            |
| --dangerously-skip-permissions        Bypass all permission checks           |
| --allowed-tools                TEXT   Comma or space-separated tool allowlist |
| --disallowed-tools             TEXT   Comma or space-separated tool denylist |
+-----------------------------------------------------------------------------+
+- System & Context ----------------------------------------------------------+
| --system-prompt         -s  TEXT   Override the default system prompt        |
| --append-system-prompt      TEXT   Append text to the default system prompt |
| --settings                  TEXT   Path to a JSON settings file              |
| --base-url                  TEXT   Anthropic-compatible API base URL         |
| --api-key            -k     TEXT   API key (overrides config and env)        |
| --bare                            Minimal mode: skip hooks, plugins, MCP    |
| --api-format                 TEXT   API format: anthropic, openai, or copilot|
| --theme                      TEXT   TUI theme                                |
+-----------------------------------------------------------------------------+
+- Advanced ------------------------------------------------------------------+
| --debug      -d        Enable debug logging                                 |
| --mcp-config    TEXT   Load MCP servers from JSON files or strings          |
+-----------------------------------------------------------------------------+
```

---

## 3. 参数定义的底层原理

### 3.1 Typer Option 装饰器语法

以 `--model` 参数为例：

```python
# cli.py 第 2214-2219 行
model: str | None = typer.Option(
    None,                              # default 值
    "--model",                         # 长选项名
    "-m",                              # 短选项名
    help="Model alias (e.g. 'sonnet', 'opus') or full model ID",
    rich_help_panel="Model & Effort",  # ⭐ 分组面板名
)
```

**原理**：`typer.Option()` 创建一个 Click `Option` 对象，`rich_help_panel` 参数将选项归入指定面板分组显示。Typer 利用 Python 类型注解（`str | None`）自动推断参数类型。

### 3.2 两种参数类型

| 类型 | Python 语法 | 示例 |
|------|------------|------|
| **Option**（选项） | `typer.Option(default, "--name")` | `--model sonnet` |
| **Argument**（位置参数） | `typer.Argument(default, help="...")` | `oh provider use <name>` |

```python
# Option 示例 - 可选，有名字
model: str | None = typer.Option(None, "--model", "-m", help="...")

# Argument 示例 - 必须按位置提供
name: str = typer.Argument(..., help="Provider profile name")
```

### 3.3 隐藏参数

有些参数对用户不可见，仅供内部使用：

```python
# cli.py 第 2349-2366 行
cwd: str = typer.Option(
    str(Path.cwd()),
    "--cwd",
    help="Working directory for the session",
    hidden=True,             # ⭐ 不出现在帮助信息中
),
backend_only: bool = typer.Option(
    False,
    "--backend-only",
    help="Run the structured backend host for the React terminal UI",
    hidden=True,
),
task_worker: bool = typer.Option(
    False,
    "--task-worker",
    help="Run the stdin-driven headless worker loop",
    hidden=True,
),
```

`--backend-only` 和 `--task-worker` 是内部实现通道——React TUI 前端通过 `--backend-only` 启动结构化后端，多 Agent 协调通过 `--task-worker` 启动 headless 工作进程。

---

## 4. 主回调函数 main() 的执行流程

`main()` 是整个 CLI 的核心调度器（第 2180-2551 行）：

```python
@app.callback(invoke_without_command=True)  # ⭐ 无子命令时调用此函数
def main(ctx: typer.Context, ... 参数列表 ...) -> None:
    """Start an interactive session or run a single prompt."""
```

### 4.1 执行决策树

```
main() 被调用
  │
  ├─ ctx.invoked_subcommand is not None?
  │    └─→ YES: return（让 Typer 分派给子命令处理）
  │
  ├─ --debug → 配置 logging.DEBUG
  │
  ├─ --dangerously-skip-permissions → 强制 permission_mode = "full_auto"
  │
  ├─ --theme → 写入 settings.json
  │
  ├─ --dry-run
  │    ├─ + --continue/--resume → 报错退出
  │    └─→ _build_dry_run_preview() → 输出预览 → return
  │
  ├─ --continue 或 --resume
  │    └─→ 加载历史会话 → asyncio.run(run_repl(...)) → return
  │
  ├─ --print / -p
  │    └─→ asyncio.run(run_print_mode(...)) → return
  │
  ├─ --task-worker
  │    └─→ asyncio.run(run_task_worker(...)) → return
  │
  └─ 默认（无特殊标记）
       └─→ asyncio.run(run_repl(prompt=None, ...))
            └─→ launch_react_tui() → React/Ink 交互式终端
```

**关键设计**：
- 通过 `if ctx.invoked_subcommand is not None: return` 把子命令分派交给 Typer 框架
- 使用 `asyncio.run()` 将异步函数转为同步执行——CLI 入口是同步的，但内部引擎全是异步的
- 每种运行模式都是 `return` 终止，避免继续执行后续逻辑

---

## 5. 子命令注册机制

### 5.1 装饰器注册语法

```python
# cli.py 第 786-801 行 — 简单子命令
@mcp_app.command("list")
def mcp_list() -> None:
    """List configured MCP servers."""
    from openharness.config import load_settings
    from openharness.mcp.config import load_mcp_server_configs
    ...

# cli.py 第 804-822 行 — 带参数的子命令
@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Server name"),
    config_json: str = typer.Argument(..., help="Server config as JSON string"),
) -> None:
    """Add an MCP server configuration."""
    ...
```

### 5.2 懒加载模式

注意每个子命令函数内部才 `import` 所需模块：

```python
def mcp_list() -> None:
    """List configured MCP servers."""
    from openharness.config import load_settings    # ← 延迟导入
    from openharness.mcp.config import load_mcp_server_configs
    from openharness.plugins import load_plugins
    ...
```

**原因**：
1. **冷启动优化**——不加载不需要的模块，`oh setup` 不会加载 engine/tools/ui
2. **避免循环导入**——CLI 模块被很多子模块依赖，如果 CLI 直接导入它们会形成循环
3. **命令行响应速度**——`oh --version` 只需几十毫秒，不需要加载整个框架

---

## 6. Dry-Run 机制深度解析

`--dry-run` 是 OpenHarness 的安全预览模式，**不调用模型、不执行工具**，只做静态配置解析。这是一个极好的"安全预览"设计模式。

### 6.1 `_build_dry_run_preview()` 解析（第 396-597 行）

```python
def _build_dry_run_preview(
    *,  # ⬅ 强制关键字参数
    prompt, cwd, model, max_turns, base_url,
    system_prompt, append_system_prompt, api_key,
    api_format, permission_mode, effort,
) -> dict[str, object]:
    # 1. 解析工作目录
    resolved_cwd = str(Path(cwd).expanduser().resolve())
    
    # 2. 加载配置并合并 CLI 覆盖
    settings = load_settings().merge_cli_overrides(
        model=model, max_turns=max_turns, base_url=base_url,
        system_prompt=system_prompt, api_key=api_key,
        api_format=api_format, permission_mode=permission_mode,
        effort=effort,
    )
    
    # 3. 检测 provider 和认证状态
    provider = detect_provider(settings)
    auth = auth_status(settings)
    profile_name, profile = settings.resolve_profile()
    
    # 4. 加载所有可发现资源（但不执行）
    plugins = load_plugins(settings, resolved_cwd)
    command_registry = create_default_command_registry(...)
    skill_registry = load_skill_registry(...)
    mcp_servers = load_mcp_server_configs(settings, plugins)
    tool_registry = create_default_tool_registry()
    
    # 5. 尝试验证 API 客户端解析（捕获异常）
    try:
        with redirect_stderr(StringIO()):
            _resolve_api_client_from_settings(settings)
    except SystemExit:
        client_validation = {"status": "error", ...}
    
    # 6. 构建系统提示词预览
    system_prompt_text = build_runtime_system_prompt(...)
    
    # 7. 智能推荐匹配的 skills/tools/commands
    recommendations = _recommend_preview_candidates(
        preview_prompt, skills=skills,
        tool_schemas=tool_schemas, command_entries=command_entries,
    )
    
    # 8. 分类输入类型
    if preview_prompt.startswith("/") and command_match:
        entrypoint = {"kind": "slash_command", ...}
    elif preview_prompt.startswith("/"):
        entrypoint = {"kind": "unknown_slash_command"}
    else:
        entrypoint = {"kind": "model_prompt", ...}
    
    # 9. 评估就绪状态
    preview["readiness"] = _evaluate_dry_run_readiness(...)
    
    return preview
```

### 6.2 就绪状态评估（第 333-393 行）

```python
def _evaluate_dry_run_readiness(*, prompt, entrypoint, validation):
    level = "ready"
    
    # 未知命令 → blocked
    if entrypoint.get("kind") == "unknown_slash_command":
        level = "blocked"
    
    # API 客户端解析失败 + 需要模型调用 → blocked
    if api_client["status"] == "error":
        if entrypoint["kind"] == "model_prompt":
            level = "blocked"
        else:
            level = "warning"
    
    # MCP 配置错误 → warning
    if mcp_errors > 0 and level != "blocked":
        level = "warning"
    
    # 缺少认证 → warning
    if auth_status.startswith("missing"):
        level = "warning"
    
    return {"level": level, "reasons": [...], "next_actions": [...]}
```

**三级状态**：
- 🟢 **ready**：配置正常，可以直接运行
- 🟡 **warning**：能解析但有隐患（如 MCP 配置错误、缺少认证）
- 🔴 **blocked**：无法运行（如未知命令、必须修复认证）

---

## 7. 完整命令树

```
oh                              ← 交互式会话（默认）
├── -p/--print "<prompt>"       ← 单次问答
├── --dry-run                   ← 安全预览
├── -c/--continue               ← 继续最近会话
├── -r/--resume [ID]            ← 恢复指定会话
├── -n/--name <name>            ← 会话命名
│
├── setup                       ← 统一配置向导
│
├── mcp                         ← MCP 服务器管理
│   ├── list                    ← 列出 MCP 服务器
│   ├── add <name> <json>      ← 添加 MCP 服务器
│   └── remove <name>           ← 移除 MCP 服务器
│
├── plugin                      ← 插件管理
│   ├── list                    ← 列出插件
│   ├── install <source>        ← 安装插件
│   └── uninstall <name>        ← 卸载插件
│
├── auth                        ← 认证管理
│   ├── login [provider]        ← 交互式登录
│   ├── status                  ← 查看认证状态
│   ├── logout [provider]       ← 清除认证
│   ├── switch <provider>       ← 切换认证源
│   ├── copilot-login           ← GitHub Copilot 登录
│   ├── codex-login             ← Codex CLI 绑定
│   ├── claude-login            ← Claude CLI 绑定
│   └── copilot-logout          ← 清除 Copilot 认证
│
├── provider                    ← Provider 管理
│   ├── list                    ← 列出 Profile
│   ├── use <name>              ← 激活 Profile
│   ├── add <name> ...          ← 创建 Profile
│   ├── edit <name> ...         ← 编辑 Profile
│   └── remove <name>           ← 删除 Profile
│
├── config                      ← 配置管理
│   ├── show                    ← 显示当前设置
│   └── set <key> <value>       ← 设置单个配置项
│
├── cron                        ← 定时任务管理
│   ├── start / stop / status   ← 调度器生命周期
│   ├── list                    ← 列出所有 cron 任务
│   ├── toggle <name> <on/off>  ← 启用/禁用任务
│   ├── history [name]          ← 执行历史
│   └── logs                    ← 调度器日志
│
└── autopilot                   ← 仓库自动驾驶
    ├── status                  ← 队列状态
    ├── list [status]           ← 列出卡片
    ├── add <source> <title>    ← 添加任务卡片
    ├── scan <target>           ← 扫描来源
    ├── run-next                ← 运行下一个任务
    ├── tick                    ← 扫描+运行
    ├── context                 ← 输出仓库上下文
    ├── journal                 ← 操作日志
    ├── install-cron            ← 安装默认定时任务
    └── export-dashboard        ← 导出静态看板
```

---

## 8. 交互式引导（oh setup）的巧妙设计

`oh setup` 使用了**逐步向导模式**，用 `questionary` 库提供美观的终端交互：

```python
# cli.py 第 1752-1807 行
@app.command("setup")
def setup_cmd(profile: str | None = None):
    manager = AuthManager()
    statuses = manager.get_profile_statuses()
    
    # Step 1: 选择 Workflow
    target = _select_setup_workflow(statuses, ...)
    
    # Step 2: 展开预设 Provider（Claude/Kimi/GLM...）
    target = _specialize_setup_target(manager, target)
    
    # Step 3: 如果没有凭据 → 引导输入 API Key
    if not info["configured"]:
        _ensure_profile_auth(manager, target)
    
    # Step 4: 选择或输入模型
    model_setting = _prompt_model_for_profile(profile_obj)
    
    # Step 5: 激活并保存
    manager.use_profile(target)
```

**设计亮点**：
- `_can_use_questionary()` 检测终端能力，优雅降级到 Typer 原生 prompt
- `_select_from_menu()` 提供 `questionary` 富交互 + 数字选择器两种模式
- `_ensure_preset_profile()` 确保预设配置始终存在，不会被用户误删

---

## 9. 配置优先级体系

```
最高优先级
  │  1. CLI 参数       (--model, --api-key, --base-url, ...)
  │  2. 环境变量       (ANTHROPIC_API_KEY, OPENHARNESS_MODEL, ...)
  │  3. Profile 配置    (~/.openharness/profiles.json)
  │  4. 配置文件        (~/.openharness/settings.json)
  │  5. 外部绑定       (Claude CLI / Codex CLI subscriptions)
  ▼  6. 默认值         (hardcoded defaults)
最低优先级
```

在代码中的体现：

```python
# cli.py → settings.merge_cli_overrides()
# settings.py 中通过 Pydantic Field(default=...) 定义默认值
# 环境变量在 load_settings() 中读取
# CLI 参数通过 merge_cli_overrides() 覆盖
```

---

> 下一篇：`02-核心引擎-AgentLoop.md` — Agent Loop 引擎的完整运行流程
