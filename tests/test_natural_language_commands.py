"""自然语言绘图需求理解测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.operations import CircleOperation, OperationType, RectangleOperation
from parser.command_parser import CommandParser


def test_understands_hollow_circle_in_top_left() -> None:
    """理解“在左上角画一个空心的圆圈”。"""
    parser = CommandParser(canvas_width=1920, canvas_height=1080)

    result = parser.parse("\u5728\u5de6\u4e0a\u89d2\u753b\u4e00\u4e2a\u7a7a\u5fc3\u7684\u5706\u5708", 0.95)

    assert result.is_success
    assert len(result.operations) == 1
    op = result.operations[0]
    assert isinstance(op, CircleOperation)
    assert op.op_type == OperationType.CIRCLE
    assert op.filled is False
    assert op.center[0] >= op.radius
    assert op.center[1] >= op.radius


def test_understands_blue_rectangle_in_bottom_right() -> None:
    """理解“右下角画一个蓝色矩形”。"""
    parser = CommandParser(canvas_width=1920, canvas_height=1080)

    result = parser.parse("\u53f3\u4e0b\u89d2\u753b\u4e00\u4e2a\u84dd\u8272\u77e9\u5f62", 0.95)

    assert result.is_success
    assert len(result.operations) == 1
    op = result.operations[0]
    assert isinstance(op, RectangleOperation)
    assert op.color == "#0000FF"
    assert op.bottom_right[0] <= 1920
    assert op.bottom_right[1] <= 1080


def test_understands_large_circle_size_words() -> None:
    """理解“在中间画一个大圆”。"""
    parser = CommandParser(canvas_width=1920, canvas_height=1080)

    result = parser.parse("\u5728\u4e2d\u95f4\u753b\u4e00\u4e2a\u5927\u5706", 0.95)

    assert result.is_success
    op = result.operations[0]
    assert isinstance(op, CircleOperation)
    assert op.radius > 60


if __name__ == "__main__":
    test_understands_hollow_circle_in_top_left()
    test_understands_blue_rectangle_in_bottom_right()
    test_understands_large_circle_size_words()
    print("test_natural_language_commands: OK")
