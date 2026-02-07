import os
import hashlib
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = BASE_DIR / ".env"
ENV_LOADED = load_dotenv(DOTENV_PATH)

def get_key_fingerprint(key):
    if not key:
        return {"present": False, "prefix": None, "sha256_8": None}
    return {
        "present": True,
        "prefix": key[:8] if len(key) >= 8 else key,
        "sha256_8": hashlib.sha256(key.encode()).hexdigest()[:8]
    }

# Project Directories
PROJECT_ROOT = BASE_DIR
BACKEND_DIR = PROJECT_ROOT / "backend"

# Data Directories
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "processed"))
PROCESSED_DATA_DIR = DATA_DIR 

# Model Directories
MODEL_DIR = Path(os.getenv("MODEL_DIR", PROJECT_ROOT / "models"))

# API Keys & LLM Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") # Optional, defaults to None (official)
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 120))

KEY_FINGERPRINT = get_key_fingerprint(OPENAI_API_KEY)

# Settings
DEVICE = "cpu" # Default to CPU for backend
WINDOW_SIZE = 50
