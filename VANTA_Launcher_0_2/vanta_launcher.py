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
        root.geometry("1180x760")
        root.minsize(980, 660)
        root.configure(bg=C["bg"])
        root.protocol("WM_DELETE_WINDOW", self.close_app)

        self.events = queue.Queue()
        self.busy = False
        self.page = "home"
        self.action_buttons = []
        self.nav_buttons = {}
        self.progress_value = 0.0
        self.logs = ["VANTA запущен. Добро пожаловать."]
        self.java_path = find_java()
        self.fabric_profile = find_fabric_profile()

        self.build_shell()
        self.show_page("home")
        self.set_status("Готов к работе")
        root.after(100, self.process_events)

    # ----- Common widgets -----
    def label(self, parent, text, size=10, color=None, bold=False, **options):
        bg = options.pop("bg", parent.cget("bg"))
        return tk.Label(
            parent, text=text, bg=bg, fg=color or C["text"],
            font=("Segoe UI", size, "bold" if bold else "normal"), **options
        )

    def card(self, parent, padx=20, pady=18, bg=None):
        color = bg or C["panel"]
        outer = tk.Frame(parent, bg=C["line"], bd=0, highlightthickness=0)
        surface = tk.Frame(outer, bg=color)
        surface.pack(fill="both", expand=True, padx=1, pady=1)
        body = tk.Frame(surface, bg=color)
        body.pack(fill="both", expand=True, padx=padx, pady=pady)
        return outer, body

    def button(self, parent, text, command, primary=False, compact=False):
        base = C["accent"] if primary else C["panel2"]
        over = C["accent_hover"] if primary else C["hover"]
        widget = tk.Button(
            parent, text=text, command=command, bg=base, fg=C["text"],
            activebackground=over, activeforeground=C["text"],
            disabledforeground="#65718A", relief="flat", bd=0,
            cursor="hand2", padx=16 if not compact else 12,
            pady=10 if not compact else 7, font=("Segoe UI", 9, "bold"),
            takefocus=True,
        )
        widget.bind("<Enter>", lambda _e, b=widget, color=over:
                    b.configure(bg=color) if str(b["state"]) != "disabled" else None)
        widget.bind("<Leave>", lambda _e, b=widget, color=base: b.configure(bg=color))
        self.action_buttons.append(widget)
        if self.busy:
            widget.configure(state="disabled")
        return widget

    # ----- Window shell -----
    def build_shell(self):
        shell = tk.Frame(self.root, bg=C["bg"])
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, bg=C["sidebar"], width=224)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        main = tk.Frame(shell, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True)

        self.build_sidebar()

        header = tk.Frame(main, bg=C["bg"], height=76)
        header.pack(fill="x", padx=30, pady=(18, 4))
        header.pack_propagate(False)

        left = tk.Frame(header, bg=C["bg"])
        left.pack(side="left", fill="y")
        self.header_title = self.label(left, "Главная", 19, C["text"], True)
        self.header_title.pack(anchor="w", pady=(7, 0))
        self.header_subtitle = self.label(left, "Твой игровой центр", 9, C["muted"])
        self.header_subtitle.pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=C["bg"])
        right.pack(side="right", fill="y")
        dot = tk.Canvas(right, width=9, height=9, bg=C["bg"], highlightthickness=0)
        dot.pack(side="left", pady=30, padx=(0, 7))
        dot.create_oval(1, 1, 8, 8, fill=C["green"], outline="")
        self.header_status = self.label(right, "Готов к работе", 9, C["muted"])
        self.header_status.pack(side="left", pady=25)

        self.content = tk.Frame(main, bg=C["bg"])
        self.content.pack(fill="both", expand=True, padx=30, pady=(2, 18))

    def build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=C["sidebar"])
        brand.pack(fill="x", padx=22, pady=(25, 36))

        logo = tk.Canvas(brand, width=39, height=39, bg=C["sidebar"], highlightthickness=0)
        logo.pack(side="left")
        logo.create_rectangle(1, 1, 38, 38, fill=C["accent"], outline="")
        logo.create_text(19, 19, text="V", fill="white", font=("Segoe UI", 22, "bold"))
        name = tk.Frame(brand, bg=C["sidebar"])
        name.pack(side="left", padx=(10, 0))
        self.label(name, "VANTA", 19, C["text"], True).pack(anchor="w")
        self.label(name, "CLIENT  /  BETA", 7, C["accent"], True).pack(anchor="w")

        self.label(self.sidebar, "РАБОЧЕЕ ПРОСТРАНСТВО", 7, "#66738C", True).pack(
            anchor="w", padx=22, pady=(0, 10)
        )
        for page, symbol, title in (
            ("home", "⌂", "Главная"),
            ("install", "↓", "Установка"),
            ("settings", "⚙", "Настройки"),
        ):
            nav = tk.Button(
                self.sidebar, text=f"  {symbol}    {title}", anchor="w",
                command=lambda p=page: self.show_page(p),
                bg=C["sidebar"], fg=C["muted"],
                activebackground=C["panel2"], activeforeground=C["text"],
                relief="flat", bd=0, padx=13, pady=12, cursor="hand2",
                font=("Segoe UI", 10, "bold"),
            )
            nav.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[page] = nav

        tk.Frame(self.sidebar, bg=C["sidebar"]).pack(fill="both", expand=True)
        outer, account = self.card(self.sidebar, 13, 13)
        outer.pack(fill="x", padx=13, pady=(0, 10))
        self.label(account, "АККАУНТ MICROSOFT", 7, C["muted"], True).pack(anchor="w")
        self.label(account, "Не подключён", 10, C["text"], True).pack(anchor="w", pady=(7, 2))
        self.label(
            account, "Вход выполняется через\nофициальный лаунчер",
            8, C["muted"], justify="left"
        ).pack(anchor="w")
        self.label(
            self.sidebar, f"VANTA {APP_VERSION}  •  MC {MC_VERSION}",
            7, "#5E6A81"
        ).pack(anchor="w", padx=20, pady=(0, 17))

    # ----- Navigation / pages -----
    def show_page(self, page):
        if page not in ("home", "install", "settings"):
            page = "home"
        self.page = page
        self.action_buttons = []

        for name, nav in self.nav_buttons.items():
            nav.configure(
                bg=C["panel2"] if name == page else C["sidebar"],
                fg=C["text"] if name == page else C["muted"],
            )
        for child in self.content.winfo_children():
            child.destroy()

        metadata = {
            "home": ("Главная", "Твой игровой центр"),
            "install": ("Установка", "Подготовь Minecraft и компоненты VANTA"),
            "settings": ("Настройки", "Пути, Java и состояние установки"),
        }
        self.header_title.configure(text=metadata[page][0])
        self.header_subtitle.configure(text=metadata[page][1])

        if page == "home":
            self.render_home()
        elif page == "install":
            self.render_install()
        else:
            self.render_settings()
        self.set_action_state()

    def set_action_state(self):
        for widget in self.action_buttons:
            widget.configure(state="disabled" if self.busy else "normal")

    def render_home(self):
        outer, hero = self.card(self.content, 24, 23)
        outer.pack(fill="x", pady=(0, 15))
        layout = tk.Frame(hero, bg=C["panel"])
        layout.pack(fill="x")

        left = tk.Frame(layout, bg=C["panel"])
        left.pack(side="left", fill="both", expand=True)
        self.label(left, "VANTA  /  JAVA EDITION", 8, C["accent"], True).pack(anchor="w")
        self.label(left, "Твой Minecraft.\nТвои правила.", 25, C["text"], True,
                   justify="left").pack(anchor="w", pady=(11, 7))
        self.label(
            left,
            "Установи сборку VANTA и переходи к игре.\n"
            "Fabric Loader, Fabric API и Sodium — в одном месте.",
            9, C["muted"], justify="left"
        ).pack(anchor="w")

        controls = tk.Frame(left, bg=C["panel"])
        controls.pack(anchor="w", pady=(18, 0))
        self.button(controls, "УСТАНОВИТЬ СБОРКУ", self.start_install, True).pack(side="left", padx=(0, 8))
        self.button(controls, "ЗАПУСТИТЬ", self.play).pack(side="left")

        art = tk.Canvas(layout, width=190, height=160, bg=C["panel"], highlightthickness=0)
        art.pack(side="right", padx=(15, 5))
        art.create_oval(26, 9, 165, 148, fill="#1D2540", outline="")
        art.create_oval(47, 27, 145, 125, fill="#29264F", outline="")
        art.create_rectangle(77, 46, 131, 112, fill=C["accent"], outline="")
        art.create_text(104, 79, text="V", fill="white", font=("Segoe UI", 44, "bold"))
        art.create_oval(140, 8, 158, 26, fill=C["green"], outline="")
        art.create_oval(20, 117, 32, 129, fill=C["blue"], outline="")

        stats = tk.Frame(self.content, bg=C["bg"])
        stats.pack(fill="x", pady=(0, 15))
        for column in range(3):
            stats.grid_columnconfigure(column, weight=1, uniform="stats")
        mods_ok = mod_installed("fabric-api") and mod_installed("sodium")
        self.stat_card(stats, 0, "ВЕРСИЯ ИГРЫ", MC_VERSION, "Minecraft Java Edition")
        self.stat_card(stats, 1, "ЗАГРУЗЧИК", "Fabric",
                       "Профиль обнаружен" if self.fabric_profile else "Ожидает установки")
        self.stat_card(stats, 2, "МОДЫ VANTA", "2 / 2" if mods_ok else "Не все установлены",
                       "Fabric API + Sodium")

        outer, activity = self.card(self.content, 18, 14)
        outer.pack(fill="both", expand=True)
        top = tk.Frame(activity, bg=C["panel"])
        top.pack(fill="x", pady=(0, 8))
        self.label(top, "Последняя активность", 11, C["text"], True).pack(side="left")
        self.label(top, "ЖУРНАЛ", 7, C["muted"], True).pack(side="right")
        self.activity = tk.Text(
            activity, height=7, bg="#0D1421", fg="#AAB7CE",
            insertbackground=C["text"], relief="flat", bd=0,
            padx=12, pady=9, font=("Consolas", 9), wrap="word",
            state="disabled",
        )
        self.activity.pack(fill="both", expand=True)
        self.refresh_activity()

    def stat_card(self, parent, column, title, value, subtitle):
        outer, body = self.card(parent, 15, 13)
        outer.grid(
            row=0, column=column, sticky="nsew",
            padx=(0 if column == 0 else 6, 6 if column < 2 else 0)
        )
        self.label(body, title, 7, C["muted"], True).pack(anchor="w")
        self.label(body, value, 13, C["text"], True).pack(anchor="w", pady=(7, 2))
        self.label(body, subtitle, 8, C["muted"]).pack(anchor="w")

    def refresh_activity(self):
        if not hasattr(self, "activity") or not self.activity.winfo_exists():
            return
        self.activity.configure(state="normal")
        self.activity.delete("1.0", "end")
        self.activity.insert("end", "\n".join(self.logs[-80:]))
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def render_install(self):
        outer, intro = self.card(self.content, 22, 20)
        outer.pack(fill="x", pady=(0, 14))
        self.label(intro, "ГОТОВАЯ СБОРКА", 8, C["accent"], True).pack(anchor="w")
        self.label(intro, "VANTA Base", 20, C["text"], True).pack(anchor="w", pady=(6, 3))
        self.label(
            intro, f"Minecraft Java {MC_VERSION}  •  Fabric Loader  •  Fabric API  •  Sodium",
            9, C["muted"]
        ).pack(anchor="w")

        outer, components = self.card(self.content, 20, 17)
        outer.pack(fill="x", pady=(0, 14))
        self.label(components, "КОМПОНЕНТЫ УСТАНОВКИ", 8, C["muted"], True).pack(anchor="w")
        for title, detail in (
            ("Fabric Loader", "Создаёт игровой профиль Fabric"),
            ("Fabric API", "Базовая библиотека для Fabric-модов"),
            ("Sodium", "Оптимизация графики и производительности"),
        ):
            row = tk.Frame(components, bg=C["panel"])
            row.pack(fill="x", pady=(12, 0))
            dot = tk.Canvas(row, width=10, height=10, bg=C["panel"], highlightthickness=0)
            dot.pack(side="left", padx=(0, 10), pady=2)
            dot.create_oval(1, 1, 9, 9, fill=C["green"], outline="")
            text_box = tk.Frame(row, bg=C["panel"])
            text_box.pack(side="left", fill="x", expand=True)
            self.label(text_box, title, 9, C["text"], True).pack(anchor="w")
            self.label(text_box, detail, 8, C["muted"]).pack(anchor="w", pady=(2, 0))

        outer, progress = self.card(self.content, 20, 17)
        outer.pack(fill="x", pady=(0, 14))
        row = tk.Frame(progress, bg=C["panel"])
        row.pack(fill="x")
        self.label(row, "ХОД УСТАНОВКИ", 8, C["muted"], True).pack(side="left")
        self.progress_percent = self.label(row, f"{int(self.progress_value * 100)}%", 9, C["text"], True)
        self.progress_percent.pack(side="right")
        self.progress_canvas = tk.Canvas(progress, height=9, bg="#26334A", highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(10, 9))
        self.progress_canvas.bind("<Configure>", lambda _e: self.draw_progress())
        self.progress_status = self.label(progress, "Ожидание установки", 8, C["muted"])
        self.progress_status.pack(anchor="w")
        self.draw_progress()

        actions = tk.Frame(self.content, bg=C["bg"])
        actions.pack(fill="x")
        self.button(actions, "УСТАНОВИТЬ / ОБНОВИТЬ", self.start_install, True).pack(side="left")
        self.button(actions, "ОТКРЫТЬ ПАПКУ ИГРЫ", self.open_game_folder).pack(side="left", padx=(9, 0))

    def render_settings(self):
        outer, path_card = self.card(self.content, 20, 18)
        outer.pack(fill="x", pady=(0, 14))
        self.label(path_card, "ПАПКА MINECRAFT", 8, C["muted"], True).pack(anchor="w")
        self.label(path_card, str(MC_DIR), 9, C["text"], True,
                   wraplength=700, justify="left").pack(anchor="w", pady=(8, 13))
        self.button(path_card, "ОТКРЫТЬ ПАПКУ", self.open_game_folder, compact=True).pack(anchor="w")

        outer, environment = self.card(self.content, 20, 18)
        outer.pack(fill="x", pady=(0, 14))
        self.label(environment, "СОСТОЯНИЕ СИСТЕМЫ", 8, C["muted"], True).pack(anchor="w")
        self.java_value = self.label(environment, "", 9, C["text"], True,
                                     wraplength=700, justify="left")
        self.java_value.pack(anchor="w", pady=(10, 3))
        self.profile_value = self.label(environment, "", 9, C["muted"],
                                        wraplength=700, justify="left")
        self.profile_value.pack(anchor="w", pady=(2, 0))
        self.update_environment_labels()

        actions = tk.Frame(self.content, bg=C["bg"])
        actions.pack(fill="x")
        self.button(actions, "ПРОВЕРИТЬ JAVA И ПРОФИЛЬ", self.refresh_diagnostics, True).pack(side="left")
        self.button(actions, "ОТКРЫТЬ MINECRAFT LAUNCHER", self.open_official_launcher).pack(side="left", padx=(9, 0))

        outer, note = self.card(self.content, 20, 15)
        outer.pack(fill="x", pady=(17, 0))
        self.label(note, "ПРИМЕЧАНИЕ", 8, C["accent"], True).pack(anchor="w")
        self.label(
            note,
            "В этой версии авторизация и запуск игры пока выполняются официальным Minecraft Launcher. "
            "VANTA устанавливает сборку и открывает официальный лаунчер. Собственная Microsoft-авторизация "
            "и прямой запуск будут отдельным этапом разработки.",
            8, C["muted"], wraplength=760, justify="left"
        ).pack(anchor="w", pady=(6, 0))

    def update_environment_labels(self):
        if hasattr(self, "java_value") and self.java_value.winfo_exists():
            self.java_value.configure(
                text=f"Java: {self.java_path or 'не найдена — нужна Java 21 x64'}"
            )
        if hasattr(self, "profile_value") and self.profile_value.winfo_exists():
            self.profile_value.configure(
                text=f"Fabric: {self.fabric_profile.name if self.fabric_profile else 'профиль 1.21.11 пока не найден'}"
            )

    # ----- Status and event queue -----
    def set_status(self, text):
        self.header_status.configure(text=text)

    def add_log(self, text):
        self.logs.append(text)
        self.logs = self.logs[-100:]
        self.refresh_activity()

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
        fill_width = int(width * self.progress_value)
        if fill_width:
            canvas.create_rectangle(0, 0, fill_width, height, fill=C["accent"], outline="")

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
                    self.set_action_state()
                    self.java_path = find_java()
                    self.fabric_profile = find_fabric_profile()
                    self.update_environment_labels()
                    self.set_status("Готов к работе")
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self.process_events)

    # ----- Installation task -----
    def start_install(self):
        if self.busy:
            return
        self.busy = True
        self.set_action_state()
        self.set_status("Установка выполняется…")
        self.set_progress(0.0, "Подготовка установки")
        self.add_log("Начата установка сборки VANTA.")
        threading.Thread(target=self.install_worker, daemon=True).start()

    def install_worker(self):
        try:
            java = find_java()
            if not java:
                raise RuntimeError(
                    "Не найдена Java. Установи Java 21 x64 и проверь, что команда java доступна в PATH."
                )

            self.post("status", "Получение Fabric Installer…")
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
                self.post("status", f"Загрузка {project}…")
                url = MODRINTH_API.format(project) + "?" + urllib.parse.urlencode({
                    "game_versions": json.dumps([MC_VERSION]),
                    "loaders": json.dumps(["fabric"]),
                })
                versions = request_json(url)
                if not versions:
                    raise RuntimeError(
                        f"Для {project} пока нет версии, совместимой с Minecraft {MC_VERSION}."
                    )
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
            self.post("status", "Сборка успешно установлена")
        except Exception as exc:
            self.post("log", "ОШИБКА: " + str(exc))
            self.post("status", "Установка не завершена")
            self.post("error", str(exc))
            self.post("progress", self.progress_value, "Проверь сообщение об ошибке")
        finally:
            self.post("finished")

    # ----- Working button actions -----
    def open_game_folder(self):
        try:
            MC_DIR.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(MC_DIR))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(MC_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(MC_DIR)])
            self.add_log("Открыта папка Minecraft.")
        except Exception as exc:
            messagebox.showerror("VANTA", f"Не удалось открыть папку Minecraft:\n{exc}")

    def open_official_launcher(self):
        try:
            if sys.platform == "win32":
                candidates = [
                    Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                    Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "Minecraft Launcher" / "MinecraftLauncher.exe",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Minecraft Launcher" / "MinecraftLauncher.exe",
                ]
                launcher = next((path for path in candidates if path.is_file()), None)
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
            messagebox.showerror(
                "VANTA",
                "Не удалось открыть Minecraft Launcher. Убедись, что он установлен.\n\n" + str(exc)
            )

    def play(self):
        profile = find_fabric_profile()
        if not profile:
            install_first = messagebox.askyesno(
                "Сборка ещё не установлена",
                "Профиль Fabric для Minecraft 1.21.11 не найден.\n"
                "Перейти к установке VANTA?\n\nДа — установить. Нет — открыть официальный лаунчер."
            )
            if install_first:
                self.show_page("install")
                return
        else:
            messagebox.showinfo(
                "VANTA",
                f"Профиль обнаружен: {profile.name}\n\n"
                "Сейчас запуск передаётся официальному Minecraft Launcher. "
                "Выбери этот профиль в списке установок."
            )
        self.open_official_launcher()

    def refresh_diagnostics(self):
        self.java_path = find_java()
        self.fabric_profile = find_fabric_profile()
        self.update_environment_labels()
        self.set_status("Java обнаружена" if self.java_path else "Java не найдена")
        self.add_log("Выполнена проверка Java и профиля Fabric.")
        if not self.java_path:
            messagebox.showwarning("VANTA", "Java не найдена. Для установки Fabric нужна Java 21 x64.")
        else:
            messagebox.showinfo(
                "VANTA",
                "Проверка завершена.\n"
                f"Java: {self.java_path}\n"
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
    for page in ("home", "install", "settings", "home"):
        app.show_page(page)
        root.update_idletasks()
        root.update()

    if set(app.nav_buttons) != {"home", "install", "settings"}:
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
