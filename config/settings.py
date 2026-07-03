import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from a .env file if it exists
load_dotenv(override=True)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
WORKSPACE_DIR = BASE_DIR / "workspace"
MCP_DIR = BASE_DIR / "mcp"
AGENTS_DIR = BASE_DIR / "agents"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
MCP_DIR.mkdir(parents=True, exist_ok=True)
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

# Data paths
CALENDAR_DATA_PATH = CONFIG_DIR / "simulated_calendar.json"
EMAIL_DATA_PATH = CONFIG_DIR / "simulated_emails.json"

# API Settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
AZURE_API_BASE = os.environ.get("AZURE_API_BASE")
AZURE_API_VERSION = os.environ.get("AZURE_API_VERSION", "2024-02-01")

# Server settings
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "127.0.0.1")
