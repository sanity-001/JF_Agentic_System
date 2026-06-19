"""Shared Pydantic models for JF_Control_System."""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class CommandResponse(BaseModel):
    success: bool
    message: str = ""


class WsDisplacementData(BaseModel):
    connected: bool = False
    position: float = 0.0
    drive_state: str = ""
    emg: bool = False
    origin_signal: bool = False
    limit_signal: bool = False
    servo_ready: bool = False
    origin_complete: bool = False
    scan_running: bool = False
    scan_current: int = 0
    scan_total: int = 0


class WsChillerData(BaseModel):
    connected: bool = False
    temperature: Optional[float] = None
    flow_rate: Optional[float] = None
    running: bool = False
    indicators: dict = {}


class WsDetectorData(BaseModel):
    connected: bool = False
    fpga_temp: Optional[float] = None
    adc_temp: Optional[float] = None
    hv: Optional[float] = None
    acquiring: bool = False
    frames_done: int = 0


class WsPushData(BaseModel):
    timestamp: float = 0.0
    displacement: WsDisplacementData = WsDisplacementData()
    chiller: WsChillerData = WsChillerData()
    detector: WsDetectorData = WsDetectorData()
