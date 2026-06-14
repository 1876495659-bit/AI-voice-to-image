"""绘画上下文代理测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.drawing_agent import DrawingAgent
from engine.drawing_engine import DrawingEngine
from engine.operations import (
    AIImageOperation,
    CircleOperation,
    LineDrawOperation,
    RecolorSelectedOperation,
    StrokeGroupOperation,
)


def test_agent_labels_recent_shape_as_sun() -> None:
    """理解“刚刚画的是太阳”，并给当前图形标注语义。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=1080)
    circle = CircleOperation(center=(300, 220), radius=50)
    engine.execute(circle)

    agent = DrawingAgent()
    operations = agent.plan("我刚刚画的是一个太阳", engine)

    assert operations
    engine.execute_multiple(operations)
    assert circle.semantic_label == "太阳"


def test_agent_fills_current_circle_with_yellow() -> None:
    """理解“用黄色涂满这个圆”，生成填充当前图形的操作。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=1080)
    circle = CircleOperation(center=(300, 220), radius=50, color="#000000", filled=False)
    engine.execute(circle)

    agent = DrawingAgent()
    operations = agent.plan("用黄色涂满这个圆", engine)

    assert len(operations) == 1
    assert isinstance(operations[0], RecolorSelectedOperation)
    engine.execute_multiple(operations)
    assert circle.color == "#FFFF00"
    assert circle.filled is True


def test_agent_adds_sun_details_around_labeled_circle() -> None:
    """理解“补充太阳细节”，用画布线条补太阳光芒。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    circle = CircleOperation(center=(300, 220), radius=50, color="#FFFF00")
    circle.semantic_label = "太阳"
    engine.execute(circle)

    agent = DrawingAgent()
    operations = agent.plan("帮我补充一点它的细节", engine)

    rays = [op for op in operations if isinstance(op, LineDrawOperation)]
    assert len(rays) >= 8
    engine.execute_multiple(operations)
    assert any(isinstance(op, LineDrawOperation) for op in engine.get_history())


def test_agent_generates_open_vocabulary_ai_element() -> None:
    """用户要求任意元素时，应交给 Agnes 生成单色画笔元素。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    agent = DrawingAgent()

    operations = agent.plan("画一座房子", engine)

    assert len(operations) == 1
    op = operations[0]
    assert isinstance(op, AIImageOperation)
    assert "房子" in op.prompt
    assert op.semantic_label == "房子"
    assert op.position == (200, 100)


def test_agent_places_open_vocabulary_element_near_reference() -> None:
    """普通开放词汇元素仍能引用之前由模型生成的语义元素位置。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=1080)
    tree = AIImageOperation(prompt="树", position=(200, 80))
    tree.semantic_label = "树"
    engine.history.push(tree)

    agent = DrawingAgent()
    operations = agent.plan("在树的下面画一座房子", engine)

    assert len(operations) == 1
    op = operations[0]
    assert isinstance(op, AIImageOperation)
    assert "房子" in op.prompt
    assert op.semantic_label == "房子"
    assert op.position[1] >= 500


def test_agent_draws_river_right_of_tree_as_canvas_lines() -> None:
    """“在大树右边画河流”应生成融入画布的线条，而不是独立 AI 图片。"""
    engine = DrawingEngine(canvas_width=900, canvas_height=600)
    tree = StrokeGroupOperation(
        color="#000000",
        size=3,
        semantic_label="大树",
        strokes=[
            [(240, 150), (190, 210), (180, 310), (250, 390), (360, 380), (420, 300), (390, 180), (300, 130), (240, 150)],
            [(285, 370), (280, 500), (330, 500), (325, 370)],
        ],
    )
    engine.execute(tree)

    operations = DrawingAgent().plan("在大树的右边画一条河流", engine)

    assert operations
    assert not any(isinstance(op, AIImageOperation) for op in operations)
    assert all(isinstance(op, LineDrawOperation) for op in operations)
    assert all(op.semantic_label == "河流" for op in operations[:5])
    assert min(min(op.start[0], op.end[0]) for op in operations) >= 420
    assert max(max(op.start[0], op.end[0]) for op in operations) <= 860


def test_agent_recolors_named_ai_element() -> None:
    """“用蓝色涂满小河”应按语义目标给小河上色。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    river = AIImageOperation(prompt="小河", position=(100, 420), color="#000000")
    river.semantic_label = "小河"
    engine.execute(river)

    agent = DrawingAgent()
    operations = agent.plan("用蓝色涂满小河", engine)

    assert len(operations) == 1
    op = operations[0]
    assert isinstance(op, RecolorSelectedOperation)
    assert op.color == "#0000FF"
    assert op.target_label == "小河"

    engine.execute_multiple(operations)
    assert river.color == "#0000FF"


def test_agent_places_apples_inside_tree_canopy_as_pen_strokes() -> None:
    """“在树上画苹果”应变成树冠内的小笔画，而不是独立大图覆盖。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    tree = StrokeGroupOperation(
        color="#000000",
        size=3,
        semantic_label="树",
        strokes=[
            [(300, 120), (240, 180), (220, 260), (260, 330), (360, 340), (430, 280), (410, 180), (350, 120), (300, 120)],
            [(315, 330), (310, 430), (350, 430), (345, 330)],
        ],
    )
    engine.execute(tree)

    agent = DrawingAgent()
    operations = agent.plan("在树上画几个红色苹果", engine)

    assert len(operations) == 3
    assert all(isinstance(op, StrokeGroupOperation) for op in operations)
    assert all(op.color == "#FF0000" for op in operations)
    assert all(op.semantic_label == "苹果" for op in operations)

    for op in operations:
        points = [point for stroke in op.strokes for point in stroke]
        assert points
        assert all(220 <= x <= 430 for x, _ in points)
        assert all(120 <= y <= 340 for _, y in points)


def test_agent_places_exact_two_apples_on_tree_without_new_ai_image() -> None:
    """“两个苹果”应只追加两个树冠内笔画苹果。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    tree = StrokeGroupOperation(
        color="#000000",
        size=3,
        semantic_label="大树",
        strokes=[
            [(280, 100), (220, 170), (210, 260), (290, 350), (430, 330), (460, 220), (390, 110), (280, 100)],
            [(330, 330), (320, 470), (370, 470), (360, 330)],
        ],
    )
    engine.execute(tree)

    operations = DrawingAgent().plan("在大树上画两个红色苹果", engine)

    assert len(operations) == 2
    assert all(isinstance(op, StrokeGroupOperation) for op in operations)
    assert not any(isinstance(op, AIImageOperation) for op in operations)
    for op in operations:
        points = [point for stroke in op.strokes for point in stroke]
        assert all(210 <= x <= 460 for x, _ in points)
        assert all(100 <= y <= 350 for _, y in points)


if __name__ == "__main__":
    test_agent_labels_recent_shape_as_sun()
    test_agent_fills_current_circle_with_yellow()
    test_agent_adds_sun_details_around_labeled_circle()
    test_agent_generates_open_vocabulary_ai_element()
    test_agent_places_open_vocabulary_element_near_reference()
    test_agent_draws_river_right_of_tree_as_canvas_lines()
    test_agent_recolors_named_ai_element()
    test_agent_places_apples_inside_tree_canopy_as_pen_strokes()
    test_agent_places_exact_two_apples_on_tree_without_new_ai_image()
    print("test_drawing_agent: OK")
