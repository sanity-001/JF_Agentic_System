"""Water chiller service — thin wrapper around original ChillerService + ModbusClient.

Provides two modes:
  - Simulation mode (default): Self-contained simulation, no pymodbus needed.
  - Real mode: Wraps the original ChillerService. Requires pymodbus.

Original source files (models.py, modbus_client.py, chiller_service.py) are
copied into this directory and imported directly.
"""
import asyncio
import random
import time
from typing import Optional, Any

# Direct import from copied original files
from .models import SerialConfig
from .chiller_service import ChillerService as _ChillerServiceOrig
from .modbus_client import ModbusClient as _ModbusClient


# ── Indicator constants ──

_INDICATOR_BITS = {
    "power": 0,
    "level_alarm": 1,
    "temp_alarm": 2,
    "pump": 3,
    "flow_alarm": 4,
    "cool": 5,
    "out": 6,
    "run": 7,
}


def _encode_indicators(ind: dict) -> int:
    value = 0
    for name, bit in _INDICATOR_BITS.items():
        if ind.get(name):
            value |= (1 << bit)
    return value


def _decode_indicators(reg_value: int) -> dict:
    return {name: bool(reg_value & (1 << bit)) for name, bit in _INDICATOR_BITS.items()}


class ChillerService:
    """Water chiller service wrapper.

    In simulation mode, provides a self-contained simulation with no external
    dependencies. In real mode, wraps the original ChillerService + ModbusClient.
    """

    def __init__(self, simulation: bool = True):
        self._simulation = simulation
        self._service = None
        self._client = None
        self._connected = False
        self._last_status = {"connected": False}

        # Simulation state
        self._sim_temp = 25.0
        self._sim_flow = 12.5
        self._sim_target_temp = 25.0
        self._sim_running = True
        self._sim_time = 0
        self._sim_alarm = 50.0
        self._sim_deviation = 5.0
        self._sim_pid = (30.0, 240.0, 60.0)
        self._sim_task: Optional[asyncio.Task] = None
        self._sim_running_flag = False

    def get_status_sync(self):
        """Return last cached status (for WebSocket broadcast loop)."""
        return dict(self._last_status)

    # ── Async API ──

    async def connect_async(self, config: dict = None):
        if self._simulation:
            self._sim_running_flag = True
            self._sim_task = asyncio.create_task(self._sim_poll_loop())
            self._connected = True
            return True

        serial_config = SerialConfig()
        if config:
            for k, v in config.items():
                if hasattr(serial_config, k):
                    setattr(serial_config, k, v)

        self._service = _ChillerServiceOrig(serial_config, simulation=False)
        await self._service.start()
        self._connected = True
        return True

    async def disconnect_async(self):
        if self._simulation:
            self._sim_running_flag = False
            if self._sim_task:
                self._sim_task.cancel()
                try:
                    await self._sim_task
                except asyncio.CancelledError:
                    pass
                self._sim_task = None
        elif self._service:
            await self._service.stop()
        self._connected = False
        return True

    # ── Simulation poll loop ──

    async def _sim_poll_loop(self):
        while self._sim_running_flag:
            self._sim_time += 2
            if self._sim_running:
                drift = (self._sim_target_temp - self._sim_temp) * 0.1
                noise = random.uniform(-0.15, 0.15)
                self._sim_temp += drift + noise
                self._sim_flow = 12.5 + random.uniform(-0.3, 0.3)
            else:
                self._sim_temp += random.uniform(-0.05, 0.05)
            await asyncio.sleep(2)

    # ── Status queries ──

    async def get_status_async(self):
        if self._simulation:
            if not self._connected:
                self._last_status = {"connected": False}
                return self._last_status
            status = {
                "temperature": round(self._sim_temp, 2),
                "flow_rate": round(self._sim_flow, 2),
                "running_time": self._sim_time,
                "indicators": _decode_indicators(_encode_indicators({
                    "power": True,
                    "level_alarm": False,
                    "temp_alarm": False,
                    "pump": self._sim_running,
                    "flow_alarm": False,
                    "cool": self._sim_running and self._sim_temp > self._sim_target_temp,
                    "out": self._sim_running,
                    "run": self._sim_running,
                })),
                "connection": "connected",
            }
            self._last_status = status
            return status

        if not self._service:
            self._last_status = {"connected": False}
            return self._last_status
        try:
            status = self._service.get_status()
            if hasattr(status, 'model_dump'):
                status = status.model_dump()
            self._last_status = status
            return status
        except Exception:
            self._last_status = {"connected": False}
            return self._last_status

    async def get_ws_data_async(self):
        if self._simulation:
            status = await self.get_status_async()
            status["timestamp"] = time.time()
            return status

        if not self._service:
            return {"connected": False}
        try:
            data = self._service.get_ws_data()
            if hasattr(data, 'model_dump'):
                return data.model_dump()
            return data
        except Exception:
            return {"connected": False}

    # ── Parameter read/write ──

    async def get_params(self):
        if self._simulation:
            return {
                "temperature_sp": self._sim_target_temp,
                "time_sp": 0,
                "alarm": self._sim_alarm,
                "deviation": self._sim_deviation,
                "p_band": self._sim_pid[0],
                "i_time": self._sim_pid[1],
                "d_time": self._sim_pid[2],
            }
        if not self._service:
            return {}
        return await self._service.get_params()

    async def set_temperature_sp(self, value: float):
        if self._simulation:
            self._sim_target_temp = value
            return
        if self._service:
            return await self._service.set_temperature_sp(value)

    async def set_alarm_limit(self, value: float):
        if self._simulation:
            self._sim_alarm = value
            return
        if self._service:
            return await self._service.set_alarm_limit(value)

    async def set_deviation(self, value: float):
        if self._simulation:
            self._sim_deviation = value
            return
        if self._service:
            return await self._service.set_deviation(value)

    async def set_pid(self, p: float, i: float, d: float):
        if self._simulation:
            self._sim_pid = (p, i, d)
            return
        if self._service:
            return await self._service.set_pid(p, i, d)

    async def start_chiller(self):
        if self._simulation:
            self._sim_running = True
            return
        if self._service:
            return await self._service.start_chiller()

    async def stop_chiller(self):
        if self._simulation:
            self._sim_running = False
            return
        if self._service:
            return await self._service.stop_chiller()

    async def start_autotune(self):
        if self._simulation:
            return
        if self._service:
            return await self._service.start_autotune()

    async def mute_buzzer(self):
        if self._simulation:
            return
        if self._service:
            return await self._service.mute_buzzer()

    @property
    def connected(self) -> bool:
        return self._connected
