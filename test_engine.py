"""自动化测试 — 无需 GUI 显示。"""
import sys
from pathlib import Path

# ── 1. 引擎测试 ──────────────────────────────
from engine.operations import (
    CircleOperation, ColorOperation, DrawingOperation,
    EraserTool, LineTool, OperationType, PenTool,
    RectangleOperation, SizeOperation, StarOperation, TriangleOperation,
    FreehandOperation, LineDrawOperation, AIImageOperation,
)
from engine.undo_history import UndoHistory
from engine.drawing_engine import DrawingEngine

print("=== 引擎测试 ===")

# UndoHistory
history = UndoHistory(max_size=3)
history.push(CircleOperation())
history.push(ColorOperation(color='#FF0000'))
history.push(SizeOperation(size=10))
assert history.undo_count == 3
assert history.redo_count == 0

op = history.undo()
assert op.op_type == OperationType.SIZE
assert history.undo_count == 2
assert history.redo_count == 1

op = history.redo()
assert op.op_type == OperationType.SIZE
assert history.undo_count == 3
assert history.redo_count == 0

# 溢出测试
history.clear()
history.push(CircleOperation())
history.push(ColorOperation())
history.push(SizeOperation())
history.push(LineDrawOperation())  # 第 4 条，触发溢出
assert history.undo_count == 3  # 只保留 3 条
print("[1] UndoHistory OK")

# DrawingEngine
engine = DrawingEngine(canvas_width=1920, canvas_height=1080)
assert engine.current_tool == 'pen'
assert engine.current_color == '#000000'
assert engine.current_size == 3

engine.execute(PenTool())
assert engine.current_tool == 'pen'

engine.execute(ColorOperation(color='#FF0000'))
assert engine.current_color == '#FF0000'

engine.execute(SizeOperation(size=10))
assert engine.current_size == 10

engine.execute(CircleOperation(color='#FF0000', size=3))
# 4 ops pushed to history (PenTool, ColorOp, SizeOp, CircleOp)
assert engine.history.undo_count == 4

engine.undo()
assert engine.history.undo_count == 3
engine.redo()
assert engine.history.undo_count == 4

engine.execute(ColorOperation(color='#0000FF'))  # 打断 redo 链
assert engine.history.undo_count == 5
assert engine.history.redo_count == 0
print("[2] DrawingEngine OK")

# ── 2. 解析测试 ──────────────────────────────
from parser.command_parser import CommandParser, ParseResult, ParseResultType

print("\n=== 解析测试 ===")
parser = CommandParser(fallback_threshold=0.7, canvas_width=1920, canvas_height=1080)

tests = [
    ('用画笔', ParseResultType.SUCCESS, ['PEN']),
    ('红色', ParseResultType.SUCCESS, ['COLOR']),
    ('画个圆', ParseResultType.SUCCESS, ['CIRCLE']),
    ('画个矩形', ParseResultType.SUCCESS, ['RECTANGLE']),
    ('画个三角形', ParseResultType.SUCCESS, ['TRIANGLE']),
    ('画个星', ParseResultType.SUCCESS, ['STAR']),
    ('撤销', ParseResultType.SUCCESS, ['UNDO']),
    ('清空', ParseResultType.SUCCESS, ['CLEAR']),
    ('大小 10', ParseResultType.SUCCESS, ['SIZE']),
    ('生成一幅日落海景', ParseResultType.SUCCESS, ['AI_IMAGE']),
    ('用红色画笔画个圆', ParseResultType.SUCCESS, ['COLOR', 'PEN', 'CIRCLE']),
    ('用红笔画一个圆圈', ParseResultType.SUCCESS, ['COLOR', 'PEN', 'CIRCLE']),
    ('', ParseResultType.REJECT, []),
]

for text, expected_type, expected_ops in tests:
    r = parser.parse(text, 0.95)
    assert r.type == expected_type, f'FAIL: "{text}" type={r.type} expected={expected_type}'
    op_names = [o.op_type.name for o in r.operations]
    assert op_names == expected_ops, f'FAIL: "{text}" ops={op_names} expected={expected_ops}'
    print(f"  OK: \"{text}\" -> {op_names}")
print(f"[3] 命令解析 {len(tests)}/{len(tests)} OK")

# ── 3. 颜色映射测试 ──────────────────────────
from parser import color_map

print("\n=== 颜色映射测试 ===")
assert color_map.get_color('红色') == '#FF0000'
assert color_map.get_color('蓝色') == '#0000FF'
assert color_map.get_color('深蓝') == '#00008B'
assert color_map.get_color('#FF5733') == '#FF5733'
assert color_map.get_color('xyz') == '#000000'  # 未知色
print("[4] 颜色映射 5/5 OK")
print(f"  总色数: {len(color_map.COLOR_MAP)}")

# ── 5. 综合流程测试 ──────────────────────────
print("\n=== 综合流程 ===")
engine2 = DrawingEngine()
result = parser.parse('用红色画笔画个圆', 0.95)
assert result.is_success
for op in result.operations:
    engine2.execute(op)
assert engine2.current_tool == 'pen'
assert engine2.current_color == '#FF0000'
assert engine2.history.undo_count == 3
print("[5] 综合流程 OK")

print("\n=== 全部通过，无错误 ===")
