"""整图快照时间线测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.operations import CircleOperation
from ui.canvas_widget import CanvasWidget
from ui.history_timeline import HistoryTimelinePanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_canvas_can_render_full_picture_snapshot() -> None:
    """画布应能把当前整幅画渲染成缩略图。"""
    app = _app()
    canvas = CanvasWidget(width=320, height=240)
    circle = CircleOperation(center=(160, 120), radius=40, color="#000000")

    snapshot = canvas.render_snapshot([circle], max_width=160, max_height=120)

    assert isinstance(snapshot, QPixmap)
    assert not snapshot.isNull()
    assert snapshot.width() <= 160
    assert snapshot.height() <= 120
    assert app is not None


def test_timeline_displays_picture_snapshots() -> None:
    """右侧时间线应显示每一步整幅画快照，而不是只有文字操作。"""
    app = _app()
    panel = HistoryTimelinePanel()
    pixmap = QPixmap(120, 80)
    pixmap.fill(QColor("#FFFFFF"))

    panel.update_snapshots([("第 1 步：画一棵树", pixmap)])

    assert panel.timeline_list.count() == 1
    item = panel.timeline_list.item(0)
    assert "第 1 步" in item.text()
    assert not item.icon().isNull()
    assert app is not None


if __name__ == "__main__":
    test_canvas_can_render_full_picture_snapshot()
    test_timeline_displays_picture_snapshots()
    print("test_history_timeline_snapshots: OK")
