"""Configuration. Every model id and tunable lives here, nothing is hard-coded."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- keys -------------------------------------------------------------------
def _load_env():
    """Read keys.env if present; real environment variables win."""
    f = ROOT / "keys.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

_load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# --- models -----------------------------------------------------------------
# Vision + planning. Sonnet is enough for both and keeps latency sane.
TEXT_MODEL = os.environ.get("FLOORAI_TEXT_MODEL", "claude-sonnet-4-5-20250929")

# Image generation. Two measured options; see README "Findings".
#   fast    - Nano Banana. ~6s, square, flatter lighting. The default: an
#             interactive generate should not make the user wait.
#   quality - Nano Banana Pro. ~18s, 16:9, markedly more photorealistic.
IMAGE_MODELS = {
    "fast": "gemini-2.5-flash-image",
    "quality": "gemini-3-pro-image",
}
DEFAULT_IMAGE_QUALITY = os.environ.get("FLOORAI_IMAGE_QUALITY", "quality")
IMAGE_MODEL = IMAGE_MODELS[DEFAULT_IMAGE_QUALITY]


def image_model(quality=None):
    """Resolve a quality label to a model id, falling back to the default."""
    return IMAGE_MODELS.get(quality or DEFAULT_IMAGE_QUALITY, IMAGE_MODEL)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")

# --- paths ------------------------------------------------------------------
CATALOG_DIR = ROOT / "catalog"
SCENES_DIR = ROOT / "scenes"
RENDERS_DIR = ROOT / "static" / "renders"
SAMPLES_DIR = ROOT / "samples"

for _d in (SCENES_DIR, RENDERS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- generation defaults ----------------------------------------------------
DEFAULT_VIEWPOINTS = 4
DEFAULT_VARIATIONS = 2
MAX_VIEWPOINTS = 6
MAX_VARIATIONS = 4
