"""AI 线稿转笔画测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.stroke_extractor import StrokeExtractor
from engine.drawing_engine import DrawingEngine
from engine.operations import AIImageOperation, StrokeGroupOperation


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _line_art_png() -> bytes:
    image = QImage(80, 60, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    painter.setPen(QPen(QColor("#000000"), 4))
    painter.drawLine(10, 20, 70, 20)
    painter.drawLine(20, 40, 60, 48)
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _large_line_art_png() -> bytes:
    image = QImage(1000, 900, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    painter.setPen(QPen(QColor("#000000"), 8))
    painter.drawRect(100, 80, 760, 700)
    painter.drawLine(120, 760, 850, 120)
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def test_extractor_converts_line_art_image_to_stroke_group() -> None:
    """线稿图片应被提取成笔画组，而不是作为方形图片贴到画布上。"""
    app = _app()

    op = StrokeExtractor().extract(
        _line_art_png(),
        position=(100, 200),
        label="杯子",
        color="#000000",
        size=3,
    )

    assert isinstance(op, StrokeGroupOperation)
    assert op.semantic_label == "杯子"
    assert op.strokes
    assert all(len(stroke) >= 2 for stroke in op.strokes)
    assert min(x for stroke in op.strokes for x, _ in stroke) >= 100
    assert min(y for stroke in op.strokes for _, y in stroke) >= 200
    assert app is not None


def test_extractor_fits_large_line_art_inside_ai_element_box() -> None:
    """大尺寸模型线稿应缩放进 400x400 元素框，避免整幅画比例失控。"""
    app = _app()

    op = StrokeExtractor().extract(
        _large_line_art_png(),
        position=(50, 70),
        label="大树",
        color="#000000",
        size=3,
    )

    points = [point for stroke in op.strokes for point in stroke]
    assert points
    assert min(x for x, _ in points) >= 50
    assert min(y for _, y in points) >= 70
    assert max(x for x, _ in points) <= 450
    assert max(y for _, y in points) <= 470
    assert app is not None


def test_engine_replaces_ai_image_with_stroke_group_after_generation() -> None:
    """Agnes 生成成功后，历史中应落为笔画组而不是 AI 图片。"""
    app = _app()
    engine = DrawingEngine(canvas_width=400, canvas_height=300)
    engine.ai_service.generate_image = lambda prompt: _line_art_png()

    ai_op = AIImageOperation(prompt="杯子", position=(20, 30))
    ai_op.semantic_label = "杯子"
    engine.history.push(ai_op)
    engine._generate_ai_image(ai_op)

    history = engine.get_history()
    assert len(history) == 1
    assert isinstance(history[0], StrokeGroupOperation)
    assert history[0].semantic_label == "杯子"
    assert engine.selected_operation_id == history[0].id
    assert app is not None


if __name__ == "__main__":
    test_extractor_converts_line_art_image_to_stroke_group()
    test_extractor_fits_large_line_art_inside_ai_element_box()
    test_engine_replaces_ai_image_with_stroke_group_after_generation()
    print("test_stroke_extraction: OK")
