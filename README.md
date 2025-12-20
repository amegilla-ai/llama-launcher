## Model Launcher

A clean, lightweight web interface for managing and launching Large Language Models (LLMs) from your local directories. It streamlines the process of generating terminal commands for different hardware configurations (GPU vs. CPU) and binary types (Server vs. CLI).

---

### 🚀 Features

* **Automatic Model Scanning**: Automatically detects models in common locations like `~/.cache` and `~/ComfyUI`.
* **Hardware Optimization**: Quickly generate commands tailored for **GPU** (using flags like `--flash-attn`) or **CPU**.
* **Dual Mode Support**: Choose between running your model as a background **Server** or an interactive **CLI**.
* **Parameter Management**: Customize flags and values for every model individually or set global defaults for newly discovered models.
* **One-Click Copy**: Copy generated commands directly to your clipboard for instant terminal execution.

---

### 🛠️ Core Components

* **Dashboard (`index.html`)**: View all discovered models grouped by their directory, showing file sizes and quick-launch options.
* **Parameters Editor (`edit.html`)**: A refined, side-by-side interface to manage specific GPU and CPU flags for a selected model.
* **Global Defaults (`defaults.html`)**: Define a base set of parameters that are automatically applied to any new model the app finds.
* **Execution View (`run.html`)**: A focused modal that displays the final command string and handles the clipboard copy action.

---

### 📝 Configuration

The app uses a flexible parameter system where you define **Flags** (e.g., `-c`) and **Values** (e.g., `2048`).

| Mode | Common Parameters |
| --- | --- |
| **GPU** | High-performance flags like `--flash-attn` and layer offloading. |
| **CPU** | Thread management and memory-efficient settings. |

---

### 🖥️ Getting Started
0. **Run & Scan** Run app.py
1. **View**: Open the URL (http://127.0.0.1:5000) to see the models discovered.
2. **Configure**: Click **Edit Params** on a model to tune its performance or use **Edit Defaults** for global settings.
3. **Launch**: Select a launch mode (e.g., **Server GPU**). The app will generate the command text.
4. **Execute**: Click **Copy Command** and paste it into your terminal to start the model.

** Please note:** for security reasons this app doesn't launch the model, it just gives you the full command to run it in your terminal.