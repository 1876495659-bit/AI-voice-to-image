"""命令解析器核心（四层流水线）。

将语音识别文本转换为 DrawingOperation 列表。

解析流程:
  Phase 1 — 意图分类：确定是工具/形状/AI/系统/颜色/粗细哪一种
  Phase 2 — 槽位提取：提取颜色名、粗细数字、位置等
  Phase 3 — 多步分解：复杂指令拆为多个操作（"用红色画笔画个圆" → 选颜色+选工具+画圆）
  Phase 4 — 置信度验证：< 阈值则返回 UncertainParse

引用:
- `parser/command_grammar.py` — 预编译正则模式 + 匹配函数
- `parser/color_map.py` — 颜色名 → HEX 映射
- `engine/operations.py` — DrawingOperation 数据类
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

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
    MoveSelectedOperation,
    OperationType,
    PenTool,
    RecolorSelectedOperation,
    PointLocation,
    RectangleOperation,
    ScaleSelectedOperation,
    SelectLastOperation,
    SizeOperation,
    StarOperation,
    ToolOperation,
    TriangleOperation,
)
from parser import color_map
from parser.command_grammar import (
    ANCHOR_SHAPE_PATTERN,
    NUMBER_PATTERN,
    RELATIVE_MOVE_PATTERN,
    SHAPE_PATTERNS,
    is_ai_command,
    is_background_color_command,
    match_color,
    match_shape,
    match_size,
    match_system,
    match_tool,
)


# ---------------------------------------------------------------------------
# 解析结果
# ---------------------------------------------------------------------------

class ParseResultType(Enum):
    SUCCESS = auto()
    UNCERTAIN = auto()  # 置信度不足
    REJECT = auto()     # 听不清 / 无意义


@dataclass
class UncertainParse:
    """置信度不足时的结果。

    Attributes:
        text: 原始语音文本。
        reason: 不确定原因说明。
        confidence: 置信度分数 (0-1)。
    """
    text: str
    reason: str
    confidence: float


@dataclass
class ParseResult:
    """命令解析的最终结果。

    Attributes:
        type: 解析结果类型。
        operations: 成功时生成的操作列表。
        uncertain: 置信度不足时的详情。
        confidence: 解析置信度 (0-1)。
        raw_text: 原始语音文本。
    """

    type: ParseResultType = ParseResultType.SUCCESS
    operations: List[DrawingOperation] = None  # type: ignore[assignment]
    uncertain: Optional[UncertainParse] = None
    confidence: float = 1.0
    raw_text: str = ""

    def __post_init__(self) -> None:
        if self.operations is None:
            self.operations = []

    @property
    def is_success(self) -> bool:
        return self.type == ParseResultType.SUCCESS

    @property
    def is_uncertain(self) -> bool:
        return self.type == ParseResultType.UNCERTAIN


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------

class CommandParser:
    """四层命令解析器。

    Attributes:
        fallback_threshold: 置信度回退阈值，低于此值标记为 UNCERTAIN。
        canvas_width: 画布宽度（用于定位计算）。
        canvas_height: 画布高度（用于定位计算）。
        canvas_operations: 当前画布上的操作列表，用于智能参照物匹配。
    """

    def __init__(self,
                 fallback_threshold: float = config.WHISPER_FALLBACK_THRESHOLD,
                 canvas_width: int = config.CANVAS_DEFAULT_WIDTH,
                 canvas_height: int = config.CANVAS_DEFAULT_HEIGHT) -> None:
        self.fallback_threshold = fallback_threshold
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.canvas_operations: List[DrawingOperation] = []

    def parse(self, text: str, confidence: float = 1.0) -> ParseResult:
        """解析一条语音文本。

        执行四层流水线，返回 ParseResult。

        Args:
            text: 语音识别得到的文本（已做基础清理）。
            confidence: Whisper 置信度分数 (0-1)。

        Returns:
            解析结果。
        """
        text = text.strip()
        if not text:
            return ParseResult(
                type=ParseResultType.REJECT,
                raw_text=text,
                confidence=0.0,
                uncertain=UncertainParse(text, "语音为空", 0.0),
            )

        # Phase 1: 意图分类
        intent = self._classify_intent(text)

        # Phase 2: 槽位提取
        slots = self._extract_slots(text)

        # Phase 3: 多步分解
        operations = self._build_operations(intent, slots, text)

        # Phase 4: 置信度验证
        if confidence < self.fallback_threshold:
            return ParseResult(
                type=ParseResultType.UNCERTAIN,
                operations=operations if operations else [],
                uncertain=UncertainParse(
                    text,
                    f"置信度 {confidence:.2f} 低于阈值 {self.fallback_threshold:.2f}",
                    confidence,
                ),
                confidence=confidence,
                raw_text=text,
            )

        return ParseResult(
            type=ParseResultType.SUCCESS,
            operations=operations,
            confidence=confidence,
            raw_text=text,
        )

    # --- Phase 1: 意图分类 ---

    def _classify_intent(self, text: str) -> str:
        """确定语音意图类别。

        Returns:
            意图键: "tool" / "color" / "size" / "shape" / "system" / "ai" / "unknown"
        """
        # 新增：以已有图形为参照定位 — 最高优先级
        if ANCHOR_SHAPE_PATTERN.search(text):
            return "anchor"

        # 新增：相对位置移动 — 最高优先级（防止"直线"等词被误匹配为工具）
        if RELATIVE_MOVE_PATTERN.search(text):
            return "edit"

        # 背景色设置 — 在 edit 之前检查，避免"换"等词被误匹配
        if is_background_color_command(text):
            return "background"

        # 系统命令要先于 AI/编辑识别，避免“清空画布”被“画布”误解。
        sys_cmd = match_system(text)
        if sys_cmd:
            return "system"

        # AI 生成（最高优先级，因为可能包含"画"字）
        if is_ai_command(text):
            return "ai"

        # 编辑命令
        if self._is_edit_command(text):
            return "edit"

        # 工具
        if match_tool(text):
            return "tool"

        # 形状（包含"画"的关键词）
        if match_shape(text):
            return "shape"

        # 颜色
        if match_color(text):
            return "color"

        # 粗细
        if match_size(text) is not None:
            return "size"

        return "unknown"

    # --- Phase 2: 槽位提取 ---

    def _extract_slots(self, text: str) -> dict:
        """提取结构化槽位。

        Returns:
            槽位字典，可能包含: tool, color, color_hex, size, shape, position
        """
        slots: dict = {}

        tool = match_tool(text)
        if tool:
            slots["tool"] = tool

        size = match_size(text)
        if size is not None:
            slots["size"] = size
        else:
            radius = self._extract_radius_hint(text)
            if radius is not None:
                slots["radius"] = radius

        color_name = match_color(text)
        if not color_name:
            color_name = self._extract_brush_color(text)
        if color_name:
            slots["color"] = color_name
            slots["color_hex"] = color_map.get_color(color_name)

        shape = match_shape(text)
        if shape:
            slots["shape"] = shape

        slots["filled"] = self._extract_fill_style(text)

        return slots

    # --- Phase 3: 多步分解 ---

    def _build_operations(self, intent: str, slots: dict, text: str) -> List[DrawingOperation]:
        """根据意图和槽位构建 DrawingOperation 列表。

        Args:
            intent: 意图分类结果。
            slots: 槽位字典。
            text: 原始文本。

        Returns:
            操作列表。
        """
        ops: List[DrawingOperation] = []

        if intent == "tool":
            ops.extend(self._build_tool_ops(slots))
            # 如果同时有形状，也生成形状操作（组合命令）
            if slots.get("shape"):
                ops.extend(self._build_shape_ops(slots, text))
        elif intent == "color":
            ops.extend(self._build_color_ops(slots))
            if slots.get("shape"):
                ops.extend(self._build_shape_ops(slots, text))
        elif intent == "size":
            ops.extend(self._build_size_ops(slots))
        elif intent == "shape":
            ops.extend(self._build_shape_ops(slots, text))
        elif intent == "system":
            ops.extend(self._build_system_ops(slots, text))
        elif intent == "ai":
            ops.extend(self._build_ai_ops(slots, text))
        elif intent == "anchor":
            ops.extend(self._build_anchor_ops(slots, text))
        elif intent == "edit":
            ops.extend(self._build_edit_ops(slots, text))
        elif intent == "background":
            ops.extend(self._build_background_ops(slots, text))

        # 组合操作：工具+颜色+形状，如"用红色画笔画个圆"
        # 如果同时有 tool + color + shape，额外生成颜色操作
        if "tool" in slots and "color_hex" in slots:
            color_op = ColorOperation(color=slots["color_hex"])
            if color_op not in ops:
                ops.insert(0, color_op)

        return ops

    def _build_tool_ops(self, slots: dict) -> List[DrawingOperation]:
        """生成工具切换操作。"""
        tool = slots.get("tool")
        if tool == "pen":
            return [PenTool()]
        elif tool == "eraser":
            return [EraserTool()]
        elif tool == "line":
            return [LineTool()]
        return []

    def _build_color_ops(self, slots: dict) -> List[DrawingOperation]:
        """生成颜色变更操作。"""
        hex_color = slots.get("color_hex", "#000000")
        return [ColorOperation(color=hex_color)]

    def _build_size_ops(self, slots: dict) -> List[DrawingOperation]:
        """生成粗细变更操作。"""
        size = slots.get("size", 3)
        return [SizeOperation(size=size)]

    def _build_shape_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成形状绘制操作。"""
        shape = slots.get("shape")
        color = slots.get("color_hex", "#000000")
        size = slots.get("size", 3)
        filled = slots.get("filled", True)

        if not shape:
            return []

        # 尝试提取位置信息
        position = self._extract_position(text)

        if shape == "circle":
            radius = float(slots.get("radius", 60))
            center = self._fit_center(
                position if position else (self.canvas_width // 2, self.canvas_height // 2),
                radius,
                radius,
            )
            return [CircleOperation(color=color, size=size, filled=filled, center=center, radius=radius)]

        elif shape == "rectangle":
            half_w, half_h = self._extract_rect_size_hint(text)
            center = self._fit_center(
                position if position else (self.canvas_width // 2, self.canvas_height // 2),
                half_w,
                half_h,
            )
            tl = (center[0] - half_w, center[1] - half_h)
            br = (center[0] + half_w, center[1] + half_h)
            return [RectangleOperation(color=color, size=size, filled=filled, top_left=tl, bottom_right=br)]

        elif shape == "triangle":
            center = position if position else (self.canvas_width // 2, self.canvas_height // 2)
            s = int(slots.get("radius", 60))
            center = self._fit_center(center, s, s)
            p1 = (center[0], center[1] - s)
            p2 = (center[0] - s, center[1] + s // 2)
            p3 = (center[0] + s, center[1] + s // 2)
            return [TriangleOperation(color=color, size=size, filled=filled, p1=p1, p2=p2, p3=p3)]

        elif shape == "star":
            center = position if position else (self.canvas_width // 2, self.canvas_height // 2)
            radius = float(slots.get("radius", 60))
            center = self._fit_center(center, radius, radius)
            return [StarOperation(color=color, size=size, filled=filled, center=center, outer_radius=radius, inner_radius=radius * 0.4)]

        elif shape == "line_draw":
            # 直线：默认中心到右下
            start = position if position else (100, self.canvas_height - 100)
            end = (self.canvas_width - 100, 100)
            return [LineDrawOperation(color=color, size=size, start=start, end=end)]

        elif shape == "freehand":
            return [FreehandOperation(color=color, size=size, points=[(0, 0)])]

        return []

    def _build_system_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成交互系统操作（undo/clear/save等不生成绘图操作）。"""
        cmd = match_system(text)
        if cmd in ("undo", "redo", "clear", "save", "listen_start", "listen_stop"):
            from engine.operations import OperationType
            return [DrawingOperation(op_type=getattr(OperationType, cmd.upper()))]
        return []

    def _build_ai_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成 AI 生成图片操作。"""
        prompt = self._extract_prompt(text)
        position = self._extract_position(text)

        # 检查是否有"附近"/"旁边"
        is_nearby = any(w in text for w in ("附近", "旁边"))

        # 检查数量+对象（批量生成）— 只有数量 > 1 才批量
        qty_animal = self._extract_quantity_and_animal(text)

        if qty_animal and qty_animal[0] > 1:
            qty, animal = qty_animal
            if is_nearby:
                anchor = position if position else (self.canvas_width // 2, self.canvas_height // 2)
                return self._generate_batch_nearby(prompt, animal, qty, anchor)
            else:
                anchor = position if position else (self.canvas_width // 2, self.canvas_height // 2)
                return self._generate_batch_centered(prompt, animal, qty, anchor)

        # 单图模式
        pos = position if position else (self.canvas_width // 2 - 200, self.canvas_height // 2 - 200)
        return [AIImageOperation(prompt=prompt, position=pos)]

    def _extract_quantity_and_animal(self, text: str) -> Optional[tuple]:
        """从文本提取数量和对象关键词。

        例如 "三只灰色小老鼠" → (3, "老鼠")
        返回 (数量, 对象关键词) 或 None。
        """
        qty_map: dict[str, int] = {
            "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "多": 3, "几": 3, "数": 3,
        }

        # 找数量词
        qty = None
        for word, num in qty_map.items():
            if word in text:
                qty = num
                break

        if qty is None:
            return None

        # 找动物/对象关键词（按最长匹配优先）
        animal_keywords = [
            "小老鼠", "猫头鹰", "蝴蝶", "蜻蜓", "蜜蜂", "蚂蚁", "蜘蛛", "螃蟹",
            "海豚", "鲸", "企鹅", "鹦鹉", "松鼠", "熊猫", "兔子", "小兔子",
            "小狗", "小猫", "小鸟", "小鱼", "小花", "小树",
            "猫", "狗", "鼠", "兔", "鸟", "鱼", "星", "花", "树", "草", "人",
            "熊", "狮", "虎", "象", "马", "羊", "牛", "猪", "鸡", "鸭", "鹅",
            "蛙", "蛇", "龟", "虫", "蝶", "蜂", "鲤",
        ]

        animal = None
        for kw in animal_keywords:
            if kw in text:
                animal = kw
                break

        if animal is not None:
            return (qty, animal)
        return None

    def _generate_batch_nearby(
        self, prompt: str, animal: str, qty: int, anchor: tuple,
    ) -> List[DrawingOperation]:
        """在锚点周围环形分布生成 N 个 AI 图像。"""
        ops: List[DrawingOperation] = []
        radius = 180
        for i in range(qty):
            angle_deg = -90 + (360.0 / qty) * i
            rad = math.radians(angle_deg)
            x = int(anchor[0] + radius * math.cos(rad))
            y = int(anchor[1] + radius * math.sin(rad))
            x = max(0, min(self.canvas_width - 100, x))
            y = max(0, min(self.canvas_height - 100, y))
            label = f"另一只{animal}" if i > 0 else f"一只{animal}"
            ops.append(AIImageOperation(prompt=f"{prompt} {label}", position=(x, y)))
        return ops

    def _generate_batch_centered(
        self, prompt: str, animal: str, qty: int, anchor: tuple,
    ) -> List[DrawingOperation]:
        """在画布中央线性排列生成 N 个 AI 图像。"""
        ops: List[DrawingOperation] = []
        spacing = 130
        start_x = anchor[0] - (qty - 1) * spacing // 2
        for i in range(qty):
            x = max(0, min(self.canvas_width - 100, start_x + i * spacing))
            y = max(0, min(self.canvas_height - 100, anchor[1]))
            label = f"另一只{animal}" if i > 0 else f"一只{animal}"
            ops.append(AIImageOperation(prompt=f"{prompt} {label}", position=(x, y)))
        return ops

    def _build_background_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成画布背景色变更操作。"""
        color_name = match_color(text)
        if color_name:
            hex_color = color_map.get_color(color_name)
            return [BackgroundOperation(color=hex_color)]
        return [BackgroundOperation(color="#FFFFFF")]

    def _build_edit_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成当前/最近图形编辑操作。"""
        if any(word in text for word in ("选中", "选择")):
            return [SelectLastOperation()]

        if self._is_delete_selected_command(text):
            return [DeleteSelectedOperation()]

        color_name = match_color(text)
        if color_name and any(word in text for word in ("改", "换", "变")):
            return [RecolorSelectedOperation(color=color_map.get_color(color_name))]

        if any(word in text for word in ("变大", "放大", "大一点", "扩大")):
            return [ScaleSelectedOperation(factor=self._extract_scale_factor(text, 1.15))]

        if any(word in text for word in ("变小", "缩小", "小一点", "缩")):
            return [ScaleSelectedOperation(factor=self._extract_scale_factor(text, 0.85))]

        move = self._extract_move_operation(text)
        if move is not None:
            shape, color = self._extract_target_spec(text)
            move.target_shape = shape
            move.target_color = color
            return [move]

        return []

    def _build_anchor_ops(self, slots: dict, text: str) -> List[DrawingOperation]:
        """生成以已有图形为参照的绘制操作。

        解析 "在圆的正上方画个三角形" → AnchorShapeOperation
        解析 "在兔子下面画一条直线" → AnchorShapeOperation(ref_shape="ai_image")
        """
        ref_shape, ref_color = self._extract_target_spec(text, consider_anchor=True)
        direction = self._extract_anchor_direction(text)
        shape = slots.get("shape")  # 要画的形状

        if not shape or not direction:
            return []

        radius = float(slots.get("radius", 60))
        return [AnchorShapeOperation(
            ref_shape=ref_shape,
            ref_color=ref_color,
            ref_direction=direction,
            shape_type=shape,
            color=slots.get("color_hex", "#000000"),
            size=slots.get("size", 3),
            filled=slots.get("filled", True),
            radius_hint=radius,
        )]

    def _extract_anchor_direction(self, text: str) -> str:
        """从文本提取相对方向。"""
        if "正上" in text:
            return "above"
        if "正下" in text:
            return "below"
        if "里面" in text:
            return "inside"
        # "三角形上" / "圆圈上" / "三角形下" / "圆圈下"（几何形状）
        if re.search(r"[三角圆星矩线形圈](上)", text):
            return "above"
        if re.search(r"[三角圆星矩线形圈](下)", text):
            return "below"
        # 通用方向词（支持"兔子下面"/"乌龟的上面"等，不强制"的"）
        if "下面" in text:
            return "below"
        if "上面" in text:
            return "above"
        if "左边" in text:
            return "left"
        if "右边" in text:
            return "right"
        return ""

    def _is_edit_command(self, text: str) -> bool:
        """判断是否是作用于最近图形的编辑命令。"""
        if RELATIVE_MOVE_PATTERN.search(text):
            return True
        if any(word in text for word in ("选中", "选择")):
            return True
        if self._is_delete_selected_command(text):
            return True
        if self._is_absolute_move_command(text):
            return True
        if any(word in text for word in ("移动", "移一点", "往左", "往右", "往上", "往下", "左移", "右移", "上移", "下移")):
            return True
        if any(word in text for word in ("变大", "变小", "放大", "缩小", "扩大", "小一点", "大一点")):
            return True
        return bool(match_color(text) and any(word in text for word in ("改", "换", "变")))

    def _is_absolute_move_command(self, text: str) -> bool:
        """判断“把它放到右上角/让它到中间”这类绝对定位编辑命令。"""
        if self._extract_position(text) is None:
            return False
        has_move_verb = any(word in text for word in ("移", "移动", "放", "摆", "挪", "拖", "到", "去"))
        has_target = any(word in text for word in ("它", "他", "这个", "图形", "对象", "圆", "圈", "矩形", "方形", "太阳"))
        return has_move_verb and (has_target or any(word in text for word in ("移", "移动", "放", "摆", "挪", "拖")))

    def _is_delete_selected_command(self, text: str) -> bool:
        """判断是否是删除当前/最近图形。"""
        if not any(word in text for word in ("删除", "删掉", "去掉", "移除", "删了", "删")):
            return False
        return any(word in text for word in ("它", "这个", "当前", "最近", "上一个", "图形", "正方形", "方形", "矩形", "圆", "圈", "三角", "星"))

    def _extract_move_operation(self, text: str) -> Optional[MoveSelectedOperation]:
        """从语音文本提取移动操作。"""
        # 新增：相对位置偏移（"在直线的左上方"）
        rel_match = RELATIVE_MOVE_PATTERN.search(text)
        if rel_match:
            pos_word = rel_match.group(1)
            offsets = {
                "左上方": (-40, -40),
                "右上方": (40, -40),
                "左下方": (-40, 40),
                "右下方": (40, 40),
                "左边": (-40, 0),
                "右边": (40, 0),
                "上边": (0, -40),
                "下边": (0, 40),
                "左上": (-40, -40),
                "右上": (40, -40),
                "左下": (-40, 40),
                "右下": (40, 40),
            }
            dx, dy = offsets.get(pos_word, (-20, -20))
            return MoveSelectedOperation(dx=dx, dy=dy)

        position = self._extract_position(text)
        if position and self._is_absolute_move_command(text):
            return MoveSelectedOperation(target_position=position)

        distance = self._extract_number(text, default=40)
        dx, dy = 0, 0
        if any(word in text for word in ("往左", "向左", "左移", "左边")):
            dx = -distance
        elif any(word in text for word in ("往右", "向右", "右移", "右边")):
            dx = distance
        elif any(word in text for word in ("往上", "向上", "上移", "上面")):
            dy = -distance
        elif any(word in text for word in ("往下", "向下", "下移", "下面")):
            dy = distance

        if dx == 0 and dy == 0:
            return None
        return MoveSelectedOperation(dx=dx, dy=dy)

    def _extract_target_spec(self, text: str, consider_anchor: bool = False) -> tuple[str, str]:
        """从文本提取目标图形的形状类型和颜色。

        例如 "蓝色圆圈要在直线的左上方" → ("circle", "蓝")
        例如 "圆圈要在直线的左上方" → ("circle", "")
        例如 "在兔子下面画一条直线" → ("ai_image", "")（参照物是兔子）

        Args:
            text: 语音文本。
            consider_anchor: 在锚点定位场景下，优先匹配动物/对象名作为参照物。

        Returns:
            (shape_key, color_name) 或 ("", "") 如果无法识别
        """
        color = ""
        shape = ""
        first_pos = len(text)  # 追踪最早匹配的位置

        # 匹配颜色名
        color_m = match_color(text)
        if color_m:
            color = color_m

        if consider_anchor:
            # 锚点场景：在"画"字之前优先匹配 AI 图像关键词作为参照物
            # 比如 "在兔子下面画一条直线" → 参照物=兔子 (ai_image)
            draw_idx = text.find("画")
            prefix = text[:draw_idx] if draw_idx >= 0 else text
            ai_keyword = self._extract_ai_anchor_keyword(prefix)
            if ai_keyword:
                return ("ai_image", color)
            # AI 关键词没匹配到，回退到几何形状匹配
            # 比如 "在圆的正上方画个三角形" → 参照物=圆 (circle)
            loose_shapes: dict[str, Pattern[str]] = {
                "circle": re.compile(r"(圆|圆形|圈圈|圆圈)", re.IGNORECASE),
                "rectangle": re.compile(r"(矩形|方形|正方|长方形|方框)", re.IGNORECASE),
                "triangle": re.compile(r"(三角|三角形)", re.IGNORECASE),
                "star": re.compile(r"(星|星星|五角星)", re.IGNORECASE),
                "line_draw": re.compile(r"(直线|线条)", re.IGNORECASE),
                "freehand": re.compile(r"(手绘|随便画)", re.IGNORECASE),
            }
            for shape_key, pattern in loose_shapes.items():
                m = pattern.search(prefix)
                if m and m.start() < first_pos:
                    first_pos = m.start()
                    shape = shape_key
        else:
            # 常规场景：匹配形状名——使用宽松模式（不需要"画"字），取最早出现的匹配
            loose_shapes: dict[str, Pattern[str]] = {
                "circle": re.compile(r"(圆|圆形|圈圈|圆圈)", re.IGNORECASE),
                "rectangle": re.compile(r"(矩形|方形|正方|长方形|方框)", re.IGNORECASE),
                "triangle": re.compile(r"(三角|三角形)", re.IGNORECASE),
                "star": re.compile(r"(星|星星|五角星)", re.IGNORECASE),
                "line_draw": re.compile(r"(直线|线条)", re.IGNORECASE),
                "freehand": re.compile(r"(手绘|随便画)", re.IGNORECASE),
            }
            for shape_key, pattern in loose_shapes.items():
                m = pattern.search(text)
                if m and m.start() < first_pos:
                    first_pos = m.start()
                    shape = shape_key

            # 如果没匹配到几何形状，尝试匹配 AI 图像（通过动物/对象关键词）
            if not shape:
                ai_keyword = self._extract_ai_anchor_keyword(text)
                if ai_keyword:
                    return ("ai_image", color)

        return (shape, color)

    def update_canvas_operations(self, operations: List[DrawingOperation]) -> None:
        """同步当前画布上的操作列表，供智能参照物匹配使用。

        在每次解析前调用，parser 会根据画布中已有的 AI 图像 prompt
        推断用户提到的实体名称。
        """
        self.canvas_operations = list(operations)

    def _extract_ai_anchor_keyword(self, text: str) -> str:
        """从文本中提取 AI 图像的参照关键词。

        策略：优先查询画布中已有的 AI 图像 prompt，
        匹配用户提到的动物/对象名。画布中没有的实体不回退到硬编码列表，
        因为用户不会引用画布上不存在的物体。

        例如 "乌龟" 在文本中出现 → 查画布里有没有 prompt 含"乌龟"的 AI 图像
        返回最长匹配的关键词或空字符串。
        """
        # 1. 从画布中收集所有 AI 图像的 prompt 关键词
        canvas_keywords: dict[str, int] = {}
        for op in self.canvas_operations:
            prompt = getattr(op, "prompt", "")
            if not prompt:
                continue
            # 从 prompt 中提取有意义的中文词（去掉英文和修饰词）
            chinese_chars = re.findall(r'[一-鿿]', prompt)
            if not chinese_chars:
                continue
            ch_text = "".join(chinese_chars)
            # 从 prompt 中提取动物/对象关键词
            for kw in self._CANVAS_AI_KEYWORDS:
                if kw in ch_text:
                    if kw not in canvas_keywords:
                        canvas_keywords[kw] = len(kw)  # 最长匹配优先

        # 2. 如果画布中有已知实体，只在这些实体中匹配
        if canvas_keywords:
            # 按长度降序，优先最长匹配
            for kw in sorted(canvas_keywords, key=lambda k: -len(k)):
                if kw in text:
                    return kw
            return ""

        # 3. 画布中没有 AI 图像，回退到通用关键词匹配（兜底）
        for kw in self._CANVAS_AI_KEYWORDS:
            if kw in text:
                return kw
        return ""

    # 通用动物/对象关键词（画布为空时的兜底）
    _CANVAS_AI_KEYWORDS: tuple[str, ...] = (
        "小老鼠", "猫头鹰", "蝴蝶", "蜻蜓", "蜜蜂", "蚂蚁", "蜘蛛", "螃蟹",
        "海豚", "鲸", "企鹅", "鹦鹉", "松鼠", "熊猫", "兔子", "小兔子",
        "小狗", "小猫", "小鸟", "小鱼", "小花", "小树",
        "小老鼠",
        "猫", "狗", "鼠", "兔", "鸟", "鱼", "星", "花", "树", "草", "人",
        "熊", "狮", "虎", "象", "马", "羊", "牛", "猪", "鸡", "鸭", "鹅",
        "蛙", "蛇", "龟", "乌龟", "虫", "蝶", "蜂", "鲤", "风景", "图案",
        "动物", "植物", "人物", "场景", "卡通", "房子", "房屋",
        "建筑", "城市", "乡村", "海洋", "森林", "龙", "凤",
    )

    def _extract_brush_color(self, text: str) -> str:
        """理解“红笔/蓝笔/黄笔”这类口语颜色。"""
        for color_name in sorted(color_map.COLOR_MAP, key=len, reverse=True):
            if f"{color_name}笔" in text or f"{color_name}画笔" in text:
                return color_name
        return ""

    def _extract_scale_factor(self, text: str, default: float) -> float:
        """提取缩放比例，没有数字时使用默认步进。"""
        number = self._extract_number(text, default=0)
        if "%" in text and number > 0:
            amount = number / 100
            return 1 + amount if default >= 1 else max(0.1, 1 - amount)
        return default

    def _extract_number(self, text: str, default: int) -> int:
        match = NUMBER_PATTERN.search(text)
        if not match:
            return default
        return max(1, int(match.group(1)))

    # --- 辅助方法 ---

    def _extract_position(self, text: str) -> Optional[tuple]:
        """从文本中提取位置关键字，计算画布坐标。

        Returns:
            (x, y) 坐标或 None。
        """
        pos_map = {
            "center": (self.canvas_width // 2, self.canvas_height // 2),
            "中间": (self.canvas_width // 2, self.canvas_height // 2),
            "正中": (self.canvas_width // 2, self.canvas_height // 2),
            "当中": (self.canvas_width // 2, self.canvas_height // 2),
            "top_left": (40, 40),
            "左上角": (40, 40),
            "左上": (40, 40),
            "顶左": (40, 40),
            "top_right": (self.canvas_width - 40, 40),
            "右上角": (self.canvas_width - 40, 40),
            "右上": (self.canvas_width - 40, 40),
            "顶右": (self.canvas_width - 40, 40),
            "bottom_left": (40, self.canvas_height - 40),
            "左下角": (40, self.canvas_height - 40),
            "左下": (40, self.canvas_height - 40),
            "底左": (40, self.canvas_height - 40),
            "bottom_right": (self.canvas_width - 40, self.canvas_height - 40),
            "右下角": (self.canvas_width - 40, self.canvas_height - 40),
            "右下": (self.canvas_width - 40, self.canvas_height - 40),
            "底右": (self.canvas_width - 40, self.canvas_height - 40),
            "mid_top": (self.canvas_width // 2, 40),
            "上中": (self.canvas_width // 2, 40),
            "顶上中": (self.canvas_width // 2, 40),
            "mid_bottom": (self.canvas_width // 2, self.canvas_height - 40),
            "下中": (self.canvas_width // 2, self.canvas_height - 40),
            "底中": (self.canvas_width // 2, self.canvas_height - 40),
            "mid_left": (40, self.canvas_height // 2),
            "左中": (40, self.canvas_height // 2),
            "左正中": (40, self.canvas_height // 2),
            "mid_right": (self.canvas_width - 40, self.canvas_height // 2),
            "右中": (self.canvas_width - 40, self.canvas_height // 2),
            "右正中": (self.canvas_width - 40, self.canvas_height // 2),
            # 简单方位
            "左边": (40, self.canvas_height // 2),
            "右侧": (self.canvas_width - 40, self.canvas_height // 2),
            "顶部": (self.canvas_width // 2, 40),
            "底部": (self.canvas_width // 2, self.canvas_height - 40),
            "上边": (self.canvas_width // 2, 40),
            "下边": (self.canvas_width // 2, self.canvas_height - 40),
            "左边": (40, self.canvas_height // 2),
            "右边": (self.canvas_width - 40, self.canvas_height // 2),
        }

        for key, coord in pos_map.items():
            if key in text:
                return coord
        return None

    def _extract_fill_style(self, text: str) -> bool:
        """提取空心/实心语义。"""
        if any(word in text for word in ("空心", "不填充", "无填充", "轮廓", "描边")):
            return False
        return True

    def _extract_radius_hint(self, text: str) -> Optional[int]:
        """从大小描述中推断形状半径。"""
        if any(word in text for word in ("很大", "超大", "巨大")):
            return 110
        if any(word in text for word in ("大一点", "大圆", "大的", "大号", "大")):
            return 90
        if any(word in text for word in ("很小", "小一点", "小圆", "小的", "小号", "小")):
            return 36
        return None

    def _extract_rect_size_hint(self, text: str) -> tuple[int, int]:
        """从大小描述中推断矩形半宽高。"""
        radius = self._extract_radius_hint(text)
        if radius is None:
            return 50, 40
        return radius, max(30, int(radius * 0.75))

    def _fit_center(self, center: tuple, half_w: float, half_h: float) -> tuple:
        """将中心点夹在画布内，避免边角形状被裁切。"""
        x, y = center
        x = max(int(half_w), min(self.canvas_width - int(half_w), int(x)))
        y = max(int(half_h), min(self.canvas_height - int(half_h), int(y)))
        return x, y

    def _extract_prompt(self, text: str) -> str:
        """从 AI 生成命令中提取提示词。

        去掉各种口语化动词前缀，保留核心描述。
        支持多种口语表达方式：
          "画一只小猫" → "小猫"
          "帮我画一只小猫" → "小猫"
          "生成一幅风景画" → "风景"
          "来一张小猫图" → "小猫"
          "我想要一只小狗" → "小狗"
          "能不能画个猫" → "猫"
        """
        # 最外层口语前缀（含"帮"/"想"/"要"/"能"等）
        outer_prefixes = [
            "帮我画", "帮我生成", "帮我把", "帮我做一个",
            "我想画", "我想生成", "我想要", "我想画一个",
            "能不能画", "能不能生成", "能不能帮我画",
            "给我画", "给我生成", "给我画一个",
            "帮我画一个", "帮我画一只", "帮我画一只",
            "帮我画一只", "帮我画一条", "帮我画一幅",
            "帮我画一张", "帮我画个",
            "我想要画", "我想要画一个", "我想要画一只",
            "我想要生成", "我想要画一个",
            "给我画只", "给我画个", "给我画一只",
            "给我画一个", "给我画一条", "给我画一幅",
            "给我画一张", "给我画个",
            "帮我画一只", "帮我画一个", "帮我画一幅",
            "帮我画一张", "帮我画条",
        ]
        prompt = text
        for prefix in outer_prefixes:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break

        # 内层动词前缀
        inner_prefixes = [
            "画一个", "画一只", "画一幅", "画一张", "画一条", "画头",
            "画个", "画幅", "画张", "画条",
            "生成一个", "生成一只", "生成一幅", "生成一张", "生成一条",
            "做一个", "做一个", "做一只", "做一幅", "做一张",
            "来一个", "来一只", "来一幅", "来一张", "来一条",
            "来一个", "来个", "来只", "来幅", "来张",
            "画一", "生成一", "做一", "来一",
            "画", "生成", "创建", "做", "来",
        ]
        for prefix in inner_prefixes:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break

        # 清理末尾标点
        prompt = prompt.rstrip("。,.！？!?,")
        return prompt if prompt else text

    # --- 静默操作类型（不生成绘图操作） ---

    @staticmethod
    def _is_silent_command(text: str) -> bool:
        """检查是否是静默系统命令（不产生绘图操作）。"""
        sys_cmd = match_system(text)
        return sys_cmd in ("listen_start", "listen_stop")
