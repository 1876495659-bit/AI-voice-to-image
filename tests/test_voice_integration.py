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


if __name__ == "__main__":
    test_transcription_signal_drives_canvas()
    test_low_confidence_shape_command_still_draws_when_parse_is_clear()
    test_complex_transcription_executes_without_manual_button()
    print("test_voice_integration: OK")
