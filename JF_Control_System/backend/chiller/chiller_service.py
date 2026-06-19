"""
Business logic layer: register map, polling, caching, and control operations.
Supports both real MODBUS communication and simulation mode.
"""

import asyncio
import logging
import random
import threading
import time
from typing import Optional

from .models import (
    ChillerStatus,
    ConnectionState,
    SerialConfig,
    WSPushData,
)
from .modbus_client import ModbusClient, ModbusClientError

logger = logging.getLogger(__name__)

# Register map
REG_TEMPERATURE = 0x0000     # Temperature PV (read only)
REG_TIME_RUNNING = 0x0001    # Time running (read only)
REG_INDICATORS = 0x0002      # Indicator status (read only)
REG_TEMP_SP = 0x0003         # Temperature setpoint
REG_TIME_SP = 0x0004         # Time setpoint
REG_ALARM = 0x0005           # Over-temp alarm
REG_DEVIATION = 0x0006       # Cooling deviation
REG_P_BAND = 0x0007          # P proportional band
REG_I_TIME = 0x0008          # I integral time
REG_D_TIME = 0x0009          # D derivative time
REG_START_STOP = 0x0031      # Start/Stop control (0=stop, 3=run)
REG_AUTOTUNE = 0x0032        # Auto-tuning (0=stop, 1=start)
REG_BUZZER = 0x0035          # Buzzer mute (write 1 to mute)
REG_FLOW_SP = 0x003E         # Flow setpoint
REG_FLOW_PV = 0x003F         # Flow PV (read only)

# Indicator bit mapping
INDICATOR_BITS = {
    "power": 0,
    "level_alarm": 1,
    "temp_alarm": 2,
    "pump": 3,
    "flow_alarm": 4,
    "cool": 5,
    "out": 6,
    "run": 7,
}


def _decode_indicators(reg_value: int) -> dict:
    return {name: bool(reg_value & (1 << bit)) for name, bit in INDICATOR_BITS.items()}


def _encode_indicators(ind: dict) -> int:
    value = 0
    for name, bit in INDICATOR_BITS.items():
        if ind.get(name):
            value |= (1 << bit)
    return value


def _decode_temperature(reg_value: int) -> Optional[int]:
    if reg_value == 0x7FFF:
        return None
    if reg_value == 0x8001:
        return None
    return reg_value


class ChillerService:
    def __init__(self, config: SerialConfig, simulation: bool = False):
        self.config = config
        self.simulation = simulation
        self.client = ModbusClient(config) if not simulation else None
        self._cache: dict = {}
        self._lock = threading.Lock()
        self._poll_task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1
        self._max_reconnect_delay = 30
        self._running = False

        # Simulation state
        self._sim_temp = 25.0
        self._sim_flow = 12.5
        self._sim_target_temp = 25.0
        self._sim_running = True
        self._sim_time = 0

    @property
    def connection_state(self) -> ConnectionState:
        if self.simulation:
            return ConnectionState.CONNECTED
        if self.client and self.client.is_connected:
            return ConnectionState.CONNECTED
        return ConnectionState.DISCONNECTED

    async def start(self):
        self._running = True
        if self.simulation:
            self._poll_task = asyncio.create_task(self._sim_poll_loop())
        else:
            await self._try_connect()
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self.client:
            self.client.disconnect()

    async def _try_connect(self) -> bool:
        if self.simulation:
            return True
        success = await self.client.connect()
        if success:
            self._reconnect_delay = 1
        return success

    async def _reconnect(self):
        if self.simulation:
            return
        self.client.disconnect()
        delay = self._reconnect_delay
        logger.info(f"Reconnecting in {delay}s...")
        await asyncio.sleep(delay)
        if await self._try_connect():
            self._reconnect_delay = 1
        else:
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    # ---- Simulation poll ----

    async def _sim_poll_loop(self):
        while self._running:
            self._sim_time += 2
            # Gradually approach target temperature with noise
            if self._sim_running:
                drift = (self._sim_target_temp - self._sim_temp) * 0.1
                noise = random.uniform(-0.15, 0.15)
                self._sim_temp += drift + noise
                self._sim_flow = 12.5 + random.uniform(-0.3, 0.3)
            else:
                self._sim_temp += random.uniform(-0.05, 0.05)

            sim_data = {
                "_temperature_raw": int(self._sim_temp * 100),
                "_indicators_raw": _encode_indicators({
                    "power": True,
                    "level_alarm": False,
                    "temp_alarm": False,
                    "pump": self._sim_running,
                    "flow_alarm": False,
                    "cool": self._sim_running and self._sim_temp > self._sim_target_temp,
                    "out": self._sim_running,
                    "run": self._sim_running,
                }),
                "_flow_raw": int(self._sim_flow * 100),
                "_time_raw": self._sim_time,
            }
            with self._lock:
                self._cache.update(sim_data)
            await asyncio.sleep(2)

    # ---- Real MODBUS poll ----

    async def _poll_loop(self):
        while self._running:
            try:
                if self.simulation:
                    break
                if self.client.is_connected:
                    data = await self._read_status_registers()
                    with self._lock:
                        self._cache.update(data)
                else:
                    await self._reconnect()
            except ModbusClientError as e:
                logger.warning(f"Poll error: {e}")
                with self._lock:
                    self._cache["_error"] = str(e)
                await self._reconnect()
            except Exception as e:
                logger.error(f"Unexpected poll error: {e}")
                await asyncio.sleep(2)

            await asyncio.sleep(2)

    async def _read_status_registers(self) -> dict:
        temps = await self.client.read_registers(REG_TEMPERATURE, 1)
        indicators_reg = await self.client.read_registers(REG_INDICATORS, 1)
        flows = await self.client.read_registers(REG_FLOW_PV, 1)
        times = await self.client.read_registers(REG_TIME_RUNNING, 1)

        return {
            "_temperature_raw": temps[0] if temps else 0,
            "_indicators_raw": indicators_reg[0] if indicators_reg else 0,
            "_flow_raw": flows[0] if flows else 0,
            "_time_raw": times[0] if times else 0,
        }

    # ---- Status queries ----

    def get_status(self) -> ChillerStatus:
        with self._lock:
            temp_raw = self._cache.get("_temperature_raw", 0)
            indicators_raw = self._cache.get("_indicators_raw", 0)
            flow_raw = self._cache.get("_flow_raw", 0)
            time_raw = self._cache.get("_time_raw", 0)

        temp_decoded = _decode_temperature(temp_raw)
        flow_decoded = _decode_temperature(flow_raw)
        logger.debug(f"Status: temp_raw={temp_raw} -> {temp_decoded}°C, flow_raw={flow_raw} -> {flow_decoded}L/min")

        return ChillerStatus(
            temperature=temp_decoded,
            flow_rate=flow_decoded,
            running_time=time_raw if time_raw else None,
            indicators=_decode_indicators(indicators_raw),
            connection=self.connection_state,
        )

    def get_ws_data(self) -> WSPushData:
        status = self.get_status()
        return WSPushData(
            temperature=status.temperature,
            flow_rate=status.flow_rate,
            running_time=status.running_time,
            indicators=status.indicators,
            connection=status.connection,
            timestamp=time.time(),
        )

    # ---- Parameter read/write ----

    async def get_params(self) -> dict:
        if self.simulation:
            return {
                "temperature_sp": self._sim_target_temp,
                "time_sp": 0,
                "alarm": 50,
                "deviation": 5,
                "p_band": 30,
                "i_time": 240,
                "d_time": 60,
            }
        if not self.client.is_connected:
            raise ModbusClientError("Device not connected")
        regs = await self.client.read_registers(REG_TEMP_SP, 7)
        return {
            "temperature_sp": _decode_temperature(regs[0]) if len(regs) > 0 else None,
            "time_sp": regs[1] if len(regs) > 1 else None,
            "alarm": regs[2] if len(regs) > 2 else None,
            "deviation": regs[3] if len(regs) > 3 else None,
            "p_band": regs[4] if len(regs) > 4 else None,
            "i_time": regs[5] if len(regs) > 5 else None,
            "d_time": regs[6] if len(regs) > 6 else None,
        }

    async def set_temperature_sp(self, value: float):
        if self.simulation:
            self._sim_target_temp = value
            return
        reg_value = int(value * 100)
        await self.client.write_register(REG_TEMP_SP, reg_value)

    async def set_alarm_limit(self, value: float):
        if self.simulation:
            return
        await self.client.write_register(REG_ALARM, int(value))

    async def set_deviation(self, value: float):
        if self.simulation:
            return
        await self.client.write_register(REG_DEVIATION, int(value))

    async def set_pid(self, p: float, i: float, d: float):
        if self.simulation:
            return
        await self.client.write_register(REG_P_BAND, int(p))
        await self.client.write_register(REG_I_TIME, int(i))
        await self.client.write_register(REG_D_TIME, int(d))

    async def set_flow_sp(self, value: float):
        if self.simulation:
            return
        reg_value = int(value * 100)
        await self.client.write_register(REG_FLOW_SP, reg_value)

    async def start_chiller(self):
        if self.simulation:
            self._sim_running = True
            return
        await self.client.write_register(REG_START_STOP, 3)

    async def stop_chiller(self):
        if self.simulation:
            self._sim_running = False
            return
        await self.client.write_register(REG_START_STOP, 0)

    async def start_autotune(self):
        if self.simulation:
            return
        await self.client.write_register(REG_AUTOTUNE, 1)

    async def mute_buzzer(self):
        if self.simulation:
            return
        await self.client.write_register(REG_BUZZER, 1)

    async def update_serial_config(self, config: SerialConfig):
        await self.stop()
        self.config = config
        if not self.simulation:
            self.client = ModbusClient(config)
        self._cache.clear()
        await self.start()
