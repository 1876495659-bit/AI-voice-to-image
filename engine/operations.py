"""绘图操作数据模型。

定义所有绘图操作的数据类，作为撤销/重做、画布渲染、命令解析之间的通用契约。
每个操作包含唯一 ID、类型、参数，仅存储数据而非像素快照。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List


# ---------------------------------------------------------------------------
# 操作类型枚举
# ---------------------------------------------------------------------------

class OperationType(Enum):
    """所有支持的绘图操作类型。"""

    # 工具类（不直接产生图元，但改变当前状态）
    PEN = auto()          # 切换到笔/铅笔工具
    ERASER = auto()       # 切换到橡皮工具
    LINE = auto()         # 切换到线条工具

    # 颜色 / 粗细（状态变更）
    COLOR = auto()
    SIZE = auto()

    # 形状绘制
    FREEHAND = auto()     # 自由手绘
    LINE_DRAW = auto()    # 画直线
    RECTANGLE = auto()    # 画矩形
    CIRCLE = auto()       # 画圆
    TRIANGLE = auto()     # 画三角形
    STAR = auto()         # 画星形

    # AI 生成
    AI_IMAGE = auto()     # AI 生成图片

    # 对象编辑
    SELECT_LAST = auto()        # 选中最近图形
    MOVE_SELECTED = auto()      # 移动当前/最近图形
    SCALE_SELECTED = auto()     # 缩放当前/最近图形
    RECOLOR_SELECTED = auto()   # 修改当前/最近图形颜色
    DELETE_SELECTED = auto()    # 删除当前/最近图形
    LABEL_SELECTED = auto()     # 给当前/最近图形标注语义名称

    # 参照定位绘制
    ANCHOR_SHAPE = auto()       # 以已有图形为参照绘制新图形

    # 操作
    UNDO = auto()
    REDO = auto()
    CLEAR = auto()        # 清空画布
    BACKGROUND = auto()   # 设置画布背景色


# ---------------------------------------------------------------------------
# 定位点（用于"从左下到右上"等相对定位）
# ---------------------------------------------------------------------------

class PointLocation(Enum):
    """画布上的相对定位点。"""

    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    MID_TOP = "mid_top"
    MID_BOTTOM = "mid_bottom"
    MID_LEFT = "mid_left"
    MID_RIGHT = "mid_right"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class DrawingOperation:
    """所有绘图操作的基类。

    Attributes:
        id:       唯一标识符 (UUID)。
        op_type:  操作类型枚举。
        color:    颜色 HEX 字符串（如 "#FF0000"），默认为黑色。
        size:     笔刷粗细（像素），默认为 3。
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    op_type: OperationType = OperationType.PEN
    color: str = "#000000"
    size: int = 3
    filled: bool = True
    semantic_label: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DrawingOperation):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


# --- 工具切换 ---

@dataclass
class ToolOperation(DrawingOperation):
    """切换到某个绘图工具。"""

    op_type: OperationType = field(default=OperationType.PEN, init=False)


@dataclass
class PenTool(DrawingOperation):
    """切换到笔/铅笔工具。"""
    op_type: OperationType = field(default=OperationType.PEN, init=False)


@dataclass
class EraserTool(DrawingOperation):
    """切换到橡皮工具。"""
    op_type: OperationType = field(default=OperationType.ERASER, init=False)


@dataclass
class LineTool(DrawingOperation):
    """切换到线条工具。"""
    op_type: OperationType = field(default=OperationType.LINE, init=False)


# --- 颜色和粗细 ---

@dataclass
class ColorOperation(DrawingOperation):
    """改变当前颜色。"""
    op_type: OperationType = field(default=OperationType.COLOR, init=False)


@dataclass
class SizeOperation(DrawingOperation):
    """改变当前笔刷粗细。"""
    op_type: OperationType = field(default=OperationType.SIZE, init=False)


# --- 图元绘制 ---

@dataclass
class FreehandOperation(DrawingOperation):
    """自由手绘：点序列。

    Attributes:
        points: 绘制路径上的点坐标列表 [(x, y), ...]。
    """

    op_type: OperationType = field(default=OperationType.FREEHAND, init=False)
    points: List[tuple] = field(default_factory=list)


@dataclass
class LineDrawOperation(DrawingOperation):
    """画直线。

    Attributes:
        start: 起点 (x, y)。
        end:   终点 (x, y)。
    """

    op_type: OperationType = field(default=OperationType.LINE_DRAW, init=False)
    start: tuple = field(default=(0, 0))
    end: tuple = field(default=(0, 0))


@dataclass
class RectangleOperation(DrawingOperation):
    """画矩形。

    Attributes:
        top_left: 左上角 (x, y)。
        bottom_right: 右下角 (x, y)。
    """

    op_type: OperationType = field(default=OperationType.RECTANGLE, init=False)
    top_left: tuple = field(default=(0, 0))
    bottom_right: tuple = field(default=(0, 0))


@dataclass
class CircleOperation(DrawingOperation):
    """画圆。

    Attributes:
        center: 圆心 (x, y)。
        radius: 半径（像素）。
    """

    op_type: OperationType = field(default=OperationType.CIRCLE, init=False)
    center: tuple = field(default=(0, 0))
    radius: float = 50.0


@dataclass
class TriangleOperation(DrawingOperation):
    """画三角形。

    Attributes:
        p1: 顶点1 (x, y)。
        p2: 顶点2 (x, y)。
        p3: 顶点3 (x, y)。
    """

    op_type: OperationType = field(default=OperationType.TRIANGLE, init=False)
    p1: tuple = field(default=(0, 0))
    p2: tuple = field(default=(0, 0))
    p3: tuple = field(default=(0, 0))


@dataclass
class StarOperation(DrawingOperation):
    """画五角星。

    Attributes:
        center: 中心 (x, y)。
        outer_radius: 外圆半径。
        inner_radius: 内圆半径。
    """

    op_type: OperationType = field(default=OperationType.STAR, init=False)
    center: tuple = field(default=(0, 0))
    outer_radius: float = 60.0
    inner_radius: float = 24.0


@dataclass
class AIImageOperation(DrawingOperation):
    """AI 生成图片。

    Attributes:
        prompt:      原始提示词。
        image_bytes: 生成的图片二进制数据。
        position:    图片放置位置 (x, y)，左上角锚点。
    """

    op_type: OperationType = field(default=OperationType.AI_IMAGE, init=False)
    prompt: str = ""
    image_bytes: bytes = b""
    position: tuple = field(default=(0, 0))


@dataclass
class SelectLastOperation(DrawingOperation):
    """选中最近可编辑图形。"""

    op_type: OperationType = field(default=OperationType.SELECT_LAST, init=False)


@dataclass
class MoveSelectedOperation(DrawingOperation):
    """移动当前选中图形。"""

    op_type: OperationType = field(default=OperationType.MOVE_SELECTED, init=False)
    dx: int = 0
    dy: int = 0
    target_position: tuple | None = None
    target_id: str = ""
    target_shape: str = ""
    target_color: str = ""
    before: DrawingOperation | None = None
    after: DrawingOperation | None = None


@dataclass
class ScaleSelectedOperation(DrawingOperation):
    """缩放当前选中图形。"""

    op_type: OperationType = field(default=OperationType.SCALE_SELECTED, init=False)
    factor: float = 1.0
    target_id: str = ""
    before: DrawingOperation | None = None
    after: DrawingOperation | None = None


@dataclass
class RecolorSelectedOperation(DrawingOperation):
    """修改当前选中图形颜色。"""

    op_type: OperationType = field(default=OperationType.RECOLOR_SELECTED, init=False)
    target_id: str = ""
    target_label: str = ""
    fill: bool | None = None
    before: DrawingOperation | None = None
    after: DrawingOperation | None = None


@dataclass
class DeleteSelectedOperation(DrawingOperation):
    """删除当前选中图形。"""

    op_type: OperationType = field(default=OperationType.DELETE_SELECTED, init=False)
    target_id: str = ""
    deleted_operation: DrawingOperation | None = None
    deleted_index: int = -1


@dataclass
class LabelSelectedOperation(DrawingOperation):
    """给当前选中图形标注语义名称。"""

    op_type: OperationType = field(default=OperationType.LABEL_SELECTED, init=False)
    label: str = ""
    target_id: str = ""
    before: DrawingOperation | None = None
    after: DrawingOperation | None = None


@dataclass
class BackgroundOperation(DrawingOperation):
    """改变画布背景颜色。

    背景色独立于图元操作，这样已有绘图在改变背景时保持视觉外观不变。

    Attributes:
        color: 背景色 HEX 字符串。
    """

    op_type: OperationType = field(default=OperationType.BACKGROUND, init=False)
    color: str = "#FFFFFF"


# --- 参照定位绘制 ---

@dataclass
class AnchorShapeOperation(DrawingOperation):
    """以已有图形为参照，在指定方向绘制新图形。

    引擎执行时：查找 ref_shape+ref_color 匹配的图形，
    计算其边界框，在 ref_direction 方向紧邻处生成 shape_type 指定的形状。

    Attributes:
        ref_shape:       参照物形状类型，如 "circle"、"triangle"。
        ref_color:       参照物颜色名，如 "蓝色"。
        ref_direction:   相对方向："above"/"below"/"left"/"right"/"inside"。
        shape_type:      要绘制的形状，如 "triangle"、"rectangle"。
        radius_hint:     新图形的大小提示（半径/半宽）。
    """

    op_type: OperationType = field(default=OperationType.ANCHOR_SHAPE, init=False)
    ref_shape: str = ""
    ref_color: str = ""
    ref_direction: str = ""
    shape_type: str = ""
    radius_hint: float = 60.0
