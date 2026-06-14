"""主窗口 — 极简留白风格。

仅保留两块内容：
1. 中央白布（画布）
2. 底部语音输入指示器（麦克风状态 + 识别文字）

移除了：左侧工具栏、颜色面板、命令历史面板、音量柱状图、缩放滑块。
所有交互通过语音完成。

引用:
- `engine/drawing_engine.py` — DrawingEngine 绘图引擎
- `voice/voice_service.py` — VoiceService 语音服务
- `parser/command_parser.py` — CommandParser 命令解析
- `ui/canvas_widget.py` — CanvasWidget 画布
- `ui/voice_feedback_panel.py` — VoiceFeedbackPanel 语音反馈
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import config
from ai.drawing_agent import DrawingAgent
from engine.drawing_engine import DrawingEngine
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    DeleteSelectedOperation,
    FreehandOperation,
    LineDrawOperation,
    LabelSelectedOperation,
    MoveSelectedOperation,
    RecolorSelectedOperation,
    RectangleOperation,
    ScaleSelectedOperation,
    SelectLastOperation,
    StarOperation,
    TriangleOperation,
)
from parser.command_parser import CommandParser
from ui.canvas_widget import CanvasWidget
from ui.voice_feedback_panel import VoiceFeedbackPanel
from voice.voice_service import VoiceService

logger = logging.getLogger(__name__)

# ── 极简配色 ───────────────────────────────────────────────
BG = "#F5F5F7"          # Apple 浅灰背景
WHITE = "#FFFFFF"        # 画布白
INK = "#1D1D1F"          # 主文字（Apple 深灰）
MUTED = "#86868B"        # 次要文字
ACCENT = "#0071E3"       # Apple 蓝
ACCENT_SOFT = "#E8F2FF"  # 蓝色浅底
BORDER = "#D2D2D7"       # 微妙边框


class MainWindow(QMainWindow):
    """极简语音绘图窗口。

    布局:
        ┌─────────────────────────────────┐
        │                                 │
        │         白布（画布）             │
        │                                 │
        │                                 │
        ├─────────────────────────────────┤
        │   🎤  请说话...                  │
        │   ━━━━━━━━━━━━━━━━━━━━ 进度条    │
        │   [ 开始语音识别 ]               │
        └─────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()

        self._setup_window()
        self._create_components()
        self._connect_signals()
        self._setup_shortcuts()

    # ── 窗口 ────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowTitle("语音绘图")
        self.setMinimumSize(960, 640)
        self.resize(1280, 860)

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(BG))
        self.setPalette(palette)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG};
            }}
        """)

    # ── 组件 ────────────────────────────────────────────────

    def _create_components(self) -> None:
        # 引擎 + 服务
        self.engine = DrawingEngine(
            canvas_width=config.CANVAS_DEFAULT_WIDTH,
            canvas_height=config.CANVAS_DEFAULT_HEIGHT,
        )
        self.voice_service = VoiceService()
        self._voice_listening_active = False
        self.parser = CommandParser(
            fallback_threshold=config.WHISPER_FALLBACK_THRESHOLD,
            canvas_width=config.CANVAS_DEFAULT_WIDTH,
            canvas_height=config.CANVAS_DEFAULT_HEIGHT,
        )
        self.drawing_agent = DrawingAgent()

        # 画布（白布）
        self.canvas = CanvasWidget(
            width=config.CANVAS_DEFAULT_WIDTH,
            height=config.CANVAS_DEFAULT_HEIGHT,
        )
        self.canvas.set_zoom(50)

        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG};
                border: none;
            }}
        """)

        # 语音反馈面板
        self.voice_panel = VoiceFeedbackPanel()

        # 操作历史时间线面板
        from ui.history_timeline import HistoryTimelinePanel
        self.timeline_panel = HistoryTimelinePanel()

        # 主布局 — 左右分栏：左侧画布+语音，右侧时间线
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # 左侧: 画布区域 + 语音面板
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(16)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("canvasFrame")
        canvas_frame.setStyleSheet(f"""
            #canvasFrame {{
                background-color: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 16px;
            }}
        """)
        canvas_inner = QVBoxLayout(canvas_frame)
        canvas_inner.setContentsMargins(0, 0, 0, 0)
        canvas_inner.addWidget(self.canvas_scroll)
        left_col.addWidget(canvas_frame, stretch=1)
        left_col.addWidget(self.voice_panel)

        main_layout.addLayout(left_col, stretch=1)

        # 右侧: 时间线面板
        main_layout.addWidget(self.timeline_panel, stretch=0)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.voice_service.signals.transcription_ready.connect(
            self._on_transcription_ready
        )
        self.voice_service.signals.partial_transcription.connect(
            self.voice_panel.show_partial_transcription
        )
        self.voice_service.signals.recognition_started.connect(
            self.voice_panel.show_recognition_started
        )
        self.voice_service.signals.listening_started.connect(
            self._on_listening_started
        )
        self.voice_service.signals.listening_stopped.connect(
            self._on_listening_stopped
        )
        self.voice_service.signals.error.connect(
            self.voice_panel.show_error
        )
        self.voice_service.audio_buffer.volume_changed.connect(
            self.voice_panel.show_volume
        )
        self.voice_panel.listen_requested.connect(
            self._on_listen_requested
        )
        self.engine.signals.operation_added.connect(
            self.canvas.add_operation
        )
        self.engine.signals.canvas_cleared.connect(
            self.canvas.clear
        )
        self.engine.signals.repaint.connect(
            self._on_repaint
        )
        self.engine.signals.selection_changed.connect(
            self.canvas.set_selected_operation
        )
        self.engine.signals.edit_failed.connect(
            self.voice_panel.show_error
        )
        self.engine.signals.background_changed.connect(
            self.canvas.set_background_color
        )
        self.timeline_panel.item_clicked.connect(
            self._on_timeline_click
        )

    def _setup_shortcuts(self) -> None:
        esc = QAction("Esc", self)
        esc.setShortcut("Esc")
        esc.triggered.connect(self.voice_service.stop_listening)
        self.addAction(esc)

        undo = QAction("Undo", self)
        undo.setShortcut("Ctrl+Z")
        undo.triggered.connect(self.engine.undo)
        self.addAction(undo)

    # ── 信号处理 ──────────────────────────────────────────

    def _on_transcription_ready(self, text: str, confidence: float) -> None:
        self.voice_panel.show_transcription(text, confidence)

        if text in ("开始监听", "开始听", "打开麦克风", "开始录音"):
            self.voice_service.start_listening()
            return
        if text in ("停止监听", "停止听", "关闭麦克风", "停止录音"):
            self.voice_service.stop_listening()
            return

        self._execute_voice_text(text, confidence)

    def _on_listening_started(self) -> None:
        self._voice_listening_active = True
        self.voice_panel.show_listening()

    def _on_listening_stopped(self) -> None:
        self._voice_listening_active = False
        self.voice_panel.show_silence()

    def _on_execute_requested(self, text: str) -> None:
        self._execute_voice_text(text, 1.0, manual=True)

    def _on_listen_requested(self) -> None:
        if self._voice_listening_active or self.voice_service.is_listening:
            self.voice_service.stop_listening()
            self._voice_listening_active = False
            self.voice_panel.set_listening_active(False)
            return

        if self.voice_service._base_model is None:
            self.voice_panel.show_error("语音识别模型未就绪，请稍后再试")
            return

        if self.voice_service.start_listening():
            self._voice_listening_active = True
            self.voice_panel.set_listening_active(True)

    def _execute_voice_text(self, text: str, confidence: float, manual: bool = False) -> None:
        agent_ops = self.drawing_agent.plan(text, self.engine)
        if agent_ops:
            if self._requires_edit_target(agent_ops) and not self.engine.has_edit_target():
                self.voice_panel.show_error("没有可编辑的图形，请先画一个图形")
                return
            self.engine.execute_multiple(agent_ops)
            self.voice_panel.show_action(self._describe_operations(agent_ops))
            return

        result = self.parser.parse(text, confidence)
        if result.is_success:
            if self._requires_edit_target(result.operations) and not self.engine.has_edit_target():
                self.voice_panel.show_error("没有可编辑的图形，请先画一个图形")
                return
            self.engine.execute_multiple(result.operations)
            prefix = "已执行: " if not manual else "手动执行: "
            self.voice_panel.show_action(f"{prefix}{self._describe_operations(result.operations)}")
        elif result.is_uncertain:
            if result.operations:
                if self._requires_edit_target(result.operations) and not self.engine.has_edit_target():
                    self.voice_panel.show_error("没有可编辑的图形，请先画一个图形")
                    return
                self.engine.execute_multiple(result.operations)
                prefix = "手动执行: " if manual else "低置信已执行: "
                self.voice_panel.show_action(f"{prefix}{self._describe_operations(result.operations)}")
            else:
                self.voice_panel.show_error(result.uncertain.reason if result.uncertain else "不确定")
        else:
            self.voice_panel.show_error("未识别")

    def _describe_operations(self, operations) -> str:
        if not operations:
            return "未识别"

        op = operations[-1]
        if isinstance(op, MoveSelectedOperation):
            if op.target_position is not None:
                return "已将图形移动到指定位置"
            if abs(op.dx) >= abs(op.dy):
                direction = "右" if op.dx > 0 else "左"
                amount = abs(op.dx)
            else:
                direction = "下" if op.dy > 0 else "上"
                amount = abs(op.dy)
            return f"已将最近图形向{direction}移动 {amount}px"
        if isinstance(op, ScaleSelectedOperation):
            if op.factor >= 1:
                return f"已将最近图形放大 {int(round((op.factor - 1) * 100))}%"
            return f"已将最近图形缩小 {int(round((1 - op.factor) * 100))}%"
        if isinstance(op, RecolorSelectedOperation):
            return "已修改最近图形颜色"
        if isinstance(op, LabelSelectedOperation):
            return f"已记住：这个图形是{op.label}"
        if isinstance(op, DeleteSelectedOperation):
            return "已删除最近图形"
        if isinstance(op, SelectLastOperation):
            return "已选中最近图形"
        if any(getattr(item, "semantic_label", "").startswith("太阳") for item in operations):
            return "已补充太阳细节"

        return ", ".join(item.op_type.name for item in operations)

    def _requires_edit_target(self, operations) -> bool:
        return any(isinstance(op, (
            MoveSelectedOperation,
            RecolorSelectedOperation,
            ScaleSelectedOperation,
            SelectLastOperation,
            DeleteSelectedOperation,
            LabelSelectedOperation,
        )) for op in operations)

    def _on_repaint(self) -> None:
        self.canvas.clear()
        self.canvas.set_background_color(self.engine.background_color)
        for op in self.engine.get_history():
            if self._is_renderable_operation(op):
                self.canvas._operations.append(op)
        self.canvas.set_selected_operation(self.engine.selected_operation_id)
        self.canvas.update()
        # 更新时间线
        self.timeline_panel.update_from_history(self.engine.get_history())

    def _on_timeline_click(self, item) -> None:
        """点击时间线某项，撤销到该步。"""
        index = item.data(Qt.ItemDataRole.UserRole)
        history = self.engine.get_history()
        steps_to_undo = len(history) - 1 - index
        if steps_to_undo > 0:
            for _ in range(steps_to_undo):
                self.engine.undo()

    def _is_renderable_operation(self, operation) -> bool:
        return isinstance(operation, (
            AIImageOperation,
            CircleOperation,
            FreehandOperation,
            LineDrawOperation,
            RectangleOperation,
            StarOperation,
            TriangleOperation,
        ))


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("语音绘图")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
