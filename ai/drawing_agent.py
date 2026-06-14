"""语音绘画上下文代理。

把"在大树旁边画一条小河""补充细节"这类上下文语音，
转换成可撤销、可继续编辑的本地画布操作。

代理核心能力:
- 理解画布整体状态（所有元素及其位置关系）
- 根据用户请求规划新元素的放置位置
- 逐步构建完整画作（每步在上一帧基础上追加）
"""

from __future__ import annotations

import math
import random
import re
from typing import List, Optional

from engine.drawing_engine import DrawingEngine
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    ColorOperation,
    DrawingOperation,
    FreehandOperation,
    LabelSelectedOperation,
    LineDrawOperation,
    MoveSelectedOperation,
    OperationType,
    PointLocation,
    RecolorSelectedOperation,
    RectangleOperation,
    StarOperation,
    TriangleOperation,
)
from parser import color_map


class DrawingAgent:
    """智能绘画规划器。

    核心思路：把用户语音理解为"在当前画布基础上追加元素"，
    代理负责理解画布状态并规划新元素的位置。
    """

    def plan(
        self,
        text: str,
        engine: DrawingEngine,
        canvas_ops: List[DrawingOperation] | None = None,
    ) -> List[DrawingOperation]:
        """根据画布状态和用户请求规划操作。

        Args:
            text: 用户语音文本。
            engine: 绘图引擎（提供画布状态）。
            canvas_ops: 画布上的所有操作（如果不提供则从 engine 获取）。

        Returns:
            规划好的操作列表。
        """
        canvas_ops = canvas_ops or engine.get_history()
        normalized = text.strip()
        if not normalized:
            return []

        # 1. 先检查是否有语义标签/颜色/大小等简单操作
        simple_ops = self._plan_simple(normalized, canvas_ops)
        if simple_ops:
            return simple_ops

        if self._is_detail_command(normalized):
            detail_ops = self._plan_detail(normalized, engine)
            if detail_ops:
                return detail_ops

        # 几何形状与工具组合继续交给 CommandParser，避免抢走“用红笔画圆”。
        if self._is_draw_shape(normalized):
            return []

        # 2. 检查是否需要追加元素到画布
        if self._is_add_element_command(normalized, canvas_ops):
            return self._plan_add_element(normalized, canvas_ops, engine)

        # 3. 检查是否需要移动/调整已有元素
        if self._is_edit_command(normalized):
            return self._plan_edit(normalized, canvas_ops, engine)

        return []

    # ── 简单操作 ──────────────────────────────────────────

    def _plan_simple(
        self, text: str, ops: List[DrawingOperation],
    ) -> List[DrawingOperation]:
        """处理简单操作：语义标签、颜色、粗细等。"""
        label = self._extract_label(text)
        if label:
            return [LabelSelectedOperation(label=label)]

        color_op = self._match_color_operation(text)
        if color_op:
            return color_op

        return []

    def _extract_label(self, text: str) -> str:
        """提取语义标签（如"这是太阳"）。"""
        if "太阳" in text and any(word in text for word in ("是", "叫", "画的是")):
            return "太阳"
        return ""

    def _match_color_operation(self, text: str) -> Optional[List[DrawingOperation]]:
        """匹配颜色操作。"""
        if not any(kw in text for kw in ["颜色", "涂满", "填充", "上色", "改", "换"]):
            return None
        for name in sorted(color_map.COLOR_MAP, key=len, reverse=True):
            if name in text:
                return [ColorOperation(color=color_map.get_color(name))]
        return None

    def _is_detail_command(self, text: str) -> bool:
        """判断是否是“帮它补充细节/完善一下”这类上下文命令。"""
        return any(word in text for word in ("补充", "细节", "完善", "丰富", "加点", "加些"))

    def _plan_detail(self, text: str, engine: DrawingEngine) -> List[DrawingOperation]:
        """给当前语义对象补充第一版可控细节。"""
        target = engine.find_semantic_target("太阳") if "太阳" in text else engine.find_semantic_target()
        if target is None:
            return []
        if getattr(target, "semantic_label", "") == "太阳":
            return self._plan_sun_details(target)
        return []

    def _plan_sun_details(self, target: DrawingOperation) -> List[DrawingOperation]:
        """给太阳补充单色画笔光芒。"""
        bbox = self._get_bounding_box(target)
        if not bbox:
            return []
        cx, cy = int(bbox["cx"]), int(bbox["cy"])
        radius = int(max(bbox["right"] - bbox["left"], bbox["bottom"] - bbox["top"]) / 2)
        color = getattr(target, "color", "#000000")
        size = max(2, int(getattr(target, "size", 3)))
        ops: List[DrawingOperation] = []
        for i in range(12):
            angle = math.tau * i / 12
            start = (
                int(cx + math.cos(angle) * (radius + 10)),
                int(cy + math.sin(angle) * (radius + 10)),
            )
            end = (
                int(cx + math.cos(angle) * (radius + 48)),
                int(cy + math.sin(angle) * (radius + 48)),
            )
            ray = LineDrawOperation(color=color, size=size, start=start, end=end)
            ray.semantic_label = "太阳光芒"
            ops.append(ray)
        return ops

    # ── 追加元素 ──────────────────────────────────────────

    def _is_add_element_command(self, text: str, ops: List[DrawingOperation]) -> bool:
        """判断是否是追加元素的命令。

        关键词：画、生成、画一条、画一个、加一条、加一个、放一个、再来
        排除：撤销、清空、颜色、粗细等
        """
        add_keywords = [
            "画", "生成", "画一条", "画一个", "加一条", "加一个",
            "放一个", "再来", "补一条", "添一条", "绘", "创作",
        ]
        for kw in add_keywords:
            if kw in text:
                return True

        # "画个/画只/画张/画幅" 等口语
        if re.search(r"画[个只张幅头条]?", text):
            return True

        # "来一个/来一张/来一幅" 等
        if re.search(r"来[个只张幅条]?", text):
            return True

        return False

    def _is_ai_image_command(self, text: str) -> bool:
        """判断是否是 AI 生图命令（交给 parser 处理）。

        AI 生图的特征是描述具体的实体对象（动物、自然元素、场景等），
        而不是几何形状或线条。
        但"在X旁边画Y"这种有参照物的命令，Y可能是线条/几何，agent 要处理。
        """
        # 如果有参照物结构，说明不是纯 AI 生图
        if re.search(r"在[^(（]*(?:的)?[^(（]*(?:旁边|下面|上面|左边|右边|下边|上边|下面|里面)", text):
            return False

        # AI 生图实体关键词（动物、自然、场景）
        ai_entities = [
            "小猫", "小狗", "小兔", "小老鼠", "小乌龟",
            "风景", "图案", "动物", "植物", "人物", "场景", "卡通",
            "美女", "帅哥", "房屋", "建筑", "城市", "乡村", "海洋", "森林",
            "花朵", "月亮", "太阳", "星星", "龙", "凤",
            "熊猫", "狮子", "大象", "猴子", "蝴蝶", "蜜蜂", "蚂蚁",
            "玫瑰", "百合", "樱花", "桃花", "荷花", "梅花", "菊花",
            "向日葵", "蘑菇", "仙人掌", "珊瑚", "水母",
            "小猫", "小狗", "小兔子", "小老鼠", "小乌龟",
        ]
        for kw in ai_entities:
            if kw in text:
                return True

        # "画一个/只/头/幅/张 + 实体" 模式
        if re.search(r"画[一个只头幅张条][^(（]*(?:猫|狗|兔|鼠|龟|鸟|鱼|龙|凤|熊猫|狮子|大象|猴子|蝴蝶|蜜蜂|蚂蚁|玫瑰|百合|樱花|桃花|荷花|梅花|菊花|向日葵|蘑菇|仙人掌|珊瑚|水母|风景|图案|动物|植物|人物|场景|卡通|美女|帅哥|房屋|建筑|城市|乡村|海洋|森林|月亮|太阳|星星|云|花|树|草)", text):
            return True

        return False

    def _plan_add_element(
        self,
        text: str,
        ops: List[DrawingOperation],
        engine: DrawingEngine,
    ) -> List[DrawingOperation]:
        """规划追加元素操作。

        核心：从文本中提取要画的元素类型，然后：
        1. 分析画布整体构图（元素分布、空白区域）
        2. 根据参照物和方向词计算位置
        3. 确保新元素自然地融入画面
        """
        # 分析画布上的元素
        canvas_elements = self._analyze_canvas(ops)

        # 判断是哪种追加类型
        if self._is_draw_shape(text):
            return self._plan_draw_shape(text, canvas_elements, ops, engine)

        if self._is_draw_line(text):
            return self._plan_draw_line(text, canvas_elements, ops, engine)

        return self._plan_draw_ai_image(text, canvas_elements, engine)

    def _is_draw_shape(self, text: str) -> bool:
        return any(kw in text for kw in [
            "圆", "方形", "矩形", "正方", "三角", "星", "圈圈",
        ])

    def _is_draw_line(self, text: str) -> bool:
        return any(kw in text for kw in [
            "直线", "横线", "竖线", "曲线", "线条", "波浪线",
        ])

    def _is_draw_ai_image(self, text: str) -> bool:
        return self._is_add_element_command(text, [])

    def _plan_draw_ai_image(
        self,
        text: str,
        canvas_elements: List[dict],
        engine: DrawingEngine,
    ) -> List[DrawingOperation]:
        """规划 AI 生图操作。"""
        # 提取 prompt（去除"画一个"等前缀）
        prompt = self._extract_ai_prompt(text)
        if not prompt:
            prompt = text

        # 计算位置：有参照物就放参照物旁边，否则放画布中心。
        center = self._compute_element_position(text, canvas_elements, engine)
        pos = self._center_to_image_position(center, engine)
        op = AIImageOperation(prompt=self._build_element_prompt(prompt), position=pos)
        op.semantic_label = self._extract_semantic_label(prompt)
        op.color = self._extract_color_from_text(text)
        return [op]

    def _plan_draw_line(
        self,
        text: str,
        canvas_elements: List[dict],
        ops: List[DrawingOperation],
        engine: DrawingEngine,
    ) -> List[DrawingOperation]:
        """规划线条/河流等操作。"""
        color = self._extract_color_from_text(text)
        size = self._extract_size(text)

        cw, ch = engine.canvas_width, engine.canvas_height

        # 判断是否是大型场景元素（横跨整个画布）
        is_large_scene = any(kw in text for kw in [
            "河", "河流", "小河", "小溪",
            "天空", "天", "草地", "草坪", "草原",
            "地面", "土地", "田野", "山坡", "山顶",
            "水面", "海", "湖", "海洋", "池塘",
        ])

        if is_large_scene:
            # 大型场景元素：横跨整个画布
            return self._plan_large_scene_element(text, color, size, cw, ch, canvas_elements)

        # 普通线条
        is_horizontal = any(kw in text for kw in ["横线", "水平", "横向"])
        is_vertical = any(kw in text for kw in ["竖线", "垂直", "纵向"])
        is_curve = any(kw in text for kw in ["曲线", "波浪", "弯"])

        pos = self._compute_element_position(text, canvas_elements, engine)
        cx, cy = pos

        if is_curve:
            return self._plan_wavy_line(cx, cy, color, size, cw, ch, canvas_elements)

        elif is_horizontal:
            start = (20, cy)
            end = (cw - 20, cy)
            return [LineDrawOperation(color=color, size=size, start=start, end=end)]

        elif is_vertical:
            start = (cx, 20)
            end = (cx, ch - 20)
            return [LineDrawOperation(color=color, size=size, start=start, end=end)]

        else:
            start = (20, cy)
            end = (cw - 20, cy)
            return [LineDrawOperation(color=color, size=size, start=start, end=end)]

    def _plan_large_scene_element(
        self, text: str, color: str, size: int,
        cw: int, ch: int, elements: List[dict],
    ) -> List[DrawingOperation]:
        """大型场景元素：横跨整个画布，位置由画面内容决定。"""
        ops: List[DrawingOperation] = []

        # 判断元素类型
        if "河" in text or "溪" in text or "水" in text:
            # 河流：在画面下部从左到右的波浪线
            # 找所有非大型元素的最低点，放在其下方
            min_bottom = ch * 0.5
            for elem in elements:
                bb = elem.get("bbox", {})
                if bb.get("bottom", 0) > min_bottom:
                    min_bottom = bb["bottom"]
            river_y = min_bottom + 40
            river_y = min(river_y, ch - 80)  # 不超过底部

            # 创建波浪线（横跨整个画布）
            points = []
            segments = 40
            for i in range(segments + 1):
                x = int(40 + i * (cw - 80) / segments)
                wave_amp = 12 + 8 * math.sin(i * 0.6)
                y = int(river_y + math.sin(i * 0.7) * wave_amp)
                points.append((x, y))

            for i in range(len(points) - 1):
                op = LineDrawOperation(color=color, size=size,
                                       start=points[i], end=points[i + 1])
                op.semantic_label = "河流"
                ops.append(op)

            # 河流通常有宽度（两条平行波浪线）
            for offset in [-8, 8]:
                points2 = []
                for i in range(segments + 1):
                    x = int(40 + i * (cw - 80) / segments)
                    wave_amp = 12 + 8 * math.sin(i * 0.6)
                    y = int(river_y + offset + math.sin(i * 0.7) * wave_amp)
                    points2.append((x, y))
                for i in range(len(points2) - 1):
                    op = LineDrawOperation(color=color, size=size,
                                           start=points2[i], end=points2[i + 1])
                    ops.append(op)

        elif "草" in text or "草坪" in text or "草原" in text:
            # 草地：在画面下部绘制多条短横线表示草丛
            grass_y = ch - 120
            # 找参照物的底部
            for elem in elements:
                bb = elem.get("bbox", {})
                if bb.get("bottom", 0) > grass_y - 50:
                    grass_y = bb["bottom"] + 20
            for row in range(3):
                y = grass_y + row * 15
                for x in range(40, cw - 40, 30):
                    end_x = x + 20 + random.randint(-5, 5)
                    ops.append(LineDrawOperation(color=color, size=size,
                                                 start=(x, y), end=(end_x, y)))

        elif "天空" in text or "天" in text:
            # 天空：在画面上部绘制水平线表示天际线
            sky_y = 80
            ops.append(LineDrawOperation(color=color, size=size,
                                         start=(20, sky_y), end=(cw - 20, sky_y)))

        elif "地面" in text or "土地" in text:
            # 地面：画面底部横线
            ground_y = ch - 80
            ops.append(LineDrawOperation(color=color, size=size,
                                         start=(20, ground_y), end=(cw - 20, ground_y)))

        elif "海" in text or "湖" in text:
            # 水面：多条水平波浪线
            water_y = ch - 150
            for row in range(3):
                points = []
                segments = 30
                for i in range(segments + 1):
                    x = int(40 + i * (cw - 80) / segments)
                    y = int(water_y + row * 20 + math.sin(i * 0.5) * 5)
                    points.append((x, y))
                for i in range(len(points) - 1):
                    op = LineDrawOperation(color=color, size=size,
                                           start=points[i], end=points[i + 1])
                    ops.append(op)

        else:
            # 默认：横跨画布的横线
            y = ch // 2
            ops.append(LineDrawOperation(color=color, size=size,
                                         start=(20, y), end=(cw - 20, y)))

        return ops

    def _plan_draw_shape(
        self,
        text: str,
        canvas_elements: List[dict],
        ops: List[DrawingOperation],
        engine: DrawingEngine,
    ) -> List[DrawingOperation]:
        """规划形状绘制操作。"""
        color = self._extract_color_from_text(text)
        size = self._extract_size(text)
        cx, cy = self._compute_element_position(text, canvas_elements, engine)

        if "圆" in text:
            r = max(40, size * 5)
            return [CircleOperation(color=color, size=size, center=(cx, cy), radius=r)]
        elif "方" in text or "矩" in text:
            w, h = max(60, size * 6), max(40, size * 4)
            return [RectangleOperation(
                color=color, size=size,
                top_left=(cx - w // 2, cy - h // 2),
                bottom_right=(cx + w // 2, cy + h // 2),
            )]
        elif "三角" in text:
            s = max(40, size * 5)
            p1 = (cx, cy - s)
            p2 = (cx - s, cy + s // 2)
            p3 = (cx + s, cy + s // 2)
            return [TriangleOperation(color=color, size=size, p1=p1, p2=p2, p3=p3)]
        elif "星" in text:
            r = max(40, size * 5)
            return [StarOperation(color=color, size=size, center=(cx, cy), outer_radius=r, inner_radius=r * 0.4)]

        return []

    # ── 编辑操作 ──────────────────────────────────────────

    def _is_edit_command(self, text: str) -> bool:
        return any(kw in text for kw in [
            "移动", "移", "放大", "缩小", "变大", "变小",
            "改颜色", "换个颜色", "涂满", "填充",
        ])

    def _plan_edit(
        self,
        text: str,
        ops: List[DrawingOperation],
        engine: DrawingEngine,
    ) -> List[DrawingOperation]:
        """规划编辑操作。"""
        # 移动
        if any(kw in text for kw in ["移动", "移", "放", "挪"]):
            target = engine.find_semantic_target()
            if target:
                cx, cy = engine._operation_center(target)
                if cx is None:
                    return []
                cw, ch = engine.canvas_width, engine.canvas_height
                # 简单逻辑：往右移动
                return [MoveSelectedOperation(dx=40, dy=0)]

        return []

    # ── 画布分析 ──────────────────────────────────────────

    def _analyze_canvas(self, ops: List[DrawingOperation]) -> List[dict]:
        """分析画布上的元素，返回结构化的元素列表。

        每个元素包含:
        - type: 元素类型 (circle, rectangle, triangle, star, line, freehand, ai_image)
        - bbox: 边界框 {cx, cy, left, right, top, bottom}
        - color: 颜色（如果有）
        - prompt: AI 图像的 prompt（如果有）
        """
        elements = []

        for op in ops:
            if not isinstance(op, (
                CircleOperation, RectangleOperation, TriangleOperation,
                StarOperation, LineDrawOperation, FreehandOperation, AIImageOperation,
            )):
                continue

            bbox = self._get_bounding_box(op)
            if bbox is None:
                continue

            elem = {
                "type": self._operation_type_name(op),
                "bbox": bbox,
                "color": getattr(op, "color", ""),
                "semantic_label": getattr(op, "semantic_label", ""),
            }

            if isinstance(op, AIImageOperation):
                elem["prompt"] = getattr(op, "prompt", "")

            elements.append(elem)

        return elements

    def _operation_type_name(self, op: DrawingOperation) -> str:
        """获取操作类型的中文名称。"""
        if isinstance(op, CircleOperation):
            return "circle"
        elif isinstance(op, RectangleOperation):
            return "rectangle"
        elif isinstance(op, TriangleOperation):
            return "triangle"
        elif isinstance(op, StarOperation):
            return "star"
        elif isinstance(op, LineDrawOperation):
            return "line"
        elif isinstance(op, FreehandOperation):
            return "freehand"
        elif isinstance(op, AIImageOperation):
            prompt = getattr(op, "prompt", "")
            # 从 prompt 中提取关键词作为类型
            return self._extract_element_type(prompt)
        return "unknown"

    def _extract_element_type(self, prompt: str) -> str:
        """从 AI 图像 prompt 中提取元素类型关键词。"""
        if not prompt:
            return "ai_image"

        chinese = re.findall(r'[一-鿿]', prompt)
        if not chinese:
            return "ai_image"
        ch_text = "".join(chinese)

        type_map = {
            "树": "tree", "树": "tree", "树": "tree", "树": "tree",
            "草": "grass", "河": "river", "河": "river", "河": "river", "河": "river",
            "花": "flower", "花": "flower", "山": "mountain", "云": "cloud",
            "太阳": "sun", "月亮": "moon", "星星": "star", "星": "star",
            "鸟": "bird", "鸟": "bird", "猫": "cat", "狗": "dog",
            "人": "person", "房子": "house", "房子": "house", "房子": "house",
            "兔子": "rabbit", "兔": "rabbit", "老鼠": "mouse", "鼠": "mouse",
            "龙": "dragon", "凤": "phoenix", "鱼": "fish", "鱼": "fish",
            "乌龟": "turtle", "龟": "turtle", "风景": "landscape",
            "图案": "pattern", "动物": "animal", "卡通": "cartoon",
        }

        for cn, etype in type_map.items():
            if cn in ch_text:
                return etype

        return "ai_image"

    def _get_bounding_box(self, op: DrawingOperation) -> Optional[dict]:
        """获取操作的边界框。"""
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

        elif isinstance(op, AIImageOperation):
            x, y = op.position
            return {"cx": x + 200, "cy": y + 200,
                    "top": y, "bottom": y + 400,
                    "left": x, "right": x + 400}

        return None

    # ── 位置计算 ──────────────────────────────────────────

    def _compute_element_position(
        self,
        text: str,
        canvas_elements: List[dict],
        engine: DrawingEngine,
    ) -> tuple:
        """计算新元素的放置位置。

        策略:
        1. 如果文本中有参照物（"在树旁边"），找到参照物并放在其附近
        2. 如果有方向词（"左/右/上/下"），按方向计算
        3. 默认放在画布右侧或底部（不重叠已有元素）
        """
        cw, ch = engine.canvas_width, engine.canvas_height

        # 1. 尝试从文本中提取参照物
        ref_elem = self._find_reference_element(text, canvas_elements)
        if ref_elem:
            return self._position_near_element(text, ref_elem, engine)

        # 2. 尝试从文本中提取方向
        direction = self._extract_direction(text)
        if direction:
            return self._position_by_direction(text, direction, canvas_elements, engine)

        # 3. 默认：放到画布右侧（从左到右构建画作）
        # 找到最右边的元素，在其右侧放置
        rightmost = self._find_rightmost_element(canvas_elements, engine)
        if rightmost:
            bbox = rightmost["bbox"]
            cx = bbox["right"] + 80
            cy = bbox["cy"]
            # 如果超出画布，换行
            if cx + 100 > cw:
                # 找最下方的元素
                bottommost = self._find_bottommost_element(canvas_elements, engine)
                if bottommost:
                    bbox2 = bottommost["bbox"]
                    cx = bbox2["left"]
                    cy = bbox2["bottom"] + 80
                else:
                    cx = 100
                    cy = 100
            return (int(cx), int(cy))

        # 4. 画布为空：默认中心
        return (cw // 2, ch // 2)

    def _find_reference_element(
        self, text: str, elements: List[dict],
    ) -> Optional[dict]:
        """从文本中提取参照物对应的元素。"""
        # 元素类型关键词映射
        type_keywords = {
            "tree": ["树", "大树", "小树", "树", "树"],
            "river": ["河", "小河", "河流", "小溪", "溪流"],
            "grass": ["草", "草地", "小草", "草坪"],
            "flower": ["花", "花朵", "小花", "鲜花"],
            "mountain": ["山", "大山", "小山", "山峰"],
            "cloud": ["云", "白云", "云朵", "云彩"],
            "sun": ["太阳", "日"],
            "moon": ["月亮", "月"],
            "star": ["星", "星星", "五角星"],
            "bird": ["鸟", "小鸟", "飞鸟", "飞鸟"],
            "cat": ["猫", "小猫", "猫咪"],
            "dog": ["狗", "小狗", "狗狗"],
            "rabbit": ["兔", "兔子", "小兔子"],
            "turtle": ["龟", "乌龟", "小乌龟"],
            "person": ["人", "小人", "人物"],
            "house": ["房子", "房屋", "屋", "小屋", "房子"],
        }

        for elem in reversed(elements):  # 从最近到最早
            etype = elem["type"]
            prompt = elem.get("prompt", "")
            semantic_label = elem.get("semantic_label", "")

            if semantic_label and semantic_label in text:
                return elem

            # 检查元素类型是否匹配文本
            for type_key, keywords in type_keywords.items():
                if etype == type_key:
                    for keyword in keywords:
                        if keyword in text:
                            return elem

            # 检查 prompt 中是否有匹配的中文关键词
            if prompt:
                chinese = re.findall(r'[一-鿿]', prompt)
                if chinese:
                    ch_text = "".join(chinese)
                    for keywords in type_keywords.values():
                        for keyword in keywords:
                            if keyword in ch_text and keyword in text:
                                return elem

        return None

    def _position_near_element(
        self, text: str, elem: dict, engine: DrawingEngine,
    ) -> tuple:
        """在参照物附近放置新元素。"""
        bbox = elem["bbox"]
        cx, cy = bbox["cx"], bbox["cy"]
        cw, ch = engine.canvas_width, engine.canvas_height

        # 判断方向
        if "上" in text and "下" not in text:
            return (int(cx), int(bbox["top"] - 60))
        elif "下" in text:
            return (int(cx), int(bbox["bottom"] + 60))
        elif "左" in text:
            return (int(bbox["left"] - 60), int(cy))
        elif "右" in text or "旁边" in text or "边" in text:
            return (int(bbox["right"] + 60), int(cy))

        # 默认：右侧
        return (int(bbox["right"] + 60), int(cy))

    def _extract_direction(self, text: str) -> str:
        """从文本中提取方向。"""
        if "上面" in text or "上" in text:
            return "above"
        if "下面" in text or "下" in text:
            return "below"
        if "左边" in text or "左" in text:
            return "left"
        if "右边" in text or "右" in text:
            return "right"
        return ""

    def _position_by_direction(
        self, text: str, direction: str,
        elements: List[dict], engine: DrawingEngine,
    ) -> tuple:
        """按方向放置新元素。"""
        cw, ch = engine.canvas_width, engine.canvas_height

        if direction == "above":
            topmost = self._find_topmost_element(elements, engine)
            if topmost:
                bbox = topmost["bbox"]
                return (int(bbox["cx"]), int(bbox["top"] - 60))
            return (cw // 2, 60)
        elif direction == "below":
            bottommost = self._find_bottommost_element(elements, engine)
            if bottommost:
                bbox = bottommost["bbox"]
                return (int(bbox["cx"]), int(bbox["bottom"] + 60))
            return (cw // 2, ch - 60)
        elif direction == "left":
            leftmost = self._find_leftmost_element(elements, engine)
            if leftmost:
                bbox = leftmost["bbox"]
                return (int(bbox["left"] - 60), int(bbox["cy"]))
            return (60, ch // 2)
        elif direction == "right":
            rightmost = self._find_rightmost_element(elements, engine)
            if rightmost:
                bbox = rightmost["bbox"]
                return (int(bbox["right"] + 60), int(bbox["cy"]))
            return (cw - 60, ch // 2)

        return (cw // 2, ch // 2)

    def _find_rightmost_element(self, elements: List[dict], engine: DrawingEngine) -> Optional[dict]:
        if not elements:
            return None
        return max(elements, key=lambda e: e["bbox"]["right"])

    def _find_bottommost_element(self, elements: List[dict], engine: DrawingEngine) -> Optional[dict]:
        if not elements:
            return None
        return max(elements, key=lambda e: e["bbox"]["bottom"])

    def _find_topmost_element(self, elements: List[dict], engine: DrawingEngine) -> Optional[dict]:
        if not elements:
            return None
        return min(elements, key=lambda e: e["bbox"]["top"])

    def _find_leftmost_element(self, elements: List[dict], engine: DrawingEngine) -> Optional[dict]:
        if not elements:
            return None
        return min(elements, key=lambda e: e["bbox"]["left"])

    # ── 曲线（河流） ──────────────────────────────────────

    def _plan_wavy_line(
        self, cx: int, cy: int, color: str, size: int,
        cw: int, ch: int, elements: List[dict],
    ) -> List[DrawingOperation]:
        """绘制波浪线（河流）。

        改进：不再横跨整张画布，而是根据画面整体构图，
        让河流自然地从画面中部延伸，宽度适中。
        """
        # 计算画面中下区域（河流通常在底部）
        # 找到所有元素的最低点
        min_bottom = ch * 0.5  # 默认从画布 50% 处开始
        for elem in elements:
            bb = elem.get("bbox", {})
            if bb.get("bottom", 0) > min_bottom:
                min_bottom = bb["bottom"]

        # 河流中心线放在所有元素的最低点下方一点
        river_y = min_bottom + 30
        river_y = min(river_y, ch - 60)  # 不超过画布底部

        # 河流宽度：从左到右贯穿，但留边距
        start_x = 60
        end_x = cw - 60

        # 创建波浪线
        points = []
        segments = 30
        dx = (end_x - start_x) / segments
        for i in range(segments + 1):
            x = int(start_x + i * dx)
            # 正弦波浪，振幅随位置变化更自然
            wave_amp = 15 + 10 * math.sin(i * 0.5)
            y = int(river_y + math.sin(i * 0.8) * wave_amp)
            points.append((x, y))

        # 用多段直线绘制曲线
        ops: List[DrawingOperation] = []
        for i in range(len(points) - 1):
            op = LineDrawOperation(color=color, size=size,
                                   start=points[i], end=points[i + 1])
            op.semantic_label = "河流"
            ops.append(op)

        return ops

    # ── 工具方法 ──────────────────────────────────────────

    def _extract_ai_prompt(self, text: str) -> str:
        """从 AI 生成命令中提取提示词。"""
        text = self._strip_reference_clause(text)
        prefixes = [
            "画一个", "画一只", "画一幅", "画一张", "画一条", "画头",
            "画一棵", "画一颗", "画一座", "画几颗", "画几个", "画几条",
            "加一个", "加一只", "加一条", "加一座", "加几个", "加几颗",
            "画个", "画幅", "画张", "画条",
            "生成一个", "生成一只", "生成一幅", "生成一张", "生成一条",
            "做一个", "来一个", "来一只", "来一幅", "来一张",
            "画一", "生成一", "做一", "来一",
            "画", "生成", "创建", "做", "来",
        ]
        prompt = text
        for prefix in prefixes:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break

        return prompt.rstrip("。,.！？!?,") or text

    def _strip_reference_clause(self, text: str) -> str:
        """去掉“在树下面”这类参照位置短语，保留真正要画的元素。"""
        match = re.search(r"(?:画|加|添|生成|创建|放)(.+)$", text)
        if match:
            return match.group(0)
        return text

    def _build_element_prompt(self, element: str) -> str:
        """构造交给 Agnes 的元素级 prompt，保持开放词汇。"""
        clean = element.strip(" 。,.！？!?,")
        return clean or element

    def _extract_semantic_label(self, element: str) -> str:
        """从元素描述中提取后续可引用的语义标签。"""
        label = element.strip(" 。,.！？!?,")
        label = re.sub(r"^(一些|几个|几颗|几条|一棵|一颗|一座|一个|一只|一条|一片|一朵|一辆|一幅|一张)", "", label)
        label = re.sub(r"(的|漂亮的|可爱的|简单的|单色的|黑色|红色|蓝色|绿色|黄色|白色|紫色|橙色|棕色|灰色|粉色)", "", label)
        return label.strip() or element.strip()

    def _center_to_image_position(self, center: tuple, engine: DrawingEngine) -> tuple:
        """AI 图片以左上角定位，语义规划以中心点定位。"""
        x = int(center[0] - 200)
        y = int(center[1] - 200)
        return (
            max(0, min(engine.canvas_width - 400, x)),
            max(0, min(engine.canvas_height - 400, y)),
        )

    def _extract_color_from_text(self, text: str) -> str:
        """从文本中提取颜色。"""
        for name in sorted(color_map.COLOR_MAP, key=len, reverse=True):
            if name in text:
                return color_map.get_color(name)
        return "#000000"

    def _extract_size(self, text: str) -> int:
        """从文本中提取大小。"""
        num = re.search(r"(\d+)", text)
        if num:
            return max(1, min(50, int(num.group(1))))
        return 3

    def _match_color_operation(self, text: str) -> Optional[List[DrawingOperation]]:
        """匹配颜色操作。"""
        if not any(kw in text for kw in ["颜色", "涂满", "填充", "上色"]):
            return None
        for name in sorted(color_map.COLOR_MAP, key=len, reverse=True):
            if name in text:
                if any(kw in text for kw in ["涂满", "填充", "上色", "改", "换"]):
                    return [RecolorSelectedOperation(color=color_map.get_color(name), fill=True)]
                return [ColorOperation(color=color_map.get_color(name))]
        return None
