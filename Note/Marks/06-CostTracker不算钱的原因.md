# Q6: CostTracker 为什么不算实际金额

## 问题

不同大模型计费规则不同，CostTracker 如何获得实际花费金额？

## 答案：CostTracker 只追踪 Token 数，不算钱

### 源码真相

```python
# api/usage.py
class UsageSnapshot(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    # ← 没有 cost_usd 字段！

# engine/cost_tracker.py
class CostTracker:
    def __init__(self):
        self._usage = UsageSnapshot()

    def add(self, usage):
        self._usage = UsageSnapshot(
            input_tokens=self._usage.input_tokens + usage.input_tokens,
            output_tokens=self._usage.output_tokens + usage.output_tokens,
        )
    # ← 没有任何价格计算
```

### 为什么不算钱

1. **计费规则过于复杂**：不同模型价格天差地别，还有 Prompt Caching 折扣（-90%）、Batch API 折扣（-50%）、不同 Region 不同价、订阅 vs 按量付费

2. **API 响应中不含费用**：绝大多数 LLM API 只返回 token 数，费用由服务端计费系统计算

3. **准确计费应看账单**：客户端估算只是近似值，和实际账单总有差异

### 如果一定要加

维护价格表 + 根据模型名查找：

```python
MODEL_PRICING = {
    "claude-sonnet-4-6": (3.0, 15.0),   # (input, output) $/百万token
    "deepseek-chat":     (0.27, 1.10),
}

class UsageSnapshot:
    def cost_usd(self, model: str) -> float:
        inp, out = MODEL_PRICING.get(model, (0, 0))
        return (self.input_tokens/1_000_000)*inp + (self.output_tokens/1_000_000)*out
```

但代价是需要持续维护价格表，每次新模型/调价都要更新代码。OpenHarness 选择不做，精力放在核心功能上。
