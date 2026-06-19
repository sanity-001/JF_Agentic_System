"""
Data IO module
Responsible for reading raw data files, baseline data processing, memmap creation, etc.
"""
import os
import struct
import numpy as np


class DataIO:
    """Data input/output processing class"""

    def __init__(self, header_size=112, frame_shape=(512, 1024)):
        self.header_size = header_size
        self.frame_shape = frame_shape
        self.frame_size = self.header_size + frame_shape[0] * frame_shape[1] * 2

    def _read_single_frame_data(self, f, frame_idx):
        """Internal helper: read a single frame of image data from a file object

        Args:
            f: Open file object
            frame_idx: Frame index

        Returns:
            img: Image array (512, 1024), dtype=float64
        """
        f.seek(frame_idx * self.frame_size)
        _hdr = f.read(self.header_size)
        raw_data = np.frombuffer(f.read(self.frame_shape[0] * self.frame_shape[1] * 2), dtype='<u2')
        data_bits = (raw_data & 0x3FFF).astype(np.float64)
        img = data_bits.reshape(self.frame_shape[0], self.frame_shape[1])
        return img

    def read_frame(self, file_path, frame_idx):
        """Read a single frame of data

        Args:
            file_path: Path to the raw file
            frame_idx: Frame index

        Returns:
            img_array: Image array (512, 1024)
            frame_number: Frame number
        """
        with open(file_path, 'rb') as f:
            f.seek(frame_idx * self.frame_size)
            header = f.read(self.header_size)
            frame_number = struct.unpack('<Q', header[:8])[0]
            img_array = self._read_single_frame_data(f, frame_idx)
            return img_array, frame_number

    def read_average_frames(self, file_path, start_frame=0, end_frame=None):
        """Read and compute the average frame

        Args:
            file_path: Path to the raw file
            start_frame: Starting frame index (default 0)
            end_frame: Ending frame index (inclusive), None means read to end of file

        Returns:
            avg_img: Average image array (512, 1024)

        Usage Examples:
            # Read the average of the first 100 frames
            avg = data_io.read_average_frames('baseline.raw', 0, 99)

            # Read the average of all frames
            avg = data_io.read_average_frames('baseline.raw')

            # Read the average of a specified range
            avg = data_io.read_average_frames('data.raw', 100, 200)
        """
        size = os.path.getsize(file_path)
        total_frames = size // self.frame_size
        if total_frames == 0:
            raise ValueError(f"No frames found in file {file_path}")

        # Determine the actual frame range
        if end_frame is None:
            end_frame = total_frames - 1

        if start_frame < 0 or start_frame >= total_frames:
            raise ValueError(f"start_frame {start_frame} out of range [0, {total_frames-1}]")

        end_frame = min(end_frame, total_frames - 1)
        frame_count = end_frame - start_frame + 1

        if frame_count <= 0:
            raise ValueError(f"Invalid frame range: start={start_frame}, end={end_frame}")

        # Accumulate all frames
        acc = None
        with open(file_path, 'rb') as f:
            for i in range(start_frame, end_frame + 1):
                img = self._read_single_frame_data(f, i)
                if acc is None:
                    acc = np.zeros_like(img, dtype=np.float64)
                acc += img

        avg_img = acc / float(frame_count)
        return avg_img

    def make_memmap_from_raw(self, raw_path, memmap_path, dtype='<u2', force=True):
        """Create memmap from raw file (for fast access to large data volumes)

        Args:
            raw_path: Input raw file path
            memmap_path: Memmap file path
            dtype: Data type
            force: Whether to force rebuild

        Returns:
            memmap object
        """
        H = int(self.frame_shape[0])
        W = int(self.frame_shape[1])
        header_size = int(self.header_size)
        dtype_itemsize = int(np.dtype(dtype).itemsize)

        # If memmap already exists and force rebuild is not set
        if os.path.exists(memmap_path) and not force:
            file_size = os.path.getsize(memmap_path)
            total_elems = file_size // int(np.dtype(np.float32).itemsize)
            if total_elems % (H * W) != 0:
                raise ValueError("Existing memmap size incompatible with frame_shape")
            n_frames = total_elems // (H * W)
            return np.memmap(memmap_path, mode='r+', dtype=np.float32, shape=(n_frames, H, W))

        # Create memmap from raw file
        size = os.path.getsize(raw_path)
        frame_bytes = header_size + (H * W) * dtype_itemsize
        frame_bytes = int(frame_bytes)
        n_frames = size // frame_bytes
        if n_frames == 0:
            raise ValueError("no frames in raw file")

        # Create float32 memmap
        mm = np.memmap(memmap_path, mode='w+', dtype=np.float32, shape=(n_frames, H, W))
        with open(raw_path, 'rb') as f:
            for i in range(int(n_frames)):
                img = self._read_single_frame_data(f, i)
                mm[i, :, :] = img.astype(np.float32)
        # Flush to disk
        del mm
        return np.memmap(memmap_path, mode='r+', dtype=np.float32, shape=(n_frames, H, W))

    def read_gain_from_frame(self, file_path, frame_idx):
        """Read gain information from a single frame (upper 2 bits)

        Args:
            file_path: Path to the raw file
            frame_idx: Frame index

        Returns:
            gain_img: Gain image (512, 1024)
        """
        rows, cols = self.frame_shape
        frame_bytes = rows * cols * 2
        with open(file_path, 'rb') as f:
            f.seek(frame_idx * self.frame_size)
            _hdr = f.read(self.header_size)
            raw = f.read(frame_bytes)
            if len(raw) < frame_bytes:
                raise ValueError(f"Frame {frame_idx} data incomplete")
            data = np.frombuffer(raw, dtype='<u2')

        # Extract upper 2 bits for gain code
        gain = (data >> 14) & 0x3
        gain_img = gain.reshape(rows, cols).astype(np.uint8)
        return gain_img

    def read_pixel_series(self, file_path, rx, cx, start_frame, end_frame, baseline_data=None):
        """Read the value series of a specified pixel across multiple frames

        Args:
            file_path: Path to the raw file
            rx: Row coordinate (0-based)
            cx: Column coordinate (0-based)
            start_frame: Starting frame
            end_frame: Ending frame (-1 means read to end of file)
            baseline_data: Baseline data (optional)

        Returns:
            pixel_series: Array of pixel value series
        """
        r_idx = rx
        c_idx = cx

        # Calculate total number of frames in the file
        size = os.path.getsize(file_path)
        total_frames = size // self.frame_size

        # If end_frame is -1, read to end of file
        if end_frame == -1:
            end_frame = total_frames - 1

        pixel_values = []
        with open(file_path, 'rb') as f:
            for frame_idx in range(start_frame, end_frame + 1):
                img = self._read_single_frame_data(f, frame_idx)

                pixel_value = img[r_idx, c_idx]
                if baseline_data is not None:
                    pixel_value = pixel_value - baseline_data[r_idx, c_idx]

                pixel_values.append(pixel_value)

        return np.array(pixel_values)
