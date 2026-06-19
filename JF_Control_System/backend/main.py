"""JF_Control_System — Unified FastAPI backend."""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.ws_manager import ws_manager

# Suppress uvicorn access logs for poll endpoints
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup: register status callbacks and start broadcast loop
    import asyncio as _asyncio

    def get_disp_status():
        try:
            from backend.displacement.router import _stage
            return _stage.get_status(axis=1)
        except Exception:
            return {"connected": False}

    def get_ch_status():
        try:
            from backend.chiller.router import _chiller
            return _chiller.get_status_sync()
        except Exception:
            return {"connected": False}

    def get_det_status():
        try:
            from backend.detector.router import _detector
            return _detector.get_status()
        except Exception:
            return {"connected": False}

    ws_manager.set_status_callbacks(get_disp_status, get_ch_status, get_det_status)

    # Start the broadcast loop as a background task
    broadcast_task = _asyncio.create_task(ws_manager.start_broadcast_loop())

    yield

    # Shutdown: cancel broadcast
    broadcast_task.cancel()
    try:
        await broadcast_task
    except _asyncio.CancelledError:
        pass


app = FastAPI(title="JF Control System", lifespan=lifespan)

from backend.detector.router import router as detector_router
app.include_router(detector_router)

from backend.displacement.router import router as displacement_router
app.include_router(displacement_router)

from backend.chiller.router import router as chiller_router
app.include_router(chiller_router)

from backend.processing.router import router as processing_router
app.include_router(processing_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    return {
        "displacement": {"default_port": "COM1", "default_baudrate": 115200},
        "chiller": {"default_port": "/dev/ttyUSB0", "default_baudrate": 4800},
    }
