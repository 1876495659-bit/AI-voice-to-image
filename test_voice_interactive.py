"""交互式语音测试 — 在终端运行，无需 GUI。

用法:
    python test_voice_interactive.py

它会:
1. 列出可用麦克风
2. 录制 3 秒音频
3. 用 Whisper 识别
4. 打印结果
"""
import sys
import numpy as np
import sounddevice as sd
import whisper

print("=" * 50)
print("交互式语音测试")
print("=" * 50)
print()

# 1. 选择麦克风
print("[1] 选择麦克风:")
devices = sd.query_devices()
for i, dev in enumerate(devices):
    name = dev.get('name', f'设备{i}')
    inp = dev.get('max_input_channels', '?')
    if inp > 0:
        marker = " << 默认" if i == sd.default.device[0] else ""
        print(f"  {i}: {name}{marker}")

try:
    idx = int(input(f"\n  输入麦克风编号 (默认 {sd.default.device[0]}): ") or sd.default.device[0])
    print(f"  使用麦克风 #{idx}: {devices[idx]['name']}")
except ValueError:
    idx = sd.default.device[0]
    print(f"  使用默认麦克风: {devices[idx]['name']}")
print()

# 2. 加载 Whisper 模型
print("[2] 加载 Whisper 模型...")
model = whisper.load_model("base", device="cpu")
print("  模型加载完成")
print()

# 3. 录制并识别
print("[3] 开始录音...")
print("  请对着麦克风说话 (3秒后自动停止)")
print()

# 录制 3 秒
recording = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype=np.float32, device=idx)
sd.wait()

# 分析音量
rms = float(np.sqrt(np.mean(recording ** 2)))
peak = float(np.max(np.abs(recording)))
print(f"  录制完成")
print(f"  RMS 音量: {rms:.6f}")
print(f"  峰值: {peak:.6f}")
print()

if rms < 0.0001:
    print("  ⚠️  音量太低! 请:")
    print("     1. 确认麦克风已连接")
    print("     2. 确认麦克风权限已开启")
    print("     3. 确认没有静音")
    print("     4. 靠近麦克风说话")
    sys.exit(1)

# 识别
print("  Whisper 正在识别...")
result = model.transcribe(
    recording.flatten(),
    language="zh",
    fp16=False,
    task="transcribe",
)
text = result.get("text", "").strip()

print()
print("=" * 50)
print(f"  识别结果: \"{text}\"")
print("=" * 50)
print()

if text:
    print("  ✅ 语音识别成功!")
    print()
    print("  下一步: 运行 python main.py")
    print("  然后说: \"开始监听\"")
    print("  再说指令如: \"画个圆\"")
else:
    print("  ⚠️  未识别到语音")
    print()
    print("  可能原因:")
    print("     1. 语音不够清晰")
    print("     2. 环境噪音太大")
    print("     3. 尝试大声、清晰地说话")
    print()
    print("  建议:")
    print("     1. 关闭不必要的软件")
    print("     2. 在安静环境中测试")
    print("     3. 确认使用的是正确的麦克风")
