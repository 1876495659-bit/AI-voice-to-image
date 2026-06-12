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


def test_transcription_signal_drives_canvas_and_history() -> None:
    """语音识别结果应进入解析器、绘图引擎和命令历史。"""
    app = _app()
    window = MainWindow()

    command = "\u753b\u4e2a\u5706"
    window.voice_service.signals.transcription_ready.emit(command, 0.95)

    assert window.canvas.operation_count == 1
    assert window.history_panel.entry_count == 1
    assert window.voice_panel.text_label.text() == command
    assert app is not None


def test_low_confidence_shape_command_still_draws_when_parse_is_clear() -> None:
    """置信度偏低但已解析出明确绘图操作时，应执行该操作。"""
    app = _app()
    window = MainWindow()
    command = "\u753b\u4e00\u4e2a\u5706\u5708"

    window.voice_service.signals.transcription_ready.emit(command, 0.49)

    assert window.canvas.operation_count == 1
    assert window.history_panel.entry_count == 1
    assert window.voice_panel.text_label.text() == command
    assert app is not None


def test_execute_button_runs_current_transcription_text() -> None:
    """点击执行按钮应按当前显示的识别文本执行命令。"""
    app = _app()
    window = MainWindow()
    command = "\u7528\u7ea2\u7b14\u753b\u4e00\u4e2a\u5706\u5708"

    window.voice_service.signals.transcription_ready.emit(command, 0.46)
    assert window.canvas.operation_count == 1
    assert window.voice_panel.execute_button.isEnabled()

    window.voice_panel.execute_button.click()

    assert window.canvas.operation_count == 2
    assert window.history_panel.entry_count == 2
    assert "\u624b\u52a8\u6267\u884c" in window.voice_panel.action_label.text()
    assert app is not None


if __name__ == "__main__":
    test_transcription_signal_drives_canvas_and_history()
    test_low_confidence_shape_command_still_draws_when_parse_is_clear()
    test_execute_button_runs_current_transcription_text()
    print("test_voice_integration: OK")
