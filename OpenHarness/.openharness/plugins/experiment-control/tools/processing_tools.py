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
        parts = [f"像素 ({arguments.x},{arguments.y}):"]
        if gain is not None:
            parts.append(f"Gain={gain:.2f} ADU/keV")
        if noise is not None:
            parts.append(f"噪声峰={noise:.1f} ADU")
        if signal is not None:
            parts.append(f"信号峰={signal:.1f} ADU")
        return ToolResult(output=" | ".join(parts))


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

        return ToolResult(output="\n".join(results) if results else "⚠️ 分析未能完成")
