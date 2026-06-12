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


if __name__ == "__main__":
    test_transcription_signal_drives_canvas_and_history()
    print("test_voice_integration: OK")
