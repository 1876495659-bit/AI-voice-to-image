"""画布渲染组件 — 美化版。

自定义 QWidget，重写 paintEvent() 用 QPainter 渲染所有绘图操作。
新增：网格背景、坐标参考线、操作数量统计。
"""

from __future__ import annotations

import math
from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
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
    """美化版画布组件。

    新增特性:
    - 浅灰网格背景（10px 间隔）
    - 十字参考线（中心线）
    - 操作数量统计
    - 缩放支持
    """

    operation_added = pyqtSignal(DrawingOperation)
    canvas_cleared = pyqtSignal()

    def __init__(self, width: int = config.CANVAS_DEFAULT_WIDTH,
                 height: int = config.CANVAS_DEFAULT_HEIGHT,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._operations: List[DrawingOperation] = []
        self._base_width = width
        self._base_height = height
        self._zoom: int = 100

        self.setFixedSize(width, height)
        self.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                border: 2px solid #E0E0E0;
                border-radius: 8px;
            }
        """)

        self.operation_added.connect(self._add_operation)
        self.canvas_cleared.connect(self._clear_canvas)

    # ── 公开 API ──────────────────────────────────────────

    def add_operation(self, operation: DrawingOperation) -> None:
        self._add_operation(operation)

    def clear(self) -> None:
        self._operations.clear()
        self.update()

    @property
    def operations(self) -> List[DrawingOperation]:
        return list(self._operations)

    @property
    def operation_count(self) -> int:
        return len(self._operations)

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(10, min(300, zoom))
        self.setFixedSize(
            int(self._base_width * self._zoom / 100),
            int(self._base_height * self._zoom / 100),
        )
        self.update()

    # ── 内部 ──────────────────────────────────────────────

    def _add_operation(self, operation: DrawingOperation) -> None:
        self._operations.append(operation)
        self.update()

    def _clear_canvas(self) -> None:
        self._operations.clear()
        self.update()

    # ── QPainter 渲染 ─────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self._zoom / 100, self._zoom / 100)

        # 1. 绘制网格背景
        self._draw_grid(painter)

        # 2. 绘制十字参考线
        self._draw_guides(painter)

        # 3. 绘制所有操作
        for op in self._operations:
            self._draw_operation(painter, op)

        # 4. 操作数量统计
        self._draw_stats(painter)

        painter.end()

    def _draw_grid(self, painter: QPainter) -> None:
        """绘制浅灰网格背景。"""
        grid_color = QColor("#F0F0F0")
        pen = QPen(grid_color, 0.5)
        painter.setPen(pen)
        painter.setBrush(Qt.GlobalColor.white)

        spacing = 20
        w = self.width()
        h = self.height()
        if self._zoom != 0:
            w = self._base_width
            h = self._base_height

        x = spacing
        while x < w:
            painter.drawLine(x, 0, x, h)
            x += spacing

        y = spacing
        while y < h:
            painter.drawLine(0, y, w, y)
            y += spacing

    def _draw_guides(self, painter: QPainter) -> None:
        """绘制中心十字参考线。"""
        guide_color = QColor("#E8E8E8")
        pen = QPen(guide_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        cx, cy = self._base_width // 2, self._base_height // 2
        painter.drawLine(cx, 0, cx, self._base_height)
        painter.drawLine(0, cy, self._base_width, cy)

    def _draw_stats(self, painter: QPainter) -> None:
        """左下角绘制操作数量统计。"""
        painter.setPen(QColor("#CCCCCC"))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(10, self._base_height - 10,
                         f"操作: {len(self._operations)} 个")

    def _draw_operation(self, painter: QPainter, op: DrawingOperation) -> None:
        """根据操作类型调用对应的绘制方法。"""
        pen_color = QColor(op.color) if op.op_type != OperationType.ERASER else QColor("#FFFFFF")
        pen_width = op.size if op.op_type != OperationType.ERASER else op.size * 3

        painter.setPen(QPen(pen_color, pen_width,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        if op.filled and op.op_type not in (OperationType.FREEHAND, OperationType.LINE_DRAW):
            painter.setBrush(QBrush(pen_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        draw_method = self._draw_handlers.get(op.op_type)
        if draw_method is not None:
            draw_method(self, painter, op)

    def _draw_freehand(self, painter: QPainter, op: FreehandOperation) -> None:
        if not op.points or len(op.points) < 2:
            return
        for i in range(len(op.points) - 1):
            painter.drawLine(*op.points[i], *op.points[i + 1])

    def _draw_line(self, painter: QPainter, op: LineDrawOperation) -> None:
        painter.drawLine(*op.start, *op.end)

    def _draw_rectangle(self, painter: QPainter, op: RectangleOperation) -> None:
        x, y = op.top_left
        w, h = op.bottom_right[0] - x, op.bottom_right[1] - y
        painter.drawRect(x, y, w, h)

    def _draw_circle(self, painter: QPainter, op: CircleOperation) -> None:
        cx, cy = op.center
        painter.drawEllipse(cx - int(op.radius), cy - int(op.radius),
                            int(op.radius * 2), int(op.radius * 2))

    def _draw_triangle(self, painter: QPainter, op: TriangleOperation) -> None:
        polygon = QPolygon([QPoint(*op.p1), QPoint(*op.p2), QPoint(*op.p3)])
        painter.drawPolygon(polygon)

    def _draw_star(self, painter: QPainter, op: StarOperation) -> None:
        cx, cy = op.center
        outer_r = op.outer_radius
        inner_r = op.inner_radius
        points = []
        for i in range(10):
            angle = math.pi / 2 + (i * math.pi) / 5
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)
            points.append((int(x), int(y)))
        polygon = QPolygon([QPoint(px, py) for px, py in points])
        painter.drawPolygon(polygon)

    def _draw_ai_image(self, painter: QPainter, op: AIImageOperation) -> None:
        if not op.image_bytes:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(op.image_bytes):
            x, y = op.position
            max_size = 400
            scaled = pixmap.scaled(max_size, max_size,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(x, y, scaled)

    _draw_handlers = {
        OperationType.FREEHAND: _draw_freehand,
        OperationType.LINE_DRAW: _draw_line,
        OperationType.RECTANGLE: _draw_rectangle,
        OperationType.CIRCLE: _draw_circle,
        OperationType.TRIANGLE: _draw_triangle,
        OperationType.STAR: _draw_star,
        OperationType.AI_IMAGE: _draw_ai_image,
    }
