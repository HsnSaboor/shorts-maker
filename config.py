import os
from pathlib import Path

# Add deno to PATH for yt-dlp
os.environ['PATH'] = '/home/saboor/.deno/bin:' + os.environ.get('PATH', '')

# Load .env file if it exists
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

DEEPGRAM_API_KEYS = [k.strip() for k in os.getenv("DEEPGRAM_API_KEYS", os.getenv("DEEPGRAM_API_KEY", "")).split(",") if k.strip()]
USE_DEEPGRAM_FALLBACK = os.getenv("USE_DEEPGRAM_FALLBACK", "true").lower() == "true"

LOCAL_LLM_URL = "http://localhost:8317/v1/chat/completions"
LOCAL_LLM_MODEL = "kiro-glm-5"
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "")

RULES_DIR = "rules"
MASTER_CSV = "master_results.csv"
TEMP_DIR = "temp"
OUTPUT_DIR = "output"

MIN_DURATION = 30
MAX_DURATION = 360

MICRO_PAD = 0.04
SILENCE_THRESHOLD_MIN = 0.2
SILENCE_THRESHOLD_MAX = 0.6

# Virality scoring
MIN_VIRALITY_SCORE = 45

# VPS Configuration
VPS_HOST = os.getenv("VPS_HOST", "http://localhost:8000")

# Google Drive Configuration
GDRIVE_REMOTE_NAME = os.getenv("GDRIVE_REMOTE_NAME", "gdrive")
GDRIVE_LOCAL_SYNC_PATH = os.getenv("GDRIVE_LOCAL_SYNC_PATH", os.path.expanduser("~/Google Drive/shorts-maker"))
