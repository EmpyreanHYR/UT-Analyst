"""shortcut_manager 和 layout_manager 模块的单元测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from PyQt5.QtCore import QByteArray

from app.common.shortcut_manager import ShortcutManager, DEFAULT_SHORTCUTS
from app.common.layout_manager import LayoutManager


class TestShortcutManager:
    """验证快捷键管理器功能。"""

    def test_default_shortcuts(self) -> None:
        """默认快捷键应包含所有必需的动作。"""
        assert "start_acquisition" in DEFAULT_SHORTCUTS
        assert "stop_acquisition" in DEFAULT_SHORTCUTS
        assert "freeze_toggle" in DEFAULT_SHORTCUTS
        assert "single_shot" in DEFAULT_SHORTCUTS
        assert "open_file" in DEFAULT_SHORTCUTS
        assert "save_file" in DEFAULT_SHORTCUTS
        assert "generate_report" in DEFAULT_SHORTCUTS

    def test_get_shortcut(self) -> None:
        """应能获取指定动作的快捷键。"""
        # 创建一个模拟的窗口对象
        class MockWindow:
            pass

        manager = ShortcutManager(MockWindow())

        shortcut = manager.get_shortcut("start_acquisition")
        assert shortcut == "Ctrl+Enter"

    def test_shortcut_map_has_no_duplicates(self) -> None:
        """默认快捷键之间不能互相冲突。"""
        configured = [value for value in DEFAULT_SHORTCUTS.values() if value]

        assert len(configured) == len(set(configured))

    def test_all_documented_primary_shortcuts_exist(self) -> None:
        """帮助文档中的主要快捷键应对应真实动作。"""
        assert DEFAULT_SHORTCUTS["statistics_toggle"] == "F6"
        assert DEFAULT_SHORTCUTS["toggle_grid"] == "Ctrl+Shift+H"

    def test_set_shortcut(self) -> None:
        """应能设置指定动作的快捷键。"""
        class MockWindow:
            pass

        manager = ShortcutManager(MockWindow())

        manager.set_shortcut("start_acquisition", "Ctrl+F1")
        assert manager.get_shortcut("start_acquisition") == "Ctrl+F1"

    def test_get_shortcut_tips(self) -> None:
        """应能获取所有快捷键提示。"""
        class MockWindow:
            pass

        manager = ShortcutManager(MockWindow())

        tips = manager.get_shortcut_tips()

        assert isinstance(tips, list)
        assert len(tips) > 0

        # 检查返回格式
        for action_id, desc, shortcut in tips:
            assert isinstance(action_id, str)
            assert isinstance(desc, str)
            assert isinstance(shortcut, str)


class TestLayoutManager:
    """验证布局管理器功能。"""

    def setup_method(self) -> None:
        """每个测试前创建临时目录。"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = LayoutManager(config_dir=self.temp_dir)

    def test_save_and_load_window_geometry(self) -> None:
        """应能保存和加载窗口几何信息。"""
        geometry = {
            "x": 100,
            "y": 200,
            "width": 1360,
            "height": 860,
        }

        self.manager.save_window_geometry(geometry)
        loaded = self.manager.load_window_geometry()

        assert loaded is not None
        assert loaded["x"] == 100
        assert loaded["y"] == 200
        assert loaded["width"] == 1360
        assert loaded["height"] == 860

    def test_load_nonexistent_geometry(self) -> None:
        """加载不存在的几何信息应返回None。"""
        loaded = self.manager.load_window_geometry()
        assert loaded is None

    def test_save_and_load_dock_layout(self) -> None:
        """应能保存和加载Dock布局状态。"""
        # 模拟的dock状态数据
        dock_state = b"test_dock_state_data"

        self.manager.save_dock_layout(dock_state)
        loaded = self.manager.load_dock_layout()

        assert loaded is not None
        assert loaded == dock_state

    def test_save_qbytearray_dock_layout(self) -> None:
        """Qt 的 QByteArray 布局状态应能直接保存。"""
        dock_state = QByteArray(b"qt-dock-state")

        self.manager.save_dock_layout(dock_state)

        assert self.manager.load_dock_layout() == b"qt-dock-state"

    def test_load_nonexistent_dock_layout(self) -> None:
        """加载不存在的Dock布局应返回None。"""
        loaded = self.manager.load_dock_layout()
        assert loaded is None

    def test_save_and_load_preferences(self) -> None:
        """应能保存和加载用户偏好设置。"""
        preferences = {
            "theme": "dark",
            "language": "zh_CN",
            "auto_save": True,
        }

        self.manager.save_preferences(preferences)
        loaded = self.manager.load_preferences()

        assert loaded["theme"] == "dark"
        assert loaded["language"] == "zh_CN"
        assert loaded["auto_save"] == True

    def test_load_nonexistent_preferences(self) -> None:
        """加载不存在的偏好设置应返回空字典。"""
        loaded = self.manager.load_preferences()
        assert loaded == {}

    def test_update_existing_preferences(self) -> None:
        """更新偏好设置应合并现有设置。"""
        # 保存初始设置
        self.manager.save_preferences({"theme": "dark", "language": "zh_CN"})

        # 更新部分设置
        self.manager.save_preferences({"theme": "light", "auto_save": True})

        loaded = self.manager.load_preferences()

        assert loaded["theme"] == "light"  # 已更新
        assert loaded["language"] == "zh_CN"  # 保留
        assert loaded["auto_save"] == True  # 新增

    def test_config_files_created(self) -> None:
        """保存操作应创建配置文件。"""
        self.manager.save_window_geometry({"x": 0, "y": 0})

        config_dir = Path(self.temp_dir)
        assert (config_dir / "layout.json").exists()

    def test_preferences_file_created(self) -> None:
        """保存偏好设置应创建配置文件。"""
        self.manager.save_preferences({"test": "value"})

        config_dir = Path(self.temp_dir)
        assert (config_dir / "preferences.json").exists()
