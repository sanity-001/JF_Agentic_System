"""
MODBUS RTU communication layer using pymodbus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .models import SerialConfig

logger = logging.getLogger(__name__)

# Lazy import pymodbus — only needed when actually connecting to hardware.
# This allows the module to be imported without pymodbus installed.
AsyncModbusSerialClient = None
ModbusException = None
ConnectionException = None
WriteSingleRegisterRequest = None

def _ensure_pymodbus():
    """Import pymodbus, raising a clear error if not installed."""
    global AsyncModbusSerialClient, ModbusException, ConnectionException
    global WriteSingleRegisterRequest
    if AsyncModbusSerialClient is not None:
        return
    try:
        from pymodbus.client import AsyncModbusSerialClient as _client
        from pymodbus.exceptions import ModbusException as _me, ConnectionException as _ce
        from pymodbus.pdu.register_message import WriteSingleRegisterRequest as _wsrr
        AsyncModbusSerialClient = _client
        ModbusException = _me
        ConnectionException = _ce
        WriteSingleRegisterRequest = _wsrr
    except ImportError:
        raise ImportError(
            "pymodbus is required for Modbus RTU communication. "
            "Install it with: pip install pymodbus"
        )


class ModbusClientError(Exception):
    pass


class ModbusClient:
    def __init__(self, config: SerialConfig):
        _ensure_pymodbus()
        self.config = config
        self._client: Optional[AsyncModbusSerialClient] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> bool:
        try:
            self._client = AsyncModbusSerialClient(
                port=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.data_bits,
                parity=self.config.parity,
                stopbits=self.config.stop_bits,
                timeout=1,
                retries=2,
            )
            await self._client.connect()
            self._connected = True
            logger.info(f"Connected to chiller on {self.config.port}")
            return True
        except Exception as e:
            self._connected = False
            logger.error(f"Failed to connect: {e}")
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False
        self._client = None

    async def read_registers(self, address: int, count: int = 1) -> list[int]:
        if not self.is_connected:
            raise ModbusClientError("Not connected to device")

        try:
            result = await self._client.read_holding_registers(
                address=address,
                count=count,
            )
            if result.isError():
                error_msg = _format_modbus_error(result)
                raise ModbusClientError(error_msg)
            raw = list(result.registers)
            logger.debug(f"Read addr=0x{address:04X} count={count} => {raw}")
            return raw
        except ModbusClientError:
            raise
        except (ModbusException, ConnectionException) as e:
            self._connected = False
            raise ModbusClientError(f"Communication error: {e}")
        except Exception as e:
            self._connected = False
            raise ModbusClientError(f"Unexpected error: {e}")

    async def write_register(self, address: int, value: int) -> bool:
        if not self.is_connected:
            raise ModbusClientError("Not connected to device")

        logger.debug(f"Write addr=0x{address:04X} value={value} slave={self.config.slave_address}")
        try:
            request = WriteSingleRegisterRequest(address=address, registers=[value])
            result = await self._client.execute(False, request)
            if result.isError():
                error_msg = _format_modbus_error(result)
                logger.error(f"Write failed: {error_msg}")
                raise ModbusClientError(error_msg)
            logger.debug(f"Write addr=0x{address:04X} OK")
            return True
        except ModbusClientError:
            raise
        except (ModbusException, ConnectionException) as e:
            self._connected = False
            raise ModbusClientError(f"Write communication error: {e}")
        except Exception as e:
            self._connected = False
            raise ModbusClientError(f"Unexpected write error: {e}")

    async def update_config(self, config: SerialConfig):
        self.disconnect()
        self.config = config
        await self.connect()


_MODBUS_ERROR_NAMES = {
    1: "Illegal Function",
    2: "Illegal Data Address",
    3: "Illegal Data Value",
    4: "Slave Device Failure",
    5: "Acknowledge",
    6: "Slave Device Busy",
    8: "Memory Parity Error",
    9: "CRC/LRC Error",
    10: "Parity Error",
    12: "Data Too Short",
    13: "Data Too Long",
}


def _format_modbus_error(result) -> str:
    """Extract human-readable error from a Modbus exception response."""
    try:
        if hasattr(result, 'exception_code'):
            code = result.exception_code
            name = _MODBUS_ERROR_NAMES.get(code, f"Unknown({code})")
            return f"Modbus error: code={code} ({name})"
    except Exception:
        pass
    return f"Modbus error: {result}"
