"""语音绘画上下文代理。

把“这是太阳”“涂满这个圆”“补充细节”这类上下文语音，
转换成可撤销、可继续编辑的本地画布操作。
"""

from __future__ import annotations

import math
from typing import List

from engine.drawing_engine import DrawingEngine
from engine.operations import (
    CircleOperation,
    DrawingOperation,
    LabelSelectedOperation,
    LineDrawOperation,
    RecolorSelectedOperation,
)
from parser import color_map


class DrawingAgent:
    """轻量绘画规划器。

    第一版使用确定性规则保证体验稳定；接口保持为 plan(text, engine)，
    后续可以替换为大模型输出结构化绘画步骤。
    """

    def plan(self, text: str, engine: DrawingEngine) -> List[DrawingOperation]:
        normalized = text.strip()
        if not normalized:
            return []

        label = self._extract_label(normalized)
        if label:
            return [LabelSelectedOperation(label=label)]

        fill_ops = self._plan_fill(normalized)
        if fill_ops:
            return fill_ops

        if self._asks_for_details(normalized):
            return self._plan_details(normalized, engine)

        return []

    def _extract_label(self, text: str) -> str:
        if "太阳" in text and any(word in text for word in ("是", "叫", "画的是")):
            return "太阳"
        return ""

    def _plan_fill(self, text: str) -> List[DrawingOperation]:
        if not any(word in text for word in ("涂满", "填满", "填充", "上色")):
            return []
        color_name = self._match_color_name(text)
        if not color_name:
            return []
        return [RecolorSelectedOperation(color=color_map.get_color(color_name), fill=True)]

    def _match_color_name(self, text: str) -> str:
        for name in sorted(color_map.COLOR_MAP, key=len, reverse=True):
            if name and name in text:
                return name
        return ""

    def _asks_for_details(self, text: str) -> bool:
        return any(word in text for word in ("补充", "细节", "完善", "丰富", "加一点", "加些"))

    def _plan_details(self, text: str, engine: DrawingEngine) -> List[DrawingOperation]:
        target = engine.find_semantic_target("太阳")
        if isinstance(target, CircleOperation):
            return self._sun_detail_ops(target)
        if "太阳" in text:
            target = engine.find_semantic_target()
            if isinstance(target, CircleOperation):
                return [LabelSelectedOperation(label="太阳"), *self._sun_detail_ops(target)]
        return []

    def _sun_detail_ops(self, sun: CircleOperation) -> List[DrawingOperation]:
        cx, cy = sun.center
        inner = sun.radius + 12
        outer = sun.radius + 54
        color = "#FFA500"
        ops: List[DrawingOperation] = []
        for index in range(12):
            angle = math.tau * index / 12
            start = (int(cx + math.cos(angle) * inner), int(cy + math.sin(angle) * inner))
            end = (int(cx + math.cos(angle) * outer), int(cy + math.sin(angle) * outer))
            ray = LineDrawOperation(color=color, size=5, start=start, end=end)
            ray.semantic_label = "太阳光芒"
            ops.append(ray)

        smile_y = int(cy + sun.radius * 0.18)
        eye_offset_x = int(sun.radius * 0.32)
        eye_offset_y = int(sun.radius * 0.18)
        for eye_x in (cx - eye_offset_x, cx + eye_offset_x):
            eye = CircleOperation(
                color="#1D1D1F",
                size=2,
                filled=True,
                center=(int(eye_x), int(cy - eye_offset_y)),
                radius=max(4, sun.radius * 0.08),
            )
            eye.semantic_label = "太阳眼睛"
            ops.append(eye)

        smile = LineDrawOperation(
            color="#1D1D1F",
            size=3,
            start=(int(cx - sun.radius * 0.25), smile_y),
            end=(int(cx + sun.radius * 0.25), smile_y),
        )
        smile.semantic_label = "太阳微笑"
        ops.append(smile)
        return ops
