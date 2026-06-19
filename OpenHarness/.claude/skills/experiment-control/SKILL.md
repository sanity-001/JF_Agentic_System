---
name: experiment-control
description: 探测器实验控制助手。当用户要求操作水冷机、位移台、探测器、数据采集或分析时使用此技能。触发词包括：开启水冷、关闭水冷、查看水冷状态、设置温度、开启位移台、采集数据、数据分析等。
version: 0.1.0
---

# 探测器实验控制助手

此技能用于控制 JF_Control_System 实验设备。所有操作通过 HTTP REST API 调用后端服务。

## 前置条件

- JF_Control_System FastAPI 服务必须已启动（`uvicorn backend.main:app` 或类似方式）
- 默认服务地址：`http://localhost:8000`
- 如果服务地址不同，修改下方 `BASE_URL` 即可

```
BASE_URL=http://localhost:8000
```

---

## 水冷机控制 (Chiller)

水冷机通过 MODBUS RTU 串口通信控制，API 前缀为 `/api/chiller`。

### 状态查询

| 用户指令（自然语言） | 对应操作 |
|---|---|
| 查看水冷状态 / 水冷状态 / 水冷机运行情况 | `curl -s {BASE_URL}/api/chiller/status` |
| 查看水冷参数 / 水冷机设置参数 | `curl -s {BASE_URL}/api/chiller/params` |
| 查看可用串口 | `curl -s {BASE_URL}/api/chiller/ports` |

### 开关控制

| 用户指令（自然语言） | 对应操作 |
|---|---|
| 开启水冷 / 启动水冷机 / 开水冷 / 打开水冷机 | `curl -s -X POST {BASE_URL}/api/chiller/start` |
| 关闭水冷 / 停止水冷机 / 关水冷 | `curl -s -X POST {BASE_URL}/api/chiller/stop` |

### 参数设置

| 用户指令（自然语言） | 对应操作 |
|---|---|
| 设置水温到XX度 / 设定目标温度XX / 温度设为XX | `curl -s -X POST {BASE_URL}/api/chiller/setpoint -H "Content-Type: application/json" -d '{"value": XX}'` |
| 设置报警温度XX度 / 超温报警设为XX | `curl -s -X POST {BASE_URL}/api/chiller/alarm -H "Content-Type: application/json" -d '{"value": XX}'` |
| 设置偏差XX度 / 冷却偏差设为XX | `curl -s -X POST {BASE_URL}/api/chiller/deviation -H "Content-Type: application/json" -d '{"value": XX}'` |
| 设置PID参数 P=XX I=YY D=ZZ | `curl -s -X POST {BASE_URL}/api/chiller/pid -H "Content-Type: application/json" -d '{"p": XX, "i": YY, "d": ZZ}'` |

### 设备连接

| 用户指令（自然语言） | 对应操作 |
|---|---|
| 连接水冷机 / 连接水冷 端口COM3 | `curl -s -X POST {BASE_URL}/api/chiller/connect -H "Content-Type: application/json" -d '{"port": "COM3", "baudrate": 4800, "slave_address": 1}'` |
| 断开水冷机 / 断开连接 | `curl -s -X POST {BASE_URL}/api/chiller/disconnect` |

### 其他功能

| 用户指令（自然语言） | 对应操作 |
|---|---|
| 水冷机自动调谐 / 开始自整定 | `curl -s -X POST {BASE_URL}/api/chiller/autotune` |
| 蜂鸣器静音 / 关闭蜂鸣器 | `curl -s -X POST {BASE_URL}/api/chiller/mute` |

---

## 执行规则

1. **执行前先确认服务可用**：如果用户第一次操作或长时间未操作，先执行 `curl -s {BASE_URL}/api/health` 确认服务在线。
2. **操作后反馈结果**：将 API 返回的 JSON 结果解析为人类可读的中文描述告知用户。
3. **错误处理**：如果 curl 返回错误（连接拒绝、超时等），提示用户检查 FastAPI 服务是否启动。
4. **温度单位**：所有温度值单位为摄氏度（°C）。
5. **安全性**：
   - 设置参数时，温度合理范围 15~25°C，超出范围先询问用户确认。
   - `start` / `stop` 操作直接执行，不需要确认。
