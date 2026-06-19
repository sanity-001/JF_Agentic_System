"""Water chiller REST API routes -- /api/chiller/*"""
import serial.tools.list_ports
from fastapi import APIRouter, HTTPException
from backend.models import CommandResponse
from backend.chiller.service import ChillerService
from pydantic import BaseModel

router = APIRouter(prefix="/api/chiller", tags=["chiller"])

_chiller = ChillerService(simulation=False)


class ConnectRequest(BaseModel):
    port: str = "COM3"
    baudrate: int = 4800
    slave_address: int = 1


class SetpointRequest(BaseModel):
    value: float


class PIDRequest(BaseModel):
    p: float
    i: float
    d: float


@router.get("/ports")
async def list_ports():
    ports = serial.tools.list_ports.comports()
    return {"ports": [p.device for p in ports]}


@router.post("/connect")
async def connect(req: ConnectRequest):
    try:
        config = {"port": req.port, "baudrate": req.baudrate, "slave_address": req.slave_address}
        await _chiller.connect_async(config)
        return CommandResponse(success=True, message="Connected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect():
    try:
        await _chiller.disconnect_async()
        return CommandResponse(success=True, message="Disconnected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    return await _chiller.get_status_async()


@router.get("/params")
async def get_params():
    try:
        return await _chiller.get_params()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setpoint")
async def set_setpoint(req: SetpointRequest):
    try:
        await _chiller.set_temperature_sp(req.value)
        return CommandResponse(success=True, message=f"Setpoint set to {req.value}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alarm")
async def set_alarm(req: SetpointRequest):
    try:
        await _chiller.set_alarm_limit(req.value)
        return CommandResponse(success=True, message=f"Alarm limit set to {req.value}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deviation")
async def set_deviation(req: SetpointRequest):
    try:
        await _chiller.set_deviation(req.value)
        return CommandResponse(success=True, message=f"Deviation set to {req.value}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pid")
async def set_pid(req: PIDRequest):
    try:
        await _chiller.set_pid(req.p, req.i, req.d)
        return CommandResponse(success=True, message=f"PID set P={req.p} I={req.i} D={req.d}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start():
    try:
        await _chiller.start_chiller()
        return CommandResponse(success=True, message="Chiller started")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop():
    try:
        await _chiller.stop_chiller()
        return CommandResponse(success=True, message="Chiller stopped")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autotune")
async def autotune():
    try:
        await _chiller.start_autotune()
        return CommandResponse(success=True, message="Auto-tuning started")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mute")
async def mute():
    try:
        await _chiller.mute_buzzer()
        return CommandResponse(success=True, message="Buzzer muted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
