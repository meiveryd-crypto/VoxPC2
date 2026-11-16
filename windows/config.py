"""Настройки VoxPC: хранятся в %APPDATA%\\VoxPC\\config.json"""
import copy
import json
import os
import secrets
import sys
import threading
from pathlib import Path

APP_NAME = "VoxPC"
VERSION = "1.0.0"
HTTP_PORT = 47800
DISCOVERY_PORT = 47801


def data_dir() -> Path:
    base = Path(os.getenv("APPDATA") or Path.home()) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def resource_path(name: str) -> str:
    """Путь к файлу рядом с программой (работает и в собранном .exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


CONFIG_PATH = data_dir() / "config.json"

# path может быть: путём к .exe, командой, URL или URI-схемой (steam://, discord://)
DEFAULT_APPS = [
    {"name": "Steam", "icon": "🎮", "aliases": ["стим", "steam", "стима"],
     "path": "steam://open/main", "process": "steam.exe"},
    {"name": "Discord", "icon": "💬", "aliases": ["дискорд", "discord", "дис"],
     "path": "discord://", "process": "Discord.exe"},
    {"name": "Telegram", "icon": "✈️", "aliases": ["телеграм", "телеграмм", "телега", "telegram"],
     "path": "tg://", "process": "Telegram.exe"},
    {"name": "Браузер", "icon": "🌐", "aliases": ["браузер", "хром", "chrome", "интернет"],
     "path": "https://www.google.com", "process": "chrome.exe"},
    {"name": "YouTube", "icon": "▶️", "aliases": ["ютуб", "youtube", "ютюб"],
     "path": "https://www.youtube.com", "process": ""},
    {"name": "Spotify", "icon": "🎵", "aliases": ["спотифай", "spotify", "музыку"],
     "path": "spotify:", "process": "Spotify.exe"},
    {"name": "Counter-Strike 2", "icon": "🔫", "aliases": ["кс", "контру", "контр страйк", "cs", "кс2"],
     "path": "steam://rungameid/730", "process": "cs2.exe"},
    {"name": "Проводник", "icon": "📁", "aliases": ["проводник", "папки", "мой компьютер"],
     "path": "explorer.exe", "process": ""},
    {"name": "Диспетчер задач", "icon": "📊", "aliases": ["диспетчер задач", "диспетчер"],
     "path": "taskmgr.exe", "process": "Taskmgr.exe"},
    {"name": "Блокнот", "icon": "📝", "aliases": ["блокнот", "notepad"],
     "path": "notepad.exe", "process": "notepad.exe"},
    {"name": "Калькулятор", "icon": "🧮", "aliases": ["калькулятор"],
     "path": "calc.exe", "process": "CalculatorApp.exe"},
    {"name": "Настройки Windows", "icon": "⚙️", "aliases": ["настройки", "параметры"],
     "path": "ms-settings:", "process": ""},
]

DEFAULTS = {
    "port": HTTP_PORT,
    "token": "",
    "wake_word": "компьютер",
    "tts": True,
    "always_listen": False,
    "start_minimized": False,
    "apps": DEFAULT_APPS,
}

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_token() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Config:
    def __init__(self):
        self._lock = threading.RLock()
        self.data = {}
        self.load()

    def load(self):
        data = {}
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        for key, value in DEFAULTS.items():
            data.setdefault(key, copy.deepcopy(value))
        if not data.get("token"):
            data["token"] = new_token()
        self.data = data
        self.save()

    def save(self):
        with self._lock:
            tmp = CONFIG_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CONFIG_PATH)

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.data[key] = value
            self.save()

    @property
    def apps(self):
        with self._lock:
            return list(self.data.get("apps", []))

    def set_apps(self, apps):
        self.set("apps", apps)

    def regenerate_token(self) -> str:
        token = new_token()
        self.set("token", token)
        return token
