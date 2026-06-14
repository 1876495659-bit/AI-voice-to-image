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
import uuid
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
    StrokeGroupOperation,
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

        整幅画布 I2I 模式由 MainWindow 和 DrawingEngine 优先处理。

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

    def build_i2i_delta(self, text: str, canvas_ops: List[DrawingOperation]) -> str:
        """为 I2I 模式构建增量提示词。

        从用户语音中提取要添加/修改的内容，转换为英文提示词。
        例如 “在大树上画一些苹果” → “add apples on the tree”

        Args:
            text: 用户语音文本。
            canvas_ops: 当前画布上的操作。

        Returns:
            英文增量提示词。
        """
        # 提取核心对象
        prompt = self._extract_ai_prompt(text)
        if not prompt:
            prompt = text

        # 翻译为英文（简化版：直接返回中文，模型能理解）
        # 更好的做法是用 LLM 翻译，但这里先返回中文
        # 因为 Agnes 的 _clean_prompt_for_model 已经做了英文处理
        return prompt

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
                if any(kw in text for kw in ["涂满", "填充", "上色", "改", "换"]):
                    return [RecolorSelectedOperation(
                        color=color_map.get_color(name),
                        target_label=self._extract_target_label_from_text(text),
                        fill=True,
                    )]
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

        if self._should_place_fish_in_water(text, canvas_elements):
            quantity = self._extract_quantity(text)
            return self._plan_fish_in_water(text, canvas_elements, quantity)

        if self._is_draw_line(text):
            return self._plan_draw_line(text, canvas_elements, ops, engine)

        # 提取数量，支持批量绘制
        quantity = self._extract_quantity(text)
        return self._plan_draw_ai_image(text, canvas_elements, engine, quantity)

    def _is_draw_shape(self, text: str) -> bool:
        return any(kw in text for kw in [
            "圆", "方形", "矩形", "正方", "三角", "星", "圈圈",
        ])

    def _is_draw_line(self, text: str) -> bool:
        return any(kw in text for kw in [
            "直线", "横线", "竖线", "曲线", "线条", "波浪线",
            "河", "河流", "小河", "小溪", "溪流", "水面", "湖", "池塘",
        ])

    def _is_draw_ai_image(self, text: str) -> bool:
        return self._is_add_element_command(text, [])

    def _plan_draw_ai_image(
        self,
        text: str,
        canvas_elements: List[dict],
        engine: DrawingEngine,
        quantity: int = 1,
    ) -> List[DrawingOperation]:
        """规划 AI 生图操作。

        当 quantity > 1 时，围绕参照物环形分布 N 个实例，
        共享同一个 group_id 以复用 API 调用结果。
        """
        prompt = self._extract_ai_prompt(text)
        if not prompt:
            prompt = text

        ref_elem = self._find_reference_element(text, canvas_elements)

        if ref_elem and self._should_embed_fruit_in_tree(text, prompt, ref_elem):
            return self._plan_tree_fruit_strokes(prompt, ref_elem, quantity, text)

        if quantity > 1 and ref_elem:
            # 批量绘制：环形分布在参照物周围
            return self._plan_batch_ai_image(
                prompt, ref_elem, quantity, text, engine, canvas_elements,
            )

        pos = self._compute_ai_image_position(text, canvas_elements, engine)
        op = AIImageOperation(prompt=self._build_element_prompt(prompt), position=pos)
        op.semantic_label = self._extract_semantic_label(prompt)
        op.color = self._extract_color_from_text(text)
        return [op]

    def _plan_batch_ai_image(
        self,
        prompt: str,
        ref_elem: dict,
        quantity: int,
        text: str,
        engine: DrawingEngine,
        canvas_elements: List[dict],
    ) -> List[DrawingOperation]:
        """批量绘制多个相同元素，围绕参照物环形分布。"""
        ops: List[DrawingOperation] = []
        bbox = ref_elem["bbox"]
        cx, cy = bbox["cx"], bbox["cy"]

        # 树冠区域：上半部分
        if ref_elem["type"] == "tree":
            # 树冠在树的上半部分
            placement_cy = int((bbox["top"] + bbox["cy"]) / 2)
        else:
            placement_cy = int(cy)

        placement_cx = int(cx)
        # 半径随数量扩展，避免重叠
        radius = 60 + min(quantity * 8, 40)

        group_id = uuid.uuid4().hex[:8]

        for i in range(quantity):
            angle_deg = -90 + (360.0 / quantity) * i
            rad = math.radians(angle_deg)
            x = int(placement_cx + radius * math.cos(rad))
            y = int(placement_cy + radius * math.sin(rad))
            x = max(0, min(engine.canvas_width - 400, x))
            y = max(0, min(engine.canvas_height - 400, y))

            label = self._extract_semantic_label(prompt)
            if i == 0:
                semantic_label = f"一个{label}"
            else:
                semantic_label = f"另一个{label}"

            op = AIImageOperation(
                prompt=self._build_element_prompt(prompt),
                position=(x, y),
                group_id=group_id,
            )
            op.semantic_label = semantic_label
            op.color = self._extract_color_from_text(text)
            ops.append(op)

        return ops

    def _should_embed_fruit_in_tree(self, text: str, prompt: str, ref_elem: dict) -> bool:
        """判断生图构图是否应嵌入参照物，而不是生成独立大元素。"""
        if ref_elem.get("type") != "tree":
            return False
        target_text = f"{text}{prompt}"
        is_fruit = any(word in target_text for word in ("苹果", "果子", "果实", "水果"))
        relation_on_tree = any(word in text for word in ("树上", "树的上面", "树冠", "长在树"))
        return is_fruit and relation_on_tree

    def _plan_tree_fruit_strokes(
        self,
        prompt: str,
        ref_elem: dict,
        quantity: int,
        text: str,
    ) -> List[DrawingOperation]:
        """把“树上苹果”规划为树冠内的小笔画，避免独立贴图覆盖。"""
        bbox = ref_elem["bbox"]
        left, right = int(bbox["left"]), int(bbox["right"])
        top, bottom = int(bbox["top"]), int(bbox["bottom"])
        width = max(1, right - left)
        height = max(1, bottom - top)

        canopy_top = top
        canopy_bottom = int(top + height * 0.55)
        canopy_left = int(left + width * 0.10)
        canopy_right = int(right - width * 0.10)
        quantity = max(1, min(quantity, 8))
        radius = max(6, min(16, int(min(width, height) * 0.045)))
        color = self._extract_color_from_text(text)
        label = self._extract_semantic_label(prompt)
        if "果" in label and "苹果" not in label:
            label = "苹果"
        if "苹果" in text or "苹果" in prompt:
            label = "苹果"

        placements = self._fruit_canopy_positions(
            canopy_left, canopy_right, canopy_top, canopy_bottom, quantity,
        )
        ops: List[DrawingOperation] = []
        for cx, cy in placements:
            op = StrokeGroupOperation(
                color=color,
                size=max(2, self._extract_size(text)),
                semantic_label=label or "苹果",
                strokes=self._apple_strokes(cx, cy, radius),
            )
            ops.append(op)
        return ops

    def _fruit_canopy_positions(
        self,
        left: int,
        right: int,
        top: int,
        bottom: int,
        quantity: int,
    ) -> List[tuple]:
        """在树冠内给果实生成稳定、分散的位置。"""
        width = max(1, right - left)
        height = max(1, bottom - top)
        anchors = [
            (0.30, 0.42), (0.52, 0.30), (0.72, 0.46), (0.42, 0.62),
            (0.62, 0.66), (0.20, 0.58), (0.82, 0.30), (0.50, 0.50),
        ]
        return [
            (int(left + width * fx), int(top + height * fy))
            for fx, fy in anchors[:quantity]
        ]

    def _apple_strokes(self, cx: int, cy: int, radius: int) -> List[List[tuple]]:
        """用几笔画一个小苹果轮廓，保留手绘风格。"""
        r = radius
        outline = [
            (cx - r, cy - r // 5),
            (cx - r, cy - r // 2),
            (cx - r // 2, cy - r),
            (cx, cy - r // 2),
            (cx + r // 2, cy - r),
            (cx + r, cy - r // 2),
            (cx + r, cy + r // 5),
            (cx + r // 2, cy + r),
            (cx, cy + r),
            (cx - r // 2, cy + r),
            (cx - r, cy - r // 5),
        ]
        stem = [(cx, cy - r // 2), (cx + max(2, r // 4), cy - r - max(4, r // 3))]
        leaf = [
            (cx + max(2, r // 4), cy - r),
            (cx + r, cy - r - max(2, r // 5)),
            (cx + max(2, r // 3), cy - r + max(2, r // 5)),
        ]
        shine = [
            (cx - r // 2, cy - r // 5),
            (cx - r // 3, cy + r // 4),
        ]
        return [outline, stem, leaf, shine]

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
            ref_elem = self._find_reference_element(text, elements)
            if ref_elem:
                return self._plan_contextual_river(text, ref_elem, color, size, cw, ch)

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

    def _plan_contextual_river(
        self,
        text: str,
        ref_elem: dict,
        color: str,
        size: int,
        cw: int,
        ch: int,
    ) -> List[DrawingOperation]:
        """根据参照物规划河流，让它作为画面背景/场景线条融入画布。"""
        bbox = ref_elem["bbox"]
        margin = 26
        direction = self._extract_direction(text)

        if direction == "right" or ("右" in text and "左" not in text):
            start_x = int(min(cw - 80, bbox["right"] + margin))
            end_x = cw - 40
            base_y = int(min(ch - 110, max(120, bbox["cy"] + 35)))
        elif direction == "left":
            start_x = 40
            end_x = int(max(80, bbox["left"] - margin))
            base_y = int(min(ch - 110, max(120, bbox["cy"] + 35)))
        elif direction == "below":
            start_x = 40
            end_x = cw - 40
            base_y = int(min(ch - 90, bbox["bottom"] + 55))
        else:
            start_x = int(max(40, bbox["left"] - 60))
            end_x = int(min(cw - 40, bbox["right"] + 220))
            base_y = int(min(ch - 100, bbox["bottom"] + 45))

        if end_x - start_x < 80:
            start_x = max(40, min(start_x, cw - 160))
            end_x = min(cw - 40, start_x + 140)

        return self._river_strokes(start_x, end_x, base_y, color, size)

    def _river_strokes(
        self,
        start_x: int,
        end_x: int,
        base_y: int,
        color: str,
        size: int,
    ) -> List[DrawingOperation]:
        """用多条波浪线画河流，保留画笔感和整体画面连贯性。"""
        ops: List[DrawingOperation] = []
        segments = max(8, min(32, int((end_x - start_x) / 18)))
        offsets = (-18, 0, 18)
        for row, offset in enumerate(offsets):
            points = []
            for i in range(segments + 1):
                t = i / segments
                x = int(start_x + (end_x - start_x) * t)
                perspective = int(t * 36)
                wave = int(math.sin(i * 0.85 + row * 0.7) * (10 + row * 2))
                y = int(base_y + offset + perspective + wave)
                points.append((x, y))
            for i in range(len(points) - 1):
                op = LineDrawOperation(color=color, size=size, start=points[i], end=points[i + 1])
                op.semantic_label = "河流"
                ops.append(op)

        for i in range(4):
            t = (i + 1) / 5
            x0 = int(start_x + (end_x - start_x) * t)
            y0 = int(base_y + 42 + math.sin(i) * 10)
            op = LineDrawOperation(
                color=color,
                size=max(1, size - 1),
                start=(x0 - 18, y0),
                end=(x0 + 24, y0 + 8),
            )
            op.semantic_label = "河流"
            ops.append(op)
        return ops

    def _should_place_fish_in_water(self, text: str, elements: List[dict]) -> bool:
        """判断是否应把鱼追加到已有水域，而不是生成独立鱼图片。"""
        mentions_fish = "鱼" in text
        mentions_water = any(word in text for word in ("河", "河流", "小河", "小溪", "溪", "水里", "水中", "里面"))
        has_water_element = any(elem.get("type") == "river" for elem in elements)
        return mentions_fish and mentions_water and has_water_element

    def _plan_fish_in_water(
        self,
        text: str,
        elements: List[dict],
        quantity: int,
    ) -> List[DrawingOperation]:
        """在已有河流/水域内部追加小鱼笔画。"""
        river_boxes = [elem["bbox"] for elem in elements if elem.get("type") == "river"]
        if not river_boxes:
            return []

        left = int(min(box["left"] for box in river_boxes))
        right = int(max(box["right"] for box in river_boxes))
        top = int(min(box["top"] for box in river_boxes))
        bottom = int(max(box["bottom"] for box in river_boxes))
        quantity = max(1, min(quantity, 6))
        color = self._extract_color_from_text(text)
        size = max(2, self._extract_size(text))

        placements = self._fish_positions(left, right, top, bottom, quantity)
        ops: List[DrawingOperation] = []
        for cx, cy in placements:
            fish = StrokeGroupOperation(
                color=color,
                size=size,
                semantic_label="鱼",
                strokes=self._fish_strokes(cx, cy, max(10, min(22, (right - left) // 18))),
            )
            ops.append(fish)
        return ops

    def _fish_positions(
        self,
        left: int,
        right: int,
        top: int,
        bottom: int,
        quantity: int,
    ) -> List[tuple]:
        width = max(1, right - left)
        height = max(1, bottom - top)
        anchors = [
            (0.22, 0.45), (0.46, 0.58), (0.70, 0.42),
            (0.34, 0.72), (0.58, 0.28), (0.82, 0.62),
        ]
        return [
            (int(left + width * fx), int(top + height * fy))
            for fx, fy in anchors[:quantity]
        ]

    def _fish_strokes(self, cx: int, cy: int, radius: int) -> List[List[tuple]]:
        body = [
            (cx - radius, cy),
            (cx - radius // 3, cy - radius // 2),
            (cx + radius, cy),
            (cx - radius // 3, cy + radius // 2),
            (cx - radius, cy),
        ]
        tail = [
            (cx + radius, cy),
            (cx + radius + radius // 2, cy - radius // 2),
            (cx + radius + radius // 2, cy + radius // 2),
            (cx + radius, cy),
        ]
        eye = [(cx - radius // 2, cy - 1), (cx - radius // 2 + 1, cy - 1)]
        return [body, tail, eye]

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
                StarOperation, LineDrawOperation, FreehandOperation, StrokeGroupOperation, AIImageOperation,
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
            label = getattr(op, "semantic_label", "")
            if any(word in label for word in ("河", "溪", "水")):
                return "river"
            return "line"
        elif isinstance(op, FreehandOperation):
            return "freehand"
        elif isinstance(op, StrokeGroupOperation):
            return self._extract_element_type(getattr(op, "semantic_label", ""))
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
            "苹果": "apple", "果子": "fruit", "果实": "fruit", "水果": "fruit",
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

        elif isinstance(op, StrokeGroupOperation) and op.strokes:
            points = [point for stroke in op.strokes for point in stroke]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
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

    def _compute_ai_image_position(
        self,
        text: str,
        canvas_elements: List[dict],
        engine: DrawingEngine,
    ) -> tuple:
        """计算 AI 元素左上角，避免新增元素压住参照物。"""
        ref_elem = self._find_reference_element(text, canvas_elements)
        if ref_elem:
            bbox = ref_elem["bbox"]
            gap = 24
            if "上" in text and "下" not in text:
                x = int(bbox["cx"] - 200)
                y = int(bbox["top"] - 400 - gap)
            elif "下" in text:
                x = int(bbox["cx"] - 200)
                y = int(bbox["bottom"] + gap)
            elif "左" in text:
                x = int(bbox["left"] - 400 - gap)
                y = int(bbox["cy"] - 200)
            elif "右" in text or "旁边" in text or "边" in text:
                x = int(bbox["right"] + gap)
                y = int(bbox["cy"] - 200)
            else:
                x = int(bbox["right"] + gap)
                y = int(bbox["cy"] - 200)
            return self._fit_image_position((x, y), engine)

        center = self._compute_element_position(text, canvas_elements, engine)
        return self._center_to_image_position(center, engine)

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

    def _extract_quantity(self, text: str) -> int:
        """从文本中提取数量。

        例如 "在大树上画三个苹果" → 3
        "在大树上画一个苹果" → 1
        "在大树上画几个苹果" → 3（默认）
        """
        qty_map: dict[str, int] = {
            "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "2": 2, "3": 3, "4": 4, "5": 5,
            "两": 2,
        }

        # 查数字
        for word, num in qty_map.items():
            if word in text:
                return num

        # "几个"默认 3
        if "几" in text:
            return 3

        return 1

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
            # 数量前缀（含中文数字）
            "画三个", "画两个", "画四个", "画五个", "画六个", "画七个", "画八个", "画九个", "画十个",
            "画两只", "画五只",
            "画三", "画两", "画四", "画五", "画六", "画七", "画八", "画九", "画十",
            "画几",
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
        label = re.sub(r"^(一些|几个|几颗|几条|一棵|一颗|一座|一个|一只|一条|一片|一朵|一辆|一幅|一张|三个|两个|四个|五个|六个|七个|八个|九个|十个|五只|两只)", "", label)
        # 去掉量词前缀（如"朵花" → "花"）
        label = re.sub(r"^[朵株棵个条只头张幅]", "", label)
        label = re.sub(r"(的|漂亮的|可爱的|简单的|单色的|黑色|红色|蓝色|绿色|黄色|白色|紫色|橙色|棕色|灰色|粉色)", "", label)
        return label.strip() or element.strip()

    def _center_to_image_position(self, center: tuple, engine: DrawingEngine) -> tuple:
        """AI 图片以左上角定位，语义规划以中心点定位。"""
        x = int(center[0] - 200)
        y = int(center[1] - 200)
        return self._fit_image_position((x, y), engine)

    def _fit_image_position(self, position: tuple, engine: DrawingEngine) -> tuple:
        """将 400px AI 元素放置在画布内。"""
        x, y = position
        return (
            max(0, min(engine.canvas_width - 400, x)),
            max(0, min(engine.canvas_height - 400, y)),
        )

    def _extract_target_label_from_text(self, text: str) -> str:
        """从“涂满小河/把云换成蓝色”中提取被编辑对象。"""
        candidates = [
            "小溪", "溪流", "小河", "河流", "河",
            "大树", "树", "苹果", "房子", "房屋", "桥", "云", "太阳",
        ]
        for label in candidates:
            if label in text:
                return label
        match = re.search(r"(?:涂满|填充|上色|改|换)[^一-鿿]*([一-鿿]{1,6})", text)
        return match.group(1) if match else ""

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
                    return [RecolorSelectedOperation(
                        color=color_map.get_color(name),
                        target_label=self._extract_target_label_from_text(text),
                        fill=True,
                    )]
                return [ColorOperation(color=color_map.get_color(name))]
        return None
