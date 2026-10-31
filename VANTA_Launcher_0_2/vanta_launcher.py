import os
import sys
import json
import threading
import subprocess
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

APP_NAME = "VANTA"
MC_VERSION = "1.21.11"
FABRIC_META = "https://meta.fabricmc.net/v2/versions/installer"
MODRINTH_API = "https://api.modrinth.com/v2/project/{}/version"

def minecraft_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/minecraft"
    return Path.home() / ".minecraft"

MC_DIR = minecraft_dir()
MODS_DIR = MC_DIR / "mods"

def configure_packaged_tcl_tk():
    """Point Tkinter at the actual Tcl/Tk script directories inside a frozen EXE."""
    if not getattr(sys, "frozen", False):
        return

    bundle_dir = Path(sys._MEIPASS)
    required_files = (
        ("_tcl_data", "init.tcl", "TCL_LIBRARY"),
        ("_tk_data", "tk.tcl", "TK_LIBRARY"),
    )

    for folder_name, marker_name, env_name in required_files:
        folder = bundle_dir / folder_name
        marker = folder / marker_name
        if not marker.is_file() and folder.is_dir():
            marker = next(folder.rglob(marker_name), None)
        if marker is None or not marker.is_file():
            raise RuntimeError(
                f"В сборке VANTA отсутствует {marker_name}. "
                f"Проверь содержимое папки {folder_name}."
            )
        os.environ[env_name] = str(marker.parent)


def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "VANTA-Launcher/0.1 (launcher prototype)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "VANTA-Launcher/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response, open(destination, "wb") as out:
        while True:
            chunk = response.read(1024 * 128)
            if not chunk:
                break
            out.write(chunk)

def find_java():
    import shutil
    java = shutil.which("java")
    if java:
        return java
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Java",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Eclipse Adoptium",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Eclipse Adoptium",
        Path(os.environ.get("APPDATA", "")) / ".minecraft" / "runtime",
    ]
    for root in candidates:
        if root.exists():
            for p in root.rglob("java.exe" if os.name == "nt" else "java"):
                return str(p)
    return None

class VantaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VANTA Launcher")
        self.root.geometry("900x570")
        self.root.minsize(800, 520)
        self.root.configure(bg="#0c0e14")
        self.busy = False

        self.bg = "#0c0e14"
        self.panel = "#141824"
        self.panel2 = "#1b2232"
        self.text = "#f1f3fa"
        self.muted = "#929bb0"
        self.accent = "#8b75ff"
        self.green = "#6fe0b2"

        self.build_ui()
        self.set_status("Готов к установке. Minecraft 1.21.11 · Fabric")

    def label(self, parent, text, size=11, color=None, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or self.text,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def build_ui(self):
        top = tk.Frame(self.root, bg=self.bg)
        top.pack(fill="x", padx=32, pady=(24, 12))
        self.label(top, "VANTA", 27, self.text, True).pack(side="left")
        self.label(top, "CLIENT  /  LAUNCHER", 9, self.accent, True).pack(side="left", padx=(14, 0), pady=(11, 0))
        self.label(top, "BETA 0.1", 9, self.muted, True).pack(side="right", pady=(12, 0))

        hero = tk.Frame(self.root, bg=self.panel, highlightthickness=1, highlightbackground="#252c3d")
        hero.pack(fill="x", padx=32, pady=12)
        inner = tk.Frame(hero, bg=self.panel)
        inner.pack(fill="x", padx=26, pady=25)
        self.label(inner, "ТВОЯ ИГРА. ТВОИ ПРАВИЛА.", 22, self.text, True).pack(anchor="w")
        self.label(inner, "Minecraft Java Edition  ·  Fabric Loader  ·  1.21.11", 11, self.muted).pack(anchor="w", pady=(8, 0))

        body = tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True, padx=32, pady=(8, 16))
        left = tk.Frame(body, bg=self.panel, highlightthickness=1, highlightbackground="#252c3d")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(body, bg=self.panel, width=260, highlightthickness=1, highlightbackground="#252c3d")
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        self.label(left, "УСТАНОВКА", 10, self.accent, True).pack(anchor="w", padx=22, pady=(20, 8))
        self.label(left, "Базовая сборка VANTA", 17, self.text, True).pack(anchor="w", padx=22)
        self.label(left, "Fabric Loader + Fabric API + Sodium", 11, self.muted).pack(anchor="w", padx=22, pady=(5, 16))
        self.progress = tk.Canvas(left, height=7, bg="#252c3d", highlightthickness=0)
        self.progress.pack(fill="x", padx=22)
        self.progress_bar = self.progress.create_rectangle(0, 0, 0, 7, fill=self.accent, width=0)
        self.status = self.label(left, "", 10, self.muted)
        self.status.pack(anchor="w", padx=22, pady=(12, 14))
        self.log = tk.Text(left, height=6, bg="#0e121b", fg="#b7c0d3", insertbackground=self.text,
                           relief="flat", font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        self.log.insert("end", "VANTA Launcher запущен.\n")
        self.log.configure(state="disabled")

        self.label(right, "УПРАВЛЕНИЕ", 10, self.accent, True).pack(anchor="w", padx=20, pady=(20, 14))
        self.install_btn = self.button(right, "УСТАНОВИТЬ СБОРКУ", self.install, self.accent, self.bg)
        self.install_btn.pack(fill="x", padx=18, pady=5, ipady=11)
        self.play_btn = self.button(right, "ИГРАТЬ", self.play, "#283247", self.text)
        self.play_btn.pack(fill="x", padx=18, pady=5, ipady=11)
        self.button(right, "ОТКРЫТЬ ПАПКУ .MINECRAFT", self.open_folder, "#20283a", self.text).pack(fill="x", padx=18, pady=5, ipady=8)
        self.label(right, "ВЕРСИЯ", 9, self.muted, True).pack(anchor="w", padx=20, pady=(24, 3))
        self.label(right, "Minecraft 1.21.11", 11, self.text, True).pack(anchor="w", padx=20)
        self.label(right, "Fabric · Sodium · Fabric API", 9, self.muted).pack(anchor="w", padx=20, pady=(4, 0))
        self.label(right, "АККАУНТ", 9, self.muted, True).pack(anchor="w", padx=20, pady=(20, 3))
        self.label(right, "Авторизация через официальный\nMinecraft Launcher", 9, self.muted).pack(anchor="w", padx=20)

        footer = tk.Frame(self.root, bg=self.bg)
        footer.pack(fill="x", padx=32, pady=(0, 14))
        self.label(footer, "VANTA is an independent launcher prototype. Not affiliated with Mojang or Microsoft.", 8, "#667086").pack(anchor="w")

    def button(self, parent, text, command, bg, fg):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=self.accent,
                         activeforeground=self.text, relief="flat", bd=0, cursor="hand2",
                         font=("Segoe UI", 9, "bold"))

    def log_line(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, msg):
        self.status.configure(text=msg)

    def set_progress(self, value):
        self.progress.update_idletasks()
        width = max(0, self.progress.winfo_width())
        self.progress.coords(self.progress_bar, 0, 0, width * max(0, min(1, value)), 7)

    def run_bg(self, fn):
        if self.busy:
            return
        self.busy = True
        self.install_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(fn,), daemon=True).start()

    def _worker(self, fn):
        try:
            fn()
        except Exception as exc:
            error_text = str(exc)
            self.root.after(0, lambda msg=error_text: self.log_line("ОШИБКА: " + msg))
            self.root.after(0, lambda: self.set_status("Не удалось завершить операцию. См. журнал."))
            self.root.after(0, lambda msg=error_text: messagebox.showerror("VANTA", msg))
        finally:
            self.busy = False
            self.root.after(0, lambda: self.install_btn.configure(state="normal"))

    def install(self):
        self.run_bg(self._install)

    def _install(self):
        self.root.after(0, lambda: self.set_status("Подготовка Fabric Loader..."))
        self.root.after(0, lambda: self.log_line("Проверяю Java и метаданные Fabric..."))
        java = find_java()
        if not java:
            raise RuntimeError("Не найдена Java. Установи Java 21 (64-bit), затем повтори установку.")
        installers = request_json(FABRIC_META)
        installer = installers[0]
        installer_url = installer.get("url") or installer.get("maven")
        if not installer_url:
            raise RuntimeError("Fabric не вернул ссылку на установщик.")
        installer_path = MC_DIR / "vanta-downloads" / "fabric-installer.jar"
        self.root.after(0, lambda: self.log_line("Скачиваю Fabric Installer " + installer.get("version", "") + "..."))
        download(installer_url, installer_path)
        self.root.after(0, lambda: self.set_progress(0.25))
        self.root.after(0, lambda: self.set_status("Установка Fabric Loader..."))
        cmd = [java, "-jar", str(installer_path), "client", "-dir", str(MC_DIR),
               "-mcversion", MC_VERSION, "-loader", "latest"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError("Fabric Installer завершился с ошибкой:\n" + (result.stderr or result.stdout)[-1800:])
        self.root.after(0, lambda: self.log_line("Fabric Loader установлен."))
        self.root.after(0, lambda: self.set_progress(0.55))
        MODS_DIR.mkdir(parents=True, exist_ok=True)
        for idx, project in enumerate(("fabric-api", "sodium")):
            self.root.after(0, lambda p=project: self.set_status("Скачиваю " + p + "..."))
            versions_url = MODRINTH_API.format(project) + "?" + urllib.parse.urlencode({
                "game_versions": json.dumps([MC_VERSION]), "loaders": json.dumps(["fabric"])
            })
            versions = request_json(versions_url)
            if not versions:
                raise RuntimeError(f"Для {project} пока нет совместимой версии Minecraft {MC_VERSION}.")
            version = versions[0]
            files_list = version.get("files", [])
            primary = next((f for f in files_list if f.get("primary")), files_list[0] if files_list else None)
            if not primary:
                raise RuntimeError(f"Modrinth не вернул файл для {project}.")
            dest = MODS_DIR / primary["filename"]
            download(primary["url"], dest)
            self.root.after(0, lambda p=project, v=version.get("version_number", ""): self.log_line(f"Установлен {p} {v}"))
            self.root.after(0, lambda x=0.55 + (idx + 1) * 0.2: self.set_progress(x))
        self.root.after(0, lambda: self.set_progress(1))
        self.root.after(0, lambda: self.set_status("Готово! Выбери профиль Fabric в официальном лаунчере."))
        self.root.after(0, lambda: self.log_line("Установка завершена. Нажми «Играть» и выбери профиль Fabric Loader 1.21.11."))

    def play(self):
        if sys.platform == "win32":
            candidates = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "Minecraft.exe",
            ]
            launcher = next((p for p in candidates if p.exists()), None)
            try:
                if launcher:
                    os.startfile(str(launcher))
                else:
                    os.startfile("minecraft://")
            except OSError as exc:
                messagebox.showerror(
                    "VANTA",
                    "Не удалось открыть Minecraft Launcher. Убедись, что официальный лаунчер установлен.\n\n" + str(exc)
                )
                return
        else:
            messagebox.showinfo("VANTA", "Открой официальный Minecraft Launcher и выбери профиль Fabric Loader 1.21.11.")
        self.set_status("Открой профиль Fabric Loader 1.21.11 в официальном лаунчере.")

    def open_folder(self):
        MC_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(MC_DIR))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(MC_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(MC_DIR)])

if __name__ == "__main__":
    # Set Tcl/Tk paths before initializing any Tcl interpreter or Tk window.
    configure_packaged_tcl_tk()

    # CI smoke test: initialize Tcl, build the real UI, update it, and exit.
    if "--self-test" in sys.argv:
        tcl = tk.Tcl()
        tcl.eval("info library")
        test_root = tk.Tk()
        test_root.withdraw()
        VantaApp(test_root)
        test_root.update_idletasks()
        test_root.update()
        test_root.destroy()
        raise SystemExit(0)

    root = tk.Tk()
    app = VantaApp(root)
    root.mainloop()
