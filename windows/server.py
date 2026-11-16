"""HTTP API для телефона + UDP-поиск ПК в локальной сети.

GET  /api/ping              -> {name, version, auth}
GET  /api/apps              -> [{name, icon}]
POST /api/command {"text"}  -> {ok, message}
POST /api/action  {"action", "app"} -> {ok, message}
Авторизация: заголовок X-Token = код доступа из настроек.
"""
import hmac
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import netinfo
from config import DISCOVERY_PORT, VERSION

DISCOVER_MAGIC = b"VOXPC_DISCOVER"


class ApiServer:
    def __init__(self, config, processor, on_event=None):
        self.config = config
        self.processor = processor
        self.on_event = on_event or (lambda *a: None)
        self.httpd = None
        self._stop = threading.Event()

    def _authorized(self, token: str) -> bool:
        return hmac.compare_digest((token or "").strip().upper(), str(self.config.get("token")).upper())

    def _make_handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"VoxPC/{VERSION}"

            def log_message(self, *args):
                pass

            def _send(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _is_auth(self):
                return api._authorized(self.headers.get("X-Token", ""))

            def _path(self):
                return self.path.split("?", 1)[0].rstrip("/")

            def do_GET(self):
                path = self._path()
                if path == "/api/ping":
                    return self._send(200, {"name": netinfo.hostname(), "version": VERSION,
                                            "auth": self._is_auth()})
                if not self._is_auth():
                    return self._send(401, {"ok": False, "message": "Неверный код доступа"})
                if path == "/api/apps":
                    return self._send(200, [{"name": a.get("name", ""), "icon": a.get("icon", "🧩")}
                                            for a in api.config.apps])
                self._send(404, {"ok": False, "message": "Not found"})

            def do_POST(self):
                if not self._is_auth():
                    return self._send(401, {"ok": False, "message": "Неверный код доступа"})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    data = json.loads(self.rfile.read(length) or b"{}") if length else {}
                except (ValueError, json.JSONDecodeError):
                    return self._send(400, {"ok": False, "message": "Некорректный запрос"})
                path = self._path()
                try:
                    if path == "/api/command":
                        text = str(data.get("text", ""))
                        res = api.processor.execute(text)
                        api.on_event("phone", text, res)
                        return self._send(200, res)
                    if path == "/api/action":
                        name = str(data.get("action", ""))
                        res = api.processor.action(name, data.get("app"))
                        label = f"{name} {data.get('app') or ''}".strip()
                        api.on_event("phone", label, res)
                        return self._send(200, res)
                except Exception as e:  # не роняем сервер из-за ошибки в команде
                    return self._send(500, {"ok": False, "message": f"Ошибка: {e}"})
                self._send(404, {"ok": False, "message": "Not found"})

        return Handler

    def start(self):
        port = int(self.config.get("port"))
        self.httpd = ThreadingHTTPServer(("0.0.0.0", port), self._make_handler())
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._discovery_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    def _discovery_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(1.0)
        except OSError:
            return
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.strip() == DISCOVER_MAGIC:
                reply = {"name": netinfo.hostname(), "port": int(self.config.get("port")),
                         "mac": netinfo.mac_address(), "version": VERSION}
                try:
                    sock.sendto(json.dumps(reply, ensure_ascii=False).encode("utf-8"), addr)
                except OSError:
                    pass
        sock.close()
