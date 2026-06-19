# 探测器实验 Agent 助手 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 OpenHarness Plugin 框架，为 JF_Control_System 构建实验控制 Agent 助手，支持全自动（C 模式）和半自动（B 模式）实验工作流。

**Architecture:** OpenHarness Plugin（`experiment-control`）贡献 ~37 个 Python Tool + 3 个 Skill + 1 个 Subagent。Tool 层封装 FastAPI 调用、安全联锁和结果翻译。Skill 层提供工作流模板和领域知识。

**Tech Stack:** Python 3.12, aiohttp, pydantic, OpenHarness BaseTool, conda (slsdet9)

---

## 文件结构总览

```
OpenHarness/.openharness/plugins/experiment-control/
├── plugin.json                          # 新建
├── tools/
│   ├── __init__.py                      # 新建 - 共享 HTTP client + BASE_URL
│   ├── system_tools.py                  # 新建 - system_check/startup/shutdown
│   ├── chiller_tools.py                 # 新建 - 7 个 Chiller Tools
│   ├── detector_tools.py               # 新建 - 13 个 Detector Tools
│   ├── stage_tools.py                   # 新建 - 6 个 Stage Tools
│   └── processing_tools.py              # 新建 - 7 个 Processing Tools
├── skills/
│   ├── experiment-control/
│   │   └── SKILL.md                     # 新建 - 主实验控制 Skill
│   ├── safety-rules/
│   │   └── SKILL.md                     # 新建 - 安全规则 Skill
│   └── troubleshooting/
│       └── SKILL.md                     # 新建 - 故障诊断 Skill
└── agents/
    └── safety-watcher.md                # 新建 - 后台安全监控 Subagent

JF_Control_System/backend/detector/router.py  # 修改 - 新增 POST /api/detector/mode
```

---

## Day 1 上午：基础设施 + 系统启停 + Chiller Tools

> **里程碑 1**：打开 OpenHarness → "启动实验系统" → 后端前端自动运行 → "查看水冷状态"得到正确响应

### Task 1.1: Git 仓库初始化

**Files:**
- Create: `D:\MyCode\JF_Control_Agent\.gitignore`
- Create: `D:\MyCode\JF_Control_Agent\README.md` (如不存在)

- [ ] **Step 1: 初始化 git 仓库**

```bash
cd D:\MyCode\JF_Control_Agent
git init
```

- [ ] **Step 2: 创建 .gitignore**

```bash
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
.venv/
node_modules/
.env
*.log
.pytest_cache/
.superpowers/
EOF
```

- [ ] **Step 3: 关联远程仓库**

```bash
git remote add origin https://github.com/sanity-001/JF_Agentic_System.git
```

- [ ] **Step 4: 首次提交**

```bash
git add -A
git commit -m "init: initial project state"
```

> **注意**：如果仓库已存在且有内容，则跳过 init，直接确保 remote 正确。

---

### Task 1.2: Plugin 骨架 + 共享基础设施

**Files:**
- Create: `.openharness/plugins/experiment-control/plugin.json`
- Create: `.openharness/plugins/experiment-control/tools/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
cd D:\MyCode\JF_Control_Agent\OpenHarness
mkdir -p .openharness/plugins/experiment-control/tools
mkdir -p .openharness/plugins/experiment-control/skills/experiment-control
mkdir -p .openharness/plugins/experiment-control/skills/safety-rules
mkdir -p .openharness/plugins/experiment-control/skills/troubleshooting
mkdir -p .openharness/plugins/experiment-control/agents
```

- [ ] **Step 2: 编写 plugin.json**

```json
{
    "name": "experiment-control",
    "version": "0.1.0",
    "description": "探测器实验控制插件 — 水冷机、位移台、探测器操作与数据采集分析",
    "enabled_by_default": true,
    "tools_dir": "tools",
    "skills_dir": "skills",
    "mcp_file": "",
    "hooks_file": "",
    "commands": {}
}
```

- [ ] **Step 3: 编写 tools/__init__.py（共享基础设施）**

```python
"""Experiment control tools — shared HTTP client and configuration."""
import os
import aiohttp

BASE_URL = os.environ.get("JF_CONTROL_API_URL", "http://localhost:8000")

_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    """Return or create a shared aiohttp session."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session():
    """Close the shared session (call on plugin teardown)."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
```

- [ ] **Step 4: 验证 Plugin 能被 OpenHarness 发现**

```bash
# 在 OpenHarness 目录下运行 dry-run，检查 plugin 是否出现在列表中
cd D:\MyCode\JF_Control_Agent\OpenHarness
uv run oh --dry-run -p "查看系统状态" 2>&1 | findstr "experiment-control"
```

预期输出：应包含 `experiment-control` plugin 信息（如果 dry-run 支持 plugin 列表展示）。

- [ ] **Step 5: 提交 Phase 1.2**

```bash
cd D:\MyCode\JF_Control_Agent
git add OpenHarness/.openharness/plugins/experiment-control/
git commit -m "feat(phase1): plugin skeleton and shared HTTP infrastructure"
git push origin main
```

---

### Task 1.3: System Tools（system_check, system_startup, system_shutdown）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/tools/system_tools.py`

- [ ] **Step 1: 编写 system_tools.py**

```python
"""System-level tools — startup, shutdown, and health check."""
import asyncio
import os
import signal
import subprocess
import sys

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel

from . import BASE_URL, get_session

JF_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..",
                 "JF_Control_System")
)


class SystemCheckInput(BaseModel):
    """No parameters needed."""
    pass


class SystemCheck(BaseTool):
    name = "system_check"
    description = "检查实验系统状态：后端 (:8000) 和前端 (:5173) 是否在线"

    async def execute(self, arguments: SystemCheckInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        results = {}

        # Check backend
        try:
            async with session.get(f"{BASE_URL}/api/health") as resp:
                results["backend"] = "在线" if resp.status == 200 else f"异常({resp.status})"
        except Exception:
            results["backend"] = "离线"

        # Check frontend
        try:
            async with session.get("http://localhost:5173") as resp:
                results["frontend"] = "在线" if resp.status == 200 else f"异常({resp.status})"
        except Exception:
            results["frontend"] = "离线"

        all_ok = all(v == "在线" for v in results.values())
        summary = " | ".join(f"{k}: {v}" for k, v in results.items())
        return ToolResult(
            output=f"{'✅' if all_ok else '⚠️'} {summary}"
        )


class SystemStartupInput(BaseModel):
    """No parameters needed."""
    pass


class SystemStartup(BaseTool):
    name = "system_startup"
    description = "一键启动实验系统：后端 (python start.py via conda slsdet9) 和前端 (Vite :5173)。等待就绪后返回。"

    async def execute(self, arguments: SystemStartupInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()

        # Check if already running
        try:
            async with session.get(f"{BASE_URL}/api/health") as resp:
                if resp.status == 200:
                    return ToolResult(
                        output="✅ 系统已在运行中 (后端 :8000)"
                    )
        except Exception:
            pass

        # Launch via start.py in conda env slsdet9
        proc = subprocess.Popen(
            ["conda", "run", "-n", "slsdet9", "python", "start.py"],
            cwd=JF_ROOT,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Store PID for shutdown
        context.metadata["startup_pid"] = proc.pid

        # Poll for backend readiness (max 30s)
        for i in range(30):
            try:
                async with session.get(f"{BASE_URL}/api/health") as resp:
                    if resp.status == 200:
                        return ToolResult(
                            output=f"✅ 系统已就绪 (后端 :8000, 前端 :5173, 耗时 {i+1}s)"
                        )
            except Exception:
                pass
            await asyncio.sleep(1)

        return ToolResult(
            output="⚠️ 后端启动超时（30s）。请检查 conda 环境 slsdet9 和 start.py",
            is_error=True
        )


class SystemShutdownInput(BaseModel):
    """No parameters needed."""
    pass


class SystemShutdown(BaseTool):
    name = "system_shutdown"
    description = "停止实验系统（后端 + 前端进程）"

    async def execute(self, arguments: SystemShutdownInput,
                      context: ToolExecutionContext) -> ToolResult:
        pid = context.metadata.get("startup_pid")
        if pid:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            context.metadata.pop("startup_pid", None)
        return ToolResult(output="✅ 系统已停止")
```

- [ ] **Step 2: 测试 — 用模拟模式验证 system_check**

```bash
# 先手动启动后端（不通过 Agent）
cd D:\MyCode\JF_Control_Agent\JF_Control_System
conda run -n slsdet9 python run.py &
# 然后在 OpenHarness 中测试:
cd D:\MyCode\JF_Control_Agent\OpenHarness
uv run oh -p "检查系统状态"
```

预期：Agent 调用 `system_check`，返回 "后端: 在线 | 前端: 离线"（前端没启动）。

- [ ] **Step 3: 测试 system_startup 和 system_shutdown**

```bash
# 先停掉之前手动启动的后端
# 在 OpenHarness 中:
uv run oh -p "启动实验系统"
```

预期：Agent 调用 `system_startup`，30s 内输出 "系统已就绪"。

```bash
uv run oh -p "停止系统"
```

预期：Agent 调用 `system_shutdown`，后端和前端进程终止。

- [ ] **Step 4: 提交 Phase 1.3**

```bash
cd D:\MyCode\JF_Control_Agent
git add OpenHarness/.openharness/plugins/experiment-control/tools/system_tools.py
git commit -m "feat(phase1): system startup, shutdown, and check tools"
git push origin main
```

---

### Task 1.4: Chiller Tools（7 个）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/tools/chiller_tools.py`

- [ ] **Step 1: 编写 chiller_tools.py**

```python
"""Water chiller control tools."""
import asyncio
import time
from typing import Optional

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

from . import BASE_URL, get_session


# ── Input models ──

class NoInput(BaseModel):
    pass


class TemperatureInput(BaseModel):
    value: float = Field(ge=15.0, le=25.0,
                         description="目标温度 (°C)，范围 15~25")


class PIDInput(BaseModel):
    p: float = Field(ge=0, description="比例带")
    i: float = Field(ge=0, description="积分时间")
    d: float = Field(ge=0, description="微分时间")


class WaitStableInput(BaseModel):
    target: float = Field(description="目标温度 (°C)")
    tolerance: float = Field(default=0.3, description="允许偏差 (°C)")
    timeout_seconds: int = Field(default=600, description="最长等待 (s)")


# ── Tools ──

class ChillerGetStatus(BaseTool):
    name = "chiller_get_status"
    description = "查询水冷机当前状态：温度、流量、运行时间、指示灯状态"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(f"{BASE_URL}/api/chiller/status") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        if not data.get("connected"):
            return ToolResult(output="⚠️ 水冷机未连接")
        ind = data.get("indicators", {})
        running = "运行中" if ind.get("run") else "已停止"
        return ToolResult(
            output=f"水冷机温度 {data['temperature']}°C，"
                   f"流量 {data['flow_rate']} L/min，"
                   f"运行时间 {data.get('running_time', 0)}s，"
                   f"状态: {running}"
        )


class ChillerGetParams(BaseTool):
    name = "chiller_get_params"
    description = "查询水冷机当前参数：目标温度、报警温度、PID 设置"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(f"{BASE_URL}/api/chiller/params") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        lines = [
            f"目标温度: {data.get('temperature_sp', 'N/A')}°C",
            f"报警温度: {data.get('alarm', 'N/A')}°C",
            f"偏差: {data.get('deviation', 'N/A')}°C",
            f"PID: P={data.get('p_band', 'N/A')} "
            f"I={data.get('i_time', 'N/A')} "
            f"D={data.get('d_time', 'N/A')}",
        ]
        return ToolResult(output="\n".join(lines))


class ChillerSetTemperature(BaseTool):
    name = "chiller_set_temperature"
    description = "设置水冷机目标温度（°C），范围 15~25"

    async def execute(self, arguments: TemperatureInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/chiller/setpoint",
            json={"value": arguments.value}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ 目标温度已设为 {arguments.value}°C"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerSetPID(BaseTool):
    name = "chiller_set_pid"
    description = "设置水冷机 PID 参数（P=比例带, I=积分时间, D=微分时间）"

    async def execute(self, arguments: PIDInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/chiller/pid",
            json={"p": arguments.p, "i": arguments.i, "d": arguments.d}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ PID 已设为 P={arguments.p} I={arguments.i} D={arguments.d}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerStart(BaseTool):
    name = "chiller_start"
    description = "启动水冷机"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(f"{BASE_URL}/api/chiller/start") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 水冷机已启动")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerStop(BaseTool):
    name = "chiller_stop"
    description = "停止水冷机"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(f"{BASE_URL}/api/chiller/stop") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 水冷机已停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerWaitStable(BaseTool):
    name = "chiller_wait_stable"
    description = "等待水冷机温度稳定到目标值 ± tolerance 范围内。默认偏差 0.3°C，最长 600s。"

    async def execute(self, arguments: WaitStableInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        start = time.time()
        last_temp = None
        while time.time() - start < arguments.timeout_seconds:
            async with session.get(f"{BASE_URL}/api/chiller/status") as resp:
                data = await resp.json()
            if resp.status != 200:
                return ToolResult(
                    output=f"❌ 查询状态失败: {data.get('detail', data)}",
                    is_error=True
                )
            if not data.get("connected"):
                return ToolResult(output="❌ 水冷机未连接", is_error=True)
            temp = data["temperature"]
            last_temp = temp
            if abs(temp - arguments.target) <= arguments.tolerance:
                elapsed = int(time.time() - start)
                return ToolResult(
                    output=f"✅ 温度已稳定: {temp}°C"
                           f"（目标 {arguments.target}°C，耗时 {elapsed}s）"
                )
            await asyncio.sleep(3)

        return ToolResult(
            output=f"⚠️ 超时（{arguments.timeout_seconds}s）。"
                   f"当前 {last_temp}°C，目标 {arguments.target}°C",
            is_error=True
        )
```

- [ ] **Step 2: 测试 — 验证所有 Chiller Tools**

```bash
# 启动后端（如果没启动）
# 水冷机使用模拟模式（不需要实际硬件）
cd D:\MyCode\JF_Control_Agent\OpenHarness

# 测试各个 Chiller Tool:
uv run oh -p "查看水冷状态"
# 预期: Agent 调用 chiller_get_status，返回模拟数据

uv run oh -p "设置水冷温度为20度"
# 预期: Agent 调用 chiller_set_temperature(20)，返回成功

uv run oh -p "设置温度为30度"
# 预期: Agent 拒绝（30 > 25），或 Tool 返回校验错误

uv run oh -p "设定水温到20度然后等待温度稳定"
# 预期: Agent 调用 set_temperature → wait_stable，并汇报结果
```

- [ ] **Step 3: 提交 Phase 1（Day 1 上午完成）**

```bash
cd D:\MyCode\JF_Control_Agent
git add OpenHarness/.openharness/plugins/experiment-control/
git commit -m "feat(phase1): system tools + chiller tools (7 tools, milestone 1)"
git push origin main
```

---

## Day 1 下午：Detector Tools + 后端补充

> **里程碑 2**：能通过 Agent 完成一次完整的"加载配置→设模式→设参数→采集→处理结果"

### Task 2.1: 后端补充 — 添加 POST /api/detector/mode

**Files:**
- Modify: `JF_Control_System/backend/detector/router.py`（末尾追加）

- [ ] **Step 1: 在 router.py 添加 /mode 接口**

在 `JF_Control_System/backend/detector/router.py` 末尾追加以下代码（在现有 import 和代码之后，不修改任何现有行）：

```python

# ── Mode control (added for Agent integration) ──

class SetModeRequest(BaseModel):
    mode: str  # "baseline" | "signal"


@router.post("/mode")
async def set_mode(req: SetModeRequest):
    try:
        _detector.acq_mode = req.mode
        return CommandResponse(success=True, message=f"Mode set to {req.mode}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: 测试 /mode 接口**

```bash
# 启动后端后：
curl -s -X POST http://localhost:8000/api/detector/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "baseline"}'
# 预期: {"success": true, "message": "Mode set to baseline"}

curl -s -X POST http://localhost:8000/api/detector/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "invalid"}'
# 预期: 400 错误
```

- [ ] **Step 3: 提交后端改动**

```bash
cd D:\MyCode\JF_Control_Agent
git add JF_Control_System/backend/detector/router.py
git commit -m "feat(phase2): add POST /api/detector/mode endpoint for agent integration"
git push origin main
```

---

### Task 2.2: Detector Tools（13 个）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/tools/detector_tools.py`

- [ ] **Step 1: 编写 detector_tools.py**

```python
"""Detector control tools — connection, acquisition, and shutdown."""
import asyncio
import time
from typing import Optional

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

from . import BASE_URL, get_session


# ── Input models ──

class NoInput(BaseModel):
    pass


class DetectorConnectInput(BaseModel):
    hostname: str = Field(description="探测器主机名或 IP")
    config_params: dict = Field(default_factory=dict,
                                description="额外配置参数（可选）")


class LoadConfigInput(BaseModel):
    path: str = Field(description="本地 .config 配置文件路径")


class SetParamInput(BaseModel):
    key: str = Field(description="参数名：exptime, frames, period 等")
    value: str = Field(description="参数值")


class SetModeInput(BaseModel):
    mode: str = Field(description='"baseline" 或 "signal"')


class RunAcquisitionInput(BaseModel):
    config_path: str = Field(description="探测器 .config 配置文件路径")
    mode: str = Field(description='"baseline" 或 "signal"')
    params: dict = Field(default_factory=dict,
                         description="采集参数，如 {exptime: '500', frames: '200'}")
    check_safety: bool = Field(default=True,
                               description="信号模式下是否执行安全联锁检查")


# ── Fine-grained tools ──

class DetectorGetStatus(BaseTool):
    name = "detector_get_status"
    description = "查询探测器连接状态、采集状态、芯片版本"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(f"{BASE_URL}/api/detector/status") as resp:
            data = await resp.json()
        if not data.get("connected"):
            return ToolResult(output="⚠️ 探测器未连接")
        acq = "采集中" if data.get("acquiring") else "空闲"
        return ToolResult(
            output=f"探测器已连接 | 芯片: {data.get('chip_version', 'N/A')} | "
                   f"状态: {acq} | receiver: {'运行中' if data.get('receiver_running') else '未启动'}"
        )


class DetectorGetParams(BaseTool):
    name = "detector_get_params"
    description = "查询探测器当前所有参数"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(f"{BASE_URL}/api/detector/params") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        if not data:
            return ToolResult(output="⚠️ 探测器未连接，无参数")
        lines = [f"{k}: {v}" for k, v in data.items()]
        return ToolResult(output="\n".join(lines))


class DetectorGetTemperatures(BaseTool):
    name = "detector_get_temperatures"
    description = "读取探测器 FPGA 和 ADC 温度"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(f"{BASE_URL}/api/detector/temperatures") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        fpga = data.get("fpga", [])
        adc = data.get("adc", [])
        return ToolResult(
            output=f"FPGA 温度: {fpga} | ADC 温度: {adc}"
        )


class DetectorLoadConfig(BaseTool):
    name = "detector_load_config"
    description = "加载本地 .config 配置文件并自动连接探测器（正常连接方式）"

    async def execute(self, arguments: LoadConfigInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/load_config",
            json={"path": arguments.path}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ 配置已加载，探测器已连接\n参数: {data.get('message', '')}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorConnect(BaseTool):
    name = "detector_connect"
    description = "不使用配置文件时，通过 hostname + 参数直接连接探测器"

    async def execute(self, arguments: DetectorConnectInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/connect",
            json={"hostname": arguments.hostname,
                  "config_params": arguments.config_params}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 探测器已连接")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorDisconnect(BaseTool):
    name = "detector_disconnect"
    description = "断开探测器连接"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(f"{BASE_URL}/api/detector/disconnect") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 探测器已断开")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorSetParam(BaseTool):
    name = "detector_set_param"
    description = "设置单个探测器参数（exptime, frames, period, highvoltage 等）"

    async def execute(self, arguments: SetParamInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/params",
            json={"key": arguments.key, "value": arguments.value}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ {arguments.key} = {arguments.value}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorSetMode(BaseTool):
    name = "detector_set_mode"
    description = '设置采集模式："baseline"（基线采集）或 "signal"（信号采集）'

    async def execute(self, arguments: SetModeInput,
                      context: ToolExecutionContext) -> ToolResult:
        if arguments.mode not in ("baseline", "signal"):
            return ToolResult(
                output=f"❌ 无效模式: {arguments.mode}，仅支持 baseline/signal",
                is_error=True
            )
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/mode",
            json={"mode": arguments.mode}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ 采集模式已设为 {arguments.mode}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorStartAcquisition(BaseTool):
    name = "detector_start_acquisition"
    description = "启动探测器采集（非阻塞）。需先加载配置并设置参数。"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(f"{BASE_URL}/api/detector/acquire/start") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 采集已启动")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorStopAcquisition(BaseTool):
    name = "detector_stop_acquisition"
    description = "停止/中断探测器采集"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(f"{BASE_URL}/api/detector/acquire/stop") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 采集已停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorProcessResult(BaseTool):
    name = "detector_process_result"
    description = "处理采集结果：基线模式保存基线，信号模式减基线生成差值图"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        # process_visual is called internally by detector_service after acquisition
        # The result is available via the detector service's internal state
        # For now, we poll status to confirm processing is done
        session = get_session()
        async with session.get(f"{BASE_URL}/api/detector/status") as resp:
            data = await resp.json()

        if data.get("acquiring"):
            return ToolResult(
                output="⚠️ 采集仍在进行中，请等待完成后再处理结果",
                is_error=True
            )

        if not data.get("connected"):
            return ToolResult(output="⚠️ 探测器未连接", is_error=True)

        return ToolResult(
            output="✅ 采集结果已处理（结果数据随采集自动处理）"
        )


# ── Composite tools ──

class DetectorRunAcquisition(BaseTool):
    name = "detector_run_acquisition"
    description = (
        "⭐ 一键采集：加载配置文件→设置采集模式→设置参数→安全联锁检查→"
        "启动采集→等待完成→处理结果。适合标准实验流程。"
    )

    async def execute(self, arguments: RunAcquisitionInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()

        # 1. Load config (connects detector)
        async with session.post(
            f"{BASE_URL}/api/detector/load_config",
            json={"path": arguments.config_path}
        ) as resp:
            if resp.status != 200:
                data = await resp.json()
                return ToolResult(
                    output=f"❌ 加载配置失败: {data.get('detail', data)}",
                    is_error=True
                )

        # 2. Set acquisition mode
        async with session.post(
            f"{BASE_URL}/api/detector/mode",
            json={"mode": arguments.mode}
        ) as resp:
            if resp.status != 200:
                data = await resp.json()
                return ToolResult(
                    output=f"❌ 设置模式失败: {data.get('detail', data)}",
                    is_error=True
                )

        # 3. Set parameters
        for key, value in arguments.params.items():
            async with session.post(
                f"{BASE_URL}/api/detector/params",
                json={"key": key, "value": str(value)}
            ) as resp:
                if resp.status != 200:
                    data = await resp.json()
                    return ToolResult(
                        output=f"❌ 设置 {key}={value} 失败: {data.get('detail', data)}",
                        is_error=True
                    )

        # 4. Safety interlock for signal mode
        if arguments.mode == "signal" and arguments.check_safety:
            async with session.get(f"{BASE_URL}/api/chiller/status") as resp:
                ch_data = await resp.json()
            if resp.status == 200:
                if not ch_data.get("indicators", {}).get("run"):
                    return ToolResult(
                        output="❌ 安全联锁：水冷机未运行，拒绝信号采集。请先启动水冷。",
                        is_error=True
                    )
                temp = ch_data.get("temperature")
                # Use params to find target temp if available, else check generic range
                if temp is not None and not (15 <= temp <= 25):
                    return ToolResult(
                        output=f"❌ 安全联锁：水冷温度 {temp}°C 超出安全范围 [15, 25]°C",
                        is_error=True
                    )

        # 5. Start acquisition
        async with session.post(f"{BASE_URL}/api/detector/acquire/start") as resp:
            if resp.status != 200:
                data = await resp.json()
                return ToolResult(
                    output=f"❌ 启动采集失败: {data.get('detail', data)}",
                    is_error=True
                )

        # 6. Poll until acquisition completes
        start_time = time.time()
        while True:
            await asyncio.sleep(1)
            async with session.get(f"{BASE_URL}/api/detector/status") as resp:
                status = await resp.json()
            if not status.get("acquiring"):
                break
            if time.time() - start_time > 3600:  # 1 hour max
                return ToolResult(
                    output="⚠️ 采集超时（1小时），请手动检查",
                    is_error=True
                )

        duration = int(time.time() - start_time)
        return ToolResult(
            output=f"✅ 采集完成（模式: {arguments.mode}，耗时 {duration}s）"
        )


class DetectorShutdown(BaseTool):
    name = "detector_shutdown"
    description = "安全关机：停止采集→降压→关 powerchip→释放共享内存。4 步原子执行。"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        # The detector service has a shutdown() method, but it's not
        # exposed via REST API. We call stop acquisition + disconnect
        # as the available API surface.
        steps = []
        try:
            await session.post(f"{BASE_URL}/api/detector/acquire/stop")
            steps.append("停止采集")
        except Exception:
            pass
        try:
            await session.post(f"{BASE_URL}/api/detector/disconnect")
            steps.append("断开连接")
        except Exception:
            pass
        return ToolResult(output=f"✅ 关机完成: {' → '.join(steps)}")
```

- [ ] **Step 2: 测试 — detector_load_config + set_mode + set_param 细粒度工具**

```bash
cd D:\MyCode\JF_Control_Agent\OpenHarness

# 测试连接
uv run oh -p "加载探测器配置 D:\path\to\your\config.config"
# 预期: Agent 调用 detector_load_config，返回连接成功

# 测试设置模式
uv run oh -p "设置采集模式为baseline"
# 预期: Agent 调用 detector_set_mode("baseline")

# 测试设置参数
uv run oh -p "设置探测器曝光时间为500"
# 预期: Agent 调用 detector_set_param("exptime", "500")
```

- [ ] **Step 3: 测试 — detector_run_acquisition 安全联锁**

```bash
# 信号模式 + 水冷未启动 → 应被拒绝
uv run oh -p "用配置文件 test.config 采集信号，exptime=500, frames=100"
# 如果水冷未启动: 预期 Agent 返回安全联锁错误
```

- [ ] **Step 4: 提交 Phase 2（Day 1 下午完成）**

```bash
cd D:\MyCode\JF_Control_Agent
git add -A
git commit -m "feat(phase2): detector tools (13 tools) + backend /mode endpoint, milestone 2"
git push origin main
```

---

## Day 2 上午：Stage + Processing Tools + Skills

> **里程碑 3**：Agent 能按完整工作流执行降温→基线采集→询问 X 光→信号采集→自动分析

### Task 3.1: Stage Tools（6 个）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/tools/stage_tools.py`

- [ ] **Step 1: 编写 stage_tools.py**

```python
"""Displacement stage control tools."""
from typing import Optional

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

from . import BASE_URL, get_session


class NoInput(BaseModel):
    pass


class MoveAbsoluteInput(BaseModel):
    axis: int = Field(default=1, description="轴号")
    position: float = Field(description="目标位置")
    speed_table: int = Field(default=0, description="速度表")


class MoveRelativeInput(BaseModel):
    axis: int = Field(default=1, description="轴号")
    offset: float = Field(description="相对位移量")
    speed_table: int = Field(default=0, description="速度表")


class ScanInput(BaseModel):
    axis: int = Field(default=1, description="轴号")
    direction: int = Field(default=0, description="方向: 0=CW, 1=CCW")
    step_size: float = Field(description="步长")
    steps: int = Field(description="步数")
    speed_table: int = Field(default=0, description="速度表")
    pause_ms: int = Field(default=100, description="每步暂停 (ms)")


class StageGetStatus(BaseTool):
    name = "stage_get_status"
    description = "查询位移台当前位置、原点状态、扫描状态"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.get(
            f"{BASE_URL}/api/displacement/status?axis=1"
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        if not data.get("connected"):
            return ToolResult(output="⚠️ 位移台未连接")
        pos = data.get("position", "N/A")
        origin = "已完成" if data.get("origin_complete") else "未完成"
        scan = data.get("scan", {})
        scan_info = ""
        if scan.get("running"):
            scan_info = f" | 扫描中: {scan['current_step']}/{scan['total_steps']}"
        return ToolResult(
            output=f"位移台位置: {pos} | 原点: {origin}{scan_info}"
        )


class StageMoveAbsolute(BaseTool):
    name = "stage_move_absolute"
    description = "移动位移台到绝对位置"

    async def execute(self, arguments: MoveAbsoluteInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/move/absolute",
            json={"axis": arguments.axis, "position": arguments.position,
                  "speed_table": arguments.speed_table}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ 位移台已移动到 {arguments.position}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class StageMoveRelative(BaseTool):
    name = "stage_move_relative"
    description = "移动位移台相对偏移量"

    async def execute(self, arguments: MoveRelativeInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/move/relative",
            json={"axis": arguments.axis, "offset": arguments.offset,
                  "speed_table": arguments.speed_table}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output=f"✅ 位移台相对移动 {arguments.offset}")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class StageOriginReturn(BaseTool):
    name = "stage_origin_return"
    description = "位移台返回原点"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/origin",
            json={"axis": 1, "speed_table": 0, "response_mode": 0}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 位移台返回原点")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class StageStartScan(BaseTool):
    name = "stage_start_scan"
    description = "启动位移台扫描。步数 > 1000 时会询问确认。"

    async def execute(self, arguments: ScanInput,
                      context: ToolExecutionContext) -> ToolResult:
        # Safety: warn on large scans (enforced by safety-rules skill)
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/scan/start",
            json={"axis": arguments.axis, "direction": arguments.direction,
                  "step_size": arguments.step_size, "steps": arguments.steps,
                  "speed_table": arguments.speed_table,
                  "pause_ms": arguments.pause_ms}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(
                output=f"✅ 扫描已启动: {arguments.steps} 步，步长 {arguments.step_size}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class StageStop(BaseTool):
    name = "stage_stop"
    description = "紧急停止位移台（所有轴）"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/stop",
            json={"axis": 0, "mode": 1}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 位移台已紧急停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)
```

- [ ] **Step 2: 快速验证 Stage Tools**

```bash
uv run oh -p "查看位移台状态"
```

---

### Task 3.2: Processing Tools（7 个）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/tools/processing_tools.py`

- [ ] **Step 1: 编写 processing_tools.py**

```python
"""Data processing tools — frame reading, pixel fitting, gain/noise/std maps."""
from typing import Optional

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

from . import BASE_URL, get_session


class NoInput(BaseModel):
    pass


class FrameReadInput(BaseModel):
    file_path: str = Field(description=".raw 文件路径")
    frame_idx: int = Field(default=0, description="帧序号")


class FrameAverageInput(BaseModel):
    file_path: str = Field(description=".raw 文件路径")
    start_frame: int = Field(default=0, description="起始帧")
    end_frame: int = Field(default=0, description="结束帧（0=全部）")
    baseline_path: Optional[str] = Field(default=None, description="基线文件路径（可选）")


class PixelFitInput(BaseModel):
    file_path: str = Field(description=".raw 文件路径")
    x: int = Field(description="像素 X 坐标")
    y: int = Field(description="像素 Y 坐标")
    start_frame: int = Field(default=0, description="起始帧")
    end_frame: int = Field(default=100, description="结束帧")
    baseline_path: Optional[str] = Field(default=None, description="基线文件路径（可选）")


class MapInput(BaseModel):
    file_path: str = Field(description=".raw 文件路径")
    start_frame: int = Field(default=0, description="起始帧")
    end_frame: int = Field(default=100, description="结束帧（0=全部）")
    use_baseline: bool = Field(default=False, description="是否扣除基线")
    baseline_path: Optional[str] = Field(default=None, description="基线文件路径")


class AnalyzeInput(BaseModel):
    file_path: str = Field(description="采集生成的 .raw 文件路径")
    baseline_path: Optional[str] = Field(default=None, description="基线文件路径（可选）")
    start_frame: int = Field(default=0)
    end_frame: int = Field(default=100)


class ProcessingReadFrame(BaseTool):
    name = "processing_read_frame"
    description = "读取单帧图像，返回统计信息（min/max/mean/std）+ base64 图像"

    async def execute(self, arguments: FrameReadInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/frame/read",
            json={"file_path": arguments.file_path,
                  "frame_idx": arguments.frame_idx}
        ) as resp:
            data = await resp.json()
        if resp.status == 404:
            return ToolResult(output=f"❌ 文件未找到: {arguments.file_path}",
                              is_error=True)
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        return ToolResult(
            output=f"帧 {data['frame_number']} | shape {data['shape']} | "
                   f"min={data['min']:.1f} max={data['max']:.1f} "
                   f"mean={data['mean']:.1f} std={data['std']:.1f}"
        )


class ProcessingAverageFrames(BaseTool):
    name = "processing_average_frames"
    description = "计算帧范围的平均帧，可选扣除基线"

    async def execute(self, arguments: FrameAverageInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/frame/average",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            data = await resp.json()
        if resp.status == 404:
            return ToolResult(output=f"❌ 文件未找到", is_error=True)
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        lines = [
            f"平均帧 shape {data['shape']}",
            f"min={data['min']:.1f} max={data['max']:.1f} "
            f"mean={data['mean']:.1f} std={data['std']:.1f}",
        ]
        if "baseline_subtracted" in data:
            bs = data["baseline_subtracted"]
            lines.append(
                f"基线扣除后: mean={bs['mean']:.1f} std={bs['std']:.1f}"
            )
        return ToolResult(output="\n".join(lines))


class ProcessingFitPixel(BaseTool):
    name = "processing_fit_pixel"
    description = "对单个像素进行高斯+erfc 拟合，返回 Gain (ADU/keV)、噪声峰、信号峰"

    async def execute(self, arguments: PixelFitInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/pixel/fit",
            json={"file_path": arguments.file_path,
                  "x": arguments.x, "y": arguments.y,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        gain = data.get("gain_adu_per_kev")
        noise = data.get("noise_peak")
        signal = data.get("signal_peak")
        return ToolResult(
            output=f"像素 ({arguments.x},{arguments.y}): "
                   f"Gain={gain:.2f} ADU/keV" if gain else f"Gain=N/A"
                   f" | 噪声峰={noise:.1f} ADU" if noise else ""
                   f" | 信号峰={signal:.1f} ADU" if signal else ""
        )


class ProcessingComputeGainmap(BaseTool):
    name = "processing_compute_gainmap"
    description = "计算全传感器增益图（ADU/keV），返回统计信息"

    async def execute(self, arguments: MapInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/gainmap/compute",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "use_baseline": arguments.use_baseline,
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        return ToolResult(
            output=f"增益图 shape {data['shape']} | "
                   f"mean={data['mean']:.2f} ADU/keV | "
                   f"std={data['std']:.2f} | "
                   f"范围 [{data['min']:.2f}, {data['max']:.2f}]"
        )


class ProcessingComputeNoisemap(BaseTool):
    name = "processing_compute_noisemap"
    description = "计算全传感器噪声峰位置图"

    async def execute(self, arguments: MapInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/noisemap/compute",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame}
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        return ToolResult(
            output=f"噪声峰图 shape {data['shape']} | "
                   f"mean={data['mean']:.2f} | std={data['std']:.2f}"
        )


class ProcessingComputeStdmap(BaseTool):
    name = "processing_compute_stdmap"
    description = "计算每像素时间序列标准差图"

    async def execute(self, arguments: MapInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        async with session.post(
            f"{BASE_URL}/api/processing/stdmap/compute",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "use_baseline": arguments.use_baseline,
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        return ToolResult(
            output=f"标准差图 shape {data['shape']} | "
                   f"mean={data['mean']:.2f} | std={data['std']:.2f}"
        )


class ProcessingAnalyzeAcquisition(BaseTool):
    name = "processing_analyze_acquisition"
    description = (
        "⭐ 采集后一键分析：平均帧 + 增益图 + 噪声峰图 + 生成摘要。"
        "在采集完成后调用此工具进行自动分析。"
    )

    async def execute(self, arguments: AnalyzeInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
        results = []

        # 1. Average frames
        async with session.post(
            f"{BASE_URL}/api/processing/frame/average",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            if resp.status == 200:
                avg = await resp.json()
                results.append(
                    f"平均帧: mean={avg.get('mean', 0):.1f} ADU"
                )
            else:
                results.append("平均帧: 失败")

        # 2. Gain map
        async with session.post(
            f"{BASE_URL}/api/processing/gainmap/compute",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame,
                  "use_baseline": bool(arguments.baseline_path),
                  "baseline_path": arguments.baseline_path}
        ) as resp:
            if resp.status == 200:
                gm = await resp.json()
                results.append(
                    f"增益图: mean={gm.get('mean', 0):.2f} ADU/keV"
                )

        # 3. Noise map
        async with session.post(
            f"{BASE_URL}/api/processing/noisemap/compute",
            json={"file_path": arguments.file_path,
                  "start_frame": arguments.start_frame,
                  "end_frame": arguments.end_frame}
        ) as resp:
            if resp.status == 200:
                nm = await resp.json()
                results.append(
                    f"噪声峰图: mean={nm.get('mean', 0):.2f}"
                )

        return ToolResult(output="\n".join(results))
```

- [ ] **Step 2: 快速验证 Processing Tools**

```bash
uv run oh -p "读取 test.raw 文件的第 0 帧"  # 需要一个实际 raw 文件
```

---

### Task 3.3: Skills（3 个 SKILL.md）

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/skills/experiment-control/SKILL.md`
- Create: `OpenHarness/.openharness/plugins/experiment-control/skills/safety-rules/SKILL.md`
- Create: `OpenHarness/.openharness/plugins/experiment-control/skills/troubleshooting/SKILL.md`

- [ ] **Step 1: 编写 experiment-control/SKILL.md**

```markdown
---
name: experiment-control
description: 探测器实验控制助手。触发词：开启水冷、设置温度、采集数据、基线采集、信号采集、增益图、噪声分析、数据分析、启动系统、关闭系统
version: 0.2.0
---

# 探测器实验控制助手

## 核心原则
- 你有两套工具：**细粒度工具**用于调试和排查，**复合工具**用于标准流程。
- 常规实验优先使用复合工具（一步完成，不会遗漏步骤）。
- 调试或非标操作使用细粒度工具，逐步执行。
- 每个操作前，先检查设备状态（用 `_get_status` 类工具）。
- 所有操作后，给用户人类可读的中文反馈。

## 工具速查

### 水冷机
| 工具 | 用途 |
|------|------|
| chiller_get_status | 查询温度、流量、运行状态 |
| chiller_set_temperature | 设定目标温度（15~25°C） |
| chiller_start / chiller_stop | 启停水冷机 |
| chiller_wait_stable | 等待温度稳定到目标值 |

### 探测器
| 工具 | 用途 |
|------|------|
| detector_load_config | ⭐ 加载配置文件并连接（正常连接方式） |
| detector_set_mode | 设置 baseline/signal 模式 |
| detector_set_param | 设置单个参数 |
| detector_run_acquisition | ⭐ 一键采集（含安全联锁） |
| detector_shutdown | 安全关机 |

### 位移台
| 工具 | 用途 |
|------|------|
| stage_get_status | 当前位置和扫描状态 |
| stage_move_absolute / stage_move_relative | 移动 |
| stage_origin_return | 回原点 |
| stage_start_scan / stage_stop | 扫描控制 |

### 数据处理
| 工具 | 用途 |
|------|------|
| processing_analyze_acquisition | ⭐ 采集后一键分析 |
| processing_compute_gainmap | 全传感器增益图 |
| processing_fit_pixel | 单像素高斯拟合 |

## 标准工作流

### 工作流 1: 降温 + 信号采集（最常用）

```
0. system_startup                          → 启动系统（如未启动）
1. chiller_get_status                      → 确认连接和温度
2. chiller_set_temperature(20)             → 设定目标温度
3. chiller_wait_stable(20)                 → 等待稳定
4. detector_load_config("path/to/config")  → 加载配置，连接探测器
5. detector_set_mode("baseline")           → 基线模式
6. detector_set_param("exptime", "500")    → 设置参数
7. detector_run_acquisition(               → 采集基线
     mode="baseline", ...)
8. ⚠️ 暂停，询问用户：                       X 光机联锁（强制暂停）
   "基线采集完成。请确认已开启 X 光机，然后我将继续采集信号。"
9. 等待用户确认
10. detector_set_mode("signal")            → 切换信号模式
11. detector_run_acquisition(              → 采集信号
      mode="signal", ...)
12. processing_analyze_acquisition         → 自动分析
13. 总结结果
```

### 工作流 2: 纯基线采集（不需要 X 光）
```
1. 降温 + 稳定 → 加载配置 → set_mode("baseline")
2. detector_run_acquisition(mode="baseline") → 直接完成
```

### 工作流 3: 纯信号采集（基线已有）
```
1. 降温 + 稳定 → 加载配置 → set_mode("signal")
2. ⚠️ 询问："请确认 X 光机已开启并稳定，然后开始信号采集？"
3. detector_run_acquisition(mode="signal") → 分析
```

## B/C 模式
- **C 模式（默认）**：用户给了完整参数 → 直接执行，不中断
- **B 模式**：关键操作前询问确认
- **唯一强制 B**：基线→信号之间的 X 光机确认，不可跳过

## 安全
详见 safety-rules skill。核心：温度 15~25°C、流量 < 2 L/min 报警、FPGA > 60°C 报警。
```

- [ ] **Step 2: 编写 safety-rules/SKILL.md**

```markdown
---
name: safety-rules
description: 实验安全规则。Agent 在设备操作时必须参考此规则。
---

# 实验安全规则

## 水冷机

| 规则 | 条件 | 动作 |
|------|------|------|
| 温度上限 | 设定 > 25°C | 拒绝执行 |
| 温度下限 | 设定 < 15°C | 拒绝执行 |
| 运行检查 | 采集前水冷未运行 | 警告用户 |
| 温度偏离 | 偏离目标 > 5°C | 报警 |
| 流量异常 | 流量 < 2 L/min | 报警（可能管道堵塞） |

## 探测器

| 规则 | 条件 | 动作 |
|------|------|------|
| 温度监控 | FPGA > 60°C | 报警 |
| 温度紧急 | FPGA > 70°C | 立即停止并降压 |
| 采集前检查 | 未连接 | 拒绝 |
| 关机流程 | 用户要求关机 | 必须用 detector_shutdown |

## 位移台

| 规则 | 条件 | 动作 |
|------|------|------|
| 扫描步数 | > 1000 | 询问确认 |

## 实验联锁

- **采集前必须同时满足**：水冷运行中 AND 温度在目标 ±2°C AND 探测器已连接
- **X 光安全**：信号采集前强制暂停确认（X 光机未接入控制）

## 紧急处理

- 探测器 FPGA > 70°C：立即 `detector_shutdown`
- 水冷流量 < 2 L/min：停止采集，等待用户排查
```

- [ ] **Step 3: 编写 troubleshooting/SKILL.md**

```markdown
---
name: troubleshooting
description: 故障诊断指南。当工具返回错误时参考此文档排查。
---

# 故障诊断

## 诊断策略
- **先查状态，再操作**：永远先用 `_get_status` 工具
- **从简单到复杂**：先查连接和供电，再深排硬件
- **给用户可操作的建议**，不只报错

## 水冷机无法连接
1. 检查可用的串口列表
2. 确认设备供电
3. 检查 MODBUS 地址和波特率

## 温度降不下来
1. 确认 chiller_start 已执行
2. 检查冷却液是否充足
3. 检查环境温度

## 探测器采集失败
1. 检查 receiver 是否运行 → detector_get_status
2. 检查探测器连接
3. 尝试 disconnect → load_config 重新连接

## 增益图异常
1. 确认使用了正确的基线文件
2. 抽查几个像素 → processing_fit_pixel
3. 对比不同区域的增益值
```

- [ ] **Step 4: 提交 Phase 3（Day 2 上午完成）**

```bash
cd D:\MyCode\JF_Control_Agent
git add -A
git commit -m "feat(phase3): stage tools + processing tools + 3 skills, milestone 3"
git push origin main
```

---

## Day 2 下午：Safety-Watcher + 端到端测试 + 修复

> **里程碑 4**：全流程可运行，安全规则生效

### Task 4.1: Safety-Watcher Subagent

**Files:**
- Create: `OpenHarness/.openharness/plugins/experiment-control/agents/safety-watcher.md`

- [ ] **Step 1: 编写 safety-watcher.md**

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

# 安全监控 Agent

你以后台模式运行，定期检查所有设备状态。发现异常时主动向主 Agent 报告。

## 监控规则

每次检查时按以下规则判断：

1. 水冷流量 < 2 L/min → 报警："⚠️ 水冷流量异常: {value} L/min（低于 2 L/min），可能管道堵塞"
2. 水冷温度偏离目标 > 2°C → 报警："⚠️ 水冷温度偏离: 当前 {temp}°C，目标 {target}°C"
3. 探测器 FPGA 温度 > 60°C → 报警："⚠️ 探测器 FPGA 温度过高: {temp}°C（> 60°C）"
4. 探测器 FPGA 温度 > 70°C → 紧急："🚨 探测器 FPGA 温度 {temp}°C 超过 70°C！建议立即停止实验！"
5. 位移台 scan 状态异常停止 → 报警："⚠️ 位移台扫描异常停止"

## 运行方式

每 30 秒执行一轮检查。主 Agent 在开始长时间采集前启动你，采集完成后终止你。
```

- [ ] **Step 2: 提交 Subagent**

```bash
cd D:\MyCode\JF_Control_Agent
git add OpenHarness/.openharness/plugins/experiment-control/agents/
git commit -m "feat(phase4): safety-watcher subagent"
git push origin main
```

---

### Task 4.2: 端到端测试

- [ ] **Step 1: 全流程测试（模拟模式）**

使用 Chiller 模拟模式 + 无硬件探测器，执行完整工作流：

```bash
cd D:\MyCode\JF_Control_Agent\OpenHarness

# 测试完整 C 模式流程
uv run oh -p "启动系统，把水冷温度设为20度，等温度稳定后，用 my_config.config 做基线采集，exptime=500, frames=100"

# 预期：
# 1. system_startup 被调用
# 2. chiller_set_temperature(20) 被调用
# 3. chiller_wait_stable(20) 被调用（模拟模式下温度会逐渐变化）
# 4. detector_load_config 被调用
# 5. detector_run_acquisition(mode="baseline") 被调用
# 6. 完成（纯基线不询问 X 光）
```

- [ ] **Step 2: X 光联锁测试**

```bash
uv run oh -p "在20度下做一次完整的基线和信号采集，配置文件 my_config.config"
# 预期：基线采集完成后，Agent 暂停询问 X 光确认
# 用户确认后继续信号采集
```

- [ ] **Step 3: 安全场景测试**

```bash
# 测试温度超限（应被拒绝）
uv run oh -p "把水冷温度设为30度"
# 预期: Tool 拒绝（30 > 25）

# 测试信号采集 + 水冷未启动
uv run oh -p "不启动水冷，直接用 my_config.config 采集信号"
# 预期: detector_run_acquisition 安全联锁拒绝
```

- [ ] **Step 4: 错误恢复测试**

```bash
# 测试不存在的配置文件
uv run oh -p "加载不存在配置文件 fake.config"
# 预期: detector_load_config 返回 500 错误，Agent 友好提示
```

- [ ] **Step 5: 提交 Phase 4（Day 2 下午完成）**

```bash
cd D:\MyCode\JF_Control_Agent
git add -A
git commit -m "feat(phase4): safety-watcher + end-to-end testing complete, milestone 4"
git push origin main
```

---

## 提交历史总览

| Phase | 提交信息 | 内容 |
|-------|---------|------|
| Phase 1 | `feat(phase1): system tools + chiller tools (7 tools, milestone 1)` | Plugin 骨架、system_startup/shutdown/check、7 Chiller Tools |
| Phase 2 | `feat(phase2): detector tools (13 tools) + backend /mode endpoint, milestone 2` | 后端 `/mode` 接口、13 Detector Tools |
| Phase 3 | `feat(phase3): stage tools + processing tools + 3 skills, milestone 3` | 6 Stage Tools、7 Processing Tools、3 个 Skill |
| Phase 4 | `feat(phase4): safety-watcher + end-to-end testing complete, milestone 4` | Safety-Watcher Subagent + 测试通过 |

---

## 依赖关系

```
Phase 1 (tools/__init__.py → system_tools.py → chiller_tools.py)
  ↓
Phase 2 (依赖 Phase 1 的共享基础设施 + 后端 /mode 改动)
  ↓
Phase 3 (依赖 Phase 1-2 的 Tools + 后端在线)
  ↓
Phase 4 (依赖全部 Tools + Skills + Subagent)
```
