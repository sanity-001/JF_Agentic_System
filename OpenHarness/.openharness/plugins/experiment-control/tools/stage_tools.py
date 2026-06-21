"""Displacement stage control tools."""
import os

import aiohttp
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel, Field

BASE_URL = os.environ.get("JF_CONTROL_API_URL", "http://localhost:8000")
_http_session: aiohttp.ClientSession | None = None

def ___get_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


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
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
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
    input_model = MoveAbsoluteInput

    async def execute(self, arguments: MoveAbsoluteInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
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
    input_model = MoveRelativeInput

    async def execute(self, arguments: MoveRelativeInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
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
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
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
    input_model = ScanInput

    async def execute(self, arguments: ScanInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
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
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = __get_session()
        async with session.post(
            f"{BASE_URL}/api/displacement/stop",
            json={"axis": 0, "mode": 1}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 位移台已紧急停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)
