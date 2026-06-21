# Q8: tool_metadata 作为跨 Turn 状态通道

## 问题

"工具元数据 (tool_metadata) 作为跨 turn 的状态通道，如'已读文件列表'在多次工具调用间传递" 如何理解？

## 解答

### 核心问题

LLM 每次被调用时只能看到 `messages` 列表。它不知道引擎层面发生了什么——比如"这个文件我已经读过了"。

`tool_metadata` 是引擎在模型不知情的情况下维护的"便签本"。

### 实际流程

```
Turn 1:
  模型: tool_use { name: "Read", input: {file_path: "main.py"} }
  引擎: 执行 Read("main.py")
  引擎: tool_metadata["read_file_state"] = [
          {path: "main.py", span: "lines 1-200", preview: "import...", timestamp: ...}
        ]
  系统提示词注入: "Recently read files: main.py"

Turn 2:
  模型: (看到提示词中 main.py 已读过)
        "我已经知道 main.py 了，现在读 utils.py"
```

### 源码机制

```python
# query.py _remember_read_file()
def _remember_read_file(tool_metadata, *, path, offset, limit, output):
    bucket = tool_metadata.setdefault("read_file_state", [])  # 延迟创建
    # 去重（同文件保留最新记录）
    bucket[:] = [e for e in bucket if e.get("path") != path]
    bucket.append({
        "path": path,
        "span": f"lines {offset+1}-{offset+limit}",
        "preview": " | ".join(preview_lines)[:320],
        "timestamp": time.time(),
    })
    # 最多保留 6 个
    if len(bucket) > 6:
        del bucket[:-6]
```

### tool_metadata 的全部内容

```python
tool_metadata = {
    "read_file_state": [...],        # 已读文件（最多6个）
    "invoked_skills": [...],         # 已调用技能（最多8个）
    "task_focus_state": {            # 任务焦点
        "goal": "Fix the auth bug",
        "recent_goals": [...],
        "active_artifacts": [...],
        "verified_state": [...],
        "next_step": "...",
    },
    "verified_work": [...],          # 已验证工作（最多10条）
    "recent_work_log": [...],        # 最近日志（最多10条）
    "active_artifacts": [...],       # 活跃文件（最多8个）
    "permission_mode": "default",
    "vision_model_config": {...},    # 视觉模型配置
    # ... 等 11 种状态
}
```

### 与 messages 的本质区别

| | messages | tool_metadata |
|---|---|---|
| **谁维护** | 模型通过工具调用写 | 引擎自己写 |
| **模型能直接看吗** | 能（在对话历史中） | 不能（但注入到系统提示词） |
| **存什么** | 完整对话记录 | 结构化摘要/索引 |
| **大小** | 可能几万字 | 固定上限，每个字段最多几条 |

### 一句话

`tool_metadata` 是引擎给模型写的"小抄"——不是把整本书给模型看（messages），而是把"你读过哪些章节、修过哪些问题、现在进度如何"浓缩成几条摘要。
