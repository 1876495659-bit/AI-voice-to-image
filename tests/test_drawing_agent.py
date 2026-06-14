"""绘画上下文代理测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.drawing_agent import DrawingAgent
from engine.drawing_engine import DrawingEngine
from engine.operations import CircleOperation, LineDrawOperation, RecolorSelectedOperation


def test_agent_labels_recent_shape_as_sun() -> None:
    """理解“刚刚画的是太阳”，并给当前图形标注语义。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    circle = CircleOperation(center=(300, 220), radius=50)
    engine.execute(circle)

    agent = DrawingAgent()
    operations = agent.plan("我刚刚画的是一个太阳", engine)

    assert operations
    engine.execute_multiple(operations)
    assert circle.semantic_label == "太阳"


def test_agent_fills_current_circle_with_yellow() -> None:
    """理解“用黄色涂满这个圆”，生成填充当前图形的操作。"""
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
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


if __name__ == "__main__":
    test_agent_labels_recent_shape_as_sun()
    test_agent_fills_current_circle_with_yellow()
    test_agent_adds_sun_details_around_labeled_circle()
    print("test_drawing_agent: OK")
