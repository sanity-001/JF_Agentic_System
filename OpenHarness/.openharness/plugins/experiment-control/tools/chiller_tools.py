"""Water chiller control tools."""
import asyncio
import os
import time

import aiohttp
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

BASE_URL = os.environ.get("JF_CONTROL_API_URL", "http://localhost:8000")
_http_session: aiohttp.ClientSession | None = None

def _get_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


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


class ChillerConnectInput(BaseModel):
    port: str = Field(default="/dev/ttyUSB1", description="串口设备路径")
    baudrate: int = Field(default=4800, description="波特率")
    slave_address: int = Field(default=1, description="MODBUS 从站地址")


class WaitStableInput(BaseModel):
    target: float = Field(description="目标温度 (°C)")
    tolerance: float = Field(default=0.3, description="允许偏差 (°C)")
    timeout_seconds: int = Field(default=600, description="最长等待 (s)")


# ── Tools ──

class ChillerConnect(BaseTool):
    name = "chiller_connect"
    description = "连接水冷机（MODBUS RTU）。默认串口 /dev/ttyUSB1，波特率 4800。"
    input_model = ChillerConnectInput

    async def execute(self, arguments: ChillerConnectInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(
            f"{BASE_URL}/api/chiller/connect",
            json={"port": arguments.port, "baudrate": arguments.baudrate,
                  "slave_address": arguments.slave_address}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output=f"✅ 水冷机已连接 ({arguments.port})")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerDisconnect(BaseTool):
    name = "chiller_disconnect"
    description = "断开与水冷机的连接"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/chiller/disconnect") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 水冷机已断开")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)

class ChillerGetStatus(BaseTool):
    name = "chiller_get_status"
    description = "查询水冷机当前状态：温度、流量、运行时间、指示灯状态"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.get(f"{BASE_URL}/api/chiller/status") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        if not data.get("connected") and data.get("connection") != "connected":
            return ToolResult(output="⚠️ 水冷机未连接")
        ind = data.get("indicators", {})
        running = "运行中" if ind.get("run") else "已停止"
        temp = data.get("temperature", 0) / 100.0
        flow = data.get("flow_rate", 0) / 100.0
        return ToolResult(
            output=f"水冷机温度 {temp:.1f}°C，"
                   f"流量 {flow:.2f} L/min，"
                   f"运行时间 {data.get('running_time', 0)}s，"
                   f"状态: {running}"
        )


class ChillerGetParams(BaseTool):
    name = "chiller_get_params"
    description = "查询水冷机当前参数：目标温度、报警温度、PID 设置"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    input_model = TemperatureInput

    async def execute(self, arguments: TemperatureInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    input_model = PIDInput

    async def execute(self, arguments: PIDInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/chiller/start") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 水冷机已启动")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerStop(BaseTool):
    name = "chiller_stop"
    description = "停止水冷机"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/chiller/stop") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 水冷机已停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class ChillerWaitStable(BaseTool):
    name = "chiller_wait_stable"
    description = "等待水冷机温度稳定到目标值 ± tolerance 范围内。默认偏差 0.3°C，最长 600s。"
    input_model = WaitStableInput

    async def execute(self, arguments: WaitStableInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
            if not data.get("connected") and data.get("connection") != "connected":
                return ToolResult(output="❌ 水冷机未连接", is_error=True)
            temp = data["temperature"] / 100.0
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
                   f"当前 {last_temp:.1f}°C，目标 {arguments.target}°C",
            is_error=True
        )
