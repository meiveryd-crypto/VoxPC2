"""MCP-сервер VoxPC: инструменты, через которые Claude управляет компьютером.

Транспорт — Streamable HTTP (POST JSON-RPC, ответ application/json) по адресу /mcp/<секрет>.
Для Claude Desktop есть stdio-мост voxpc_mcp.py, который пересылает сообщения сюда.
"""
import base64
import datetime

import actions
import netinfo
import programs
from config import APP_NAME, VERSION

PROTOCOLS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = (
    "VoxPC управляет Windows-компьютером пользователя: запускает и закрывает программы и игры, "
    "управляет звуком, музыкой, питанием, открывает сайты и делает скриншоты. "
    "Если программы нет в list_apps, используй open_app — он сам ищет её в меню «Пуск», "
    "или find_programs. Выключение, перезагрузку, сон и гибернацию выполняй только после явного "
    "согласия пользователя в этом разговоре и передавай confirmed=true. Отвечай на языке пользователя."
)

POWER_CONFIRM = {"shutdown", "restart", "sleep", "hibernate"}


def _tool(name, title, desc, props=None, required=None, read_only=False, destructive=False):
    return {
        "name": name,
        "title": title,
        "description": desc,
        "inputSchema": {"type": "object", "properties": props or {}, "required": required or []},
        "annotations": {"title": title, "readOnlyHint": read_only, "destructiveHint": destructive,
                        "openWorldHint": False},
    }


TOOLS = [
    _tool("get_status", "Состояние ПК", "Имя компьютера, время, IP и список настроенных приложений.",
          read_only=True),
    _tool("list_apps", "Список приложений",
          "Приложения и игры, настроенные в VoxPC, с голосовыми названиями.", read_only=True),
    _tool("find_programs", "Поиск программ", "Ищет установленные программы в меню «Пуск» и на рабочем столе.",
          {"query": {"type": "string", "description": "Название программы, например «photoshop» или «obs»"}},
          ["query"], read_only=True),
    _tool("open_app", "Открыть программу",
          "Запускает программу или игру по названию: сначала среди приложений VoxPC, затем в меню «Пуск».",
          {"name": {"type": "string", "description": "Название, например Steam, Discord, «кс», Photoshop"}},
          ["name"]),
    _tool("close_app", "Закрыть программу", "Закрывает программу по названию или имени процесса.",
          {"name": {"type": "string"}}, ["name"], destructive=True),
    _tool("list_open_windows", "Открытые окна", "Список открытых окон: процесс и заголовок.", read_only=True),
    _tool("volume", "Громкость", "Меняет громкость системы.",
          {"action": {"type": "string", "enum": ["up", "down", "mute", "set"]},
           "level": {"type": "integer", "minimum": 0, "maximum": 100,
                     "description": "Громкость в процентах для action=set"}}, ["action"]),
    _tool("media", "Медиа", "Управление воспроизведением музыки и видео.",
          {"action": {"type": "string", "enum": ["play_pause", "next", "prev"]}}, ["action"]),
    _tool("power", "Питание",
          "Блокировка, сон, гибернация, перезагрузка, выключение или отмена выключения. "
          "Для shutdown/restart/sleep/hibernate нужен confirmed=true после явного согласия пользователя.",
          {"action": {"type": "string", "enum": ["lock", "sleep", "hibernate", "restart", "shutdown", "cancel"]},
           "confirmed": {"type": "boolean", "description": "Пользователь явно подтвердил действие"}},
          ["action"], destructive=True),
    _tool("open_url", "Открыть сайт", "Открывает адрес в браузере по умолчанию.",
          {"url": {"type": "string"}}, ["url"]),
    _tool("search", "Поиск в интернете", "Открывает поиск Google или YouTube в браузере на ПК.",
          {"query": {"type": "string"}, "site": {"type": "string", "enum": ["google", "youtube"]}}, ["query"]),
    _tool("show_desktop", "Свернуть все окна", "Сворачивает все окна (Win+D)."),
    _tool("screenshot", "Скриншот экрана", "Делает снимок экрана ПК, чтобы увидеть, что на нём происходит.",
          read_only=True),
    _tool("add_app", "Добавить приложение в VoxPC",
          "Сохраняет программу в список VoxPC, чтобы её можно было открывать голосом.",
          {"name": {"type": "string"},
           "path": {"type": "string", "description": "Путь к .exe/.lnk, URL или steam://rungameid/ID"},
           "aliases": {"type": "array", "items": {"type": "string"}, "description": "Голосовые названия"},
           "process": {"type": "string", "description": "Имя процесса для закрытия, например obs64.exe"},
           "icon": {"type": "string", "description": "Эмодзи"}},
          ["name", "path"]),
    _tool("voice_command", "Голосовая команда VoxPC",
          "Выполняет фразу так же, как если бы её сказали в микрофон VoxPC (например «громкость 30»).",
          {"text": {"type": "string"}}, ["text"]),
]


def _rpc_error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


class McpHandler:
    def __init__(self, config, processor, on_event=None):
        self.config = config
        self.processor = processor
        self.on_event = on_event or (lambda *a: None)

    # ---------- JSON-RPC ----------
    def handle(self, msg):
        """Возвращает ответ или None (для уведомлений и ответов клиента)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "Invalid Request")
        method = msg.get("method")
        if method is None:
            return None
        mid = msg.get("id")
        notification = "id" not in msg
        params = msg.get("params") or {}
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                result = {
                    "protocolVersion": requested if requested in PROTOCOLS else PROTOCOLS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "voxpc", "title": APP_NAME, "version": VERSION},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self.call(params.get("name", ""), params.get("arguments") or {})
            elif method.startswith("notifications/"):
                return None
            else:
                return None if notification else _rpc_error(mid, -32601, f"Method not found: {method}")
        except Exception as e:
            return None if notification else _rpc_error(mid, -32603, str(e))
        return None if notification else {"jsonrpc": "2.0", "id": mid, "result": result}

    # ---------- инструменты ----------
    def call(self, name, args):
        fn = getattr(self, f"t_{name}", None)
        if fn is None or name not in {t["name"] for t in TOOLS}:
            return self._text(f"Неизвестный инструмент: {name}", False)
        try:
            out = fn(**args)
        except TypeError as e:
            return self._text(f"Неверные параметры: {e}", False)
        except Exception as e:
            out = {"ok": False, "message": f"Ошибка: {e}"}
        if isinstance(out, dict) and out.get("_image"):
            self.on_event("claude", "Скриншот экрана", {"ok": True, "message": "Снимок отправлен Claude"})
            return {"content": [{"type": "image", "data": out["_image"], "mimeType": "image/jpeg"}],
                    "isError": False}
        label = {"open_app": "Открыть", "close_app": "Закрыть"}.get(name, name)
        detail = args.get("name") or args.get("action") or args.get("query") or args.get("url") or args.get("text") or ""
        if name not in ("get_status", "list_apps", "find_programs", "list_open_windows"):
            self.on_event("claude", f"{label} {detail}".strip(), out)
        return self._text(out.get("message", ""), out.get("ok", True))

    @staticmethod
    def _text(text, ok=True):
        return {"content": [{"type": "text", "text": text}], "isError": not ok}

    @staticmethod
    def _ok(message):
        return {"ok": True, "message": message}

    @staticmethod
    def _fail(message):
        return {"ok": False, "message": message}

    def t_get_status(self):
        apps = ", ".join(a["name"] for a in self.config.apps)
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        return self._ok(f"Компьютер: {netinfo.hostname()} ({netinfo.local_ip()}), время {now}. "
                        f"VoxPC {VERSION}. Приложения: {apps}")

    def t_list_apps(self):
        lines = [f"- {a['name']} (голосом: {', '.join(a.get('aliases', [])) or '—'})" for a in self.config.apps]
        return self._ok("Приложения VoxPC:\n" + "\n".join(lines))

    def t_find_programs(self, query):
        found = programs.find(query, limit=8, min_score=0.5)
        if not found:
            return self._fail(f"Программы по запросу «{query}» не найдены")
        return self._ok("Найдено:\n" + "\n".join(f"- {p['name']} — {p['path']}" for p in found))

    def t_open_app(self, name):
        app = self.processor.find_app(name)
        if app:
            return self.processor.open_app(app)
        found = programs.find(name, limit=1)
        if found:
            return self.processor.open_program(found[0])
        return self._fail(f"Не нашёл программу «{name}». Попробуйте find_programs или add_app.")

    def t_close_app(self, name):
        app = self.processor.find_app(name)
        if app and app.get("process"):
            return self.processor.close_app(app)
        q = programs._norm(name)
        for w in actions.open_windows():
            if q and (q in programs._norm(w["process"]) or q in programs._norm(w["title"])):
                actions.kill(w["process"], force=False)
                return self._ok(f"Закрываю {w['title'] or w['process']}")
        return self._fail(f"Не нашёл открытую программу «{name}»")

    def t_list_open_windows(self):
        wins = actions.open_windows()
        if not wins:
            return self._ok("Открытых окон нет")
        return self._ok("Открытые окна:\n" + "\n".join(f"- {w['title']} ({w['process']})" for w in wins))

    def t_volume(self, action, level=None):
        if action == "set":
            if level is None:
                return self._fail("Укажите level от 0 до 100")
            actions.set_volume(int(level))
            return self._ok(f"Громкость {int(level)}%")
        return self.processor.action({"up": "vol_up", "down": "vol_down", "mute": "mute"}[action])

    def t_media(self, action):
        return self.processor.action(action)

    def t_power(self, action, confirmed=False):
        if action in POWER_CONFIRM and not confirmed:
            return self._fail("Это действие нужно подтвердить: спросите пользователя и повторите с confirmed=true")
        return self.processor.action(action)

    def t_open_url(self, url):
        actions.open_url(url)
        return self._ok(f"Открываю {url}")

    def t_search(self, query, site="google"):
        (actions.youtube_search if site == "youtube" else actions.web_search)(query)
        return self._ok(f"Ищу на {'YouTube' if site == 'youtube' else 'Google'}: {query}")

    def t_show_desktop(self):
        return self.processor.action("desktop")

    def t_screenshot(self):
        return {"_image": base64.b64encode(actions.screenshot_jpeg()).decode("ascii")}

    def t_add_app(self, name, path, aliases=None, process="", icon="🧩"):
        apps = [a for a in self.config.apps if a.get("name") != name]
        apps.append({"name": name, "icon": icon or "🧩", "aliases": aliases or [name.lower()],
                     "path": path, "process": process or ""})
        self.config.set_apps(apps)
        return self._ok(f"«{name}» добавлено в VoxPC")

    def t_voice_command(self, text):
        return self.processor.execute(text)
