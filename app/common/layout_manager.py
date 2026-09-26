"""界面布局保存/恢复模块。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("ut_analyst.layout_manager")


class LayoutManager:
    """
    界面布局管理器。

    功能：
    1. 保存/恢复窗口位置和大小
    2. 保存/恢复DockWidget布局
    3. 保存/恢复检测参数偏好
    4. 保存/恢复用户自定义设置
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        """
        初始化布局管理器。

        参数：
        - config_dir: 配置文件保存目录，默认为应用目录下的config/
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.layout_file = self.config_dir / "layout.json"
        self.preferences_file = self.config_dir / "preferences.json"

    def save_window_geometry(self, window_geometry: dict[str, Any]) -> None:
        """
        保存窗口几何信息。

        参数：
        - window_geometry: 包含x, y, width, height的字典
        """
        layout = self._load_layout()
        layout["window_geometry"] = window_geometry
        layout["saved_at"] = datetime.now().isoformat()
        self._save_layout(layout)
        logger.info("窗口布局已保存")

    def load_window_geometry(self) -> dict[str, Any] | None:
        """
        加载窗口几何信息。

        返回：
        - 窗口几何字典，或None
        """
        layout = self._load_layout()
        return layout.get("window_geometry")

    def save_dock_layout(self, dock_state: bytes | bytearray) -> None:
        """
        保存DockWidget布局状态。

        参数：
        - dock_state: QByteArray状态数据
        """
        layout = self._load_layout()
        if hasattr(dock_state, "data"):
            raw_state = bytes(dock_state.data())
        else:
            raw_state = bytes(dock_state)
        layout["dock_state"] = raw_state.hex()
        layout["saved_at"] = datetime.now().isoformat()
        self._save_layout(layout)
        logger.info("Dock布局已保存")

    def load_dock_layout(self) -> bytes | None:
        """
        加载DockWidget布局状态。

        返回：
        - 状态数据bytes，或None
        """
        layout = self._load_layout()
        hex_data = layout.get("dock_state")
        if hex_data:
            return bytes.fromhex(hex_data)
        return None

    def save_preferences(self, preferences: dict[str, Any]) -> None:
        """
        保存用户偏好设置。

        参数：
        - preferences: 偏好设置字典
        """
        existing = self._load_preferences()
        existing.update(preferences)
        existing["saved_at"] = datetime.now().isoformat()

        try:
            self.preferences_file.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("用户偏好已保存")
        except Exception as error:
            logger.error("保存偏好失败：%s", error)

    def load_preferences(self) -> dict[str, Any]:
        """
        加载用户偏好设置。

        返回：
        - 偏好设置字典
        """
        return self._load_preferences()

    def _load_layout(self) -> dict[str, Any]:
        """从文件加载布局配置。"""
        if not self.layout_file.exists():
            return {}
        try:
            return json.loads(self.layout_file.read_text(encoding="utf-8"))
        except Exception as error:
            logger.warning("加载布局文件失败：%s", error)
            return {}

    def _save_layout(self, layout: dict[str, Any]) -> None:
        """保存布局配置到文件。"""
        try:
            self.layout_file.write_text(
                json.dumps(layout, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as error:
            logger.error("保存布局文件失败：%s", error)

    def _load_preferences(self) -> dict[str, Any]:
        """从文件加载偏好设置。"""
        if not self.preferences_file.exists():
            return {}
        try:
            return json.loads(self.preferences_file.read_text(encoding="utf-8"))
        except Exception as error:
            logger.warning("加载偏好文件失败：%s", error)
            return {}
