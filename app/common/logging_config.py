"""日志配置模块。

集中管理日志格式与级别，供全项目统一调用。GUI 状态栏消息仍走 View，
但关键业务事件（校准、文件 I/O、报告生成、采集启停）同时写入日志文件，
便于排查问题和审计。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: str | Path = "logs", level: int = logging.INFO) -> logging.Logger:
    """初始化项目根日志器。

    Args:
        log_dir: 日志文件存放目录。
        level: 日志级别。

    Returns:
        配置好的根日志器。
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("ut_analyst")
    root_logger.setLevel(level)

    # 避免重复添加 handler。
    if root_logger.handlers:
        return root_logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler：记录全部事件。
    file_handler = logging.FileHandler(
        log_path / "ut_analyst.log",
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台 handler：仅输出 WARNING 及以上。
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger
