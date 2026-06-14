"""语音链路回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_transcription_signal_drives_canvas() -> None:
    """语音识别结果应进入解析器、绘图引擎和画布。"""
    app = _app()
    window = MainWindow()

    command = "\u753b\u4e2a\u5706"
    window.voice_service.signals.transcription_ready.emit(command, 0.95)

    assert window.canvas.operation_count == 1
    assert window.voice_panel.text_label.text() == command
    assert "CIRCLE" in window.voice_panel.action_label.text()
    assert app is not None


def test_low_confidence_shape_command_still_draws_when_parse_is_clear() -> None:
    """置信度偏低但已解析出明确绘图操作时，应执行该操作。"""
    app = _app()
    window = MainWindow()
    command = "\u753b\u4e00\u4e2a\u5706\u5708"

    window.voice_service.signals.transcription_ready.emit(command, 0.49)

    assert window.canvas.operation_count == 1
    assert window.voice_panel.text_label.text() == command
    assert "CIRCLE" in window.voice_panel.action_label.text()
    assert app is not None


def test_complex_transcription_executes_without_manual_button() -> None:
    """复杂识别文本应自动解析执行。"""
    app = _app()
    window = MainWindow()
    command = "\u7528\u7ea2\u7b14\u753b\u4e00\u4e2a\u5706\u5708"

    window.voice_service.signals.transcription_ready.emit(command, 0.46)

    assert window.canvas.operation_count == 1
    assert "COLOR" in window.voice_panel.action_label.text()
    assert "PEN" in window.voice_panel.action_label.text()
    assert "CIRCLE" in window.voice_panel.action_label.text()
    assert app is not None


def test_voice_edit_command_moves_recent_shape_and_updates_selection_feedback() -> None:
    """语音编辑应作用于最近图形并显示中文反馈。"""
    app = _app()
    window = MainWindow()

    window.voice_service.signals.transcription_ready.emit("画一个圆", 0.95)
    circle = window.engine.get_history()[0]
    original_center = circle.center

    window.voice_service.signals.transcription_ready.emit("把它往右移一点", 0.95)

    assert circle.center == (original_center[0] + 40, original_center[1])
    assert window.canvas.selected_operation_id == circle.id
    assert "已将最近图形向右移动 40px" in window.voice_panel.action_label.text()
    assert app is not None


def test_voice_edit_command_without_shape_keeps_error_feedback() -> None:
    """没有图形时语音编辑应保留错误提示，不显示成功文案。"""
    app = _app()
    window = MainWindow()

    window.voice_service.signals.transcription_ready.emit("把它往右移一点", 0.95)

    assert window.canvas.operation_count == 0
    assert "没有可编辑的图形" in window.voice_panel.action_label.text()
    assert app is not None


def test_voice_delete_command_removes_recent_shape() -> None:
    """语音删除应移除最近选中的图形。"""
    app = _app()
    window = MainWindow()

    window.voice_service.signals.transcription_ready.emit("画一个正方形", 0.95)
    assert window.canvas.operation_count == 1

    window.voice_service.signals.transcription_ready.emit("删除这个正方形", 0.34)

    assert window.canvas.operation_count == 0
    assert window.canvas.selected_operation_id is None
    assert "已删除最近图形" in window.voice_panel.action_label.text()
    assert app is not None


def test_voice_agent_labels_fills_and_details_sun() -> None:
    """语音绘画代理应支持逐步完善太阳。"""
    app = _app()
    window = MainWindow()

    window.voice_service.signals.transcription_ready.emit("画一个圆", 0.95)
    circle = window.engine.get_history()[0]

    window.voice_service.signals.transcription_ready.emit("我刚刚画的是一个太阳", 0.95)
    assert circle.semantic_label == "太阳"

    window.voice_service.signals.transcription_ready.emit("用黄色涂满这个圆", 0.95)
    assert circle.color == "#FFFF00"
    assert circle.filled is True

    before_count = window.canvas.operation_count
    window.voice_service.signals.transcription_ready.emit("帮我补充一点它的细节", 0.95)
    assert window.canvas.operation_count > before_count
    assert "细节" in window.voice_panel.action_label.text()
    assert app is not None


if __name__ == "__main__":
    test_transcription_signal_drives_canvas()
    test_low_confidence_shape_command_still_draws_when_parse_is_clear()
    test_complex_transcription_executes_without_manual_button()
    test_voice_edit_command_moves_recent_shape_and_updates_selection_feedback()
    test_voice_edit_command_without_shape_keeps_error_feedback()
    test_voice_delete_command_removes_recent_shape()
    test_voice_agent_labels_fills_and_details_sun()
    print("test_voice_integration: OK")
