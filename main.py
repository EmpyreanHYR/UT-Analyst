"""超声波智能辅助检测系统应用入口。"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from app.common.logging_config import setup_logging
from app.common.theme import buildDarkIndustrialStyleSheet
from app.controller.main_controller import MainController
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.main_window import MainWindow

# 初始化日志系统。
logger = setup_logging()


def main() -> int:
    """
    应用主函数。

    执行流程：
    1. 初始化 QApplication；
    2. 应用深色工业主题；
    3. 创建 MVC 三层对象并建立连接；
    4. 显示主窗口，进入事件循环。
    """
    logger.info("应用启动")
    application = QApplication(sys.argv)
    application.setApplicationName("超声波智能辅助检测系统")
    application.setStyleSheet(buildDarkIndustrialStyleSheet())

    signalModel = UltrasonicSignalModel()
    mainWindow = MainWindow()
    # 关键：必须持有控制器引用，避免被垃圾回收后导致菜单/工具栏无响应。
    mainWindow.mainController = MainController(model=signalModel, view=mainWindow)

    mainWindow.show()
    logger.info("主窗口已显示，进入事件循环")
    return application.exec_()


if __name__ == "__main__":
    sys.exit(main())
