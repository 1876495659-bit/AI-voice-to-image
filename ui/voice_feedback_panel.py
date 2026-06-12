"""语音反馈面板 — 美化版。

大字显示识别到的语音文字 + 渐变置信度条 + 解析动作。
深色主题 + 渐变背景 + 动画淡出效果。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QVariantAnimation
from PyQt6.QtGui import QFont, QLinearGradient, QColor
from PyQt6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class VoiceFeedbackPanel(QWidget):
    """美化版语音反馈面板。"""

    _BG = """
        QWidget {
            background-color: #2A2A3C;
            border-radius: 12px;
        }
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._setup_ui()
        self._reset_timeout = QTimer(self)
        self._reset_timeout.setSingleShot(True)
        self._reset_timeout.timeout.connect(self._reset_text)
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        # 识别文字 — 大字渐变
        self.text_label = QLabel("请说话...")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Microsoft YaHei", 26, QFont.Weight.Bold)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet("""
            color: #EAEAEA;
            min-height: 36px;
        """)
        layout.addWidget(self.text_label)

        # 置信度进度条 — 渐变填充
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setFixedHeight(10)
        self.confidence_bar.setStyleSheet(self._progress_style("#00AA00"))
        layout.addWidget(self.confidence_bar)

        # 解析动作
        self.action_label = QLabel("")
        font2 = QFont("Microsoft YaHei", 13)
        self.action_label.setFont(font2)
        self.action_label.setStyleSheet("color: #AAAAAA; min-height: 20px;")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.action_label)

        self.setStyleSheet(self._BG)

    # ── 进度条样式 ──────────────────────────────────────────

    def _progress_style(self, color: str) -> str:
        return f"""
            QProgressBar {{
                background-color: #1a1a2a;
                border: none;
                border-radius: 5px;
                height: 10px;
            }}
            QProgressBar::chunk {{
                background: QLinearGradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {color},
                    stop: 1 {color}cc
                );
                border-radius: 5px;
            }}
        """

    # ── 公共 API ──────────────────────────────────────────

    def show_transcription(self, text: str, confidence: float) -> None:
        self.text_label.setText(text)
        self.text_label.setStyleSheet("color: #EAEAEA; min-height: 36px;")

        pct = int(confidence * 100)
        self.confidence_bar.setValue(pct)

        if confidence >= 0.8:
            color = "#4ADE80"   # 绿色
        elif confidence >= 0.6:
            color = "#FBBF24"   # 黄色
        else:
            color = "#F87171"   # 红色
        self.confidence_bar.setStyleSheet(self._progress_style(color))

        # 显示动作
        self._fade_timer.stop()
        self._fade_timer.start(3000)

    def show_action(self, action_text: str) -> None:
        self.action_label.setText(f"→ {action_text}")

    def show_error(self, error_text: str) -> None:
        self.text_label.setText("请再说一遍")
        self.text_label.setStyleSheet("color: #F87171; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText(f"→ {error_text}")

    def show_listening(self) -> None:
        self.text_label.setText("请说话...")
        self.text_label.setStyleSheet("color: #EAEAEA; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def show_silence(self) -> None:
        self.text_label.setText("麦克风未连接")
        self.text_label.setStyleSheet("color: #777777; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def _reset_text(self) -> None:
        self.text_label.setText("")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def _fade_out(self) -> None:
        """渐变淡出效果."""
        self.action_label.clear()
