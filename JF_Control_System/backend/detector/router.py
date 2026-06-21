"""Detector REST API routes — /api/detector/*"""
import os
from typing import Dict
from fastapi import APIRouter, HTTPException, Body
from backend.models import CommandResponse
from backend.detector.service import DetectorService
from pydantic import BaseModel

router = APIRouter(prefix="/api/detector", tags=["detector"])

_detector = DetectorService()


class ConnectRequest(BaseModel):
    hostname: str
    config_params: Dict[str, str] = {}


class LoadConfigRequest(BaseModel):
    path: str


class SetParamRequest(BaseModel):
    key: str
    value: str


class StartReceiverRequest(BaseModel):
    port: int = 1954


@router.post("/connect")
async def connect(req: ConnectRequest):
    try:
        _detector.connect(req.hostname, req.config_params)
        return CommandResponse(success=True, message="Connected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load_config")
async def load_config(req: LoadConfigRequest):
    try:
        params = _detector.load_config_file(req.path)
        return CommandResponse(success=True, message=f"Config loaded: {dict(params)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect():
    try:
        _detector.disconnect()
        return CommandResponse(success=True, message="Disconnected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    try:
        return _detector.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/temperatures")
async def get_temperatures():
    try:
        return _detector.get_temperatures()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/params")
async def get_params():
    try:
        return _detector.get_params()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/params")
async def set_param(req: SetParamRequest):
    try:
        _detector.set_param(req.key, req.value)
        return CommandResponse(success=True, message=f"Set {req.key}={req.value}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acquire/start")
async def start_acquire():
    try:
        _detector.start_acquisition()
        return CommandResponse(success=True, message="Acquisition started")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acquire/stop")
async def stop_acquire():
    try:
        _detector.stop_acquisition()
        return CommandResponse(success=True, message="Acquisition stopped")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/receiver/start")
async def start_receiver(req: StartReceiverRequest):
    try:
        _detector.start_receiver(req.port)
        return CommandResponse(success=True, message="Receiver started")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/receiver/stop")
async def stop_receiver():
    try:
        _detector.stop_receiver()
        return CommandResponse(success=True, message="Receiver stopped")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/browse")
async def browse_files(path: str = "."):
    try:
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        dirs = []
        files = []
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                dirs.append({"name": entry, "path": full})
            else:
                files.append({"name": entry, "path": full})
        dirs.sort(key=lambda d: d["name"].lower())
        files.sort(key=lambda f: f["name"].lower())
        parent = os.path.dirname(path)
        if parent == path:
            parent = None
        return {"current": path, "parent": parent, "dirs": dirs, "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_history(limit: int = 50, offset: int = 0):
    try:
        return _detector.get_history(limit, offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Mode control (added for Agent integration) ──

class SetModeRequest(BaseModel):
    mode: str  # "baseline" | "signal"


@router.post("/mode")
async def set_mode(req: SetModeRequest):
    try:
        _detector.acq_mode = req.mode
        return CommandResponse(success=True, message=f"Mode set to {req.mode}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Visual processing (added for Agent + frontend integration) ──

import glob as _glob


@router.post("/visual/process")
async def process_visual():
    """Process the most recent acquisition and return heatmap data."""
    if not _detector.connected:
        raise HTTPException(status_code=400, detail="Detector not connected")
    if _detector.acquiring:
        raise HTTPException(status_code=400, detail="Acquisition still in progress")

    try:
        params = _detector.get_params()
        fpath = params.get("fpath", "")
        fname = params.get("fname", "")
        if not fpath or not fname:
            raise HTTPException(status_code=400, detail="fpath/fname not configured")

        # Find the latest raw file (500K: single file)
        pattern = os.path.join(fpath, f"{fname}_d0_f0_*.raw")
        files = sorted(_glob.glob(pattern))
        if not files:
            raise HTTPException(status_code=404, detail=f"No raw files found: {pattern}")

        raw_paths = [files[-1]]  # Use latest file
        result = _detector.process_acquisition_visual(raw_paths)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Shutdown (added for Agent + frontend integration) ──

import asyncio as _asyncio


@router.post("/shutdown")
async def shutdown():
    """Safe shutdown: stop acquisition, receiver, high voltage, power chip, free shared memory."""
    try:
        loop = _asyncio.get_event_loop()
        await loop.run_in_executor(None, _detector.shutdown)
        return CommandResponse(success=True, message="Detector shutdown complete")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
