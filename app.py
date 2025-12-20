#!/usr/bin/env python3
import os
import json
import sqlite3
import pickle
from pathlib import Path
from collections import defaultdict
from flask import Flask, render_template, request, redirect

app = Flask(__name__)
DB_PATH = os.path.expanduser("~/models/model_params.db")
DEFAULTS_PATH = os.path.expanduser("~/models/defaults.pkl")
FOLDERS_PATH = os.path.expanduser("~/models/folders.pkl")

# UPDATED: Only GPU and CPU modes
DEFAULT_PARAMS = {
    "gpu": {
        "-c": "16384",
        "--flash-attn": "on",
        "--no-mmap": ""
    },
    "cpu": {
        "-c": "16384",
        "--no-mmap": ""
    },
}

# Default folders to scan
DEFAULT_FOLDERS = [
    "~/.cache",
    "~/ComfyUI",
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Ensure the directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_path TEXT UNIQUE,
            model_name TEXT,
            params_json TEXT
        );
    """)
    conn.commit()
    conn.close()

# ADDED: Functions for default parameters
def load_defaults():
    """Load default parameters from file, or return built-in defaults"""
    if os.path.exists(DEFAULTS_PATH):
        try:
            with open(DEFAULTS_PATH, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return DEFAULT_PARAMS.copy()

def save_defaults(defaults):
    """Save default parameters to file"""
    os.makedirs(os.path.dirname(DEFAULTS_PATH), exist_ok=True)
    with open(DEFAULTS_PATH, 'wb') as f:
        pickle.dump(defaults, f)

def load_folders():
    """Load scan folders from file, or return default folders"""
    if os.path.exists(FOLDERS_PATH):
        try:
            with open(FOLDERS_PATH, 'rb') as f:
                folders = pickle.load(f)
                # Filter out empty strings
                return [f for f in folders if f.strip()]
        except:
            pass
    return DEFAULT_FOLDERS.copy()

def save_folders(folders):
    """Save scan folders to file"""
    os.makedirs(os.path.dirname(FOLDERS_PATH), exist_ok=True)
    with open(FOLDERS_PATH, 'wb') as f:
        pickle.dump(folders, f)

# UPDATED: Now uses load_folders()
def scan_models():
    """Scan configured folders for .gguf files"""
    home = Path.home()
    
    # Load configured folders
    folder_list = load_folders()
    search_dirs = []
    
    for folder in folder_list:
        # Expand ~ and environment variables
        expanded = os.path.expanduser(os.path.expandvars(folder))
        path = Path(expanded)
        if path.exists():
            search_dirs.append(path)
        else:
            print(f"Warning: Folder does not exist: {folder}")

    found = []
    for base in search_dirs:
        if base.exists():
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.endswith(".gguf"):
                        full = os.path.join(root, f)
                        found.append((f, full))

    # Load current defaults (either saved or built-in)
    current_defaults = load_defaults()

    conn = db()
    try:
        for name, path in found:
            exists = conn.execute(
                "SELECT id FROM model_configs WHERE model_path=?",
                (path,)
            ).fetchone()

            if not exists:
                conn.execute(
                    "INSERT INTO model_configs (model_path, model_name, params_json) VALUES (?,?,?)",
                    (path, name, json.dumps(current_defaults))
                )
        conn.commit()
    finally:
        conn.close()

# UPDATED: Added try/finally for connection management
def get_all_models():
    conn = db()
    try:
        return conn.execute("SELECT * FROM model_configs").fetchall()
    finally:
        conn.close()

def load_model_config(path):
    conn = db()
    try:
        row = conn.execute(
            "SELECT params_json FROM model_configs WHERE model_path=?",
            (path,)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["params_json"])
    finally:
        conn.close()

def save_model_config(path, config):
    conn = db()
    try:
        conn.execute(
            "UPDATE model_configs SET params_json=? WHERE model_path=?",
            (json.dumps(config), path)
        )
        conn.commit()
    finally:
        conn.close()

# ADDED: Helper function to format file size
def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

# ADDED: Helper function for grouping models
def group_models_by_directory(models):
    """Group models by their parent directory and add file size"""
    grouped = defaultdict(list)
    
    for model in models:
        path = model["model_path"]
        # Get the parent directory
        parent_dir = os.path.dirname(path)
        # Use the last part of the directory path as the key
        dir_name = os.path.basename(parent_dir) if parent_dir else "root"
        
        # Add file size to model dict
        model_dict = dict(model)
        if os.path.exists(path):
            size_bytes = os.path.getsize(path)
            model_dict['file_size'] = format_file_size(size_bytes)
        else:
            model_dict['file_size'] = 'N/A'
        
        grouped[dir_name].append(model_dict)
    
    # Sort by directory name
    return dict(sorted(grouped.items()))

# ADDED: Custom Jinja filter
@app.template_filter('dirname')
def dirname_filter(path):
    """Extract directory name from path"""
    return os.path.dirname(path)

# UPDATED: Now uses grouping
@app.route("/")
def index():
    scan_models()
    models = get_all_models()
    model_groups = group_models_by_directory(models)
    return render_template("index.html", model_groups=model_groups)

# UPDATED: Now fetches model_name too
@app.route("/edit")
def edit():
    path = request.args.get("path")
    
    conn = db()
    try:
        row = conn.execute(
            "SELECT model_name, params_json FROM model_configs WHERE model_path=?",
            (path,)
        ).fetchone()
        
        if not row:
            return "Model not found", 404
            
        model_name = row["model_name"]
        config = json.loads(row["params_json"])
        
        return render_template("edit.html", 
                             model_path=path, 
                             model_name=model_name,
                             model_config=config)
    finally:
        conn.close()

@app.route("/save", methods=["POST"])
def save():
    path = request.form.get("model_path")

    model_config = load_model_config(path)
    
    # Reset both modes
    model_config['gpu'] = {}
    model_config['cpu'] = {}

    # Build a mapping of unique IDs to key-value pairs
    pairs = {}
    for form_key, form_value in request.form.items():
        if form_key.startswith("k_"):
            # Extract the unique ID
            uid = form_key[2:]
            if uid not in pairs:
                pairs[uid] = {}
            pairs[uid]['key'] = form_value.strip()
        elif form_key.startswith("v_"):
            # Extract the unique ID
            uid = form_key[2:]
            if uid not in pairs:
                pairs[uid] = {}
            pairs[uid]['value'] = form_value.strip()

    # Now build the config from the pairs
    for uid, pair in pairs.items():
        # Extract mode from uid (format: mode_timestamp_random)
        mode = uid.split('_')[0]  # 'gpu' or 'cpu'
        param_key = pair.get('key', '')
        param_value = pair.get('value', '')
        
        # Only add if key is not empty and mode exists
        if param_key and mode in model_config:
            model_config[mode][param_key] = param_value

    save_model_config(path, model_config)
    return redirect("/")

@app.route("/run")
def run():
    path = request.args.get("path")
    mode = request.args.get("mode")  # gpu or cpu
    binary_type = request.args.get("binary")  # server or cli

    config = load_model_config(path)
    
    # Debug: print what we loaded
    print(f"Loaded config for {path}: {config}")
    print(f"Mode requested: {mode}")
    
    if not config or mode not in config:
        return f"<pre>Error: No configuration found for mode '{mode}'</pre><a href='/'>Back</a>"
    
    cfg = config[mode]
    
    # Choose binary based on type
    if binary_type == "server":
        binary = "~/llama.cpp/build/bin/llama-server"
    else:  # cli
        binary = "~/llama.cpp/build/bin/llama-cli"

    param_str = " ".join(f"{k} {v}".strip() for k, v in cfg.items())
    cmd = f"{binary} -m {path} {param_str}"

    # Get model name for display
    conn = db()
    try:
        row = conn.execute(
            "SELECT model_name FROM model_configs WHERE model_path=?",
            (path,)
        ).fetchone()
        model_name = row["model_name"] if row else os.path.basename(path)
    finally:
        conn.close()

    return render_template("run.html", 
                         command=cmd, 
                         model_name=model_name,
                         mode=mode.upper(),
                         binary_type=binary_type.upper())

# ADDED: Routes for default parameters
@app.route("/defaults")
def defaults():
    """Show page to edit default parameters"""
    current_defaults = load_defaults()
    return render_template("defaults.html", defaults=current_defaults)

@app.route("/save-defaults", methods=["POST"])
def save_defaults_route():
    """Save updated default parameters"""
    new_defaults = {
        "gpu": {},
        "cpu": {}
    }
    
    # Parse form data
    pairs = {}
    for form_key, form_value in request.form.items():
        if form_key.startswith("k_"):
            uid = form_key[2:]
            if uid not in pairs:
                pairs[uid] = {}
            pairs[uid]['key'] = form_value.strip()
        elif form_key.startswith("v_"):
            uid = form_key[2:]
            if uid not in pairs:
                pairs[uid] = {}
            pairs[uid]['value'] = form_value.strip()
    
    # Build defaults from pairs
    for uid, pair in pairs.items():
        # Extract mode from uid (format: mode_timestamp_random)
        mode_parts = uid.split('_')
        mode = mode_parts[0]  # Should be 'gpu' or 'cpu'
        param_key = pair.get('key', '')
        param_value = pair.get('value', '')
        
        if param_key and mode in new_defaults:
            new_defaults[mode][param_key] = param_value
    
    # Debug: print what we're saving
    print(f"Saving defaults: {new_defaults}")
    
    save_defaults(new_defaults)
    return redirect("/")

@app.route("/reset-to-defaults")
def reset_to_defaults():
    """Reset a model's parameters to current defaults"""
    path = request.args.get("path")
    
    if not path:
        return redirect("/")
    
    # Load current defaults
    current_defaults = load_defaults()
    
    # Save them to this model
    save_model_config(path, current_defaults)
    
    # Redirect back to edit page
    return redirect(f"/edit?path={path}")

@app.route("/folders")
def folders():
    """Show page to edit scan folders"""
    current_folders = load_folders()
    return render_template("folders.html", folders=current_folders)

@app.route("/save-folders", methods=["POST"])
def save_folders_route():
    """Save updated scan folders"""
    folders = request.form.getlist('folders[]')
    
    # Filter out empty strings and strip whitespace
    folders = [f.strip() for f in folders if f.strip()]
    
    if not folders:
        folders = DEFAULT_FOLDERS.copy()
    
    print(f"Saving folders: {folders}")
    save_folders(folders)
    
    # Check if we should rescan
    if request.form.get('rescan'):
        scan_models()
    
    return redirect("/")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
