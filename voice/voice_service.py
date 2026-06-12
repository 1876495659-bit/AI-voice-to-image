"""语音识别服务。

将 AudioBuffer 采集的语音片段送入 Whisper 进行识别，
支持 tiny/base 双模型策略。

引用:
- `config.py` — WHISPER_MODEL_SIZE, WHISPER_FALLBACK_MODEL,
                 WHISPER_FALLBACK_THRESHOLD, WHISPER_USE_CUDA
- `voice/audio_buffer.py` — AudioBuffer 音频采集 + VAD
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional

import numpy as np
import whisper
from PyQt6.QtCore import QObject, pyqtSignal

import config
from voice.audio_buffer import AudioBuffer

logger = logging.getLogger(__name__)


class VoiceServiceSignals(QObject):
    """语音服务信号。"""

    transcription_ready = pyqtSignal(str, float)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()
    error = pyqtSignal(str)


class VoiceService(QObject):
    """语音识别服务，集成 AudioBuffer + Whisper 推理。

    工作流程:
      AudioBuffer (VAD) → 语音段到达 → Whisper 识别 → 转录信号

    双模型策略:
      - tiny 模型先行（~0.3s，超快但精度略低）
      - 如果置信度 < 阈值，自动用 base 模型重试（~1s，更准）
    """

    def __init__(self, audio_buffer: Optional[AudioBuffer] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.signals = VoiceServiceSignals()
        self.audio_buffer = audio_buffer or AudioBuffer()

        self._base_model: Optional[whisper.Whisper] = None
        self._fallback_model: Optional[whisper.Whisper] = None

        # 防抖: 两次识别之间至少间隔 2 秒
        self._last_transcribe_time = 0.0
        self._COOLDOWN = 2.0

        self.audio_buffer.audio_ready.connect(self._on_audio_ready)
        self.audio_buffer.error.connect(self.signals.error)

    # ── 生命周期 ───────────────────────────────────────

    def initialize(self) -> bool:
        """初始化 Whisper 模型。"""
        try:
            device = "cuda" if config.WHISPER_USE_CUDA else "cpu"
            self._base_model = whisper.load_model(
                config.WHISPER_MODEL_SIZE, device=device
            )
            logger.info("Whisper 主模型 (%s) 加载完成", config.WHISPER_MODEL_SIZE)
            return True
        except Exception as e:
            logger.error("Whisper 模型加载失败: %s", e)
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
        return self.audio_buffer.is_running

    # ── 音频处理 ──────────────────────────────────────

    def _on_audio_ready(self, audio: np.ndarray) -> None:
        """VAD 触发: 一段完整语音到达。"""
        # 防抖: 避免短时间内重复触发
        now = time.monotonic()
        if now - self._last_transcribe_time < self._COOLDOWN:
            logger.debug("防抖: 跳过 (距上次 %.1fs)", now - self._last_transcribe_time)
            return

        if self._base_model is None:
            return

        # 只取非零部分的音频
        non_zero = np.where(np.abs(audio) > 1e-6)[0]
        if len(non_zero) == 0:
            return

        start = non_zero[0]
        end = non_zero[-1]
        trimmed = audio[start:end + 1]

        # 太长则截断
        max_len = int(self.audio_buffer._target_sr * 6.0)
        if len(trimmed) > max_len:
            trimmed = trimmed[:max_len]

        try:
            text, confidence = self._transcribe(trimmed)
            if text:
                self._last_transcribe_time = time.monotonic()
                logger.info("识别: \"%s\" (置信度: %.2f)", text, confidence)
                self.signals.transcription_ready.emit(text, confidence)
            else:
                logger.debug("未识别到语音 (trimmed: %.2fs)", len(trimmed) / 16000)
        except Exception as e:
            logger.error("Whisper 推理失败: %s", e)
            self.signals.error.emit(f"语音识别失败: {e}")

    def _transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        """使用主模型识别，置信度低时回退。

        Returns:
            (text, confidence)
        """
        device = "cuda" if config.WHISPER_USE_CUDA else "cpu"
        prompt = "绘图指令 颜色 形状 工具 画笔 橡皮 线条 圆 矩形 撤销 清空 保存 红色 蓝色"

        result = self._base_model.transcribe(
            audio,
            language="zh",
            fp16=False,
            task="transcribe",
            initial_prompt=prompt,
        )
        text = result.get("text", "").strip()
        confidence = self._estimate_confidence(result, text)

        if confidence < config.WHISPER_FALLBACK_THRESHOLD:
            # 回退到更大模型
            if self._fallback_model is None:
                try:
                    self._fallback_model = whisper.load_model(
                        config.WHISPER_FALLBACK_MODEL, device=device
                    )
                    logger.info("Whisper 回退模型 (%s) 加载完成", config.WHISPER_FALLBACK_MODEL)
                except Exception as e:
                    logger.error("回退模型加载失败: %s", e)
                    return text, confidence

            result2 = self._fallback_model.transcribe(
                audio,
                language="zh",
                fp16=False,
                initial_prompt=prompt,
            )
            text2 = result2.get("text", "").strip()
            conf2 = self._estimate_confidence(result2, text2)
            if conf2 > confidence and text2:
                return text2, conf2

        return text, confidence

    def _estimate_confidence(self, result: dict, text: str) -> float:
        """从 Whisper 结果估算置信度。"""
        if not text:
            return 0.0

        segments = result.get("segments", [])
        if segments:
            total_logprob = 0.0
            count = 0
            for seg in segments:
                avg_lp = seg.get("avg_logprob", None)
                if avg_lp is not None:
                    total_logprob += avg_lp
                    count += 1
            if count > 0:
                avg = total_logprob / count
                confidence = 1.0 / (1.0 + math.exp(-avg))
                return max(0.0, min(1.0, confidence))

        # 回退启发式
        n = len(text)
        if n < 3:
            return 0.5
        if n < 10:
            return 0.7
        return 0.85
