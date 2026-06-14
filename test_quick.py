"""快速冒烟测试。"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QPushButton

from engine.operations import CircleOperation
from parser.command_parser import ParseResultType
from ui.main_window import MainWindow


app = QApplication.instance() or QApplication(sys.argv)
win = MainWindow()
buttons = win.findChildren(QPushButton)

print(f"[1] 组件: OK, 按钮: {len(buttons)}")
assert len(buttons) == 1
assert buttons[0].text() in ("开始语音识别", "停止语音识别")
assert hasattr(win, "canvas_scroll")
assert not hasattr(win, "toolbar")

r = win.parser.parse("画个圆", 0.95)
print(f"[2] 解析 '画个圆': {'OK' if r.is_success else 'FAIL'}")
assert r.is_success

win.engine.execute(CircleOperation(color="#FF0000", size=3))
print(f"[3] 执行后操作数: {win.canvas.operation_count}")
assert win.canvas.operation_count == 1

win.engine.undo()
print(f"[4] 撤销后操作数: {win.canvas.operation_count}")
assert win.canvas.operation_count == 0

win.engine.redo()
print(f"[5] 重做后操作数: {win.canvas.operation_count}")
assert win.canvas.operation_count == 1

win.engine.clear()
print(f"[6] 清空后操作数: {win.canvas.operation_count}")
assert win.canvas.operation_count == 0

command = "帮我用红色画笔 在中间画一个 圆圈"
win.voice_service.signals.transcription_ready.emit(command, 0.46)
print(f"[7] 语音执行后操作数: {win.canvas.operation_count}")
assert win.canvas.operation_count == 1
assert "CIRCLE" in win.voice_panel.action_label.text()

print("\n=== 全部通过 ===")
assert app is not None
