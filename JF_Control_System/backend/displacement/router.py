"""Displacement stage REST API routes — /api/displacement/*"""
from fastapi import APIRouter, HTTPException
from backend.models import CommandResponse
from backend.displacement.service import DisplacementService
from pydantic import BaseModel

router = APIRouter(prefix="/api/displacement", tags=["displacement"])

_stage = DisplacementService()


class ConnectRequest(BaseModel):
    port: str
    baudrate: int = 115200


class MoveAbsoluteRequest(BaseModel):
    axis: int = 1
    position: float
    speed_table: int = 0


class MoveRelativeRequest(BaseModel):
    axis: int = 1
    offset: float
    speed_table: int = 0


class FreeRotationRequest(BaseModel):
    axis: int = 1
    speed_table: int = 0
    direction: int = 0


class StopRequest(BaseModel):
    axis: int = 0
    mode: int = 0


class OriginReturnRequest(BaseModel):
    axis: int = 1
    speed_table: int = 0
    response_mode: int = 1


class ScanStartRequest(BaseModel):
    axis: int = 1
    direction: int = 0
    step_size: float = 1.0
    steps: int = 10
    speed_table: int = 0
    pause_ms: int = 500


@router.get("/ports")
async def list_ports():
    ports = _stage.list_ports()
    return {"ports": ports}


@router.post("/connect")
async def connect(req: ConnectRequest):
    ok = _stage.connect(req.port, req.baudrate)
    if ok:
        return CommandResponse(success=True, message=f"Connected to {req.port}")
    else:
        raise HTTPException(status_code=500, detail="Connection failed")


@router.post("/disconnect")
async def disconnect():
    _stage.disconnect()
    return CommandResponse(success=True, message="Disconnected")


@router.get("/status/{axis}")
async def get_status(axis: int = 1):
    return _stage.get_status(axis)


@router.post("/move/absolute")
async def move_absolute(req: MoveAbsoluteRequest):
    ok = _stage.move_absolute(req.axis, req.position, req.speed_table)
    return CommandResponse(success=ok, message="Move complete" if ok else "Move failed")


@router.post("/move/relative")
async def move_relative(req: MoveRelativeRequest):
    ok = _stage.move_relative(req.axis, req.offset, req.speed_table)
    return CommandResponse(success=ok, message="Move complete" if ok else "Move failed")


@router.post("/move/free")
async def free_rotation(req: FreeRotationRequest):
    ok = _stage.free_rotation(req.axis, req.speed_table, req.direction)
    return CommandResponse(success=ok, message="Free rotation started" if ok else "Free rotation failed")


@router.post("/stop")
async def stop(req: StopRequest):
    ok = _stage.stop(req.axis, req.mode)
    return CommandResponse(success=ok, message="Stopped")


@router.post("/origin")
async def origin_return(req: OriginReturnRequest):
    ok = _stage.origin_return(req.axis, req.speed_table, req.response_mode)
    return CommandResponse(success=ok, message="Origin return started" if ok else "Origin return failed")


@router.post("/reset")
async def system_reset():
    ok = _stage.system_reset()
    return CommandResponse(success=ok, message="System reset complete" if ok else "Reset failed")


@router.post("/emergency/release")
async def emergency_release():
    ok = _stage.emergency_release()
    return CommandResponse(success=ok, message="Emergency released" if ok else "Release failed")


@router.get("/wait/{axis}")
async def wait_until_stop(axis: int = 1):
    ok = _stage.wait_until_stop(axis)
    return CommandResponse(success=ok, message="Axis stopped" if ok else "Wait timeout or error")


@router.post("/scan/start")
async def start_scan(req: ScanStartRequest):
    ok = _stage.start_scan(req.axis, req.direction, req.step_size,
                            req.steps, req.speed_table, req.pause_ms)
    return CommandResponse(success=ok, message="Scan started" if ok else "Scan already running")


@router.post("/scan/stop")
async def stop_scan():
    _stage.stop_scan()
    return CommandResponse(success=True, message="Scan stopped")


@router.get("/scan/state")
async def get_scan_state():
    return _stage.get_scan_state()
