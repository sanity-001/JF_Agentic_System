# Q4: QueryContext 设计模式理解

## 问题

"QueryContext 设计模式：用 dataclass 封装上下文，避免函数参数膨胀。一次构建，全程使用。" 如何理解？

## 解答

### 没有 dataclass 时的灾难

`run_query()` 需要 14 个参数，每次调用都要传：

```python
async def run_query(
    api_client, tool_registry, permission_checker,  # 3
    cwd, model, system_prompt, max_tokens,          # 4
    effort, context_window_tokens,                  # 2
    auto_compact_threshold_tokens,                  # 1
    permission_prompt, ask_user_prompt,             # 2
    max_turns, hook_executor, tool_metadata,        # 3
    messages,                                       # 1
):  # 共计 14 个参数，修一个全链路要改
```

### 用 dataclass 之后

```python
@dataclass
class QueryContext:
    api_client: SupportsStreamingMessages
    tool_registry: ToolRegistry
    # ... 其余 10+ 个字段，各有默认值

# 函数签名从 14 → 2
async def run_query(
    context: QueryContext,
    messages: list[ConversationMessage],
):
```

### 三个关键优势

1. **一次构建**：`build_runtime()` 中组装好，全链路传递同一个对象
2. **避免参数膨胀**：传给任何函数只需 `context` 一个参数
3. **全程使用**：同一对象在引擎层、工具层、命令层之间传递，状态一致

### 为什么是 dataclass 而不是 dict？

```python
# ❌ dict：拼写错误不报错，IDE 没有自动补全
context = {"apic_lient": client}  # typo 悄悄通过
# → 运行时 KeyError

# ✅ dataclass：拼写错误当场报错
context = QueryContext(apic_lient=client)  # IDE 红线
```

dataclass 自动生成 `__init__`、`__repr__`、`__eq__`，省去大量样板代码。
