# 工具系统 (Tool System) —— 深度源码解析

> **关键文件**: `tools/base.py`、`tools/__init__.py`、各个 `tools/*_tool.py`  
> **数量**: 43+ 个工具  
> **设计模式**: 策略模式 + 注册表模式 + Pydantic 类型安全

---

## 1. 工具系统架构

```
tools/
├── base.py                    # 🔑 基础抽象：BaseTool、ToolRegistry、ToolResult
├── __init__.py                #    工厂函数 create_default_tool_registry()
│
├── # === 文件操作类 ===
├── file_read_tool.py          #    Read —— 读取文件内容
├── file_write_tool.py         #    Write —— 覆盖写入
├── file_edit_tool.py          #    Edit —— 精确字符串替换
├── glob_tool.py               #    Glob —— 文件名模式匹配
├── grep_tool.py               #    Grep —— 正则内容搜索
│
├── # === Shell 执行类 ===
├── bash_tool.py               #    Bash —— 执行 Shell 命令
│
├── # === Web 类 ===
├── web_fetch_tool.py          #    WebFetch —— URL 抓取转 Markdown
├── web_search_tool.py         #    WebSearch —— 搜索引擎查询
│
├── # === Agent 调度类 ===
├── agent_tool.py              #    Agent —— 派生子 Agent
├── send_message_tool.py       #    SendMessage —— 向子 Agent 发消息
├── team_create_tool.py        #    TeamCreate —— 创建团队
├── team_delete_tool.py        #    TeamDelete —— 删除团队
│
├── # === 任务管理类 ===
├── task_create_tool.py        #    TaskCreate —— 创建任务
├── task_get_tool.py           #    TaskGet —— 获取任务详情
├── task_list_tool.py          #    TaskList —— 列出所有任务
├── task_update_tool.py        #    TaskUpdate —— 更新任务状态
├── task_output_tool.py        #    TaskOutput —— 获取任务输出
├── task_stop_tool.py          #    TaskStop —— 停止任务
│
├── # === 模式切换类 ===
├── enter_plan_mode_tool.py    #    EnterPlanMode —— 进入计划模式
├── exit_plan_mode_tool.py     #    ExitPlanMode —— 退出计划模式
├── enter_worktree_tool.py     #    EnterWorktree —— 进入工作树
├── exit_worktree_tool.py      #    ExitWorktree —— 退出工作树
│
├── # === 定时任务类 ===
├── cron_create_tool.py        #    CronCreate —— 创建定时任务
├── cron_list_tool.py          #    CronList —— 列出定时任务
├── cron_delete_tool.py        #    CronDelete —— 删除定时任务
├── cron_toggle_tool.py        #    CronToggle —— 开关定时任务
│
├── # === 交互类 ===
├── ask_user_question_tool.py  #    AskUserQuestion —— 向用户提问
├── skill_tool.py              #    Skill —— 加载技能
│
├── # === MCP 类 ===
├── mcp_tool.py                #    MCPTool —— 调用 MCP 工具
├── list_mcp_resources_tool.py #    ListMcpResources
├── read_mcp_resource_tool.py  #    ReadMcpResource
│
├── # === Notebook ===
├── notebook_edit_tool.py      #    NotebookEdit —— 编辑 Jupyter Notebook
│
├── # === 辅助类 ===
├── image_generation_tool.py   #    ImageGeneration —— AI 图片生成
├── image_to_text_tool.py      #    ImageToText —— 图片转文本
├── lsp_tool.py                #    LSP —— 语言服务器协议
├── sleep_tool.py              #    Sleep —— 等待
├── brief_tool.py              #    Brief —— 上下文简报
├── config_tool.py             #    Config —— 配置管理
├── todo_write_tool.py         #    TodoWrite —— 写入 TODO
├── tool_search_tool.py        #    ToolSearch —— 工具搜索
└── remote_trigger_tool.py     #    RemoteTrigger —— 远程触发
```

---

## 2. 工具基础架构

### 2.1 BaseTool —— 所有工具的抽象基类

```python
# tools/base.py 第 35-57 行
class BaseTool(ABC):
    """所有 OpenHarness 工具的基类"""
    
    name: str                           # 工具名（会被模型引用）
    description: str                    # 工具描述（模型据此决定是否使用）
    input_model: type[BaseModel]        # Pydantic 输入模型（类型安全！）
    
    @abstractmethod
    async def execute(
        self, 
        arguments: BaseModel,           # 类型安全的参数
        context: ToolExecutionContext   # 执行上下文（cwd、hooks 等）
    ) -> ToolResult:
        """子类实现具体逻辑"""
    
    def is_read_only(self, arguments: BaseModel) -> bool:
        """默认返回 False；只读工具覆写返回 True"""
        return False
    
    def to_api_schema(self) -> dict[str, Any]:
        """将工具定义转换为 Anthropic API 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }
```

**关键设计**：
- `input_model` 使用 **Pydantic BaseModel**——参数被自动校验、序列化为 JSON Schema 传给 LLM
- `to_api_schema()` 利用 Pydantic 的 `model_json_schema()` 自动生成 API 所需的 JSON Schema，无需手写
- `is_read_only()` 区分读写——只读工具在 default 模式下无需用户确认

### 2.2 ToolResult —— 统一的执行结果

```python
# tools/base.py 第 26-32 行
@dataclass(frozen=True)
class ToolResult:
    output: str                         # 执行输出文本
    is_error: bool = False              # 是否出错
    metadata: dict[str, Any] = field(default_factory=dict)  # 附加元数据
```

**不可变设计**（`frozen=True`）：工具结果不应被后续逻辑修改，保证执行的可追溯性。

### 2.3 ToolExecutionContext —— 执行上下文

```python
@dataclass
class ToolExecutionContext:
    cwd: Path                           # 当前工作目录
    metadata: dict[str, Any] = field(default_factory=dict)  # 共享元数据
    hook_executor: HookExecutor | None = None  # 钩子访问
```

### 2.4 ToolRegistry —— 工具注册表

```python
# tools/base.py 第 60-80 行
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具实例"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> BaseTool | None:
        """按名称查找工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> list[BaseTool]:
        """列出所有已注册工具"""
        return list(self._tools.values())
    
    def to_api_schema(self) -> list[dict[str, Any]]:
        """将所有工具转为 API 格式的 Schema 列表"""
        return [tool.to_api_schema() for tool in self._tools.values()]
```

---

## 3. 实际工具示例：Read 工具

以文件读取工具为例展示完整实现模式：

```python
# 伪代码示意（实际实现在 file_read_tool.py）
from pydantic import BaseModel, Field

class ReadInput(BaseModel):
    """模型会看到这个 schema"""
    file_path: str = Field(description="Absolute path to the file to read")
    offset: int | None = Field(None, description="Start reading from this line")
    limit: int | None = Field(None, description="Number of lines to read")

class ReadTool(BaseTool):
    name = "Read"
    description = "Reads a file from the local filesystem."
    input_model = ReadInput
    
    def is_read_only(self, arguments: BaseModel) -> bool:
        return True  # ← 读文件不需要用户确认
    
    async def execute(
        self, 
        arguments: ReadInput, 
        context: ToolExecutionContext
    ) -> ToolResult:
        file_path = Path(arguments.file_path)
        if not file_path.exists():
            return ToolResult(
                output=f"File not found: {arguments.file_path}",
                is_error=True,
            )
        try:
            content = file_path.read_text(encoding="utf-8")
            return ToolResult(output=content)
        except Exception as e:
            return ToolResult(output=str(e), is_error=True)
```

---

## 4. 工厂函数：create_default_tool_registry()

```python
# tools/__init__.py
def create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(BashTool())
    registry.register(WebFetchTool())
    registry.register(WebSearchTool())
    registry.register(AgentTool())
    # ... 43+ 个工具依次注册
    return registry
```

在 `cli.py` 的 dry-run 流程和 `ui/runtime.py` 的 `build_runtime()` 中调用此函数。

---

## 5. 自定义工具扩展示例

OpenHarness 的工具系统对扩展开放：

```python
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

class MyToolInput(BaseModel):
    query: str = Field(description="Search query")

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    input_model = MyToolInput
    
    async def execute(
        self, arguments: MyToolInput, context: ToolExecutionContext
    ) -> ToolResult:
        # 你的业务逻辑
        return ToolResult(output=f"Result for: {arguments.query}")

# 注册
registry.register(MyTool())
```

---

## 6. 工具分类总览

| 类别 | 工具数量 | 典型工具 | 权限特征 |
|------|---------|---------|---------|
| **文件 I/O** | 5 | Read, Write, Edit, Glob, Grep | Write/Edit 需要确认 |
| **Shell** | 1 | Bash | 高风险，严格检查 |
| **Web** | 2 | WebFetch, WebSearch | 只读，SSRF 防护 |
| **Agent 调度** | 4 | Agent, SendMessage, TeamCreate/Delete | 子进程创建 |
| **任务管理** | 6 | TaskCreate/Get/List/Update/Output/Stop | 状态变更 |
| **模式切换** | 4 | Enter/ExitPlanMode, Enter/ExitWorktree | 模式变更 |
| **定时任务** | 4 | CronCreate/List/Delete/Toggle | 持久化写入 |
| **MCP 协议** | 3 | MCPTool, List/ReadMcpResource | 外部调用 |
| **交互** | 2 | AskUserQuestion, Skill | 暂停等待用户 |
| **其他** | 8+ | ImageGen, Sleep, TodoWrite, ... | 各不相同 |

---

## 7. 工具的权限检查整合

每个工具执行前都会经过 `PermissionChecker.evaluate()`：

```python
# 权限检查调用
decision = permission_checker.evaluate(
    tool_name="Write",           # 工具名
    is_read_only=tool.is_read_only(args),  # 是否只读
    file_path="/etc/hosts",     # 操作的文件路径
    command="rm -rf /",         # Shell 命令内容
)
# 返回 PermissionDecision(allowed=True/False, requires_confirmation=True/False)
```

这个设计让权限系统和工具系统完全解耦——工具不需要知道权限逻辑，权限系统通过工具名、路径、命令内容做判断。

---

> 下一篇：`04-配置与Provider系统.md` — 多层配置优先级与多 Provider 热切换
