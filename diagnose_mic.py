"""诊断麦克风问题并修复。"""
import sys
import numpy as np
import sounddevice as sd

print("=" * 50)
print("麦克风诊断")
print("=" * 50)
print()

# 1. 列出所有音频设备
print("[1] 可用音频设备:")
devices = sd.query_devices()
print(f"  默认输入设备: {sd.default.device[0]}")
print(f"  默认输出设备: {sd.default.device[1]}")
print()
for i, dev in enumerate(devices):
    name = dev.get('name', f'设备{i}')
    inp = dev.get('max_input_channels', '?')
    out = dev.get('max_output_channels', '?')
    sr = dev.get('default_samplerate', '?')
    kind = ''
    if inp > 0:
        kind += ' [IN]'
    if out > 0:
        kind += ' [OUT]'
    if i == sd.default.device[0]:
        kind += ' << 默认输入'
    if i == sd.default.device[1]:
        kind += ' << 默认输出'
    print(f"  {i}: {name}{kind}")
    print(f"      输入: {inp}, 输出: {out}, 采样率: {sr}")
print()

# 2. 测试麦克风采集
print("[2] 麦克风采集测试 (5秒):")
try:
    print("  正在录制... 请对着麦克风说话")
    print("  (5秒后自动停止)")

    # 使用默认设备
    rec = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype=np.float32)
    sd.wait()

    # 分析
    rms = float(np.sqrt(np.mean(rec ** 2)))
    peak = float(np.max(np.abs(rec)))
    duration = len(rec) / 16000

    print(f"  录制时长: {duration:.1f}s")
    print(f"  采样点数: {len(rec)}")
    print(f"  RMS 音量: {rms:.6f}")
    print(f"  峰值音量: {peak:.6f}")

    # 检测是否有语音段
    chunks = np.split(rec, max(1, len(rec) // 16000))  # 每秒一块
    speech_chunks = sum(1 for c in chunks if np.sqrt(np.mean(c**2)) > 0.001)
    print(f"  语音片段: {speech_chunks}/{len(chunks)} 秒")

    if rms < 0.0001:
        print()
        print("  ⚠️  警告: 音量极低! 可能原因:")
        print("     1. 麦克风未连接或被禁用")
        print("     2. 麦克风权限未授予")
        print("     3. 输入设备选择错误")
        print("     4. 麦克风静音了")
    else:
        print()
        print("  ✅ 麦克风工作正常!")

except Exception as e:
    print(f"  ❌ 采集失败: {e}")
    print()
    print("  可能原因:")
    print("     1. sounddevice 无法访问音频设备")
    print("     2. 需要安装 PortAudio")
    print(f"     错误详情: {e}")

print()
print("=" * 50)
