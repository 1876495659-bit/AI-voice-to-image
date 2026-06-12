"""绘图执行引擎。

连接命令解析器与画布渲染之间的桥梁：
- 接收命令解析器输出的 DrawingOperation
- 将其压入撤销历史
- 向 UI 层发出信号，触发画布重绘

引用:
- `config.py` — MAX_UNDO_HISTORY、CANVAS_DEFAULT_WIDTH/HEIGHT
- `engine/operations.py` — DrawingOperation 数据类
- `engine/undo_history.py` — UndoHistory 栈式历史管理
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

import config
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    ColorOperation,
    DrawingOperation,
    EraserTool,
    FreehandOperation,
    LineDrawOperation,
    LineTool,
    OperationType,
    PenTool,
    RectangleOperation,
    SizeOperation,
    StarOperation,
    ToolOperation,
    TriangleOperation,
)
from engine.undo_history import UndoHistory


# ---------------------------------------------------------------------------
# 引擎信号
# ---------------------------------------------------------------------------

class DrawingEngineSignals(QObject):
    """引擎向 UI 层发出的信号。"""

    # 有新操作需要渲染
    operation_added = pyqtSignal(DrawingOperation)
    # 画布被清空
    canvas_cleared = pyqtSignal()
    # 状态变更（当前工具/颜色/粗细）
    state_changed = pyqtSignal(str, str, int)  # tool, color, size
    # 撤销/重做后需要重绘
    repaint = pyqtSignal()

    def get_history(self):
        """返回当前历史中的所有操作（供 canvas 重绘使用）。"""
        return self.history.history


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------

class DrawingEngine:
    """绘图执行引擎。

    维护当前绘图状态（工具、颜色、粗细），管理撤销历史，
    向 UI 层发出重绘信号。

    Attributes:
        signals: 信号对象，用于与 PyQt UI 通信。
        history: 撤销/重做历史管理器。
        current_tool: 当前工具名称（"pen" / "eraser" / "line"）。
        current_color: 当前颜色 HEX 字符串。
        current_size: 当前笔刷粗细（像素）。
        canvas_width: 画布宽度。
        canvas_height: 画布高度。
    """

    def __init__(self, canvas_width: int = config.CANVAS_DEFAULT_WIDTH,
                 canvas_height: int = config.CANVAS_DEFAULT_HEIGHT) -> None:
        self.signals = DrawingEngineSignals()
        self.history = UndoHistory(max_size=config.MAX_UNDO_HISTORY)

        self.current_tool: str = "pen"
        self.current_color: str = "#000000"
        self.current_size: int = 3

        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

    # --- 核心操作 ---

    def execute(self, operation: DrawingOperation) -> None:
        """执行一个绘图操作。

        根据操作类型分发到具体处理方法，并将结果压入撤销历史。
        不执行绘制本身（绘制由 UI 层的 canvas_widget 完成）。

        Args:
            operation: 要执行的绘图操作。
        """
        handler = self._handlers.get(operation.op_type)
        if handler is not None:
            handler(self, operation)
        else:
            # 未知操作类型也压入历史（避免历史丢失）
            self.history.push(operation)

    def execute_multiple(self, operations: List[DrawingOperation]) -> None:
        """批量执行操作。

        Args:
            operations: 操作列表。
        """
        for op in operations:
            self.execute(op)

    # --- 撤销/重做 ---

    def undo(self) -> Optional[DrawingOperation]:
        """撤销一步。"""
        op = self.history.undo()
        if op is not None:
            self.signals.repaint.emit()
        return op

    def redo(self) -> Optional[DrawingOperation]:
        """重做一步。"""
        op = self.history.redo()
        if op is not None:
            self.signals.repaint.emit()
        return op

    def clear(self) -> None:
        """清空画布：清空历史并通知 UI。"""
        self.history.clear()
        self.signals.canvas_cleared.emit()

    # --- 状态查询 ---

    def get_state(self) -> tuple:
        """返回当前 (工具, 颜色, 粗细) 状态。"""
        return self.current_tool, self.current_color, self.current_size

    # --- 私有分发 ---

    def _handle_tool(self, operation: ToolOperation) -> None:
        """处理工具切换操作。"""
        if isinstance(operation, PenTool):
            self.current_tool = "pen"
        elif isinstance(operation, EraserTool):
            self.current_tool = "eraser"
        elif isinstance(operation, LineTool):
            self.current_tool = "line"

        self.history.push(operation)
        self._emit_state_changed()

    def _handle_color(self, operation: ColorOperation) -> None:
        """处理颜色变更操作。"""
        self.current_color = operation.color
        self.history.push(operation)
        self._emit_state_changed()

    def _handle_size(self, operation: SizeOperation) -> None:
        """处理粗细变更操作。"""
        self.current_size = operation.size
        self.history.push(operation)
        self._emit_state_changed()

    def _handle_freehand(self, operation: FreehandOperation) -> None:
        """处理自由手绘。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_line_draw(self, operation: LineDrawOperation) -> None:
        """处理直线绘制。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_rectangle(self, operation: RectangleOperation) -> None:
        """处理矩形绘制。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_circle(self, operation: CircleOperation) -> None:
        """处理圆形绘制。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_triangle(self, operation: TriangleOperation) -> None:
        """处理三角形绘制。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_star(self, operation: StarOperation) -> None:
        """处理星形绘制。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_ai_image(self, operation: AIImageOperation) -> None:
        """处理 AI 生成图片。"""
        self.history.push(operation)
        self.signals.operation_added.emit(operation)

    def _handle_clear(self, operation: DrawingOperation) -> None:
        """处理清空画布。"""
        self.clear()

    def _emit_state_changed(self) -> None:
        """发出状态变更信号。"""
        self.signals.state_changed.emit(
            self.current_tool,
            self.current_color,
            self.current_size,
        )

    # 操作类型 → 处理函数 映射表
    _handlers = {
        OperationType.PEN: _handle_tool,
        OperationType.ERASER: _handle_tool,
        OperationType.LINE: _handle_tool,
        OperationType.COLOR: _handle_color,
        OperationType.SIZE: _handle_size,
        OperationType.FREEHAND: _handle_freehand,
        OperationType.LINE_DRAW: _handle_line_draw,
        OperationType.RECTANGLE: _handle_rectangle,
        OperationType.CIRCLE: _handle_circle,
        OperationType.TRIANGLE: _handle_triangle,
        OperationType.STAR: _handle_star,
        OperationType.AI_IMAGE: _handle_ai_image,
        OperationType.CLEAR: _handle_clear,
    }
