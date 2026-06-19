"""Unified WebSocket manager — pushes all module states to connected clients."""
import asyncio
import time
from typing import Set
from fastapi import WebSocket

from backend.models import WsPushData, WsDisplacementData, WsChillerData, WsDetectorData


class WsManager:
    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._get_displacement_status = lambda: {"connected": False}
        self._get_chiller_status = lambda: {"connected": False}
        self._get_detector_status = lambda: {"connected": False}

    def set_status_callbacks(self, displacement_cb, chiller_cb, detector_cb):
        """Register callbacks for collecting status from each module."""
        self._get_displacement_status = displacement_cb
        self._get_chiller_status = chiller_cb
        self._get_detector_status = detector_cb

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients.difference_update(dead)

    async def start_broadcast_loop(self):
        """Background loop: collect status from all modules and push every 500ms."""
        while True:
            try:
                payload = WsPushData(timestamp=time.time())

                # Displacement
                try:
                    d = self._get_displacement_status()
                    payload.displacement = WsDisplacementData(
                        connected=d.get("connected", False),
                        position=d.get("position", 0.0) or 0.0,
                        drive_state=str(d.get("status", [""])[0]) if d.get("status") else "",
                        origin_complete=d.get("origin_complete", False),
                        scan_running=(d.get("scan") or {}).get("running", False),
                        scan_current=(d.get("scan") or {}).get("current_step", 0),
                        scan_total=(d.get("scan") or {}).get("total_steps", 0),
                    )
                except Exception:
                    pass

                # Chiller
                try:
                    c = self._get_chiller_status()
                    indicators = c.get("indicators", {})
                    if not isinstance(indicators, dict):
                        indicators = {}
                    payload.chiller = WsChillerData(
                        connected=c.get("connected", False) or c.get("connection") == "connected",
                        temperature=c.get("temperature"),
                        flow_rate=c.get("flow_rate"),
                        indicators=indicators,
                    )
                except Exception:
                    pass

                # Detector
                try:
                    det = self._get_detector_status()
                    payload.detector = WsDetectorData(
                        connected=det.get("connected", False),
                        fpga_temp=det.get("fpga_temp"),
                        adc_temp=det.get("adc_temp"),
                        hv=det.get("hv"),
                        acquiring=det.get("acquiring", False),
                        frames_done=det.get("frames_done", 0),
                    )
                except Exception:
                    pass

                await self.broadcast(payload.model_dump())
            except Exception:
                pass
            await asyncio.sleep(0.5)


# Singleton
ws_manager = WsManager()
