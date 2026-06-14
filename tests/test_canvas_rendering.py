"""画布渲染回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.operations import CircleOperation, StarOperation, TriangleOperation
from ui.canvas_widget import CanvasWidget


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_canvas_draws_basic_shapes_without_qt_enum_errors() -> None:
    """基础形状渲染不应触发 PyQt6 枚举或点类型错误。"""
    app = _app()
    canvas = CanvasWidget(width=320, height=240)
    pixmap = QPixmap(canvas.size())
    painter = QPainter(pixmap)

    canvas._draw_operation(
        painter,
        CircleOperation(center=(160, 120), radius=40, color="#FF0000", size=3),
    )
    canvas._draw_operation(
        painter,
        TriangleOperation(
            p1=(160, 60),
            p2=(110, 160),
            p3=(210, 160),
            color="#00AA00",
            size=3,
        ),
    )
    canvas._draw_operation(
        painter,
        StarOperation(center=(160, 120), color="#0000FF", size=3),
    )

    painter.end()
    assert app is not None


def test_canvas_zoom_changes_rendered_widget_size() -> None:
    """画布缩放应改变实际显示尺寸。"""
    app = _app()
    canvas = CanvasWidget(width=1000, height=500)

    canvas.set_zoom(50)

    assert canvas.width() == 500
    assert canvas.height() == 250
    assert app is not None


if __name__ == "__main__":
    test_canvas_draws_basic_shapes_without_qt_enum_errors()
    test_canvas_zoom_changes_rendered_widget_size()
    print("test_canvas_rendering: OK")
