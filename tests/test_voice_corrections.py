"""语音识别文本纠错测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.voice_service import VoiceService


def test_voice_correction_fixes_stream_and_creek_misrecognition() -> None:
    """小溪/小河常见误识别应在进入解析前修正。"""
    service = VoiceService()

    assert service._clean_transcription("在树的下面画一条合流") == "在树的下面画一条河流"
    assert service._clean_transcription("站速的右边画一条流动的小锡") == "在树的右边画一条流动的小溪"


if __name__ == "__main__":
    test_voice_correction_fixes_stream_and_creek_misrecognition()
    print("test_voice_corrections: OK")
