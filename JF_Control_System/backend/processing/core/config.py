"""
Configuration management module
Centralized management of all configuration parameters, supports loading from files and environment variable overrides
"""
import os
from pathlib import Path
from typing import Tuple


class Config:
    """Configuration management class"""

    # ==================== File Path Configuration ====================
    DEFAULT_INPUT_FILE = "run_100Hz_1000Frames_10us_xray30kV30uA_d0_f0_3.raw"
    DEFAULT_BASELINE_FILE = r"D:\MyCode\ImageSensor\X_ray_on\run_d0_f0_0.raw"
    DEFAULT_OUTPUT_DIR = "output"

    # ==================== Data Format Configuration ====================
    HEADER_SIZE = 112
    FRAME_SHAPE: Tuple[int, int] = (512, 1024)
    BITS_MASK = 0x3FFF  # 14-bit data mask

    # ==================== Processing Parameter Configuration ====================
    # Contrast range
    COLOR_MIN = 0
    COLOR_MAX = 65535

    # Histogram configuration
    DEFAULT_BINS = 200
    DEFAULT_HIST_RANGE = (100.0, 500.0)

    # Fitting parameters
    NOISE_RANGE = (-50.0, 50.0)
    KA_GAUSS_RANGE = (280.0, 380.0)
    KA_FULL_RANGE = (100.0, 500.0)
    BINS_NOISE = 50
    BINS_GAUSS = 50
    BINS_FULL = 100
    MAXFEV_DEFAULT = 5000
    MAXFEV_FULL = 10000

    # Gain map calculation
    ENERGY_KEV_FACTOR = 8.048  # Cu K-alpha energy in keV
    DEFAULT_BLOCK_WIDTH = 64

    # ==================== Performance Configuration ====================
    MAX_FRAMES_TO_PROCESS = 1000  # Maximum number of frames to process in mode 1
    PROGRESS_UPDATE_INTERVAL = 100  # Update progress every N frames

    # ==================== Logging Configuration ====================
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    LOG_LEVEL = 'INFO'

    # ==================== UI Theme Configuration ====================
    UI_THEME_BG = "#0f172a"
    UI_THEME_SURFACE = "#1e293b"
    UI_ACCENT = "#3b82f6"
    UI_ACCENT_HOVER = "#2563eb"
    UI_TEXT_PRIMARY = "#e2e8f0"
    UI_TEXT_SECONDARY = "#94a3b8"
    UI_TEXT_MUTED = "#64748b"

    @classmethod
    def validate_file_path(cls, file_path: str, check_exists: bool = True) -> Path:
        """Validate and return a normalized file path

        Args:
            file_path: File path string
            check_exists: Whether to check if the file exists

        Returns:
            Path object

        Raises:
            FileNotFoundError: File does not exist
            ValueError: Invalid path
        """
        if not file_path:
            raise ValueError("File path cannot be empty")

        path = Path(file_path)

        if check_exists and not path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")

        return path

    @classmethod
    def ensure_output_dir(cls, output_dir: str) -> Path:
        """Ensure the output directory exists

        Args:
            output_dir: Output directory path

        Returns:
            Path object
        """
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def validate_frame_range(cls, start_frame: int, end_frame: int,
                            max_frames: int = None) -> Tuple[int, int]:
        """Validate the validity of the frame range

        Args:
            start_frame: Starting frame
            end_frame: Ending frame
            max_frames: Maximum number of frames (optional)

        Returns:
            (start_frame, end_frame) tuple

        Raises:
            ValueError: Invalid frame range
        """
        if start_frame < 0:
            raise ValueError(f"Start frame number cannot be negative: {start_frame}")

        if end_frame != -1 and end_frame <= start_frame:
            raise ValueError(f"End frame ({end_frame}) must be greater than start frame ({start_frame})")

        if max_frames is not None and end_frame > max_frames:
            raise ValueError(f"End frame ({end_frame}) exceeds maximum frame count of file ({max_frames})")

        return start_frame, end_frame

    @classmethod
    def validate_pixel_coords(cls, row: int, col: int) -> Tuple[int, int]:
        """Validate the validity of pixel coordinates

        Args:
            row: Row coordinate (1-based)
            col: Column coordinate (1-based)

        Returns:
            (row, col) tuple

        Raises:
            ValueError: Coordinates out of range
        """
        if not (1 <= row <= cls.FRAME_SHAPE[0]):
            raise ValueError(f"Row coordinate ({row}) out of range [1, {cls.FRAME_SHAPE[0]}]")

        if not (1 <= col <= cls.FRAME_SHAPE[1]):
            raise ValueError(f"Column coordinate ({col}) out of range [1, {cls.FRAME_SHAPE[1]}]")

        return row, col


# Global configuration instance
config = Config()
