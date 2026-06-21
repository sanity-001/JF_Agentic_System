# Q9: MyToolInput 和 MyTool 为什么要分开写

## 问题

自定义工具扩展示例中，`MyToolInput` (参数模型) 和 `MyTool` (工具类) 需要写成两个独立的类？

## 解答

### 各自的服务对象不同

```python
# MyToolInput —— 消费者是 LLM + Pydantic 校验器
class MyToolInput(BaseModel):
    query: str = Field(description="Search query")  # description → JSON Schema

# MyTool —— 消费者是 Harness 引擎
class MyTool(BaseTool):
    name = "my_tool"            # 引擎用此查找
    input_model = MyToolInput   # 引擎用此校验参数

    async def execute(self, arguments: MyToolInput, context):
        return ToolResult(output=f"Result: {arguments.query}")
```

### 原因一：`to_api_schema()` 只需要 Input

引擎将工具定义发给 LLM 时，只需要参数的 JSON Schema：

```python
def to_api_schema(self):
    return {
        "name": self.name,
        "description": self.description,
        "input_schema": self.input_model.model_json_schema(),
        #   ↑ Pydantic 自动从 MyToolInput 生成，和 execute() 逻辑完全无关
    }
```

如果不拆开，无法只对参数部分调用 `model_json_schema()`。

### 原因二：参数校验与业务逻辑解耦

```python
# 引擎执行工具时的两步
parsed_args = tool.input_model.model_validate(tool_call.input)
# → 纯数据校验，Pydantic 自动完成。这步完全不需要 MyTool

result = await tool.execute(parsed_args, context)
# → 拿到合法数据后执行业务逻辑
```

Input 管"数据长什么样"，Tool 管"拿到合法数据后做什么"。拆开后不用在 `execute` 里写防御代码。

### 原因三：IDE 类型推断

```python
async def execute(self, arguments: MyToolInput, context):
    arguments.query    # ✅ IDE 自动补全
    arguments.xxx      # ❌ IDE 标红
```

如果 `arguments` 是 `BaseModel`，IDE 不知道具体有哪些字段。

### 类比

```python
# HTTP 请求处理中，Request Body 和 Handler 也是分开的
class SearchRequest(BaseModel):   # 纯数据
    query: str
    limit: int = 10

class SearchHandler:              # 纯逻辑
    def handle(self, req: SearchRequest):
        ...

# 分离的好处：改参数只改 SearchRequest，Handler 签名永远是 req: SearchRequest
```

### 一句话

```
MyToolInput = "这个工具需要什么参数、参数长什么样" → 给 Pydantic + LLM
MyTool      = "有了合法参数后，这个工具做什么事"   → 给引擎

拆开 = 数据结构 和 业务逻辑 各管各的。
```
