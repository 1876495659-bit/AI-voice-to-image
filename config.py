"""
Global configuration for the AI Voice Drawing Tool.
"""
import os
from pathlib import Path

# Load .env file for local development
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# ── Whisper Settings ──────────────────────────────────────────────
# Model size: "tiny" < "base" < "small" < "medium" < "large"
# base: fastest on CPU (~1s per 10s audio), good accuracy
# small: slower (~2s), better accuracy — used as fallback
WHISPER_MODEL_SIZE: str = "base"
WHISPER_FALLBACK_MODEL: str = "small"
WHISPER_FALLBACK_THRESHOLD: float = 0.55  # Retry with fallback model only when base is clearly uncertain

# Use CUDA if available (set True only if you have an NVIDIA GPU with CUDA)
WHISPER_USE_CUDA: bool = False

# ── Voice Settings ────────────────────────────────────────────────
AUDIO_SAMPLE_RATE: int = 16000
AUDIO_CHUNK_DURATION: float = 2.0  # seconds of audio per Whisper batch
AUDIO_VOLUME_THRESHOLD: float = 0.006  # VAD threshold — tuned above observed background noise

# ── UI Settings ───────────────────────────────────────────────────
CANVAS_DEFAULT_WIDTH: int = 1920
CANVAS_DEFAULT_HEIGHT: int = 1080
CANVAS_BACKGROUND_COLOR: str = "#FFFFFF"  # White background

# ── Undo History ──────────────────────────────────────────────────
MAX_UNDO_HISTORY: int = 50

# ── AI Image Generation ──────────────────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
AI_IMAGE_MODEL: str = "dall-e-3"
AI_IMAGE_SIZE: str = "1024x1024"
AI_IMAGE_QUALITY: str = "standard"

# Agnes Image 2.1 Flash
AGNES_API_KEY: str = os.environ.get("AGNES_API_KEY", "")
AGNES_API_BASE: str = "https://apihub.agnes-ai.com"
AGNES_IMAGE_MODEL: str = "agnes-image-2.1-flash"
AGNES_IMAGE_SIZE: str = "1024x1024"

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parent
OUTPUT_DIR: Path = BASE_DIR / "output"
