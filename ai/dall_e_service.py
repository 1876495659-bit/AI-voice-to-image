"""DALL·E 3 图像生成实现。

通过 OpenAI API 实现 DALL·E 3 图像生成。

引用:
- `config.py` — OPENAI_API_KEY, AI_IMAGE_MODEL, AI_IMAGE_SIZE, AI_IMAGE_QUALITY
- `ai/ai_service.py` — AIService 抽象接口
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import openai
from openai import OpenAI
import requests

import config
from ai.ai_service import AIService

logger = logging.getLogger(__name__)


class DalleService(AIService):
    """DALL·E 3 图像生成服务。

    通过 OpenAI REST API 调用 DALL·E 3 生成图像。
    支持图片缓存（相同提示词不重复调用 API）。

    Attributes:
        _client: OpenAI API 客户端。
        _cache: 提示词 → 图片二进制 缓存字典。
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__()

        key = api_key or config.OPENAI_API_KEY
        if not key:
            logger.warning("OPENAI_API_KEY 未设置，AI 图像生成功能不可用")

        self._client = OpenAI(api_key=key) if key else None
        self._cache: dict[str, bytes] = {}

    def generate_image(self, prompt: str) -> Optional[bytes]:
        """使用 DALL·E 3 生成图像。

        优先从缓存返回，缓存未命中时调用 API。

        Args:
            prompt: 图像描述提示词。

        Returns:
            图像的二进制数据 (PNG)，失败返回 None。
        """
        # 检查缓存
        cache_key = self.get_cache_key(prompt)
        if cache_key in self._cache:
            logger.info("AI 图像缓存命中")
            return self._cache[cache_key]

        if self._client is None:
            logger.error("OpenAI API Key 未配置")
            return None

        try:
            response = self._client.images.generate(
                model=config.AI_IMAGE_MODEL,
                prompt=prompt,
                size=config.AI_IMAGE_SIZE,
                quality=config.AI_IMAGE_QUALITY,
                n=1,
            )

            data = response.data[0]

            if data.b64_json:
                # Base64 编码的图像数据
                image_bytes = base64.b64decode(data.b64_json)
            elif data.url:
                # 通过 URL 下载
                resp = requests.get(data.url)
                resp.raise_for_status()
                image_bytes = resp.content
            else:
                logger.error("AI 生成返回空数据")
                return None

            if image_bytes:
                self._cache[cache_key] = image_bytes
                logger.info(f"AI 图像生成成功: {len(image_bytes)} bytes")
                return image_bytes

            return None

        except openai.NotFoundError as e:
            logger.error(f"DALL·E 模型不存在或不可用: {e}")
            return None
        except openai.RateLimitError as e:
            logger.error(f"API 限流: {e}")
            return None
        except openai.APIError as e:
            logger.error(f"API 错误: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"下载图片失败: {e}")
            return None
        except Exception as e:
            logger.error(f"AI 生成失败: {e}")
            return None

    def is_available(self) -> bool:
        """检查 DALL·E 服务是否可用。"""
        if self._client is None:
            return False
        try:
            self._client.models.list(limit=1)
            return True
        except Exception:
            return False

    def clear_cache(self) -> None:
        """清除图像缓存。"""
        self._cache.clear()
