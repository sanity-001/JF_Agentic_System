# 权限与 Hook 系统 — 深度源码解析

> **关键文件**: `permissions/checker.py`、`permissions/modes.py`、`hooks/executor.py`  
> **核心概念**: 多层防护 + 可扩展生命周期钩子 = LLM 代理的安全边界

---

## 1. 权限系统总览

OpenHarness 的权限系统定义了三层防护：

```
用户请求
  │
  ▼
┌─────────────────────────────────────────┐
│  Layer 1: 敏感路径硬编码拦截             │
│  → SSH keys, AWS creds, GPG keys, etc.  │
│  → 不可被任何配置覆盖                    │
├─────────────────────────────────────────┤
│  Layer 2: 用户配置的规则                 │
│  → allowed_tools / denied_tools          │
│  → path_rules (glob 模式)                │
│  → denied_commands (命令黑名单)           │
├─────────────────────────────────────────┤
│  Layer 3: Permission Mode 决策           │
│  → full_auto: 全部放行                   │
│  → plan: 阻止所有写操作                   │
│  → default: 读操作放行，写操作需确认       │
└─────────────────────────────────────────┘
```

---

## 2. PermissionChecker — 权限检查器源码解析

### 2.1 三种权限模式

```python
# permissions/modes.py
class PermissionMode(str, Enum):
    DEFAULT = "default"      # 读放行，写需确认
    PLAN = "plan"            # 全部阻止修改
    FULL_AUTO = "full_auto"  # 全部放行（沙箱环境）
```

### 2.2 evaluate() 方法逐步解析

```python
# permissions/checker.py 第 75-156 行
def evaluate(
    self,
    tool_name: str,           # 工具名
    *,
    is_read_only: bool,       # 是否只读
    file_path: str | None,    # 操作的文件路径
    command: str | None,      # Shell 命令内容
) -> PermissionDecision:
    
    # ═══════════════════════════════════════════════════
    # Step 1: 敏感路径保护（硬编码，不可覆盖）
    # ═══════════════════════════════════════════════════
    if file_path:
        for candidate in _policy_match_paths(file_path):
            for pattern in SENSITIVE_PATH_PATTERNS:
                if fnmatch.fnmatch(candidate, pattern):
                    return PermissionDecision(
                        allowed=False,
                        reason=f"Access denied: {file_path} matches "
                               f"built-in sensitive pattern '{pattern}'"
                    )
    
    # Step 2: 工具明确被禁止
    if tool_name in self._settings.denied_tools:
        return PermissionDecision(allowed=False, reason=f"{tool_name} is denied")
    
    # Step 3: 工具明确被允许
    if tool_name in self._settings.allowed_tools:
        return PermissionDecision(allowed=True, reason=f"{tool_name} is allowed")
    
    # Step 4: 路径级规则检查（用户定义的 glob 规则）
    if file_path and self._path_rules:
        for candidate in _policy_match_paths(file_path):
            for rule in self._path_rules:
                if fnmatch.fnmatch(candidate, rule.pattern):
                    if not rule.allow:
                        return PermissionDecision(
                            allowed=False,
                            reason=f"Path {file_path} matches deny rule: {rule.pattern}"
                        )
    
    # Step 5: 命令黑名单（如 "rm -rf /", "DROP TABLE"）
    if command:
        for pattern in self._settings.denied_commands:
            if fnmatch.fnmatch(command, pattern):
                return PermissionDecision(
                    allowed=False,
                    reason=f"Command matches deny pattern: {pattern}"
                )
    
    # Step 6: Full Auto 模式 → 全部放行
    if self._settings.mode == PermissionMode.FULL_AUTO:
        return PermissionDecision(allowed=True, reason="Auto mode")
    
    # Step 7: 只读工具 → 放行
    if is_read_only:
        return PermissionDecision(allowed=True, reason="Read-only tool")
    
    # Step 8: Plan 模式 → 阻止所有修改
    if self._settings.mode == PermissionMode.PLAN:
        return PermissionDecision(
            allowed=False,
            reason="Plan mode blocks mutating tools"
        )
    
    # Step 9: Default 模式 → 需要用户确认
    return PermissionDecision(
        allowed=False,
        requires_confirmation=True,
        reason="Mutating tools require user confirmation"
    )
```

### 2.3 敏感路径列表（硬编码保护）

```python
SENSITIVE_PATH_PATTERNS = (
    "*/.ssh/*",                          # SSH 密钥
    "*/.aws/credentials",                # AWS 凭据
    "*/.aws/config",
    "*/.config/gcloud/*",               # GCP 凭据
    "*/.azure/*",                        # Azure 凭据
    "*/.gnupg/*",                        # GPG 密钥
    "*/.docker/config.json",            # Docker 凭据
    "*/.kube/config",                   # Kubernetes 凭据
    "*/.openharness/credentials.json",  # OpenHarness 自己的凭据
    "*/.openharness/copilot_auth.json",
)
```

**设计意义**：即使 LLM 被 prompt injection 攻击要求读取密钥文件，PermissionChecker 会直接拒绝，不给模型任何机会。

---

## 3. PermissionDecision 的数据结构

```python
@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool                # 是否允许执行
    requires_confirmation: bool = False  # 是否需要用户确认
    reason: str = ""             # 决策原因（用于 UI 显示）
```

**四种可能结果**：

| allowed | requires_confirmation | 含义 | UI 行为 |
|---------|----------------------|------|--------|
| True | False | 立即执行 | 无交互 |
| False | True | 等待用户批准 | 弹出确认对话框 |
| False | False | 直接拒绝 | 显示拒绝原因 |
| - | - | 敏感路径 | 无例外拒绝 |

---

## 4. Hook 系统 —— 生命周期扩展

### 4.1 Hook 事件类型

```python
class HookEvent(str, Enum):
    PRE_TOOL_USE = "PreToolUse"        # 工具执行前
    POST_TOOL_USE = "PostToolUse"      # 工具执行后
    # 还有更多内部事件...
```

### 4.2 Hook 在 Agent Loop 中的位置

```
┌──────────────────────────────────────────────┐
│  模型决定调用 Read("main.py")                  │
│                                              │
│  ⚡ PreToolUse Hook 触发                      │
│     → 插件可检查/修改参数                       │
│     → 如 security-guidance 插件检查路径是否安全  │
│                                              │
│  🛡️ PermissionChecker.evaluate()              │
│     → 权限决策                                │
│                                              │
│  🔧 ReadTool.execute()                       │
│     → 实际读取文件                            │
│                                              │
│  ⚡ PostToolUse Hook 触发                     │
│     → 插件可检查结果                           │
│     → 如数据脱敏插件清理敏感输出                │
└──────────────────────────────────────────────┘
```

### 4.3 Hook 定义格式

```json
// 插件中的 hooks/hooks.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "echo 'Preparing to execute...'"
        }]
      }
    ]
  }
}
```

### 4.4 HookExecutor 执行模型

```python
# hooks/executor.py（简化示意）
class HookExecutor:
    def __init__(self):
        self._pre_tool_hooks: dict[str, list[HookDefinition]] = {}
        self._post_tool_hooks: dict[str, list[HookDefinition]] = {}
    
    async def run_hooks(self, event: HookEvent, context: dict):
        if event == HookEvent.PRE_TOOL_USE:
            for hook in self._pre_tool_hooks.get(context["tool_name"], []):
                await hook.run(context)
        elif event == HookEvent.POST_TOOL_USE:
            for hook in self._post_tool_hooks.get(context["tool_name"], []):
                await hook.run(context)
```

---

## 5. 权限系统与 CLI 参数的映射

```python
# cli.py main() 参数
--permission-mode default|plan|full_auto    # 权限模式
--dangerously-skip-permissions              # 强制 full_auto
--allowed-tools "Read,Glob,Grep"            # 工具白名单
--disallowed-tools "Bash,Write"             # 工具黑名单

# 这些参数最终传递给：
settings.permission.mode = permission_mode
settings.permission.allowed_tools = allowed_tools
settings.permission.denied_tools = disallowed_tools

# 然后在 build_runtime() 中构建 PermissionChecker：
checker = PermissionChecker(settings.permission)
```

---

## 6. 安全设计总结

| 防护层 | 机制 | 可配置性 |
|-------|------|---------|
| 敏感路径 | 硬编码 `SENSITIVE_PATH_PATTERNS` | 不可覆盖 |
| 工具白名单 | `allowed_tools` | CLI / config |
| 工具黑名单 | `denied_tools` | CLI / config |
| 路径规则 | `path_rules` (glob) | config |
| 命令黑名单 | `denied_commands` (glob) | config |
| 权限模式 | `FULL_AUTO` / `DEFAULT` / `PLAN` | CLI / 运行时 |
| Hook 干预 | PreToolUse / PostToolUse | 插件 |

**安全哲学**：多重防护，默认安全（Default Deny），敏感路径不可覆盖。Hook 提供"最后一公里"的可定制性。

---

> 下一篇：`06-技能与插件系统.md` — 按需加载的知识体系与可扩展生态
