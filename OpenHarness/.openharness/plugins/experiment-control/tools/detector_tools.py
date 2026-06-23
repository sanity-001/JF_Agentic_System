"""Detector control tools — connection, acquisition, and shutdown (500K mode)."""
import asyncio
import glob
import json
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

# ── Default config for 500K detector ──
DEFAULT_CONFIG_PATH = "/home/jfdaq/JF500K/JF500K-shine.config"

# ── Persistent baseline state (on disk, survives tool metadata resets) ──
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
    "..", "..", "..", "..", ".."))
BASELINE_STATE_FILE = os.path.join(_REPO_ROOT, ".baseline_state.json")

def _read_baseline_state():
    """Return persistent baseline state or None."""
    try:
        with open(BASELINE_STATE_FILE) as f:
            s = json.load(f)
        fpath, fname = s.get("fpath", ""), s.get("fname", "")
        if fpath and fname and glob.glob(f"{fpath}/{fname}_d0_f0_*.raw"):
            return s
    except Exception:
        pass
    return None

def _write_baseline_state(fpath, fname):
    try:
        with open(BASELINE_STATE_FILE, 'w') as f:
            json.dump({"fpath": fpath, "fname": fname}, f)
    except OSError:
        pass


# ── Input models ──

class NoInput(BaseModel):
    pass


class DetectorConnectInput(BaseModel):
    hostname: str = Field(description="探测器主机名或 IP")
    config_params: dict = Field(default_factory=dict,
                                description="额外配置参数（可选）")


class LoadConfigInput(BaseModel):
    path: str = Field(
        default=DEFAULT_CONFIG_PATH,
        description=f"本地 .config 配置文件路径（默认: {DEFAULT_CONFIG_PATH}）"
    )


class BrowseFilesInput(BaseModel):
    path: str = Field(default=".", description="浏览目录路径")


class SetParamInput(BaseModel):
    key: str = Field(description="参数名：exptime, frames, period 等")
    value: str = Field(description="参数值")


class SetModeInput(BaseModel):
    mode: str = Field(description='"baseline" 或 "signal"')


class RunAcquisitionInput(BaseModel):
    mode: str = Field(description='"baseline" 或 "signal"')
    check_safety: bool = Field(default=True,
                               description="是否执行安全联锁检查")


# ── Fine-grained tools ──

class DetectorGetStatus(BaseTool):
    name = "detector_get_status"
    description = "查询探测器连接状态、采集状态、芯片版本"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    description = "查询探测器当前所有参数（含 fpath/fname，用于确定 raw 文件位置）"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.get(f"{BASE_URL}/api/detector/params") as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)
        if not data:
            return ToolResult(output="⚠️ 探测器未连接，无参数")
        lines = [f"{k}: {v}" for k, v in sorted(data.items())]
        return ToolResult(output="\n".join(lines))


class DetectorGetTemperatures(BaseTool):
    name = "detector_get_temperatures"
    description = "读取探测器 FPGA 和 ADC 温度"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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


class DetectorBrowseFiles(BaseTool):
    name = "detector_browse_files"
    description = "浏览服务器上的文件和目录，用于查找配置文件或 raw 数据文件"
    input_model = BrowseFilesInput

    async def execute(self, arguments: BrowseFilesInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.get(
            f"{BASE_URL}/api/detector/browse",
            params={"path": arguments.path}
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            return ToolResult(output=f"❌ {data.get('detail', data)}",
                              is_error=True)

        lines = [f"📁 当前目录: {data['current']}"]
        if data.get("parent"):
            lines.append(f"  📂 ../ (上级目录)")
        for d in data.get("dirs", []):
            lines.append(f"  📂 {d['name']}/")
        for f in data.get("files", []):
            lines.append(f"  📄 {f['name']}")

        # Store for later use by load_config
        context.metadata["last_browse_dir"] = data["current"]
        return ToolResult(output="\n".join(lines))


class DetectorLoadConfig(BaseTool):
    name = "detector_load_config"
    description = (
        f"加载本地 .config 配置文件并自动连接探测器。"
        f"默认加载 {DEFAULT_CONFIG_PATH}，不传路径则使用默认配置。"
    )
    input_model = LoadConfigInput

    async def execute(self, arguments: LoadConfigInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/load_config",
            json={"path": arguments.path}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            context.metadata["config_loaded"] = True
            context.metadata["config_path"] = arguments.path
            return ToolResult(
                output=f"✅ 配置已加载，探测器已连接\n"
                       f"配置文件: {arguments.path}\n"
                       f"参数: {data.get('message', '')}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorConnect(BaseTool):
    name = "detector_connect"
    description = "不使用配置文件时，通过 hostname + 参数直接连接探测器"
    input_model = DetectorConnectInput

    async def execute(self, arguments: DetectorConnectInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/connect",
            json={"hostname": arguments.hostname,
                  "config_params": arguments.config_params}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            context.metadata["config_loaded"] = True
            return ToolResult(output="✅ 探测器已连接")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorDisconnect(BaseTool):
    name = "detector_disconnect"
    description = "断开探测器连接"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/detector/disconnect") as resp:
            data = await resp.json()
        if resp.status == 200:
            context.metadata.pop("config_loaded", None)
            return ToolResult(output="✅ 探测器已断开")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorSetParam(BaseTool):
    name = "detector_set_param"
    description = "设置单个探测器参数（exptime, frames, period, highvoltage 等）"
    input_model = SetParamInput

    async def execute(self, arguments: SetParamInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    description = '设置采集模式："baseline"（基线采集，结果保存为基线）或 "signal"（信号采集，需先有基线）'
    input_model = SetModeInput

    async def execute(self, arguments: SetModeInput,
                      context: ToolExecutionContext) -> ToolResult:
        if arguments.mode not in ("baseline", "signal"):
            return ToolResult(
                output=f"❌ 无效模式: {arguments.mode}，仅支持 baseline/signal",
                is_error=True
            )
        session = _get_session()
        async with session.post(
            f"{BASE_URL}/api/detector/mode",
            json={"mode": arguments.mode}
        ) as resp:
            data = await resp.json()
        if resp.status == 200:
            context.metadata["acq_mode"] = arguments.mode
            return ToolResult(
                output=f"✅ 采集模式已设为 {arguments.mode}"
            )
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorStartAcquisition(BaseTool):
    name = "detector_start_acquisition"
    description = "启动探测器采集（非阻塞）。需先加载配置并设置参数。"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/detector/acquire/start") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 采集已启动")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


class DetectorStopAcquisition(BaseTool):
    name = "detector_stop_acquisition"
    description = "停止/中断探测器采集"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/detector/acquire/stop") as resp:
            data = await resp.json()
        if resp.status == 200:
            return ToolResult(output="✅ 采集已停止")
        return ToolResult(output=f"❌ {data.get('detail', data)}",
                          is_error=True)


# ── Composite tools ──

class DetectorRunAcquisition(BaseTool):
    name = "detector_run_acquisition"
    description = (
        "启动探测器采集并等待完成。"
        "⚠️ 调用前需已通过 detector_load_config 加载配置、"
        "detector_set_mode 设置模式、detector_set_param 设置参数。"
        "baseline 模式会自动记录基线状态，signal 模式会检查是否已有基线。"
    )
    input_model = RunAcquisitionInput

    async def execute(self, arguments: RunAcquisitionInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()

        if arguments.mode not in ("baseline", "signal"):
            return ToolResult(
                output=f"❌ 无效模式: {arguments.mode}，仅支持 baseline/signal",
                is_error=True
            )

        # 0. Check baseline prerequisite for signal mode
        if arguments.mode == "signal":
            # Check in-memory metadata first, then fall back to disk state
            if not context.metadata.get("has_baseline"):
                saved = _read_baseline_state()
                if saved:
                    # Restore into metadata so downstream tools can use it
                    context.metadata["has_baseline"] = True
                    context.metadata["baseline_fpath"] = saved["fpath"]
                    context.metadata["baseline_fname"] = saved["fname"]
                else:
                    return ToolResult(
                        output="❌ 尚未采集基线。请先执行一次基线采集（mode='baseline'）。",
                        is_error=True
                    )

        # 1. Safety interlock — mandatory for ALL acquisition modes
        if arguments.check_safety:
            async with session.get(f"{BASE_URL}/api/chiller/status") as resp:
                ch_data = await resp.json()
            if resp.status == 200:
                if not ch_data.get("indicators", {}).get("run"):
                    return ToolResult(
                        output="❌ 安全联锁：水冷机未运行，拒绝采集。请先启动水冷。",
                        is_error=True
                    )
                temp = ch_data.get("temperature", 0) / 100.0
                if temp is not None and not (15 <= temp <= 25):
                    return ToolResult(
                        output=f"❌ 安全联锁：水冷温度 {temp:.1f}°C 超出安全范围 [15, 25]°C",
                        is_error=True
                    )

        # 2. Start acquisition
        async with session.post(f"{BASE_URL}/api/detector/acquire/start") as resp:
            if resp.status != 200:
                data = await resp.json()
                return ToolResult(
                    output=f"❌ 启动采集失败: {data.get('detail', data)}",
                    is_error=True
                )

        # 3. Poll until acquisition completes
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

        # 4. Read params to determine raw file location (500K: single file)
        async with session.get(f"{BASE_URL}/api/detector/params") as resp:
            params = await resp.json()

        fpath = params.get("fpath", "")
        fname = params.get("fname", "")
        raw_file = f"{fpath}/{fname}_d0_f0_*.raw"

        # 5. Store state in metadata for downstream tools
        context.metadata["last_raw_pattern"] = raw_file
        context.metadata["last_fpath"] = fpath
        context.metadata["last_fname"] = fname
        context.metadata["last_acq_mode"] = arguments.mode

        if arguments.mode == "baseline":
            context.metadata["has_baseline"] = True
            context.metadata["baseline_fpath"] = fpath
            context.metadata["baseline_fname"] = fname
            _write_baseline_state(fpath, fname)  # persist to disk

        return ToolResult(
            output=f"✅ 采集完成（模式: {arguments.mode}，耗时 {duration}s）\n"
                   f"文件位置: {fpath}/{fname}_*.raw"
        )


class DetectorShutdown(BaseTool):
    name = "detector_shutdown"
    description = "安全关机：停止采集→停receiver→降压→关powerchip→释放共享内存"
    input_model = NoInput

    async def execute(self, arguments: NoInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
        async with session.post(f"{BASE_URL}/api/detector/shutdown") as resp:
            data = await resp.json()
        if resp.status == 200:
            # Clear acquisition state
            context.metadata.pop("has_baseline", None)
            context.metadata.pop("last_raw_pattern", None)
            return ToolResult(output="✅ 探测器安全关机完成")
        return ToolResult(output=f"❌ 关机失败: {data.get('detail', data)}",
                          is_error=True)
