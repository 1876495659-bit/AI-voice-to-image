"""智能语音编辑操作测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.drawing_engine import DrawingEngine
from engine.operations import (
    CircleOperation,
    MoveSelectedOperation,
    OperationType,
    RecolorSelectedOperation,
    ScaleSelectedOperation,
)
from parser.command_parser import CommandParser
from ui.canvas_widget import CanvasWidget


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_parser_understands_move_selected_commands() -> None:
    """理解“把它往右移一点”和带数字移动。"""
    parser = CommandParser(canvas_width=1920, canvas_height=1080)

    result = parser.parse("把它往右移一点", 0.95)
    assert result.is_success
    op = result.operations[0]
    assert isinstance(op, MoveSelectedOperation)
    assert op.op_type == OperationType.MOVE_SELECTED
    assert op.dx == 40
    assert op.dy == 0

    result2 = parser.parse("向左移动80像素", 0.95)
    op2 = result2.operations[0]
    assert isinstance(op2, MoveSelectedOperation)
    assert op2.dx == -80
    assert op2.dy == 0


def test_parser_understands_scale_and_recolor_commands() -> None:
    """理解缩放和改色语音编辑。"""
    parser = CommandParser(canvas_width=1920, canvas_height=1080)

    grow = parser.parse("变大一点", 0.95).operations[0]
    assert isinstance(grow, ScaleSelectedOperation)
    assert grow.factor == 1.15

    shrink = parser.parse("缩小一点", 0.95).operations[0]
    assert isinstance(shrink, ScaleSelectedOperation)
    assert shrink.factor == 0.85

    recolor = parser.parse("把它改成红色", 0.95).operations[0]
    assert isinstance(recolor, RecolorSelectedOperation)
    assert recolor.color == "#FF0000"


def test_engine_auto_selects_and_moves_recent_shape() -> None:
    """新建图形后自动选中，移动命令会改变其位置。"""
    engine = DrawingEngine(canvas_width=1920, canvas_height=1080)
    circle = CircleOperation(center=(100, 100), radius=30)

    engine.execute(circle)
    assert engine.selected_operation_id == circle.id

    engine.execute(MoveSelectedOperation(dx=40, dy=0))

    assert circle.center == (140, 100)
    assert engine.selected_operation_id == circle.id


def test_engine_scales_and_recolors_selected_shape() -> None:
    """缩放和改色会作用于当前选中图形。"""
    engine = DrawingEngine(canvas_width=1920, canvas_height=1080)
    circle = CircleOperation(center=(100, 100), radius=60, color="#000000")
    engine.execute(circle)

    engine.execute(ScaleSelectedOperation(factor=1.15))
    assert round(circle.radius, 2) == 69.0

    engine.execute(RecolorSelectedOperation(color="#FF0000"))
    assert circle.color == "#FF0000"


def test_engine_undo_redo_reverts_selected_edit() -> None:
    """编辑操作应支持撤销和重做。"""
    engine = DrawingEngine(canvas_width=1920, canvas_height=1080)
    circle = CircleOperation(center=(100, 100), radius=30)
    engine.execute(circle)
    engine.execute(MoveSelectedOperation(dx=40, dy=0))

    engine.undo()
    assert circle.center == (100, 100)
    assert engine.selected_operation_id == circle.id

    engine.redo()
    assert circle.center == (140, 100)
    assert engine.selected_operation_id == circle.id


def test_engine_edit_without_target_reports_failure() -> None:
    """没有图形时编辑命令不崩溃，并给出错误反馈。"""
    engine = DrawingEngine(canvas_width=1920, canvas_height=1080)
    messages: list[str] = []
    engine.signals.edit_failed.connect(messages.append)

    engine.execute(MoveSelectedOperation(dx=40, dy=0))

    assert messages == ["没有可编辑的图形，请先画一个图形"]
    assert engine.selected_operation_id is None


def test_canvas_tracks_selected_operation_id() -> None:
    """画布应保存选中 ID，清空后选中状态消失。"""
    app = _app()
    canvas = CanvasWidget(width=320, height=240)
    circle = CircleOperation(center=(100, 100), radius=30)

    canvas.add_operation(circle)
    canvas.set_selected_operation(circle.id)
    assert canvas.selected_operation_id == circle.id

    canvas.clear()
    assert canvas.selected_operation_id is None
    assert app is not None


if __name__ == "__main__":
    test_parser_understands_move_selected_commands()
    test_parser_understands_scale_and_recolor_commands()
    test_engine_auto_selects_and_moves_recent_shape()
    test_engine_scales_and_recolors_selected_shape()
    test_engine_undo_redo_reverts_selected_edit()
    test_engine_edit_without_target_reports_failure()
    test_canvas_tracks_selected_operation_id()
    print("test_voice_editing_operations: OK")
