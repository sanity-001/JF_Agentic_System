# Q1: Typer 三个关键参数的设置原因

## 问题

`cli.py` 中 Typer 实例创建时设置了三个参数：

```python
app = typer.Typer(
    name="openharness",
    add_completion=False,         # 为什么关闭？
    rich_markup_mode="rich",      # 为什么用 rich？
    invoke_without_command=True,  # 为什么允许无子命令？
)
```

## 解答

### 1. `invoke_without_command=True` — 让裸 `oh` 成为合法命令

Typer 默认行为是"必须有子命令"。只输入 `oh` 会报错要求你选一个命令。

但 OpenHarness 的核心场景就是无子命令直接启动：

```bash
oh          # 进入交互式 REPL ← 不需要子命令
oh -p "hi"  # 单次问答
oh --dry-run  # 安全预览
```

代码第 2369 行的逻辑：

```python
if ctx.invoked_subcommand is not None:
    return  # 有子命令 → Typer 分派
# 无子命令 → 走默认交互式会话
asyncio.run(run_repl(...))
```

### 2. `add_completion=False` — 避免跨平台补全安装问题

Shell 补全在以下场景容易失败：
- Windows 环境（补全机制和 Unix 完全不同）
- pip install 后不在 PATH
- 非交互环境（ohmo gateway、CI/CD）
- 安装方式多样（pip/uv/brew/install script）

与其生成半失效的补全脚本惹来 issue，不如关闭让有需要的用户手动配置。

### 3. `rich_markup_mode="rich"` — 帮助信息支持 Rich 终端标记

开启后支持 `rich_help_panel` 分组，效果就是 `oh --help` 看到的分组面板：

```
+- Options ----------+
+- Session ----------+
+- Model & Effort ---+
+- Output -----------+
+- Permissions ------+
+- System & Context -+
+- Advanced ---------+
```

每组分不同颜色和图标，层次感远强于纯文本。
