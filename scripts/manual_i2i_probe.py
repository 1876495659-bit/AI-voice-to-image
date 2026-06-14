"""手动探测 Agnes I2I 字段名。

此脚本会真实调用远端 Agnes API，只用于人工排查图生图字段兼容性。

用法:
  cd C:\\Users\\DJ\\Desktop\\git\\AI-voice-to-image
  python scripts/manual_i2i_probe.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config


API_BASE = config.AGNES_API_BASE
MODEL = config.AGNES_IMAGE_MODEL
SIZE = config.AGNES_IMAGE_SIZE
KEY = config.AGNES_API_KEY


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    }


def _read_image_bytes(payload: dict) -> bytes:
    img = payload["data"][0]
    if img.get("url"):
        resp = requests.get(img["url"], timeout=30)
        resp.raise_for_status()
        return resp.content
    if img.get("b64_json"):
        return base64.b64decode(img["b64_json"])
    raise RuntimeError("Agnes response contains no image data")


def generate_base_image() -> bytes:
    resp = requests.post(
        f"{API_BASE}/v1/images/generations",
        headers=_headers(),
        json={
            "model": MODEL,
            "prompt": (
                "a simple single-color line drawing of a tree drawn with black ink, "
                "clean white background, no fill colors, no shading"
            ),
            "size": SIZE,
            "n": 1,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return _read_image_bytes(resp.json())


def try_i2i_field(image_bytes: bytes, field: str) -> bytes | None:
    data_uri = f"data:image/png;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    resp = requests.post(
        f"{API_BASE}/v1/images/generations",
        headers=_headers(),
        json={
            "model": MODEL,
            "prompt": "keep the original tree unchanged and add two small apples on the tree",
            "size": SIZE,
            "n": 1,
            field: data_uri,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        print(f"{field}: HTTP {resp.status_code}")
        return None
    return _read_image_bytes(resp.json())


def main() -> None:
    if not KEY:
        raise SystemExit("AGNES_API_KEY 未配置")

    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    base = generate_base_image()
    (output_dir / "manual_i2i_base.png").write_bytes(base)
    print("已生成基础图: output/manual_i2i_base.png")

    for field in ("image", "input_image", "init_image", "image_url"):
        result = try_i2i_field(base, field)
        if result:
            out = output_dir / f"manual_i2i_{field}.png"
            out.write_bytes(result)
            print(f"{field}: 成功，结果已保存到 {out}")
            return

    print("所有候选字段都未成功，请检查 Agnes I2I API 文档。")


if __name__ == "__main__":
    main()
