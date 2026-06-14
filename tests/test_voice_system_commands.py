"""语音系统指令回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.drawing_engine import DrawingEngine
from engine.operations import CircleOperation, DrawingOperation, OperationType


def test_voice_undo_operation_undoes_last_drawing_operation() -> None:
    """语音解析得到的 UNDO 操作应触发真正撤销，而不是压入历史。"""
    engine = DrawingEngine()
    engine.execute(CircleOperation())

    engine.execute(DrawingOperation(op_type=OperationType.UNDO))

    assert engine.history.undo_count == 0
    assert engine.history.redo_count == 1


def test_voice_redo_operation_redoes_last_undone_operation() -> None:
    """语音解析得到的 REDO 操作应触发真正重做。"""
    engine = DrawingEngine()
    engine.execute(CircleOperation())
    engine.undo()

    engine.execute(DrawingOperation(op_type=OperationType.REDO))

    assert engine.history.undo_count == 1
    assert engine.history.redo_count == 0


if __name__ == "__main__":
    test_voice_undo_operation_undoes_last_drawing_operation()
    test_voice_redo_operation_redoes_last_undone_operation()
    print("test_voice_system_commands: OK")
