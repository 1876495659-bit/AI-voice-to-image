"""应用启动时的语音监听初始化测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import initialize_voice


class _FakeVoiceService:
    def __init__(self, can_initialize: bool = True) -> None:
        self.can_initialize = can_initialize
        self.initialize_called = False
        self.start_called = False

    def initialize(self) -> bool:
        self.initialize_called = True
        return self.can_initialize

    def start_listening(self) -> bool:
        self.start_called = True
        return True


class _FakeVoicePanel:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def show_error(self, message: str) -> None:
        self.errors.append(message)


class _FakeWindow:
    def __init__(self, can_initialize: bool = True) -> None:
        self.voice_service = _FakeVoiceService(can_initialize)
        self.voice_panel = _FakeVoicePanel()


def test_initialize_voice_starts_listening_after_model_load() -> None:
    """Whisper 初始化成功后应立即开启麦克风监听。"""
    window = _FakeWindow(can_initialize=True)

    assert initialize_voice(window) is True
    assert window.voice_service.initialize_called is True
    assert window.voice_service.start_called is True
    assert window.voice_panel.errors == []


def test_initialize_voice_reports_error_when_model_load_fails() -> None:
    """Whisper 初始化失败时应展示错误且不启动监听。"""
    window = _FakeWindow(can_initialize=False)

    assert initialize_voice(window) is False
    assert window.voice_service.initialize_called is True
    assert window.voice_service.start_called is False
    assert window.voice_panel.errors


if __name__ == "__main__":
    test_initialize_voice_starts_listening_after_model_load()
    test_initialize_voice_reports_error_when_model_load_fails()
    print("test_app_voice_startup: OK")
