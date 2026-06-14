"""语音识别及时性与连续指令测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.audio_buffer import AudioBuffer
from voice.voice_service import VoiceService


class _SlowWhisperModel:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio, **kwargs):
        self.calls += 1
        time.sleep(0.2)
        return {
            "text": f"\u753b\u4e2a\u5706{self.calls}",
            "segments": [{"avg_logprob": 2.0}],
        }


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_vad_uses_responsive_timings() -> None:
    """VAD 参数应偏向快速结束一句话。"""
    assert AudioBuffer.SILENCE_DURATION <= 0.5
    assert AudioBuffer.MIN_VOICE_DURATION <= 0.35
    assert AudioBuffer.BLOCK_DURATION <= 0.2


def test_voice_service_keeps_latest_audio_when_busy() -> None:
    """识别忙时不应直接丢掉最新语音片段。"""
    app = _app()
    model = _SlowWhisperModel()
    service = VoiceService()
    service._base_model = model
    audio1 = np.ones(16000, dtype=np.float32) * 0.02
    audio2 = np.ones(16000, dtype=np.float32) * 0.03
    transcriptions: list[str] = []
    service.signals.transcription_ready.connect(
        lambda text, confidence: transcriptions.append(text)
    )

    service._on_audio_ready(audio1)
    service._on_audio_ready(audio2)

    deadline = time.perf_counter() + 3.0
    while len(transcriptions) < 2 and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert model.calls == 2
    assert transcriptions == ["\u753b\u4e2a\u57061", "\u753b\u4e2a\u57062"]
    assert app is not None


if __name__ == "__main__":
    test_vad_uses_responsive_timings()
    test_voice_service_keeps_latest_audio_when_busy()
    print("test_voice_responsiveness: OK")
