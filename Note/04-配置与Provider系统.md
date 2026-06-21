# 配置与 Provider 系统 —— 深度源码解析

> **关键文件**: `config/settings.py`、`config/paths.py`、`auth/manager.py`  
> **模型**: Pydantic BaseModel + 多层优先级合并  
> **核心概念**: Provider Profile 将"用什么模型"从"怎么连接 API"中解耦

---

## 1. 配置优先级体系

OpenHarness 的配置优先级从高到低：

```
优先级最高
  │  1. CLI 参数         (--model sonnet, --api-key sk-xxx, --base-url ...)
  │  2. 环境变量         (ANTHROPIC_API_KEY, OPENHARNESS_MODEL, ...)
  │  3. Provider Profile (~/.openharness/profiles.json)
  │  4. 设置文件          (~/.openharness/settings.json)
  │  5. 外部绑定          (Claude CLI / Codex CLI subscription bridging)
  ▼  6. 代码默认值        (Pydantic Field(default=...))
优先级最低
```

在代码中体现为 **链式覆盖**：

```python
# cli.py 中
settings = load_settings().merge_cli_overrides(
    model=model, api_key=api_key, base_url=base_url, ...
)
# load_settings(): 从文件 + 环境变量加载
# merge_cli_overrides(): 用 CLI 参数覆盖
```

---

## 2. Settings 模型 — Pydantic 驱动的类型安全配置

```python
# config/settings.py
class PermissionSettings(BaseModel):
    mode: PermissionMode = PermissionMode.DEFAULT
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    path_rules: list[PathRuleConfig] = Field(default_factory=list)
    denied_commands: list[str] = Field(default_factory=list)

class MemorySettings(BaseModel):
    enabled: bool = True
    max_files: int = 5
    max_entrypoint_lines: int = 200
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None
    auto_extract_enabled: bool = False
    session_memory_enabled: bool = True
    auto_dream_enabled: bool = False
    auto_dream_min_hours: float = 24.0

class SandboxSettings(BaseModel):
    network: SandboxNetworkSettings = Field(default_factory=SandboxNetworkSettings)
    filesystem: SandboxFilesystemSettings = Field(...)
    docker: DockerSandboxSettings = Field(...)

class Settings(BaseModel):
    """顶层 Settings，聚合所有配置子模型"""
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 16384
    base_url: str | None = None
    api_format: str = "anthropic"
    max_turns: int | None = None
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    sandbox: SandboxSettings = Field(...)
    # ... 更多字段
```

**Pydantic 的优势**：
- 自动类型校验：`model: str` 不会接受 `int`
- 嵌套模型：`Settings.permission.mode` 自动递归校验
- JSON 序列化：`settings.model_dump_json()` 一行写入文件
- 默认值工厂：`Field(default_factory=list)` 避免可变默认值的陷阱

---

## 3. Provider Profile —— 多后端管理

### 3.1 为什么需要 Profile？

同一个用户可能同时使用多个 AI 后端：

```
- Claude API       (api.anthropic.com)         → 写复杂代码
- DeepSeek         (api.deepseek.com)           → 快速迭代
- 本地 Ollama       (localhost:11434)            → 离线使用
- Codex 订阅       (~/.codex/auth.json)         → 用已有的订阅
```

Profile 机制让这些后端以"命名配置"的方式共存，一键切换。

### 3.2 ProviderProfile 数据模型

```python
@dataclass
class ProviderProfile:
    label: str                    # 显示名："Claude Official"
    provider: str                 # 运行时后端："anthropic" | "openai" | ...
    api_format: str               # API 格式："anthropic" | "openai" | "copilot"
    auth_source: str              # 认证来源："anthropic_api_key" | ...
    default_model: str            # 默认模型："claude-sonnet-4-6"
    last_model: str               # 最近使用的模型
    base_url: str | None = None   # 自定义后端 URL
    credential_slot: str | None   # 独立凭据槽
    allowed_models: list[str]     # 允许的模型列表
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None
    
    @property
    def resolved_model(self) -> str:
        """last_model 为空时回退到 default_model"""
        return self.last_model or self.default_model
```

### 3.3 内置 Profile 一览

| Profile 名 | Provider | API 格式 | 认证方式 |
|-----------|----------|---------|---------|
| `claude-api` | anthropic | anthropic | API Key |
| `claude-subscription` | anthropic_claude | anthropic | Claude CLI 绑定 |
| `openai-compatible` | openai | openai | API Key |
| `codex` | openai_codex | openai | Codex CLI 绑定 |
| `copilot` | copilot | copilot | GitHub OAuth |
| `kimi-anthropic` | anthropic | anthropic | API Key (Moonshot) |
| `glm-anthropic` | anthropic | anthropic | API Key (Zhipu) |
| `minimax-anthropic` | anthropic | anthropic | API Key (MiniMax) |
| `openrouter` | openai | openai | API Key (OpenRouter) |

### 3.4 AuthManager —— Profile 的 CRUD

```python
# auth/manager.py
class AuthManager:
    def list_profiles(self) -> dict[str, ProviderProfile]: ...
    def get_active_profile(self) -> str | None: ...
    def use_profile(self, name: str) -> None: ...
    def upsert_profile(self, name: str, profile: ProviderProfile) -> None: ...
    def update_profile(self, name: str, **kwargs) -> None: ...
    def remove_profile(self, name: str) -> None: ...
    def store_profile_credential(self, name, kind, value) -> None: ...
    def get_profile_statuses(self) -> dict[str, dict]: ...
    def switch_provider(self, provider: str) -> None: ...
```

---

## 4. 配置加载流程

```
cli.py: main() 被调用
  │
  ├─ load_settings()  ←─────────────────────────────┐
  │    │                                              │
  │    ├─ 读取 ~/.openharness/settings.json           │
  │    ├─ 读取环境变量 (ANTHROPIC_API_KEY,            │
  │    │   OPENHARNESS_MODEL, OPENHARNESS_BASE_URL...) │
  │    └─ 返回 Settings 对象                          │
  │                                                   │
  ├─ settings.merge_cli_overrides(                    │
  │      model=model,                                 │
  │      api_key=api_key,                             │
  │      base_url=base_url,                           │
  │      ...                                          │
  │  )                                                │
  │    │                                              │
  │    └─ 返回新 Settings（用 CLI 参数覆盖字段）        │
  │                                                   │
  ├─ settings.resolve_profile()                       │
  │    │                                              │
  │    ├─ 读取 ~/.openharness/profiles.json            │
  │    ├─ 找到 active profile                        │
  │    └─ 将 profile 的 model/base_url/auth 合并      │
  │                                                   │
  └─ 构建 RuntimeBundle                              │
       ├─ QueryEngine(settings, ...)                  │
       ├─ ToolRegistry                                │
       ├─ PermissionChecker(settings.permission)       │
       └─ ...                                         │
```

---

## 5. Dry-Run 的配置验证

`--dry-run` 模式的核心价值之一：**在不调用模型的前提下验证配置完整性**。

```python
# cli.py _evaluate_dry_run_readiness()
# 检查链路：

1. 斜杠命令存在？
   └─ NO → blocked: "does not match any registered slash command"

2. API 客户端能解析？
   └─ NO + 需要模型调用 → blocked: "Fix authentication first"
   └─ NO + 仅交互式 → warning: "model execution would fail"

3. MCP 服务器配置正确？
   └─ 有错误 → warning: "Fix broken MCP config"

4. 认证状态正常？
   └─ 缺失 → warning: "Run `oh auth login` first"

5. 以上全通过 → ready: "You can run this directly"
```

这是一个非常实用的"启动前检查"模式，避免用户折腾半天发现 API Key 没配。

---

## 6. 凭据存储

```
~/.openharness/
├── settings.json             # 主配置
├── profiles.json             # Provider 配置
├── credentials.json          # API Key（加密存储）
├── copilot_auth.json         # Copilot OAuth token
├── external_bindings.json    # Claude/Codex CLI 绑定
├── skills/                   # 用户级技能
├── plugins/                  # 用户级插件
├── sessions/                 # 会话历史
└── logs/                     # 日志
```

凭据存储的安全性设计：
- `credentials.json` 只有当前用户可读（`chmod 600`）
- 敏感路径（`.ssh`、`.aws`、`.kube`）在 **PermissionChecker 层面硬编码禁止访问**，即使 LLM 要求读取也会被拒绝
- 外部绑定（Claude CLI / Codex CLI）不存储原始凭据，只记录绑定关系，实际 token 由上游 CLI 管理

---

## 7. Provider 检测机制

```python
# api/provider.py
def detect_provider(settings: Settings) -> ProviderInfo:
    if settings.api_format == "copilot":
        return ProviderInfo("copilot", ...)
    if settings.api_format == "openai":
        return ProviderInfo("openai", ...)
    # 默认
    return ProviderInfo("anthropic", ...)
```

Provider 决定了：
- API 请求格式（Anthropic vs OpenAI 消息格式）
- 流式解析方式
- Token 计数方式
- 支持的模型特性（视觉、推理等）

---

> 下一篇：`05-权限与Hook系统.md` — 多层安全防护与生命周期钩子
