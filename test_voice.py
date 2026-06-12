"""语音功能测试脚本 — 无需 GUI。"""
import sys
import numpy as np
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

print("=" * 50)
print("语音功能测试")
print("=" * 50)
print()

# ── 1. AudioBuffer ──────────────────────────────────
print("[1] AudioBuffer 测试")
from voice.audio_buffer import AudioBuffer
buf = AudioBuffer()
print(f"  采样率: {buf._sample_rate}")
print(f"  块大小: {buf._chunk_size}")
print(f"  运行中: {buf.is_running}")

buf.start()
print(f"  启动后运行中: {buf.is_running}")

# 采集 1 秒
import time
time.sleep(1.1)
data = buf.get_buffer_data()
if data is not None:
    print(f"  缓冲区数据长度: {len(data)}")
    rms = float(np.sqrt(np.mean(data ** 2)))
    print(f"  当前音量(RMS): {rms:.6f}")
    print(f"  VAD活跃: {buf.vad_active}")
else:
    print("  缓冲区数据: None")

buf.stop()
print(f"  停止后运行中: {buf.is_running}")
print("  OK")
print()

# ── 2. VoiceService 初始化 ─────────────────────────
print("[2] VoiceService 初始化")
from voice.voice_service import VoiceService
vs = VoiceService()
print("  正在加载 Whisper base 模型...")
result = vs.initialize()
print(f"  初始化结果: {result}")
print(f"  模型加载: {vs._base_model is not None}")
if result:
    print("  OK")
else:
    print("  WARN: 模型加载失败")
print()

# ── 3. Whisper 推理测试 ────────────────────────────
print("[3] Whisper 推理测试")
if vs._base_model:
    # 静音测试
    silence = np.zeros(16000, dtype=np.float32)
    result = vs._base_model.transcribe(silence, language="zh", fp16=False)
    text = result.get("text", "").strip()
    print(f"  静音输入: \"{text}\"")
    print(f"  segments: {len(result.get('segments', []))}")

    # 短语音测试（2秒）
    short_audio = np.random.randn(32000).astype(np.float32) * 0.01
    result2 = vs._base_model.transcribe(short_audio, language="zh", fp16=False)
    text2 = result2.get("text", "").strip()
    print(f"  噪声输入: \"{text2}\"")
    print("  OK")
else:
    print("  SKIP: 模型未加载")
print()

# ── 4. 置信度估算 ──────────────────────────────────
print("[4] 置信度估算")
if vs._base_model:
    conf = vs._estimate_confidence({"segments": [{"tokens": [{"avg_logprob": -0.5}]}]}, "你好世界")
    print(f"  正常文本置信度: {conf:.4f}")
    conf_empty = vs._estimate_confidence({}, "")
    print(f"  空文本置信度: {conf_empty}")
    print("  OK")
print()

# ── 5. 命令解析管道 ────────────────────────────────
print("[5] 命令解析管道")
from parser.command_parser import CommandParser
parser = CommandParser()
test_cases = [
    ("用画笔", "工具"),
    ("画个圆", "形状"),
    ("红色", "颜色"),
    ("撤销", "系统"),
    ("清空", "系统"),
    ("大小 10", "粗细"),
    ("生成一幅日落海景", "AI"),
]
for text, category in test_cases:
    r = parser.parse(text, 0.9)
    status = "OK" if r.is_success else "FAIL"
    ops = [o.op_type.name for o in r.operations]
    print(f"  [{status}] [{category}] \"{text}\" -> {ops}")
print()

# ── 6. 完整管道 ────────────────────────────────────
print("[6] 完整管道测试 (语音 -> 解析 -> 引擎)")
from engine.drawing_engine import DrawingEngine
engine = DrawingEngine()

# 模拟语音识别结果
mock_transcriptions = [
    ("用画笔", 0.95),
    ("红色", 0.92),
    ("画个圆", 0.88),
    ("撤销", 0.99),
]

for text, confidence in mock_transcriptions:
    r = parser.parse(text, confidence)
    if r.is_success:
        engine.execute_multiple(r.operations)
        print(f"  \"{text}\" -> 执行 {len(r.operations)} 个操作")
    else:
        print(f"  \"{text}\" -> 解析失败")

print(f"  最终状态: 工具={engine.current_tool}, 颜色={engine.current_color}, 粗细={engine.current_size}")
print(f"  历史操作数: {engine.history.undo_count}")
print("  OK")

print()
print("=" * 50)
print("语音管道测试完成！")
print("=" * 50)
print()
print("实际麦克风语音测试需要:")
print("  1. 运行 python main.py")
print("  2. 说\"开始监听\"启动麦克风")
print("  3. 说指令如\"画个圆\"")
print()
sys.exit(0)
