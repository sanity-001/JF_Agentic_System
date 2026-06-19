"""DataIO — 原始帧读取与多帧平均."""
import os
from typing import Optional
import numpy as np


class DataIO:
    """数据输入输出处理类：读取 .raw 二进制帧文件."""

    def __init__(self, header_size: int = 112, frame_shape: tuple = (512, 1024)):
        self.header_size = header_size
        self.frame_shape = frame_shape
        self.frame_size = self.header_size + frame_shape[0] * frame_shape[1] * 2

    def read_single_frame(self, f, frame_idx: int):
        """从已打开的文件对象中读取单帧图像数据（14位有效数据）."""
        f.seek(frame_idx * self.frame_size)
        _hdr = f.read(self.header_size)
        raw_data = np.frombuffer(
            f.read(self.frame_shape[0] * self.frame_shape[1] * 2), dtype='<u2'
        )
        data_bits = (raw_data & 0x3FFF).astype(dtype=np.float32)
        img = data_bits.reshape(self.frame_shape[0], self.frame_shape[1])
        return img

    def read_average_frames(
        self, file_path: str, start_frame: int = 0, end_frame: Optional[int] = None
    ):
        """读取指定帧范围并计算平均帧."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Raw file not found: {file_path}")

        size = os.path.getsize(file_path)
        total_frames = size // self.frame_size
        if total_frames == 0:
            raise ValueError(f"No frames found in file {file_path}")

        if end_frame is None:
            end_frame = total_frames - 1

        if start_frame < 0 or start_frame >= total_frames:
            raise ValueError(
                f"start_frame {start_frame} out of range [0, {total_frames - 1}]"
            )

        end_frame = min(end_frame, total_frames - 1)
        frame_count = end_frame - start_frame + 1

        if frame_count <= 0:
            raise ValueError(
                f"Invalid frame range: start={start_frame}, end={end_frame}"
            )

        acc = None
        with open(file_path, 'rb') as f:
            for i in range(start_frame, end_frame + 1):
                img = self.read_single_frame(f, i)
                if acc is None:
                    acc = np.zeros_like(img, dtype=np.float32)
                acc += img

        avg_img = acc / float(frame_count)
        return avg_img

    def ndarray_to_list(self, arr: np.ndarray) -> list:
        """将 np.ndarray 转换为嵌套 list，用于 JSON 序列化."""
        return arr.tolist()
