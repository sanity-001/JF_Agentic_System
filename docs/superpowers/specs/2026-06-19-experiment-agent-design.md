# 探测器实验 Agent 助手 — 设计方案

> 日期：2026-06-19
> 状态：待审查
> 目标：基于 OpenHarness 框架，将 JF_Control_System 改造为智能实验 Agent 助手

---

## 1. 背景与目标

### 1.1 当前状态

- **JF_Control_System**：完整的 FastAPI 后端，控制水冷机（MODBUS RTU）、位移台（串口）、X 射线探测器（slsDet），以及数据处理管线（增益图、噪声峰图、高斯拟合等）
- **OpenHarness**：完整的 Agent 运行时框架，提供 Agent Loop、Tool 注册、Skill 加载、Memory、Session 管理等基础设施
- **现有 Skill**（`.claude/skills/experiment-control/SKILL.md`）：本质上是一个"自然语言→curl 命令"的短语手册，缺少状态感知、工作流编排、安全联锁和数据解读能力

### 1.2 目标

- **C 模式（全自动）**：用户给出实验目标 → Agent 自主完成全部步骤并汇报结果
- **B 模式（半自动）**：关键步骤暂停等待用户确认（C 模式的子集，在步骤间插入确认节点即可）
- **唯一例外**：X 光机未接入控制系统，基线→信号之间必须人工确认 X 光已开启

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **不改后端** | JF_Control_System 的 FastAPI 代码不动，所有扩展在 OpenHarness 侧完成 |
| **Tool 做手脚，Skill 做脑子** | Tool 负责执行（调用 API、校验、翻译），Skill 负责知识（工作流、安全规则、诊断） |
| **安全联锁在 Tool 层硬编码** | 不可绕过 Agent 推理，即使 Agent 忘记检查，Tool 也会拒绝危险操作 |
| **混合粒度** | 常规操作提供复合 Tool（一步完成），调试操作提供细粒度 Tool（逐步排查） |

---

## 2. 架构

```
┌─────────────────────────────────────────┐
│  OpenHarness Agent Runtime（不动）       │
│  Agent Loop / Tool Registry / Skills    │
│  Memory / Session / Permission          │
├─────────────────────────────────────────┤
│  🔌 Experiment Control Plugin（新建）    │
│  ┌──────────────┐  ┌──────────────────┐ │
│  │ Tools (Python)│  │ Skills (Markdown)│ │
│  │ ~37 个 Tool   │  │ 3 个 SKILL.md   │ │
│  └──────┬───────┘  └──────────────────┘ │
│  ┌──────┴──────────────────────────────┐ │
│  │  Agents（Subagent）                  │ │
│  │  safety-watcher（后台安全监控）       │ │
│  └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│  JF_Control_System FastAPI（不动）       │
│  /api/chiller /api/detector ...         │
├─────────────────────────────────────────┤
│  物理硬件                                │
│  MODBUS / 串口 / slsDet                  │
└─────────────────────────────────────────┘
```

### 2.1 Plugin 文件结构

```
.openharness/plugins/experiment-control/
├── plugin.json
├── tools/
│   ├── __init__.py
│   ├── chiller_tools.py
│   ├── detector_tools.py
│   ├── stage_tools.py
│   ├── processing_tools.py
│   └── system_tools.py
├── skills/
│   ├── experiment-control/
│   │   └── SKILL.md
│   ├── safety-rules/
│   │   └── SKILL.md
│   └── troubleshooting/
│       └── SKILL.md
└── agents/
    └── safety-watcher.md
```

---

## 3. Tool 设计

### 3.1 配置

Plugin 通过以下方式获取 FastAPI 地址（优先级从高到低）：

1. 环境变量 `JF_CONTROL_API_URL`（如 `http://localhost:8000`）
2. Plugin 默认值 `http://localhost:8000`

所有 Tool 的 HTTP 调用使用 `aiohttp`（异步，不阻塞 Agent Loop）。

### 3.2 设计模式

所有 Tool 遵循统一模式：

```python
class SomeToolInput(BaseModel):
    """参数定义（Pydantic，自动生成 JSON Schema）"""
    value: float

class SomeTool(BaseTool):
    name = "some_tool_name"
    description = "做什么，Agent 据此决定何时调用"

    async def execute(self, arguments, context):
        # 1. 参数校验（范围、类型）
        # 2. 调用 FastAPI（HTTP GET/POST）
        # 3. 翻译结果为人类可读文本
        # 4. 错误时返回 ToolResult(is_error=True)
```

### 3.2 水冷机 Tools（7 个）

| Tool | 类型 | API | 说明 |
|------|------|-----|------|
| `chiller_get_status` | 细粒度 | `GET /api/chiller/status` | 温度、流量、运行时间、指示灯 |
| `chiller_get_params` | 细粒度 | `GET /api/chiller/params` | PID、报警温度、偏差等参数 |
| `chiller_set_temperature` | 细粒度 | `POST /api/chiller/setpoint` | 设定目标温度，Tool 层校验 15~25°C |
| `chiller_set_pid` | 细粒度 | `POST /api/chiller/pid` | 设定 PID 参数 |
| `chiller_start` | 细粒度 | `POST /api/chiller/start` | 启动水冷机 |
| `chiller_stop` | 细粒度 | `POST /api/chiller/stop` | 停止水冷机 |
| `chiller_wait_stable` | **复合** | 轮询 `GET /api/chiller/status` | 等待温度稳定到目标 ±0.3°C，最长 600s，超时报错 |

### 3.3 探测器 Tools（13 个）

> **后端补充**：需在 `detector/router.py` 中新增 `POST /api/detector/mode` 接口（~6 行代码），暴露 `_detector.acq_mode` 属性。现有代码不动。

| Tool | 类型 | API | 说明 |
|------|------|-----|------|
| `detector_get_status` | 细粒度 | `GET /api/detector/status` | 连接状态、采集状态、芯片版本 |
| `detector_get_params` | 细粒度 | `GET /api/detector/params` | 当前所有参数 |
| `detector_get_temperatures` | 细粒度 | `GET /api/detector/temperatures` | FPGA/ADC 温度 |
| `detector_load_config` | 细粒度 | `POST /api/detector/load_config` | ⭐ 加载本地 .config 配置文件并自动连接（正常连接方式） |
| `detector_connect` | 细粒度 | `POST /api/detector/connect` | 不使用配置文件时的连接方式（hostname + 参数） |
| `detector_disconnect` | 细粒度 | `POST /api/detector/disconnect` | 断开连接 |
| `detector_set_param` | 细粒度 | `POST /api/detector/params` | 设置单个参数（exptime、frames 等） |
| `detector_set_mode` | 细粒度 | `POST /api/detector/mode` | 设置采集模式：`"baseline"` 或 `"signal"` |
| `detector_start_acquisition` | 细粒度 | `POST /api/detector/acquire/start` | 启动采集（非阻塞） |
| `detector_stop_acquisition` | 细粒度 | `POST /api/detector/acquire/stop` | 停止采集 |
| `detector_process_result` | 细粒度 | 内部调用 process_visual | 处理采集结果（基线模式→保存基线，信号模式→减基线） |
| `detector_run_acquisition` | **复合** | 多个 API 组合 | ⭐ 一键采集：加载配置→设模式→设参数→启动→等待→处理结果。内部含安全联锁（见下） |
| `detector_shutdown` | **复合** | stopDetector→降压→关powerchip→释放共享内存 | 安全关机，4 步原子执行 |

**detector_run_acquisition 的执行流程**：
```python
# 复合 Tool 内部伪代码
async def execute(self, args, ctx):
    # 1. 加载配置文件（连接探测器）
    POST /api/detector/load_config {"path": args.config_path}

    # 2. 设置采集模式
    POST /api/detector/mode {"mode": args.mode}  # "baseline" | "signal"

    # 3. 设置参数
    for key, value in args.params.items():
        POST /api/detector/params {"key": key, "value": value}

    # 4. 🛡️ 信号模式下的安全联锁
    if args.mode == "signal":
        chiller_status = GET /api/chiller/status
        if not chiller_status["indicators"]["run"]:
            return error("水冷未运行，拒绝采集")
        if not (target_temp - 2 <= chiller_status["temperature"] <= target_temp + 2):
            return error(f"温度偏离目标超过 2°C")

    # 5. 启动采集 + 轮询等待完成
    POST /api/detector/acquire/start
    while not done:
        sleep(1)
        status = GET /api/detector/status

    # 6. 处理结果（baseline 模式保存基线，signal 模式减基线）
    result = process_visual(raw_paths)

    # 7. 返回人类可读摘要
    return f"采集完成。模式：{args.mode}，{shape}，耗时 {duration}s"
```

### 3.4 位移台 Tools（6 个）

| Tool | 类型 | API | 说明 |
|------|------|-----|------|
| `stage_get_status` | 细粒度 | `GET /api/displacement/status` | 当前位置、原点、扫描状态 |
| `stage_move_absolute` | 细粒度 | `POST /api/displacement/move/absolute` | 绝对定位 |
| `stage_move_relative` | 细粒度 | `POST /api/displacement/move/relative` | 相对移动 |
| `stage_origin_return` | 细粒度 | `POST /api/displacement/origin` | 回原点 |
| `stage_start_scan` | 细粒度 | `POST /api/displacement/scan/start` | 启动扫描 |
| `stage_stop` | 细粒度 | `POST /api/displacement/stop` | 紧急停止（所有轴） |

### 3.5 数据处理 Tools（7 个）

| Tool | 类型 | API | 说明 |
|------|------|-----|------|
| `processing_read_frame` | 细粒度 | `POST /api/processing/frame/read` | 读单帧 + 统计（min/max/mean/std）+ base64 图像 |
| `processing_average_frames` | 细粒度 | `POST /api/processing/frame/average` | 帧范围平均帧，可选扣基线 |
| `processing_fit_pixel` | 细粒度 | `POST /api/processing/pixel/fit` | 单像素高斯+erfc 拟合 → Gain (ADU/keV)、噪声峰、信号峰 |
| `processing_compute_gainmap` | 细粒度 | `POST /api/processing/gainmap/compute` | 全传感器增益图 + base64 热力图 |
| `processing_compute_noisemap` | 细粒度 | `POST /api/processing/noisemap/compute` | 全传感器噪声峰位置图 |
| `processing_compute_stdmap` | 细粒度 | `POST /api/processing/stdmap/compute` | 像素时间序列标准差图 |
| `processing_analyze_acquisition` | **复合** | 多个 API 组合 | ⭐ 采集后一键分析：平均帧 + 增益图 + 噪声峰图 + 生成摘要 |

### 3.6 系统 Tools（3 个）

| Tool | 类型 | API | 说明 |
|------|------|-----|------|
| `system_check` | 细粒度 | `GET /api/health` + 前端探测 | 检查后端和前端是否在线 |
| `system_startup` | **复合** | subprocess + 健康轮询 | ⭐ 一键启动后端（`python run.py`）和前端（`npm run dev`），轮询等待就绪 |
| `system_shutdown` | **复合** | 终止子进程 | 停止后端和前端进程 |

**system_startup 执行流程**：
```python
async def execute(self, args, ctx):
    # 1. 直接调用项目自带的 start.py（通过 conda 环境 slsdet9）
    proc = subprocess.Popen(
        ["conda", "run", "-n", "slsdet9", "python", "start.py"],
        cwd=JF_CONTROL_SYSTEM_DIR,
        start_new_session=True  # 独立进程组，工具返回后进程不挂
    )
    # 2. 轮询后端就绪
    for _ in range(30):
        try:
            resp = await http_get("http://localhost:8000/api/health")
            if resp.status_code == 200: break
        except Exception: pass
        await asyncio.sleep(1)
    # 3. 保存 PID 供 shutdown 使用
    ctx.metadata["startup_pid"] = proc.pid
    return "✅ 后端 :8000 + 前端 :5173 已就绪"
```

**system_shutdown 执行流程**：
```python
async def execute(self, args, ctx):
    pid = ctx.metadata.get("startup_pid")
    if pid:
        os.killpg(pid, signal.SIGTERM)  # 终止进程组（start.py + backend + frontend）
    return "✅ 系统已停止"
```

**设计要点**：
- 直接调用项目自带的 `start.py`，不重复实现其逻辑
- `conda run -n slsdet9` 自动激活 conda 环境
- `start_new_session=True` 创建独立进程组 → `os.killpg` 一键终止整棵树

**使用方式**：用户打开 OpenHarness 后，第一个指令就是"启动实验系统"，Agent 调用 `system_startup`，然后直接进入实验流程，不再需要用户手动操作。

---

## 4. Skill 设计

### 4.1 experiment-control（主 Skill）

**触发词**：开启水冷、设置温度、采集数据、基线采集、信号采集、增益图、噪声分析、数据分析

**核心内容**：
- 工具清单速查表（4 类设备的全部可用工具）
- 3 个标准实验工作流
- B/C 模式切换规则
- X 光机联锁规则

**标准工作流**：

#### 工作流 1：降温 + 信号采集（最常用）

```
0. system_startup                 → 一键启动后端+前端（如未启动）
1. chiller_get_status              → 确认连接和温度
2. chiller_set_temperature(20)     → 设定目标温度
3. chiller_wait_stable(20)         → 等待稳定
4. detector_load_config(           → 加载配置文件，连接探测器
     "path/to/config.config")
5. detector_set_mode("baseline")   → 设为基线模式
6. detector_set_param("exptime", "500")
7. detector_run_acquisition(       → 采集基线
     mode="baseline", ...)
8. ⚠️ 暂停，询问用户：               X 光机联锁（强制 B 模式）
   "基线采集完成。请确认已开启 X 光机，然后我将继续采集信号。"
9. 等待用户确认
10. detector_set_mode("signal")    → 切换为信号模式
11. detector_run_acquisition(      → 采集信号
      mode="signal", ...)
12. processing_analyze_acquisition → 自动分析
13. 总结结果
```

#### 工作流 2：纯基线采集（不需要 X 光）
```
1. 降温 + 稳定
2. detector_load_config → detector_set_mode("baseline")
3. detector_run_acquisition(mode="baseline") → 直接完成，不询问 X 光
```

#### 工作流 3：纯信号采集（基线已有）
```
1. 降温 + 稳定
2. detector_load_config → detector_set_mode("signal")
3. ⚠️ 询问："请确认 X 光机已开启并稳定，然后开始信号采集？"
4. detector_run_acquisition(mode="signal")
5. processing_analyze_acquisition
```

### 4.2 safety-rules（安全规则 Skill）

被主 Skill 引用，独立维护的安全约束。内容包括：

| 类别 | 规则 | 条件 | 动作 |
|------|------|------|------|
| 水冷 | 温度上限 | 设定 > 25°C | 拒绝 |
| 水冷 | 温度下限 | 设定 < 15°C | 拒绝 |
| 水冷 | 运行检查 | 采集前水冷未运行 | 警告 |
| 水冷 | 温度偏离 | 偏离目标 > 5°C | 报警 |
| 水冷 | 流量异常 | 流量 < **2** L/min | 报警（可能管道堵塞） |
| 探测器 | 温度监控 | FPGA > 60°C | 报警 |
| 探测器 | 温度紧急 | FPGA > 70°C | 立即停止采集并降压 |
| 探测器 | 采集前检查 | 未连接 | 拒绝采集 |
| 探测器 | 关机流程 | 用户要求关机 | 必须用 detector_shutdown |
| 位移台 | 行程保护 | 目标超出行程 | 拒绝 |
| 位移台 | 扫描保护 | 扫描步数 > 1000 | 询问确认 |
| 实验联锁 | 采集前提 | 水冷运行 + 温度在目标 ±2°C + 探测器已连接 | 必须全部满足 |
| X 光 | 信号采集前 | 强制暂停确认 | 不可跳过 |

### 4.3 troubleshooting（故障诊断 Skill）

常见故障的诊断步骤和可操作建议：

- **水冷无法连接**：检查串口列表 → 检查供电 → 检查 MODBUS 参数
- **温度降不下来**：确认已启动 → 检查冷却液 → 检查环境温度
- **探测器采集失败**：检查 receiver → 检查连接 → 尝试重连
- **增益图异常**：确认基线文件 → 抽查像素 → 对比区域差异

诊断策略：先查状态再操作，从简单到复杂，给用户可操作的建议而非纯报错。

---

## 5. Safety-Watcher Subagent

### 5.1 定义

```markdown
---
name: safety-watcher
description: 后台安全监控 agent，定期检查设备状态，异常时主动报警
background: true
tools:
  - chiller_get_status
  - detector_get_status
  - detector_get_temperatures
  - stage_get_status
max_turns: 1
color: red
---
```

### 5.2 监控规则（每次检查）

| 条件 | 动作 |
|------|------|
| 水冷流量 < 2 L/min | 报警：可能管道堵塞 |
| 水冷温度偏离目标 > 2°C | 报警：温度异常 |
| 探测器 FPGA 温度 > 60°C | 报警：探测器过热 |
| 探测器 FPGA 温度 > 70°C | 紧急：建议立即停止实验 |
| 位移台异常停止 | 报警：位移台状态异常 |

### 5.3 运行方式

- 主 Agent 在开始长时间采集前 spawn safety-watcher 作为后台任务
- 每 30 秒执行一轮检查
- 发现异常时向主 Agent 发送通知
- 采集完成后主 Agent 终止 safety-watcher

---

## 6. B/C 模式策略

| 场景 | 默认模式 | 行为 |
|------|---------|------|
| 日常标准实验 | C（全自动） | 降温→采集→分析，全程自动 |
| **基线→信号切换** | **B（强制）** | X 光机未接入控制，必须人工确认 |
| 用户说"每一步确认" | B（手动切换） | 所有关键操作前暂停 |
| 调试/首次使用 | B（手动切换） | 用户想逐步观察 |
| 夜间批量实验 | C（全自动） | 完整脚本化执行 |

---

## 7. 与现有 Skill 的对比

| 维度 | 旧 Skill | 新 Skill |
|------|---------|---------|
| 执行机制 | Markdown 里写死 curl 命令 | 调用类型安全的 Python Tool |
| 状态感知 | 无，每次 curl 独立执行 | Tool 可获取设备状态，Agent 据此推理 |
| 工作流 | 无，只能单步操作 | 结构化工作流模板，Agent 自主编排 |
| 安全联锁 | 无，依赖 Agent 推理（可能忘记） | Tool 层硬编码 + safety-watcher 双重保障 |
| 错误处理 | 返回原始 JSON | 人类可读诊断 + 可操作建议 |
| 数据解读 | 无 | Agent 解读增益图、噪声峰、拟合结果 |

---

## 8. 实现阶段（2 天计划）

### Day 1 上午：基础设施 + 系统启停 + Chiller Tools
- [ ] 创建 Plugin 骨架（plugin.json + 目录结构）
- [ ] 实现 `system_check` + `system_startup` + `system_shutdown`（一键启动后端+前端）
- [ ] 实现 `system_health_check` 打通 Tool→API→OpenHarness 链路
- [ ] 7 个 Chiller Tools（get_status、set_temperature、start/stop、wait_stable 等）
- [ ] **里程碑 1**：打开 OpenHarness → "启动实验系统" → 后端前端自动运行 → "查看水冷状态"得到正确响应

### Day 1 下午：Detector Tools + 后端补充
- [ ] 后端补充：在 router.py 新增 `POST /api/detector/mode`（~6 行）
- [ ] 13 个 Detector Tools（load_config、set_mode、set_param、run_acquisition、shutdown 等）
- [ ] `detector_run_acquisition` 完整实现（含安全联锁逻辑）
- [ ] **里程碑 2**：能通过 Agent 完成一次完整的"加载配置→设模式→设参数→采集→处理结果"

### Day 2 上午：Stage Tools + Processing Tools + Skills
- [ ] 6 个 Stage Tools（get_status、move、scan 等）
- [ ] 7 个 Processing Tools（fit_pixel、compute_gainmap、analyze_acquisition 等）
- [ ] 编写 3 个 SKILL.md（experiment-control、safety-rules、troubleshooting）
- [ ] 替换旧的 experiment-control skill
- [ ] **里程碑 3**：Agent 能按完整工作流执行降温→基线采集→询问 X 光→信号采集→自动分析

### Day 2 下午：Safety-Watcher + 端到端测试 + 修复
- [ ] 编写 safety-watcher.md，验证后台监控触发
- [ ] 端到端测试：完整实验流程（使用 Chiller 模拟模式）
- [ ] 安全场景测试：温度超限被拒绝、流量 < 2 L/min 报警、FPGA 过热报警
- [ ] X 光联锁测试：基线→信号暂停确认，纯基线不询问
- [ ] 根据测试结果修复问题
- [ ] **里程碑 4**：全流程可运行，安全规则生效
