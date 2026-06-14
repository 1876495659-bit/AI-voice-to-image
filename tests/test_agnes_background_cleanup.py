from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from ai.agnes_service import AgnesImageService


def _paper_like_line_art() -> bytes:
    image = Image.new("RGB", (80, 60), "#EEE9DC")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 12, 64, 48), outline="#111111", width=4)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalize_canvas_background_turns_paper_texture_white() -> None:
    service = AgnesImageService(api_key="fake")

    cleaned = service._normalize_canvas_background(_paper_like_line_art())
    result = Image.open(BytesIO(cleaned)).convert("RGB")

    assert result.getpixel((2, 2)) == (255, 255, 255)
    assert result.getpixel((40, 12))[0] < 80


def test_canvas_prompt_rejects_paper_texture_and_shadow() -> None:
    service = AgnesImageService(api_key="fake")

    prompt = service._enhance_for_sketch_style("画一棵树")

    assert "pure white digital canvas background" in prompt
    assert "no paper texture" in prompt
    assert "no drop shadow" in prompt


if __name__ == "__main__":
    test_normalize_canvas_background_turns_paper_texture_white()
    test_canvas_prompt_rejects_paper_texture_and_shadow()
    print("test_agnes_background_cleanup: OK")
