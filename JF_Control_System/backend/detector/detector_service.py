import os
import signal
import subprocess
import tempfile
import threading
import time
from typing import Dict, Any, List, Optional
import numpy as np
from .data_io import DataIO

try:
    import slsdet
    HAS_SLSDET = True
except ImportError:
    slsdet = None
    HAS_SLSDET = False

# freeSharedMemory: 旧版在 _slsdet，新版直接在 slsdet 里
try:
    from _slsdet import freeSharedMemory
except ImportError:
    try:
        freeSharedMemory = slsdet.freeSharedMemory if slsdet else None
    except AttributeError:
        freeSharedMemory = None


class DetectorService:
    def __init__(self):
        self._detector = None
        self._connected = False
        self._lock = threading.Lock()
        self._acquiring = False
        self._acq_done = False
        self._acq_duration = 0
        self._receiver_proc: Optional[subprocess.Popen] = None
        self._receiver_port = 1954
        self._acq_mode: str = "signal"  # "baseline" | "signal"
        self._acq_thread = None
        self._stop_pipe_w = None
        self._result: Optional[np.ndarray] = None
        self._data_io = DataIO()
        # 4M support
        self._is_4m = False
        self._baselines: Dict[str, np.ndarray] = {}  # module_id → baseline array
        self._module_averages: Dict[str, np.ndarray] = {}  # cached for re-stitch

    def connect(self, hostname: str, config_params: Dict[str, str]) -> bool:
        if slsdet is None:
            raise RuntimeError("slsdet package not available")
        with self._lock:
            # 启动 Receiver（必须在配置探测器之前）
            if not self.receiver_running:
                self.start_receiver()
            # 构建配置内容，rx_hostname 放在 hostname 前面
            lines = []
            if "rx_hostname" not in config_params:
                lines.append("rx_hostname localhost")
            for key, value in config_params.items():
                if key == "hostname":
                    continue
                lines.append(f"{key} {value}")
            lines.append(f"hostname {hostname}")
            config_text = "\n".join(lines) + "\n"
            # 写入临时文件，用 d.config 一次性加载（slsdet 推荐方式）
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".config", delete=False
            ) as f:
                f.write(config_text)
                tmp_path = f.name
            try:
                self._detector = slsdet.Detector()
                self._detector.config = tmp_path
                self._connected = True
                # Auto-detect detector type
                from .config_manager import detect_detector_type
                self._is_4m = detect_detector_type(config_params) == "4M"
            finally:
                import os
                os.unlink(tmp_path)
        return True

    def disconnect(self):
        self.stop_receiver()
        with self._lock:
            self._connected = False
            self._detector = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def acquiring(self) -> bool:
        return self._acquiring

    @property
    def receiver_running(self) -> bool:
        return self._receiver_proc is not None and self._receiver_proc.poll() is None

    @property
    def is_4m(self) -> bool:
        return self._is_4m

    def set_detector_type(self, detector_type: str) -> None:
        """外部设置探测器类型（在加载配置文件之前调用）."""
        self._is_4m = (detector_type == "4M")

    @staticmethod
    def _cleanup_orphan_receivers():
        """清理可能存在的孤儿 receiver 进程（后端重启后残留）."""
        import subprocess as sp
        for name in ("slsMultiReceiver", "slsReceiver"):
            try:
                sp.run(
                    ["pkill", "-x", name],
                    timeout=5,
                    stdout=sp.DEVNULL,
                    stderr=sp.DEVNULL,
                )
            except Exception:
                pass
        time.sleep(0.5)  # 等待端口释放

    def start_receiver(self, port: int = 1954) -> bool:
        if self.receiver_running:
            raise RuntimeError("Receiver already running")
        # 清理可能存在的孤儿进程（后端重启后残留）
        self._cleanup_orphan_receivers()
        if self._is_4m:
            cmd = ["slsMultiReceiver", "1952", "8"]
            self._receiver_port = 1952
        else:
            self._receiver_port = port
            cmd = ["slsReceiver", "-t", str(port)]
        self._receiver_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            preexec_fn=os.setpgrp,  # 放入独立进程组，方便 stop 时整组发信号
        )
        # 等待 receiver 进程就绪并检查是否立即退出
        time.sleep(1.5)
        if self._receiver_proc.poll() is not None:
            exit_code = self._receiver_proc.returncode
            stderr_output = self._receiver_proc.stderr.read().decode(errors="replace").strip()
            self._receiver_proc = None
            msg = f"slsReceiver failed to start (exit code: {exit_code})"
            if stderr_output:
                msg += f"\nstderr: {stderr_output}"
            raise RuntimeError(msg)
        return True

    def stop_receiver(self):
        if self._receiver_proc is None:
            return
        proc = self._receiver_proc
        self._receiver_proc = None
        # 模拟 Ctrl+C：先发 SIGINT 给整个进程组（父+所有子进程）
        # 不行再 escalate 到 SIGTERM → SIGKILL
        try:
            os.killpg(proc.pid, signal.SIGINT)
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def get_status(self) -> Dict[str, Any]:
        if not self._connected or not self._detector:
            return {"connected": False, "receiver_running": self.receiver_running}
        d = self._detector
        return {
            "connected": True,
            "receiver_running": self.receiver_running,
            "chip_version": d.chipversion if hasattr(d, "chipversion") else "N/A",
            "status": str(d.status) if d.status is not None else "unknown",
            "acquiring": self._acquiring,
        }

    def get_temperatures(self) -> Dict[str, Any]:
        """读取温度：FPGA 和 ADC，优先使用 dacIndex（参考 slsdet 示例用法）"""
        if not self._connected or not self._detector:
            return {}
        d = self._detector
        result = {}
        sensors = [
            ("fpga", "TEMPERATURE_FPGA"),
            ("adc",  "TEMPERATURE_ADC"),
        ]
        for key, enum_name in sensors:
            try:
                # 优先 slsdet.dacIndex（用户示例用法）
                if hasattr(slsdet, "dacIndex"):
                    ev = getattr(slsdet.dacIndex, enum_name, None)
                    if ev is not None:
                        vals = d.getTemperature(ev)
                        if vals is not None:
                            result[key] = list(vals) if hasattr(vals, "__iter__") else [vals]
                            continue
                # 回退到 slsdet.temperature
                if hasattr(slsdet, "temperature"):
                    ev = getattr(slsdet.temperature, enum_name, None)
                    if ev is not None:
                        vals = d.getTemperature(ev)
                        if vals is not None:
                            result[key] = list(vals) if hasattr(vals, "__iter__") else [vals]
            except Exception:
                pass
        return result

    def get_params(self) -> Dict[str, str]:
        if not self._connected or not self._detector:
            return {}
        d = self._detector
        params = {}
        for attr in ["hostname", "exptime", "frames", "period", "highvoltage",
                      "powerchip", "timing", "fpath", "fname", "fwrite", "readoutspeed"]:
            if hasattr(d, attr):
                val = getattr(d, attr)
                params[attr] = self._normalize_param(attr, val)
        return params

    def _normalize_param(self, name: str, val) -> str:
        """将 slsdet 内部类型归一化为前端期望的字符串"""
        if name == "timing":
            return self._timing_to_str(val)
        if name == "exptime":
            return self._format_num(float(val) * 1_000_000)
        if name == "period":
            return self._format_num(float(val) * 1_000)
        if name == "powerchip":
            if isinstance(val, bool):
                return "1" if val else "0"
            if isinstance(val, (int, float)):
                return "1" if val else "0"
        if name == "fwrite":
            if isinstance(val, bool):
                return "True" if val else "False"
            if isinstance(val, (int, float)):
                return "True" if val else "False"
        if name == "readoutspeed":
            return self._speed_to_str(val)
        return str(val)

    def _collect_raw_files(self, data_path: str, fname: str, findex: int) -> List[str]:
        """收集采集生成的 raw 文件路径列表.
        500K: 1 个文件，4M: 8 个文件.
        """
        if self._is_4m:
            return [
                f"{data_path}/{fname}_d{i}_f0_{findex - 1}.raw"
                for i in range(8)
            ]
        else:
            return [f"{data_path}/{fname}_d0_f0_{findex - 1}.raw"]

    @staticmethod
    def _format_num(v: float) -> str:
        """数字转字符串，去除多余的 .0 后缀"""
        if v == int(v):
            return str(int(v))
        return f"{v:.1f}"

    def _timing_to_str(self, val) -> str:
        """timingMode 枚举 → 'auto'/'trigger'"""
        s = str(val).lower()
        if "auto" in s:    return "auto"
        if "trigger" in s: return "trigger"
        return s

    def _str_to_timing(self, value: str):
        """'auto' → timingMode.AUTO_TIMING, 'trigger' → timingMode.TRIGGER_EXPOSURE"""
        v = value.strip().lower()
        if hasattr(slsdet, "timingMode"):
            if "auto" in v:
                return slsdet.timingMode.AUTO_TIMING
            if "trigger" in v:
                return slsdet.timingMode.TRIGGER_EXPOSURE
        return value

    def _speed_to_str(self, val) -> str:
        """speedLevel 枚举 → 'full_speed'/'half_speed'/'quarter_speed'"""
        s = str(val).lower()
        if "full" in s:    return "full_speed"
        if "half" in s:    return "half_speed"
        if "quarter" in s: return "quarter_speed"
        return s

    @staticmethod
    def _str_to_bool(value: str) -> str:
        """'True'/'False'/'1'/'0' → '1'/'0'"""
        v = value.strip().lower()
        if v in ("true", "1"):
            return "1"
        if v in ("false", "0"):
            return "0"
        return value

    def _str_to_speed(self, value: str):
        """'half_speed' → speedLevel.HALF_SPEED 枚举，失败返回原值"""
        try:
            name = value.strip().upper().replace("_SPEED", "") + "_SPEED"
            if hasattr(slsdet, "speedLevel"):
                return getattr(slsdet.speedLevel, name)
        except Exception:
            pass
        return value

    def set_param(self, name: str, value: str) -> bool:
        if not self._connected or not self._detector:
            raise RuntimeError("Detector not connected")
        if self._acquiring and name in ("exptime", "frames", "period"):
            raise RuntimeError(f"Cannot change '{name}' during acquisition")
        d = self._detector
        if hasattr(d, name):
            current = getattr(d, name)
            if name == "readoutspeed":
                value = self._str_to_speed(value)
            elif name == "timing":
                value = self._str_to_timing(value)
            elif name == "exptime":
                value = str(float(value) / 1_000_000)
            elif name == "period":
                value = str(float(value) / 1_000)
            elif name in ("fwrite", "powerchip"):
                value = self._str_to_bool(value)
            if isinstance(current, int):
                setattr(d, name, int(value))
            elif isinstance(current, float):
                setattr(d, name, float(value))
            else:
                setattr(d, name, value)
            return True
        raise ValueError(f"Unknown parameter: {name}")

    def load_config_file(self, path: str) -> Dict[str, str]:
        """加载配置文件即建立连接，不需要预先 connected"""
        if slsdet is None:
            raise RuntimeError("slsdet package not available")
        self._detector = slsdet.Detector()
        self._detector.config = path
        self._connected = True
        # Auto-detect detector type (only if not already set by caller)
        if not self._is_4m:
            params = self.get_params()
            from .config_manager import detect_detector_type
            self._is_4m = detect_detector_type(params) == "4M"
        return self.get_params()

    def start_acquisition(self):
        if not self._connected or not self._detector:
            raise RuntimeError("Detector not connected")
        with self._lock:
            if self._acquiring:
                raise RuntimeError("Acquisition already in progress")
            self._acquiring = True
        self._acq_done = False
        # 创建管道：写端存下来供 stop 注入 'q'，读端传给采集线程当 stdin
        pipe_r, pipe_w = os.pipe()
        self._stop_pipe_w = pipe_w
        self._acq_thread = threading.Thread(
            target=self._run_acquire, args=(pipe_r,), daemon=True
        )
        self._acq_thread.start()

    def _run_acquire(self, pipe_r: int):
        """后台线程运行阻塞 acquire."""
        start = time.time()
        saved_stdin = os.dup(0)      # 保存原始 stdin
        os.dup2(pipe_r, 0)           # 将 fd 0 重定向到管道读端
        os.close(pipe_r)
        try:
            self._detector.acquire()
        except Exception:
            pass
        finally:
            os.dup2(saved_stdin, 0)  # 恢复原始 stdin
            os.close(saved_stdin)
            if self._stop_pipe_w is not None:
                os.close(self._stop_pipe_w)
                self._stop_pipe_w = None
            self._acq_duration = int((time.time() - start) * 1000)
            self._acq_done = True
            self._acquiring = False

    def stop_acquisition(self):
        """中止采集：往 stdin 管道写入 'q' 触发 acquire 优雅停止."""
        if not self._connected or not self._detector:
            self._acquiring = False
            return
        # 往管道写端写入 'q\n'，模拟终端按键
        # acquire() 内部轮询 stdin 读到 'q' 后自行返回
        try:
            if self._stop_pipe_w is not None:
                os.write(self._stop_pipe_w, b'q\n')
        except Exception:
            pass
        # 等后台线程返回
        if self._acq_thread and self._acq_thread.is_alive():
            self._acq_thread.join(timeout=10)
            if self._acq_thread.is_alive():
                print("[WARNING] acquire thread did not stop within 10s")
        self._acquiring = False

    @property
    def acq_mode(self) -> str:
        return self._acq_mode

    @acq_mode.setter
    def acq_mode(self, mode: str):
        if mode not in ("baseline", "signal"):
            raise ValueError("mode must be 'baseline' or 'signal'")
        self._acq_mode = mode

    @property
    def baseline(self) -> Optional[np.ndarray]:
        return self._baselines.get("d0") if self._baselines else None

    @property
    def result(self) -> Optional[np.ndarray]:
        return self._result

    def clear_baseline(self):
        """清除基线和结果."""
        self._baselines = {}
        self._module_averages = {}
        self._result = None

    @staticmethod
    def _read_one_module(data_io, path: str, module_id: str) -> tuple:
        """读取单个模块 raw 文件并返回平均帧（供 ThreadPoolExecutor 调用）."""
        try:
            avg = data_io.read_average_frames(path)
            return module_id, avg
        except Exception as e:
            print(f"[ERROR] Failed to read module {module_id} from {path}: {e}")
            return module_id, None

    def process_acquisition_visual(self, raw_paths: List[str]) -> dict:
        """采集完成后处理视觉数据.
        500K: 读单文件 → 平均 → 模式处理
        4M:  读 8 文件 → 各模块平均 → 拼接 → 模式处理
        """
        if self._is_4m:
            return self._process_4m_visual(raw_paths)
        else:
            return self._process_500k_visual(raw_paths[0])

    def _process_500k_visual(self, raw_path: str) -> dict:
        """500K 单模块视觉处理（原逻辑不变）."""
        avg = self._data_io.read_average_frames(raw_path)

        result_data = None
        baseline_data = None
        avail = list(self._baselines.keys())
        first_key = avail[0] if avail else "d0"
        existing_baseline = self._baselines.get(first_key)
        baseline_data = existing_baseline.tolist() if existing_baseline is not None else None

        if self._acq_mode == "baseline":
            self._baselines["d0"] = avg
            self._result = None
            baseline_data = avg.tolist()
        elif self._acq_mode == "signal":
            if existing_baseline is not None:
                result = avg - existing_baseline
                result = np.clip(result, 0, None)
                self._result = result
                result_data = result.tolist()

        arr = avg if self._result is None else self._result
        vmin = float(np.min(arr)) if arr.size > 0 else 0.0
        vmax = float(np.max(arr)) if arr.size > 0 else 100.0

        return {
            "baseline": baseline_data,
            "result": result_data,
            "vmin": vmin,
            "vmax": vmax,
            "shape": list(avg.shape),
            "is_4m": False,
            "expand": False,
        }

    def _process_4m_visual(self, raw_paths: List[str]) -> dict:
        """4M 八模块视觉处理：并行读取 → 模式处理 → 拼接."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from .stitching import (
            get_default_configs,
            insert_split_rows_and_cols,
            EightModuleProcessor,
        )

        module_ids = [f"d{i}" for i in range(8)]
        configs = get_default_configs()

        # 并行读取 8 个模块 raw 文件
        module_avgs: Dict[str, np.ndarray] = {}
        failed_modules: List[str] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(
                    self._read_one_module, self._data_io, path, mid
                )
                for mid, path in zip(module_ids, raw_paths)
            ]
            for future in as_completed(futures):
                mid, avg = future.result()
                if avg is not None:
                    module_avgs[mid] = avg
                else:
                    failed_modules.append(mid)

        if not module_avgs:
            raise RuntimeError("All 8 modules failed to read")

        # 缓存模块平均帧供 expand 切换用（仅成功模块）
        self._module_averages = module_avgs

        # 模式处理
        if self._acq_mode == "baseline":
            self._baselines = module_avgs
            self._result = None
            images_for_stitch = [module_avgs[mid] for mid in module_ids if mid in module_avgs]
        elif self._acq_mode == "signal":
            corrected: Dict[str, np.ndarray] = {}
            for mid in module_ids:
                if mid not in module_avgs:
                    continue
                baseline = self._baselines.get(mid)
                if baseline is None:
                    failed_modules.append(mid)
                    continue
                result = module_avgs[mid] - baseline
                result = np.clip(result, 0, None)
                corrected[mid] = result
            if not corrected:
                raise RuntimeError("No modules could be corrected. Check baselines.")
            self._result = None
            images_for_stitch = [corrected[mid] for mid in module_ids if mid in corrected]

        # 拼接（过滤掉失败模块的 configs，缺失模块在画布上留空）
        successful_ids = {mid for mid in module_ids if mid in module_avgs}
        successful_configs = [cfg for cfg in configs if cfg.module_id in successful_ids]
        processor = EightModuleProcessor(successful_configs)
        stitched = processor.stitch_images(images_for_stitch, expand=False)

        # 拼接 baseline（如有），用于前端切换显示
        baseline_data = None
        if self._baselines:
            baseline_ids = [mid for mid in module_ids if mid in self._baselines]
            baseline_images = [self._baselines[mid] for mid in baseline_ids]
            baseline_configs = [cfg for cfg in configs if cfg.module_id in self._baselines]
            baseline_processor = EightModuleProcessor(baseline_configs)
            baseline_stitched = baseline_processor.stitch_images(
                baseline_images, expand=False
            )
            baseline_data = baseline_stitched.tolist()

        result_data = None
        if self._acq_mode == "signal":
            result_data = stitched.tolist()

        vmin = float(np.min(stitched)) if stitched.size > 0 else 0.0
        vmax = float(np.max(stitched)) if stitched.size > 0 else 100.0

        return {
            "baseline": baseline_data,
            "result": result_data,
            "vmin": vmin,
            "vmax": vmax,
            "shape": list(stitched.shape),
            "is_4m": True,
            "expand": False,
            "failed_modules": failed_modules if failed_modules else None,
        }

    def restitch_with_expand(self, expand: bool) -> dict:
        """使用缓存的模块平均帧重新拼接（expand 切换用）."""
        if not self._module_averages:
            raise RuntimeError("No cached module averages. Run acquisition first.")

        from .stitching import (
            get_default_configs,
            insert_split_rows_and_cols,
            EightModuleProcessor,
        )

        module_ids = [f"d{i}" for i in range(8)]
        configs = get_default_configs()

        # 根据当前模式选择数据源
        if self._acq_mode == "baseline":
            source = self._baselines
        else:
            source = {}
            for mid in module_ids:
                if mid not in self._module_averages:
                    continue
                baseline = self._baselines.get(mid)
                if baseline is None:
                    continue
                corrected = self._module_averages[mid] - baseline
                corrected = np.clip(corrected, 0, None)
                source[mid] = corrected

        # 只使用有数据的模块
        available_ids = [mid for mid in module_ids if mid in source]
        images = []
        for mid in available_ids:
            img = source[mid]
            if expand:
                img = insert_split_rows_and_cols(img)
            images.append(img)

        successful_configs = [cfg for cfg in configs if cfg.module_id in source]
        processor = EightModuleProcessor(successful_configs)
        stitched = processor.stitch_images(images, expand=expand)

        baseline_data = None
        result_data = None
        if self._acq_mode == "baseline":
            baseline_data = stitched.tolist()
        else:
            result_data = stitched.tolist()

        vmin = float(np.min(stitched)) if stitched.size > 0 else 0.0
        vmax = float(np.max(stitched)) if stitched.size > 0 else 100.0

        return {
            "baseline": baseline_data,
            "result": result_data,
            "vmin": vmin,
            "vmax": vmax,
            "shape": list(stitched.shape),
            "is_4m": True,
            "expand": expand,
        }

    def shutdown(self):
        """安全关机：停止采集 → 降压 → 关powerchip → 释放共享内存"""
        self.stop_receiver()
        if not self._connected or not self._detector:
            return
        with self._lock:
            d = self._detector
            try:
                d.stopDetector()
            except Exception:
                pass
            time.sleep(0.5)
            try:
                d.stopReceiver()
            except Exception:
                pass
            time.sleep(0.5)
            try:
                d.highvoltage = 0
            except Exception:
                pass
            time.sleep(0.5)
            try:
                d.powerchip = 0
            except Exception:
                pass
            time.sleep(0.5)
            try:
                if freeSharedMemory is not None:
                    freeSharedMemory()
            except Exception:
                pass
            self._acquiring = False
            self._connected = False
            self._detector = None

    def get_acquisition_progress(self) -> Dict[str, Any]:
        if not self._connected or not self._detector:
            return {"acquiring": False}
        return {"acquiring": self._acquiring}
