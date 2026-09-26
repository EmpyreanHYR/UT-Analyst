"""超声波智能辅助检测系统应用入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from app.common.logging_config import setup_logging
from app.common.auth import AuthService
from app.common.theme import buildDarkIndustrialStyleSheet
from app.controller.main_controller import MainController
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.main_window import MainWindow
from app.view.login_dialog import LoginDialog

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

    data_directory = Path(__file__).resolve().parent / "data"
    auth_service = AuthService(data_directory / "ut_analyst.db")
    login_dialog = LoginDialog(auth_service)
    if login_dialog.exec_() != LoginDialog.Accepted:
        auth_service.close()
        return 0

    signalModel = UltrasonicSignalModel()
    mainWindow = MainWindow()
    # 关键：必须持有控制器引用，避免被垃圾回收后导致菜单/工具栏无响应。
    mainWindow.mainController = MainController(
        model=signalModel,
        view=mainWindow,
        auth_service=auth_service,
        current_user=login_dialog.authenticated_user,
    )

    mainWindow.show()
    logger.info("主窗口已显示，进入事件循环")
    return application.exec_()


if __name__ == "__main__":
    sys.exit(main())
