"""语音识别逐字展示测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.voice_feedback_panel import VoiceFeedbackPanel
from voice.voice_service import VoiceService


class _FakeWhisperModel:
    def transcribe(self, audio, **kwargs):
        return {
            "text": "\u753b\u4e2a\u5706",
            "segments": [{"avg_logprob": 2.0}],
        }


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_voice_service_emits_partial_text_prefixes_before_final_result() -> None:
    """识别结果应逐字输出，再发最终文本。"""
    app = _app()
    service = VoiceService()
    service._base_model = _FakeWhisperModel()
    service._stream_char_interval = 0.0
    partials: list[str] = []
    finals: list[str] = []
    service.signals.partial_transcription.connect(partials.append)
    service.signals.transcription_ready.connect(lambda text, confidence: finals.append(text))

    service._on_audio_ready(np.ones(16000, dtype=np.float32) * 0.02)

    deadline = time.perf_counter() + 2.0
    while not finals and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert partials == ["\u753b", "\u753b\u4e2a", "\u753b\u4e2a\u5706"]
    assert finals == ["\u753b\u4e2a\u5706"]
    assert app is not None


def test_voice_feedback_panel_displays_partial_text() -> None:
    """语音面板应展示逐字更新的识别文本。"""
    app = _app()
    panel = VoiceFeedbackPanel()

    panel.show_partial_transcription("\u753b")
    assert panel.text_label.text() == "\u753b"
    panel.show_partial_transcription("\u753b\u4e2a")
    assert panel.text_label.text() == "\u753b\u4e2a"

    assert app is not None


if __name__ == "__main__":
    test_voice_service_emits_partial_text_prefixes_before_final_result()
    test_voice_feedback_panel_displays_partial_text()
    print("test_voice_streaming_display: OK")
