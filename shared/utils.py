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
    STATIC_TEMPLATES, STATIC_OUTPUT, PARAM_REFERENCES_PATH, DATA_ROOT
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
                return pickle.load(f)
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

def load_defaults_old():
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
    default_params = defaults_data["params"]
    default_comments = defaults_data["comments"]
    
    found_models = []
    for folder in folders:
        folder_path = Path(os.path.expanduser(os.path.expandvars(folder)))
        if not folder_path.exists():
            continue
            
        for gguf_file in folder_path.rglob("*.gguf"):
            file_size = format_file_size(gguf_file.stat().st_size)
            found_models.append((gguf_file.name, str(gguf_file), file_size))
    
    # Add new models to database with default parameters and comments
    with sqlite3.connect(str(DB_PATH)) as conn:
        for name, path, size in found_models:
            conn.execute("""
                INSERT OR IGNORE INTO model_configs (model_path, model_name, params_json, comments_json, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (path, name, json.dumps(default_params), json.dumps(default_comments), size))
            
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
    # Import the same utility used in your INI generator
    from .utils import load_defaults 
    
    try:
        # Parse JSON configs for template
        for models in model_groups.values():
            for model in models:
                try:
                    model["params"] = json.loads(model["params_json"])
                except json.JSONDecodeError:
                    model["params"] = {"common": {}, "server": {}, "cli": {}}
        
        cfg = load_scan_cfg()
        # Load defaults to get the server settings
        defaults = load_defaults()
        
        env = Environment(
            loader=FileSystemLoader(str(STATIC_TEMPLATES)),
            autoescape=select_autoescape(["html", "xml"])
        )

        server_gpu_bin = cfg.get("llama_server_gpu_bin", "llama-server")
        server_cpu_bin = cfg.get("llama_server_cpu_bin", "llama-server")
        ini_path = (DATA_ROOT / "llama-server.ini").resolve()
        
        # Extract host and port from defaults nested structure
        # We use .get() safely and check for 'gpu' value
        server_params = defaults.get("params", {}).get("server", {})
        host = server_params.get("--host", {}).get("gpu")
        port = server_params.get("--port", {}).get("gpu")

        # Build strings: Only add the flag if the value exists
        host_flag = f" --host {host}" if host else ""
        port_flag = f" --port {port}" if port else ""

        llama_server_commands = {
            "gpu": f'{server_gpu_bin} --models-preset {ini_path} {host_flag}{port_flag}'.strip(),
            "cpu": f'{server_cpu_bin} --models-preset {ini_path} {host_flag}{port_flag}'.strip()
        }

        # Render template...
        template = env.get_template("model_list.html")
        rendered = template.render(
            model_groups=model_groups,
            SERVER_GPU_BIN=cfg.get("llama_server_gpu_bin", ""),
            SERVER_CPU_BIN=cfg.get("llama_server_cpu_bin", ""),
            CLI_GPU_BIN=cfg.get("llama_cli_gpu_bin", ""),
            CLI_CPU_BIN=cfg.get("llama_cli_cpu_bin", ""),
            llama_server_commands=llama_server_commands,
            css_url="../../static_site/assets/style.css",
            js_url="../../static_site/assets/copy.js"
        )
        
        # Write output...
        output_file = STATIC_OUTPUT / "index.html"  
        STATIC_OUTPUT.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()    
        output_file.write_text(rendered, encoding="utf-8")
        
    except Exception as e:
        print(f"❗ Failed to render static page: {e}")

def render_static_page_0(model_groups):
    """Render static HTML page from model data."""
    try:
        # Parse JSON configs for template
        for models in model_groups.values():
            for model in models:
                try:
                    model["params"] = json.loads(model["params_json"])
                except json.JSONDecodeError:
                    model["params"] = {"common": {}, "server": {}, "cli": {}}
        
        # Get binary paths
        cfg = load_scan_cfg()
        
        # Setup Jinja environment
        env = Environment(
            loader=FileSystemLoader(str(STATIC_TEMPLATES)),
            autoescape=select_autoescape(["html", "xml"])
        )

        # Build GPU and CPU server commands
        server_gpu_bin = cfg.get("llama_server_gpu_bin", "llama-server")
        server_cpu_bin = cfg.get("llama_server_cpu_bin", "llama-server")
        ini_path = (DATA_ROOT / "llama-server.ini").resolve()
        
        # Get the llama-server models directory (or fallback to first folder)
        models_dir = cfg.get("llama_server_models_dir", "")
        if not models_dir:
            folders = cfg.get("folders", [])
            models_dir = folders[0] if folders else "./models"
        
        models_dir = str(Path(os.path.expanduser(os.path.expandvars(models_dir))).resolve())
        
        llama_server_commands = {
            "gpu": f'{server_gpu_bin} --models-preset {ini_path} --models-dir {models_dir}',
            "cpu": f'{server_cpu_bin} --models-preset {ini_path} --models-dir {models_dir}'
        }

        # Render template with relative paths for standalone use
        template = env.get_template("model_list.html")
        rendered = template.render(
            model_groups=model_groups,
            SERVER_GPU_BIN=cfg.get("llama_server_gpu_bin", ""),
            SERVER_CPU_BIN=cfg.get("llama_server_cpu_bin", ""),
            CLI_GPU_BIN=cfg.get("llama_cli_gpu_bin", ""),
            CLI_CPU_BIN=cfg.get("llama_cli_cpu_bin", ""),
            llama_server_commands=llama_server_commands,
            css_url="../../static_site/assets/style.css",
            js_url="../../static_site/assets/copy.js"
        )
        
        # Write output
        output_file = STATIC_OUTPUT / "index.html"  
        STATIC_OUTPUT.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()    
        (STATIC_OUTPUT / "index.html").write_text(rendered, encoding="utf-8")
    except Exception as e:
        print(f"❗ Failed to render static page: {e}")
    
    try:
        generate_llama_server_ini()
        print("✅ Generated llama-server.ini successfully.")
    except Exception as e:
        print(f"❗ Failed to generate llama-server.ini: {e}")

def render_static_page_old_1(model_groups):
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

        server_bin = cfg.get("llama_server_gpu_bin", "llama-server")
        ini_path = STATIC_OUTPUT.parent / "llama-server.ini"
        ini_path = ini_path.resolve()
        llama_server_cmd = f"{server_bin} --config {ini_path}"

        # Render template with relative paths for standalone use
        template = env.get_template("model_list.html")
        rendered = template.render(
            model_groups=model_groups,
            SERVER_GPU_BIN=cfg.get("llama_server_gpu_bin", ""),
            SERVER_CPU_BIN=cfg.get("llama_server_cpu_bin", ""),
            CLI_GPU_BIN=cfg.get("llama_cli_gpu_bin", ""),
            CLI_CPU_BIN=cfg.get("llama_cli_cpu_bin", ""),
            llama_server_cmd=llama_server_cmd, 
            css_url="../../static_site/assets/style.css",
            js_url="../../static_site/assets/copy.js"
        )
        
        # Write output
        STATIC_OUTPUT.mkdir(parents=True, exist_ok=True)
        (STATIC_OUTPUT / "index.html").write_text(rendered, encoding="utf-8")
    except Exception as e:
        print(f"❗ Failed to render static page: {e}")
    
    try:
        generate_llama_server_ini()
        print("✅ Generated llama-server.ini successfully.")
    except Exception as e:
        print(f"❗ Failed to generate llama-server.ini: {e}")


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


def get_help_text(binary_path):
    """Execute --help on binary and return output."""
    try:
        result = subprocess.run([binary_path, '--help'], 
                              capture_output=True, text=True, timeout=10)
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        print(f"Error getting help from {binary_path}: {e}")
        return None


def parse_help_text_directly(server_help, cli_help):
    """Parse help text directly without LLM."""
    import re
    
    def extract_params_by_section(text):
        """Extract parameters organized by section, preserving order."""
        from collections import OrderedDict
        sections = {"common": OrderedDict(), "specific": OrderedDict()}
        lines = text.split('\n')
        current_section = None
        current_param = None
        current_desc = ""
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            
            # Check for section headers
            if line.startswith('----- ') and line.endswith(' -----'):
                # Save any pending parameter
                if current_param and current_desc and current_section in sections:
                    sections[current_section][current_param] = current_desc.strip()
                current_param = None
                current_desc = ""
                
                if 'common' in line.lower() or 'sampling' in line.lower():
                    current_section = "common"
                elif 'example-specific' in line.lower():
                    current_section = "specific"
                else:
                    current_section = "other"
                continue
            
            # Skip empty lines or if no section
            if not line or current_section is None:
                continue
                
            # Check if this is a continuation line (starts with spaces)
            if original_line.startswith('                                        ') and current_param:
                # This is a continuation of the previous description
                current_desc += " " + line
                continue
            
            # Look for parameter lines (start with - or contain --)
            if re.match(r'^-[a-zA-Z]|^--[a-zA-Z]', line):
                # Save previous parameter if exists
                if current_param and current_desc and current_section in sections:
                    sections[current_section][current_param] = current_desc.strip()
                
                # Extract parameter names and description
                parts = re.split(r'\s{2,}', line, 1)  # Split on 2+ spaces
                if len(parts) >= 2:
                    param_part = parts[0].strip()
                    desc_part = parts[1].strip()
                    
                    # Extract all parameter variants from the BEGINNING of the line only
                    # Format is like: "-t, --threads N" or "--port N"
                    param_matches = re.findall(r'(-[a-zA-Z]|--[a-zA-Z][a-zA-Z0-9-]*)', param_part)
                    
                    # Use shortest parameter name as key
                    if param_matches:
                        current_param = min(param_matches, key=len)
                        current_desc = desc_part
                    else:
                        current_param = None
                        current_desc = ""
                else:
                    current_param = None
                    current_desc = ""
        
        # Save final parameter
        if current_param and current_desc and current_section in sections:
            sections[current_section][current_param] = current_desc.strip()
        
        return sections
    
    # Extract parameters from both files by section
    server_sections = extract_params_by_section(server_help)
    cli_sections = extract_params_by_section(cli_help)
    
    # Common parameters are from common/sampling sections of both files
    common_params = {}
    common_params.update(server_sections["common"])
    common_params.update(cli_sections["common"])
    
    # For specific sections, separate truly unique ones from shared ones
    server_specific = server_sections["specific"]
    cli_specific = cli_sections["specific"]
    
    # Move shared "specific" parameters to common
    shared_specific = {}
    server_only = {}
    cli_only = {}
    
    # Find parameters that appear in both specific sections
    for param, desc in server_specific.items():
        if param in cli_specific:
            shared_specific[param] = desc
        else:
            server_only[param] = desc
    
    # Find CLI-only parameters
    for param, desc in cli_specific.items():
        if param not in server_specific:
            cli_only[param] = desc
    
    # Add shared specific parameters to common
    common_params.update(shared_specific)
    
    return {
        "common": [{"param": k, "desc": v} for k, v in common_params.items()],
        "server": [{"param": k, "desc": v} for k, v in server_only.items()],
        "cli": [{"param": k, "desc": v} for k, v in cli_only.items()]
    }


def extract_parameters_directly(server_path, cli_path):
    """Extract parameters using direct parsing of help text."""
    # Get help text from both binaries
    server_help = get_help_text(server_path)
    cli_help = get_help_text(cli_path)
    
    if not server_help or not cli_help:
        return {"error": "Could not get help text from binaries"}
    
    try:
        return parse_help_text_directly(server_help, cli_help)
    except Exception as e:
        return {"error": f"Failed to parse help text: {e}"}


def save_param_references_directly(server_path, cli_path):
    """Generate and save parameter references using direct parsing."""
    print(f"DEBUG: Extracting parameters from {server_path} and {cli_path}")
    
    result = extract_parameters_directly(server_path, cli_path)
    
    if "error" in result:
        print(f"DEBUG: Error in extraction: {result['error']}")
        return False, result["error"]
    
    try:
        print(f"DEBUG: Saving to {PARAM_REFERENCES_PATH}")
        with open(PARAM_REFERENCES_PATH, "w") as f:
            json.dump(result, f, indent=2)
        print("DEBUG: Save successful")
        return True, "Parameters extracted and saved successfully"
    except Exception as e:
        print(f"DEBUG: Save failed: {e}")
        return False, f"Error saving parameters: {e}"

def generate_llama_server_ini():
    """
    Generate a single llama-server.ini containing all models.
    """
    from .config import DATA_ROOT
    from .utils import get_all_models, get_model_config, load_defaults

    defaults = load_defaults()
    params = defaults["params"]
    comments = defaults["comments"]

    lines = []
    lines.append("version = 1")
    lines.append("")

    # -------------------------
    # Global section
    # -------------------------
    lines.append("[*]")

    for key, vals in params.get("common", {}).items():
        val = vals.get("gpu", "")
        comment = comments.get("common", {}).get(key)

        if comment:
            lines.append(f"; {comment}")

        # Remove leading dashes from key
        clean_key = key.lstrip('-')
        
        if val:
            lines.append(f"{clean_key} = {val}")
        else:
            lines.append(f"{clean_key} = true")

    lines.append("")

    # -------------------------
    # Model sections
    # -------------------------
    for row in get_all_models():
        config = get_model_config(row["model_path"])
        if not config:
            continue

        name = config["model_name"]
        model_cfg = config["model_config"]
        model_comments = config["model_comments"]

        is_named = "/" in name or ":" in name
        
        # Make section name unique
        if is_named:
            section = name
        else:
            from pathlib import Path
            model_filename = Path(config['model_path']).stem
            section = model_filename.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "_")

        lines.append(f"[{section}]")

        if not is_named:
            from pathlib import Path
            lines.append(f"model = {Path(config['model_path']).absolute()}")

        def render(section_name):
            for k, v in model_cfg.get(section_name, {}).items():
                val = v.get("gpu", "")
                comment = model_comments.get(section_name, {}).get(k)

                if comment:
                    lines.append(f"; {comment}")

                # Remove leading dashes from key
                clean_key = k.lstrip('-')
                
                if val:
                    lines.append(f"{clean_key} = {val}")
                else:
                    lines.append(f"{clean_key} = true")

        render("common")
        render("server")
        lines.append("")

    ini_path = DATA_ROOT / "llama-server.ini"
    ini_path.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"✅ Generated INI with {len([l for l in lines if l.startswith('[') and l != '[*]'])} model sections")

    return ini_path