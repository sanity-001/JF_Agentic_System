"""
工具函数模块
提供通用的辅助函数
"""
import os
import sys
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
import time


def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    """格式化时间
    
    Args:
        seconds: 秒数
        
    Returns:
        格式化的时间字符串（如 "1h 23m 45s"）
    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.0f}s"


def get_file_info(file_path: str) -> dict:
    """获取文件信息
    
    Args:
        file_path: 文件路径
        
    Returns:
        包含文件信息的字典
    """
    path = Path(file_path)
    if not path.exists():
        return {}
    
    stat = path.stat()
    return {
        'path': str(path.absolute()),
        'name': path.name,
        'size': stat.st_size,
        'size_formatted': format_size(stat.st_size),
        'modified': time.ctime(stat.st_mtime)
    }


@contextmanager
def timer(description: str = "Operation"):
    """计时上下文管理器
    
    Args:
        description: 操作描述
        
    Yields:
        None
        
    Example:
        with timer("Data loading"):
            data = load_data()
    """
    from .logger import get_logger
    logger = get_logger()
    
    logger.info(f"{description} started...")
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        logger.info(f"{description} completed in {format_time(elapsed)}")



