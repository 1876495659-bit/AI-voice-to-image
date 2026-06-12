"""麦克风 VAD 灵敏度测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.audio_buffer import AudioBuffer


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_soft_speech_above_default_threshold_triggers_audio_ready() -> None:
    """较轻的说话音量也应触发语音片段。"""
    app = _app()
    buffer = AudioBuffer()
    buffer._mic_sr = 16000
    buffer._volume_threshold = 0.004
    ready_audio: list[np.ndarray] = []
    buffer.audio_ready.connect(ready_audio.append)

    speech = np.ones(8000, dtype=np.float32) * 0.006
    silence = np.zeros(8000, dtype=np.float32)
    buffer._audio_callback(speech.reshape(-1, 1), len(speech), None, None)
    buffer._audio_callback(silence.reshape(-1, 1), len(silence), None, None)
    buffer._silence_start = time.monotonic() - buffer.SILENCE_DURATION - 0.05
    buffer._try_flush(0.0)
    buffer._poll_queue()

    assert ready_audio
    assert app is not None


if __name__ == "__main__":
    test_soft_speech_above_default_threshold_triggers_audio_ready()
    print("test_audio_buffer_sensitivity: OK")
