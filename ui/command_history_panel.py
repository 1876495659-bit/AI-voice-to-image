"""命令历史面板。

可滚动的命令历史日志，显示时间戳 + 语音文本 + 执行动作。

引用:
- `parser/command_parser.py` — ParseResult 解析结果
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from parser.command_parser import ParseResult, ParseResultType


class CommandHistoryPanel(QWidget):
    """命令历史面板。

    位于窗口底部，以可滚动列表展示历史命令。
    每条记录包含: 时间戳 + 语音文本 + 执行动作。

    最多保留 100 条记录，超出时自动清除最旧的。
    """

    MAX_ENTRIES = 100

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 分组框标题
        title = QLabel("命令历史")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("padding: 4px;")
        layout.addWidget(title)

        # 历史列表
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(200)
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #F8F8F8;
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                font-size: 12px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #EEEEEE;
            }
            QListWidget::item:selected {
                background-color: #E8F0FE;
            }
        """)
        layout.addWidget(self.history_list)

        # 清空按钮
        clear_btn = QLabel("(点击面板外任意处关闭)")
        clear_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear_btn.setStyleSheet("color: #999999; font-size: 11px;")
        layout.addWidget(clear_btn)

        self.setLayout(layout)

    # --- 公共 API ---

    def add_entry(self, result: ParseResult) -> None:
        """添加一条命令历史记录。

        Args:
            result: 解析结果。
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # 构建显示文本
        parts = [f"[{timestamp}]"]

        if result.is_success:
            # 成功: 显示语音文本 + 操作数量
            op_names = []
            for op in result.operations:
                op_names.append(op.op_type.name)
            action = ", ".join(op_names) if op_names else "无操作"
            parts.append(f"\"{result.raw_text}\" → [{action}]")
            icon = "✓"
            color = "#2E7D32"  # 绿色
        elif result.is_uncertain:
            parts.append(f"\"{result.raw_text}\" → ? (置信度 {result.confidence:.0%})")
            icon = "?"
            color = "#F57F17"  # 黄色
        else:
            parts.append(f"\"{result.raw_text}\" → ✗ (未识别)")
            icon = "✗"
            color = "#C62828"  # 红色

        display = f"{icon} {parts[-1]}"
        item = QListWidgetItem(display)
        item.setForeground(Qt.GlobalColor.darkGreen if result.is_success else
                           Qt.GlobalColor.darkYellow if result.is_uncertain else
                           Qt.GlobalColor.darkRed)

        self.history_list.addItem(item)

        # 自动滚动到底部
        self.history_list.scrollToBottom()

        # 限制条目数量
        while self.history_list.count() > self.MAX_ENTRIES:
            self.history_list.takeItem(0)

    def clear(self) -> None:
        """清空历史记录。"""
        self.history_list.clear()

    @property
    def entry_count(self) -> int:
        """当前记录数量。"""
        return self.history_list.count()
