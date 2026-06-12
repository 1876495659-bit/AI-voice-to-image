"""AI 语音绘图工具 - 应用入口。

启动流程:
1. 创建 PyQt6 应用
2. 初始化 MainWindow（含 DrawingEngine / VoiceService / Canvas / UI）
3. 加载 Whisper 语音模型
4. 显示主窗口，进入事件循环

用法:
    python main.py

环境变量:
    OPENAI_API_KEY: DALL·E API 密钥（AI 生成功能需要）
"""

import logging
import sys

# 必须在 import PyQt6 之前设置
import os
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "Lib", "site-packages", "PyQt6", "Qt6", "plugins"
)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """应用入口。"""
    # Qt 应用高 DPI 缩放支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AI 语音绘图")
    app.setOrganizationName("AI-Voice-To-Image")

    # 创建并显示主窗口
    window = MainWindow()

    # 初始化语音服务（加载 Whisper 模型）
    logger.info("正在初始化语音识别...")
    if not window.voice_service.initialize():
        logger.warning("语音识别初始化失败，仍可正常使用绘图功能")
        window.voice_panel.show_error("语音识别不可用，请检查 whisper 安装")

    window.show()

    # 进入事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
