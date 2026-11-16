"""«Мозг» VoxPC: команды пользователя уходят в Claude (через Claude Code по подписке),
Claude решает, что сделать, и выполняет это инструментами VoxPC (MCP), затем отвечает.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from actions import CREATE_NO_WINDOW
from config import data_dir

MODELS = {"haiku": "Быстрый (Haiku)", "sonnet": "Умный (Sonnet)", "opus": "Максимум (Opus)"}
SESSION_TTL = 300  # сек: в течение 5 минут Claude помнит контекст разговора

SYSTEM_PROMPT = (
    "Ты — голосовой помощник VoxPC на Windows-компьютере пользователя. Фразы пользователя распознаны "
    "из речи автоматически и могут содержать ошибки распознавания — угадывай смысл. Выполняй просьбы "
    "с помощью инструментов voxpc (открыть/закрыть программу, звук, музыка, питание, сайты, поиск, "
    "скриншот). Можно выполнять несколько действий подряд. Если нужно ответить на вопрос, просто ответь. "
    "Отвечай по-русски одной-двумя короткими фразами, без markdown, списков и эмодзи — ответ будет "
    "озвучен. Если пользователь прямо просит выключить, перезагрузить или усыпить компьютер, это и есть "
    "его согласие: передавай confirmed=true. Если просьба неоднозначна и действие необратимо — переспроси."
)

DENY_TOOLS = "Bash,PowerShell,Edit,Write,MultiEdit,NotebookEdit,Read,Glob,Grep,WebFetch,Task,Agent"


def find_claude():
    for name in ("claude", "claude.exe", "claude.cmd"):
        exe = shutil.which(name)
        if exe:
            return exe
    home = Path.home()
    for c in (home / ".local" / "bin" / "claude.exe",
              Path(os.getenv("APPDATA") or "") / "npm" / "claude.cmd",
              Path(os.getenv("LOCALAPPDATA") or "") / "Programs" / "claude" / "claude.exe"):
        if c.is_file():
            return str(c)
    return None


def install_claude_code():
    subprocess.Popen('start "Установка Claude Code" powershell -NoExit -ExecutionPolicy Bypass '
                     '-Command "irm https://claude.ai/install.ps1 | iex"', shell=True)


def login_claude_code():
    exe = find_claude()
    if not exe:
        raise FileNotFoundError("Claude Code не установлен")
    workdir = data_dir() / "brain"
    workdir.mkdir(exist_ok=True)
    subprocess.Popen(f'start "Вход в Claude Code" /D "{workdir}" cmd /k ""{exe}""', shell=True)


class ClaudeBrain:
    def __init__(self, config):
        self.config = config
        self.session_id = None
        self.last_used = 0.0
        self._lock = threading.Lock()

    @property
    def installed(self) -> bool:
        return find_claude() is not None

    def reset(self):
        self.session_id = None

    def _write_mcp_config(self, workdir: Path) -> Path:
        path = workdir / "mcp.json"
        url = f"http://127.0.0.1:{self.config.get('port')}/mcp/{self.config.get('mcp_secret')}"
        path.write_text(json.dumps({"mcpServers": {"voxpc": {"type": "http", "url": url}}}), encoding="utf-8")
        return path

    def ask(self, text: str) -> dict:
        exe = find_claude()
        if not exe:
            return {"ok": False, "message": "Claude Code не установлен. Откройте Настройки → «Мозг: Claude»."}
        with self._lock:
            workdir = data_dir() / "brain"
            workdir.mkdir(exist_ok=True)
            mcp = self._write_mcp_config(workdir)
            args = [exe, "-p", "--output-format", "json",
                    "--model", self.config.get("brain_model") or "haiku",
                    "--mcp-config", str(mcp), "--strict-mcp-config",
                    "--allowedTools", "mcp__voxpc",
                    "--disallowedTools", DENY_TOOLS,
                    "--append-system-prompt", SYSTEM_PROMPT]
            if self.session_id and time.time() - self.last_used < SESSION_TTL:
                args += ["--resume", self.session_id]
            env = dict(os.environ, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
            try:
                proc = subprocess.run(args, input=text, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=180, cwd=str(workdir), env=env,
                                      creationflags=CREATE_NO_WINDOW)
            except subprocess.TimeoutExpired:
                return {"ok": False, "message": "Claude не ответил вовремя"}
            except OSError as e:
                return {"ok": False, "message": f"Не удалось запустить Claude Code: {e}"}
            return self._parse(proc)

    def _parse(self, proc) -> dict:
        out = (proc.stdout or "").strip()
        data = None
        for line in reversed(out.splitlines()):
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
        if isinstance(data, list):  # на случай формата-массива
            data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), None)
        if not isinstance(data, dict):
            err = ((proc.stderr or "") + out).strip()
            low = err.lower()
            if any(k in low for k in ("login", "log in", "authenticat", "/login", "api key")):
                return {"ok": False, "message": "Войдите в Claude Code: Настройки → «Мозг: Claude» → «Войти в аккаунт»"}
            return {"ok": False, "message": "Ошибка Claude Code: " + (err[-300:] or f"код {proc.returncode}")}
        if data.get("session_id"):
            self.session_id = data["session_id"]
            self.last_used = time.time()
        result = str(data.get("result") or "").strip()
        if data.get("is_error"):
            self.session_id = None
            low = result.lower()
            if "login" in low or "auth" in low:
                return {"ok": False, "message": "Войдите в Claude Code: Настройки → «Мозг: Claude» → «Войти в аккаунт»"}
            return {"ok": False, "message": result or "Claude вернул ошибку"}
        return {"ok": True, "message": result or "Готово"}
