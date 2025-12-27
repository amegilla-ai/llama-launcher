#!/usr/bin/env python3
"""
Flask admin interface for managing GGUF model configurations.
"""
import json
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory

from shared.config import ADMIN_TEMPLATES, STATIC_OUTPUT, DB_PATH
from shared.utils import (
    init_db, scan_models, get_all_models, load_defaults, save_defaults,
    load_scan_cfg, save_scan_cfg, group_models_by_directory, render_static_page,
    get_model_config, update_model_config, load_param_references,
    save_param_references_directly
)

import sqlite3

app = Flask(__name__, template_folder=str(ADMIN_TEMPLATES))
app.secret_key = "dev-secret"  # Change for production


def rebuild_static():
    """Regenerate static site from current database."""
    try:
        groups = group_models_by_directory(get_all_models())
        render_static_page(groups)
    except Exception as e:
        print(f"❗ Failed to rebuild static page: {e}")


def parse_form_pairs(form_data):
    """Parse key-value pairs from form data with k_, vg_, vc_, and c_ prefixes."""
    pairs = {}
    for key, value in form_data.items():
        if key.startswith(("k_", "vg_", "vc_", "c_")):
            uid = key[2:] if key.startswith("k_") else key[3:]
            pairs.setdefault(uid, {})[key.split("_")[0]] = value.strip()
    
    result = {"common": {}, "server": {}, "cli": {}}
    comments = {"common": {}, "server": {}, "cli": {}}
    
    for uid, pair in pairs.items():
        if "k" in pair and ("vg" in pair or "vc" in pair) and pair["k"]:
            # Extract section and parameter name
            parts = uid.split("_", 1)
            if len(parts) == 2:
                section, _ = parts
                if section in result:
                    param_name = pair["k"]
                    gpu_val = pair.get("vg", "")
                    cpu_val = pair.get("vc", "")
                    
                    result[section][param_name] = {"gpu": gpu_val, "cpu": cpu_val}
                    
                    if "c" in pair and pair["c"]:
                        comments[section][param_name] = pair["c"]
    
    return result, comments


# Routes
@app.route("/")
def admin_home():
    groups = group_models_by_directory(get_all_models())
    
    # Parse JSON parameters for display
    for models in groups.values():
        for model in models:
            try:
                params = json.loads(model["params_json"])
                
                # Handle old format migration for display
                if "gpu" in params and "cpu" in params:
                    # Old format - convert for display
                    old_params = params
                    new_params = {"common": {}, "server": {}, "cli": {}}
                    
                    # Migrate old GPU/CPU structure to new common structure for display
                    all_keys = set()
                    if "gpu" in old_params:
                        all_keys.update(old_params["gpu"].keys())
                    if "cpu" in old_params:
                        all_keys.update(old_params["cpu"].keys())
                    
                    for key in all_keys:
                        gpu_val = old_params.get("gpu", {}).get(key, "")
                        cpu_val = old_params.get("cpu", {}).get(key, "")
                        new_params["common"][key] = {"gpu": gpu_val, "cpu": cpu_val}
                    
                    model["parsed_params"] = new_params
                else:
                    model["parsed_params"] = params
                    
            except json.JSONDecodeError:
                model["parsed_params"] = {"common": {}, "server": {}, "cli": {}}
    
    defaults_data = load_defaults()
    return render_template(
        "admin_index.html",
        groups=groups,
        total_models=sum(len(models) for models in groups.values()),
        defaults=defaults_data["params"],
        folders=load_scan_cfg().get("folders", [])
    )


@app.route("/scan")
def scan():
    scan_models()
    rebuild_static()
    flash("🔎 Scan completed and static page updated.")
    return redirect(url_for("admin_home"))


@app.route("/edit")
def edit():
    path = request.args.get("path")
    if not path:
        flash("❗ No model path provided.")
        return redirect(url_for("admin_home"))
    
    config = get_model_config(path)
    if not config:
        flash("❗ Model not found.")
        return redirect(url_for("admin_home"))
    
    defaults_data = load_defaults()
    config["defaults"] = defaults_data["params"]
    config["default_comments"] = defaults_data["comments"]
    config["param_refs"] = load_param_references()
    
    return render_template("edit.html", **config)


@app.route("/save", methods=["POST"])
def save():
    path = request.form.get("model_path")
    if not path:
        flash("❗ No model path provided.")
        return redirect(url_for("admin_home"))
    
    new_params, new_comments = parse_form_pairs(request.form)
    if update_model_config(path, new_params, new_comments):
        rebuild_static()
        flash("✅ Model parameters saved.")
    else:
        flash("❗ Failed to save model parameters.")
    
    return redirect(url_for("admin_home"))


@app.route("/settings")
def settings():
    defaults_data = load_defaults()
    return render_template("settings.html", 
                         defaults=defaults_data,
                         param_refs=load_param_references(),
                         folders_cfg=load_scan_cfg())


@app.route("/save-settings", methods=["POST"])
def save_settings():
    # Save folder configuration
    folders_cfg = {
        "folders": [f.strip() for f in request.form.get("folders", "").splitlines() if f.strip()],
        "llama_server_gpu_bin": request.form.get("server_gpu_bin", "").strip(),
        "llama_server_cpu_bin": request.form.get("server_cpu_bin", "").strip(),
        "llama_cli_gpu_bin": request.form.get("cli_gpu_bin", "").strip(),
        "llama_cli_cpu_bin": request.form.get("cli_cpu_bin", "").strip()
    }
    save_scan_cfg(folders_cfg)
    
    # Save default parameters
    new_params, new_comments = parse_form_pairs(request.form)
    save_defaults(new_params, new_comments)
    
    rebuild_static()
    flash("✅ Settings saved.")
    return redirect(url_for("settings"))


@app.route("/save-defaults", methods=["POST"])
def save_defaults_route():
    new_params, new_comments = parse_form_pairs(request.form)
    save_defaults(new_params, new_comments)
    rebuild_static()
    flash("✅ Default parameters saved.")
    return redirect(url_for("admin_home"))


@app.route("/folders")
def folders():
    return render_template("folders.html", folders_cfg=load_scan_cfg())


@app.route("/save-folders", methods=["POST"])
def save_folders_route():
    cfg = {
        "folders": [f.strip() for f in request.form.get("folders", "").splitlines() if f.strip()],
        "llama_server_gpu_bin": request.form.get("server_gpu_bin", "").strip(),
        "llama_server_cpu_bin": request.form.get("server_cpu_bin", "").strip(),
        "llama_cli_gpu_bin": request.form.get("cli_gpu_bin", "").strip(),
        "llama_cli_cpu_bin": request.form.get("cli_cpu_bin", "").strip()
    }
    
    save_scan_cfg(cfg)
    
    if request.form.get("rescan"):
        scan_models()
    
    rebuild_static()
    flash("✅ Configuration saved.")
    return redirect(url_for("admin_home"))


@app.route("/delete")
def delete_model():
    path = request.args.get("path")
    if not path:
        flash("❗ No model path provided.")
        return redirect(url_for("admin_home"))
    
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM model_configs WHERE model_path=?", (path,))
        rebuild_static()
        flash("✅ Model deleted from database.")
    except Exception:
        flash("❗ Failed to delete model.")
    
    return redirect(url_for("admin_home"))


@app.route("/static-page")
def static_page():
    """Serve the generated static page."""
    try:
        static_file = STATIC_OUTPUT / "index.html"
        if not static_file.exists():
            rebuild_static()
        return send_from_directory(str(STATIC_OUTPUT), "index.html")
    except Exception:
        flash("❗ Failed to load static page.")
        return redirect(url_for("admin_home"))


@app.route("/static_site/<path:filename>")
def serve_static_assets(filename):
    """Serve static site assets (CSS, JS)."""
    from shared.config import PROJECT_ROOT
    static_dir = PROJECT_ROOT / "static_site"
    return send_from_directory(str(static_dir), filename)


@app.route("/generate-params", methods=["POST"])
def generate_params():
    """Generate parameter references using direct parsing."""
    try:
        cfg = load_scan_cfg()
        
        # Use server GPU binary as primary
        server_path = cfg.get("llama_server_gpu_bin", "")
        cli_path = cfg.get("llama_cli_gpu_bin", "")
        
        if not server_path or not cli_path:
            flash("❗ Please configure binary paths in Folders to Scan first.")
            return redirect(url_for("settings"))
        
        # Check if binaries exist
        from pathlib import Path
        if not Path(server_path).exists():
            flash(f"❗ Server binary not found: {server_path}")
            return redirect(url_for("settings"))
        
        if not Path(cli_path).exists():
            flash(f"❗ CLI binary not found: {cli_path}")
            return redirect(url_for("settings"))
        
        success, message = save_param_references_directly(server_path, cli_path)
        
        if success:
            flash(f"✅ {message}")
        else:
            flash(f"❗ {message}")
    
    except Exception as e:
        flash(f"❗ Unexpected error: {str(e)}")
    
    return redirect(url_for("settings"))


if __name__ == "__main__":
    init_db()
    rebuild_static()
    app.run(debug=True, port=5001)
