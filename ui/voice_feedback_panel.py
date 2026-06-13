"""语音反馈面板 — 极简留白风格。

显示:
- 麦克风状态指示灯（● 圆形呼吸动画）
- 识别文字（大字居中）
- 置信度进度条
- 语音按钮（开始/停止）

引用:
- `voice/voice_service.py` — VoiceService.signals.*
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class VoiceFeedbackPanel(QWidget):
    """极简语音反馈面板。"""

    execute_requested = pyqtSignal(str)
    listen_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._listening = False
        self._last_text = ""

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._reset_text)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(600)
        self._pulse_timer.timeout.connect(self._pulse_opacity)
        self._pulse_val = 1.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        self.setStyleSheet("background: transparent;")

        # ── 顶部: 麦克风状态 + 识别文字 ──
        top = QVBoxLayout()
        top.setSpacing(8)

        # 状态行: 指示灯 + 文字
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        # 麦克风指示灯
        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.status_indicator.setStyleSheet("color: #D2D2D7;")
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.status_indicator, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch()

        # 识别文字
        self.text_label = QLabel("请说话...")
        self.text_label.setFont(QFont("Microsoft YaHei", 22, QFont.Weight.Bold))
        self.text_label.setStyleSheet("color: #1D1D1F;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        status_row.addWidget(self.text_label)

        top.addLayout(status_row)
        top.addStretch()

        # 置信度进度条
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setFixedHeight(6)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E8E8ED;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #0071E3;
                border-radius: 3px;
            }
        """)
        top.addWidget(self.confidence_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(top)

        # 语音按钮
        self.listen_button = QPushButton("开始语音识别")
        self.listen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_button.setFixedHeight(44)
        self.listen_button.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Medium))
        self.listen_button.setStyleSheet("""
            QPushButton {
                background-color: #0071E3;
                color: #FFFFFF;
                border: none;
                border-radius: 22px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0066D0;
            }
            QPushButton:pressed {
                background-color: #005BB5;
            }
            QPushButton:disabled {
                background-color: #D2D2D7;
            }
        """)
        self.listen_button.clicked.connect(self.listen_requested.emit)
        layout.addWidget(self.listen_button)

        # 解析动作提示
        self.action_label = QLabel("")
        self.action_label.setFont(QFont("Microsoft YaHei", 12))
        self.action_label.setStyleSheet("color: #86868B;")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_label.setFixedHeight(20)
        layout.addWidget(self.action_label)

        layout.addStretch()

        self.setLayout(layout)

    # ── 状态更新 ──

    def show_transcription(self, text: str, confidence: float) -> None:
        self._last_text = text.strip()
        self.text_label.setText(text)
        self.text_label.setStyleSheet("color: #1D1D1F;")
        pct = int(confidence * 100)
        self.confidence_bar.setValue(pct)

        if confidence >= 0.8:
            self.confidence_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E8E8ED;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #34C759;
                    border-radius: 3px;
                }
            """)
        elif confidence >= 0.6:
            self.confidence_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E8E8ED;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #FF9F0A;
                    border-radius: 3px;
                }
            """)
        else:
            self.confidence_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E8E8ED;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #FF453A;
                    border-radius: 3px;
                }
            """)

        self._pulse_timer.stop()
        self._reset_timer.stop()
        self._reset_timer.start(4000)

    def show_partial_transcription(self, text: str) -> None:
        self._last_text = text.strip()
        self.text_label.setText(text)
        self.text_label.setStyleSheet("color: #86868B;")
        self.action_label.setText("正在识别...")

    def show_recognition_started(self) -> None:
        self.text_label.setText("正在整理文字...")
        self.text_label.setStyleSheet("color: #86868B;")
        self.action_label.setText("")

    def show_action(self, action_text: str) -> None:
        self.action_label.setText(action_text)
        self._reset_timer.stop()
        self._reset_timer.start(5000)

    def show_error(self, error_text: str) -> None:
        if not self._last_text:
            self.text_label.setText("请再说一遍")
        self.text_label.setStyleSheet("color: #FF453A;")
        self.confidence_bar.setValue(0)
        self.action_label.setText(f"→ {error_text}")
        self._pulse_timer.stop()

    def show_listening(self) -> None:
        self.text_label.setText("请说话...")
        self.text_label.setStyleSheet("color: #1D1D1F;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
        self.listen_button.setText("停止语音识别")
        self.status_indicator.setStyleSheet("color: #34C759;")
        self._pulse_timer.start()

    def show_silence(self) -> None:
        self.text_label.setText("语音识别已停止")
        self.text_label.setStyleSheet("color: #86868B;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
        self.listen_button.setText("开始语音识别")
        self.status_indicator.setStyleSheet("color: #D2D2D7;")
        self._pulse_timer.stop()

    def show_volume(self, rms: float) -> None:
        """不显示音量柱状图，仅触发呼吸灯。"""
        if rms > 0.02:
            self.status_indicator.setStyleSheet("color: #34C759;")

    def _pulse_opacity(self) -> None:
        self._pulse_val = 1.0 if self._pulse_val < 0.5 else 0.4
        alpha = int(self._pulse_val * 255)
        self.status_indicator.setStyleSheet(
            f"color: rgba(52, 199, 89, {self._pulse_val:.1f});"
        )

    def _reset_text(self) -> None:
        self.text_label.setText("请说话...")
        self.text_label.setStyleSheet("color: #1D1D1F;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")

    def set_listening_active(self, active: bool) -> None:
        self.listen_button.setText("停止语音识别" if active else "开始语音识别")
