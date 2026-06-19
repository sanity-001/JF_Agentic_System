# 探测器实验 Agent 助手 — 测试计划

> 对应实现计划 4 个 Phase，每个 Phase 完成后执行对应测试

---

## Phase 1：基础设施 + 系统启停 + Chiller Tools

> **里程碑 1**：打开 OpenHarness → "启动实验系统" → 后端前端自动运行 → "查看水冷状态"得到正确响应

### 1.1 目录结构检查

```bash
# 确认所有目录已创建
ls OpenHarness/.openharness/plugins/experiment-control/plugin.json
ls OpenHarness/.openharness/plugins/experiment-control/tools/__init__.py
ls OpenHarness/.openharness/plugins/experiment-control/tools/system_tools.py
ls OpenHarness/.openharness/plugins/experiment-control/tools/chiller_tools.py
ls OpenHarness/.openharness/plugins/experiment-control/skills/experiment-control/
ls OpenHarness/.openharness/plugins/experiment-control/skills/safety-rules/
ls OpenHarness/.openharness/plugins/experiment-control/skills/troubleshooting/
ls OpenHarness/.openharness/plugins/experiment-control/agents/
```

预期：所有路径存在。

### 1.2 system_check 测试

```bash
# 先手动启动后端（Chiller 使用模拟模式）
cd JF_Control_System
conda run -n slsdet9 python run.py &

# 在 OpenHarness 中测试
cd ../OpenHarness
uv run oh -p "检查系统状态"
```

预期：Agent 调用 `system_check`，返回类似 "⚠️ backend: 在线 | frontend: 离线"。

### 1.3 system_startup 测试

```bash
# 先停掉手动启动的后端，然后：
uv run oh -p "启动实验系统"
```

预期：Agent 调用 `system_startup`，30s 内输出 "✅ 系统已就绪 (后端 :8000, 前端 :5173)"。

### 1.4 system_shutdown 测试

```bash
uv run oh -p "停止系统"
```

预期：Agent 调用 `system_shutdown`，后端和前端进程终止。

### 1.5 Chiller Tools 测试

```bash
# 确保后端运行中（通过 system_startup 启动或手动启动）

# 测试 1：查看水冷状态
uv run oh -p "查看水冷机状态"
# 预期: Agent 调用 chiller_get_status，返回温度、流量、运行时间

# 测试 2：查看水冷参数
uv run oh -p "查看水冷机参数"
# 预期: Agent 调用 chiller_get_params，返回 PID、报警温度等

# 测试 3：设置温度（正常值）
uv run oh -p "设置水冷温度为20度"
# 预期: Agent 调用 chiller_set_temperature(20)，返回成功

# 测试 4：设置温度（超限值 — 安全测试）
uv run oh -p "设置水冷温度为30度"
# 预期: Agent 拒绝或 Tool 返回校验错误（30 > 25）

# 测试 5：设置温度（下限超限）
uv run oh -p "设置水冷温度为10度"
# 预期: Agent 拒绝（10 < 15）

# 测试 6：设定温度并等待稳定（仅模拟模式有效）
uv run oh -p "设定水温到20度然后等待温度稳定"
# 预期: Agent 调用 set_temperature → wait_stable，等待稳定后汇报

# 测试 7：启停水冷机
uv run oh -p "启动水冷机"
# 预期: chiller_start 返回成功
uv run oh -p "停止水冷机"
# 预期: chiller_stop 返回成功
```

### 1.6 提交检查

```bash
git log --oneline | grep phase1
```

预期：存在 `feat(phase1): ...` 提交。

---

## Phase 2：Detector Tools + 后端 /mode

> **里程碑 2**：能通过 Agent 完成一次完整的"加载配置→设模式→设参数→采集→处理结果"

### 2.1 后端 /mode 接口测试

```bash
# 测试设置 baseline 模式
curl -s -X POST http://localhost:8000/api/detector/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "baseline"}'
# 预期: {"success": true, "message": "Mode set to baseline"}

# 测试设置 signal 模式
curl -s -X POST http://localhost:8000/api/detector/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "signal"}'
# 预期: {"success": true, "message": "Mode set to signal"}

# 测试无效模式
curl -s -X POST http://localhost:8000/api/detector/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "invalid"}'
# 预期: HTTP 400 错误
```

### 2.2 Detector 细粒度工具测试

```bash
# 测试 1：加载配置文件（需要准备一个实际的 .config 文件）
uv run oh -p "加载探测器配置 /path/to/your/config.config"
# 预期: Agent 调用 detector_load_config，返回连接成功

# 测试 2：查看探测器状态
uv run oh -p "查看探测器状态"
# 预期: Agent 调用 detector_get_status

# 测试 3：查看探测器参数
uv run oh -p "查看探测器参数"
# 预期: Agent 调用 detector_get_params

# 测试 4：查看探测器温度
uv run oh -p "查看探测器温度"
# 预期: Agent 调用 detector_get_temperatures

# 测试 5：设置采集模式
uv run oh -p "设置采集模式为baseline"
# 预期: Agent 调用 detector_set_mode("baseline")

# 测试 6：设置采集参数
uv run oh -p "设置探测器曝光时间为500"
# 预期: Agent 调用 detector_set_param("exptime", "500")

uv run oh -p "设置探测器帧数为200"
# 预期: Agent 调用 detector_set_param("frames", "200")
```

### 2.3 Detector 安全联锁测试

```bash
# 测试：信号模式 + 水冷未启动 → 应被拒绝
# 先确保水冷已停止，然后：
uv run oh -p "用配置文件 test.config 采集信号，曝光时间500，帧数100"
# 预期: detector_run_acquisition 安全联锁拒绝，提示"水冷机未运行"

# 测试：信号模式 + 温度超限 → 应被拒绝
# 启动水冷，设置温度为 30°C 超限...（Tool 层会拒绝设温）
# 或者：启动水冷后，等待温度超出 [15,25] 范围，然后：
uv run oh -p "用配置文件 test.config 采集信号"
# 预期: 安全联锁拒绝，提示温度超出安全范围
```

### 2.4 不存在的配置文件测试

```bash
uv run oh -p "加载配置文件 /nonexistent/path/fake.config"
# 预期: detector_load_config 返回错误，Agent 友好提示
```

### 2.5 提交检查

```bash
git log --oneline | grep phase2
```

预期：存在 `feat(phase2): ...` 提交。

---

## Phase 3：Stage + Processing Tools + Skills

> **里程碑 3**：Agent 能按完整工作流执行降温→基线采集→询问 X 光→信号采集→自动分析

### 3.1 Stage Tools 测试

```bash
# 测试 1：查看位移台状态
uv run oh -p "查看位移台状态"
# 预期: Agent 调用 stage_get_status

# 测试 2：回原点
uv run oh -p "位移台回原点"
# 预期: Agent 调用 stage_origin_return

# 测试 3：绝对移动
uv run oh -p "移动位移台到位置100"
# 预期: Agent 调用 stage_move_absolute(axis=1, position=100)

# 测试 4：相对移动
uv run oh -p "位移台相对移动10"
# 预期: Agent 调用 stage_move_relative(offset=10)

# 测试 5：紧急停止
uv run oh -p "紧急停止位移台"
# 预期: Agent 调用 stage_stop
```

### 3.2 Processing Tools 测试

```bash
# 测试 1：读取单帧（需要实际 raw 文件）
uv run oh -p "读取 /path/to/test.raw 文件的第 0 帧"
# 预期: Agent 调用 processing_read_frame，返回帧统计信息

# 测试 2：计算平均帧
uv run oh -p "计算 test.raw 文件前100帧的平均帧"
# 预期: Agent 调用 processing_average_frames

# 测试 3：单像素拟合
uv run oh -p "对 test.raw 文件的像素 (300, 300) 做高斯拟合，帧范围 0-100"
# 预期: Agent 调用 processing_fit_pixel，返回 Gain、噪声峰、信号峰

# 测试 4：计算增益图
uv run oh -p "计算 test.raw 的增益图，帧范围 0-100"
# 预期: Agent 调用 processing_compute_gainmap，返回统计

# 测试 5：计算噪声峰图
uv run oh -p "计算 test.raw 的噪声峰图"
# 预期: Agent 调用 processing_compute_noisemap

# 测试 6：一键分析
uv run oh -p "对 test.raw 做一键分析，基线文件 baseline.raw"
# 预期: Agent 调用 processing_analyze_acquisition，返回平均帧+增益图+噪声峰图摘要
```

### 3.3 完整工作流测试（C 模式 + B 模式 X 光联锁）

```bash
# C 模式：纯基线采集（不询问 X 光）
uv run oh -p "启动系统，把水冷温度设为20度，等温度稳定后，用 my_config.config 做基线采集，exptime=500, frames=100"
# 预期:
# 1. system_startup
# 2. chiller_set_temperature(20)
# 3. chiller_wait_stable(20) — 模拟模式温度会逐渐变化
# 4. detector_load_config
# 5. detector_set_mode("baseline")
# 6. detector_run_acquisition(mode="baseline")
# 7. 完成（纯基线不询问 X 光）

# B+C 混合：基线+信号采集（基线后强制暂停确认 X 光）
uv run oh -p "在20度下做一次完整的基线和信号采集，配置文件 my_config.config"
# 预期:
# 1. 降温+稳定 → 加载配置 → 基线采集完成
# 2. ⚠️ Agent 暂停："基线采集完成。请确认已开启 X 光机"
# 3. 用户回复"已开启" → 继续信号采集
# 4. 信号采集完成 → 自动分析
```

### 3.4 Skill 加载验证

```bash
# 检查 experiment-control skill 是否被 OpenHarness 发现
cd OpenHarness
uv run oh --dry-run -p "采集数据" 2>&1 | grep -i "experiment-control"
# 预期: 输出中包含 experiment-control skill 信息
```

### 3.5 提交检查

```bash
git log --oneline | grep phase3
```

预期：存在 `feat(phase3): ...` 提交。

---

## Phase 4：Safety-Watcher + 端到端测试 + 修复

> **里程碑 4**：全流程可运行，安全规则生效

### 4.1 Safety-Watcher 文件验证

```bash
# 检查文件存在
cat OpenHarness/.openharness/plugins/experiment-control/agents/safety-watcher.md

# 验证 frontmatter
head -10 OpenHarness/.openharness/plugins/experiment-control/agents/safety-watcher.md
```

预期：包含 `background: true`、`max_turns: 1`、`color: red`、4 个只读工具。

### 4.2 安全规则覆盖测试

#### 4.2.1 温度超限拒绝
```bash
uv run oh -p "把水冷温度设为30度"
# 预期: 被拒绝（18 > 25）
```

#### 4.2.2 信号采集 + 水冷未启动
```bash
uv run oh -p "不启动水冷，直接用 my_config.config 采集信号，exptime=500"
# 预期: detector_run_acquisition 安全联锁拒绝
```

#### 4.2.3 流量异常报警（检查 safety-rules skill 内容）
```bash
# 验证 safety-rules SKILL.md 中流量阈值
grep "2 L/min" OpenHarness/.openharness/plugins/experiment-control/skills/safety-rules/SKILL.md
# 预期: 流量 < 2 L/min → 报警
```

#### 4.2.4 FPGA 温度报警（检查 safety-watcher）
```bash
grep "60°C\|70°C" OpenHarness/.openharness/plugins/experiment-control/agents/safety-watcher.md
# 预期: > 60°C 报警，> 70°C 紧急
```

### 4.3 X 光联锁测试

#### 4.3.1 基线采集 → 不询问 X 光
```bash
uv run oh -p "在20度下只做基线采集，配置文件 my_config.config"
# 预期: 直接完成，不询问 X 光
```

#### 4.3.2 纯信号采集（基线已有）→ 询问 X 光
```bash
uv run oh -p "基线已经有了，在20度下直接采集信号，配置文件 my_config.config"
# 预期: ⚠️ Agent 先询问"请确认 X 光机已开启" → 用户确认后继续
```

#### 4.3.3 基线+信号完整流程 → 基线后暂停
```bash
uv run oh -p "做一次完整的基线和信号采集，20度，配置文件 my_config.config"
# 预期: 基线完成后暂停 → 询问 X 光 → 确认后采集信号
```

### 4.4 错误恢复测试

```bash
# 不存在的配置文件
uv run oh -p "加载配置文件 /nonexistent/fake.config 然后采集基线"
# 预期: load_config 返回错误 → Agent 友好提示，不崩溃

# 未连接时采集
uv run oh -p "不加载配置，直接开始采集"
# 预期: Agent 提示需要先加载配置
```

### 4.5 B/C 模式行为测试

```bash
# C 模式：完整参数 → 自动执行
uv run oh -p "在20°C下用 my_config.config 采集基线，exptime=500, frames=200"
# 预期: 全程自动，不暂停（纯基线无 X 光步骤）

# B 模式：用户说"每一步确认"
uv run oh -p "每一步都确认一下——在20°C下用 my_config.config 采集基线"
# 预期: 每个关键操作前暂停询问
```

### 4.6 完整端到端流程

```bash
uv run oh -p "从零开始做一次完整实验：启动系统，水冷设到20度，等温度稳定，加载 my_config.config，采集基线（exptime=500, frames=200），然后做信号采集，最后分析结果"
# 预期全流程:
# system_startup → chiller_set_temperature(20) → chiller_wait_stable(20)
# → detector_load_config → detector_set_mode("baseline")
# → detector_run_acquisition(baseline) → X 光确认暂停
# → detector_set_mode("signal") → detector_run_acquisition(signal)
# → processing_analyze_acquisition → 总结汇报
```

### 4.7 提交检查

```bash
git log --oneline | grep phase4
```

预期：存在 `feat(phase4): ...` 提交。

---

## 测试环境准备

| 条件 | 说明 |
|------|------|
| Conda 环境 | `slsdet9` 已安装并激活 |
| 后端依赖 | `pip install -r JF_Control_System/requirements.txt` |
| OpenHarness | `uv sync --extra dev` 已完成 |
| 水冷模拟模式 | Chiller Service 默认 `simulation=True` |
| 探测器配置文件 | 准备一个有效的 `.config` 文件用于测试 |
| Raw 测试数据 | 准备 `.raw` 文件用于 Processing Tools 测试 |

## 注意事项

- Chiller 模拟模式不需要实际硬件，温度会随设定逐渐变化
- Detector 采集需要实际硬件或 slsDet 库支持
- Processing Tools 需要实际的 `.raw` 数据文件才能返回有意义的结果
- `conda run -n slsdet9` 需要 conda 在 PATH 中
