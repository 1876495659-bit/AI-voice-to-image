"""极简语音绘图界面测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.main_window import MainWindow
from ui.voice_feedback_panel import VoiceFeedbackPanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_main_window_uses_minimal_voice_canvas_layout() -> None:
    """主界面应只暴露语音控制和画布，不再展示工具栏/颜色/历史面板。"""
    app = _app()
    window = MainWindow()

    assert isinstance(window.voice_panel, VoiceFeedbackPanel)
    assert isinstance(window.canvas_scroll, QScrollArea)
    assert not hasattr(window, "toolbar")
    assert not hasattr(window, "history_panel")
    assert not hasattr(window, "color_panel")
    assert window.voice_panel.listen_button.text() in ("开始语音识别", "停止语音识别")
    assert app is not None


def test_voice_button_toggles_listening_state() -> None:
    """点击语音按钮应启动/停止语音监听。"""
    app = _app()
    window = MainWindow()
    calls: list[str] = []
    window.voice_service._base_model = object()
    window.voice_service.start_listening = lambda: calls.append("start") or True
    window.voice_service.stop_listening = lambda: calls.append("stop")

    window.voice_panel.listen_button.click()
    window.voice_panel.listen_button.click()

    assert calls == ["start", "stop"]
    assert app is not None


def test_voice_button_reports_when_model_is_not_ready() -> None:
    """模型未加载时点击语音按钮应给出明确提示。"""
    app = _app()
    window = MainWindow()
    window.voice_service._base_model = None

    window.voice_panel.listen_button.click()

    assert "语音识别模型未就绪" in window.voice_panel.action_label.text()
    assert app is not None


if __name__ == "__main__":
    test_main_window_uses_minimal_voice_canvas_layout()
    test_voice_button_toggles_listening_state()
    test_voice_button_reports_when_model_is_not_ready()
    print("test_minimal_voice_ui: OK")
