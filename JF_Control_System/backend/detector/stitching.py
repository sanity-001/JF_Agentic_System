"""拼接处理：行列拆分扩展 + 8模块拼接器."""
from dataclasses import dataclass
import numpy as np
from typing import List


@dataclass
class ModuleConfig:
    """单个模块的配置."""
    module_id: str
    x_offset: int = 0
    y_offset: int = 0
    origin: str = 'top-left'
    raw_path: str = ''
    rotation: int = 0


def insert_split_rows_and_cols(img: np.ndarray) -> np.ndarray:
    """
    对单模块图像做行/列拆分（选 A 策略）：
    - 行：第255和256行各像素除2并在其后各插入一行（高度 512→514）
    - 列：第255,256,511,512,767,768 列各像素除2并在其后各插入一列（宽度 1024→1030）
    返回 float32 数组，shape (514, 1030)
    """
    if img.ndim != 2:
        img = img.squeeze()
    img = img.astype(np.float32)
    h, w = img.shape
    if (h, w) != (512, 1024):
        raise ValueError(
            f"insert_split_rows_and_cols expects (512,1024), got {(h, w)}"
        )

    # 行拆分 (512 → 514)
    r1, r2 = 255, 256
    half_r1 = img[r1, :] / 2.0
    half_r2 = img[r2, :] / 2.0
    new_h = h + 2
    tmp = np.zeros((new_h, w), dtype=np.float32)
    tmp[0:r1, :] = img[0:r1, :]
    tmp[r1, :] = half_r1
    tmp[r1 + 1, :] = half_r1
    tmp[r1 + 2, :] = half_r2
    tmp[r1 + 3, :] = half_r2
    tmp[r1 + 4:, :] = img[r2 + 1:, :]

    # 列拆分 (1024 → 1030)
    cols_to_dup = {255, 256, 511, 512, 767, 768}
    new_w = w + len(cols_to_dup)
    out = np.zeros((new_h, new_w), dtype=np.float32)

    dst = 0
    for c in range(w):
        col = tmp[:, c]
        if c in cols_to_dup:
            half_col = col / 2.0
            out[:, dst] = half_col
            out[:, dst + 1] = half_col
            dst += 2
        else:
            out[:, dst] = col
            dst += 1

    return out


def get_default_configs() -> List[ModuleConfig]:
    """返回默认 8 模块配置（d0~d7）."""
    return [
        ModuleConfig(module_id="d0", rotation=0),
        ModuleConfig(module_id="d1", rotation=0),
        ModuleConfig(module_id="d2", rotation=0),
        ModuleConfig(module_id="d3", rotation=0),
        ModuleConfig(module_id="d4", rotation=0),
        ModuleConfig(module_id="d5", rotation=0),
        ModuleConfig(module_id="d6", rotation=0),
        ModuleConfig(module_id="d7", rotation=0),
    ]


class EightModuleProcessor:
    """8模块拼接处理器，支持扩展/不扩展双模式."""

    # gap 参数（两种模式共用）
    LONG_GAP = 36
    SHORT_GAP = 23
    SQUARE_HOLE_SIDE = 91

    def __init__(self, configs: List[ModuleConfig]):
        if not configs:
            raise ValueError("必须至少提供1个模块配置")
        self.configs = configs

    @staticmethod
    def _rotate_image(image: np.ndarray, rotation: int) -> np.ndarray:
        if rotation == 0:
            return image
        elif rotation == 90:
            return np.rot90(image, k=1)
        elif rotation == 180:
            return np.rot90(image, k=2)
        elif rotation == 270:
            return np.rot90(image, k=3)
        else:
            raise ValueError(f"Unsupported rotation angle: {rotation}")

    def _build_layout(
        self,
        module_row: int,
        module_col: int,
        offset: int,
    ) -> dict:
        """根据模块尺寸和参数生成 8 模块布局字典."""
        lg = self.LONG_GAP
        sg = self.SHORT_GAP
        sq = self.SQUARE_HOLE_SIDE

        return {
            "d0": (0, 0 + offset - 1, module_col, module_row),
            "d1": (0, module_row + offset + lg - 1, module_col, module_row),
            "d2": (module_col - 1 + sg, 0, module_row, module_col),
            "d3": (
                module_row + module_col - 1 + sg + lg,
                0,
                module_row,
                module_col,
            ),
            "d4": (
                0 + offset - 1,
                module_row * 2 - 1 + sg + lg + offset,
                module_row,
                module_col,
            ),
            "d5": (
                module_row - 1 + lg + offset,
                module_row * 2 - 1 + sg + lg + offset,
                module_row,
                module_col,
            ),
            "d6": (module_col - 1 + sq, module_col - 1 + sg, module_col, module_row),
            "d7": (
                module_col - 1 + sq,
                module_row + module_col - 1 + sg + lg,
                module_col,
                module_row,
            ),
        }

    def stitch_images(
        self,
        module_images: List[np.ndarray],
        expand: bool = True,
    ) -> np.ndarray:
        """将各模块图像拼接到画布上."""
        if len(module_images) != len(self.configs):
            raise ValueError(
                f"Expected {len(self.configs)} module images, "
                f"got {len(module_images)}"
            )

        if expand:
            module_row, module_col = 514, 1030
            canvas_h, canvas_w = 2151, 2151
            offset = 34
        else:
            module_row, module_col = 512, 1024
            canvas_h, canvas_w = 2139, 2139
            offset = 32

        layout = self._build_layout(module_row, module_col, offset)
        stitched = np.zeros((canvas_h, canvas_w), dtype=np.float32)

        # map id → image (apply rotation)
        id_to_img = {}
        for cfg, img in zip(self.configs, module_images):
            if img.ndim > 2:
                img = img.squeeze()
            id_to_img[cfg.module_id] = self._rotate_image(img, cfg.rotation)

        selected_ids = {cfg.module_id for cfg in self.configs}
        for module_id, (x0, y0, expected_w, expected_h) in layout.items():
            if module_id not in selected_ids:
                continue
            if module_id not in id_to_img:
                raise ValueError(f"Missing image for module: {module_id}")

            img = id_to_img[module_id]

            if img.shape != (expected_h, expected_w):
                if img.shape == (expected_w, expected_h):
                    img = np.rot90(img, k=1)
                else:
                    raise ValueError(
                        f"{module_id} shape {img.shape} cannot fit "
                        f"expected {(expected_h, expected_w)}"
                    )

            stitched[y0:y0 + expected_h, x0:x0 + expected_w] = img

        return stitched
