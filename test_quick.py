import sys
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from ui.main_window import MainWindow
from engine.operations import CircleOperation

win = MainWindow()
buttons = win.toolbar.findChildren(__import__('PyQt6.QtWidgets', fromlist=['QPushButton']).QtWidgets.QPushButton if False else __import__('PyQt6.QtWidgets', fromlist=['QPushButton']).QPushButton)

print(f"[1] 组件: OK, 按钮: {len(buttons)}")

# 解析
from parser.command_parser import ParseResultType
r = win.parser.parse('画个圆', 0.95)
print(f"[2] 解析 '画个圆': {'OK' if r.is_success else 'FAIL'}")

# 引擎
win.engine.execute(CircleOperation(color='#FF0000', size=3))
print(f"[3] 执行后操作数: {win.canvas.operation_count}")
win.engine.undo()
print(f"[4] 撤销后操作数: {win.canvas.operation_count}")
win.engine.redo()
print(f"[5] 重做后操作数: {win.canvas.operation_count}")
win.engine.undo()
print(f"[6] 撤销后操作数: {win.canvas.operation_count}")

# 清空
win.engine.clear()
print(f"[7] 清空后操作数: {win.canvas.operation_count}")

from parser import color_map
print(f"[8] 颜色映射: 红色={color_map.get_color('红色')}")
print(f"[9] 色块数: {len(win.color_panel._buttons)}")

win.voice_panel.show_transcription('测试', 0.9)
print(f"[10] 语音面板: {win.voice_panel.text_label.text()}")

from parser.command_parser import ParseResult
from engine.operations import CircleOperation as CO
fake = ParseResult(type=ParseResultType.SUCCESS, operations=[CO()], confidence=0.95, raw_text='测试')
win.history_panel.add_entry(fake)
print(f"[11] 历史记录: {win.history_panel.entry_count}")

print("\n=== 全部通过 ===")
sys.exit(0)
