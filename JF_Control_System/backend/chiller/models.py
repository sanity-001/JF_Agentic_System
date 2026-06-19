from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ChillerStatus(BaseModel):
    temperature: Optional[float] = None
    flow_rate: Optional[float] = None
    running_time: Optional[int] = None
    indicators: dict = Field(default_factory=lambda: {
        "power": False,
        "level_alarm": False,
        "temp_alarm": False,
        "pump": False,
        "flow_alarm": False,
        "cool": False,
        "out": False,
        "run": False,
    })
    connection: ConnectionState = ConnectionState.DISCONNECTED


class SetpointUpdate(BaseModel):
    value: float = Field(..., description="Temperature setpoint value")


class AlarmLimitUpdate(BaseModel):
    value: float = Field(..., description="Over-temperature alarm limit")


class DeviationUpdate(BaseModel):
    value: float = Field(..., description="Cooling deviation control value")


class PIDParams(BaseModel):
    p: float = Field(..., description="Proportional band (0 to full scale)")
    i: float = Field(..., description="Integral time (0-3600)")
    d: float = Field(..., description="Derivative time (0-3600)")


class FlowSetpointUpdate(BaseModel):
    value: float = Field(..., description="Flow setpoint value")


class CommandResponse(BaseModel):
    success: bool
    message: str


class SerialConfig(BaseModel):
    port: str = Field(default="/dev/ttyUSB0", description="Serial port name (Linux: /dev/ttyUSB0, Windows: COM3)")
    baudrate: int = Field(default=4800, ge=1200, le=38400)
    slave_address: int = Field(default=1, ge=0, le=128)
    data_bits: int = Field(default=8, ge=7, le=8)
    parity: str = Field(default="N", pattern="^[NEO]$")
    stop_bits: int = Field(default=2, ge=1, le=2)


class WSPushData(BaseModel):
    temperature: Optional[float] = None
    flow_rate: Optional[float] = None
    running_time: Optional[int] = None
    indicators: dict = Field(default_factory=dict)
    connection: ConnectionState = ConnectionState.DISCONNECTED
    timestamp: float = 0.0
