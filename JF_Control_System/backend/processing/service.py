"""Data processing service — wraps original JF_data_processing_system analysis code.

Original source files (core/ and image_sensor/ packages) are copied into this
directory and imported directly.
"""
import os
import base64
import tempfile
from io import BytesIO
from typing import Optional

import numpy as np

# Direct import from copied original packages
from .image_sensor import DataIO
from .image_sensor.image_processing import ImageProcessor
from .image_sensor.gain_analysis import compute_gainmap, compute_noisepeakmap
from .image_sensor.gaussian_fitting import fit_pixel_full

# PIL may not be available — fall back gracefully
try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class ProcessingService:
    """Wraps original ImageSensorProcessor and analysis functions."""

    def __init__(self):
        self._data_io = DataIO()
        self._image_processor = ImageProcessor()
        # Temp directory for gainmap/noisemap computation outputs (memmaps, .npy)
        self._temp_dir = os.path.join(tempfile.gettempdir(), "jf_processing_service")
        os.makedirs(self._temp_dir, exist_ok=True)

    def read_frame(self, file_path: str, frame_idx: int):
        """Read a single frame and return metadata + base64 images.

        Returns the image array, gain array, and frame metadata.
        """
        img_array, frame_number = self._data_io.read_frame(file_path, frame_idx)
        gain_array = self._data_io.read_gain_from_frame(file_path, frame_idx)

        result = {
            "frame_number": int(frame_number),
            "shape": list(img_array.shape),
            "min": float(np.min(img_array)),
            "max": float(np.max(img_array)),
            "mean": float(np.mean(img_array)),
            "std": float(np.std(img_array.astype(np.float64))),
        }
        if _HAS_PIL:
            result["image_base64"] = self._array_to_base64(img_array)
            result["gain_base64"] = self._gain_to_base64(gain_array)
        return result

    def read_average(self, file_path: str, start_frame: int, end_frame: int,
                     baseline_path: Optional[str] = None):
        """Compute average frame over a range, optionally subtract baseline."""
        avg = self._data_io.read_average_frames(file_path, start_frame, end_frame)
        baseline_subtracted = None
        if baseline_path:
            baseline = self._data_io.read_average_frames(baseline_path, 0, 0)
            baseline_subtracted = avg.astype(np.float64) - baseline.astype(np.float64)

        result = {
            "shape": list(avg.shape),
            "min": float(np.min(avg)),
            "max": float(np.max(avg)),
            "mean": float(np.mean(avg.astype(np.float64))),
            "std": float(np.std(avg.astype(np.float64))),
        }
        if baseline_subtracted is not None:
            result["baseline_subtracted"] = {
                "min": float(np.min(baseline_subtracted)),
                "max": float(np.max(baseline_subtracted)),
                "mean": float(np.mean(baseline_subtracted)),
                "std": float(np.std(baseline_subtracted)),
            }
            if _HAS_PIL:
                result["baseline_subtracted"]["image_base64"] = self._array_to_base64(baseline_subtracted)
        if _HAS_PIL:
            result["image_base64"] = self._array_to_base64(avg)
        return result

    def fit_pixel(self, file_path: str, x: int, y: int, start_frame: int, end_frame: int,
                  baseline_path: Optional[str] = None):
        """Fit Gaussian+erfc model to a single pixel's time series.

        Reads the pixel series, optionally subtracts a per-pixel baseline,
        then calls fit_pixel_full with return_details=True.
        """
        baseline_series = None
        if baseline_path:
            baseline_series = self._data_io.read_pixel_series(
                baseline_path, x, y, 0, -1, None
            )

        pixel_values = self._data_io.read_pixel_series(
            file_path, x, y, start_frame, end_frame, None
        )

        # If we have a baseline, also read baseline-subtracted version
        if baseline_path:
            baseline_map = self._data_io.read_average_frames(baseline_path, 0, 0)
            pixel_values = self._data_io.read_pixel_series(
                file_path, x, y, start_frame, end_frame, baseline_map
            )

        result = fit_pixel_full(
            pixel_values,
            gauss_guess=None,
            full_range=(100, 500),
            bins=100,
            sub_range=(280.0, 380.0),
            only_gaussian=False,
            noise_range=(-100, 100),
            return_details=True,
            use_raw_for_noise=(baseline_path is None),
            baseline_series=baseline_series,
        )

        noise_peak = result[0] if isinstance(result, tuple) and len(result) >= 1 else np.nan
        signal_peak = result[1] if isinstance(result, tuple) and len(result) >= 2 else np.nan
        gain = result[2] if isinstance(result, tuple) and len(result) >= 3 else np.nan

        return {
            "pixel": [x, y],
            "gain_adu_per_kev": None if np.isnan(gain) else float(gain),
            "noise_peak": None if np.isnan(noise_peak) else float(noise_peak),
            "signal_peak": None if np.isnan(signal_peak) else float(signal_peak),
            "noise_sigma": None,
        }

    def compute_gainmap(self, file_path: str, start_frame: int = 0, end_frame: int = -1,
                        use_baseline: bool = False, baseline_path: Optional[str] = None):
        """Compute full-sensor gain map (ADU/keV per pixel).

        Uses a temp directory for intermediate outputs (memmaps, .npy).
        """
        out_dir = os.path.join(self._temp_dir, "gainmap")
        os.makedirs(out_dir, exist_ok=True)

        baseline_memmap = None
        if use_baseline and baseline_path:
            baseline_memmap = self._data_io.read_average_frames(baseline_path, 0, 0)

        result = compute_gainmap(
            file_path, out_dir,
            make_memmap_func=self._data_io.make_memmap_from_raw,
            use_baseline=use_baseline,
            baseline_memmap=baseline_memmap,
            block_width=64,
            bins=100,
        )

        out = {
            "shape": list(result.shape),
            "min": float(np.nanmin(result)),
            "max": float(np.nanmax(result)),
            "mean": float(np.nanmean(result)),
            "std": float(np.nanstd(result)),
        }
        if _HAS_PIL:
            out["image_base64"] = self._array_to_base64(result)
        return out

    def compute_noisemap(self, file_path: str, start_frame: int = 0, end_frame: int = -1):
        """Compute full-sensor noise peak position map.

        Uses a temp directory for intermediate outputs (memmaps, .npy).
        """
        out_dir = os.path.join(self._temp_dir, "noisemap")
        os.makedirs(out_dir, exist_ok=True)

        result = compute_noisepeakmap(
            file_path, out_dir,
            make_memmap_func=self._data_io.make_memmap_from_raw,
            block_width=64,
            bins=100,
        )

        out = {
            "shape": list(result.shape),
            "min": float(np.nanmin(result)),
            "max": float(np.nanmax(result)),
            "mean": float(np.nanmean(result)),
            "std": float(np.nanstd(result)),
        }
        if _HAS_PIL:
            out["image_base64"] = self._array_to_base64(result)
        return out

    def compute_stdmap(self, file_path: str, start_frame: int, end_frame: int,
                       use_baseline: bool = False, baseline_path: Optional[str] = None):
        """Compute per-pixel temporal std deviation (Welford's online algorithm)."""
        n = 0
        mean_map = np.zeros((512, 1024), dtype=np.float64)
        M2_map = np.zeros((512, 1024), dtype=np.float64)
        baseline = None
        if use_baseline and baseline_path:
            baseline = self._data_io.read_average_frames(baseline_path, 0, 0)
        for fi in range(start_frame, end_frame + 1):
            img, _ = self._data_io.read_frame(file_path, fi)
            if baseline is not None:
                img = self._image_processor.subtract_baseline(img, baseline)
            n += 1
            delta = img.astype(np.float64) - mean_map
            mean_map += delta / n
            M2_map += delta * (img.astype(np.float64) - mean_map)
        std_map = np.sqrt(M2_map / n) if n > 1 else np.zeros_like(mean_map)
        out = {
            "shape": list(std_map.shape),
            "min": float(np.nanmin(std_map)),
            "max": float(np.nanmax(std_map)),
            "mean": float(np.nanmean(std_map)),
            "std": float(np.nanstd(std_map)),
        }
        if _HAS_PIL:
            out["image_base64"] = self._array_to_base64(std_map)
        return out

    # ── Helpers ──

    def _array_to_base64(self, arr: np.ndarray) -> str:
        """Convert 2D numpy array to a base64-encoded PNG (grayscale with percentile contrast)."""
        arr_valid = np.nan_to_num(arr, nan=0.0)
        flat = arr_valid.flatten()
        nonzero = flat[flat > 0] if np.any(flat > 0) else flat
        vmin, vmax = np.percentile(nonzero, [2, 98]) if len(nonzero) > 1 else (0, 1)
        if vmax <= vmin:
            vmax = vmin + 1
        arr_clipped = np.clip(arr_valid, vmin, vmax).astype(np.float64)
        arr_norm = ((arr_clipped - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        img = Image.fromarray(arr_norm, mode='L')
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _gain_to_base64(self, gain: np.ndarray) -> str:
        """Convert gain code array to base64 PNG (3-color map)."""
        mapped = np.zeros(gain.shape, dtype=np.uint8)
        mapped[gain == 3] = 64     # Low gain (dark)
        mapped[gain == 1] = 128    # Mid gain
        mapped[gain == 0] = 192    # High gain (bright)
        mapped[gain == 2] = 128    # Also mid gain
        img = Image.fromarray(mapped, mode='L')
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
