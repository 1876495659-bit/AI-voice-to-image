"""语音功能测试脚本（无需真实麦克风和 Whisper 模型）。"""

from __future__ import annotations

import sys

import numpy as np
from PyQt6.QtWidgets import QApplication

from engine.drawing_engine import DrawingEngine
from parser.command_parser import CommandParser
from voice.audio_buffer import AudioBuffer
from voice.voice_service import VoiceService


app = QApplication.instance() or QApplication(sys.argv)

print("=" * 50)
print("语音功能测试")
print("=" * 50)
print()


print("[1] AudioBuffer 合成 VAD 测试")
buf = AudioBuffer(volume_threshold=0.008)
buf._mic_sr = 16000
buf._volume_threshold = 0.008

ready_audio: list[np.ndarray] = []
buf.audio_ready.connect(ready_audio.append)

speech = np.ones(16000, dtype=np.float32) * 0.02
silence = np.zeros(16000, dtype=np.float32)
buf._audio_callback(speech.reshape(-1, 1), len(speech), None, None)
buf._audio_callback(silence.reshape(-1, 1), len(silence), None, None)
buf._silence_start = 0.0
buf._try_flush(0.0)
buf._silence_start -= buf.SILENCE_DURATION + 0.1
buf._try_flush(0.0)
buf._poll_queue()

assert ready_audio, "合成语音应触发 audio_ready"
print(f"  输出语音长度: {len(ready_audio[0])}")
print("  OK")
print()


print("[2] VoiceService 转录信号测试")


class _FakeWhisperModel:
    def transcribe(self, audio, **kwargs):
        return {
            "text": "\u753b\u4e2a\u5706",
            "segments": [{"avg_logprob": 2.0}],
        }


service = VoiceService(audio_buffer=buf)
service._base_model = _FakeWhisperModel()

transcriptions: list[tuple[str, float]] = []
service.signals.transcription_ready.connect(
    lambda text, confidence: transcriptions.append((text, confidence))
)
service._on_audio_ready(ready_audio[0])

assert transcriptions, "转录结果应通过 transcription_ready 发出"
print(f"  识别文本: {transcriptions[0][0]}")
print(f"  置信度: {transcriptions[0][1]:.2f}")
print("  OK")
print()


print("[3] 命令解析管道")
parser = CommandParser()
test_cases = [
    ("\u7528\u753b\u7b14", "工具"),
    ("\u753b\u4e2a\u5706", "形状"),
    ("\u7ea2\u8272", "颜色"),
    ("\u64a4\u9500", "系统"),
    ("\u6e05\u7a7a", "系统"),
    ("\u5927\u5c0f 10", "粗细"),
    ("\u751f\u6210\u4e00\u5e45\u65e5\u843d\u6d77\u666f", "AI"),
]
for text, category in test_cases:
    result = parser.parse(text, 0.9)
    status = "OK" if result.is_success else "FAIL"
    ops = [op.op_type.name for op in result.operations]
    print(f"  [{status}] [{category}] \"{text}\" -> {ops}")
    assert result.is_success
print()


print("[4] 完整管道测试（转录 -> 解析 -> 引擎）")
engine = DrawingEngine()

for text, confidence in transcriptions:
    result = parser.parse(text, confidence)
    assert result.is_success
    engine.execute_multiple(result.operations)

assert engine.history.undo_count == 1
print(f"  历史操作数: {engine.history.undo_count}")
print("  OK")
print()

print("=" * 50)
print("语音管道测试完成！")
print("=" * 50)

assert app is not None
