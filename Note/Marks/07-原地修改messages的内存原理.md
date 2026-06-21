# Q7: 原地修改 messages 列表的内存原理

## 问题

"原地修改 messages 列表，避免大量内存拷贝，50+ 轮对话可能包含数万字" 如何理解？

## 解答

### 核心概念

Agent Loop 中对 `messages` 的所有操作都是 **原地修改**，从不复制整个列表。

### 三种原地操作

```python
# 1. 列表追加（最轻量）
messages.append(ConversationMessage(...))
# 只在尾部追加指针，已有元素纹丝不动

# 2. 块级原地替换
msg.content[blk_idx] = TextBlock(text=description)
# 只改数组中一个槽位，消息对象和列表都不重建

# 3. Microcompact 内容替换
block.content = "[Old tool result content cleared]"
# 旧内容（可能 5000 字）被 GC 回收，内存反而减少
```

### 对比：每次复制会怎样

```
原地修改：
  Turn 1: [msg1, msg2] ─append→ [msg1, msg2, msg3]
  Turn 50: 同一个列表对象，只变长 → 数据复制次数 = 0
  Turn 100: 仍然 0 次复制

每次复制：
  Turn 1: messages.copy() → 分配新内存，复制全部元素
  Turn 2: messages.copy() → 又分配新内存，又复制一遍
  Turn 50: 49 个废弃副本，累计复制数千个对象引用
```

### 类比 Python 字符串

```python
# ❌ 每次 + 创建新字符串（O(n²)）
result = ""
for i in range(10000):
    result = result + str(i)

# ✅ 原地追加（O(n)）
parts = []
for i in range(10000):
    parts.append(str(i))
result = "".join(parts)
```

Agent Loop 用的是后一种思路。
