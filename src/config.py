import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
LOGGING_DIR = BASE_DIR / "logging"
TRACE_FILE = BASE_DIR / "trace.jsonl"
TRACE_FILE_LOGGING = LOGGING_DIR / "trace.jsonl"
METADATA_FILE = BASE_DIR / "metadata.json"
METADATA_FILE_LOGGING = LOGGING_DIR / "metadata.json"

# Create output and logging dirs if not exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGGING_DIR.mkdir(parents=True, exist_ok=True)


# Load .env (Check root first, then input/.env)
load_dotenv(BASE_DIR / ".env")
load_dotenv(INPUT_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = "llama-3.1-8b-instant"
MODEL_PARAM_SIZE = "8B"
MODEL_PROVIDER = "Groq"

def get_groq_client():
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing! Please check your .env file.")
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)
