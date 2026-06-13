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

import copy
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

import config
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    ColorOperation,
    DeleteSelectedOperation,
    DrawingOperation,
    EraserTool,
    FreehandOperation,
    LineDrawOperation,
    LineTool,
    MoveSelectedOperation,
    OperationType,
    PenTool,
    RecolorSelectedOperation,
    RectangleOperation,
    ScaleSelectedOperation,
    SelectLastOperation,
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
    # 当前选中对象变化
    selection_changed = pyqtSignal(object)
    # 编辑命令失败
    edit_failed = pyqtSignal(str)

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
        self.selected_operation_id: Optional[str] = None

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
            self._revert_edit_operation(op)
            self._refresh_selection_after_history_change()
            self.signals.repaint.emit()
        return op

    def redo(self) -> Optional[DrawingOperation]:
        """重做一步。"""
        op = self.history.redo()
        if op is not None:
            self._apply_edit_after(op)
            self._refresh_selection_after_history_change(preferred_id=self._edit_target_id(op))
            self.signals.repaint.emit()
        return op

    def clear(self) -> None:
        """清空画布：清空历史并通知 UI。"""
        self.history.clear()
        self._set_selected_operation(None)
        self.signals.canvas_cleared.emit()

    # --- 状态查询 ---

    def get_state(self) -> tuple:
        """返回当前 (工具, 颜色, 粗细) 状态。"""
        return self.current_tool, self.current_color, self.current_size

    def get_history(self) -> List[DrawingOperation]:
        """返回当前可重绘的操作历史。"""
        return self.history.history

    def has_edit_target(self) -> bool:
        """是否存在可供语音编辑的图形。"""
        return self._resolve_edit_target() is not None

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
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_line_draw(self, operation: LineDrawOperation) -> None:
        """处理直线绘制。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_rectangle(self, operation: RectangleOperation) -> None:
        """处理矩形绘制。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_circle(self, operation: CircleOperation) -> None:
        """处理圆形绘制。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_triangle(self, operation: TriangleOperation) -> None:
        """处理三角形绘制。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_star(self, operation: StarOperation) -> None:
        """处理星形绘制。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_ai_image(self, operation: AIImageOperation) -> None:
        """处理 AI 生成图片。"""
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

    def _handle_clear(self, operation: DrawingOperation) -> None:
        """处理清空画布。"""
        self.clear()

    def _handle_undo(self, operation: DrawingOperation) -> None:
        """处理语音撤销命令。"""
        self.undo()

    def _handle_redo(self, operation: DrawingOperation) -> None:
        """处理语音重做命令。"""
        self.redo()

    def _handle_select_last(self, operation: SelectLastOperation) -> None:
        """选中最近可编辑图形。"""
        target = self._find_recent_editable_operation()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return
        self._set_selected_operation(target.id)

    def _handle_move_selected(self, operation: MoveSelectedOperation) -> None:
        """移动当前选中图形。"""
        target = self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return

        before = copy.deepcopy(target)
        if operation.target_position is not None:
            dx, dy = self._offset_to_center(target, operation.target_position)
        else:
            dx, dy = operation.dx, operation.dy

        if not self._move_operation(target, dx, dy):
            self.signals.edit_failed.emit("当前对象暂不支持该编辑")
            return

        operation.target_id = target.id
        operation.before = before
        operation.after = copy.deepcopy(target)
        self.history.push(operation)
        self._set_selected_operation(target.id)
        self.signals.repaint.emit()

    def _handle_scale_selected(self, operation: ScaleSelectedOperation) -> None:
        """缩放当前选中图形。"""
        target = self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return

        before = copy.deepcopy(target)
        if not self._scale_operation(target, operation.factor):
            self.signals.edit_failed.emit("当前对象暂不支持该编辑")
            return

        operation.target_id = target.id
        operation.before = before
        operation.after = copy.deepcopy(target)
        self.history.push(operation)
        self._set_selected_operation(target.id)
        self.signals.repaint.emit()

    def _handle_recolor_selected(self, operation: RecolorSelectedOperation) -> None:
        """修改当前选中图形颜色。"""
        target = self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return
        if not hasattr(target, "color"):
            self.signals.edit_failed.emit("当前对象暂不支持该编辑")
            return

        before = copy.deepcopy(target)
        target.color = operation.color
        operation.target_id = target.id
        operation.before = before
        operation.after = copy.deepcopy(target)
        self.history.push(operation)
        self._set_selected_operation(target.id)
        self.signals.repaint.emit()

    def _handle_delete_selected(self, operation: DeleteSelectedOperation) -> None:
        """删除当前选中图形。"""
        target = self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return

        removed = self._remove_operation_from_history(target.id)
        if removed is None:
            self.signals.edit_failed.emit("当前对象暂不支持该编辑")
            return

        deleted_operation, deleted_index = removed
        operation.target_id = target.id
        operation.deleted_operation = copy.deepcopy(deleted_operation)
        operation.deleted_index = deleted_index
        self.history.push(operation)
        self._refresh_selection_after_history_change()
        self.signals.repaint.emit()

    def _emit_state_changed(self) -> None:
        """发出状态变更信号。"""
        self.signals.state_changed.emit(
            self.current_tool,
            self.current_color,
            self.current_size,
        )

    def _set_selected_operation(self, operation_id: Optional[str]) -> None:
        """更新当前选中对象并通知 UI。"""
        self.selected_operation_id = operation_id
        self.signals.selection_changed.emit(operation_id)

    def _resolve_edit_target(self) -> Optional[DrawingOperation]:
        """返回当前选中图形，没有选中时回退到最近图形。"""
        if self.selected_operation_id:
            target = self._find_operation_by_id(self.selected_operation_id)
            if self._is_editable_operation(target):
                return target
        return self._find_recent_editable_operation()

    def _find_operation_by_id(self, operation_id: str) -> Optional[DrawingOperation]:
        for op in self.history.history:
            if op.id == operation_id:
                return op
        return None

    def _find_recent_editable_operation(self) -> Optional[DrawingOperation]:
        for op in reversed(self.history.history):
            if self._is_editable_operation(op):
                return op
        return None

    def _remove_operation_from_history(self, operation_id: str) -> Optional[tuple]:
        stack = self.history._undo_stack
        for index, op in enumerate(stack):
            if op.id == operation_id:
                return stack.pop(index), index
        return None

    def _insert_operation_into_history(self, operation: DrawingOperation, index: int) -> None:
        stack = self.history._undo_stack
        safe_index = max(0, min(index, len(stack)))
        stack.insert(safe_index, operation)

    def _refresh_selection_after_history_change(self, preferred_id: Optional[str] = None) -> None:
        if preferred_id:
            preferred = self._find_operation_by_id(preferred_id)
            if self._is_editable_operation(preferred):
                self._set_selected_operation(preferred_id)
                return
        target = self._find_recent_editable_operation()
        self._set_selected_operation(target.id if target else None)

    def _is_editable_operation(self, operation: Optional[DrawingOperation]) -> bool:
        return isinstance(operation, (
            AIImageOperation,
            CircleOperation,
            FreehandOperation,
            LineDrawOperation,
            RectangleOperation,
            StarOperation,
            TriangleOperation,
        ))

    def _move_operation(self, operation: DrawingOperation, dx: int, dy: int) -> bool:
        if isinstance(operation, CircleOperation):
            operation.center = self._fit_point((operation.center[0] + dx, operation.center[1] + dy))
        elif isinstance(operation, RectangleOperation):
            operation.top_left = self._fit_point((operation.top_left[0] + dx, operation.top_left[1] + dy))
            operation.bottom_right = self._fit_point((operation.bottom_right[0] + dx, operation.bottom_right[1] + dy))
        elif isinstance(operation, TriangleOperation):
            operation.p1 = self._fit_point((operation.p1[0] + dx, operation.p1[1] + dy))
            operation.p2 = self._fit_point((operation.p2[0] + dx, operation.p2[1] + dy))
            operation.p3 = self._fit_point((operation.p3[0] + dx, operation.p3[1] + dy))
        elif isinstance(operation, StarOperation):
            operation.center = self._fit_point((operation.center[0] + dx, operation.center[1] + dy))
        elif isinstance(operation, LineDrawOperation):
            operation.start = self._fit_point((operation.start[0] + dx, operation.start[1] + dy))
            operation.end = self._fit_point((operation.end[0] + dx, operation.end[1] + dy))
        elif isinstance(operation, FreehandOperation):
            operation.points = [self._fit_point((x + dx, y + dy)) for x, y in operation.points]
        elif isinstance(operation, AIImageOperation):
            operation.position = self._fit_point((operation.position[0] + dx, operation.position[1] + dy))
        else:
            return False
        return True

    def _offset_to_center(self, operation: DrawingOperation, target_center: tuple) -> tuple:
        center = self._operation_center(operation)
        if center is None:
            return 0, 0
        return int(target_center[0] - center[0]), int(target_center[1] - center[1])

    def _operation_center(self, operation: DrawingOperation) -> Optional[tuple]:
        if isinstance(operation, (CircleOperation, StarOperation)):
            return operation.center
        if isinstance(operation, RectangleOperation):
            return (
                (operation.top_left[0] + operation.bottom_right[0]) / 2,
                (operation.top_left[1] + operation.bottom_right[1]) / 2,
            )
        if isinstance(operation, TriangleOperation):
            return (
                (operation.p1[0] + operation.p2[0] + operation.p3[0]) / 3,
                (operation.p1[1] + operation.p2[1] + operation.p3[1]) / 3,
            )
        if isinstance(operation, LineDrawOperation):
            return (
                (operation.start[0] + operation.end[0]) / 2,
                (operation.start[1] + operation.end[1]) / 2,
            )
        if isinstance(operation, FreehandOperation) and operation.points:
            return (
                sum(x for x, _ in operation.points) / len(operation.points),
                sum(y for _, y in operation.points) / len(operation.points),
            )
        if isinstance(operation, AIImageOperation):
            return operation.position
        return None

    def _scale_operation(self, operation: DrawingOperation, factor: float) -> bool:
        factor = max(0.1, min(5.0, factor))
        if isinstance(operation, CircleOperation):
            operation.radius = max(4.0, operation.radius * factor)
        elif isinstance(operation, RectangleOperation):
            cx = (operation.top_left[0] + operation.bottom_right[0]) / 2
            cy = (operation.top_left[1] + operation.bottom_right[1]) / 2
            half_w = max(4, (operation.bottom_right[0] - operation.top_left[0]) * factor / 2)
            half_h = max(4, (operation.bottom_right[1] - operation.top_left[1]) * factor / 2)
            operation.top_left = self._fit_point((int(cx - half_w), int(cy - half_h)))
            operation.bottom_right = self._fit_point((int(cx + half_w), int(cy + half_h)))
        elif isinstance(operation, TriangleOperation):
            cx = (operation.p1[0] + operation.p2[0] + operation.p3[0]) / 3
            cy = (operation.p1[1] + operation.p2[1] + operation.p3[1]) / 3
            operation.p1 = self._scale_point(operation.p1, cx, cy, factor)
            operation.p2 = self._scale_point(operation.p2, cx, cy, factor)
            operation.p3 = self._scale_point(operation.p3, cx, cy, factor)
        elif isinstance(operation, StarOperation):
            operation.outer_radius = max(4.0, operation.outer_radius * factor)
            operation.inner_radius = max(2.0, operation.inner_radius * factor)
        elif isinstance(operation, LineDrawOperation):
            cx = (operation.start[0] + operation.end[0]) / 2
            cy = (operation.start[1] + operation.end[1]) / 2
            operation.start = self._scale_point(operation.start, cx, cy, factor)
            operation.end = self._scale_point(operation.end, cx, cy, factor)
        elif isinstance(operation, FreehandOperation) and operation.points:
            cx = sum(x for x, _ in operation.points) / len(operation.points)
            cy = sum(y for _, y in operation.points) / len(operation.points)
            operation.points = [self._scale_point(point, cx, cy, factor) for point in operation.points]
        else:
            return False
        return True

    def _scale_point(self, point: tuple, cx: float, cy: float, factor: float) -> tuple:
        x, y = point
        return self._fit_point((int(cx + (x - cx) * factor), int(cy + (y - cy) * factor)))

    def _fit_point(self, point: tuple) -> tuple:
        x, y = point
        return (
            max(0, min(self.canvas_width, int(x))),
            max(0, min(self.canvas_height, int(y))),
        )

    def _revert_edit_operation(self, operation: DrawingOperation) -> None:
        if isinstance(operation, DeleteSelectedOperation):
            if operation.deleted_operation is not None:
                self._insert_operation_into_history(
                    copy.deepcopy(operation.deleted_operation),
                    operation.deleted_index,
                )
            return

        before = getattr(operation, "before", None)
        target_id = self._edit_target_id(operation)
        if before is not None and target_id:
            target = self._find_operation_by_id(target_id)
            if target is not None:
                self._copy_operation_state(before, target)

    def _apply_edit_after(self, operation: DrawingOperation) -> None:
        if isinstance(operation, DeleteSelectedOperation):
            if operation.target_id:
                self._remove_operation_from_history(operation.target_id)
            return

        after = getattr(operation, "after", None)
        target_id = self._edit_target_id(operation)
        if after is not None and target_id:
            target = self._find_operation_by_id(target_id)
            if target is not None:
                self._copy_operation_state(after, target)

    def _edit_target_id(self, operation: DrawingOperation) -> Optional[str]:
        target_id = getattr(operation, "target_id", None)
        return target_id if target_id else None

    def _copy_operation_state(self, source: DrawingOperation, target: DrawingOperation) -> None:
        for key, value in vars(source).items():
            setattr(target, key, copy.deepcopy(value))

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
        OperationType.SELECT_LAST: _handle_select_last,
        OperationType.MOVE_SELECTED: _handle_move_selected,
        OperationType.SCALE_SELECTED: _handle_scale_selected,
        OperationType.RECOLOR_SELECTED: _handle_recolor_selected,
        OperationType.DELETE_SELECTED: _handle_delete_selected,
        OperationType.CLEAR: _handle_clear,
        OperationType.UNDO: _handle_undo,
        OperationType.REDO: _handle_redo,
    }
