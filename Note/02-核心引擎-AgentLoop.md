# Agent Loop 核心引擎 —— 深度源码解析

> **关键文件**: `engine/query.py`、`engine/query_engine.py`、`engine/stream_events.py`、`engine/cost_tracker.py`  
> **核心概念**: 模型是大脑，Harness 是身体。引擎是连接两者的神经系统。

---

## 1. 什么是 Agent Loop？

Agent Loop 是整个 OpenHarness 系统的**心脏**。它实现了一个由模型自主决策、工具执行、观察结果、继续推理的循环：

```
用户输入 "帮我修 main.py 的 bug"
  │
  ▼
┌──────────────────────────────────────────────────┐
│  while True:                                     │
│    ① response = api.stream(messages, tools)      │  ← 模型推理
│    ② if stop_reason != "tool_use": break         │  ← 模型说"完成了"
│    ③ for each tool_call:                         │
│         permission → hook → execute → hook       │  ← 工具执行
│    ④ messages.append(tool_results)               │  ← 追加到对话
│    ⑤ 循环继续 —— 模型看到结果后决定下一步          │
└──────────────────────────────────────────────────┘
```

**关键洞察**：
- 模型决定 **做什么**（what）—— 读哪个文件、搜什么关键字
- Harness 处理 **怎么做**（how）—— 安全检查、钩子触发、实际执行

---

## 2. 引擎模块文件结构

```
engine/
├── query_engine.py    # QueryEngine 类：对话的有状态管理者
├── query.py           # run_query() 函数：Agent Loop 的具体实现
├── messages.py        # 对话消息模型（ConversationMessage 等）
├── stream_events.py   # 流式事件定义（所有事件类型）
└── cost_tracker.py    # Token 成本追踪
```

---

## 3. 核心类：QueryEngine

`QueryEngine`（`query_engine.py` 第 21 行）是对话的**有状态管理者**：

```python
class QueryEngine:
    def __init__(
        self,
        *,
        api_client: SupportsStreamingMessages,      # LLM API 客户端
        tool_registry: ToolRegistry,                 # 工具注册表
        permission_checker: PermissionChecker,       # 权限检查器
        cwd: str | Path,                             # 当前工作目录
        model: str,                                  # 模型标识符
        system_prompt: str,                          # 系统提示词
        max_tokens: int = 4096,                      # 最大输出 token 数
        context_window_tokens: int | None = None,     # 上下文窗口大小
        auto_compact_threshold_tokens: int | None,    # 自动压缩触发阈值
        max_turns: int | None = 8,                   # 每轮最大工具调用次数
        hook_executor: HookExecutor | None = None,    # 生命周期钩子
        tool_metadata: dict | None = None,            # 工具间共享的元数据
        settings: Settings | None = None,             # 全局设置
    ):
        self._api_client = api_client
        self._tool_registry = tool_registry
        self._permission_checker = permission_checker
        self._messages: list[ConversationMessage] = []  # 对话历史
        self._cost_tracker = CostTracker()               # 成本追踪
```

### 3.1 运行时动态配置

QueryEngine 支持在会话中**热切换**核心组件，无需重启：

```python
engine.set_system_prompt(new_prompt)     # /system 命令 → 换提示词
engine.set_model("claude-opus-4-6")     # /model 命令 → 换模型
engine.set_effort("high")               # /effort 命令 → 调推理深度
engine.set_max_turns(10)                # /turns 命令 → 调轮次上限
engine.set_api_client(new_client)       # /provider 命令 → 热切换后端
engine.set_permission_checker(checker)   # /permissions 命令 → 换权限
```

**设计意图**：所有 `/` 斜杠命令最终都会调用这些 setter 方法，动态改变引擎行为而不丢失对话历史。

---

## 4. 核心函数：run_query() —— Agent Loop 的完整实现

`run_query()`（`query.py` 第 633 行）是整个系统最关键的异步生成器。

### 4.1 函数签名

```python
async def run_query(
    context: QueryContext,                             # 不可变的运行时配置
    messages: list[ConversationMessage],               # 对话历史（会被原地修改）
) -> AsyncIterator[tuple[StreamEvent, UsageSnapshot | None]]:
    """返回事件迭代器 —— 引擎逐步产出事件，UI 实时消费"""
```

返回 `AsyncIterator` 而非一次性结果：引擎每产生一个事件就立即 `yield` 给 UI 层，实现**流式架构**。

### 4.2 QueryContext —— 不可变运行时配置

```python
@dataclass
class QueryContext:
    api_client: SupportsStreamingMessages
    tool_registry: ToolRegistry
    permission_checker: PermissionChecker
    system_prompt: str
    model: str
    max_tokens: int
    max_turns: int | None = 200       # 默认 200 次工具调用/轮
    effort: str | None = None
    cwd: Path
    hook_executor: HookExecutor | None = None
    permission_prompt: PermissionPrompt | None = None  # 交互式确认回调
    ask_user_prompt: AskUserPrompt | None = None       # 交互式询问回调
    tool_metadata: dict[str, object] | None = None     # 跨 turn 状态共享
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None
```

**设计模式**：用 `dataclass` 封装上下文，避免函数参数膨胀。一次构建，全程使用。

### 4.3 主循环逐行解析

```python
turn_count = 0
while context.max_turns is None or turn_count < context.max_turns:
    turn_count += 1

    # ═══════════════════════════════════════════════════════════
    # Step 1: Token 上限自适应
    # ═══════════════════════════════════════════════════════════
    # 防止用户设置了过大的 max_tokens 导致 API 调用失败
    # 某些 provider（如 OpenAI 兼容后端）会拒绝超大的 max_tokens
    effective_max_tokens = _bounded_completion_tokens(
        context.max_tokens, context.context_window_tokens
    )
    # _bounded_completion_tokens: 上限 128000，取 min(max_tokens, 128000)

    # ═══════════════════════════════════════════════════════════
    # Step 2: 自动压缩检查 (Auto-Compaction)
    # ═══════════════════════════════════════════════════════════
    # 如果对话太长超出上下文窗口，先压缩再调用模型
    async for event, usage in _stream_compaction(trigger="auto"):
        yield event, usage

    # ═══════════════════════════════════════════════════════════
    # Step 3: 图像预处理
    # ═══════════════════════════════════════════════════════════
    # 对非视觉模型，将消息中的图片转换为文本描述
    async for event in _preprocess_images_in_messages(messages, context):
        yield event, None

    # ═══════════════════════════════════════════════════════════
    # Step 4: 调用模型（流式）
    # ═══════════════════════════════════════════════════════════
    try:
        async for event in context.api_client.stream_message(
            ApiMessageRequest(
                model=context.model,
                messages=messages,               # 完整对话历史
                system_prompt=context.system_prompt,
                max_tokens=effective_max_tokens,
                tools=context.tool_registry.to_api_schema(),  # 所有工具定义
                effort=context.effort,
            )
        ):
            if isinstance(event, ApiTextDeltaEvent):
                # 增量文本 → 立即推送到 UI 实现打字机效果
                yield AssistantTextDelta(text=event.text), None

            elif isinstance(event, ApiRetryEvent):
                # 重试事件 → UI 显示状态
                yield StatusEvent(
                    message=f"Retrying in {event.delay_seconds:.1f}s "
                            f"(attempt {event.attempt + 1} of {event.max_attempts})"
                ), None

            elif isinstance(event, ApiMessageCompleteEvent):
                final_message = event.message   # 完整的模型响应
                usage = event.usage             # Token 消耗统计

    except Exception as exc:
        # ═══════════════════════════════════════════════════════
        # Step 4a: 错误恢复 —— Token 限制自适应
        # ═══════════════════════════════════════════════════════
        # 某些 provider 严格限制 max_tokens，动态降低后重试
        if _is_completion_token_limit_error(exc):
            effective_max_tokens = _extract_completion_token_limit(exc)
            turn_count -= 1       # 不计入 turn 计数
            continue              # 回到主循环顶部

        # ═══════════════════════════════════════════════════════
        # Step 4b: 错误恢复 —— 上下文过长强制压缩
        # ═══════════════════════════════════════════════════════
        if not reactive_compact_attempted and _is_prompt_too_long_error(exc):
            reactive_compact_attempted = True
            yield StatusEvent(message="Compacting conversation memory..."), None
            async for event, _ in _stream_compaction(trigger="reactive", force=True):
                yield event, _
            continue              # 压缩后重试

        # ═══════════════════════════════════════════════════════
        # Step 4c: 不可恢复的错误
        # ═══════════════════════════════════════════════════════
        if "connect" in error_msg or "timeout" in error_msg:
            yield ErrorEvent(message=f"Network error: {error_msg}"), None
        else:
            yield ErrorEvent(message=f"API error: {error_msg}"), None
        return  # ← 终止循环

    # ═══════════════════════════════════════════════════════════
    # Step 5: 检查是否需要工具调用
    # ═══════════════════════════════════════════════════════════
    if not _has_tool_use(final_message):
        # 模型没有请求工具 → 对话结束
        yield AssistantTurnComplete(
            turn_count=turn_count,
            message=final_message,
            messages=self._messages,
        ), usage
        return

    # ═══════════════════════════════════════════════════════════
    # Step 6: 工具执行流水线
    # ═══════════════════════════════════════════════════════════
    tool_results = []
    for tool_call in _tool_calls_from_message(final_message):
        # 6a: 查找工具
        tool = context.tool_registry.get(tool_call.name)
        if tool is None:
            tool_results.append(ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Unknown tool: {tool_call.name}",
                is_error=True,
            ))
            continue

        # 6b: 权限检查
        decision = context.permission_checker.evaluate(
            tool_name=tool_call.name,
            is_read_only=tool.is_read_only(arguments),
            file_path=arguments.get("file_path"),
            command=arguments.get("command"),
        )
        if not decision.allowed and not decision.requires_confirmation:
            tool_results.append(ToolResultBlock(error="Permission denied"))
            continue

        if decision.requires_confirmation:
            # 需要用户确认 → 通过 permission_prompt 回调获取用户输入
            approved = await context.permission_prompt(tool_call.name, str(arguments))
            if not approved:
                tool_results.append(ToolResultBlock(error="User denied"))
                continue

        # 6c: 发送执行开始事件
        yield ToolExecutionStarted(tool_name=tool_call.name), None

        # 6d: PreToolUse 钩子
        if context.hook_executor:
            await context.hook_executor.run_hooks(HookEvent.PRE_TOOL_USE, {...})

        # 6e: 实际执行
        try:
            result = await tool.execute(arguments, ToolExecutionContext(...))
        except Exception as e:
            result = ToolResult(output=str(e), is_error=True)

        # 6f: PostToolUse 钩子
        if context.hook_executor:
            await context.hook_executor.run_hooks(HookEvent.POST_TOOL_USE, {...})

        # 6g: 发送执行完成事件
        tool_results.append(result)
        yield ToolExecutionCompleted(tool_name=tool_call.name), None

    # ═══════════════════════════════════════════════════════════
    # Step 7: 追加结果 → 循环继续
    # ═══════════════════════════════════════════════════════════
    messages.append(
        ConversationMessage(role="user", content=tool_results)
    )
    # while 循环回到 Step 1 — 模型会看到工具执行结果并继续推理
```

---

## 5. 上下文压缩 (Auto-Compaction)

长时间运行的 Agent 会话中，对话消息不断增长可能超出模型上下文窗口。OpenHarness 的应对策略：

### 5.1 两级压缩

```
Level 1: Microcompact（微型压缩）
  ─→ 清除旧的工具输出内容，保留工具调用结构
  ─→ 速度快，不需要调用 LLM

Level 2: Full Compaction（完整压缩）  
  ─→ 用 LLM 总结较早的消息，替换原始对话
  ─→ 质量高，但需要额外一次 API 调用
```

### 5.2 触发机制

```python
# 主动触发：每轮开始时检查
async for event in _stream_compaction(trigger="auto"):
    yield event, usage

# 被动触发：收到 "prompt too long" 错误时
if _is_prompt_too_long_error(exc):
    async for event in _stream_compaction(trigger="reactive", force=True):
        yield event, usage
```

### 5.3 "Prompt Too Long" 检测

引擎能识别 **15+ 种不同** 的错误消息格式：

```python
def _is_prompt_too_long_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(needle in text for needle in (
        "prompt too long",       "context_length_exceeded",
        "context length",        "maximum context",
        "context window",        "input tokens exceed",
        "messages resulted in",  "reduce the length of the messages",
        "configured limit",      "too many tokens",
        "too large for the model","maximum context length",
        "exceed_context",        "exceeds the available context size",
    ))
```

---

## 6. 流式事件体系

引擎通过 `StreamEvent` 类型体系与 UI 层通信：

| 事件类型 | 产生时机 | UI 反应 |
|---------|---------|---------|
| `AssistantTextDelta` | 模型每输出一段文本 | 打字机效果流式显示 |
| `ToolExecutionStarted` | 工具开始执行 | 显示 spinner + 工具名 |
| `ToolExecutionCompleted` | 工具执行完毕 | 隐藏 spinner，显示结果 |
| `StatusEvent` | 重试/压缩/状态变更 | 显示状态提示 |
| `ErrorEvent` | API 错误 / 网络错误 | 显示红色错误 |
| `CompactProgressEvent` | 上下文压缩进度 | 显示压缩进度条 |
| `AssistantTurnComplete` | 本轮 Agent 循环结束 | 显示完整响应 + 成本 |
| `MaxTurnsExceeded` | 超出 max_turns 限制 | 显示警告并停止 |

### 事件驱动架构图

```
                    QueryEngine
                        │
         run_query()    │
         ┌──────────────┼──────────────┐
         │  AsyncIterator<StreamEvent>  │
         │    yield 事件 →  →  →  →  → │→ UI 层消费
         │                              │
         │  model.stream_message()      │
         │    yield ApiTextDeltaEvent   │→ AssistantTextDelta → 屏幕打字
         │    yield ApiRetryEvent       │→ StatusEvent → 状态栏
         │    yield ApiCompleteEvent    │→ 触发工具执行
         │                              │
         │  tool.execute()              │
         │    → ToolExecutionStarted   │→ 动画开始
         │    → ToolExecutionCompleted │→ 显示结果
         │                              │
         │  yield AssistantTurnComplete│→ 完成指示
         └──────────────────────────────┘
```

---

## 7. 成本追踪 (CostTracker)

每次 API 调用后自动记录：

```python
# engine/cost_tracker.py
class CostTracker:
    def record(self, usage: UsageSnapshot):
        self._total_input_tokens += usage.input_tokens
        self._total_output_tokens += usage.output_tokens
        self._total_cache_read_tokens += usage.cache_read_input_tokens
        self._total_cache_write_tokens += usage.cache_creation_input_tokens
        self._total_cost += usage.cost   # 美元金额

    @property
    def total(self):
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "cache_read_tokens": self._total_cache_read_tokens,
            "cache_write_tokens": self._total_cache_write_tokens,
            "cost_usd": round(self._total_cost, 6),
        }
```

用户可通过 `/cost` 命令随时查询（由 commands 系统实现）。

---

## 8. Agent Loop 完整时序图

```
时间 ──────────────────────────────────────────────────────────────→

用户    │ 输入 prompt
        │──────▶
引擎    │       run_query(context, messages)
        │       │
        │       ├─ [auto-compact check]
        │       │
        │       ├─ api.stream_message() ──────────────────────┐
        │       │    ApiTextDelta("I'll") → AssistantTextDelta │→ UI: "I'll"
        │       │    ApiTextDelta(" read") → AssistantTextDelta│→ UI: " read"
        │       │    ApiTextDelta(" main.py") → ...            │→ UI: " main.py"
        │       │    ApiCompleteEvent(tool_use: Read)          │
        │       │                                              │
        │       ├─ ToolExecutionStarted("Read") ───────────────│→ UI: 🔧 Reading...
        │       ├─ PermissionChecker.evaluate()                │
        │       ├─ PreToolUse hooks                            │
        │       ├─ Read.execute() → file content               │
        │       ├─ PostToolUse hooks                           │
        │       ├─ ToolExecutionCompleted("Read") ─────────────│→ UI: ✅ Done
        │       │                                              │
        │       ├─ messages.append(tool_result)                │
        │       │                                              │
        │       ├─ api.stream_message() (continued...) ────────┤
        │       │    ApiTextDelta("The bug is") → ...          │→ UI: "The bug is"
        │       │    ApiTextDelta(" on line 42") → ...         │→ UI: " on line 42"
        │       │    ApiCompleteEvent(tool_use: Edit)          │
        │       │                                              │
        │       ├─ ToolExecutionStarted("Edit") ───────────────│→ UI: 🔧 Editing...
        │       ├─ ... 权限检查 + 钩子 + 执行 ...               │
        │       ├─ ToolExecutionCompleted("Edit") ─────────────│→ UI: ✅ Done
        │       │                                              │
        │       ├─ api.stream_message() (continued...) ────────┤
        │       │    ApiTextDelta("Fixed!") → ...              │→ UI: "Fixed!"
        │       │    ApiCompleteEvent(no tool_use)             │← stop_reason≠tool_use
        │       │                                              │
        │       └─ AssistantTurnComplete ──────────────────────│→ UI: ✓ 完成
        │                                                      
UI      │                                                     显示最终回复
```

---

## 9. 关键设计决策

| 决策 | 原因 |
|------|------|
| **AsyncIterator 而非一次性返回** | 流式事件让 UI 实时响应，用户不用等待整个 Agent Loop 结束 |
| **原地修改 messages 列表** | 避免大量内存拷贝，50+ 轮对话可能包含数万字 |
| **工具元数据 (tool_metadata)** | 作为跨 turn 的状态通道，如"已读文件列表"在多次工具调用间传递 |
| **综合错误恢复** | 自动处理 token 限制、上下文过长，对用户透明 |
| **200 次默认 max_turns** | 足够完成复杂任务，同时防止失控循环导致天价账单 |

---

> 下一篇：`03-工具系统-ToolSystem.md` — 43+ 工具的设计与实现
