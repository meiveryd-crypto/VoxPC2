"""Мост для Claude Desktop: MCP по stdio -> запущенный VoxPC (http://127.0.0.1:<порт>/mcp/<секрет>).

Claude Desktop запускает этот файл (или VoxPC-MCP.exe) сам — вручную его запускать не нужно.
Если VoxPC не запущен, мост запустит его.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path(os.getenv("APPDATA") or Path.home()) / "VoxPC" / "config.json"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost без прокси
_launched = False


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def launch_voxpc():
    global _launched
    if _launched:
        return
    _launched = True
    here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    exe = here / "VoxPC.exe"
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    try:
        if exe.is_file():
            subprocess.Popen([str(exe), "--minimized"], creationflags=flags, close_fds=True)
        elif (here / "main.py").is_file():
            py = sys.executable.replace("python.exe", "pythonw.exe")
            subprocess.Popen([py, str(here / "main.py"), "--minimized"], creationflags=flags, close_fds=True)
    except OSError:
        pass


def post(raw: bytes):
    cfg = load_config()
    url = f"http://127.0.0.1:{cfg.get('port', 47800)}/mcp/{cfg.get('mcp_secret', '')}"
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with OPENER.open(req, timeout=90) as r:
        return r.status, r.read()


def send_with_retry(raw: bytes):
    deadline = time.time() + 25
    while True:
        try:
            return post(raw)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if time.time() > deadline:
                raise
            launch_voxpc()
            time.sleep(1.5)


def write(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        try:
            status, body = send_with_retry(line.encode("utf-8"))
            if status == 202 or not body:
                continue
            write(json.loads(body.decode("utf-8")))
        except Exception as e:
            if isinstance(msg, dict) and "id" in msg and msg.get("method"):
                hint = ("VoxPC не запущен или недоступен. Запустите VoxPC на этом компьютере."
                        if not isinstance(e, urllib.error.HTTPError) else
                        f"VoxPC отклонил запрос ({e.code}). Откройте VoxPC → Настройки → Коннектор Claude "
                        "и нажмите «Подключить к Claude Desktop» ещё раз.")
                write({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": hint}})


if __name__ == "__main__":
    main()
