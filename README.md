# GGUF Model Launcher

A clean, web-based interface for managing and launching GGUF language models with customizable parameters for GPU/CPU execution across server and CLI modes.

## Features

- 🔍 **Auto-discovery**: Scan directories to find GGUF model files with automatic file size detection
- ⚙️ **Advanced Parameter Management**: Configure launch parameters organized by Common, Server-specific, and CLI-specific categories
- 💬 **Parameter Comments**: Add descriptive comments to document what each parameter does
- 🚀 **Static Launcher**: Generate standalone HTML interface for launching models
- 📊 **Overview Dashboard**: See all models and their configurations at a glance
- 🗂️ **Organized by Folder**: Models grouped by directory for easy navigation
- 🔧 **Parameter Discovery**: Extract available parameters directly from llama.cpp binaries
- 🎨 **Modern UI**: Clean interface using Inter font with consistent styling

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install flask jinja2
   ```

2. **Run the application**:
   ```bash
   python3 app.py
   ```

3. **Open in browser**: http://localhost:5001

## Setup Workflow

1. **Configure Folders**: Click "Folders to Scan" to set directories containing your GGUF files
2. **Set Binary Paths**: Configure paths to your `llama-server` and `llama-cli` executables  
3. **Generate Parameter References**: Click "Generate Parameter References" to extract available parameters from binaries
4. **Set Default Parameters**: Click "Default Parameters" to configure default settings for new models
5. **Scan Models**: Click "Scan for Models" to discover all GGUF files in configured directories
6. **Edit Parameters**: Click "Edit" on any model to customize parameters with GPU/CPU values
7. **Launch Interface**: Click "Launch Commands" to open the generated model launcher

## Parameter Architecture

### Three Parameter Categories
- **Common Parameters**: Used by both server and CLI modes (e.g., `-c`, `--threads`, `--no-mmap`)
- **Server Parameters**: Server-specific options (e.g., `--port`, `--host`, `--timeout`)
- **CLI Parameters**: CLI-specific options (e.g., `--interactive`, `--prompt`, `--file`)

### GPU/CPU Values
Each parameter can have different values for GPU and CPU execution:
- **GPU Value**: Used when running with GPU acceleration
- **CPU Value**: Used when running CPU-only mode

### Command Generation
The system generates 4 command combinations for each model:
1. **GPU Server**: `llama-server -m model.gguf [common_gpu_params] [server_gpu_params]`
2. **CPU Server**: `llama-server -m model.gguf [common_cpu_params] [server_cpu_params]`
3. **GPU CLI**: `llama-cli -m model.gguf [common_gpu_params] [cli_gpu_params]`
4. **CPU CLI**: `llama-cli -m model.gguf [common_cpu_params] [cli_cpu_params]`

## Project Structure

```
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── shared/
│   ├── config.py            # Configuration settings
│   └── utils.py             # Core functionality
├── admin_app/
│   └── templates/           # Admin interface HTML templates
├── static_site/
│   ├── templates/           # Static launcher template
│   └── assets/              # CSS and JavaScript
└── data/                    # Generated files (created automatically)
    ├── model_params.db      # SQLite database
    ├── defaults.pkl         # Default parameters
    ├── folders.pkl          # Scan configuration
    ├── param_references.json # Parameter definitions from binaries
    └── static_site/         # Generated launcher HTML
```

## Usage

### Admin Interface (http://localhost:5001)
- **Dashboard**: View all models with their Common/Server/CLI parameters in organized columns
- **Edit Models**: Click any model name to customize launch parameters with GPU/CPU values
- **Manage Defaults**: Set default parameters for new models with comments
- **Configure Scanning**: Add/remove directories to scan for models
- **Parameter Discovery**: Generate parameter references from llama.cpp binaries
- **Add from Llama.cpp**: Use modal interface to add official parameters with descriptions

### Static Launcher (`data/static_site/index.html`)
- **Standalone HTML**: Works without the Flask server running
- **Copy Commands**: Click buttons to copy launch commands to clipboard
- **Organized Display**: Models grouped by directory with file sizes
- **Four Command Types**: GPU-Server, CPU-Server, GPU-CLI, CPU-CLI combinations

## Configuration

### Default Parameters
The app comes with sensible defaults organized by category:
- **Common**: `-c 16384 --no-mmap` (context size and memory mapping)
- **Server**: `--port 8080 --host 0.0.0.0` (network configuration)
- **CLI**: `--interactive` (interactive mode)

### Parameter Comments
Add descriptive comments to document parameter purposes:
- Explain what each parameter does
- Note recommended values or ranges
- Document compatibility requirements
- 250 character limit with scrollable input

### Scan Directories
Configure which folders to scan for `.gguf` files:
- Supports environment variables (`~/models`, `$HOME/ai`)
- Recursive scanning of subdirectories
- Automatic file size detection and storage

### Binary Paths
Set paths to your llama.cpp executables:
- `llama-server`: For server mode operations
- `llama-cli`: For CLI mode operations
- Used for parameter discovery and command generation

## Advanced Features

### Parameter Discovery
Extract available parameters directly from your llama.cpp binaries:
1. Configure binary paths in "Folders to Scan"
2. Click "Generate Parameter References" 
3. System runs `--help` on both binaries
4. Automatically categorizes parameters as Common/Server/CLI
5. Use "Add from Llama.cpp" buttons to browse and add parameters

### Migration Support
Seamlessly handles data from older versions:
- Automatically converts old GPU/CPU parameter format
- Preserves existing model configurations
- Graceful fallbacks for missing data

### Database Storage
Efficient storage of model configurations:
- SQLite database for reliability
- File sizes stored to avoid recalculation
- Parameter comments preserved
- Automatic schema updates

## Tips

- **Backup**: The `data/` folder contains all your configurations
- **Sharing**: Copy `data/static_site/index.html` to share launcher with others
- **Cleanup**: Delete models from database if files are moved/removed
- **Defaults**: Set good defaults before scanning to save time on individual models
- **Comments**: Use parameter comments to document your configuration choices
- **Discovery**: Generate parameter references to explore all available llama.cpp options

## Requirements

- Python 3.7+
- Flask 2.0+
- Jinja2 3.0+
- llama.cpp binaries (for actual model execution and parameter discovery)

## License

Open source - feel free to modify and share!
