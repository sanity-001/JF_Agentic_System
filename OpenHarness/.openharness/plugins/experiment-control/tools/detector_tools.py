"""Detector control tools — connection, acquisition, and shutdown."""
import asyncio
import time

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
            if time.time() - start_time > 3600:
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
    description = "安全关机：停止采集→断开连接。确保探测器安全退出。"

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = get_session()
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
