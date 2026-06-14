"""语音识别异步执行回归测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.voice_service import VoiceService


class _SlowWhisperModel:
    def transcribe(self, audio, **kwargs):
        time.sleep(0.3)
        return {
            "text": "\u753b\u4e2a\u5706",
            "segments": [{"avg_logprob": 2.0}],
        }


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_audio_ready_does_not_block_ui_thread() -> None:
    """收到音频后应异步识别，不能阻塞 UI 主线程。"""
    app = _app()
    service = VoiceService()
    service._base_model = _SlowWhisperModel()
    audio = np.ones(16000, dtype=np.float32) * 0.02
    transcriptions: list[tuple[str, float]] = []
    service.signals.transcription_ready.connect(
        lambda text, confidence: transcriptions.append((text, confidence))
    )

    start = time.perf_counter()
    service._on_audio_ready(audio)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"语音回调阻塞了 {elapsed:.3f}s"

    deadline = time.perf_counter() + 2.0
    while not transcriptions and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert transcriptions
    assert transcriptions[0][0] == "\u753b\u4e2a\u5706"
    assert app is not None


if __name__ == "__main__":
    test_audio_ready_does_not_block_ui_thread()
    print("test_voice_async_transcription: OK")
