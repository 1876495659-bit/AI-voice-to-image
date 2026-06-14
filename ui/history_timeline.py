"""操作历史时间线面板 — 右侧可视化绘制步骤。

显示画布上所有操作的顺序时间线，每条记录含图标 + 操作名称。
点击某条可撤销到该步骤。

引用:
- `engine/operations.py` — DrawingOperation 数据类 + OperationType 枚举
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from engine.operations import (
    BackgroundOperation,
    DrawingOperation,
    OperationType,
)


class HistoryTimelinePanel(QWidget):
    """操作历史时间线面板。

    右侧面板，以垂直列表展示所有绘制步骤。
    每条记录包含序号 + 图标 + 操作名称。
    点击某条会撤销到该步（回退到该操作之后的所有操作）。
    """

    item_clicked = pyqtSignal(QListWidgetItem)

    MAX_ENTRIES = 100

    # 操作类型 → 图标映射
    _OP_ICONS: dict[OperationType, str] = {
        OperationType.PEN: "✏️",
        OperationType.ERASER: "🧹",
        OperationType.LINE: "📏",
        OperationType.COLOR: "🎨",
        OperationType.SIZE: "📐",
        OperationType.FREEHAND: "〰️",
        OperationType.LINE_DRAW: "➖",
        OperationType.RECTANGLE: "▭",
        OperationType.CIRCLE: "◯",
        OperationType.TRIANGLE: "△",
        OperationType.STAR: "☆",
        OperationType.AI_IMAGE: "🖼️",
        OperationType.BACKGROUND: "🖌️",
        OperationType.SELECT_LAST: "👆",
        OperationType.MOVE_SELECTED: "↔️",
        OperationType.SCALE_SELECTED: "🔍",
        OperationType.RECOLOR_SELECTED: "🔄",
        OperationType.DELETE_SELECTED: "🗑️",
        OperationType.LABEL_SELECTED: "🏷️",
        OperationType.ANCHOR_SHAPE: "📍",
        OperationType.UNDO: "↩️",
        OperationType.REDO: "↪️",
        OperationType.CLEAR: "❌",
    }

    # 操作类型 → 中文标签映射
    _OP_LABELS: dict[OperationType, str] = {
        OperationType.PEN: "笔工具",
        OperationType.ERASER: "橡皮工具",
        OperationType.LINE: "线条工具",
        OperationType.COLOR: "颜色",
        OperationType.SIZE: "粗细",
        OperationType.FREEHAND: "手绘",
        OperationType.LINE_DRAW: "直线",
        OperationType.RECTANGLE: "矩形",
        OperationType.CIRCLE: "圆形",
        OperationType.TRIANGLE: "三角形",
        OperationType.STAR: "星形",
        OperationType.AI_IMAGE: "AI 图像",
        OperationType.BACKGROUND: "背景色",
        OperationType.SELECT_LAST: "选中图形",
        OperationType.MOVE_SELECTED: "移动图形",
        OperationType.SCALE_SELECTED: "缩放图形",
        OperationType.RECOLOR_SELECTED: "修改颜色",
        OperationType.DELETE_SELECTED: "删除图形",
        OperationType.LABEL_SELECTED: "标注图形",
        OperationType.ANCHOR_SHAPE: "参照绘制",
        OperationType.UNDO: "撤销",
        OperationType.REDO: "重做",
        OperationType.CLEAR: "清空画布",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("操作时间线")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #AAAAAA; padding: 4px 0;")
        layout.addWidget(title)

        self.timeline_list = QListWidget()
        self.timeline_list.setStyleSheet("""
            QListWidget {
                background-color: #FAFAFA;
                border: 1px solid #E8E8ED;
                border-radius: 8px;
                font-size: 11px;
                padding: 6px;
                color: #1D1D1F;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #F0F0F5;
            }
            QListWidget::item:selected {
                background-color: #E8F2FF;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #F5F5F7;
                border-radius: 4px;
            }
        """)
        self.timeline_list.currentItemChanged.connect(self._on_item_selected)
        layout.addWidget(self.timeline_list)

    def _on_item_selected(self, current: Optional[QListWidgetItem],
                          previous: Optional[QListWidgetItem]) -> None:
        if current:
            self.item_clicked.emit(current)

    def update_from_history(self, operations: List[DrawingOperation]) -> None:
        """从引擎历史更新时间线显示。"""
        self.timeline_list.clear()
        for i, op in enumerate(operations):
            icon = self._OP_ICONS.get(op.op_type, "●")
            label = self._get_op_label(op)
            text = f"  {i + 1}. {icon} {label}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.timeline_list.addItem(item)

        if self.timeline_list.count() > 0:
            self.timeline_list.scrollToBottom()

    def _get_op_label(self, op: DrawingOperation) -> str:
        """获取操作的人类可读标签。"""
        base_label = self._OP_LABELS.get(op.op_type, op.op_type.name)
        # 添加颜色/粗细等额外信息
        if op.op_type == OperationType.COLOR:
            base_label = f"颜色: {op.color}"
        elif op.op_type == OperationType.SIZE:
            base_label = f"粗细: {op.size}"
        elif op.op_type == OperationType.BACKGROUND:
            base_label = f"背景色: {op.color}"
        elif op.op_type == OperationType.AI_IMAGE:
            # 截取提示词前 20 字
            prompt = getattr(op, "prompt", "")
            if prompt:
                base_label = f"AI: {prompt[:20]}"
        return base_label

    def clear(self) -> None:
        self.timeline_list.clear()
