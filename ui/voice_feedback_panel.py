"""语音反馈面板 — 增强版。

大字显示识别到的语音文字 + 置信度进度条 + 解析动作确认。
新增: 实时音量柱状图可视化，让你能看到麦克风是否收到声音。
引用:
- `voice/voice_service.py` — VoiceService.signals.transcription_ready 信号
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QLinearGradient
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class VoiceFeedbackPanel(QWidget):
    """增强版语音反馈面板。"""

    execute_requested = pyqtSignal(str)
    listen_requested = pyqtSignal()

    _BG = """
        QWidget {
            background-color: #2A2A3C;
            border-radius: 12px;
        }
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._setup_ui()
        self._last_text = ""
        self._reset_timeout = QTimer(self)
        self._reset_timeout.setSingleShot(True)
        self._reset_timeout.timeout.connect(self._reset_text)
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        # --- 音量指示器 ---
        vol_layout = QVBoxLayout()
        vol_title = QLabel("🎤 麦克风音量")
        vol_title.setFont(QFont("Microsoft YaHei", 11))
        vol_title.setStyleSheet("color: #AAAAAA; padding: 0;")
        vol_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_layout.addWidget(vol_title)

        # 音量条容器
        self.volume_frame = QWidget()
        self.volume_frame.setFixedHeight(60)
        self.volume_frame.setStyleSheet("background: transparent;")
        vol_layout.addWidget(self.volume_frame)

        volume_h = QHBoxLayout(self.volume_frame)
        volume_h.setContentsMargins(10, 10, 10, 5)
        volume_h.setSpacing(3)

        # 15 个音量条
        self.vol_bars: list[QLabel] = []
        for i in range(15):
            bar = QLabel()
            bar.setFixedSize(20, 30)
            bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bar.setStyleSheet(self._vol_bar_style("#555555", 10))
            volume_h.addWidget(bar)
            self.vol_bars.append(bar)

        volume_h.addStretch()

        layout.addLayout(vol_layout)
        layout.addSpacing(4)

        # --- 识别文字 ---
        self.text_label = QLabel("请说话...")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Microsoft YaHei", 24, QFont.Weight.Bold)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet("color: #EAEAEA; min-height: 36px;")
        layout.addWidget(self.text_label)

        # --- 置信度进度条 ---
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setFixedHeight(10)
        self.confidence_bar.setStyleSheet(self._progress_style("#00AA00"))
        layout.addWidget(self.confidence_bar)

        self.listen_button = QPushButton("开始语音识别")
        self.listen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_button.setFixedHeight(40)
        self.listen_button.setStyleSheet("""
            QPushButton {
                background-color: #6C63FF;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5544CC;
            }
        """)
        self.listen_button.clicked.connect(self.listen_requested.emit)
        layout.addWidget(self.listen_button)

        # --- 解析动作 ---
        self.action_label = QLabel("")
        font2 = QFont("Microsoft YaHei", 13)
        self.action_label.setFont(font2)
        self.action_label.setStyleSheet("color: #AAAAAA; min-height: 20px;")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.action_label)

        self.setLayout(layout)
        self.setStyleSheet(self._BG)

    # ── 样式 ──────────────────────────────────────────────

    def _vol_bar_style(self, color: str, height: int = 30) -> str:
        return f"""
            QLabel {{
                background-color: {color};
                border-radius: 3px;
                min-height: {height}px;
                max-height: {height}px;
            }}
        """

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

    def _update_volume_display(self, rms: float) -> None:
        """根据 RMS 音量更新柱状图。"""
        intensity = min(14, int(rms * 100))  # 0-14 格
        for i, bar in enumerate(self.vol_bars):
            if i < intensity:
                if rms > 0.05:
                    color = "#F87171"   # 高音量红色
                elif rms > 0.01:
                    color = "#FBBF24"   # 中音量黄色
                else:
                    color = "#4ADE80"   # 低音量绿色
                bar.setStyleSheet(self._vol_bar_style(color, 10 + i * 2))
                bar.show()
            else:
                bar.setStyleSheet(self._vol_bar_style("#555555", 10))
                bar.hide()

    # ── 公共 API ──────────────────────────────────────────

    def show_transcription(self, text: str, confidence: float) -> None:
        self._last_text = text.strip()
        self.text_label.setText(text)
        self.text_label.setStyleSheet("color: #EAEAEA; min-height: 36px;")
        pct = int(confidence * 100)
        self.confidence_bar.setValue(pct)
        if confidence >= 0.8:
            color = "#4ADE80"
        elif confidence >= 0.6:
            color = "#FBBF24"
        else:
            color = "#F87171"
        self.confidence_bar.setStyleSheet(self._progress_style(color))
        self._fade_timer.stop()
        self._fade_timer.start(3000)

    def show_action(self, action_text: str) -> None:
        self.action_label.setText(f"→ {action_text}")

    def show_error(self, error_text: str) -> None:
        if not self._last_text:
            self.text_label.setText("请再说一遍")
        self.text_label.setStyleSheet("color: #F87171; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText(f"→ {error_text}")

    def show_listening(self) -> None:
        self.text_label.setText("请说话...")
        self.text_label.setStyleSheet("color: #EAEAEA; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
        self.listen_button.setText("停止语音识别")

    def show_silence(self) -> None:
        self.text_label.setText("语音识别已停止")
        self.text_label.setStyleSheet("color: #777777; min-height: 36px;")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
        self.listen_button.setText("开始语音识别")

    def show_volume(self, rms: float) -> None:
        """显示音量（由 AudioBuffer.volume_changed 连接）。"""
        self._update_volume_display(rms)

    def _reset_text(self) -> None:
        self.text_label.setText("")
        self.confidence_bar.setValue(0)
        self.action_label.setText("")
        self.listen_button.setText("开始语音识别")

    def _fade_out(self) -> None:
        self.action_label.clear()

    def _emit_execute_requested(self) -> None:
        if self._last_text:
            self.execute_requested.emit(self._last_text)

    def set_listening_active(self, active: bool) -> None:
        self.listen_button.setText("停止语音识别" if active else "开始语音识别")
