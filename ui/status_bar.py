"""状态栏组件 — 美化版。

显示当前工具、颜色色块、笔刷粗细、麦克风状态。
深色主题 + 胶囊样式。
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


class AppStatusBar(QStatusBar):
    """美化版状态栏 — 胶囊式信息卡片。"""

    _STYLE = """
        QLabel {{
            color: #AAAAAA;
            font-size: 12px;
            padding: 2px 8px;
            background-color: #2A2A3C;
            border-radius: 10px;
        }}
        QLabel.status-highlight {{
            color: #6C63FF;
            font-weight: bold;
        }}
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QStatusBar {{ background-color: #1E1E2E; padding: 2px; border: none; font-size: 12px; }}")
        self.setContentsMargins(8, 2, 8, 2)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.tool_label = QLabel("🖊️ 笔")
        self.tool_label.setProperty("class", "status-highlight")

        self.color_label = QLabel("颜色: #000000")

        self.size_label = QLabel("粗细: 3")

        self.mic_label = QLabel("🎤 未连接")

        self.addPermanentWidget(self.mic_label)
        self.addPermanentWidget(QLabel("  │  "))
        self.addPermanentWidget(self.size_label)
        self.addPermanentWidget(QLabel("  │  "))
        self.addPermanentWidget(self.color_label)
        self.addPermanentWidget(QLabel("  │  "))
        self.addPermanentWidget(self.tool_label)

    def set_tool(self, tool: str) -> None:
        name_map = {"pen": "🖊️ 笔", "eraser": "🧹 橡皮", "line": "📏 线条"}
        self.tool_label.setText(name_map.get(tool, f"🖊️ {tool}"))

    def set_color(self, hex_color: str) -> None:
        self.color_label.setText(f"颜色: {hex_color}")

    def set_size(self, size: int) -> None:
        self.size_label.setText(f"粗细: {size}")

    def set_mic_status(self, active: bool) -> None:
        if active:
            self.mic_label.setText("🎤 监听中")
            self.mic_label.setStyleSheet("color: #4ADE80; font-weight: bold; background-color: #1a3a2a; border-radius: 10px; padding: 2px 8px; font-size: 12px;")
        else:
            self.mic_label.setText("🎤 未连接")
            self.mic_label.setStyleSheet(AppStatusBar._STYLE)
