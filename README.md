# NPS GUI

**NoPayStation/trove graphical frontend for downloading PS3, PSV, PSP, PSX, and PSM games.**

A cross-platform GUI wrapper around [dreulavelle/trove](https://github.com/dreulavelle/trove) (the `nps` CLI) with search, multi-select, batch download, progress tracking, and cancellation support.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- 🔍 **Search** games by name across PS3, PSV, PSP, PSX, PSM catalogs
- 📋 **Results table** with region sorting (ASIA → EU → JP → US)
- ✅ **Multi-select** with checkboxes for batch downloads
- 📦 **Batch download** via aria2c (resumable, multi-connection)
- 📊 **Real-time progress** with allocation/download phase detection
- ⏹ **Cancellation** with automatic cleanup of partial files
- 📁 **Custom destination** folder selection
- 🖥 **Cross-platform**: Linux (AppImage) and Windows (.exe)

---

## Screenshots

*Coming soon*

---

## Quick Start

### Download Releases

| Platform | Download |
|----------|----------|
| **Linux (x86_64)** | [`nps-gui-linux-x86_64.AppImage`](https://github.com/emanuelv/nps-gui/releases/latest/download/nps-gui-linux-x86_64.AppImage) |
| **Windows (x86_64)** | [`nps-gui.exe`](https://github.com/emanuelv/nps-gui/releases/latest/download/nps-gui.exe) |

### Linux (AppImage)
```bash
chmod +x nps-gui-linux-x86_64.AppImage
./nps-gui-linux-x86_64.AppImage
```

### Windows
Double-click `nps-gui.exe` or run from terminal:
```cmd
nps-gui.exe
```

---

## Building from Source

### Prerequisites

- Python 3.8+
- `tkinter` (usually included with Python; on Linux: `python3-tk` / `tk`)
- `aria2c` (for downloads; `sudo apt install aria2` / `winget install aria2`)

### Development Install

```bash
git clone https://github.com/emanuelv/nps-gui.git
cd nps-gui
pip install -e .[dev]
nps-gui
```

### Build Standalone Executables

**Linux:**
```bash
pip install pyinstaller
pyinstaller nps-gui.spec --clean
# Output: dist/nps-gui
```

**Windows:**
```cmd
pip install pyinstaller pillow
pyinstaller nps-gui.spec --clean
# Output: dist/nps-gui.exe
```

**AppImage (Linux):**
```bash
# After PyInstaller build
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
cp dist/nps-gui AppDir/usr/bin/
cp assets/icon.png AppDir/usr/share/icons/hicolor/256x256/apps/nps-gui.png
# Create AppRun and .desktop, then run appimagetool
```

---

## Usage

1. **Launch** the application
2. **Select platform** (PS3, PSV, PSP, PSX, PSM) from dropdown
3. **Search** by game name (e.g., "God of War", "Persona")
4. **Select games** by clicking the ☐ checkbox column
5. **Choose destination** folder (defaults to `~/Downloads/PS3_Games`)
6. **Click "Descargar seleccionados"** to start batch download
7. **Monitor progress** in the log panel and progress bar
8. **Cancel anytime** — partial files are cleaned up automatically

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Trigger search |
| `Double-click row` | Download single game |
| `Click ☐ column` | Toggle selection |

---

## Configuration

No config file needed. The app remembers:
- Last destination folder (per session)
- Window size/position (OS managed)

---

## Troubleshooting

### "nps binary not found"
The bundled `nps` binary is included in the AppImage/.exe. If building from source, ensure `nps` is in PATH or place it in `assets/`:
```bash
# Linux
curl -L -o assets/nps-linux-x64 https://github.com/dreulavelle/trove/releases/download/v1.0.1/nps-linux-x64
chmod +x assets/nps-linux-x64

# Windows (PowerShell)
curl -L -o assets\nps-windows-x64.exe https://github.com/dreulavelle/trove/releases/download/v1.0.1/nps-windows-x64.exe
```

### Downloads fail / timeout
- Large games (5–20 GB) need time — the GUI uses 2-hour timeout
- Ensure `aria2c` is installed and in PATH
- Check disk space (NTFS on Linux may cause issues; prefer ext4/btrfs)

### Linux: "No display" / tkinter errors
```bash
# Install tkinter
sudo apt install python3-tk        # Debian/Ubuntu
sudo pacman -S tk                  # Arch/CachyOS
sudo dnf install python3-tkinter   # Fedora
```

### Windows: "Missing DLL" / won't start
- Install [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- Run from terminal to see error output

---

## Project Structure

```
nps-gui/
├── nps_gui/
│   ├── __init__.py
│   └── __main__.py          # Main GUI application
├── assets/
│   ├── nps-linux-x64        # Bundled nps binary (Linux)
│   ├── nps-windows-x64.exe  # Bundled nps binary (Windows)
│   ├── icon.png             # App icon (Linux)
│   └── icon.ico             # App icon (Windows)
├── nps-gui.spec             # PyInstaller spec
├── pyproject.toml           # Project metadata & build config
├── README.md
├── LICENSE
└── .github/workflows/
    └── build-release.yml    # CI/CD: builds AppImage + .exe on tag push
```

---

## Credits

- **trove/nps CLI**: [dreulavelle/trove](https://github.com/dreulavelle/trove) — the core downloader
- **NoPayStation**: Community catalog at [nopaystation.com](https://nopaystation.com)
- **aria2**: Multi-protocol download utility

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Disclaimer

This tool accesses publicly available game metadata and download links from NoPayStation. **You are responsible for complying with your local laws regarding game ownership and backups.** Only download games you legally own.