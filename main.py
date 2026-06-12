"""AI 语音绘图工具 - 应用入口。

用法:
    python main.py

环境变量:
    OPENAI_API_KEY: DALL·E API 密钥（AI 生成功能需要）
"""

import logging
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def initialize_voice(window: Any) -> bool:
    """初始化语音模型，等待用户点击按钮开始监听。"""
    logger.info("正在初始化语音识别...")
    if not window.voice_service.initialize():
        logger.warning("语音识别初始化失败，仍可正常使用绘图功能")
        window.voice_panel.show_error("语音识别不可用，请检查 whisper 安装")
        return False

    logger.info("语音识别已就绪，等待用户点击按钮开始监听")
    return True


def main() -> None:
    """应用入口。"""
    # 定位 PyQt6.Qt6.plugins 目录
    try:
        import PyQt6
        plugin_path = str(Path(PyQt6.__file__).parent / "Qt6" / "plugins")
        import os
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
    except Exception:
        pass

    # Qt 应用高 DPI 缩放支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AI 语音绘图")
    app.setOrganizationName("AI-Voice-To-Image")

    # 创建并显示主窗口
    window = MainWindow()

    # 初始化语音服务（加载 Whisper 模型，麦克风由界面按钮启动）
    initialize_voice(window)

    window.show()
    logger.info("窗口已显示，进入事件循环...")

    # 进入事件循环
    exit_code = app.exec()
    logger.info(f"应用退出，代码: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
