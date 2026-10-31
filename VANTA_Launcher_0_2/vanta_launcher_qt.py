import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.parse
import webbrowser
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import minecraft_launcher_lib

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QProgressBar,
    QTextEdit, QMessageBox, QFileDialog, QSlider, QCheckBox, QSizePolicy,
    QInputDialog
)
from PySide6.QtGui import QDesktopServices

APP_VERSION = "0.5"
MC_VERSION = "1.21.11"
FABRIC_META = "https://meta.fabricmc.net/v2/versions/installer"
MODRINTH_API = "https://api.modrinth.com/v2/project/{}/version"
BG = "#0b0d12"
SIDEBAR = "#10131a"
PANEL = "#151922"
PANEL_ALT = "#1b202b"
LINE = "#282e3b"
TEXT = "#f3f4f8"
MUTED = "#9299a8"
ACCENT = "#8d83ff"
GREEN = "#56d6a3"

def minecraft_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/minecraft"
    return Path.home() / ".minecraft"

def app_config_path():
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / "VANTA"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "VANTA"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "vanta"
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.json"


def load_settings():
    try:
        with app_config_path().open("r", encoding="utf-8") as stream:
            data = json.load(stream)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


SETTINGS = load_settings()
MC_DIR = Path(SETTINGS.get("game_directory") or minecraft_dir()).expanduser()
MODS_DIR = MC_DIR / "mods"


def save_settings():
    SETTINGS["game_directory"] = str(MC_DIR)
    target = app_config_path()
    temp = target.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(SETTINGS, stream, ensure_ascii=False, indent=2)
    temp.replace(target)

def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "VANTA-Launcher/0.4"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "VANTA-Launcher/0.4"})
    with urllib.request.urlopen(req, timeout=90) as response, open(destination, "wb") as out:
        shutil.copyfileobj(response, out)

def find_java():
    java = shutil.which("java")
    if java:
        return java
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Java",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Eclipse Adoptium",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Eclipse Adoptium",
        MC_DIR / "runtime",
    ]
    for root in roots:
        if root.exists():
            for item in root.rglob("java.exe" if os.name == "nt" else "java"):
                if item.is_file():
                    return str(item)
    return None

def find_fabric_profile(directory=None):
    versions = Path(directory or MC_DIR) / "versions"
    if not versions.is_dir():
        return None
    profiles = [p for p in versions.iterdir() if p.is_dir()
                and p.name.startswith("fabric-loader-") and MC_VERSION in p.name]
    return sorted(profiles, key=lambda p: p.name)[-1] if profiles else None

def mod_files():
    if not MODS_DIR.is_dir():
        return []
    return sorted([p for p in MODS_DIR.iterdir()
                   if p.is_file() and (p.name.endswith(".jar") or p.name.endswith(".jar.disabled"))])

def open_path(path):
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

class Hero(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(270)
        self.setObjectName("hero")
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor("#171c2a"))
        grad.setColorAt(.55, QColor("#20233a"))
        grad.setColorAt(1, QColor("#111722"))
        p.fillRect(self.rect(), grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(141, 131, 255, 24))
        p.drawEllipse(int(self.width()*.64), -100, 440, 440)
        p.setBrush(QColor(141, 131, 255, 17))
        p.drawEllipse(int(self.width()*.73), -40, 300, 300)
        p.setPen(QColor(118, 111, 190, 35))
        for i in range(9):
            x = int(self.width()*.67) + i*38
            p.drawLine(x, 0, x+170, self.height())
        p.end()
        super().paintEvent(event)

class InstallWorker(QThread):
    progress = Signal(int, str)
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, game_directory):
        super().__init__()
        self.game_directory = Path(game_directory)
        self.mods_directory = self.game_directory / "mods"

    def run(self):
        try:
            java = find_java()
            if not java:
                raise RuntimeError("Не найдена Java. Установи Java 21 x64 и добавь её в PATH.")

            last_status = ["Подготовка загрузки Minecraft"]
            self.progress.emit(2, "Проверка официальных файлов Minecraft")
            self.log.emit(f"Папка установки: {self.game_directory}")

            def set_status(status):
                last_status[0] = str(status)
                self.progress.emit(5, last_status[0])

            def set_max(maximum):
                self._progress_max = max(1, int(maximum))

            def set_progress(value):
                maximum = max(1, getattr(self, "_progress_max", 100))
                percent = min(42, 5 + int(37 * int(value) / maximum))
                self.progress.emit(percent, last_status[0])

            callback = {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}
            self.log.emit(f"Загружаю официальные файлы Minecraft {MC_VERSION}…")
            minecraft_launcher_lib.install.install_minecraft_version(
                MC_VERSION, str(self.game_directory), callback=callback
            )
            self.progress.emit(44, "Установка Fabric Loader")

            installers = request_json(FABRIC_META)
            if not installers:
                raise RuntimeError("Fabric не вернул список установщиков.")
            installer = installers[0]
            installer_url = installer.get("url") or installer.get("maven")
            if not installer_url:
                raise RuntimeError("Не найден URL Fabric Installer.")

            jar = self.game_directory / "vanta-downloads" / "fabric-installer.jar"
            self.log.emit("Загрузка Fabric Installer…")
            download(installer_url, jar)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            result = subprocess.run(
                [java, "-jar", str(jar), "client", "-dir", str(self.game_directory),
                 "-mcversion", MC_VERSION, "-loader", "latest"],
                capture_output=True, text=True, errors="replace", timeout=300,
                creationflags=flags, cwd=str(self.game_directory)
            )
            if result.returncode:
                details = (result.stderr or result.stdout or "Fabric Installer завершился с ошибкой.")[-1800:]
                raise RuntimeError(details)

            self.progress.emit(62, "Подготовка папки модов")
            self.mods_directory.mkdir(parents=True, exist_ok=True)
            for i, project in enumerate(("fabric-api", "sodium")):
                self.progress.emit(64 + i * 17, f"Загрузка {project}")
                url = MODRINTH_API.format(project) + "?" + urllib.parse.urlencode({
                    "game_versions": json.dumps([MC_VERSION]),
                    "loaders": json.dumps(["fabric"])
                })
                versions = request_json(url)
                if not versions:
                    raise RuntimeError(f"Нет совместимой версии {project} для Minecraft {MC_VERSION}.")
                files = versions[0].get("files", [])
                primary = next((x for x in files if x.get("primary")), files[0] if files else None)
                if not primary or not primary.get("url") or not primary.get("filename"):
                    raise RuntimeError(f"Modrinth не вернул файл {project}.")
                download(primary["url"], self.mods_directory / primary["filename"])
                self.log.emit(f"Установлен {project} {versions[0].get('version_number', '')}")

            self.progress.emit(100, "Minecraft и сборка VANTA готовы")
            self.done.emit(
                True,
                f"Minecraft {MC_VERSION}, Fabric Loader, Fabric API и Sodium установлены в:\n"
                f"{self.game_directory}\n\nДля запуска выполни вход Microsoft с аккаунтом, "
                "у которого есть Minecraft: Java Edition."
            )
        except Exception as exc:
            self.done.emit(False, str(exc))


class LoginWorker(QThread):
    done = Signal(bool, object)

    def __init__(self, client_id):
        super().__init__()
        self.client_id = client_id

    def run(self):
        server = None
        try:
            from minecraft_launcher_lib import microsoft_account

            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.server.callback_path = self.path
                    body = (
                        "<html><meta charset='utf-8'><body style='font-family:Segoe UI;background:#10131a;color:#fff'>"
                        "<h2>VANTA</h2><p>Вход завершён. Можно закрыть эту вкладку и вернуться в лаунчер.</p></body></html>"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    return

            server = HTTPServer(("localhost", 0), CallbackHandler)
            server.timeout = 1
            redirect_uri = f"http://localhost:{server.server_port}"
            login_url, state, verifier = microsoft_account.get_secure_login_data(
                self.client_id, redirect_uri
            )
            webbrowser.open(login_url)

            deadline = time.monotonic() + 300
            while time.monotonic() < deadline and not self.isInterruptionRequested():
                server.handle_request()
                callback_path = getattr(server, "callback_path", None)
                if callback_path:
                    full_url = redirect_uri + callback_path
                    code = microsoft_account.parse_auth_code_url(full_url, state)
                    account = microsoft_account.complete_login(
                        self.client_id, None, redirect_uri, code, verifier
                    )
                    self.done.emit(True, account)
                    return

            if self.isInterruptionRequested():
                raise RuntimeError("Вход отменён.")
            raise RuntimeError("Время ожидания входа Microsoft истекло.")
        except Exception as exc:
            self.done.emit(False, str(exc))
        finally:
            if server is not None:
                server.server_close()


class LaunchWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, game_directory, account):
        super().__init__()
        self.game_directory = Path(game_directory)
        self.account = dict(account)

    def run(self):
        try:
            profile = find_fabric_profile(self.game_directory)
            if not profile:
                raise RuntimeError("Профиль Fabric не найден. Сначала установи сборку VANTA.")
            java = find_java()
            if not java:
                raise RuntimeError("Не найдена Java 21 x64.")

            options = {
                "username": self.account["name"],
                "uuid": self.account["id"],
                "token": self.account["access_token"],
                "launcherName": "VANTA",
                "launcherVersion": APP_VERSION,
                "executablePath": java,
                "defaultExecutablePath": java,
                "gameDirectory": str(self.game_directory),
            }
            command = minecraft_launcher_lib.command.get_minecraft_command(
                profile.name, str(self.game_directory), options
            )
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            subprocess.Popen(
                command, cwd=str(self.game_directory), creationflags=flags,
                close_fds=(os.name != "nt")
            )
            self.done.emit(True, f"Minecraft запущен из профиля {profile.name}.")
        except Exception as exc:
            self.done.emit(False, str(exc))


class VantaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VANTA Launcher")
        self.resize(1180, 760)
        self.setMinimumSize(940, 640)
        self.worker = None
        self.login_worker = None
        self.launch_worker = None
        self.account_data = None
        self.buttons = {}
        self.pages = QStackedWidget()
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName("root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.setCentralWidget(root)
        self.build_sidebar(shell)
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(30, 25, 30, 24)
        ml.setSpacing(18)
        self.page_title = QLabel("Главная")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Твой игровой центр")
        self.page_subtitle.setObjectName("muted")
        head = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(self.page_title)
        left.addWidget(self.page_subtitle)
        head.addLayout(left)
        head.addStretch()
        self.status = QLabel("●  ГОТОВ К РАБОТЕ")
        self.status.setObjectName("status")
        head.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignVCenter)
        ml.addLayout(head)
        ml.addWidget(self.pages, 1)
        shell.addWidget(main, 1)
        self.make_pages()
        self.navigate("home")
        self.refresh_state()

    def build_sidebar(self, shell):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(218)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(18, 24, 18, 18)
        sl.setSpacing(10)
        brand = QHBoxLayout()
        mark = QLabel("V")
        mark.setObjectName("logo")
        mark.setFixedSize(43, 43)
        words = QVBoxLayout()
        name = QLabel("VANTA")
        name.setObjectName("brand")
        sub = QLabel("MINECRAFT CLIENT")
        sub.setObjectName("brandSub")
        words.addWidget(name)
        words.addWidget(sub)
        brand.addWidget(mark)
        brand.addLayout(words)
        brand.addStretch()
        sl.addLayout(brand)
        sl.addSpacing(28)
        menu = QLabel("БИБЛИОТЕКА")
        menu.setObjectName("sectionLabel")
        sl.addWidget(menu)
        for key, label, glyph in [
            ("home", "Главная", "⌂"), ("versions", "Версии", "▣"),
            ("mods", "Моды", "◇"), ("settings", "Настройки", "⚙")
        ]:
            b = QPushButton(f"{glyph}     {label}")
            b.setObjectName("nav")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            sl.addWidget(b)
            self.buttons[key] = b
        sl.addStretch(1)
        profile = QFrame()
        profile.setObjectName("profile")
        pl = QVBoxLayout(profile)
        pl.setContentsMargins(13, 13, 13, 13)
        row = QHBoxLayout()
        avatar = QLabel("V")
        avatar.setObjectName("avatar")
        avatar.setFixedSize(36, 36)
        details = QVBoxLayout()
        nick = QLabel("Локальный профиль")
        nick.setObjectName("profileName")
        account = QLabel("Офлайн-профиль")
        account.setObjectName("mutedSmall")
        details.addWidget(nick)
        details.addWidget(account)
        row.addWidget(avatar)
        row.addLayout(details)
        pl.addLayout(row)
        pl.addSpacing(8)
        self.account_label = QLabel("Не выполнен вход")
        self.account_label.setObjectName("mutedSmall")
        pl.addWidget(self.account_label)
        self.login_button = QPushButton("Войти через Microsoft")
        self.login_button.setObjectName("secondary")
        self.login_button.clicked.connect(self.start_login)
        pl.addWidget(self.login_button)
        sl.addWidget(profile)
        version = QLabel(f"VANTA {APP_VERSION}   /   {MC_VERSION}")
        version.setObjectName("mutedSmall")
        sl.addWidget(version)
        shell.addWidget(side)

    def make_pages(self):
        self.home = QWidget()
        self.versions = QWidget()
        self.mods = QWidget()
        self.settings = QWidget()
        for page in (self.home, self.versions, self.mods, self.settings):
            self.pages.addWidget(page)
        self.build_home()
        self.build_versions()
        self.build_mods()
        self.build_settings()

    def panel(self, title=None, subtitle=None):
        frame = QFrame()
        frame.setObjectName("panel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            lay.addWidget(s)
        return frame, lay

    def build_home(self):
        layout = QVBoxLayout(self.home)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        hero = Hero()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(28, 22, 28, 22)
        hl.setSpacing(8)
        self.install_badge = QLabel("●  ПРОВЕРКА УСТАНОВКИ")
        self.install_badge.setObjectName("pill")
        self.install_badge.setMaximumWidth(210)
        hl.addWidget(self.install_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        title = QLabel("VANTA")
        title.setObjectName("heroTitle")
        hl.addWidget(title)
        self.hero_info = QLabel(f"Minecraft Java Edition   •   {MC_VERSION}   •   Fabric")
        self.hero_info.setObjectName("heroSub")
        hl.addWidget(self.hero_info)
        tagline = QLabel("Твоя сборка. Твои правила.")
        tagline.setObjectName("muted")
        hl.addWidget(tagline)
        hl.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        update = QPushButton("↻   Обновить сборку")
        update.setObjectName("secondary")
        update.clicked.connect(self.start_install)
        play = QPushButton("▶   Играть")
        play.setObjectName("primary")
        play.clicked.connect(self.play)
        actions.addWidget(update)
        actions.addWidget(play)
        hl.addLayout(actions)
        layout.addWidget(hero)
        grid = QGridLayout()
        grid.setSpacing(14)
        news, nl = self.panel("Что нового", f"VANTA {APP_VERSION}")
        news_text = QLabel("•  Новый интерфейс на Qt\\n\\n•  Компактная навигация и игровые карточки\\n\\n•  Управление модами и установкой из лаунчера")
        news_text.setObjectName("bodyText")
        news_text.setWordWrap(True)
        nl.addWidget(news_text)
        mods, modl = self.panel("Моды", "Компоненты сборки")
        self.home_mods = QLabel()
        self.home_mods.setObjectName("bodyText")
        modl.addWidget(self.home_mods)
        allmods = QPushButton("Все моды  →")
        allmods.setObjectName("linkButton")
        allmods.clicked.connect(lambda: self.navigate("mods"))
        modl.addWidget(allmods, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(news, 0, 0, 1, 3)
        grid.addWidget(mods, 0, 3, 1, 2)
        layout.addLayout(grid, 1)

    def build_versions(self):
        layout = QVBoxLayout(self.versions)
        layout.setContentsMargins(0, 0, 0, 0)
        card, cl = self.panel("Minecraft Java Edition", "Управление игровой версией")
        version = QLabel(MC_VERSION)
        version.setObjectName("versionNumber")
        cl.addWidget(version)
        cl.addWidget(QLabel("Загрузчик: Fabric"))
        self.version_status = QLabel()
        self.version_status.setObjectName("bodyText")
        cl.addWidget(self.version_status)
        install = QPushButton("Установить / восстановить сборку")
        install.setObjectName("primary")
        install.clicked.connect(self.start_install)
        cl.addWidget(install, alignment=Qt.AlignmentFlag.AlignLeft)
        folder = QPushButton("Открыть папку .minecraft")
        folder.setObjectName("secondary")
        folder.clicked.connect(lambda: open_path(MC_DIR))
        cl.addWidget(folder, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)
        layout.addStretch()

    def build_mods(self):
        layout = QVBoxLayout(self.mods)
        layout.setContentsMargins(0, 0, 0, 0)
        card, cl = self.panel("Установленные моды", "Переключатели меняют расширение .jar на .jar.disabled")
        self.mod_list = QVBoxLayout()
        self.mod_list.setSpacing(8)
        cl.addLayout(self.mod_list)
        row = QHBoxLayout()
        refresh = QPushButton("Обновить список")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh_mods)
        openmods = QPushButton("Открыть папку mods")
        openmods.setObjectName("secondary")
        openmods.clicked.connect(lambda: open_path(MODS_DIR))
        row.addWidget(refresh)
        row.addWidget(openmods)
        row.addStretch()
        cl.addLayout(row)
        layout.addWidget(card)
        layout.addStretch()

    def build_settings(self):
        layout = QVBoxLayout(self.settings)
        layout.setContentsMargins(0, 0, 0, 0)
        syscard, sl = self.panel("Система", "Диагностика окружения")
        self.java_label = QLabel()
        self.java_label.setObjectName("bodyText")
        self.fabric_label = QLabel()
        self.fabric_label.setObjectName("bodyText")
        sl.addWidget(self.java_label)
        sl.addWidget(self.fabric_label)
        check = QPushButton("Проверить систему")
        check.setObjectName("secondary")
        check.clicked.connect(self.diagnostics)
        sl.addWidget(check, alignment=Qt.AlignmentFlag.AlignLeft)
        pathcard, pl = self.panel("Папка установки Minecraft", "Выбери отдельную папку для файлов игры, версий, библиотек и модов VANTA.")
        self.game_dir_label = QLabel(str(MC_DIR))
        self.game_dir_label.setObjectName("bodyText")
        self.game_dir_label.setWordWrap(True)
        pl.addWidget(self.game_dir_label)
        choose_row = QHBoxLayout()
        choose = QPushButton("Выбрать папку…")
        choose.setObjectName("primary")
        choose.clicked.connect(self.choose_game_directory)
        open_game = QPushButton("Открыть папку")
        open_game.setObjectName("secondary")
        open_game.clicked.connect(lambda: open_path(MC_DIR))
        choose_row.addWidget(choose)
        choose_row.addWidget(open_game)
        choose_row.addStretch()
        pl.addLayout(choose_row)

        authcard, al = self.panel("Microsoft", "Для запуска нужен Microsoft Client ID приложения VANTA. Client ID — публичный идентификатор, пароль от аккаунта лаунчер не запрашивает.")
        self.client_id_label = QLabel("Client ID: " + (SETTINGS.get("microsoft_client_id") or "не задан"))
        self.client_id_label.setObjectName("muted")
        self.client_id_label.setWordWrap(True)
        al.addWidget(self.client_id_label)
        auth_actions = QHBoxLayout()
        set_client = QPushButton("Настроить Client ID")
        set_client.setObjectName("secondary")
        set_client.clicked.connect(self.configure_client_id)
        sign_in = QPushButton("Войти через Microsoft")
        sign_in.setObjectName("primary")
        sign_in.clicked.connect(self.start_login)
        auth_actions.addWidget(set_client)
        auth_actions.addWidget(sign_in)
        auth_actions.addStretch()
        al.addLayout(auth_actions)

        layout.addWidget(syscard)
        layout.addWidget(pathcard)
        layout.addWidget(authcard)
        layout.addStretch()

    def navigate(self, key):
        mapping = {"home": (0, "Главная", "Твой игровой центр"),
                   "versions": (1, "Версии", "Управление установленной игрой"),
                   "mods": (2, "Моды", "Компоненты сборки VANTA"),
                   "settings": (3, "Настройки", "Java, папка игры и диагностика")}
        index, title, subtitle = mapping[key]
        self.pages.setCurrentIndex(index)
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        for name, button in self.buttons.items():
            button.setProperty("active", name == key)
            button.style().unpolish(button)
            button.style().polish(button)
        if key == "mods":
            self.refresh_mods()
        self.refresh_state()

    def refresh_state(self):
        profile = find_fabric_profile()
        self.install_badge.setText("●  ИГРА УСТАНОВЛЕНА" if profile else "●  ОЖИДАЕТ УСТАНОВКИ")
        self.version_status.setText(f"Fabric: {profile.name}" if profile else "Профиль Fabric не найден. Установи сборку.")
        self.java_label.setText(f"Java: {find_java() or 'не найдена'}")
        self.fabric_label.setText(f"Fabric: {profile.name if profile else 'не установлен'}")
        installed = [p for p in mod_files() if p.suffix == ".jar"]
        self.home_mods.setText("\\n".join([f"•  {p.name}" for p in installed[:4]]) or "Пока нет установленных модов.")
        if hasattr(self, "game_dir_label"):
            self.game_dir_label.setText(str(MC_DIR))
        if hasattr(self, "client_id_label"):
            self.client_id_label.setText("Client ID: " + (SETTINGS.get("microsoft_client_id") or "не задан"))
        if hasattr(self, "account_label"):
            self.account_label.setText(self.account_data.get("name") if self.account_data else "Не выполнен вход")
        if hasattr(self, "login_button"):
            self.login_button.setText("Выйти" if self.account_data else "Войти через Microsoft")
    
    def refresh_mods(self):
        while self.mod_list.count():
            item = self.mod_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        files = mod_files()
        if not files:
            empty = QLabel("Папка mods пока пуста. Установи базовую сборку VANTA.")
            empty.setObjectName("muted")
            self.mod_list.addWidget(empty)
        for path in files:
            row = QFrame()
            row.setObjectName("modRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 9, 12, 9)
            name = QLabel(path.name.replace(".jar.disabled", ""))
            name.setObjectName("bodyText")
            enabled = path.suffix == ".jar"
            state = QLabel("ВКЛЮЧЁН" if enabled else "ВЫКЛЮЧЕН")
            state.setObjectName("status")
            toggle = QCheckBox("Включён")
            toggle.setChecked(enabled)
            toggle.stateChanged.connect(lambda state, p=path: self.toggle_mod(p, bool(state)))
            rl.addWidget(name, 1)
            rl.addWidget(state)
            rl.addWidget(toggle)
            self.mod_list.addWidget(row)

    def toggle_mod(self, path, enabled):
        try:
            if enabled and path.name.endswith(".jar.disabled"):
                path.rename(path.with_name(path.name[:-9]))
            elif not enabled and path.suffix == ".jar":
                path.rename(path.with_name(path.name + ".disabled"))
            self.refresh_mods()
            self.refresh_state()
        except Exception as e:
            QMessageBox.critical(self, "VANTA", f"Не удалось переключить мод:\\n{e}")
            self.refresh_mods()

    def start_install(self):
        if self.worker and self.worker.isRunning():
            return
        self.status.setText("●  УСТАНОВКА…")
        self.worker = InstallWorker(MC_DIR)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(lambda text: self.statusBar().showMessage(text, 8000))
        self.worker.done.connect(self.on_install_done)
        self.worker.start()
        self.statusBar().showMessage("Подготовка установки…")

    def on_progress(self, value, text):
        self.statusBar().showMessage(f"{value}% — {text}")

    def on_install_done(self, success, message):
        self.status.setText("●  ГОТОВ К РАБОТЕ" if success else "●  ОШИБКА УСТАНОВКИ")
        self.refresh_state()
        QMessageBox.information(self, "VANTA", message) if success else QMessageBox.critical(self, "Ошибка установки", message)

    def choose_game_directory(self):
        global MC_DIR, MODS_DIR
        selected = QFileDialog.getExistingDirectory(
            self, "Выбери папку установки Minecraft", str(MC_DIR)
        )
        if not selected:
            return
        MC_DIR = Path(selected).expanduser().resolve()
        MODS_DIR = MC_DIR / "mods"
        try:
            save_settings()
        except OSError as exc:
            QMessageBox.critical(self, "VANTA", str(exc))
            return
        self.refresh_state()
        self.statusBar().showMessage(f"Папка игры: {MC_DIR}", 8000)

    def configure_client_id(self):
        current = SETTINGS.get("microsoft_client_id", "")
        value, accepted = QInputDialog.getText(
            self, "Microsoft App Client ID",
            "Вставь Application (client) ID своего приложения Microsoft:",
            text=current
        )
        if not accepted:
            return
        value = value.strip()
        if not value:
            QMessageBox.warning(self, "VANTA", "Client ID не может быть пустым.")
            return
        SETTINGS["microsoft_client_id"] = value
        try:
            save_settings()
        except OSError as exc:
            QMessageBox.critical(self, "VANTA", str(exc))
            return
        self.refresh_state()
        QMessageBox.information(
            self, "VANTA",
            "Client ID сохранён. В Azure для приложения добавь Desktop / Mobile redirect URI http://localhost. "
            "Для доступа к Minecraft Services приложению также требуется соответствующее разрешение Microsoft."
        )

    def start_login(self):
        if self.account_data:
            self.account_data = None
            self.refresh_state()
            self.status.setText("●  ВЫХОД ВЫПОЛНЕН")
            return
        client_id = SETTINGS.get("microsoft_client_id", "").strip()
        if not client_id:
            QMessageBox.information(
                self, "Вход Microsoft",
                "Сначала укажи Client ID приложения Microsoft в разделе Настройки. Это публичный ID, не пароль."
            )
            self.navigate("settings")
            return
        if self.login_worker and self.login_worker.isRunning():
            return
        self.login_button.setEnabled(False)
        self.status.setText("●  ОЖИДАНИЕ MICROSOFT…")
        self.login_worker = LoginWorker(client_id)
        self.login_worker.done.connect(self.on_login_done)
        self.login_worker.start()

    def on_login_done(self, success, result):
        self.login_button.setEnabled(True)
        if success:
            self.account_data = result
            self.refresh_state()
            self.status.setText("●  MICROSOFT ПОДКЛЮЧЁН")
            QMessageBox.information(
                self, "VANTA",
                f"Вход выполнен: {result.get('name', 'Minecraft Player')}\\n"
                "Теперь можно запускать Fabric из VANTA."
            )
        else:
            self.status.setText("●  ВХОД НЕ ВЫПОЛНЕН")
            QMessageBox.critical(self, "Ошибка входа Microsoft", str(result))

    def play(self):
        profile = find_fabric_profile()
        if not profile:
            answer = QMessageBox.question(
                self, "Сборка не установлена",
                "Minecraft и профиль Fabric не найдены в выбранной папке. Установить сборку VANTA?"
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.navigate("versions")
                self.start_install()
            return
        if not self.account_data:
            answer = QMessageBox.question(
                self, "Требуется вход Microsoft",
                "Для настоящего запуска Minecraft нужен Microsoft-аккаунт с Minecraft: Java Edition. Выполнить вход?"
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.start_login()
            return
        if self.launch_worker and self.launch_worker.isRunning():
            return
        self.status.setText("●  ЗАПУСК MINECRAFT…")
        self.launch_worker = LaunchWorker(MC_DIR, self.account_data)
        self.launch_worker.done.connect(self.on_launch_done)
        self.launch_worker.start()

    def on_launch_done(self, success, message):
        self.status.setText("●  ИГРА ЗАПУЩЕНА" if success else "●  ОШИБКА ЗАПУСКА")
        if success:
            self.statusBar().showMessage(message, 10000)
        else:
            QMessageBox.critical(self, "VANTA — ошибка запуска", message)

    def diagnostics(self):
        java = find_java()
        profile = find_fabric_profile()
        QMessageBox.information(self, "Диагностика",
            f"Java: {java or 'не найдена'}\\nFabric: {profile.name if profile else 'не установлен'}")

STYLE = """
QMainWindow, QWidget#root { background: #0b0d12; color: #f3f4f8; font-family: 'Segoe UI'; font-size: 10pt; }
QFrame#sidebar { background: #10131a; border-right: 1px solid #252a35; }
QLabel { color: #f3f4f8; }
QLabel#logo { background: #8d83ff; color: white; font-size: 25pt; font-weight: 800; qproperty-alignment: AlignCenter; border-radius: 12px; }
QLabel#brand { font-size: 20pt; font-weight: 800; letter-spacing: 1px; }
QLabel#brandSub, QLabel#sectionLabel { color: #8d83ff; font-size: 8pt; font-weight: 700; }
QLabel#sectionLabel { color: #727b8c; }
QLabel#pageTitle { font-size: 23pt; font-weight: 750; }
QLabel#muted, QLabel#mutedSmall { color: #9299a8; }
QLabel#mutedSmall { font-size: 8pt; }
QLabel#status { color: #56d6a3; font-size: 8pt; font-weight: 700; }
QLabel#profileName { font-weight: 700; }
QLabel#avatar { background: #292b49; border: 1px solid #8d83ff; border-radius: 18px; color: #c7c1ff; font-size: 15pt; font-weight: 800; qproperty-alignment: AlignCenter; }
QFrame#profile, QFrame#panel { background: #151922; border: 1px solid #292f3c; border-radius: 15px; }
QFrame#hero { border: 1px solid #34364e; border-radius: 18px; }
QLabel#pill { background: #203c38; color: #56d6a3; border-radius: 8px; padding: 7px 10px; font-size: 8pt; font-weight: 700; }
QLabel#heroTitle { font-size: 36pt; font-weight: 850; }
QLabel#heroSub { color: #c4c9d8; font-size: 11pt; }
QLabel#cardTitle { font-size: 14pt; font-weight: 750; }
QLabel#bodyText { color: #c3c8d4; font-size: 10pt; }
QLabel#versionNumber { font-size: 28pt; font-weight: 800; }
QPushButton { border: 0; border-radius: 9px; padding: 11px 16px; font-weight: 700; }
QPushButton#nav { background: transparent; color: #9299a8; text-align: left; padding: 13px 12px; }
QPushButton#nav:hover, QPushButton#nav[active="true"] { background: #20283a; color: #f3f4f8; }
QPushButton#primary { background: #8d83ff; color: #11131b; padding: 14px 24px; }
QPushButton#primary:hover { background: #a39aff; }
QPushButton#secondary { background: #242b3a; color: #e8eaf1; }
QPushButton#secondary:hover { background: #30394d; }
QPushButton#linkButton { background: transparent; color: #aaa3ff; padding-left: 0; }
QFrame#modRow { background: #1b202b; border: 1px solid #2b3240; border-radius: 9px; }
QCheckBox { color: #c9ced9; spacing: 8px; }
QCheckBox::indicator { width: 38px; height: 21px; border-radius: 10px; background: #343b4a; }
QCheckBox::indicator:checked { background: #8d83ff; }
QProgressBar { background: #242b3a; border: 0; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #8d83ff; border-radius: 4px; }
QStatusBar { background: #0b0d12; color: #9299a8; }
"""

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VANTA Launcher")
    window = VantaWindow()

    if "--self-test" in sys.argv:
        # Create and render the actual Qt window, then exit automatically for CI.
        window.resize(1100, 700)
        window.show()
        app.processEvents()
        QTimer.singleShot(1200, app.quit)
        sys.exit(app.exec())

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
