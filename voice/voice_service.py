"""语音识别服务。

将 AudioBuffer 采集的音频块送入 Whisper 进行识别，
支持 base/smallest 双模型策略。

引用:
- `config.py` — WHISPER_MODEL_SIZE, WHISPER_FALLBACK_MODEL,
                 WHISPER_FALLBACK_THRESHOLD, WHISPER_USE_CUDA
- `voice/audio_buffer.py` — AudioBuffer 音频采集
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import whisper
from PyQt6.QtCore import QObject, pyqtSignal

import config
from voice.audio_buffer import AudioBuffer

logger = logging.getLogger(__name__)


class VoiceServiceSignals(QObject):
    """语音服务信号。"""

    # 识别完成: (转录文本, 置信度)
    transcription_ready = pyqtSignal(str, float)
    # 识别开始
    listening_started = pyqtSignal()
    # 识别停止
    listening_stopped = pyqtSignal()
    # 错误
    error = pyqtSignal(str)


class VoiceService(QObject):
    """语音识别服务，集成 AudioBuffer + Whisper 推理。

    工作流程:
      AudioBuffer.audio_ready → 送入 Whisper → 转录 + 置信度 → 发出信号

    双模型策略:
      - base 模型先行（~1s，快但精度稍低）
      - 如果置信度 < 阈值，自动用 small 模型重试（~2s，更准）

    Attributes:
        signals: 信号对象。
        audio_buffer: 音频采集器。
    """

    def __init__(self, audio_buffer: Optional[AudioBuffer] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.signals = VoiceServiceSignals()

        # 音频缓冲区
        self.audio_buffer = audio_buffer or AudioBuffer()

        # Whisper 模型
        self._base_model: Optional[whisper.Whisper] = None
        self._small_model: Optional[whisper.Whisper] = None
        self._current_model_size: str = config.WHISPER_MODEL_SIZE

        # 连接信号
        self.audio_buffer.audio_ready.connect(self._on_audio_ready)
        self.audio_buffer.error.connect(self.signals.error)

    # --- 生命周期 ---

    def initialize(self) -> bool:
        """初始化 Whisper 模型。

        Returns:
            成功返回 True。
        """
        try:
            device = "cuda" if config.WHISPER_USE_CUDA else "cpu"
            self._base_model = whisper.load_model(
                config.WHISPER_MODEL_SIZE, device=device
            )
            # small 模型延迟加载（节省初始启动时间）
            logger.info("Whisper base 模型加载完成")
            return True
        except Exception as e:
            logger.error(f"Whisper 模型加载失败: {e}")
            self.signals.error.emit(f"语音识别初始化失败: {e}")
            return False

    def start_listening(self) -> bool:
        """开始监听麦克风。"""
        if not self.audio_buffer.start():
            return False
        self.signals.listening_started.emit()
        return True

    def stop_listening(self) -> None:
        """停止监听麦克风。"""
        self.audio_buffer.stop()
        self.signals.listening_stopped.emit()

    @property
    def is_listening(self) -> bool:
        """是否正在监听。"""
        return self.audio_buffer.is_running

    # --- 音频处理 ---

    def _on_audio_ready(self, audio: np.ndarray) -> None:
        """音频块到达时的回调。"""
        if self._base_model is None:
            return

        try:
            # 使用当前模型识别
            result = self._base_model.transcribe(
                audio,
                language="zh",
                fp16=False,  # CPU 上 fp16 可能出错
            )
            text = result.get("text", "").strip()
            # Whisper base 不返回置信度，使用默认高置信度
            # 实际项目中可用 whisper 的 token logprobs 计算
            confidence = self._estimate_confidence(result, text)

            # 置信度不足时尝试 small 模型
            if confidence < config.WHISPER_FALLBACK_THRESHOLD:
                confidence = self._fallback_recognition(audio, text)

            if text:
                self.signals.transcription_ready.emit(text, confidence)

        except Exception as e:
            logger.error(f"Whisper 推理失败: {e}")
            self.signals.error.emit(f"语音识别失败: {e}")

    def _fallback_recognition(self, audio: np.ndarray, current_text: str) -> float:
        """回退到 small 模型重新识别。"""
        if self._small_model is None:
            try:
                device = "cuda" if config.WHISPER_USE_CUDA else "cpu"
                self._small_model = whisper.load_model(
                    config.WHISPER_FALLBACK_MODEL, device=device
                )
                logger.info("Whisper small 模型回退加载完成")
            except Exception as e:
                logger.error(f"Whisper small 模型加载失败: {e}")
                return 0.5  # 默认低置信度

        try:
            result = self._small_model.transcribe(
                audio,
                language="zh",
                fp16=False,
            )
            text = result.get("text", "").strip()
            confidence = self._estimate_confidence(result, text)

            if text:
                self.signals.transcription_ready.emit(text, confidence)

            return confidence
        except Exception as e:
            logger.error(f"回退识别失败: {e}")
            return 0.5

    def _estimate_confidence(self, result: dict, text: str) -> float:
        """估算转录置信度。

        基于 Whisper 结果的简单启发式估计。

        Returns:
            0-1 之间的置信度分数。
        """
        if not text:
            return 0.0

        # 尝试从 result 中获取 token logprobs
        segments = result.get("segments", [])
        if segments:
            # 计算平均 token 概率
            total_prob = 0.0
            token_count = 0
            for seg in segments:
                for tok in seg.get("tokens", []):
                    if "avg_logprob" in tok:
                        total_prob += tok["avg_logprob"]
                        token_count += 1
            if token_count > 0:
                avg_logprob = total_prob / token_count
                # 将 logprob 转换为 0-1 置信度
                confidence = 1.0 / (1.0 + math.exp(-avg_logprob))
                return max(0.0, min(1.0, confidence))

        # 回退到文本长度启发式
        # 中文短句置信度更高
        char_count = len(text)
        if char_count < 3:
            return 0.5
        elif char_count < 10:
            return 0.7
        else:
            return 0.85

    # --- 辅助 ---

    def reload_models(self) -> None:
        """重新加载模型（例如在设置变更后）。"""
        self._base_model = None
        self._small_model = None
        self.initialize()
