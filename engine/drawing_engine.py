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
import logging
import threading
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

import config
from engine.operations import (
    AIImageOperation,
    AnchorShapeOperation,
    BackgroundOperation,
    CircleOperation,
    ColorOperation,
    DeleteSelectedOperation,
    DrawingOperation,
    EraserTool,
    FreehandOperation,
    LineDrawOperation,
    LineTool,
    LabelSelectedOperation,
    MoveSelectedOperation,
    OperationType,
    PenTool,
    RecolorSelectedOperation,
    RectangleOperation,
    ScaleSelectedOperation,
    SelectLastOperation,
    SizeOperation,
    StarOperation,
    StrokeGroupOperation,
    ToolOperation,
    TriangleOperation,
)
from engine.undo_history import UndoHistory

logger = logging.getLogger(__name__)


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
    # 背景色变更
    background_changed = pyqtSignal(str)
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
        self.background_color: str = "#FFFFFF"

        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.selected_operation_id: Optional[str] = None

        # Agnes AI 生图服务
        from ai.agnes_service import AgnesImageService
        self.ai_service = AgnesImageService()

        # I2I 状态：累计提示词 + 上一轮图片
        self._i2i_prompt_history: List[str] = []
        self._i2i_current_image_bytes: Optional[bytes] = None

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

    def execute_i2i(self, prompt_delta: str) -> bool:
        """兼容旧入口：已有画布时按整幅画布继续迭代。"""
        if not self._i2i_current_image_bytes:
            logger.warning("I2I: 没有上一轮图片，无法执行图生图")
            return False
        return self.execute_canvas_i2i(prompt_delta)

    def execute_canvas_i2i(self, prompt_delta: str) -> bool:
        """让模型把整张白布当作一幅画逐步生成/修改。

        首次调用走文生图；后续调用把上一轮整幅画布图片作为输入，
        要求模型在原图不变的基础上只完成用户新增的这一步。
        每次结果都作为一个 full_canvas 操作进入历史，以支持撤销到任意创作步骤。
        """
        prompt_delta = prompt_delta.strip()
        if not prompt_delta:
            return False

        is_first_step = self._i2i_current_image_bytes is None
        prompt = self._build_canvas_i2i_prompt(prompt_delta, is_first_step)

        if is_first_step:
            image_bytes = self.ai_service.generate_image(prompt)
        else:
            image_bytes = self.ai_service.extend_image(
                self._i2i_current_image_bytes or b"", prompt,
            )

        if not image_bytes:
            logger.error("整幅画布 AI 生成失败")
            self.signals.edit_failed.emit("AI 生成失败，请稍后重试")
            return False

        self._i2i_prompt_history.append(prompt_delta)
        self._i2i_current_image_bytes = image_bytes

        op = AIImageOperation(
            prompt=prompt_delta,
            image_bytes=image_bytes,
            position=(0, 0),
            full_canvas=True,
        )
        op.semantic_label = "整幅画"
        self.history.push(op)
        self._set_selected_operation(None)
        self.signals.operation_added.emit(op)
        self.signals.repaint.emit()
        return True

    def _build_canvas_i2i_prompt(self, prompt_delta: str, is_first_step: bool) -> str:
        style = (
            "单色黑色简笔画线稿，干净白色背景，像用户用同一支黑色画笔画在同一张白纸上，"
            "不要照片风格，不要彩色填充，不要方形贴图边框，不要生成独立小图片。"
        )
        if is_first_step:
            return f"{style} 在整张空白画布中按照用户要求创作第一步：{prompt_delta}"

        previous = "；".join(self._i2i_prompt_history)
        return (
            f"{style} 这是逐步绘画的下一步。已有画面步骤：{previous}。"
            f"请保持原有画面、构图、比例和位置不变，只根据用户的新要求自然地补画或修改：{prompt_delta}。"
            "新增内容必须融入整幅画，例如树上的苹果应长在树冠或树枝上，河里的鱼应位于河流内部。"
        )

    def is_i2i_mode(self) -> bool:
        """是否处于 I2I 迭代模式（已生成过第一张图）。"""
        return self._i2i_current_image_bytes is not None

    # --- 撤销/重做 ---

    def undo(self) -> Optional[DrawingOperation]:
        """撤销一步。"""
        op = self.history.undo()
        if op is not None:
            self._revert_edit_operation(op)
            self._refresh_selection_after_history_change()
            self._refresh_i2i_state_from_history()
            self.signals.repaint.emit()
        return op

    def redo(self) -> Optional[DrawingOperation]:
        """重做一步。"""
        op = self.history.redo()
        if op is not None:
            self._apply_edit_after(op)
            self._refresh_selection_after_history_change(preferred_id=self._edit_target_id(op))
            self._refresh_i2i_state_from_history()
            self.signals.repaint.emit()
        return op

    def clear(self) -> None:
        """清空画布：清空历史并重置 I2I 状态。"""
        self.history.clear()
        self._i2i_current_image_bytes = None
        self._i2i_prompt_history.clear()
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
        """处理 AI 生成图片。

        首次生成成功后，进入 I2I 模式，保存图片用于后续图生图。
        """
        self.history.push(operation)
        self._set_selected_operation(operation.id)
        self.signals.operation_added.emit(operation)

        # 同组去重：检查同 group_id 的操作是否已有 image_bytes
        group_id = getattr(operation, "group_id", "")
        if group_id:
            for prev_op in reversed(self.history.history[:-1]):
                if getattr(prev_op, "group_id", "") == group_id and getattr(prev_op, "image_bytes", b""):
                    # 已有生成的图片，直接复制
                    operation.image_bytes = prev_op.image_bytes
                    from ai.stroke_extractor import StrokeExtractor
                    stroke_op = StrokeExtractor().extract(
                        operation.image_bytes,
                        position=operation.position,
                        label=operation.semantic_label or operation.prompt,
                        color=operation.color,
                        size=operation.size,
                    )
                    stroke_op.id = operation.id
                    self._replace_operation_in_history(operation.id, stroke_op)
                    self._set_selected_operation(stroke_op.id)
                    self.signals.repaint.emit()
                    return

        # 异步调用 Agnes 生图
        threading.Thread(
            target=self._generate_ai_image,
            args=(operation,),
            daemon=True,
        ).start()

    def _generate_ai_image(self, operation: AIImageOperation) -> None:
        """后台线程调用 Agnes 生成图片。

        成功后更新 operation.image_bytes 并重绘画布。
        首次生成成功后，进入 I2I 模式保存图片。
        如果 operation 属于一组（group_id），还更新同组其他操作。
        失败时通过 edit_failed 信号通知 UI。
        """
        image_bytes = self.ai_service.generate_image(operation.prompt)
        if image_bytes:
            if getattr(operation, "full_canvas", False):
                operation.image_bytes = image_bytes
                self._i2i_current_image_bytes = image_bytes
                self._i2i_prompt_history.append(operation.prompt)
                self._set_selected_operation(None)
                self.signals.repaint.emit()
                return

            # 首次生成成功 → 进入 I2I 模式
            if not self._i2i_current_image_bytes:
                self._i2i_current_image_bytes = image_bytes
                self._i2i_prompt_history = [operation.prompt]
                logger.info("I2I 模式已激活")

            from ai.stroke_extractor import StrokeExtractor

            stroke_op = StrokeExtractor().extract(
                image_bytes,
                position=operation.position,
                label=operation.semantic_label or operation.prompt,
                color=operation.color,
                size=operation.size,
            )
            stroke_op.id = operation.id
            self._replace_operation_in_history(operation.id, stroke_op)
            self._set_selected_operation(stroke_op.id)

            # 更新同组其他操作
            group_id = getattr(operation, "group_id", "")
            if group_id:
                for prev_op in self.history.history:
                    oid = getattr(prev_op, "id", "")
                    if oid != operation.id and getattr(prev_op, "group_id", "") == group_id:
                        prev_op.image_bytes = image_bytes

            self.signals.repaint.emit()
        else:
            # 在主线程中发出错误信号
            self.signals.edit_failed.emit("AI 生成失败，请稍后重试")

    def _handle_clear(self, operation: DrawingOperation) -> None:
        """处理清空画布。"""
        self.clear()

    def _handle_background(self, operation: DrawingOperation) -> None:
        """处理背景色变更。"""
        self.background_color = operation.color
        self.history.push(operation)
        self.signals.background_changed.emit(operation.color)

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
        target = self._resolve_edit_target(
            operation.target_shape, operation.target_color,
        )
        if target is None:
            if operation.target_shape or operation.target_color:
                self.signals.edit_failed.emit("未找到匹配的图形")
            else:
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
        target = self.find_semantic_target(operation.target_label) if operation.target_label else self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return
        if not hasattr(target, "color"):
            self.signals.edit_failed.emit("当前对象暂不支持该编辑")
            return

        before = copy.deepcopy(target)
        target.color = operation.color
        if operation.fill is not None:
            target.filled = operation.fill
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

    def _handle_label_selected(self, operation: LabelSelectedOperation) -> None:
        """给当前选中图形标注语义名称。"""
        target = self._resolve_edit_target()
        if target is None:
            self.signals.edit_failed.emit("没有可编辑的图形，请先画一个图形")
            return

        before = copy.deepcopy(target)
        target.semantic_label = operation.label
        operation.target_id = target.id
        operation.before = before
        operation.after = copy.deepcopy(target)
        self.history.push(operation)
        self._set_selected_operation(target.id)
        self.signals.repaint.emit()

    def _handle_anchor_shape(self, operation: AnchorShapeOperation) -> None:
        """以已有图形为参照绘制新图形。"""
        anchor = self._find_matching_editable_operation(
            operation.ref_shape, operation.ref_color,
        )
        if anchor is None:
            self.signals.edit_failed.emit(f"未找到参照图形：{operation.ref_shape}")
            return

        bbox = self._get_bounding_box(anchor)
        if bbox is None:
            self.signals.edit_failed.emit("无法计算参照物边界")
            return

        pos = self._compute_anchor_position(
            bbox, operation.ref_direction, operation.shape_type, operation.radius_hint,
        )
        if pos is None:
            self.signals.edit_failed.emit("无法计算位置")
            return

        new_op = self._create_shape_at_pos(
            operation.shape_type, pos, operation.color, operation.size,
            operation.filled, operation.radius_hint,
        )
        if new_op:
            self._execute_and_push(new_op)

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

    def _refresh_i2i_state_from_history(self) -> None:
        """从历史中恢复最新的整幅画布图片状态。"""
        self._i2i_prompt_history = [
            op.prompt
            for op in self.history.history
            if isinstance(op, AIImageOperation)
            and getattr(op, "full_canvas", False)
            and getattr(op, "prompt", "")
        ]

        for op in reversed(self.history.history):
            if (
                isinstance(op, AIImageOperation)
                and getattr(op, "full_canvas", False)
                and getattr(op, "image_bytes", b"")
            ):
                self._i2i_current_image_bytes = op.image_bytes
                return

        self._i2i_current_image_bytes = None

    def _resolve_edit_target(
        self, target_shape: str = "", target_color: str = "",
    ) -> Optional[DrawingOperation]:
        """返回目标图形。支持三种匹配方式：
        1. 优先：精确 id 匹配（通过 SelectLastOperation 选中）
        2. 次优：按 target_shape + target_color 从 history 中匹配
        3. 回退：最近可编辑图形
        """
        if self.selected_operation_id:
            target = self._find_operation_by_id(self.selected_operation_id)
            if self._is_editable_operation(target):
                return target

        # 按形状+颜色匹配（从最近到最早）
        if target_shape or target_color:
            target = self._find_matching_editable_operation(target_shape, target_color)
            if target:
                return target

        return self._find_recent_editable_operation()

    def find_semantic_target(self, label: str = "") -> Optional[DrawingOperation]:
        """查找当前或最近的语义对象。"""
        if label:
            for op in reversed(self.history.history):
                semantic_label = getattr(op, "semantic_label", "")
                prompt = getattr(op, "prompt", "")
                if self._is_editable_operation(op) and (
                    semantic_label == label
                    or (semantic_label and (semantic_label in label or label in semantic_label))
                    or (prompt and label in prompt)
                ):
                    return op
        return self._resolve_edit_target()

    def _find_matching_editable_operation(
        self, shape: str, color: str,
    ) -> Optional[DrawingOperation]:
        """从 history 中反向查找匹配 shape+color 的图形。"""
        shape_map = {
            "circle": CircleOperation,
            "line_draw": LineDrawOperation,
            "rectangle": RectangleOperation,
            "triangle": TriangleOperation,
            "star": StarOperation,
            "freehand": FreehandOperation,
        }
        for op in reversed(self.history.history):
            if not self._is_editable_operation(op):
                continue

            # 匹配形状
            if shape == "ai_image":
                if not isinstance(op, AIImageOperation):
                    continue
                # AI 图像按 prompt 中的关键词匹配
                if color:
                    prompt = getattr(op, "prompt", "")
                    if color not in prompt:
                        continue
                # 找到最近一个 AI 图像
                return op
            elif shape and shape in shape_map:
                if not isinstance(op, shape_map[shape]):
                    continue

            # 匹配颜色（仅几何形状）
            if color and shape != "ai_image":
                op_color = getattr(op, "color", "")
                if op_color and not self._color_matches(op_color, color):
                    continue

            return op

        return None

    # --- 参照定位辅助方法 ---

    def _get_bounding_box(self, op: DrawingOperation) -> Optional[dict]:
        """获取可编辑图形的边界框 {cx, cy, top, bottom, left, right}。"""
        if isinstance(op, CircleOperation):
            r = op.radius
            cx, cy = op.center
            return {"cx": cx, "cy": cy, "r": r,
                    "top": cy - r, "bottom": cy + r,
                    "left": cx - r, "right": cx + r}
        elif isinstance(op, RectangleOperation):
            x1, y1 = op.top_left
            x2, y2 = op.bottom_right
            return {"cx": (x1 + x2) / 2, "cy": (y1 + y2) / 2,
                    "top": y1, "bottom": y2, "left": x1, "right": x2}
        elif isinstance(op, TriangleOperation):
            xs = [op.p1[0], op.p2[0], op.p3[0]]
            ys = [op.p1[1], op.p2[1], op.p3[1]]
            cx, cy = sum(xs) / 3, sum(ys) / 3
            return {"cx": cx, "cy": cy,
                    "top": min(ys), "bottom": max(ys),
                    "left": min(xs), "right": max(xs)}
        elif isinstance(op, StarOperation):
            cx, cy = op.center
            r = op.outer_radius
            return {"cx": cx, "cy": cy, "r": r,
                    "top": cy - r, "bottom": cy + r,
                    "left": cx - r, "right": cx + r}
        elif isinstance(op, LineDrawOperation):
            x1, y1 = op.start
            x2, y2 = op.end
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            return {"cx": cx, "cy": cy,
                    "top": min(y1, y2), "bottom": max(y1, y2),
                    "left": min(x1, x2), "right": max(x1, x2)}
        elif isinstance(op, FreehandOperation) and op.points:
            xs = [p[0] for p in op.points]
            ys = [p[1] for p in op.points]
            return {"cx": sum(xs) / len(xs), "cy": sum(ys) / len(ys),
                    "top": min(ys), "bottom": max(ys),
                    "left": min(xs), "right": max(xs)}
        elif isinstance(op, StrokeGroupOperation) and op.strokes:
            points = [point for stroke in op.strokes for point in stroke]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return {"cx": sum(xs) / len(xs), "cy": sum(ys) / len(ys),
                    "top": min(ys), "bottom": max(ys),
                    "left": min(xs), "right": max(xs)}
        elif isinstance(op, AIImageOperation):
            # 默认按 400x400 估算
            x, y = op.position
            return {"cx": x + 200, "cy": y + 200,
                    "top": y, "bottom": y + 400,
                    "left": x, "right": x + 400}
        return None

    def _compute_anchor_position(
        self, bbox: dict, direction: str, shape_type: str, radius: float,
    ) -> Optional[tuple]:
        """根据方向计算新图形中心坐标（紧邻参照物）。"""
        gap = 5
        if direction == "above":
            return (bbox["cx"], bbox["top"] - gap - radius)
        elif direction == "below":
            return (bbox["cx"], bbox["bottom"] + gap + radius)
        elif direction == "left":
            half = radius if shape_type == "circle" else int(radius * 0.7)
            return (bbox["left"] - gap - half, bbox["cy"])
        elif direction == "right":
            half = radius if shape_type == "circle" else int(radius * 0.7)
            return (bbox["right"] + gap + half, bbox["cy"])
        elif direction == "inside":
            return (bbox["cx"], bbox["cy"])
        return None

    def _create_shape_at_pos(
        self, shape_type: str, center: tuple, color: str,
        size: int, filled: bool, radius: float,
    ) -> Optional[DrawingOperation]:
        """在指定位置创建形状操作。"""
        if shape_type == "circle":
            return CircleOperation(color=color, size=size, filled=filled,
                                   center=center, radius=radius)
        elif shape_type == "rectangle":
            half_w, half_h = radius, max(30, int(radius * 0.75))
            tl = (center[0] - half_w, center[1] - half_h)
            br = (center[0] + half_w, center[1] + half_h)
            return RectangleOperation(color=color, size=size, filled=filled,
                                      top_left=tl, bottom_right=br)
        elif shape_type == "triangle":
            s = int(radius)
            p1 = (center[0], center[1] - s)
            p2 = (center[0] - s, center[1] + s // 2)
            p3 = (center[0] + s, center[1] + s // 2)
            return TriangleOperation(color=color, size=size, filled=filled,
                                     p1=p1, p2=p2, p3=p3)
        elif shape_type == "star":
            return StarOperation(color=color, size=size, filled=filled,
                                 center=center, outer_radius=radius,
                                 inner_radius=radius * 0.4)
        elif shape_type == "line_draw":
            return LineDrawOperation(color=color, size=size,
                                     start=center, end=center)
        return None

    def _execute_and_push(self, operation: DrawingOperation) -> None:
        """执行操作并压入历史。"""
        # 先执行
        if hasattr(operation, "center") and isinstance(
            getattr(operation, "center", None), tuple
        ):
            pass  # 位置已设定
        # 压入历史
        self.history.push(operation)
        self.signals.repaint.emit()

    def _find_operation_by_id(self, operation_id: str) -> Optional[DrawingOperation]:
        for op in self.history.history:
            if op.id == operation_id:
                return op
        return None

    def _replace_operation_in_history(self, operation_id: str, replacement: DrawingOperation) -> bool:
        for index, op in enumerate(self.history._undo_stack):
            if op.id == operation_id:
                self.history._undo_stack[index] = replacement
                return True
        return False

    def _color_matches(self, color_hex: str, color_name: str) -> bool:
        """判断 HEX 颜色名是否与中文颜色名匹配。

        通过颜色名称的中文映射（color_map）转换后比较 HEX 值。
        """
        from parser import color_map

        # 如果 color_name 本身就是 HEX
        if color_name.startswith("#"):
            return color_hex.upper() == color_name.upper()

        # 将中文颜色名转为 HEX 后比较
        mapped = color_map.get_color(color_name)
        if mapped:
            return color_hex.upper() == mapped.upper()
        # 回退：近似匹配——检查 HEX 颜色是否属于该中文颜色的常见范围
        return False

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
            StrokeGroupOperation,
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
        elif isinstance(operation, StrokeGroupOperation):
            operation.strokes = [
                [self._fit_point((x + dx, y + dy)) for x, y in stroke]
                for stroke in operation.strokes
            ]
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
        if isinstance(operation, StrokeGroupOperation) and operation.strokes:
            points = [point for stroke in operation.strokes for point in stroke]
            return (
                sum(x for x, _ in points) / len(points),
                sum(y for _, y in points) / len(points),
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
        elif isinstance(operation, StrokeGroupOperation) and operation.strokes:
            points = [point for stroke in operation.strokes for point in stroke]
            cx = sum(x for x, _ in points) / len(points)
            cy = sum(y for _, y in points) / len(points)
            operation.strokes = [
                [self._scale_point(point, cx, cy, factor) for point in stroke]
                for stroke in operation.strokes
            ]
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
        OperationType.LABEL_SELECTED: _handle_label_selected,
        OperationType.ANCHOR_SHAPE: _handle_anchor_shape,
        OperationType.BACKGROUND: _handle_background,
        OperationType.CLEAR: _handle_clear,
        OperationType.UNDO: _handle_undo,
        OperationType.REDO: _handle_redo,
    }
