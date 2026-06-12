"""AI 服务抽象接口。

定义 AI 图像生成服务的统一接口，支持多种后端实现（DALL-E、Stable Diffusion 等）。

引用:
- `config.py` — OPENAI_API_KEY, AI_IMAGE_MODEL, AI_IMAGE_SIZE
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

import config

logger = logging.getLogger(__name__)


class AIService(ABC):
    """AI 图像生成服务抽象基类。

    所有 AI 图像生成后端必须实现此接口。
    """

    @abstractmethod
    def generate_image(self, prompt: str) -> Optional[bytes]:
        """根据提示词生成图像。

        Args:
            prompt: 图像描述提示词。

        Returns:
            图像的二进制数据 (PNG/JPEG)，失败返回 None。
        """

    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用（API Key 配置、网络等）。"""

    def get_cache_key(self, prompt: str) -> str:
        """根据提示词生成缓存键。

        Args:
            prompt: 提示词文本。

        Returns:
            SHA256 哈希前 16 位。
        """
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
