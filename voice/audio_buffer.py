"""音频采集 + 语音活动检测 (VAD)。

连续采集麦克风音频，基于 RMS 音量检测语音开始/结束。
启动时自动测量背景噪音并设置阈值。

引用:
- `config.py` — AUDIO_SAMPLE_RATE, AUDIO_VOLUME_THRESHOLD
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

import config


class AudioBuffer(QObject):
    """麦克风音频采集 + VAD。

    VAD 策略:
      1. 启动时测量 2 秒背景噪音 (95 百分位)
      2. 阈值 = 噪音峰值 × 2 + 余量
      3. 语音持续期间，音量降到「接近静音」时启动静音计时
      4. 静音计时结束后发送累积的语音

    信号:
        audio_ready: (numpy.ndarray) 一段完整语音 (16kHz, float32)。
        volume_changed: (float) 当前音量 RMS。
        error: (str) 错误信息。
    """

    audio_ready = pyqtSignal(object)
    volume_changed = pyqtSignal(float)
    error = pyqtSignal(str)

    # ── 可调参数 ────────────────────────────────────────
    SILENCE_DURATION: float = 0.5       # 静音多久算语音结束
    MIN_VOICE_DURATION: float = 0.3     # 最短语音时长 (秒)
    BLOCK_DURATION: float = 0.3         # 回调块大小 (秒)
    NEAR_SILENCE_FACTOR: float = 0.3    # 接近静音倍率 (rms < threshold × factor)

    def __init__(self,
                 sample_rate: int = config.AUDIO_SAMPLE_RATE,
                 volume_threshold: Optional[float] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._target_sr = sample_rate       # 16000
        self._custom_threshold = volume_threshold

        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._lock = threading.Lock()
        self._mic_sr: int = 0
        self._volume_threshold: float = 0.0

        # VAD 状态
        self._vad_active = False
        self._voice_data: list[np.ndarray] = []
        self._silence_start: float = 0.0

        # 节流音量信号
        self._last_vol_time = 0.0
        self._pending_vol: float = 0.0

        # 线程安全队列
        import queue
        self._data_queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue(maxsize=5)

        # QTimer 主线程轮询
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(80)
        self._poll_timer.timeout.connect(self._poll_queue)

    # ── 生命周期 ───────────────────────────────────────

    def start(self) -> bool:
        """启动麦克风采集，自动检测采样率和背景噪音。"""
        with self._lock:
            if self._running:
                return True

        try:
            dev_info = sd.query_devices(sd.default.device[0])
            self._mic_sr = int(dev_info.get('default_samplerate', 16000))
            if self._mic_sr < 8000:
                self._mic_sr = 16000

            # 设定阈值 — 不测量，直接用固定值
            self._volume_threshold = self._custom_threshold if self._custom_threshold is not None and self._custom_threshold > 0 \
                else config.AUDIO_VOLUME_THRESHOLD
            print(f"[AudioBuffer] 使用阈值: {self._volume_threshold:.4f}")

            near_silence = self._volume_threshold * self.NEAR_SILENCE_FACTOR
            block_size = int(self._mic_sr * self.BLOCK_DURATION)

            print(f"[AudioBuffer] 麦克风: {self._mic_sr} Hz, "
                  f"Whisper: {self._target_sr} Hz, "
                  f"VAD阈值: {self._volume_threshold:.4f}, "
                  f"接近静音: {near_silence:.4f}, "
                  f"静音窗口: {self.SILENCE_DURATION}s")

            self._stream = sd.InputStream(
                samplerate=self._mic_sr,
                channels=1,
                blocksize=block_size,
                callback=self._audio_callback,
                latency='low',
            )
            self._stream.start()
            self._running = True
            self._reset_vad()
            self._poll_timer.start()
            return True
        except Exception as e:
            self.error.emit(f"麦克风启动失败: {e}")
            print(f"[AudioBuffer] 启动失败: {e}")
            return False

    def _measure_background_noise(self, duration: float | None = None) -> float:
        """测量 95 百分位的背景噪音 RMS。"""
        dur = duration if duration is not None else self.NOISE_MEASURE_DURATION
        block_size = int(self._mic_sr * 0.2)
        try:
            stream = sd.InputStream(
                samplerate=self._mic_sr, channels=1,
                blocksize=block_size, latency='low',
            )
            stream.start()
            rms_values = []
            for _ in range(int(dur / 0.2)):
                data, _ = stream.read(block_size)
                audio = np.mean(data, axis=1).astype(np.float32)
                rms_values.append(float(np.sqrt(np.mean(audio ** 2))))
            stream.stop()
            stream.close()
            return float(np.percentile(rms_values, 95)) if rms_values else 0.01
        except Exception:
            return 0.01

    def stop(self) -> None:
        """停止麦克风采集。"""
        with self._lock:
            if not self._running:
                return
            self._poll_timer.stop()
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
            self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def vad_active(self) -> bool:
        return self._vad_active

    # ── VAD 状态机 ────────────────────────────────────

    @property
    def _near_silence(self) -> float:
        return self._volume_threshold * self.NEAR_SILENCE_FACTOR

    def _reset_vad(self) -> None:
        self._vad_active = False
        self._voice_data = []
        self._silence_start = 0.0

    def _try_flush(self, rms: float) -> None:
        """检查是否该发送语音。

        - rms > near_silence: 还不够安静，重置计时
        - rms <= near_silence: 开始/继续静音计时
        - 静音持续 SILENCE_DURATION 后 → 发送
        """
        if not self._vad_active or not self._voice_data:
            return

        if rms > self._near_silence:
            self._silence_start = 0.0
            return

        if self._silence_start == 0.0:
            self._silence_start = time.monotonic()
            return

        if time.monotonic() - self._silence_start >= self.SILENCE_DURATION:
            self._send_voice()
            self._reset_vad()

    def _send_voice(self) -> None:
        """拼接 → 校验 → 入队。"""
        combined = np.concatenate(self._voice_data)
        self._voice_data = []

        if len(combined) == 0:
            return

        duration = len(combined) / self._target_sr
        if duration < self.MIN_VOICE_DURATION:
            return

        # 截断（CPU Whisper 很慢，最长 6 秒）
        max_samples = int(self._target_sr * 6.0)
        if len(combined) > max_samples:
            combined = combined[:max_samples]

        # 裁剪首尾静音
        abs_audio = np.abs(combined)
        idx = np.where(abs_audio > 1e-4)[0]
        if len(idx) > 0:
            combined = combined[idx[0]:idx[-1] + 1]

        if len(combined) == 0 or len(combined) / self._target_sr < 0.2:
            return

        try:
            self._data_queue.put_nowait(combined)
        except Exception:
            pass

    def _resample_chunk(self, audio: np.ndarray) -> np.ndarray:
        """线性插值重采样到 16kHz。"""
        if self._mic_sr <= 0 or self._mic_sr == self._target_sr:
            return audio.astype(np.float32)

        orig_dur = len(audio) / self._mic_sr
        n_target = max(1, int(round(orig_dur * self._target_sr)))

        orig_t = np.linspace(0, orig_dur, len(audio), endpoint=False)
        target_t = np.linspace(0, orig_dur, n_target, endpoint=False)

        return np.interp(target_t, orig_t, audio).astype(np.float32)

    # ── 回调 ───────────────────────────────────────────

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info, status: sd.CallbackFlags) -> None:
        """后台线程: 采集 → 重采样 → VAD。"""
        if status:
            return

        audio = np.mean(indata, axis=1).astype(np.float32) if indata.ndim > 1 else indata
        rms = float(np.sqrt(np.mean(audio ** 2)))

        # 节流音量信号
        now = time.monotonic()
        if now - self._last_vol_time > 0.2:
            self._last_vol_time = now
            self._pending_vol = rms

        thr = self._volume_threshold
        near = self._near_silence

        if rms > thr:
            # 明显有声音
            if not self._vad_active:
                self._vad_active = True
                self._voice_data = []
            self._voice_data.append(self._resample_chunk(audio))
        elif rms > near:
            # 较低音量 — 可能是句子内停顿，继续累积
            if self._vad_active:
                self._voice_data.append(self._resample_chunk(audio))
        else:
            # 接近静音 → 尝试 flush
            self._try_flush(rms)

    # ── 主线程轮询 ────────────────────────────────────

    def _poll_queue(self) -> None:
        while not self._data_queue.empty():
            try:
                audio = self._data_queue.get_nowait()
                if audio is not None:
                    self.audio_ready.emit(audio)
            except Exception:
                pass

        if hasattr(self, '_pending_vol'):
            self.volume_changed.emit(self._pending_vol)
