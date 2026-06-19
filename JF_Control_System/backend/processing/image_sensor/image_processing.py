"""
图像处理模块
负责图像的基本处理操作：基线扣除、ROI裁剪、对比度调整等
"""
import numpy as np
from PIL import Image


class ImageProcessor:
    """图像处理类"""
    
    @staticmethod
    def subtract_baseline(img_array, baseline_data):
        """Subtract baseline from image array.

        Allows negative values for noise peak fitting.
        """
        return img_array - baseline_data

    @staticmethod
    def adjust_contrast(img_array, color_min=0, color_max=16383):
        """Clip image array to specified contrast range."""
        return np.clip(img_array, color_min, color_max)

    @staticmethod
    def normalize_for_display(img_array, vmin=None, vmax=None):
        """Normalize image array to [0, 1] range for display."""
        if vmin is None:
            vmin = float(np.nanmin(img_array))
        if vmax is None:
            vmax = float(np.nanmax(img_array))
        if vmax <= vmin:
            vmax = vmin + 1.0
        norm = (img_array - vmin) / (vmax - vmin)
        return np.clip(norm, 0.0, 1.0)

    @staticmethod
    def save_as_png(img_array, output_path):
        """Save image array as PNG file."""
        Image.fromarray(img_array).save(output_path)

    @staticmethod
    def nan_to_num(img_array, nan_value=0.0):
        """Replace NaN values with specified value."""
        return np.nan_to_num(img_array, nan=nan_value)
