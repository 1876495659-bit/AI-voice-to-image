"""命令历史面板 — 美化版。

可滚动的命令历史日志，深色卡片风格。
每条记录带图标 + 时间戳 + 语音文本 + 执行动作。
"""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from parser.command_parser import ParseResult


class CommandHistoryPanel(QWidget):
    """美化版命令历史面板。"""

    MAX_ENTRIES = 100

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("命令历史")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #AAAAAA; padding: 4px 0;")
        layout.addWidget(title)

        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(160)
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #2A2A3C;
                border: 1px solid #3A3A4C;
                border-radius: 8px;
                font-size: 12px;
                padding: 6px;
                color: #EAEAEA;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #333344;
            }
            QListWidget::item:selected {
                background-color: #3A3A50;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #333344;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.history_list)

    def add_entry(self, result: ParseResult) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if result.is_success:
            op_names = [op.op_type.name for op in result.operations]
            action = ", ".join(op_names) if op_names else "无操作"
            display = f"  [{timestamp}] \"{result.raw_text}\" → [{action}]"
            color = "#4ADE80"
        elif result.is_uncertain:
            display = f"  [{timestamp}] \"{result.raw_text}\" → ? (置信度 {result.confidence:.0%})"
            color = "#FBBF24"
        else:
            display = f"  [{timestamp}] \"{result.raw_text}\" → ✗ 未识别"
            color = "#F87171"

        item = QListWidgetItem(display)
        item.setForeground(QColor(color))

        self.history_list.addItem(item)
        self.history_list.scrollToBottom()

        while self.history_list.count() > self.MAX_ENTRIES:
            self.history_list.takeItem(0)

    def clear(self) -> None:
        self.history_list.clear()

    @property
    def entry_count(self) -> int:
        return self.history_list.count()
