"""自动语音测试 — 无需交互。"""
import sys
import numpy as np
import sounddevice as sd
import whisper

print("=" * 50)
print("自动语音测试")
print("=" * 50)
print()

# 默认麦克风
idx = sd.default.device[0]
devices = sd.query_devices()
name = devices[idx]['name']
print(f"麦克风: #{idx} - {name}")
print()

# 加载模型
print("加载 Whisper 模型...")
model = whisper.load_model("base", device="cpu")
print("模型加载完成")
print()

# 录制
print("录制 3 秒... 请对着麦克风说话")
recording = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype=np.float32, device=idx)
sd.wait()

rms = float(np.sqrt(np.mean(recording ** 2)))
print(f"RMS 音量: {rms:.6f}")
print()

if rms < 0.0001:
    print("音量太低! 检查麦克风连接和权限")
    sys.exit(1)

# 识别
print("Whisper 识别中...")
result = model.transcribe(recording.flatten(), language="zh", fp16=False, task="transcribe")
text = result.get("text", "").strip()

print()
print("=" * 50)
print(f"识别结果: \"{text}\"")
print("=" * 50)
print()

if text:
    print("✅ 语音识别成功!")
    print("运行 python main.py，说\"开始监听\"后说指令即可")
else:
    print("⚠️ 未识别到语音")
    print("尝试: 靠近麦克风、大声清晰地说、在安静环境中")
