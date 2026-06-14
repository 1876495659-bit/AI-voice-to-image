"""将 AI 线稿图片提取为画布笔画。"""

from __future__ import annotations

from PyQt6.QtGui import QImage

from engine.operations import StrokeGroupOperation


class StrokeExtractor:
    """把白底单色线稿转成一组可编辑笔画。"""

    def extract(
        self,
        image_bytes: bytes,
        position: tuple = (0, 0),
        label: str = "",
        color: str = "#000000",
        size: int = 3,
        max_width: int = 400,
        max_height: int = 400,
    ) -> StrokeGroupOperation:
        image = QImage()
        if not image.loadFromData(image_bytes):
            return StrokeGroupOperation(color=color, size=size, semantic_label=label)

        min_x, min_y, max_x, max_y = self._content_bounds(image)
        if min_x > max_x or min_y > max_y:
            return StrokeGroupOperation(color=color, size=size, semantic_label=label)

        strokes: list[list[tuple]] = []
        sample_step = 2
        scale = self._fit_scale(
            max_x - min_x + 1,
            max_y - min_y + 1,
            max_width,
            max_height,
        )
        for y in range(min_y, max_y + 1, sample_step):
            run_start: int | None = None
            last_x = min_x
            for x in range(min_x, max_x + 1, sample_step):
                if self._is_ink(image, x, y):
                    if run_start is None:
                        run_start = x
                    last_x = x
                elif run_start is not None:
                    self._append_run(strokes, run_start, last_x, y, min_x, min_y, position, scale)
                    run_start = None
            if run_start is not None:
                self._append_run(strokes, run_start, last_x, y, min_x, min_y, position, scale)

        op = StrokeGroupOperation(color=color, size=size, strokes=strokes)
        op.semantic_label = label
        return op

    def _append_run(
        self,
        strokes: list[list[tuple]],
        run_start: int,
        run_end: int,
        y: int,
        min_x: int,
        min_y: int,
        position: tuple,
        scale: float,
    ) -> None:
        if run_end - run_start < 2:
            return
        x0 = position[0] + int((run_start - min_x) * scale)
        x1 = position[0] + int((run_end - min_x) * scale)
        yy = position[1] + int((y - min_y) * scale)
        if x0 == x1:
            x1 += 1
        strokes.append([(x0, yy), (x1, yy)])

    def _fit_scale(
        self,
        content_width: int,
        content_height: int,
        max_width: int,
        max_height: int,
    ) -> float:
        if content_width <= 0 or content_height <= 0:
            return 1.0
        return min(
            1.0,
            max_width / content_width,
            max_height / content_height,
        )

    def _content_bounds(self, image: QImage) -> tuple[int, int, int, int]:
        min_x, min_y = image.width(), image.height()
        max_x, max_y = -1, -1
        for y in range(image.height()):
            for x in range(image.width()):
                if self._is_ink(image, x, y):
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        return min_x, min_y, max_x, max_y

    def _is_ink(self, image: QImage, x: int, y: int) -> bool:
        color = image.pixelColor(x, y)
        return color.alpha() > 10 and color.lightnessF() < 0.72
