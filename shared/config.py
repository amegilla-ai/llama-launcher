# shared/config.py
"""
Central configuration for the launcher.

All persistent files are stored under a single folder called ``data/`` at the
project root.  This makes the layout simple and portable.
"""

import os
from pathlib import Path

# ----------------------------------------------------------------------
# 0️⃣  Project‑root (directory that contains app.py)
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent   # 

# ----------------------------------------------------------------------
# 1️⃣  Data folder – everything that should survive restarts lives here
# ----------------------------------------------------------------------
DATA_ROOT = PROJECT_ROOT / "data"

# Ensure the folder exists the first time we import this module
DATA_ROOT.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# 2️⃣  Paths for the SQLite DB and the two pickle files
# ----------------------------------------------------------------------
DB_PATH        = DATA_ROOT / "model_params.db"
DEFAULTS_PATH  = DATA_ROOT / "defaults.pkl"
SCAN_CFG_PATH  = DATA_ROOT / "folders.pkl"

# ----------------------------------------------------------------------
# 3️⃣  Default values (unchanged from your original defaults)
# ----------------------------------------------------------------------
DEFAULT_PARAMS = {
    "gpu": {"-c": "16384", "--flash-attn": "on", "--no-mmap": ""},
    "cpu": {"-c": "16384", "--no-mmap": ""},
}
DEFAULT_FOLDERS = ["~/.cache", "~/ComfyUI"]
DEFAULT_SCAN_CFG = {
    "folders": DEFAULT_FOLDERS,
    "llama_server_bin": os.path.expanduser("~/llama.cpp/build/bin/llama-server"),
    "llama_cli_bin":    os.path.expanduser("~/llama.cpp/build/bin/llama-cli")
}

# ----------------------------------------------------------------------
# 4️⃣  Paths used by the static‑site generator
# ----------------------------------------------------------------------
STATIC_TEMPLATES = PROJECT_ROOT / "static_site" / "templates"
STATIC_OUTPUT    = DATA_ROOT / "static_site"   # <-- generated files live here

# ----------------------------------------------------------------------
# 4️⃣  (Optional) expose the template / static folders for the admin UI
# ----------------------------------------------------------------------
ADMIN_TEMPLATES = PROJECT_ROOT / "admin_app" / "templates"
ADMIN_STATIC    = PROJECT_ROOT / "admin_app" / "static"