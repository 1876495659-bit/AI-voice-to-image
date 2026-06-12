"""状态栏组件。

显示当前工具、颜色色块、笔刷粗细、麦克风状态。

引用:
- `engine/drawing_engine.py` — DrawingEngine.signals.state_changed 信号
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStatusBar,
    QWidget,
)


class StatusBar(QStatusBar):
    """应用状态栏。

    显示：
    - 当前工具（笔/橡皮/线条）
    - 当前颜色（色块 + HEX）
    - 当前笔刷粗细
    - 麦克风监听状态
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """初始化 UI 组件。"""
        self.setContentsMargins(8, 2, 8, 2)
        self.setStyleSheet("QStatusBar { font-size: 13px; }")

        # --- 当前工具 ---
        self.tool_label = QLabel("工具: 笔")
        self.tool_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.addWidget(self.tool_label, stretch=1)

        # --- 当前颜色 ---
        color_widget = QWidget()
        color_layout = QHBoxLayout()
        color_layout.setContentsMargins(4, 0, 4, 0)

        self.color_indicator = QLabel()
        self.color_indicator.setFixedSize(16, 16)
        self.color_indicator.setStyleSheet(
            "border: 1px solid #999; border-radius: 8px;"
        )
        color_layout.addWidget(self.color_indicator)

        self.color_label = QLabel("颜色: #000000")
        self.color_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        color_layout.addWidget(self.color_label)

        color_widget.setLayout(color_layout)
        self.addWidget(color_widget, stretch=1)

        # --- 笔刷粗细 ---
        self.size_label = QLabel("粗细: 3")
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.addWidget(self.size_label, stretch=1)

        # --- 麦克风状态 ---
        self.mic_label = QLabel("麦克风: 未连接")
        self.mic_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.addPermanentWidget(self.mic_label)

    def set_tool(self, tool: str) -> None:
        """更新当前工具显示。"""
        name_map = {
            "pen": "笔",
            "eraser": "橡皮",
            "line": "线条",
        }
        self.tool_label.setText(f"工具: {name_map.get(tool, tool)}")

    def set_color(self, hex_color: str) -> None:
        """更新当前颜色显示。"""
        self.color_label.setText(f"颜色: {hex_color}")
        self.color_indicator.setStyleSheet(
            f"background-color: {hex_color}; "
            "border: 1px solid #999; border-radius: 8px;"
        )

    def set_size(self, size: int) -> None:
        """更新笔刷粗细显示。"""
        self.size_label.setText(f"粗细: {size}")

    def set_mic_status(self, active: bool) -> None:
        """更新麦克风状态显示。"""
        if active:
            self.mic_label.setText("麦克风: 监听中")
            self.mic_label.setStyleSheet("color: #00AA00; font-weight: bold;")
        else:
            self.mic_label.setText("麦克风: 未连接")
            self.mic_label.setStyleSheet("color: #999999;")
