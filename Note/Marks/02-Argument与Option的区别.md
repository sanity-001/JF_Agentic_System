# Q2: Typer 中 Option 与 Argument 的区别

## 问题

如何区分 CLI 中的 `typer.Option` 和 `typer.Argument`？

## 解答

### 核心区别表

| | Argument（位置参数） | Option（可选参数） |
|---|---|---|
| **怎么传** | 按位置，直接写值 | 按名字，`--xxx value` |
| **有无前缀** | 无 `--` | 有 `--` 或 `-` |
| **顺序** | 必须按定义顺序 | 顺序随意 |
| **典型用途** | 操作目标（名字、文件名） | 配置选项、开关 |

### 代码示例

```python
@provider_app.command("add")
def provider_add(
    name: str = typer.Argument(..., help="Provider profile name"),  # Argument
    label: str = typer.Option(..., "--label", help="Display label"), # Option
    model: str = typer.Option(..., "--model", help="Default model"), # Option
):
```

### 实际使用

```bash
# Argument 的典型场景：操作目标
oh provider use codex            # "codex" 是 Argument
oh cron toggle my-job true       # "my-job" 和 "true" 是 Argument

# Option 的典型场景：配置参数
oh --model sonnet                # --model 是 Option
oh -p "your prompt"              # -p 是 Option
oh --dry-run                     # 布尔 Option
```

### 设计原则

- Argument：操作的直接宾语，没它命令不完整 → 适合"必须指定"的核心对象
- Option：修饰语，删掉可用默认值 → 适合"可以省略"的配置项
