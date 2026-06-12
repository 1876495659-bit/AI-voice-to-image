"""语音识别反馈面板。

大字显示识别到的语音文字 + 置信度进度条 + 解析动作确认。

引用:
- `voice/voice_service.py` — VoiceService.signals.transcription_ready 信号
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class VoiceFeedbackPanel(QWidget):
    """语音反馈面板。

    位于窗口顶部，提供实时语音识别反馈：
    1. 大字显示识别到的语音文字
    2. 置信度进度条（绿/黄/红）
    3. 解析动作确认（显示引擎将执行的操作）

    4 秒后自动淡出语音文字（避免屏幕堆积）。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._setup_ui()
        self._reset_timeout = QTimer(self)
        self._reset_timeout.setSingleShot(True)
        self._reset_timeout.timeout.connect(self._reset_text)

    def _setup_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # --- 识别文字 ---
        self.text_label = QLabel("请说话...")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Microsoft YaHei", 22)
        font.setBold(True)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet("color: #333333;")
        layout.addWidget(self.text_label)

        # --- 置信度进度条 ---
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #CCCCCC;
                border-radius: 6px;
                background: #F0F0F0;
                height: 14px;
            }
            QProgressBar::chunk {
                background: #00AA00;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.confidence_bar)

        # --- 解析动作 ---
        self.action_label = QLabel("")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font2 = QFont("Microsoft YaHei", 14)
        font2.setBold(False)
        self.action_label.setFont(font2)
        self.action_label.setStyleSheet("color: #666666; min-height: 20px;")
        layout.addWidget(self.action_label)

        self.setLayout(layout)

        # 背景色
        self.setStyleSheet("background-color: #FAFAFA; border-radius: 8px;")

    # --- 公共 API ---

    def show_transcription(self, text: str, confidence: float) -> None:
        """显示识别结果。

        Args:
            text: 识别到的语音文本。
            confidence: 置信度 (0-1)。
        """
        # 更新文字
        self.text_label.setText(text)
        self.text_label.setStyleSheet("color: #333333;")

        # 更新置信度条
        pct = int(confidence * 100)
        self.confidence_bar.setValue(pct)

        # 置信度颜色
        if confidence >= 0.8:
            color = "#00AA00"  # 绿色
        elif confidence >= 0.6:
            color = "#FFAA00"  # 黄色
        else:
            color = "#FF4444"  # 红色
        self.confidence_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid #CCCCCC;
                border-radius: 6px;
                background: #F0F0F0;
                height: 14px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 4px;
            }}
        """)

        # 4 秒后自动重置文字
        self._reset_timeout.stop()
        self._reset_timeout.start(4000)

    def show_action(self, action_text: str) -> None:
        """显示解析的动作确认。

        Args:
            action_text: 动作描述文本。
        """
        self.action_label.setText(f"→ {action_text}")

    def show_error(self, error_text: str) -> None:
        """显示错误提示。

        Args:
            error_text: 错误信息。
        """
        self.text_label.setText("请再说一遍")
        self.text_label.setStyleSheet("color: #FF4444;")
        self.confidence_bar.setValue(0)
        self.action_label.setText(f"→ {error_text}")

    def show_listening(self) -> None:
        """显示正在监听。"""
        self.text_label.setText("请说话...")
        self.text_label.setStyleSheet("color: #333333;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def show_silence(self) -> None:
        """显示未监听。"""
        self.text_label.setText("麦克风未连接")
        self.text_label.setStyleSheet("color: #999999;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def _reset_text(self) -> None:
        """重置文字（定时器触发）。"""
        self.text_label.setText("")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
