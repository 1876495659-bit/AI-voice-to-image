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
import threading
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

    recognition_started = pyqtSignal()
    partial_transcription = pyqtSignal(str)
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

        # 防抖: 两次识别之间保留短间隔，避免吞掉连续语音指令
        self._last_transcribe_time = 0.0
        self._COOLDOWN = 0.35
        self._stream_char_interval = 0.025
        self._transcribe_lock = threading.Lock()
        self._is_transcribing = False
        self._pending_audio: Optional[np.ndarray] = None

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

        with self._transcribe_lock:
            if self._is_transcribing:
                self._pending_audio = trimmed
                logger.debug("识别任务仍在运行，保留最新语音片段")
                return
            self._is_transcribing = True

        worker = threading.Thread(
            target=self._transcribe_worker,
            args=(trimmed,),
            daemon=True,
        )
        worker.start()

    def _transcribe_worker(self, audio: np.ndarray) -> None:
        """后台线程执行 Whisper，避免阻塞 Qt 主线程。"""
        try:
            self.signals.recognition_started.emit()
            text, confidence = self._transcribe(audio)
            if text:
                self._last_transcribe_time = time.monotonic()
                logger.info("识别: \"%s\" (置信度: %.2f)", text, confidence)
                self._emit_partial_transcription(text)
                self.signals.transcription_ready.emit(text, confidence)
            else:
                logger.debug("未识别到语音 (trimmed: %.2fs)", len(audio) / 16000)
        except Exception as e:
            logger.error("Whisper 推理失败: %s", e)
            self.signals.error.emit(f"语音识别失败: {e}")
        finally:
            next_audio: Optional[np.ndarray] = None
            with self._transcribe_lock:
                if self._pending_audio is not None:
                    next_audio = self._pending_audio
                    self._pending_audio = None
                else:
                    self._is_transcribing = False

            if next_audio is not None:
                self._transcribe_worker(next_audio)

    def _emit_partial_transcription(self, text: str) -> None:
        """逐字发出识别文本前缀，供界面实时展示。"""
        current = ""
        for char in text:
            current += char
            self.signals.partial_transcription.emit(current)
            if self._stream_char_interval > 0:
                time.sleep(self._stream_char_interval)

    def _transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        """使用主模型识别，置信度低时回退。

        Returns:
            (text, confidence)
        """
        device = "cuda" if config.WHISPER_USE_CUDA else "cpu"
        prompt = (
            "这是中文语音绘图指令。常见命令包括："
            "开始语音识别，停止语音识别，撤销，重做，清空；"
            "用红色画笔，在中间画一个圆圈，在左上角画一个空心圆，"
            "右下角画蓝色矩形，画三角形，画星形，画直线，"
            "颜色包括红色、蓝色、绿色、黄色、黑色、白色。"
        )

        result = self._base_model.transcribe(
            audio,
            language="zh",
            fp16=False,
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
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
                temperature=0.0,
                condition_on_previous_text=False,
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
