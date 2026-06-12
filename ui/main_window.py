"""主窗口组装 — 美化版。

新增可交互按钮：
- 左侧工具栏：工具按钮（笔/橡皮/线条/画圆/画矩形/画三角形/画星/清空/撤销）
- 底部颜色面板：30+ 颜色色块可点击选择
- 画布缩放滑块 + 导航控制
- 整体深色风格 + 圆角卡片布局

引用:
- `engine/drawing_engine.py` — DrawingEngine 绘图引擎
- `voice/voice_service.py` — VoiceService 语音服务
- `parser/command_parser.py` — CommandParser 命令解析
- `parser/color_map.py` — 颜色映射表（获取颜色名列表）
- `ui/canvas_widget.py` — CanvasWidget 画布
- `ui/voice_feedback_panel.py` — VoiceFeedbackPanel 语音反馈
- `ui/command_history_panel.py` — CommandHistoryPanel 命令历史
- `engine/operations.py` — 操作类
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect, QPointF
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QPalette,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import config
from engine.drawing_engine import DrawingEngine
from parser import color_map
from parser.command_parser import CommandParser
from ui.canvas_widget import CanvasWidget
from ui.command_history_panel import CommandHistoryPanel
from ui.voice_feedback_panel import VoiceFeedbackPanel
from voice.voice_service import VoiceService

# ── 工具栏颜色 ───────────────────────────────────────────────
BG_DARK = "#1E1E2E"
BG_CARD = "#2A2A3C"
BG_HOVER = "#3A3A50"
ACCENT = "#6C63FF"
ACCENT_PRESSED = "#5544CC"
TEXT_PRIMARY = "#EAEAEA"
TEXT_SECONDARY = "#AAAAAA"
TEXT_DIM = "#777777"
BORDER_LIGHT = "#3A3A4C"


class MainWindow(QMainWindow):
    """主窗口 — 深色主题 + 工具栏 + 颜色面板 + 画布缩放。

    布局（从左到右）:
        ┌──────┬──────────────────────────────┐
        │工具栏│  语音反馈面板                 │
        ├──────┼──────────────────────────────┤
        │      │  画布 + 缩放控制              │
        │      │                              │
        ├──────┤                              │
        │      │  命令历史面板                 │
        ├──────┤                              │
        │      │  颜色面板（30+ 色块）         │
        └──────┴──────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()

        self._setup_window()
        self._create_components()
        self._connect_signals()
        self._setup_shortcuts()

    # ── 窗口 ────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowTitle("AI 语音绘图")
        self.setMinimumSize(1100, 700)
        self.resize(1600, 950)

        # 深色主题
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(BG_DARK))
        self.setPalette(palette)

        self.setStyleSheet(f"""
            QMainWindow, QFrame {{
                background-color: {BG_DARK};
            }}
            QFrame#canvasFrame {{
                background-color: #FFFFFF;
                border: 2px solid {BORDER_LIGHT};
                border-radius: 8px;
            }}
        """)

    # ── 组件 ────────────────────────────────────────────────

    def _create_components(self) -> None:
        # 引擎
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

        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # 语音反馈面板
        self.voice_panel = VoiceFeedbackPanel()
        main_layout.addWidget(self.voice_panel)

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
                background-color: {BG_DARK};
                border: 1px solid {BORDER_LIGHT};
                border-radius: 8px;
            }}
        """)
        main_layout.addWidget(self.canvas_scroll, stretch=1)

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.main_widget)
        self.setCentralWidget(central)

    def _on_repaint(self) -> None:
        """撤销/重做后重建画布操作列表。"""
        self.canvas.clear()
        for op in self.engine.get_history():
            self.canvas._operations.append(op)
        self.canvas.update()

    def _connect_signals(self) -> None:
        """连接各组件信号。"""
        self.voice_service.signals.transcription_ready.connect(
            self._on_transcription_ready
        )
        self.voice_service.signals.partial_transcription.connect(
            self.voice_panel.show_partial_transcription
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

    def _setup_shortcuts(self) -> None:
        esc = QAction(self)
        esc.setShortcut("Esc")
        esc.triggered.connect(self.voice_service.stop_listening)
        self.addAction(esc)

        undo = QAction(self)
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
        """手动执行当前识别文本，绕过 Whisper 低置信门槛。"""
        self._execute_voice_text(text, 1.0, manual=True)

    def _on_listen_requested(self) -> None:
        """语音按钮切换监听状态。"""
        if self._voice_listening_active or self.voice_service.is_listening:
            self.voice_service.stop_listening()
            self._voice_listening_active = False
            self.voice_panel.set_listening_active(False)
            return

        if self.voice_service.start_listening():
            self._voice_listening_active = True
            self.voice_panel.set_listening_active(True)

    def _execute_voice_text(self, text: str, confidence: float, manual: bool = False) -> None:
        """解析并执行语音文本。"""
        result = self.parser.parse(text, confidence)
        if result.is_success:
            self.engine.execute_multiple(result.operations)
            op_names = [op.op_type.name for op in result.operations]
            prefix = "手动执行: " if manual else ""
            self.voice_panel.show_action(f"{prefix}{', '.join(op_names)}")
        elif result.is_uncertain:
            if result.operations:
                self.engine.execute_multiple(result.operations)
                op_names = [op.op_type.name for op in result.operations]
                prefix = "手动执行: " if manual else "低置信已执行: "
                self.voice_panel.show_action(f"{prefix}{', '.join(op_names)}")
            else:
                self.voice_panel.show_error(result.uncertain.reason if result.uncertain else "不确定")
        else:
            self.voice_panel.show_error("未识别")

    def _on_tool_selected(self, tool: str) -> None:
        """工具栏按钮触发工具切换。"""
        from engine.operations import PenTool, EraserTool, LineTool
        if tool == "pen":
            self.engine.execute(PenTool())
        elif tool == "eraser":
            self.engine.execute(EraserTool())
        elif tool == "line":
            self.engine.execute(LineTool())

    def _on_color_selected(self, hex_color: str, color_name: str) -> None:
        """颜色面板选择。"""
        from engine.operations import ColorOperation
        self.engine.execute(ColorOperation(color=hex_color))

    def _on_zoom_changed(self, value: int) -> None:
        self.canvas.set_zoom(value)


# ── 左侧工具栏 ─────────────────────────────────────────────────

class Toolbar(QFrame):
    """左侧垂直工具栏。"""

    tool_selected = pyqtSignal(str)
    action_clear = pyqtSignal()
    action_undo = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("toolbarFrame")
        self.setStyleSheet(f"""
            #toolbarFrame {{
                background-color: {BG_CARD};
                border: none;
                border-radius: 6px;
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(6)

        # 标题
        title = QLabel("工具")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; padding: 4px 0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(4)

        # 绘图工具组
        group_label = QLabel("绘图工具")
        group_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(group_label)

        self._add_tool_button("✏️ 画笔", "pen", icon="🖊️")
        self._add_tool_button("🧹 橡皮", "eraser", icon="🧽")
        self._add_tool_button("📏 线条", "line", icon="📐")
        layout.addSpacing(4)

        # 形状工具组
        shape_label = QLabel("形状工具")
        shape_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(shape_label)

        self._add_shape_button("⭕ 圆形", "画个圆")
        self._add_shape_button("🟦 矩形", "画个矩形")
        self._add_shape_button("🔺 三角形", "画个三角形")
        self._add_shape_button("⭐ 星形", "画个星")
        layout.addSpacing(4)

        # 操作组
        action_label = QLabel("操作")
        action_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 2px 0;")
        layout.addWidget(action_label)

        self._add_action_button("↩ 撤销", self._on_undo)
        self._add_action_button("🗑 清空", self._on_clear, accent=True)
        self._add_action_button("📷 AI 生成", "generate")
        layout.addSpacing(8)
        layout.addStretch()

        # 当前颜色指示
        self._color_row = QLabel("当前颜色: 黑色")
        self._color_row.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; padding: 4px 0;")
        self._color_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._color_row)

        self._color_indicator = QLabel("■")
        self._color_indicator.setFixedSize(20, 20)
        self._color_indicator.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight: bold;"
        )
        self._color_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._color_indicator, alignment=Qt.AlignmentFlag.AlignCenter)

    def _add_tool_button(self, text: str, tool: str, icon: str = "") -> None:
        btn = self._make_button(f"{icon} {text}", self._on_tool, tool)
        layout = self.layout()
        if layout:
            layout.addWidget(btn)

    def _add_shape_button(self, text: str, command: str) -> None:
        btn = self._make_button(text, self._on_shape, command)
        layout = self.layout()
        if layout:
            layout.addWidget(btn)

    def _add_action_button(self, text: str, payload, accent: bool = False) -> None:
        btn = self._make_button(text, self._on_action, payload, accent)
        layout = self.layout()
        if layout:
            layout.addWidget(btn)

    def _make_button(self, text: str, handler, payload=None, accent: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setFixedWidth(160)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._btn_style(accent))

        # 用 lambda 捕获，避免 clicked(bool) 信号传 bool 导致类型错误
        def _wrap(_=None, _h=handler, _p=payload, _b=btn):
            _h(_p)
            # 工具按钮高亮
            if _p in ("pen", "eraser", "line"):
                _b.setStyleSheet(self._btn_style(True))
        btn.clicked.connect(_wrap)
        return btn

    def _btn_style(self, active: bool = False) -> str:
        bg = ACCENT if active else BG_HOVER
        text_color = "#FFFFFF" if active else TEXT_PRIMARY
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text_color};
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_PRESSED};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT};
            }}
        """

    def _on_tool(self, tool: str) -> None:
        self.tool_selected.emit(tool)

    def _on_shape(self, command: str) -> None:
        self.tool_selected.emit(f"shape:{command}")

    def _on_undo(self) -> None:
        self.action_undo.emit()

    def _on_clear(self) -> None:
        self.action_clear.emit()

    def _on_action(self, payload) -> None:
        if payload == "generate":
            self.tool_selected.emit("ai:生成一幅美丽的风景画")

    def set_current_color(self, hex_color: str) -> None:
        name = color_map.get_color(hex_color)
        self._color_row.setText(f"当前颜色: {name}")
        self._color_indicator.setStyleSheet(
            f"background-color: {hex_color}; "
            f"border: 2px solid {TEXT_DIM}; "
            f"border-radius: 4px; "
            f"font-size: 0px;"
        )


# ── 颜色面板 ─────────────────────────────────────────────────

class ColorPalette(QWidget):
    """底部颜色面板，30+ 颜色可点击。"""

    color_selected = pyqtSignal(str, str)  # hex, name

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("颜色选择")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; padding: 0;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMaximumHeight(80)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:horizontal {{
                background: {BG_CARD};
                height: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: {BORDER_LIGHT};
                border-radius: 3px;
            }}
        """)

        self._color_grid = QWidget()
        grid_layout = QHBoxLayout(self._color_grid)
        grid_layout.setContentsMargins(4, 2, 4, 2)
        grid_layout.setSpacing(3)

        self._buttons: List[tuple] = []  # (btn, hex, name)

        for name, hex_color in color_map.COLOR_MAP.items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    border: 2px solid {BORDER_LIGHT};
                    border-radius: 14px;
                }}
                QPushButton:hover {{
                    border-color: {ACCENT};
                }}
                QPushButton:pressed {{
                    border-color: #FFFFFF;
                }}
            """)
            btn.clicked.connect(lambda _=None, _hex=hex_color, _name=name: self._on_color(_hex, _name))
            grid_layout.addWidget(btn)
            self._buttons.append((btn, hex_color, name))

        scroll.setWidget(self._color_grid)
        layout.addWidget(scroll)

    def _on_color(self, hex_color: str, name: str) -> None:
        self.color_selected.emit(hex_color, name)


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
