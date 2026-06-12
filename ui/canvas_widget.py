"""画布渲染组件。

自定义 QWidget，重写 paintEvent() 用 QPainter 渲染所有绘图操作。
监听 DrawingEngine 的信号，收到新操作后自动重绘。

引用:
- `config.py` — CANVAS_DEFAULT_WIDTH/HEIGHT, CANVAS_BACKGROUND_COLOR
- `engine/operations.py` — DrawingOperation 及其子类
- `engine/drawing_engine.py` — DrawingEngine 信号
"""

from __future__ import annotations

import math
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QBrush,
    QPen,
    QPolygon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

import config
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    DrawingOperation,
    FreehandOperation,
    LineDrawOperation,
    OperationType,
    RectangleOperation,
    StarOperation,
    TriangleOperation,
)


class CanvasWidget(QWidget):
    """可绘制的画布组件。

    职责：
    1. 维护操作列表（由 DrawingEngine 信号驱动添加）
    2. 在 paintEvent 中用 QPainter 按顺序渲染所有操作
    3. 提供画布背景色、光标样式等视觉配置

    Attributes:
        operation_added: 外部信号，可由 DrawingEngine 连接。
        canvas_cleared: 清空画布信号。
    """

    # 供外部（DrawingEngine）连接的信号
    operation_added = pyqtSignal(DrawingOperation)
    canvas_cleared = pyqtSignal()

    def __init__(self, width: int = config.CANVAS_DEFAULT_WIDTH,
                 height: int = config.CANVAS_DEFAULT_HEIGHT,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._operations: List[DrawingOperation] = []
        self._background_color: str = config.CANVAS_BACKGROUND_COLOR

        # 设置固定尺寸
        self.setFixedSize(width, height)

        # 白色背景，无边框
        self.setStyleSheet(
            f"background-color: {self._background_color};"
            "border: 1px solid #CCCCCC;"
            "border-radius: 4px;"
        )

        # 连接信号
        self.operation_added.connect(self._add_operation)
        self.canvas_cleared.connect(self._clear_canvas)

    # --- 公开 API ---

    def add_operation(self, operation: DrawingOperation) -> None:
        """添加一个操作（直接调用，不走信号）。"""
        self._add_operation(operation)

    def clear(self) -> None:
        """清空画布。"""
        self._operations.clear()
        self.update()  # 触发重绘

    @property
    def operations(self) -> List[DrawingOperation]:
        """只读操作列表。"""
        return list(self._operations)

    @property
    def operation_count(self) -> int:
        """当前操作数量。"""
        return len(self._operations)

    # --- 内部 ---

    def _add_operation(self, operation: DrawingOperation) -> None:
        """添加操作并重绘。"""
        self._operations.append(operation)
        self.update()

    def _clear_canvas(self) -> None:
        """清空画布并重绘。"""
        self._operations.clear()
        self.update()

    # --- QPainter 渲染 ---

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """重写 paintEvent，按顺序渲染所有操作。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for op in self._operations:
            self._draw_operation(painter, op)

        painter.end()

    def _draw_operation(self, painter: QPainter, op: DrawingOperation) -> None:
        """根据操作类型调用对应的绘制方法。"""
        pen_color = QColor(op.color) if op.op_type != OperationType.ERASER else QColor("#FFFFFF")
        pen_width = op.size if op.op_type != OperationType.ERASER else op.size * 3

        painter.setPen(QPen(pen_color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.Round, Qt.PenJoinStyle.Round))
        painter.setBrush(QBrush(pen_color))

        draw_method = self._draw_handlers.get(op.op_type)
        if draw_method is not None:
            draw_method(painter, op)

    def _draw_freehand(self, painter: QPainter, op: FreehandOperation) -> None:
        """绘制自由手绘路径。"""
        if not op.points or len(op.points) < 2:
            return
        # 分段绘制以获得更平滑的线条
        for i in range(len(op.points) - 1):
            painter.drawLine(*op.points[i], *op.points[i + 1])

    def _draw_line(self, painter: QPainter, op: LineDrawOperation) -> None:
        """绘制直线。"""
        painter.drawLine(*op.start, *op.end)

    def _draw_rectangle(self, painter: QPainter, op: RectangleOperation) -> None:
        """绘制矩形（空心）。"""
        x, y = op.top_left
        w, h = op.bottom_right[0] - x, op.bottom_right[1] - y
        painter.drawRect(x, y, w, h)

    def _draw_circle(self, painter: QPainter, op: CircleOperation) -> None:
        """绘制圆形（空心）。"""
        cx, cy = op.center
        painter.drawEllipse(cx - int(op.radius), cy - int(op.radius),
                            int(op.radius * 2), int(op.radius * 2))

    def _draw_triangle(self, painter: QPainter, op: TriangleOperation) -> None:
        """绘制三角形。"""
        polygon = QPolygon([
            op.p1,
            op.p2,
            op.p3,
        ])
        painter.drawPolygon(polygon)

    def _draw_star(self, painter: QPainter, op: StarOperation) -> None:
        """绘制五角星。"""
        cx, cy = op.center
        outer_r = op.outer_radius
        inner_r = op.inner_radius
        points = []

        for i in range(10):
            angle = math.pi / 2 + (i * math.pi) / 5
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)  # Y 轴向下为正
            points.append((int(x), int(y)))

        polygon = QPolygon([QPoint(x, y) for x, y in points])
        painter.drawPolygon(polygon)

    def _draw_ai_image(self, painter: QPainter, op: AIImageOperation) -> None:
        """绘制 AI 生成图片。"""
        if not op.image_bytes:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(op.image_bytes):
            x, y = op.position
            # 缩放以适应画布（最大 400x400）
            max_size = 400
            scaled = pixmap.scaled(max_size, max_size,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(x, y, scaled)

    # 操作类型 → 绘制方法映射表
    _draw_handlers = {
        OperationType.FREEHAND: _draw_freehand,
        OperationType.LINE_DRAW: _draw_line,
        OperationType.RECTANGLE: _draw_rectangle,
        OperationType.CIRCLE: _draw_circle,
        OperationType.TRIANGLE: _draw_triangle,
        OperationType.STAR: _draw_star,
        OperationType.AI_IMAGE: _draw_ai_image,
    }
