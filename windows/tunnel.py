"""Бесплатный Cloudflare Quick Tunnel: публичный https-адрес для коннектора Claude."""
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from actions import CREATE_NO_WINDOW
from config import data_dir

URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared():
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    env = os.environ
    candidates = [
        data_dir() / "cloudflared.exe",
        Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "cloudflared" / "cloudflared.exe",
        Path(env.get("ProgramFiles", r"C:\Program Files")) / "cloudflared" / "cloudflared.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def install_cloudflared():
    """Открывает консоль с установкой cloudflared через winget."""
    subprocess.Popen('start "Установка cloudflared" cmd /k winget install -e --id Cloudflare.cloudflared '
                     '--accept-source-agreements --accept-package-agreements', shell=True)


class Tunnel:
    """on_status(state, url): state = missing | starting | running | stopped | error"""

    def __init__(self, port_fn, on_status):
        self.port_fn = port_fn
        self.on_status = on_status
        self.proc = None
        self.url = ""
        self._stopping = False

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running:
            return
        exe = find_cloudflared()
        if not exe:
            self.on_status("missing", "")
            return
        self._stopping = False
        self.url = ""
        try:
            self.proc = subprocess.Popen(
                [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port_fn()}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            self.on_status("error", str(e))
            return
        self.on_status("starting", "")
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        for line in proc.stdout:
            m = URL_RE.search(line)
            if m and not self.url:
                self.url = m.group(0)
                self.on_status("running", self.url)
        proc.wait()
        self.url = ""
        if not self._stopping:
            self.on_status("error", "Туннель остановился. Проверьте интернет и включите снова.")

    def stop(self):
        self._stopping = True
        if self.running:
            self.proc.terminate()
        self.proc = None
        self.url = ""
        self.on_status("stopped", "")
