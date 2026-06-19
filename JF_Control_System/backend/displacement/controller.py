import serial
import serial.tools.list_ports
import time
import threading


class AriesController:
    """ARIES/LYNX 位移台控制器 RS-232C 通信封装"""

    def __init__(self, port="COM1", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def connect(self):
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=5,
        )
        time.sleep(0.1)

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    @property
    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    # ------------------------------------------------------------------
    # 底层通信
    # ------------------------------------------------------------------
    def send_command(self, command):
        if not self.is_connected:
            raise ConnectionError("串口未打开")
        with self._lock:
            full = b"\x02" + command.strip().encode("ascii") + b"\r\n"
            self.ser.write(full)
            time.sleep(0.1)
            resp = self.ser.readline().decode("ascii").strip()
            return resp

    def wait_until_stop(self, axis, max_checks=200, interval=0.15):
        for _ in range(max_checks):
            resp = self.send_command(f"STR{axis}")
            if resp.startswith("C"):
                parts = resp.split("\t")
                if len(parts) >= 3 and parts[2] == "0":
                    return True
            elif resp.startswith("E"):
                return False
            time.sleep(interval)
        return False

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def read_position(self, axis):
        """返回当前脉冲位置 (int)"""
        resp = self.send_command(f"RDP{axis}")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 3:
                return int(parts[2])
        return None

    def read_status(self, axis):
        """返回解析后的状态字典"""
        resp = self.send_command(f"STR{axis}")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 7:
                drive_state_map = {"0": "停止", "1": "运行中", "2": "反馈运行中"}
                emg_map = {"0": "OFF", "1": "ON"}
                org_norg_map = {
                    "0": "ORG OFF, NORG OFF",
                    "1": "ORG OFF, NORG ON",
                    "2": "ORG ON, NORG OFF",
                    "3": "ORG ON, NORG ON",
                }
                cw_ccw_map = {
                    "0": "CW OFF, CCW OFF",
                    "1": "CW OFF, CCW ON",
                    "2": "CW ON, CCW OFF",
                    "3": "CW ON, CCW ON",
                }
                soft_limit_map = {"0": "正常", "1": "+侧超限", "2": "-侧超限"}
                return {
                    "axis": parts[1],
                    "drive_state": parts[2],
                    "drive_state_text": drive_state_map.get(parts[2], parts[2]),
                    "emg": parts[3],
                    "emg_text": emg_map.get(parts[3], parts[3]),
                    "org_norg": parts[4],
                    "org_norg_text": org_norg_map.get(parts[4], parts[4]),
                    "cw_ccw": parts[5],
                    "cw_ccw_text": cw_ccw_map.get(parts[5], parts[5]),
                    "soft_limit": parts[6],
                    "soft_limit_text": soft_limit_map.get(parts[6], parts[6]),
                }
        return None

    def read_servo_status(self, axis):
        resp = self.send_command(f"RSV{axis}")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 5:
                return {
                    "servo_ready": parts[2],
                    "servo_on": parts[3],
                    "in_position": parts[4],
                    "servo_alarm": parts[5],
                }
        return None

    def check_origin_complete(self, axis):
        resp = self.send_command(f"ROG{axis}")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 3:
                return parts[2] == "1"
        return None

    def read_version(self):
        resp = self.send_command("IDN")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 5:
                return {
                    "model": parts[2],
                    "major": parts[3],
                    "minor": parts[4],
                    "release": parts[5],
                }
        return None

    def read_axes_config(self):
        """读取设备配置"""
        resp = self.send_command("RAX")
        return resp if not resp.startswith("E") else None

    def read_speed_table(self, axis, table_no):
        resp = self.send_command(f"RTB{axis}/{table_no}")
        if resp.startswith("C"):
            parts = resp.split("\t")
            if len(parts) >= 10:
                accel_pattern_map = {"1": "矩形", "2": "梯形", "3": "S形"}
                return {
                    "axis": parts[1],
                    "table_no": parts[2],
                    "start_speed": parts[3],
                    "top_speed": parts[4],
                    "accel_time": parts[5],
                    "decel_time": parts[6],
                    "accel_pattern": parts[7],
                    "accel_pattern_text": accel_pattern_map.get(
                        parts[7], parts[7]
                    ),
                    "accel_pulses": parts[8],
                    "decel_pulses": parts[9],
                }
        return None

    # ------------------------------------------------------------------
    # 驱动命令
    # ------------------------------------------------------------------
    def move_absolute(self, axis, speed_table, position, response_mode=0):
        """绝对位置移动, response_mode: 0=完成型, 1=快速型"""
        cmd = f"APS{axis}/{speed_table}/{int(position)}/{response_mode}"
        resp = self.send_command(cmd)
        return not resp.startswith("E")

    def move_relative(self, axis, speed_table, offset, response_mode=1):
        """相对位置移动, response_mode: 0=完成型, 1=快速型"""
        cmd = f"RPS{axis}/{speed_table}/{int(offset)}/{response_mode}"
        resp = self.send_command(cmd)
        return not resp.startswith("E")

    def free_rotation(self, axis, speed_table, direction):
        """连续旋转, direction: 0=CW, 1=CCW"""
        cmd = f"FRP{axis}/{speed_table}/{direction}"
        resp = self.send_command(cmd)
        return not resp.startswith("E")

    def stop(self, axis=0, mode=0):
        """停止, axis=0 全部轴, mode: 0=减速停止, 1=急停"""
        cmd = f"STP{axis}/{mode}"
        resp = self.send_command(cmd)
        return not resp.startswith("E")

    def origin_return(self, axis, speed_table=0, response_mode=0):
        cmd = f"ORG{axis}/{speed_table}/{response_mode}"
        resp = self.send_command(cmd)
        return not resp.startswith("E")

    def system_reset(self):
        resp = self.send_command("RST")
        return not resp.startswith("E")

    def emergency_stop_release(self):
        resp = self.send_command("REM")
        return not resp.startswith("E")

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def list_ports():
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]
