"""Displacement stage service — thin wrapper around original AriesController."""
import threading
import time
from .controller import AriesController


class DisplacementService:
    """Thin wrapper delegating to original AriesController."""

    def __init__(self):
        self._ctrl: AriesController = None
        self._lock = threading.Lock()
        self._scan_thread = None
        self._scan_state = {"running": False, "current_step": 0, "total_steps": 0}

    @staticmethod
    def list_ports():
        return AriesController.list_ports()

    def connect(self, port: str, baudrate: int = 115200):
        with self._lock:
            if self._ctrl and self._ctrl.is_connected:
                self._ctrl.disconnect()
            if self._ctrl is None:
                self._ctrl = AriesController(port=port, baudrate=baudrate)
            else:
                self._ctrl.port = port
                self._ctrl.baudrate = baudrate
            self._ctrl.connect()
            return self._ctrl.is_connected

    def disconnect(self):
        with self._lock:
            if self._ctrl:
                self._ctrl.disconnect()
            return True

    @property
    def is_connected(self) -> bool:
        return self._ctrl is not None and self._ctrl.is_connected

    def get_status(self, axis: int = 1):
        if not self.is_connected:
            return {"connected": False}
        with self._lock:
            pos = self._ctrl.read_position(axis)
            raw_status = self._ctrl.read_status(axis)
            servo = self._ctrl.read_servo_status(axis)
            origin = self._ctrl.check_origin_complete(axis)
        return {
            "connected": True,
            "position": pos,
            "status": raw_status,
            "servo": servo,
            "origin_complete": origin,
            "scan": dict(self._scan_state),
        }

    def move_absolute(self, axis: int, position: float, speed_table: int = 0):
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.move_absolute(axis, speed_table, position, response_mode=1)

    def move_relative(self, axis: int, offset: float, speed_table: int = 0):
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.move_relative(axis, speed_table, offset, response_mode=1)

    def free_rotation(self, axis: int, speed_table: int = 0, direction: int = 0):
        """Continuous rotation. direction: 0=CW, 1=CCW."""
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.free_rotation(axis, speed_table, direction)

    def stop(self, axis: int = 0, mode: int = 0):
        """Stop movement. axis=0 means all axes. mode: 0=decel stop, 1=emergency stop."""
        if not self.is_connected:
            return False
        self._scan_state["running"] = False
        with self._lock:
            return self._ctrl.stop(axis, mode)

    def origin_return(self, axis: int = 1, speed_table: int = 0, response_mode: int = 0):
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.origin_return(axis, speed_table, response_mode)

    def system_reset(self):
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.system_reset()

    def emergency_release(self):
        if not self.is_connected:
            return False
        with self._lock:
            return self._ctrl.emergency_stop_release()

    def wait_until_stop(self, axis: int = 1, max_checks: int = 200, interval: float = 0.15):
        if not self.is_connected:
            return False
        return self._ctrl.wait_until_stop(axis, max_checks, interval)

    def start_scan(self, axis: int, direction: int, step_size: float,
                   steps: int, speed_table: int, pause_ms: int):
        if self._scan_state["running"]:
            return False
        self._scan_state = {"running": True, "current_step": 0, "total_steps": steps}
        self._scan_thread = threading.Thread(
            target=self._do_scan,
            args=(axis, direction, step_size, steps, speed_table, pause_ms),
            daemon=True,
        )
        self._scan_thread.start()
        return True

    def _do_scan(self, axis, direction, step_size, steps, speed_table, pause_ms):
        sign = 1 if direction == 0 else -1
        offset = sign * step_size
        for i in range(steps):
            if not self._scan_state["running"]:
                break
            self._scan_state["current_step"] = i + 1
            with self._lock:
                ok = self._ctrl.move_relative(axis, speed_table, offset, response_mode=1)
            if not ok:
                self._scan_state["running"] = False
                break
            with self._lock:
                self._ctrl.wait_until_stop(axis)
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)
        self._scan_state["running"] = False

    def stop_scan(self):
        self._scan_state["running"] = False

    def get_scan_state(self):
        return dict(self._scan_state)
