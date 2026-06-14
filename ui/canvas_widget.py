"""画布渲染组件 — 美化版。

自定义 QWidget，重写 paintEvent() 用 QPainter 渲染所有绘图操作。
新增：网格背景、坐标参考线、操作数量统计、AI 图片白边裁剪。
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
    StrokeGroupOperation,
    TriangleOperation,
)


class CanvasWidget(QWidget):
    """美化版画布组件。

    新增特性:
    - 浅灰网格背景（10px 间隔）
    - 十字参考线（中心线）
    - 操作数量统计
    - 缩放支持
    - AI 图片白边裁剪（不规则轮廓）
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
        self._selected_operation_id: Optional[str] = None
        self._background_color: str = "#FFFFFF"

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
        self._selected_operation_id = None
        self.update()

    @property
    def operations(self) -> List[DrawingOperation]:
        return list(self._operations)

    @property
    def operation_count(self) -> int:
        return len(self._operations)

    @property
    def selected_operation_id(self) -> Optional[str]:
        return self._selected_operation_id

    def set_selected_operation(self, operation_id: Optional[str]) -> None:
        self._selected_operation_id = operation_id
        self.update()

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
        self._selected_operation_id = None
        self.update()

    # ── QPainter 渲染 ─────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self._zoom / 100, self._zoom / 100)

        # 0. 绘制背景色
        self._draw_background(painter)

        # 1. 绘制网格背景
        self._draw_grid(painter)

        # 2. 绘制十字参考线
        self._draw_guides(painter)

        # 3. 绘制所有操作
        for op in self._operations:
            self._draw_operation(painter, op)

        # 4. 绘制选中框
        self._draw_selection(painter)

        # 5. 操作数量统计
        self._draw_stats(painter)

        painter.end()

    def _draw_background(self, painter: QPainter) -> None:
        """填充画布背景色。"""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._background_color))
        painter.drawRect(0, 0, self._base_width, self._base_height)

    def set_background_color(self, color: str) -> None:
        """设置背景色并重绘画布。"""
        self._background_color = color
        self.update()

    def render_snapshot(
        self,
        operations: Optional[List[DrawingOperation]] = None,
        max_width: int = 180,
        max_height: int = 120,
    ) -> QPixmap:
        """离屏渲染当前整幅画，用于右侧步骤快照。"""
        pixmap = QPixmap(self._base_width, self._base_height)
        pixmap.fill(QColor(self._background_color))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_background(painter)
        for op in operations if operations is not None else self._operations:
            self._draw_operation(painter, op)
        painter.end()

        return pixmap.scaled(
            max_width,
            max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _draw_grid(self, painter: QPainter) -> None:
        """绘制浅灰网格背景。"""
        grid_color = QColor("#F0F0F0")
        pen = QPen(grid_color, 0.5)
        painter.setPen(pen)

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

    def _draw_stroke_group(self, painter: QPainter, op: StrokeGroupOperation) -> None:
        for stroke in op.strokes:
            if len(stroke) < 2:
                continue
            for i in range(len(stroke) - 1):
                painter.drawLine(*stroke[i], *stroke[i + 1])

    def _draw_line(self, painter: QPainter, op: LineDrawOperation) -> None:
        painter.drawLine(*op.start, *op.end)

    def _draw_rectangle(self, painter: QPainter, op: RectangleOperation) -> None:
        x, y = op.top_left
        w, h = op.bottom_right[0] - x, op.bottom_right[1] - y
        painter.drawRect(x, y, w, h)

    def _draw_circle(self, painter: QPainter, op: CircleOperation) -> None:
        cx, cy = op.center
        r = int(op.radius)
        painter.drawEllipse(int(cx) - r, int(cy) - r, r * 2, r * 2)

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
            # 裁剪白边
            cropped = self._crop_white_edges(pixmap)
            cropped = self._tint_line_art(cropped, op.color)
            x, y = op.position
            max_size = 400
            scaled = cropped.scaled(max_size, max_size,
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            # 居中放置：让裁剪后的图片中心对准目标位置
            offset_x = x - (scaled.width() - max_size) // 2
            offset_y = y - (scaled.height() - max_size) // 2
            painter.drawPixmap(offset_x, offset_y, scaled)

    def _crop_white_edges(self, pixmap: QPixmap) -> QPixmap:
        """裁剪图片四周的纯色背景边缘，保留内容轮廓。

        采用四向扫描法：从上下左右四个方向逐像素扫描，找到第一行/列中包含
        非背景色（非白色/近白色）像素的位置，以此为边界裁剪。
        结果贴到透明背景上，实现不规则形状。
        """
        img = pixmap.toImage()
        if img.isNull():
            return pixmap

        w, h = img.width(), img.height()

        # 1. 从四个角取背景色（取亮度最高且四角一致的作为背景）
        corners = [
            img.pixelColor(0, 0),
            img.pixelColor(w - 1, 0),
            img.pixelColor(0, h - 1),
            img.pixelColor(w - 1, h - 1),
        ]
        bg_color = sorted(corners, key=lambda c: c.lightness())[len(corners) // 2]
        # 背景亮度阈值（接近白色的视为背景）
        bg_threshold = 0.92

        # 2. 从上往下扫描
        top = 0
        while top < h:
            for x in range(0, w, 2):  # 每2像素采样一次加速
                c = img.pixelColor(x, top)
                if c.lightnessF() < bg_threshold:
                    break
            else:
                top += 2
                continue
            break

        # 3. 从下往上扫描
        bottom = h - 1
        while bottom >= 0:
            for x in range(0, w, 2):
                c = img.pixelColor(x, bottom)
                if c.lightnessF() < bg_threshold:
                    break
            else:
                bottom -= 2
                continue
            break

        # 4. 从左往右扫描
        left = 0
        while left < w:
            for y in range(0, h, 2):
                c = img.pixelColor(left, y)
                if c.lightnessF() < bg_threshold:
                    break
            else:
                left += 2
                continue
            break

        # 5. 从右往左扫描
        right = w - 1
        while right >= 0:
            for y in range(0, h, 2):
                c = img.pixelColor(right, y)
                if c.lightnessF() < bg_threshold:
                    break
            else:
                right -= 2
                continue
            break

        # 回退：如果没找到任何内容，返回原图
        if top > bottom or left > right:
            return pixmap

        # 加一点内边距（让轮廓更自然）
        margin = 3
        top = max(0, top - margin)
        bottom = min(h - 1, bottom + margin)
        left = max(0, left - margin)
        right = min(w - 1, right + margin)

        # 裁剪
        cropped = pixmap.copy(left, top, right - left + 1, bottom - top + 1)

        # 贴到透明背景
        result = QPixmap(cropped.size())
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, cropped)
        painter.end()

        return result

    def _tint_line_art(self, pixmap: QPixmap, color: str) -> QPixmap:
        """将 AI 单色线稿的深色笔触重着色，支持语音涂色。"""
        target = QColor(color)
        if not target.isValid() or target.name().upper() == "#000000":
            return pixmap

        img = pixmap.toImage()
        if img.isNull():
            return pixmap

        for y in range(img.height()):
            for x in range(img.width()):
                pixel = img.pixelColor(x, y)
                if pixel.alpha() == 0:
                    continue
                if pixel.lightnessF() < 0.72:
                    target_pixel = QColor(target)
                    target_pixel.setAlpha(pixel.alpha())
                    img.setPixelColor(x, y, target_pixel)

        return QPixmap.fromImage(img)

    def _draw_selection(self, painter: QPainter) -> None:
        if not self._selected_operation_id:
            return
        target = next((op for op in self._operations if op.id == self._selected_operation_id), None)
        if target is None:
            return
        # AI 图片不显示虚线选择框，只显示自然轮廓
        if isinstance(target, AIImageOperation):
            return
        bounds = self._selection_bounds(target)
        if bounds is None:
            return

        x, y, w, h = bounds
        pad = 8
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#6C63FF"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(x - pad, y - pad, w + pad * 2, h + pad * 2)
        painter.restore()

    def _selection_bounds(self, op: DrawingOperation) -> Optional[tuple]:
        if isinstance(op, CircleOperation):
            r = int(op.radius)
            return op.center[0] - r, op.center[1] - r, r * 2, r * 2
        if isinstance(op, RectangleOperation):
            x, y = op.top_left
            return x, y, op.bottom_right[0] - x, op.bottom_right[1] - y
        if isinstance(op, TriangleOperation):
            xs = [op.p1[0], op.p2[0], op.p3[0]]
            ys = [op.p1[1], op.p2[1], op.p3[1]]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        if isinstance(op, StarOperation):
            r = int(op.outer_radius)
            return op.center[0] - r, op.center[1] - r, r * 2, r * 2
        if isinstance(op, LineDrawOperation):
            x1, y1 = op.start
            x2, y2 = op.end
            return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(x2 - x1)
        if isinstance(op, FreehandOperation) and op.points:
            xs = [p[0] for p in op.points]
            ys = [p[1] for p in op.points]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        if isinstance(op, StrokeGroupOperation) and op.strokes:
            points = [point for stroke in op.strokes for point in stroke]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        if isinstance(op, AIImageOperation):
            # AI 图片不返回固定边界（虚线框已由 _draw_selection 跳过）
            return None
        return None

    _draw_handlers = {
        OperationType.FREEHAND: _draw_freehand,
        OperationType.STROKE_GROUP: _draw_stroke_group,
        OperationType.LINE_DRAW: _draw_line,
        OperationType.RECTANGLE: _draw_rectangle,
        OperationType.CIRCLE: _draw_circle,
        OperationType.TRIANGLE: _draw_triangle,
        OperationType.STAR: _draw_star,
        OperationType.AI_IMAGE: _draw_ai_image,
    }
