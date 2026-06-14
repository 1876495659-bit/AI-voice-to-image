from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.drawing_engine import DrawingEngine
from engine.operations import AIImageOperation


class FakeCanvasImageService:
    def __init__(self):
        self.generated_prompts = []
        self.extended_calls = []

    def generate_image(self, prompt):
        self.generated_prompts.append(prompt)
        return b"first-canvas"

    def extend_image(self, prev_image_bytes, prompt):
        self.extended_calls.append((prev_image_bytes, prompt))
        return b"second-canvas"


class SlowCanvasImageService(FakeCanvasImageService):
    def generate_image(self, prompt):
        time.sleep(0.4)
        return super().generate_image(prompt)


def test_canvas_i2i_uses_previous_canvas_and_updates_undo_state():
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    service = FakeCanvasImageService()
    engine.ai_service = service

    assert engine.execute_canvas_i2i("画一棵树") is True

    assert len(engine.get_history()) == 1
    first = engine.get_history()[-1]
    assert isinstance(first, AIImageOperation)
    assert first.full_canvas is True
    assert first.image_bytes == b"first-canvas"
    assert service.generated_prompts
    assert "画一棵树" in service.generated_prompts[0]
    assert "不要纸张纹理" in service.generated_prompts[0]
    assert "不要投影" in service.generated_prompts[0]

    assert engine.execute_canvas_i2i("在树上长两个苹果") is True

    assert len(engine.get_history()) == 2
    second = engine.get_history()[-1]
    assert isinstance(second, AIImageOperation)
    assert second.full_canvas is True
    assert second.image_bytes == b"second-canvas"
    assert service.extended_calls[0][0] == b"first-canvas"
    assert "在树上长两个苹果" in service.extended_calls[0][1]

    undone = engine.undo()

    assert undone == second
    assert engine._i2i_current_image_bytes == b"first-canvas"


def test_canvas_i2i_can_run_in_background_without_blocking_ui_thread():
    engine = DrawingEngine(canvas_width=800, canvas_height=600)
    engine.ai_service = SlowCanvasImageService()

    started_at = time.perf_counter()
    assert engine.start_canvas_i2i("画一棵树") is True
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.2
    assert engine.is_canvas_i2i_busy() is True

    deadline = time.perf_counter() + 2
    while engine.is_canvas_i2i_busy() and time.perf_counter() < deadline:
        time.sleep(0.02)

    assert engine.is_canvas_i2i_busy() is False
    assert len(engine.get_history()) == 1


if __name__ == "__main__":
    test_canvas_i2i_uses_previous_canvas_and_updates_undo_state()
    test_canvas_i2i_can_run_in_background_without_blocking_ui_thread()
    print("test_model_canvas_i2i passed")
