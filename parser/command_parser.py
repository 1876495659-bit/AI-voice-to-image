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
    TriangleOperation,
)
from parser import color_map
from parser.command_grammar import (
    ANCHOR_SHAPE_PATTERN,
    NUMBER_PATTERN,
    RELATIVE_MOVE_PATTERN,
    SHAPE_PATTERNS,
    match_color,
    match_shape,
    match_size,
    match_system,
    match_tool,
    is_ai_command,
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
    """

    def __init__(self,
                 fallback_threshold: float = config.WHISPER_FALLBACK_THRESHOLD,
                 canvas_width: int = config.CANVAS_DEFAULT_WIDTH,
                 canvas_height: int = config.CANVAS_DEFAULT_HEIGHT) -> None:
        self.fallback_threshold = fallback_threshold
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

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

        # AI 生成（最高优先级，因为可能包含"画"字）
        if self._is_edit_command(text):
            return "edit"

        # AI 生成（最高优先级，因为可能包含"画"字）
        if is_ai_command(text):
            return "ai"

        # 系统命令
        sys_cmd = match_system(text)
        if sys_cmd:
            return "system"

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
        # 提取提示词：去掉命令动词部分
        prompt = self._extract_prompt(text)
        position = self._extract_position(text)
        pos = position if position else (self.canvas_width // 2 - 200, self.canvas_height // 2 - 200)
        return [AIImageOperation(prompt=prompt, position=pos)]

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
        """
        ref_shape, ref_color = self._extract_target_spec(text)
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
        # "三角形上" / "圆圈上" / "三角形下" / "圆圈下"
        if re.search(r"[三角圆星矩线形圈](上)", text):
            return "above"
        if re.search(r"[三角圆星矩线形圈](下)", text):
            return "below"
        # "的下面"/"的上面"（带"的"的上下）
        if "上面" in text and "的" in text:
            return "above"
        if "下面" in text and "的" in text:
            return "below"
        # "的左边"/"的右边" 或 "三角形左边"/"三角形右边"（省略"的"）
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
        if any(word in text for word in ("移动", "移一点", "往左", "往右", "往上", "往下", "左移", "右移", "上移", "下移")):
            return True
        if any(word in text for word in ("变大", "变小", "放大", "缩小", "扩大", "小一点", "大一点")):
            return True
        return bool(match_color(text) and any(word in text for word in ("改", "换", "变")))

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
        if position and "移" in text and any(word in text for word in ("到", "至", "去")):
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

    def _extract_target_spec(self, text: str) -> tuple[str, str]:
        """从文本提取目标图形的形状类型和颜色。

        例如 "蓝色圆圈要在直线的左上方" → ("circle", "蓝")
        例如 "圆圈要在直线的左上方" → ("circle", "")

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

        # 匹配形状名——使用宽松模式（不需要"画"字），取最早出现的匹配
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

        return (shape, color)

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

        去掉"生成"、"画"等动词前缀，保留核心描述。
        """
        # 常见前缀
        prefixes = ["生成", "画", "画个", "画幅", "画一张", "画一幅", "画一个",
                     "创建", "做一个", "画一", "来一张", "来一幅"]
        prompt = text
        for prefix in prefixes:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break

        # 如果没有去掉任何东西，尝试去掉"生成"关键词
        if prompt == text:
            # 尝试匹配更复杂的模式
            for pfx in ["生成一幅", "画一幅", "生成一张", "画一张", "生成一个", "画一个"]:
                if prompt.startswith(pfx):
                    prompt = prompt[len(pfx):].strip()
                    break

        return prompt if prompt else text

    # --- 静默操作类型（不生成绘图操作） ---

    @staticmethod
    def _is_silent_command(text: str) -> bool:
        """检查是否是静默系统命令（不产生绘图操作）。"""
        sys_cmd = match_system(text)
        return sys_cmd in ("listen_start", "listen_stop")
