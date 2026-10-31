import os
import sys
import json
import queue
import shutil
import threading
import subprocess
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

APP_NAME = "VANTA"
APP_VERSION = "0.2"
MC_VERSION = "1.21.11"
FABRIC_META = "https://meta.fabricmc.net/v2/versions/installer"
MODRINTH_API = "https://api.modrinth.com/v2/project/{}/version"

C = {
    "bg": "#0A0D14", "sidebar": "#0E1420", "panel": "#131B2A",
    "panel2": "#182235", "hover": "#202C43", "line": "#26334A",
    "text": "#F1F4FC", "muted": "#8996AE", "accent": "#8975FF",
    "accent_hover": "#9B8AFF", "green": "#54D6A2", "red": "#FF777F",
    "blue": "#6DA8FF",
}


def minecraft_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/minecraft"
    return Path.home() / ".minecraft"


MC_DIR = minecraft_dir()
MODS_DIR = MC_DIR / "mods"


def configure_packaged_tcl_tk():
    if not getattr(sys, "frozen", False):
        return
    bundle = Path(sys._MEIPASS)
    for folder_name, marker_name, env_name in (
        ("_tcl_data", "init.tcl", "TCL_LIBRARY"),
        ("_tk_data", "tk.tcl", "TK_LIBRARY"),
    ):
        folder = bundle / folder_name
        marker = folder / marker_name
        if not marker.is_file() and folder.is_dir():
            marker = next(folder.rglob(marker_name), None)
        if marker is None or not marker.is_file():
            raise RuntimeError(f"В комплекте VANTA не найден {marker_name}.")
        os.environ[env_name] = str(marker.parent)


def request_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "VANTA-Launcher/0.2"}
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "VANTA-Launcher/0.2"})
    with urllib.request.urlopen(request, timeout=90) as response:
        with open(destination, "wb") as output:
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                output.write(chunk)


def find_java():
    java = shutil.which("java")
    if java:
        return java
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Java",
        Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Eclipse Adoptium",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Eclipse Adoptium",
        MC_DIR / "runtime",
    ]
    for root in roots:
        if root.exists():
            for item in root.rglob("java.exe" if os.name == "nt" else "java"):
                if item.is_file():
                    return str(item)
    return None


def find_fabric_profile():
    versions = MC_DIR / "versions"
    if not versions.is_dir():
        return None
    profiles = [
        item for item in versions.iterdir()
        if item.is_dir()
        and item.name.startswith("fabric-loader-")
        and MC_VERSION in item.name
    ]
    return sorted(profiles, key=lambda item: item.name)[-1] if profiles else None


def mod_installed(name):
    return MODS_DIR.is_dir() and any(
        name.lower() in item.name.lower() for item in MODS_DIR.glob("*.jar")
    )


class VantaApp:
    def __init__(self, root):
        self.root = root
        root.title("VANTA Launcher")
        root.geometry("1240x790")
        root.minsize(1040, 680)
        root.configure(bg="#090C12")
        root.protocol("WM_DELETE_WINDOW", self.close_app)

        self.events = queue.Queue()
        self.busy = False
        self.page = "home"
        self.action_buttons = []
        self.nav_buttons = {}
        self.logs = ["VANTA запущен. Добро пожаловать."]
        self.progress_value = 0.0

        self.colors = {
            "bg": "#090C12",
            "sidebar": "#0E131D",
            "panel": "#141B28",
            "panel2": "#1B2637",
            "line": "#29364A",
            "text": "#F3F5FC",
            "muted": "#8995AA",
            "accent": "#8C7BFF",
            "accent_hover": "#A194FF",
            "green": "#55D9A5",
            "red": "#FF777F",
            "blue": "#6DA8FF",
        }
        self.java_path = find_java()
        self.fabric_profile = find_fabric_profile()

        self.build_shell()
        self.show_page("home")
        self.set_status("ГОТОВ К РАБОТЕ")
        root.after(100, self.process_events)

    # ----- Shared visual components -----
    def label(self, parent, text, size=10, color=None, bold=False, **options):
        bg = options.pop("bg", parent.cget("bg"))
        return tk.Label(
            parent, text=text, bg=bg, fg=color or self.colors["text"],
            font=("Segoe UI", size, "bold" if bold else "normal"), **options
        )

    def card(self, parent, padx=20, pady=18, bg=None):
        surface_color = bg or self.colors["panel"]
        outer = tk.Frame(parent, bg=self.colors["line"], bd=0, highlightthickness=0)
        surface = tk.Frame(outer, bg=surface_color)
        surface.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(surface, bg=surface_color)
        inner.pack(fill="both", expand=True, padx=padx, pady=pady)
        return outer, inner

    def button(self, parent, text, command, primary=False, compact=False):
        base = self.colors["accent"] if primary else self.colors["panel2"]
        hover = self.colors["accent_hover"] if primary else "#25334A"
        widget = tk.Button(
            parent, text=text, command=command, bg=base, fg=self.colors["text"],
            activebackground=hover, activeforeground=self.colors["text"],
            disabledforeground="#68758C", relief="flat", bd=0,
            cursor="hand2", padx=18 if not compact else 12,
            pady=11 if not compact else 7, font=("Segoe UI", 9, "bold"),
            takefocus=True,
        )
        widget.bind("<Enter>", lambda _e, w=widget, c=hover:
                    w.configure(bg=c) if str(w["state"]) != "disabled" else None)
        widget.bind("<Leave>", lambda _e, w=widget, c=base: w.configure(bg=c))
        self.action_buttons.append(widget)
        if self.busy:
            widget.configure(state="disabled")
        return widget

    def build_shell(self):
        shell = tk.Frame(self.root, bg=self.colors["bg"])
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, bg=self.colors["sidebar"], width=238)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        main = tk.Frame(shell, bg=self.colors["bg"])
        main.pack(side="left", fill="both", expand=True)

        self.build_sidebar()

        header = tk.Frame(main, bg=self.colors["bg"], height=82)
        header.pack(fill="x", padx=30, pady=(17, 0))
        header.pack_propagate(False)

        header_left = tk.Frame(header, bg=self.colors["bg"])
        header_left.pack(side="left", fill="y")
        self.header_title = self.label(header_left, "Главная", 19, self.colors["text"], True)
        self.header_title.pack(anchor="w", pady=(8, 0))
        self.header_subtitle = self.label(
            header_left, "Игровой центр VANTA", 9, self.colors["muted"]
        )
        self.header_subtitle.pack(anchor="w", pady=(2, 0))

        header_right = tk.Frame(header, bg=self.colors["bg"])
        header_right.pack(side="right", fill="y")
        self.status_dot = tk.Canvas(
            header_right, width=10, height=10, bg=self.colors["bg"], highlightthickness=0
        )
        self.status_dot.pack(side="left", pady=31, padx=(0, 8))
        self.status_dot.create_oval(1, 1, 9, 9, fill=self.colors["green"], outline="")
        self.header_status = self.label(header_right, "ГОТОВ К РАБОТЕ", 8, self.colors["muted"], True)
        self.header_status.pack(side="left", pady=27)

        self.content = tk.Frame(main, bg=self.colors["bg"])
        self.content.pack(fill="both", expand=True, padx=30, pady=(0, 22))

    def build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=self.colors["sidebar"])
        brand.pack(fill="x", padx=22, pady=(24, 31))
        logo = tk.Canvas(brand, width=42, height=42, bg=self.colors["sidebar"], highlightthickness=0)
        logo.pack(side="left")
        logo.create_rectangle(1, 1, 41, 41, fill=self.colors["accent"], outline="")
        logo.create_text(21, 20, text="V", fill="white", font=("Segoe UI", 24, "bold"))
        brand_text = tk.Frame(brand, bg=self.colors["sidebar"])
        brand_text.pack(side="left", padx=(11, 0))
        self.label(brand_text, "VANTA", 20, self.colors["text"], True).pack(anchor="w")
        self.label(brand_text, "MINECRAFT CLIENT", 7, self.colors["accent"], True).pack(anchor="w")

        self.label(self.sidebar, "МЕНЮ", 7, "#66738C", True).pack(anchor="w", padx=22, pady=(0, 9))
        items = [
            ("home", "⌂", "Главная"),
            ("versions", "▣", "Версии"),
            ("mods", "◇", "Моды"),
            ("settings", "⚙", "Настройки"),
        ]
        for page, glyph, title in items:
            nav = tk.Button(
                self.sidebar, text=f"  {glyph}    {title}", anchor="w",
                command=lambda p=page: self.show_page(p),
                bg=self.colors["sidebar"], fg=self.colors["muted"],
                activebackground=self.colors["panel2"], activeforeground=self.colors["text"],
                relief="flat", bd=0, padx=14, pady=12, cursor="hand2",
                font=("Segoe UI", 10, "bold"),
            )
            nav.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[page] = nav

        tk.Frame(self.sidebar, bg=self.colors["sidebar"]).pack(fill="both", expand=True)

        profile_outer, profile = self.card(self.sidebar, 14, 14)
        profile_outer.pack(fill="x", padx=13, pady=(0, 10))
        row = tk.Frame(profile, bg=self.colors["panel"])
        row.pack(fill="x")
        avatar = tk.Canvas(row, width=36, height=36, bg=self.colors["panel"], highlightthickness=0)
        avatar.pack(side="left", padx=(0, 9))
        avatar.create_oval(1, 1, 35, 35, fill="#2A3150", outline=self.colors["accent"])
        avatar.create_text(18, 18, text="V", fill="#C3B8FF", font=("Segoe UI", 15, "bold"))
        user = tk.Frame(row, bg=self.colors["panel"])
        user.pack(side="left", fill="x", expand=True)
        self.label(user, "Локальный профиль", 9, self.colors["text"], True).pack(anchor="w")
        self.label(user, "Minecraft Java", 8, self.colors["muted"]).pack(anchor="w")
        self.label(profile, "Авторизация VANTA не требуется", 7, self.colors["muted"]).pack(anchor="w", pady=(10, 0))
        self.label(
            self.sidebar, f"VANTA {APP_VERSION}  •  {MC_VERSION}",
            7, "#5E6A81"
        ).pack(anchor="w", padx=20, pady=(0, 17))

    # ----- Navigation -----
    def show_page(self, page):
        if page not in ("home", "versions", "mods", "settings"):
            page = "home"
        self.page = page
        self.action_buttons = []

        for name, nav in self.nav_buttons.items():
            nav.configure(
                bg=self.colors["panel2"] if name == page else self.colors["sidebar"],
                fg=self.colors["text"] if name == page else self.colors["muted"],
            )
        for child in self.content.winfo_children():
            child.destroy()

        meta = {
            "home": ("Главная", "Твой игровой центр"),
            "versions": ("Версии", "Управление установленными версиями Minecraft"),
            "mods": ("Моды", "Управление компонентами сборки VANTA"),
            "settings": ("Настройки", "Java, папка игры и состояние системы"),
        }
        self.header_title.configure(text=meta[page][0])
        self.header_subtitle.configure(text=meta[page][1])

        if page == "home":
            self.render_home()
        elif page == "versions":
            self.render_versions()
        elif page == "mods":
            self.render_mods()
        else:
            self.render_settings()
        self.set_action_state()

    def set_action_state(self):
        for widget in self.action_buttons:
            widget.configure(state="disabled" if self.busy else "normal")

    # ----- Home screen -----
    def render_home(self):
        hero_outer, hero = self.card(self.content, 0, 0, bg="#111A2B")
        hero_outer.pack(fill="x", pady=(0, 16))
        art = tk.Canvas(hero, height=292, bg="#111A2B", highlightthickness=0)
        art.pack(fill="x")
        art.bind("<Configure>", self.draw_hero)
        self.draw_hero()

        badge_row = tk.Frame(hero, bg="#111A2B")
        badge_row.place(x=27, y=22)
        badge_bg = "#203C38" if self.fabric_profile else "#382F25"
        badge_text = "●  ИГРА УСТАНОВЛЕНА" if self.fabric_profile else "●  ОЖИДАЕТ УСТАНОВКИ"
        self.label(badge_row, badge_text, 8, self.colors["green"] if self.fabric_profile else "#E7B66A", True, bg=badge_bg).pack(ipadx=10, ipady=6)

        title = tk.Frame(hero, bg="#111A2B")
        title.place(relx=0.035, rely=0.39, anchor="w")
        self.label(title, "VANTA", 31, self.colors["text"], True, bg="#111A2B").pack(anchor="w")
        self.label(title, f"Minecraft Java Edition  •  {MC_VERSION}  •  Fabric", 10, "#C0C9DA", bg="#111A2B").pack(anchor="w", pady=(2, 11))
        self.label(title, "Твоя сборка. Твои правила.", 9, "#A5B0C5", bg="#111A2B").pack(anchor="w")

        actions = tk.Frame(hero, bg="#111A2B")
        actions.place(relx=0.965, rely=0.86, anchor="e")
        self.button(actions, "↻  ОБНОВИТЬ", self.start_install, compact=True).pack(side="left", padx=(0, 8))
        self.button(actions, "▶  ИГРАТЬ", self.play, primary=True).pack(side="left")

        bottom = tk.Frame(self.content, bg=self.colors["bg"])
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)
        bottom.rowconfigure(0, weight=1)

        news_outer, news = self.card(bottom, 19, 17)
        news_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        row = tk.Frame(news, bg=self.colors["panel"])
        row.pack(fill="x")
        self.label(row, "Что нового", 12, self.colors["text"], True).pack(side="left")
        self.label(row, f"VANTA {APP_VERSION}", 8, self.colors["muted"]).pack(side="right")
        self.label(
            news,
            "•  Обновлённый игровой центр VANTA.\n\n"
            "•  Отдельные разделы версий, модов и настроек.\n\n"
            "•  Установка Fabric API и Sodium прямо из лаунчера.",
            9, self.colors["muted"], justify="left"
        ).pack(anchor="w", pady=(17, 0))

        mods_outer, mods = self.card(bottom, 19, 17)
        mods_outer.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        top = tk.Frame(mods, bg=self.colors["panel"])
        top.pack(fill="x")
        self.label(top, "Моды", 12, self.colors["text"], True).pack(side="left")
        self.label(top, f"{sum(mod_installed(x) for x in ('fabric-api', 'sodium'))} из 2", 8, self.colors["muted"]).pack(side="right")
        self.mod_summary(mods, "Fabric API", "fabric-api")
        self.mod_summary(mods, "Sodium", "sodium")
        self.button(mods, "ВСЕ МОДЫ  →", lambda: self.show_page("mods"), compact=True).pack(anchor="w", pady=(18, 0))

    def draw_hero(self, _event=None):
        if not hasattr(self, "content") or not self.content.winfo_exists():
            return
        canvas = getattr(self, "_hero_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            # The hero canvas is the first Canvas on the current home page.
            for outer in self.content.winfo_children():
                for child in outer.winfo_children():
                    for candidate in child.winfo_children():
                        if isinstance(candidate, tk.Canvas):
                            canvas = candidate
                            break
                    if canvas:
                        break
                if canvas:
                    break
        if canvas is None or not canvas.winfo_exists():
            return
        self._hero_canvas = canvas
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#111A2B", outline="")
        canvas.create_oval(width * 0.57, -height * 0.9, width * 1.12, height * 1.2, fill="#1B2944", outline="")
        canvas.create_oval(width * 0.72, -height * 0.55, width * 1.06, height * 1.05, fill="#202B49", outline="")
        # Original geometric VANTA motif — no copied artwork.
        for i in range(7):
            x = width * 0.72 + i * 32
            canvas.create_line(x, height * 0.12, x + 110, height * 0.9, fill="#2B3857", width=3)
        canvas.create_polygon(
            width * 0.79, height * 0.39,
            width * 0.88, height * 0.39,
            width * 0.94, height * 0.74,
            width * 0.85, height * 0.74,
            fill="#897BFF", outline=""
        )
        canvas.create_polygon(
            width * 0.85, height * 0.39,
            width * 0.94, height * 0.39,
            width * 0.88, height * 0.74,
            width * 0.79, height * 0.74,
            fill="#5546A7", outline=""
        )
        canvas.create_rectangle(0, height - 5, width, height, fill="#26334A", outline="")

    def mod_summary(self, parent, title, project):
        row = tk.Frame(parent, bg=self.colors["panel"])
        row.pack(fill="x", pady=(17, 0))
        self.label(row, title, 9, self.colors["text"], True).pack(side="left")
        installed = mod_installed(project)
        self.label(
            row, "ВКЛЮЧЁН" if installed else "НЕ УСТАНОВЛЕН",
            7, self.colors["green"] if installed else self.colors["muted"], True
        ).pack(side="right")

    # ----- Versions page -----
    def render_versions(self):
        outer, body = self.card(self.content, 22, 20)
        outer.pack(fill="x", pady=(0, 15))
        self.label(body, "JAVA EDITION", 8, self.colors["accent"], True).pack(anchor="w")
        self.label(body, MC_VERSION, 25, self.colors["text"], True).pack(anchor="w", pady=(7, 2))
        self.label(body, "Fabric Loader  •  Fabric API  •  Sodium", 9, self.colors["muted"]).pack(anchor="w")
        state = "Профиль обнаружен" if self.fabric_profile else "Профиль ещё не установлен"
        self.label(body, state, 9, self.colors["green"] if self.fabric_profile else "#E7B66A").pack(anchor="w", pady=(15, 0))

        outer, install = self.card(self.content, 22, 18)
        outer.pack(fill="x", pady=(0, 15))
        self.label(install, "УПРАВЛЕНИЕ ВЕРСИЕЙ", 8, self.colors["muted"], True).pack(anchor="w")
        self.label(install, "Базовая сборка VANTA", 13, self.colors["text"], True).pack(anchor="w", pady=(7, 3))
        self.label(install, "Установщик проверит профиль Fabric и обновит библиотеки модов.", 9, self.colors["muted"]).pack(anchor="w")
        row = tk.Frame(install, bg=self.colors["panel"])
        row.pack(anchor="w", pady=(15, 0))
        self.button(row, "УСТАНОВИТЬ / ОБНОВИТЬ", self.start_install, primary=True).pack(side="left")
        self.button(row, "ОТКРЫТЬ ПАПКУ ИГРЫ", self.open_game_folder, compact=True).pack(side="left", padx=(9, 0))

        outer, progress = self.card(self.content, 22, 17)
        outer.pack(fill="x")
        self.label(progress, "ХОД УСТАНОВКИ", 8, self.colors["muted"], True).pack(anchor="w")
        self.make_progress_widgets(progress)

    # ----- Mods page -----
    def render_mods(self):
        outer, intro = self.card(self.content, 22, 18)
        outer.pack(fill="x", pady=(0, 14))
        self.label(intro, "КОМПОНЕНТЫ СБОРКИ", 8, self.colors["accent"], True).pack(anchor="w")
        self.label(intro, "Управление модами", 19, self.colors["text"], True).pack(anchor="w", pady=(6, 3))
        self.label(intro, "Включение и отключение работает переименованием локальных JAR-файлов.", 9, self.colors["muted"]).pack(anchor="w")

        for title, project, detail in (
            ("Fabric API", "fabric-api", "Библиотека совместимости для Fabric-модов."),
            ("Sodium", "sodium", "Оптимизация рендеринга и производительности."),
        ):
            outer, body = self.card(self.content, 18, 16)
            outer.pack(fill="x", pady=(0, 10))
            row = tk.Frame(body, bg=self.colors["panel"])
            row.pack(fill="x")
            info = tk.Frame(row, bg=self.colors["panel"])
            info.pack(side="left", fill="x", expand=True)
            enabled = mod_installed(project)
            self.label(info, title, 11, self.colors["text"], True).pack(anchor="w")
            self.label(info, detail, 8, self.colors["muted"]).pack(anchor="w", pady=(4, 0))
            self.label(
                row, "ВКЛЮЧЁН" if enabled else "ОТКЛЮЧЁН / НЕТ ФАЙЛА",
                7, self.colors["green"] if enabled else self.colors["muted"], True
            ).pack(side="right", padx=(8, 12))
            action = "ОТКЛЮЧИТЬ" if enabled else "ВКЛЮЧИТЬ"
            self.button(row, action, lambda p=project: self.toggle_mod(p), compact=True).pack(side="right")

        self.button(self.content, "ОТКРЫТЬ ПАПКУ MODS", self.open_mods_folder, primary=True).pack(anchor="w", pady=(7, 0))

    def toggle_mod(self, project):
        candidates = list(MODS_DIR.glob("*.jar")) + list(MODS_DIR.glob("*.jar.disabled")) if MODS_DIR.exists() else []
        matches = [p for p in candidates if project.lower() in p.name.lower()]
        if not matches:
            messagebox.showinfo("VANTA", f"{project} не найден в папке mods. Сначала установи сборку.")
            return
        changed = []
        for file_path in matches:
            if file_path.name.endswith(".jar.disabled"):
                destination = file_path.with_name(file_path.name[:-9])
            elif file_path.name.endswith(".jar"):
                destination = file_path.with_name(file_path.name + ".disabled")
            else:
                continue
            if destination.exists():
                messagebox.showwarning("VANTA", f"Не удалось изменить имя: файл уже существует — {destination.name}")
                continue
            file_path.rename(destination)
            changed.append(destination.name)
        self.add_log(f"{project}: состояние изменено." if changed else f"{project}: изменений нет.")
        self.show_page("mods")

    def open_mods_folder(self):
        try:
            MODS_DIR.mkdir(parents=True, exist_ok=True)
            self.open_path(MODS_DIR)
        except Exception as exc:
            messagebox.showerror("VANTA", str(exc))

    # ----- Settings page -----
    def render_settings(self):
        outer, game = self.card(self.content, 22, 18)
        outer.pack(fill="x", pady=(0, 14))
        self.label(game, "ПАПКА ИГРЫ", 8, self.colors["muted"], True).pack(anchor="w")
        self.label(game, str(MC_DIR), 9, self.colors["text"], True, wraplength=760, justify="left").pack(anchor="w", pady=(8, 13))
        self.button(game, "ОТКРЫТЬ ПАПКУ", self.open_game_folder, compact=True).pack(anchor="w")

        outer, runtime = self.card(self.content, 22, 18)
        outer.pack(fill="x", pady=(0, 14))
        self.label(runtime, "JAVA RUNTIME", 8, self.colors["muted"], True).pack(anchor="w")
        self.java_value = self.label(runtime, "", 9, self.colors["text"], True, wraplength=760, justify="left")
        self.java_value.pack(anchor="w", pady=(9, 0))
        self.profile_value = self.label(runtime, "", 9, self.colors["muted"], wraplength=760, justify="left")
        self.profile_value.pack(anchor="w", pady=(5, 0))
        self.update_environment_labels()

        actions = tk.Frame(self.content, bg=self.colors["bg"])
        actions.pack(fill="x")
        self.button(actions, "ПРОВЕРИТЬ JAVA", self.refresh_diagnostics, primary=True).pack(side="left")
        self.button(actions, "ОТКРЫТЬ ОФИЦИАЛЬНЫЙ ЛАУНЧЕР", self.open_official_launcher).pack(side="left", padx=(9, 0))

        outer, note = self.card(self.content, 22, 15)
        outer.pack(fill="x", pady=(15, 0))
        self.label(note, "О ТЕКУЩЕЙ ВЕРСИИ", 8, self.colors["accent"], True).pack(anchor="w")
        self.label(
            note,
            "VANTA управляет локальной папкой Minecraft, Fabric и модами. "
            "Собственная система аккаунтов и прямой запуск игры пока не добавлены.",
            8, self.colors["muted"], wraplength=760, justify="left"
        ).pack(anchor="w", pady=(6, 0))

    def update_environment_labels(self):
        if hasattr(self, "java_value") and self.java_value.winfo_exists():
            self.java_value.configure(text=f"Java: {self.java_path or 'не найдена — требуется Java 21 x64'}")
        if hasattr(self, "profile_value") and self.profile_value.winfo_exists():
            self.profile_value.configure(text=f"Fabric: {self.fabric_profile.name if self.fabric_profile else 'профиль 1.21.11 не найден'}")

    # ----- Progress widgets -----
    def make_progress_widgets(self, parent):
        top = tk.Frame(parent, bg=self.colors["panel"])
        top.pack(fill="x")
        self.progress_percent = self.label(top, f"{int(self.progress_value * 100)}%", 9, self.colors["text"], True)
        self.progress_percent.pack(side="right")
        self.progress_canvas = tk.Canvas(parent, height=9, bg="#26334A", highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(9, 8))
        self.progress_canvas.bind("<Configure>", lambda _event: self.draw_progress())
        self.progress_status = self.label(parent, "Ожидание установки", 8, self.colors["muted"])
        self.progress_status.pack(anchor="w")
        self.draw_progress()

    def set_progress(self, value, status=None):
        self.progress_value = max(0.0, min(1.0, float(value)))
        if hasattr(self, "progress_percent") and self.progress_percent.winfo_exists():
            self.progress_percent.configure(text=f"{int(self.progress_value * 100)}%")
        if status and hasattr(self, "progress_status") and self.progress_status.winfo_exists():
            self.progress_status.configure(text=status)
        self.draw_progress()

    def draw_progress(self):
        if not hasattr(self, "progress_canvas") or not self.progress_canvas.winfo_exists():
            return
        canvas = self.progress_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill="#26334A", outline="")
        filled = int(width * self.progress_value)
        if filled:
            canvas.create_rectangle(0, 0, filled, height, fill=self.colors["accent"], outline="")

    # ----- Event queue and safe worker-to-UI updates -----
    def set_status(self, text):
        self.header_status.configure(text=text)

    def add_log(self, text):
        self.logs.append(text)
        self.logs = self.logs[-100:]
        if self.page == "home":
            self.refresh_activity()

    def refresh_activity(self):
        if not hasattr(self, "activity") or not self.activity.winfo_exists():
            return
        self.activity.configure(state="normal")
        self.activity.delete("1.0", "end")
        self.activity.insert("end", "\n".join(self.logs[-80:]))
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def post(self, event, *args):
        self.events.put((event, args))

    def process_events(self):
        try:
            while True:
                event, args = self.events.get_nowait()
                if event == "log":
                    self.add_log(args[0])
                elif event == "status":
                    self.set_status(args[0])
                elif event == "progress":
                    self.set_progress(args[0], args[1])
                elif event == "error":
                    messagebox.showerror("VANTA — ошибка", args[0])
                elif event == "finished":
                    self.busy = False
                    self.java_path = find_java()
                    self.fabric_profile = find_fabric_profile()
                    self.set_action_state()
                    self.update_environment_labels()
                    self.set_status("ГОТОВ К РАБОТЕ")
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self.process_events)

    # ----- Fabric and mod installation -----
    def start_install(self):
        if self.busy:
            return
        self.busy = True
        self.set_action_state()
        self.set_status("УСТАНОВКА…")
        self.set_progress(0.0, "Подготовка установщика")
        self.add_log("Начата установка сборки VANTA.")
        threading.Thread(target=self.install_worker, daemon=True).start()

    def install_worker(self):
        try:
            java = find_java()
            if not java:
                raise RuntimeError("Не найдена Java. Установи Java 21 x64 и проверь, что команда java доступна в PATH.")

            self.post("status", "ПОЛУЧЕНИЕ FABRIC INSTALLER…")
            self.post("progress", 0.08, "Получение метаданных Fabric")
            installers = request_json(FABRIC_META)
            if not isinstance(installers, list) or not installers:
                raise RuntimeError("Fabric не вернул список установщиков.")
            installer = installers[0]
            installer_url = installer.get("url") or installer.get("maven")
            if not installer_url:
                raise RuntimeError("Fabric не вернул URL установщика.")

            installer_path = MC_DIR / "vanta-downloads" / "fabric-installer.jar"
            self.post("log", f"Скачиваю Fabric Installer {installer.get('version', '')}…")
            download(installer_url, installer_path)
            self.post("progress", 0.24, "Установка Fabric Loader")

            command = [
                java, "-jar", str(installer_path), "client",
                "-dir", str(MC_DIR), "-mcversion", MC_VERSION, "-loader", "latest",
            ]
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            result = subprocess.run(
                command, capture_output=True, text=True, errors="replace",
                timeout=240, creationflags=flags
            )
            if result.returncode:
                details = (result.stderr or result.stdout or "нет подробностей")[-1800:]
                raise RuntimeError("Fabric Installer завершился с ошибкой:\n" + details)

            self.post("log", "Fabric Loader установлен.")
            self.post("progress", 0.56, "Получение Fabric API и Sodium")
            MODS_DIR.mkdir(parents=True, exist_ok=True)

            for index, project in enumerate(("fabric-api", "sodium")):
                self.post("status", f"ЗАГРУЗКА {project.upper()}…")
                url = MODRINTH_API.format(project) + "?" + urllib.parse.urlencode({
                    "game_versions": json.dumps([MC_VERSION]),
                    "loaders": json.dumps(["fabric"]),
                })
                versions = request_json(url)
                if not versions:
                    raise RuntimeError(f"Для {project} пока нет версии, совместимой с Minecraft {MC_VERSION}.")
                version = versions[0]
                files = version.get("files", [])
                primary = next((item for item in files if item.get("primary")), files[0] if files else None)
                if not primary or not primary.get("url") or not primary.get("filename"):
                    raise RuntimeError(f"Modrinth не вернул корректный файл для {project}.")
                download(primary["url"], MODS_DIR / primary["filename"])
                self.post("log", f"Установлен {project} {version.get('version_number', '')}.")
                self.post("progress", 0.56 + (index + 1) * 0.19, f"Установка {project}")

            self.post("progress", 1.0, "Сборка VANTA установлена")
            self.post("log", "Установка завершена. Открой Minecraft Launcher и выбери профиль Fabric.")
            self.post("status", "СБОРКА УСТАНОВЛЕНА")
        except Exception as exc:
            self.post("log", "ОШИБКА: " + str(exc))
            self.post("status", "ОШИБКА УСТАНОВКИ")
            self.post("error", str(exc))
            self.post("progress", self.progress_value, "Проверь сообщение об ошибке")
        finally:
            self.post("finished")

    # ----- Real button actions -----
    def open_path(self, path):
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def open_game_folder(self):
        try:
            MC_DIR.mkdir(parents=True, exist_ok=True)
            self.open_path(MC_DIR)
            self.add_log("Открыта папка Minecraft.")
        except Exception as exc:
            messagebox.showerror("VANTA", f"Не удалось открыть папку Minecraft:\n{exc}")

    def open_mods_folder(self):
        try:
            MODS_DIR.mkdir(parents=True, exist_ok=True)
            self.open_path(MODS_DIR)
            self.add_log("Открыта папка mods.")
        except Exception as exc:
            messagebox.showerror("VANTA", str(exc))

    def open_official_launcher(self):
        try:
            if sys.platform == "win32":
                candidates = [
                    Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                    Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Minecraft Launcher" / "MinecraftLauncher.exe",
                ]
                launcher = next((p for p in candidates if p.is_file()), None)
                if launcher:
                    os.startfile(str(launcher))
                else:
                    os.startfile("minecraft://")
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Minecraft"])
            else:
                subprocess.Popen(["minecraft-launcher"])
            self.add_log("Открыт официальный Minecraft Launcher.")
        except Exception as exc:
            messagebox.showerror("VANTA", "Не удалось открыть Minecraft Launcher.\n\n" + str(exc))

    def play(self):
        profile = find_fabric_profile()
        if not profile:
            go_install = messagebox.askyesno(
                "Сборка не установлена",
                "Профиль Fabric для Minecraft 1.21.11 не найден.\nПерейти к установке VANTA?"
            )
            if go_install:
                self.show_page("versions")
                return
        else:
            messagebox.showinfo(
                "VANTA",
                f"Профиль найден: {profile.name}\n\n"
                "Сейчас запуск передаётся установленному игровому лаунчеру. "
                "Выбери профиль Fabric в его списке."
            )
        self.open_official_launcher()

    def refresh_diagnostics(self):
        self.java_path = find_java()
        self.fabric_profile = find_fabric_profile()
        self.update_environment_labels()
        self.set_status("JAVA НАЙДЕНА" if self.java_path else "JAVA НЕ НАЙДЕНА")
        self.add_log("Выполнена проверка Java и профиля Fabric.")
        messagebox.showinfo(
            "VANTA — диагностика",
            f"Java: {self.java_path or 'не найдена'}\n"
            f"Fabric: {self.fabric_profile.name if self.fabric_profile else 'не установлен'}"
        )

    def close_app(self):
        if self.busy and not messagebox.askyesno(
            "VANTA", "Установка ещё выполняется. Закрыть лаунчер?"
        ):
            return
        self.root.destroy()



def run_self_test():
    if getattr(sys, "frozen", False):
        bundle = Path(sys._MEIPASS)
        for folder, marker in (("_tcl_data", "init.tcl"), ("_tk_data", "tk.tcl")):
            if not list((bundle / folder).rglob(marker)):
                raise RuntimeError(f"Self-test: {marker} отсутствует в комплекте.")

    interpreter = tk.Tcl()
    actual = Path(interpreter.eval("info library")).resolve()
    if getattr(sys, "frozen", False):
        expected = Path(os.environ["TCL_LIBRARY"]).resolve()
        if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
            raise RuntimeError(f"Self-test: Tcl загружен из {actual}, ожидался {expected}.")

    root = tk.Tk()
    root.withdraw()
    app = VantaApp(root)
    for page in ("home", "versions", "mods", "settings", "home"):
        app.show_page(page)
        root.update_idletasks()
        root.update()

    if set(app.nav_buttons) != {"home", "versions", "mods", "settings"}:
        raise RuntimeError("Self-test: не все разделы интерфейса созданы.")
    if not app.action_buttons or any(not str(button.cget("command")) for button in app.action_buttons):
        raise RuntimeError("Self-test: не все кнопки получили обработчики.")
    root.destroy()


if __name__ == "__main__":
    configure_packaged_tcl_tk()
    if "--self-test" in sys.argv:
        run_self_test()
        raise SystemExit(0)

    root = tk.Tk()
    app = VantaApp(root)
    root.mainloop()
