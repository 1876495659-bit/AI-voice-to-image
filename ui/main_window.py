"""主窗口组装。

将所有 UI 组件组装为完整应用窗口：
顶部 = 语音反馈面板
中间 = 画布 + 状态栏
底部 = 命令历史面板

纯视觉展示界面，无按钮/菜单。

引用:
- `ui/canvas_widget.py` — CanvasWidget 画布
- `ui/status_bar.py` — StatusBar 状态栏
- `ui/voice_feedback_panel.py` — VoiceFeedbackPanel 语音反馈
- `ui/command_history_panel.py` — CommandHistoryPanel 命令历史
- `engine/drawing_engine.py` — DrawingEngine 绘图引擎
- `voice/voice_service.py` — VoiceService 语音服务
- `parser/command_parser.py` — CommandParser 命令解析
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QDockWidget,
    QGridLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QWidget,
)

import config
from engine.drawing_engine import DrawingEngine
from parser.command_parser import CommandParser, ParseResultType
from ui.canvas_widget import CanvasWidget
from ui.command_history_panel import CommandHistoryPanel
from ui.status_bar import StatusBar
from ui.voice_feedback_panel import VoiceFeedbackPanel
from voice.voice_service import VoiceService


class MainWindow(QMainWindow):
    """主窗口。纯语音控制，无按钮/菜单。

    布局:
        ┌──────────────────────────────────┐
        │      VoiceFeedbackPanel          │  ← 顶部
        ├──────────────────────────────────┤
        │                                  │
        │      CanvasWidget                │  ← 中间（约 80% 高度）
        │                                  │
        ├──────────────────────────────────┤
        │      StatusBar                   │
        ├──────────────────────────────────┤
        │      CommandHistoryPanel         │  ← 底部
        └──────────────────────────────────┘

    紧急键盘快捷键:
        - Esc: 停止监听
        - Ctrl+Z: 备用撤销
    """

    def __init__(self) -> None:
        super().__init__()

        self._setup_window()
        self._create_components()
        self._connect_signals()
        self._setup_shortcuts()

    def _setup_window(self) -> None:
        """设置主窗口属性。"""
        self.setWindowTitle("AI 语音绘图")
        self.setMinimumSize(1280, 720)
        self.resize(1920, 1080)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
        """)

    def _create_components(self) -> None:
        """创建所有子组件。"""
        # 绘图引擎
        self.engine = DrawingEngine(
            canvas_width=config.CANVAS_DEFAULT_WIDTH,
            canvas_height=config.CANVAS_DEFAULT_HEIGHT,
        )

        # 语音服务
        self.voice_service = VoiceService()

        # 命令解析器
        self.parser = CommandParser(
            fallback_threshold=config.WHISPER_FALLBACK_THRESHOLD,
            canvas_width=config.CANVAS_DEFAULT_WIDTH,
            canvas_height=config.CANVAS_DEFAULT_HEIGHT,
        )

        # UI 组件
        self.voice_panel = VoiceFeedbackPanel()
        self.canvas = CanvasWidget(
            width=config.CANVAS_DEFAULT_WIDTH,
            height=config.CANVAS_DEFAULT_HEIGHT,
        )
        self.status_bar = StatusBar()
        self.history_panel = CommandHistoryPanel()

        # 设置为中心组件
        central = QWidget()
        layout = QGridLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 语音反馈面板（顶部）
        layout.addWidget(self.voice_panel, 0, 0)

        # 画布（中间）
        layout.addWidget(self.canvas, 1, 0)

        # 状态栏（中下）
        layout.addWidget(self.status_bar, 2, 0)

        # 命令历史面板（底部）
        layout.addWidget(self.history_panel, 3, 0)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        """连接各组件信号。"""
        # 语音服务 → 语音反馈面板
        self.voice_service.signals.transcription_ready.connect(
            self._on_transcription_ready
        )
        self.voice_service.signals.listening_started.connect(
            self.voice_panel.show_listening
        )
        self.voice_service.signals.listening_stopped.connect(
            self.voice_panel.show_silence
        )
        self.voice_service.signals.error.connect(
            self.voice_panel.show_error
        )

        # 语音服务 → 状态栏
        self.voice_service.signals.listening_started.connect(
            lambda: self.status_bar.set_mic_status(True)
        )
        self.voice_service.signals.listening_stopped.connect(
            lambda: self.status_bar.set_mic_status(False)
        )

        # 引擎 → 状态栏
        self.engine.signals.state_changed.connect(
            lambda tool, color, size: self._update_status(tool, color, size)
        )

        # 引擎 → 画布
        self.engine.signals.operation_added.connect(
            self.canvas.add_operation
        )
        self.engine.signals.canvas_cleared.connect(
            self.canvas.clear
        )

    def _setup_shortcuts(self) -> None:
        """设置紧急键盘快捷键。"""
        # Esc: 停止监听
        esc_action = QAction(self)
        esc_action.setShortcut("Esc")
        esc_action.triggered.connect(self._on_escape)
        self.addAction(esc_action)

        # Ctrl+Z: 备用撤销
        undo_action = QAction(self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._on_undo)
        self.addAction(undo_action)

    # --- 信号处理 ---

    def _on_transcription_ready(self, text: str, confidence: float) -> None:
        """语音识别结果到达时的处理。

        1. 在语音面板显示识别文字
        2. 通过解析器转换为操作
        3. 执行操作
        4. 在历史面板记录
        """
        self.voice_panel.show_transcription(text, confidence)

        # 静默命令（开始/停止监听）不需要解析
        if text in ("开始监听", "开始听", "打开麦克风", "开始录音"):
            self.voice_service.start_listening()
            result = self.parser.parse(text, confidence)
            self.history_panel.add_entry(result)
            return

        if text in ("停止监听", "停止听", "关闭麦克风", "停止录音"):
            self.voice_service.stop_listening()
            return

        # 解析
        result = self.parser.parse(text, confidence)

        if result.is_success:
            # 执行操作
            self.engine.execute_multiple(result.operations)

            # 构建动作描述
            op_names = [op.op_type.name for op in result.operations]
            self.voice_panel.show_action(", ".join(op_names))

            # 记录历史
            self.history_panel.add_entry(result)

        elif result.is_uncertain:
            self.voice_panel.show_error(result.uncertain.reason if result.uncertain else "不确定")
            self.history_panel.add_entry(result)

        else:
            self.voice_panel.show_error("未识别")
            self.history_panel.add_entry(result)

    def _update_status(self, tool: str, color: str, size: int) -> None:
        """更新状态栏。"""
        self.status_bar.set_tool(tool)
        self.status_bar.set_color(color)
        self.status_bar.set_size(size)

    def _on_escape(self) -> None:
        """Esc: 停止监听。"""
        self.voice_service.stop_listening()

    def _on_undo(self) -> None:
        """Ctrl+Z: 备用撤销。"""
        self.engine.undo()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """窗口关闭时清理资源。"""
        self.voice_service.stop_listening()
        event.accept()
