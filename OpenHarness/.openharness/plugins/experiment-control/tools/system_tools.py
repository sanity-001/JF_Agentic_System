"""System-level tools — startup, shutdown, and health check."""
import asyncio
import os
import signal
import subprocess
import sys

import aiohttp
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from pydantic import BaseModel

# ── Shared HTTP (inlined — plugin loader doesn't support relative imports) ──
BASE_URL = os.environ.get("JF_CONTROL_API_URL", "http://localhost:8000")
_http_session: aiohttp.ClientSession | None = None

def _get_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

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
    input_model = SystemCheckInput

    async def execute(self, arguments: SystemCheckInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()
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
    input_model = SystemStartupInput

    async def execute(self, arguments: SystemStartupInput,
                      context: ToolExecutionContext) -> ToolResult:
        session = _get_session()

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
    input_model = SystemShutdownInput

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
