#!/usr/bin/env python3
"""
NPS GUI - Main application module
GUI for NoPayStation/trove - Download PS3/PSV/PSP/PSX/PSM games
"""

import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import shlex
import re
import os
import signal
import glob
import sys
import platform
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional


def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).parent.parent
    return base_path / relative_path


def get_nps_binary() -> Path:
    """Locate the nps/trove binary for current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # In PyInstaller bundle, nps is in assets/
    if getattr(sys, 'frozen', False):
        assets_dir = get_resource_path("assets")
        if system == "windows":
            nps_path = assets_dir / "nps-windows-x64.exe"
        elif system == "darwin":
            nps_path = assets_dir / ("nps-macos-arm64" if "arm" in machine else "nps-macos-x64")
        else:  # Linux
            nps_path = assets_dir / "nps-linux-x64"
        if nps_path.exists():
            return nps_path

    # Development fallback: look in common locations
    dev_paths = [
        Path("/mnt/games/PS3/NPS/nps"),
        Path.home() / ".local" / "bin" / "nps",
        Path("/usr/local/bin/nps"),
        Path("/usr/bin/nps"),
    ]
    for p in dev_paths:
        if p.exists():
            return p

    # Last resort: assume in PATH
    return Path("nps")


NPS_BIN = get_nps_binary()
DEFAULT_DEST = str(Path.home() / "Downloads" / "PS3_Games")

# --- Tema oscuro ---
COLORS = {
    "bg": "#121212",
    "panel": "#1e1e1e",
    "fg": "#e0e0e0",
    "muted": "#9e9e9e",
    "accent": "#3574f0",
    "accent2": "#2b5fcf",
    "sel": "#252525",
    "border": "#333333",
}

# --- SteamGridDB (fondo del juego al buscar) ---
SGDB_BASE = "https://www.steamgriddb.com/api/v2"
SGDB_KEY = os.environ.get("STEAMGRIDDB_API_KEY", "")
SGDB_DEFAULT_TIMEOUT = 15


class NPSGui:
    """Main GUI application class."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NPS GUI - NoPayStation Downloader")
        self.root.geometry("950x650")
        self.root.minsize(800, 500)

        self.results: List[Dict] = []
        self.downloading = False
        self.cancel_requested = False
        self.current_proc: Optional[subprocess.Popen] = None
        self.current_title_id: Optional[str] = None
        self.current_dest: Optional[str] = None
        self.child_pids = set()
        self.bg_image = None          # PIL image actual de fondo
        self.bg_photo = None          # PhotoImage para tk

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._apply_dark_theme()
        self._build_ui()

    def _apply_dark_theme(self):
        """Aplica el tema oscuro global."""
        c = COLORS
        style = ttk.Style(self.root)
        available = set(style.theme_names())
        if "clam" in available:
            style.theme_use("clam")
        style.configure(".", background=c["panel"], foreground=c["fg"],
                        fieldbackground=c["panel"], bordercolor=c["border"])
        style.configure("TFrame", background=c["panel"])
        style.configure("TLabel", background=c["panel"], foreground=c["fg"])
        style.configure("TButton", background=c["accent"], foreground="#ffffff",
                        padding=6, borderwidth=0, focuscolor=c["accent"])
        style.map("TButton",
                  background=[("active", c["accent2"]), ("pressed", c["accent2"])],
                  foreground=[("active", "#ffffff")])
        style.configure("TEntry", fieldbackground=c["sel"], foreground=c["fg"],
                        insertcolor=c["fg"], bordercolor=c["border"])
        style.configure("TCombobox", fieldbackground=c["sel"], foreground=c["fg"],
                        background=c["panel"], arrowcolor=c["fg"])
        style.configure("TProgressbar", background=c["accent"], troughcolor=c["sel"],
                        bordercolor=c["border"])
        style.configure("Treeview", background=c["sel"], fieldbackground=c["sel"],
                        foreground=c["fg"], bordercolor=c["border"])
        style.map("Treeview", background=[("selected", c["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=c["panel"], foreground=c["fg"],
                        bordercolor=c["border"])
        style.configure("TSpinbox", fieldbackground=c["sel"], foreground=c["fg"],
                        background=c["panel"])
        style.configure("Accent.TButton", background=c["accent"], foreground="#ffffff")
        style.map("Accent.TButton",
                  background=[("active", c["accent2"]), ("pressed", c["accent2"])])
        self.root.configure(bg=c["panel"])
        self.root.option_add("*TCombobox*Listbox.background", c["sel"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["fg"])

    def _get_sgdb_key(self) -> str:
        """Lee la API key de SteamGridDB (env o config local)."""
        key = SGDB_KEY
        if not key:
            cfg = Path.home() / ".config" / "nps-gui" / "config.json"
            try:
                if cfg.exists():
                    key = json.loads(cfg.read_text()).get("steamgriddb_api_key", "")
            except Exception:
                pass
        return key.strip()

    def _sgdb_request(self, path: str, timeout: int = SGDB_DEFAULT_TIMEOUT) -> Optional[dict]:
        """GET a la API de SteamGridDB. Devuelve JSON dict o None."""
        key = self._get_sgdb_key()
        if not key:
            return None
        url = f"{SGDB_BASE}{path}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "NPS-GUI/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def _download_image(self, url: str, timeout: int = SGDB_DEFAULT_TIMEOUT) -> Optional[bytes]:
        """Descarga una imagen (bytes) desde una URL."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NPS-GUI/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            return None

    def _guess_game_search(self) -> str:
        """Devuelve el nombre del juego a buscar en SGDB (1er resultado o query)."""
        if self.results:
            return self.results[0]["name"]
        q = self.search_var.get().strip()
        return q

    def _set_background_image_path(self, path: Path):
        """Carga una imagen local (PNG/JPG) y la muestra de fondo del panel central."""
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img = img.convert("RGBA")
            # Oscurecer para legibilidad
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 150))
            img = Image.alpha_composite(img, overlay)
            self.bg_image = img.copy()
            self.bg_photo = ImageTk.PhotoImage(img)
            self._render_background()
        except Exception:
            pass

    def _set_background_image_bytes(self, data: bytes):
        """Carga una imagen desde bytes y la muestra de fondo."""
        try:
            from PIL import Image, ImageTk
            import io
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGBA")
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 150))
            img = Image.alpha_composite(img, overlay)
            self.bg_image = img.copy()
            self.bg_photo = ImageTk.PhotoImage(img)
            self._render_background()
        except Exception:
            pass

    def _render_background(self):
        """Pinta el fondo del panel (re-escalado al size actual)."""
        if not self.bg_image or not hasattr(self, "bg_canvas"):
            return
        try:
            from PIL import ImageTk
            w = max(self.bg_canvas.winfo_width(), 10)
            h = max(self.bg_canvas.winfo_height(), 10)
            img = self.bg_image.copy()
            img.thumbnail((w, h))
            self.bg_photo = ImageTk.PhotoImage(img)
            self.bg_canvas.delete("all")
            self.bg_canvas.create_image(w // 2, h // 2, image=self.bg_photo, anchor="center")
        except Exception:
            pass

    def _show_nps_logo_background(self):
        """Muestra el logo de NPS como fondo inicial."""
        logo = get_resource_path("assets/nps_logo.png")
        if logo.exists():
            self._set_background_image_path(logo)
        else:
            self.log_write("ℹ Logo NPS no encontrado en assets/")

    def _build_ui(self):
        # Canvas de fondo (logo NPS al inicio / imagen del juego al buscar)
        self.bg_canvas = tk.Canvas(self.root, bg=COLORS["bg"], highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.root.bind("<Configure>", lambda e: self._render_background())

        # Top frame: search
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Buscar juego:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=50)
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.search_entry.bind("<Return>", lambda e: self.on_search())
        ttk.Button(top, text="Buscar", command=self.on_search).pack(side=tk.LEFT, padx=5)

        # Platform selector
        platform_frame = ttk.Frame(top)
        platform_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(platform_frame, text="Plataforma:").pack(side=tk.LEFT)
        self.platform_var = tk.StringVar(value="PS3")
        platform_combo = ttk.Combobox(
            platform_frame, textvariable=self.platform_var, width=8,
            values=["PS3", "PSV", "PSP", "PSX", "PSM"], state="readonly"
        )
        platform_combo.pack(side=tk.LEFT, padx=5)

        # Middle frame: results table
        mid = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        mid.pack(fill=tk.X)

        columns = ("sel", "title_id", "region", "name")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("sel", text="☐")
        self.tree.heading("title_id", text="Title ID")
        self.tree.heading("region", text="Región")
        self.tree.heading("name", text="Nombre")
        self.tree.column("sel", width=50, anchor="center")
        self.tree.column("title_id", width=120, anchor="center")
        self.tree.column("region", width=80, anchor="center")
        self.tree.column("name", width=550)

        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        mid.grid_rowconfigure(0, weight=1)
        mid.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Bottom frame: buttons, destination, progress, log
        bot = ttk.Frame(self.root, padding=10)
        bot.pack(fill=tk.X)

        ttk.Button(bot, text="Descargar seleccionados", command=self.on_download).pack(side=tk.LEFT, padx=5)
        self.cancel_btn = ttk.Button(bot, text="Cancelar descarga", command=self.on_cancel, state="disabled")
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(bot, text="Limpiar selección", command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(bot, text="Abrir carpeta destino", command=self.open_dest_folder).pack(side=tk.LEFT, padx=5)

        # Destination folder
        dest_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        dest_frame.pack(fill=tk.X)
        ttk.Label(dest_frame, text="Destino:").pack(side=tk.LEFT)
        self.dest_var = tk.StringVar(value=DEFAULT_DEST)
        self.dest_entry = ttk.Entry(dest_frame, textvariable=self.dest_var, width=60)
        self.dest_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(dest_frame, text="Examinar", command=self.choose_dest_folder).pack(side=tk.LEFT, padx=5)

        # Progress bar with phase indicator
        prog_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        prog_frame.pack(fill=tk.X)
        ttk.Label(prog_frame, text="Progreso:").pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.progress_label = ttk.Label(prog_frame, text="Esperando...")
        self.progress_label.pack(side=tk.LEFT, padx=5)
        self.phase_indicator = tk.Canvas(prog_frame, width=20, height=20, highlightthickness=0)
        self.phase_indicator.pack(side=tk.LEFT, padx=5)
        self.phase_circle = self.phase_indicator.create_oval(2, 2, 18, 18, fill="gray", outline="")

        # Log output
        ttk.Label(self.root, text="Salida:", padding=(10, 0, 0, 0)).pack(anchor="w")
        self.log = scrolledtext.ScrolledText(self.root, height=8, state="disabled",
                                              bg=COLORS["sel"], fg=COLORS["fg"],
                                              insertbackground=COLORS["fg"],
                                              relief=tk.FLAT, wrap="word")
        self.log.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Logo NPS de fondo al iniciar
        self.root.after(50, self._show_nps_logo_background)

    def log_write(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def on_tree_click(self, event):
        """Toggle checkbox on click in 'sel' column."""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        vals = list(self.tree.item(item, "values"))
        vals[0] = "☑" if vals[0] == "☐" else "☐"
        self.tree.item(item, values=vals)

    def on_tree_double_click(self, event):
        """Download single game on double-click."""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        vals = self.tree.item(item, "values")
        title_id = vals[1]
        for r in self.results:
            if r["title_id"] == title_id:
                self.on_download_single(r)
                break

    def get_selected_items(self) -> List[Dict]:
        selected = []
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            if vals[0] == "☑":
                title_id = vals[1]
                for r in self.results:
                    if r["title_id"] == title_id:
                        selected.append(r)
                        break
        return selected

    def clear_selection(self):
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            if vals[0] == "☑":
                vals[0] = "☐"
            self.tree.item(item, values=vals)

    def on_search(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Atención", "Escribe algo para buscar")
            return

        platform = self.platform_var.get()
        self.log_write(f"Buscando [{platform}]: {query}")
        self.search_entry.config(state="disabled")
        threading.Thread(target=self._search_thread, args=(query, platform), daemon=True).start()

    def _search_thread(self, query: str, platform: str):
        cmd = [str(NPS_BIN), "-p", platform, "-l", "--name", query]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            output = proc.stdout + proc.stderr
            self.root.after(0, lambda: self._parse_results(output))
        except subprocess.TimeoutExpired:
            self.root.after(0, lambda: self.log_write("Timeout en búsqueda"))
        except Exception as e:
            self.root.after(0, lambda: self.log_write(f"Error: {e}"))
        finally:
            self.root.after(0, lambda: self.search_entry.config(state="normal"))

        # Buscar logo del juego de fondo (SteamGridDB), en un hilo aparte
        try:
            threading.Thread(target=self._fetch_game_background, args=(query,), daemon=True).start()
        except Exception:
            pass

    def _fetch_game_background(self, query: str):
        """Busca en SGDB el logo del juego buscado y lo pone de fondo."""
        key = self._get_sgdb_key()
        if not key:
            self.root.after(0, lambda: self.log_write(
                "ℹ Sin API key de SteamGridDB (STEAMGRIDDB_API_KEY). No se muestra fondo del juego."))
            return
        query = (query or "").strip()
        if not query:
            return
        try:
            term = urllib.parse.quote(query)
            data = self._sgdb_request(f"/search/autocomplete/{term}")
            if not data or not data.get("data"):
                return
            game_id = data["data"][0].get("id")
            if not game_id:
                return
            logos = self._sgdb_request(f"/logos/game/{game_id}?limit=1")
            if not logos or not logos.get("data"):
                return
            url = logos["data"][0].get("url")
            if not url:
                return
            img_bytes = self._download_image(url)
            if img_bytes:
                self.root.after(0, lambda: self._set_background_image_bytes(img_bytes))
        except Exception as e:
            self.log_write(f"⚠ No se pudo obtener logo del juego: {e}")

    def _parse_results(self, output: str):
        self.tree.delete(*self.tree.get_children())
        self.results = []

        lines = output.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("Title ID") or line.startswith("---") or "match(es)" in line:
                continue
            downloadable = "[x]" in line
            line = re.sub(r"^\[\s?[x ]\s?\]\s*", "", line)
            parts = re.split(r"\s{2,}", line)
            if len(parts) >= 3:
                title_id = parts[0].strip()
                region = parts[1].strip()
                name = "  ".join(parts[2:]).strip()
            elif len(parts) == 2:
                title_id = parts[0].strip()
                region = ""
                name = parts[1].strip()
            else:
                continue

            self.results.append({
                "title_id": title_id,
                "region": region,
                "name": name,
                "raw": line,
                "downloadable": downloadable
            })

        # Sort: primary Region (ASIA->EU->JP->US), secondary Name
        region_order = {"ASIA": 0, "EU": 1, "JP": 2, "US": 3}
        self.results.sort(key=lambda x: (region_order.get(x["region"], 99), x["name"].lower()))

        for r in self.results:
            self.tree.insert("", "end", values=("☐", r["title_id"], r["region"], r["name"]))

        self.log_write(f"Encontrados {len(self.results)} resultados")

    def on_download(self):
        selected = self.get_selected_items()
        if not selected:
            messagebox.showwarning("Atención", "Selecciona al menos un juego (click en la columna ☐)")
            return

        if self.downloading:
            messagebox.showinfo("Espera", "Ya hay una descarga en curso")
            return

        self.downloading = True
        self.cancel_requested = False
        self.cancel_btn.config(state="normal")
        self.log_write(f"Iniciando descarga de {len(selected)} juego(s)...")
        threading.Thread(target=self._download_thread, args=(selected,), daemon=True).start()

    def on_download_single(self, game: Dict):
        if self.downloading:
            messagebox.showinfo("Espera", "Ya hay una descarga en curso")
            return
        self.downloading = True
        self.cancel_requested = False
        self.cancel_btn.config(state="normal")
        self.log_write(f"Iniciando descarga de {game['title_id']}...")
        threading.Thread(target=self._download_thread, args=([game],), daemon=True).start()

    def on_cancel(self):
        if not self.downloading:
            return
        self.cancel_requested = True
        self.log_write("⚠ Cancelación solicitada... deteniendo descarga actual")
        self.cancel_btn.config(state="disabled")
        if self.current_proc and self.current_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.current_proc.pid), signal.SIGTERM)
                import time
                time.sleep(0.5)
                if self.current_proc.poll() is None:
                    os.killpg(os.getpgid(self.current_proc.pid), signal.SIGKILL)
            except Exception as e:
                self.log_write(f"Error al terminar proceso: {e}")
        for pid in self.child_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except:
                pass
        self.child_pids.clear()

    def on_closing(self):
        if self.downloading:
            self.on_cancel()
        try:
            subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
            subprocess.run(["pkill", "-f", "nps"], capture_output=True)
        except:
            pass
        try:
            dest = self.dest_var.get()
            for f in glob.glob(os.path.join(dest, "**", "*.aria2"), recursive=True):
                os.remove(f)
                self.log_write(f"🗑 Limpiado orphan: {os.path.basename(f)}")
        except:
            pass
        self.root.destroy()

    def _cleanup_partial_files(self, title_id: str, dest: str):
        try:
            pattern = os.path.join(dest, "**", f"*{title_id}*")
            files = glob.glob(pattern, recursive=True)
            for f in files:
                if os.path.isfile(f):
                    os.remove(f)
                    self.log_write(f"🗑 Borrado: {os.path.basename(f)}")
                    aria2_file = f + ".aria2"
                    if os.path.exists(aria2_file):
                        os.remove(aria2_file)
                        self.log_write(f"🗑 Borrado .aria2: {os.path.basename(aria2_file)}")
        except Exception as e:
            self.log_write(f"Error limpiando parciales: {e}")

    def _download_thread(self, games: List[Dict]):
        total_games = len(games)
        platform = self.platform_var.get()

        for i, g in enumerate(games):
            if self.cancel_requested:
                self.log_write("⏹ Descarga cancelada por el usuario")
                break

            title_id = g["title_id"]
            dest = self.dest_var.get()
            self.current_title_id = title_id
            self.current_dest = dest

            self.root.after(0, lambda t=title_id: self.log_write(f"--- Descargando {t} ---"))
            self.root.after(0, lambda c=i+1, t=total_games: self._update_progress(0, f"{c}/{t}", "alloc"))

            cmd = [
                str(NPS_BIN), "-p", platform,
                "--title-id", title_id,
                "-o", dest,
                "-a", "--aria2-run"
            ]
            self.root.after(0, lambda c=cmd: self.log_write(f"$ {' '.join(shlex.quote(x) for x in c)}"))

            try:
                self.current_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, start_new_session=True
                )
                self.child_pids.add(self.current_proc.pid)
                in_alloc_phase = True
                for line in self.current_proc.stdout:
                    if self.cancel_requested:
                        self.log_write("⏹ Cancelación detectada, terminando proceso...")
                        break
                    line = line.strip()
                    if line:
                        self.root.after(0, lambda l=line: self.log_write(l))
                        if "FileAlloc" in line:
                            if in_alloc_phase:
                                m = re.search(r'FileAlloc:#\w+\s+([\d.]+[KMGT]?i?B)/([\d.]+[KMGT]?i?B)\((\d+)%\)', line)
                                if m:
                                    alloc_pct = int(m.group(3))
                                    self.root.after(0, lambda p=alloc_pct, c=i+1, t=total_games: self._update_progress(p, f"{c}/{t}", "alloc"))
                        elif "CN:" in line and "DL:" in line:
                            if in_alloc_phase:
                                in_alloc_phase = False
                                self.root.after(0, lambda: self._set_progress_phase("download"))
                            m = re.search(r'\((\d+)%\)', line)
                            if m:
                                pct = int(m.group(1))
                                self.root.after(0, lambda p=pct, c=i+1, t=total_games: self._update_progress(p, f"{c}/{t}", "download"))
                self.current_proc.wait()

                if self.cancel_requested:
                    self.root.after(0, lambda t=title_id, d=dest: self._cleanup_partial_files(t, d))
                    self.root.after(0, lambda t=title_id: self.log_write(f"⏹ {t} cancelado y limpiado"))
                    break

                if self.current_proc.returncode == 0:
                    self.root.after(0, lambda t=title_id: self.log_write(f"✓ {t} completado"))
                    self.root.after(0, lambda c=i+1, t=total_games: self._update_progress(100, f"{c}/{t}", "download"))
                else:
                    self.root.after(0, lambda t=title_id, c=self.current_proc.returncode: self.log_write(f"✗ {t} falló (código {c})"))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda t=title_id: self.log_write(f"✗ {t} timeout"))
            except Exception as e:
                self.root.after(0, lambda t=title_id, e=e: self.log_write(f"✗ {t} error: {e}"))
            finally:
                pid_to_discard = self.current_proc.pid if self.current_proc else None
                self.current_proc = None
                self.current_title_id = None
                self.current_dest = None
                if pid_to_discard:
                    self.child_pids.discard(pid_to_discard)

        self.root.after(0, lambda: self.log_write("=== Todas las descargas finalizadas ==="))
        self.root.after(0, lambda: self._update_progress(100, "Completado" if not self.cancel_requested else "Cancelado", "download"))
        self.root.after(0, lambda: setattr(self, "downloading", False))
        self.root.after(0, lambda: self.cancel_btn.config(state="disabled"))
        self.cancel_requested = False

    def _update_progress(self, pct: float, label: str = "", phase: str = "download"):
        self.progress_var.set(pct)
        if phase == "alloc":
            self.progress_label.config(text=f"Asignando espacio: {pct}% {label}")
            self.phase_indicator.itemconfig(self.phase_circle, fill="#3498db")
        elif phase == "download":
            self.progress_label.config(text=f"Descargando: {pct}% {label}")
            self.phase_indicator.itemconfig(self.phase_circle, fill="#27ae60")
        else:
            self.progress_label.config(text=f"{pct}% {label}")
            self.phase_indicator.itemconfig(self.phase_circle, fill="gray")
        self.progress_bar.update_idletasks()
        self.root.update_idletasks()

    def _set_progress_phase(self, phase: str):
        if phase == "alloc":
            self.phase_indicator.itemconfig(self.phase_circle, fill="#3498db")
        elif phase == "download":
            self.phase_indicator.itemconfig(self.phase_circle, fill="#27ae60")

    def choose_dest_folder(self):
        folder = filedialog.askdirectory(initialdir=self.dest_var.get())
        if folder:
            self.dest_var.set(folder)

    def open_dest_folder(self):
        import webbrowser
        webbrowser.open(f"file://{self.dest_var.get()}")


def main():
    root = tk.Tk()
    # Set icon if available
    try:
        icon_path = get_resource_path("assets/icon.png")
        if icon_path.exists():
            icon = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, icon)
    except:
        pass
    app = NPSGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()