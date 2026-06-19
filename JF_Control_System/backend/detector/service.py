"""Detector service — thin wrapper around original JF_acquire_control DetectorService.

Original source files (data_io.py, stitching.py, config_manager.py, history_store.py,
detector_service.py) are copied into this directory and imported directly.
"""
from typing import Dict

from .detector_service import DetectorService as _OriginalDetectorService
from .config_manager import (
    parse_config,
    generate_config,
    validate_params,
    detect_detector_type,
)
from .data_io import DataIO
from .history_store import HistoryStore


class DetectorService:
    """Thin wrapper delegating to original DetectorService."""

    def __init__(self):
        self._original = _OriginalDetectorService()

    def connect(self, hostname: str, config_params: Dict[str, str]):
        return self._original.connect(hostname, config_params)

    def load_config_file(self, path: str):
        return self._original.load_config_file(path)

    def disconnect(self):
        return self._original.disconnect()

    def get_status(self):
        return self._original.get_status()

    def get_temperatures(self):
        return self._original.get_temperatures()

    def get_params(self):
        return self._original.get_params()

    def set_param(self, key: str, value: str):
        return self._original.set_param(key, value)

    def start_acquisition(self):
        return self._original.start_acquisition()

    def stop_acquisition(self):
        return self._original.stop_acquisition()

    def start_receiver(self, port: int = 1954):
        return self._original.start_receiver(port)

    def stop_receiver(self):
        return self._original.stop_receiver()

    @property
    def connected(self) -> bool:
        return self._original.connected

    @property
    def acquiring(self) -> bool:
        return self._original.acquiring

    @property
    def receiver_running(self) -> bool:
        return self._original.receiver_running

    @property
    def is_4m(self) -> bool:
        return self._original.is_4m

    def get_history(self, limit: int = 50, offset: int = 0):
        import asyncio
        import concurrent.futures
        hs = HistoryStore()
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    lambda: asyncio.run(self._get_history_async(hs, limit, offset))
                ).result(timeout=10)
        except RuntimeError:
            return asyncio.run(self._get_history_async(hs, limit, offset))

    async def _get_history_async(self, hs: HistoryStore, limit: int, offset: int):
        await hs.init()
        try:
            return await hs.list(limit=limit, offset=offset)
        finally:
            await hs.close()
