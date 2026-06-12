"""音频环形缓冲区。

使用 sounddevice 连续采集麦克风音频，存入固定大小的环形缓冲区。
支持 VAD（语音活动检测）过滤环境噪音。

引用:
- `config.py` — AUDIO_SAMPLE_RATE, AUDIO_CHUNK_DURATION, AUDIO_VOLUME_THRESHOLD
"""

from __future__ import annotations

import threading
from typing import Optional, Callable

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, QThread, pyqtSignal

import config


class AudioBuffer(QObject):
    """麦克风音频采集 + 环形缓冲区。

    使用 sounddevice.InputStream 在后台线程连续采集音频，
    将音频数据写入固定大小的环形缓冲区。

    信号:
        audio_ready: (numpy.ndarray) 新音频块可用。
        error: (str) 采集错误信息。
        volume_changed: (float) 当前音量 RMS 值。
    """

    audio_ready = pyqtSignal(object)  # numpy.ndarray
    error = pyqtSignal(str)
    volume_changed = pyqtSignal(float)

    def __init__(self,
                 sample_rate: int = config.AUDIO_SAMPLE_RATE,
                 chunk_duration: float = config.AUDIO_CHUNK_DURATION,
                 volume_threshold: float = config.AUDIO_VOLUME_THRESHOLD,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._sample_rate = sample_rate
        self._chunk_duration = chunk_duration
        self._chunk_size = int(sample_rate * chunk_duration)
        self._volume_threshold = volume_threshold

        self._stream: Optional[sd.InputStream] = None
        self._buffer: Optional[np.ndarray] = None
        self._running = False
        self._lock = threading.Lock()

        # 语音活动检测状态
        self._vad_active = False

    # --- 生命周期 ---

    def start(self) -> bool:
        """启动麦克风采集。

        Returns:
            成功返回 True，失败返回 False。
        """
        with self._lock:
            if self._running:
                return True

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                blocksize=self._chunk_size,
                callback=self._audio_callback,
                latency='low',
            )
            self._stream.start()
            self._running = True
            self._buffer = np.zeros(self._chunk_size, dtype=np.float32)
            return True
        except Exception as e:
            self.error.emit(f"麦克风启动失败: {e}")
            return False

    def stop(self) -> None:
        """停止麦克风采集。"""
        with self._lock:
            if not self._running:
                return
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
            self._running = False

    @property
    def is_running(self) -> bool:
        """是否正在采集音频。"""
        return self._running

    @property
    def vad_active(self) -> bool:
        """当前是否检测到语音活动。"""
        return self._vad_active

    # --- 音频数据 ---

    def get_buffer_data(self) -> Optional[np.ndarray]:
        """获取缓冲区中的音频数据副本。

        Returns:
            numpy 数组或 None。
        """
        with self._lock:
            if self._buffer is not None:
                return self._buffer.copy()
            return None

    def reset_buffer(self) -> None:
        """重置缓冲区。"""
        with self._lock:
            if self._buffer is not None:
                self._buffer[:] = 0.0

    # --- 内部 ---

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info, status: sd.CallbackFlags) -> None:
        """sounddevice 回调函数，在后台线程执行。

        Args:
            indata: 接收到的音频数据 (N, 1) 形状。
            frames: 帧数。
            time_info: 时间戳信息。
            status: 回调状态标志。
        """
        if status:
            # 记录状态但不中断
            return

        # 转换为一维数组
        audio = np.mean(indata, axis=1)  # 多声道取平均

        # VAD: 计算 RMS 音量
        rms = np.sqrt(np.mean(audio ** 2))
        self._vad_active = rms > self._volume_threshold

        # 发出音量信号（UI 可用以显示音量条）
        self.volume_changed.emit(rms)

        # 静音过滤：音量低于阈值时不发送
        if rms < self._volume_threshold:
            return

        # 更新缓冲区
        with self._lock:
            if self._buffer is not None:
                self._buffer[:] = audio

        # 发出音频块信号（PyQt 自动线程安全）
        self.audio_ready.emit(audio.copy())
