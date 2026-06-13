"""Agnes Image 2.1 Flash 图像生成服务。

通过 Agnes REST API 实现高质量图像生成。
使用 requests 直接调用，兼容 OpenAI 格式的 images.generate 接口。

引用:
- `config.py` — AGNES_API_KEY, AGNES_API_BASE, AGNES_IMAGE_MODEL
- `ai/ai_service.py` — AIService 抽象接口
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import requests

import config
from ai.ai_service import AIService

logger = logging.getLogger(__name__)


class AgnesImageService(AIService):
    """Agnes Image 2.1 Flash 图像生成服务。

    通过 Agnes REST API 生成图像，支持图片缓存。

    Attributes:
        _api_key: API 密钥。
        _api_base: API 基础 URL。
        _cache: 提示词 → 图片二进制 缓存字典。
    """

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None) -> None:
        super().__init__()

        self._api_key = api_key or config.AGNES_API_KEY
        self._api_base = api_base or config.AGNES_API_BASE
        self._cache: dict[str, bytes] = {}

    SKETCH_PREFIX = (
        "sketch style, hand-drawn pencil drawing, charcoal sketch, "
        "rough edges, artistic illustration, white background, "
    )

    _SKETCH_WORDS = frozenset((
        "sketch", "drawing", "pencil", "hand-drawn", "charcoal",
        "草图", "素描", "手绘", "素描画",
    ))

    def _enhance_for_sketch_style(self, prompt: str) -> str:
        """确保提示词导向手绘素描风格。"""
        if any(w in prompt.lower() for w in self._SKETCH_WORDS):
            return prompt
        return f"{self.SKETCH_PREFIX}{prompt}"

    def generate_image(self, prompt: str) -> Optional[bytes]:
        """使用 Agnes Image 2.1 Flash 生成图像。

        优先从缓存返回，缓存未命中时调用 API。
        自动为提示词追加手绘素描风格引导。

        Args:
            prompt: 图像描述提示词。

        Returns:
            图像的二进制数据 (PNG/JPEG)，失败返回 None。
        """
        if not self._api_key:
            logger.error("AGNES_API_KEY 未配置")
            return None

        # 手绘风格化
        sketch_prompt = self._enhance_for_sketch_style(prompt)
        cache_key = self.get_cache_key(sketch_prompt)
        if cache_key in self._cache:
            logger.info("Agnes 图像缓存命中")
            return self._cache[cache_key]

        try:
            resp = requests.post(
                f"{self._api_base}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.AGNES_IMAGE_MODEL,
                    "prompt": prompt,
                    "size": config.AGNES_IMAGE_SIZE,
                    "n": 1,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            images = data.get("data", [])
            if not images:
                logger.error("Agnes 生成返回空数据")
                return None

            img = images[0]

            # Agnes 优先返回 url
            if img.get("url"):
                img_resp = requests.get(img["url"], timeout=30)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
            elif img.get("b64_json"):
                import base64
                image_bytes = base64.b64decode(img["b64_json"])
            else:
                logger.error("Agnes 生成返回空数据")
                return None

            if image_bytes:
                self._cache[cache_key] = image_bytes
                logger.info(f"Agnes 图像生成成功: {len(image_bytes)} bytes")
                return image_bytes

            return None

        except requests.exceptions.Timeout:
            logger.error("Agnes API 请求超时")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"Agnes API HTTP 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"Agnes 生成失败: {e}")
            return None

    def is_available(self) -> bool:
        """检查 Agnes 服务是否可用。"""
        try:
            resp = requests.get(
                f"{self._api_base}/v1/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def clear_cache(self) -> None:
        """清除图像缓存。"""
        self._cache.clear()
