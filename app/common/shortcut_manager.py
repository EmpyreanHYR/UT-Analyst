"""快捷键管理模块，统一管理应用快捷键绑定。"""

from __future__ import annotations

from PyQt5.QtWidgets import QMainWindow, QAction


# 默认快捷键映射表
DEFAULT_SHORTCUTS = {
    # 采集控制
    "start_acquisition": "Ctrl+Enter",
    "stop_acquisition": "F2",
    "freeze_toggle": "F3",
    "single_shot": "F4",
    "fft_toggle": "F5",
    "statistics_toggle": "F6",
    "shortcut_help": "F1",
    # 文件操作
    "open_file": "Ctrl+O",
    "save_file": "Ctrl+S",
    "generate_report": "Ctrl+R",
    # 波形操作
    "auto_scale": "Ctrl+A",
    "clear_peak": "Ctrl+P",
    "capture_reference": "Ctrl+G",
    "clear_reference": "Ctrl+Shift+G",
    # 记录控制
    "start_record": "Ctrl+Shift+R",
    "delete_record": "Delete",
    "clear_records": "Ctrl+Shift+D",
    # 视图
    "toggle_grid": "Ctrl+Shift+H",
    "toggle_cursor_label": "Ctrl+L",
}


class ShortcutManager:
    """
    快捷键管理器。

    功能：
    1. 统一管理快捷键绑定
    2. 支持自定义快捷键
    3. 提供快捷键提示
    """

    def __init__(self, window: QMainWindow) -> None:
        """
        初始化快捷键管理器。

        参数：
        - window: 主窗口实例
        """
        self.window = window
        self.shortcuts: dict[str, str] = dict(DEFAULT_SHORTCUTS)
        self.action_map: dict[str, QAction] = {}

    def register_action(self, action_id: str, action: QAction, shortcut: str | None = None) -> None:
        """
        注册一个动作并绑定快捷键。

        参数：
        - action_id: 动作标识符
        - action: QAction实例
        - shortcut: 快捷键字符串（None则使用默认值）
        """
        key = shortcut or self.shortcuts.get(action_id, "")
        if key:
            action.setShortcut(key)
        self.action_map[action_id] = action

    def get_shortcut(self, action_id: str) -> str:
        """获取指定动作的快捷键。"""
        return self.shortcuts.get(action_id, "")

    def set_shortcut(self, action_id: str, shortcut: str) -> None:
        """
        设置指定动作的快捷键。

        参数：
        - action_id: 动作标识符
        - shortcut: 新的快捷键字符串
        """
        self.shortcuts[action_id] = shortcut
        if action_id in self.action_map:
            self.action_map[action_id].setShortcut(shortcut)

    def get_shortcut_tips(self) -> list[tuple[str, str, str]]:
        """
        获取所有快捷键提示列表。

        返回：
        - 列表元素为 (action_id, description, shortcut)
        """
        action_descriptions = {
            "start_acquisition": "开始检测",
            "stop_acquisition": "停止检测",
            "freeze_toggle": "冻结/解冻",
            "single_shot": "单次采样",
            "fft_toggle": "频谱分析面板",
            "statistics_toggle": "缺陷统计面板",
            "shortcut_help": "快捷键帮助",
            "open_file": "打开文件",
            "save_file": "保存数据",
            "generate_report": "生成报告",
            "auto_scale": "自动缩放",
            "clear_peak": "清除峰值",
            "capture_reference": "捕获参考",
            "clear_reference": "清除参考",
            "start_record": "开始记录",
            "delete_record": "删除记录",
            "clear_records": "清空记录",
            "toggle_grid": "显示/隐藏网格",
            "toggle_cursor_label": "显示/隐藏游标标签",
        }

        tips = []
        for action_id, desc in action_descriptions.items():
            shortcut = self.shortcuts.get(action_id, "")
            if shortcut:
                tips.append((action_id, desc, shortcut))

        return tips
