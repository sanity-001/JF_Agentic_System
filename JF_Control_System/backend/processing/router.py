"""Data processing REST API routes — /api/processing/*"""
from fastapi import APIRouter, HTTPException
from backend.processing.service import ProcessingService
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/processing", tags=["processing"])

_proc = ProcessingService()


class FrameReadRequest(BaseModel):
    file_path: str
    frame_idx: int = 0


class FrameAverageRequest(BaseModel):
    file_path: str
    start_frame: int = 0
    end_frame: int = 0
    baseline_path: Optional[str] = None


class PixelFitRequest(BaseModel):
    file_path: str
    x: int
    y: int
    start_frame: int = 0
    end_frame: int = 100
    baseline_path: Optional[str] = None


class MapRequest(BaseModel):
    file_path: str
    start_frame: int = 0
    end_frame: int = 100
    use_baseline: bool = False
    baseline_path: Optional[str] = None


@router.post("/frame/read")
async def read_frame(req: FrameReadRequest):
    try:
        return _proc.read_frame(req.file_path, req.frame_idx)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frame/average")
async def average_frames(req: FrameAverageRequest):
    try:
        return _proc.read_average(req.file_path, req.start_frame, req.end_frame, req.baseline_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pixel/fit")
async def fit_pixel(req: PixelFitRequest):
    try:
        return _proc.fit_pixel(req.file_path, req.x, req.y, req.start_frame, req.end_frame, req.baseline_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gainmap/compute")
async def compute_gainmap(req: MapRequest):
    try:
        return _proc.compute_gainmap(req.file_path, req.start_frame, req.end_frame,
                                     req.use_baseline, req.baseline_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/noisemap/compute")
async def compute_noisemap(req: MapRequest):
    try:
        return _proc.compute_noisemap(req.file_path, req.start_frame, req.end_frame)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stdmap/compute")
async def compute_stdmap(req: MapRequest):
    try:
        return _proc.compute_stdmap(req.file_path, req.start_frame, req.end_frame,
                                    req.use_baseline, req.baseline_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
