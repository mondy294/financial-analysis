"""日志初始化（基于 loguru）。

约定：
- 业务代码：`from loguru import logger`
- 应用入口（cli.py / main.py）启动时调用一次 setup_logging()。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from quant_system.config.settings import get_settings

_INITIALIZED = False


def setup_logging(force: bool = False) -> None:
    """按 config.logging 配置初始化 loguru。重复调用无副作用。"""
    global _INITIALIZED
    if _INITIALIZED and not force:
        return

    settings = get_settings()
    log_cfg = settings.logging

    log_dir = Path(log_cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()  # 清空默认 handler

    # 终端 sink
    logger.add(
        sys.stderr,
        level=log_cfg.level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=False,
    )

    # 文件 sink（按日期）
    logger.add(
        log_dir / "quant_system_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation=log_cfg.rotation,
        retention=log_cfg.retention,
        encoding="utf-8",
        enqueue=True,  # 多进程安全
    )

    _INITIALIZED = True
    logger.debug("logging initialized: level={} dir={}", log_cfg.level, log_dir)


def get_logger():
    """获取 loguru logger 实例（便于依赖注入到不方便直接 import 的场景）。"""
    return logger
