import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

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
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 30))

# Settings
DEVICE = "cpu" # Default to CPU for backend
WINDOW_SIZE = 50
