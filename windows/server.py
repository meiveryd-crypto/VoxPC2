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
import time
from urllib.parse import parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import actions
import netinfo
import relay
from mcp_server import McpHandler
from config import DISCOVERY_PORT, VERSION

DISCOVER_MAGIC = b"VOXPC_DISCOVER"


class ApiServer:
    def __init__(self, config, processor, on_event=None, command_handler=None, on_show=None, on_quit=None):
        self.config = config
        self.processor = processor
        self.on_event = on_event or (lambda *a: None)
        self.command_handler = command_handler or processor.execute
        self.on_show = on_show or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self.mcp = McpHandler(config, processor, self.on_event)
        self.httpd = None
        self._fails = {}          # ip -> [время неудачных попыток]
        self._fails_lock = threading.Lock()
        self._stop = threading.Event()

    def blocked(self, ip):
        now = time.time()
        with self._fails_lock:
            fails = [t for t in self._fails.get(ip, []) if now - t < 300]
            self._fails[ip] = fails
            return len(fails) >= 10

    def failed(self, ip):
        with self._fails_lock:
            self._fails.setdefault(ip, []).append(time.time())

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

            def _client_ip(self):
                return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

            def _is_auth(self):
                ip = self._client_ip()
                if api.blocked(ip):
                    return False
                ok = api._authorized(self.headers.get("X-Token", ""))
                if not ok and self.headers.get("X-Token"):
                    api.failed(ip)
                return ok

            def _path(self):
                return self.path.split("?", 1)[0].rstrip("/")

            def _via_tunnel(self):
                return bool(self.headers.get("Cf-Ray") or self.headers.get("Cf-Connecting-Ip"))

            def _mcp_ok(self, path):
                secret = str(api.config.get("mcp_secret") or "")
                given = path[len("/mcp/"):] if path.startswith("/mcp/") else ""
                return bool(secret) and hmac.compare_digest(given, secret)

            def _guard(self, path):
                """Через интернет-туннель доступен только коннектор Claude."""
                if path.startswith("/mcp/"):
                    if not self._mcp_ok(path):
                        self._send(404, {"error": "not found"})
                        return False
                    return True
                if self._via_tunnel() and not (path.startswith("/api/") and api.config.get("remote_api")):
                    self._send(403, {"ok": False, "message": "Forbidden"})
                    return False
                return True

            def do_GET(self):
                path = self._path()
                if not self._guard(path):
                    return
                if path in ("/local/show", "/local/quit"):
                    if self.client_address[0] == "127.0.0.1" and not self._via_tunnel():
                        (api.on_show if path == "/local/show" else api.on_quit)()
                        return self._send(200, {"ok": True})
                    return self._send(403, {"ok": False})
                if path.startswith("/mcp/"):
                    self.send_response(405)
                    self.send_header("Allow", "POST")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if path == "/api/ping":
                    return self._send(200, {"name": netinfo.hostname(), "version": VERSION,
                                            "auth": self._is_auth()})
                if not self._is_auth():
                    return self._send(401, {"ok": False, "message": "Неверный код доступа"})
                if path == "/api/screen":
                    q = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
                    side = max(320, min(2560, int((q.get("max") or ["1280"])[0])))
                    quality = max(20, min(90, int((q.get("q") or ["60"])[0])))
                    try:
                        data = actions.screenshot_jpeg(side, quality)
                    except Exception as e:
                        return self._send(500, {"ok": False, "message": f"Не удалось снять экран: {e}"})
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if path == "/api/apps":
                    return self._send(200, [{"name": a.get("name", ""), "icon": a.get("icon", "🧩")}
                                            for a in api.config.apps])
                self._send(404, {"ok": False, "message": "Not found"})

            def _mcp_post(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    msg = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return self._send(400, {"jsonrpc": "2.0", "id": None,
                                            "error": {"code": -32700, "message": "Parse error"}})
                if isinstance(msg, list):
                    replies = [r for r in (api.mcp.handle(m) for m in msg) if r is not None]
                else:
                    r = api.mcp.handle(msg)
                    replies = r
                if not replies:
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._send(200, replies)

            def do_DELETE(self):
                path = self._path()
                if self._guard(path):
                    self.send_response(405)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def do_POST(self):
                path = self._path()
                if not self._guard(path):
                    return
                if path.startswith("/mcp/"):
                    return self._mcp_post()
                if not self._is_auth():
                    return self._send(401, {"ok": False, "message": "Неверный код доступа"})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    data = json.loads(self.rfile.read(length) or b"{}") if length else {}
                except (ValueError, json.JSONDecodeError):
                    return self._send(400, {"ok": False, "message": "Некорректный запрос"})
                try:
                    if path == "/api/command":
                        text = str(data.get("text", ""))
                        res = api.command_handler(text)
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
                         "mac": netinfo.mac_address(), "version": VERSION,
                         "remote_id": relay.remote_id(self.config)}
                try:
                    sock.sendto(json.dumps(reply, ensure_ascii=False).encode("utf-8"), addr)
                except OSError:
                    pass
        sock.close()
