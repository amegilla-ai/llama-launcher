"""
Utility functions for the GGUF model launcher.
"""
import json
import os
import pickle
import sqlite3
import subprocess
import re
from collections import defaultdict
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import (
    DB_PATH, DEFAULTS_PATH, SCAN_CFG_PATH, DEFAULT_SCAN_CFG,
    STATIC_TEMPLATES, STATIC_OUTPUT
)


# Database operations
def init_db():
    """Initialize the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_path TEXT UNIQUE,
                model_name TEXT,
                params_json TEXT,
                comments_json TEXT DEFAULT '{}',
                file_size TEXT DEFAULT 'N/A'
            )
        """)
        # Add columns to existing tables
        try:
            conn.execute("ALTER TABLE model_configs ADD COLUMN comments_json TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE model_configs ADD COLUMN file_size TEXT DEFAULT 'N/A'")
        except sqlite3.OperationalError:
            pass  # Column already exists


def get_all_models():
    """Get all model configurations from database."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM model_configs").fetchall()


def get_model_config(path):
    """Get configuration for a specific model."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT model_name, params_json, comments_json FROM model_configs WHERE model_path=?", 
                (path,)
            ).fetchone()
            
            if not row:
                return None
            
            params = json.loads(row["params_json"])
            comments = json.loads(row["comments_json"] or "{}")
            
            # Handle old format migration
            if "gpu" in params and "cpu" in params:
                # Old format - migrate to new structure
                old_params = params
                old_comments = comments
                
                new_params = {"common": {}, "server": {}, "cli": {}}
                new_comments = {"common": {}, "server": {}, "cli": {}}
                
                # Migrate old GPU/CPU structure to new common structure
                all_keys = set()
                if "gpu" in old_params:
                    all_keys.update(old_params["gpu"].keys())
                if "cpu" in old_params:
                    all_keys.update(old_params["cpu"].keys())
                
                for key in all_keys:
                    gpu_val = old_params.get("gpu", {}).get(key, "")
                    cpu_val = old_params.get("cpu", {}).get(key, "")
                    gpu_comment = old_comments.get("gpu", {}).get(key, "")
                    cpu_comment = old_comments.get("cpu", {}).get(key, "")
                    
                    # Put everything in common for now
                    new_params["common"][key] = {"gpu": gpu_val, "cpu": cpu_val}
                    comment = gpu_comment or cpu_comment
                    if comment:
                        new_comments["common"][key] = comment
                
                params = new_params
                comments = new_comments
                
            return {
                "model_path": path,
                "model_name": row["model_name"],
                "model_config": params,
                "model_comments": comments
            }
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def update_model_config(path, params, comments=None):
    """Update model configuration in database."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            if comments is not None:
                conn.execute(
                    "UPDATE model_configs SET params_json=?, comments_json=? WHERE model_path=?",
                    (json.dumps(params), json.dumps(comments), path)
                )
            else:
                conn.execute(
                    "UPDATE model_configs SET params_json=? WHERE model_path=?",
                    (json.dumps(params), path)
                )
            return True
    except sqlite3.Error:
        return False


# Configuration management
def load_defaults():
    """Load global default parameters."""
    if DEFAULTS_PATH.exists():
        try:
            with open(DEFAULTS_PATH, "rb") as f:
                data = pickle.load(f)
                # Handle old format migration
                if isinstance(data, dict) and "params" in data and "gpu" in data["params"]:
                    # Old format - migrate to new structure
                    old_params = data["params"]
                    old_comments = data.get("comments", {"gpu": {}, "cpu": {}})
                    
                    new_data = {
                        "params": {"common": {}, "server": {}, "cli": {}},
                        "comments": {"common": {}, "server": {}, "cli": {}}
                    }
                    
                    # Migrate old GPU/CPU structure to new common structure
                    all_keys = set()
                    if "gpu" in old_params:
                        all_keys.update(old_params["gpu"].keys())
                    if "cpu" in old_params:
                        all_keys.update(old_params["cpu"].keys())
                    
                    for key in all_keys:
                        gpu_val = old_params.get("gpu", {}).get(key, "")
                        cpu_val = old_params.get("cpu", {}).get(key, "")
                        gpu_comment = old_comments.get("gpu", {}).get(key, "")
                        cpu_comment = old_comments.get("cpu", {}).get(key, "")
                        
                        # Put everything in common for now
                        new_data["params"]["common"][key] = {"gpu": gpu_val, "cpu": cpu_val}
                        comment = gpu_comment or cpu_comment
                        if comment:
                            new_data["comments"]["common"][key] = comment
                    
                    return new_data
                
                return data
        except Exception:
            pass
    
    return {
        "params": {
            "common": {
                "-c": {"gpu": "16384", "cpu": "16384"},
                "--no-mmap": {"gpu": "", "cpu": ""}
            },
            "server": {
                "--port": {"gpu": "8080", "cpu": "8080"},
                "--host": {"gpu": "0.0.0.0", "cpu": "0.0.0.0"}
            },
            "cli": {
                "--interactive": {"gpu": "", "cpu": ""}
            }
        },
        "comments": {"common": {}, "server": {}, "cli": {}}
    }


def save_defaults(params, comments):
    """Save global default parameters."""
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"params": params, "comments": comments}
    with open(DEFAULTS_PATH, "wb") as f:
        pickle.dump(data, f)


def load_scan_cfg():
    """Load scan configuration."""
    if SCAN_CFG_PATH.exists():
        try:
            with open(SCAN_CFG_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return DEFAULT_SCAN_CFG.copy()


def save_scan_cfg(cfg):
    """Save scan configuration."""
    # Merge with defaults to ensure all keys exist
    full_cfg = DEFAULT_SCAN_CFG.copy()
    full_cfg.update(cfg)
    
    SCAN_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCAN_CFG_PATH, "wb") as f:
        pickle.dump(full_cfg, f)


# Model scanning
def scan_models():
    """Scan configured folders for GGUF models."""
    folders = load_scan_cfg().get("folders", [])
    defaults_data = load_defaults()
    defaults = defaults_data["params"]
    
    found_models = []
    for folder in folders:
        folder_path = Path(os.path.expanduser(os.path.expandvars(folder)))
        if not folder_path.exists():
            continue
            
        for gguf_file in folder_path.rglob("*.gguf"):
            file_size = format_file_size(gguf_file.stat().st_size)
            found_models.append((gguf_file.name, str(gguf_file), file_size))
    
    # Add new models to database
    with sqlite3.connect(str(DB_PATH)) as conn:
        for name, path, size in found_models:
            conn.execute("""
                INSERT OR IGNORE INTO model_configs (model_path, model_name, params_json, comments_json, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (path, name, json.dumps(defaults), json.dumps({}), size))
            
        # Update file sizes for existing models
        for name, path, size in found_models:
            conn.execute("""
                UPDATE model_configs SET file_size = ? WHERE model_path = ?
            """, (size, path))


# Utility functions
def format_file_size(size_bytes):
    """Format file size in human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def group_models_by_directory(models):
    """Group models by their parent directory."""
    groups = defaultdict(list)
    
    for model in models:
        path = model["model_path"]
        if not path:
            continue
            
        dir_name = Path(path).parent.name or "root"
        model_dict = dict(model)
        
        # Use stored file size, fallback to calculation if needed
        if not model_dict.get("file_size") or model_dict["file_size"] == "N/A":
            if os.path.exists(path):
                model_dict["file_size"] = format_file_size(os.path.getsize(path))
            else:
                model_dict["file_size"] = "N/A"
            
        groups[dir_name].append(model_dict)
    
    return dict(sorted(groups.items()))


def render_static_page(model_groups):
    """Render static HTML page from model data."""
    try:
        # Parse JSON configs for template
        for models in model_groups.values():
            for model in models:
                try:
                    params = json.loads(model["params_json"])
                    
                    # Handle old format migration
                    if "gpu" in params and "cpu" in params:
                        # Old format - migrate to new structure
                        old_params = params
                        new_params = {"common": {}, "server": {}, "cli": {}}
                        
                        # Migrate old GPU/CPU structure to new common structure
                        all_keys = set()
                        if "gpu" in old_params:
                            all_keys.update(old_params["gpu"].keys())
                        if "cpu" in old_params:
                            all_keys.update(old_params["cpu"].keys())
                        
                        for key in all_keys:
                            gpu_val = old_params.get("gpu", {}).get(key, "")
                            cpu_val = old_params.get("cpu", {}).get(key, "")
                            new_params["common"][key] = {"gpu": gpu_val, "cpu": cpu_val}
                        
                        model["params"] = new_params
                    else:
                        model["params"] = params
                        
                except json.JSONDecodeError:
                    model["params"] = {"common": {}, "server": {}, "cli": {}}
        
        # Get binary paths
        cfg = load_scan_cfg()
        
        # Setup Jinja environment
        env = Environment(
            loader=FileSystemLoader(str(STATIC_TEMPLATES)),
            autoescape=select_autoescape(["html", "xml"])
        )
        
        # Render template with relative paths for standalone use
        template = env.get_template("model_list.html")
        rendered = template.render(
            model_groups=model_groups,
            SERVER_GPU_BIN=cfg.get("llama_server_gpu_bin", ""),
            SERVER_CPU_BIN=cfg.get("llama_server_cpu_bin", ""),
            CLI_GPU_BIN=cfg.get("llama_cli_gpu_bin", ""),
            CLI_CPU_BIN=cfg.get("llama_cli_cpu_bin", ""),
            css_url="../../static_site/assets/style.css",
            js_url="../../static_site/assets/copy.js"
        )
        
        # Write output
        STATIC_OUTPUT.mkdir(parents=True, exist_ok=True)
        (STATIC_OUTPUT / "index.html").write_text(rendered, encoding="utf-8")
    except Exception as e:
        print(f"❗ Failed to render static page: {e}")


def get_llama_server_bin():
    """Get llama-server binary path."""
    return load_scan_cfg().get("llama_server_bin", "")


def get_llama_cli_bin():
    """Get llama-cli binary path."""
    return load_scan_cfg().get("llama_cli_bin", "")

def load_param_references():
    """Load parameter references from file."""
    ref_file = DEFAULTS_PATH.parent / "param_references.json"
    if ref_file.exists():
        try:
            with open(ref_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"common": {}, "server": {}, "cli": {}}
