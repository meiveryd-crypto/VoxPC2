"""Разбор голосовых/текстовых команд на русском языке."""
import datetime
import difflib
import re

import actions
import programs

OPEN_WORDS = ("открой", "открыть", "запусти", "запустить", "включи", "включить",
              "поиграем в", "поиграть в", "давай", "покажи")
CLOSE_WORDS = ("закрой", "закрыть", "заверши", "завершить", "выключи", "выключить",
               "выруби", "убей", "останови")
PC_WORDS = ("компьютер", "комп", "пк", "систему", "windows", "виндовс")


def normalize(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s%.-]", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .")


def ok(message, action=None):
    return {"ok": True, "message": message, "action": action}


def fail(message):
    return {"ok": False, "message": message, "action": None}


class CommandProcessor:
    def __init__(self, config):
        self.config = config

    # ---------- поиск приложения ----------
    def find_app(self, phrase: str):
        phrase = normalize(phrase)
        if not phrase:
            return None
        words = phrase.split()
        best, best_score = None, 0.0
        for app in self.config.apps:
            names = [normalize(app.get("name", ""))] + [normalize(a) for a in app.get("aliases", [])]
            for n in filter(None, names):
                if n == phrase or re.search(rf"(?<!\w){re.escape(n)}(?!\w)", phrase):
                    return app
                for cand in [phrase] + words:
                    score = difflib.SequenceMatcher(None, n, cand).ratio()
                    if score > best_score:
                        best, best_score = app, score
        return best if best_score >= 0.75 else None

    def app_by_name(self, name: str):
        for app in self.config.apps:
            if app.get("name") == name:
                return app
        return self.find_app(name)

    def open_app(self, app):
        try:
            actions.launch(app["path"])
            return ok(f"Открываю {app['name']}", "open_app")
        except Exception as e:
            return fail(f"Не удалось открыть {app['name']}: {e}")

    def open_program(self, prog):
        try:
            actions.launch(prog["path"])
            return ok(f"Открываю {prog['name']}", "open_app")
        except Exception as e:
            return fail(f"Не удалось открыть {prog['name']}: {e}")

    def close_app(self, app):
        if not app.get("process"):
            return fail(f"Для «{app['name']}» не указан процесс для закрытия")
        actions.kill(app["process"])
        return ok(f"Закрываю {app['name']}", "close_app")

    # ---------- кнопки с телефона ----------
    def action(self, name: str, app_name: str = None):
        simple = {
            "shutdown": (actions.shutdown, "Выключаю компьютер через 5 секунд"),
            "restart": (actions.restart, "Перезагрузка через 5 секунд"),
            "cancel": (actions.cancel_shutdown, "Выключение отменено"),
            "sleep": (actions.sleep, "Перевожу в спящий режим"),
            "hibernate": (actions.hibernate, "Гибернация"),
            "lock": (actions.lock, "Компьютер заблокирован"),
            "vol_up": (actions.volume_up, "Громче"),
            "vol_down": (actions.volume_down, "Тише"),
            "mute": (actions.mute, "Звук переключён"),
            "play_pause": (actions.play_pause, "Пауза / воспроизведение"),
            "next": (actions.next_track, "Следующий трек"),
            "prev": (actions.prev_track, "Предыдущий трек"),
            "desktop": (actions.show_desktop, "Показываю рабочий стол"),
        }
        if name in simple:
            fn, msg = simple[name]
            fn()
            return ok(msg, name)
        if name in ("open_app", "close_app"):
            app = self.app_by_name(app_name or "")
            if not app:
                return fail(f"Приложение «{app_name}» не найдено")
            return self.open_app(app) if name == "open_app" else self.close_app(app)
        return fail(f"Неизвестное действие: {name}")

    # ---------- текстовая команда ----------
    def execute(self, text: str, strict: bool = False):
        """strict=True: выполнять только короткие однозначные команды (остальное — для Claude)."""
        t = normalize(text)
        wake = normalize(self.config.get("wake_word") or "")
        if wake and t.startswith(wake):
            t = t[len(wake):].strip(" ,")
        if not t:
            return fail("Пустая команда")
        if strict and (len(t.split()) > 5 or re.search(r"\b(и|потом|затем|а также|после)\b", t)):
            return fail("Сложная команда")

        def has(*ws):
            return any(w in t for w in ws)

        about_pc = has(*PC_WORDS)

        # питание
        if has("отмени выключение", "отмена выключения", "отменить выключение", "не выключай"):
            return self.action("cancel")
        if has("перезагрузи", "перезагрузка", "перезагрузить", "ребут"):
            actions.restart()
            return ok("Перезагрузка через 5 секунд. Скажите «отмени выключение» для отмены", "restart")
        if (has("выключи", "выключить", "выключение", "отключи", "заверши работу") and about_pc) \
                or t in ("выключи", "выключись", "выключайся", "выключение"):
            actions.shutdown()
            return ok("Выключаю компьютер через 5 секунд. Скажите «отмени выключение» для отмены", "shutdown")
        if has("гибернац"):
            return self.action("hibernate")
        if has("спящий режим", "в сон", "усни", "засыпай", "спать", "режим сна"):
            return self.action("sleep")
        if has("заблокируй", "блокировка", "заблокировать", "блокируй"):
            return self.action("lock")

        # звук
        m = re.search(r"громкост\w*\s*(?:на\s*)?(\d{1,3})", t)
        if m:
            actions.set_volume(int(m.group(1)))
            return ok(f"Громкость {min(100, int(m.group(1)))}%", "volume")
        if has("выключи звук", "без звука", "отключи звук", "включи звук", "заглуши", "убери звук", "mute"):
            return self.action("mute")
        if has("громче", "прибавь", "погромче", "сделай громче"):
            actions.volume_up(5 if "очень" not in t else 10)
            return ok("Громче", "vol_up")
        if has("тише", "убавь", "потише"):
            actions.volume_down(5 if "очень" not in t else 10)
            return ok("Тише", "vol_down")

        # медиа
        if has("следующ", "переключи трек", "некст", "дальше"):
            return self.action("next")
        if has("предыдущ", "прошл"):
            return self.action("prev")
        if has("пауза", "на паузу", "продолжи", "играй", "плей", "возобнови", "стоп"):
            return self.action("play_pause")

        # окна и время
        if has("сверни все", "сверни окна", "рабочий стол"):
            return self.action("desktop")
        if has("который час", "сколько времени", "текущее время"):
            return ok(f"Сейчас {datetime.datetime.now():%H:%M}", "time")

        # поиск
        m = re.match(r"(?:найди|поищи|загугли|поиск|найти|ищи)\s+(?:в\s+(ютуб\w*|youtube)\s+)?(.+)", t)
        if m:
            query = m.group(2)
            if m.group(1):
                actions.youtube_search(query)
                return ok(f"Ищу на YouTube: {query}", "search")
            actions.web_search(query)
            return ok(f"Ищу: {query}", "search")
        m = re.match(r"(?:открой|зайди на)\s+сайт\s+(.+)", t)
        if m:
            site = m.group(1).replace(" точка ", ".").replace(" ", "")
            if "." not in site:
                site += ".com"
            actions.open_url(site)
            return ok(f"Открываю сайт {site}", "url")

        # закрыть приложение
        for w in CLOSE_WORDS:
            if t.startswith(w + " "):
                if strict and len(t[len(w):].split()) > 3:
                    break
                app = self.find_app(t[len(w):])
                if app:
                    return self.close_app(app)

        # открыть приложение
        for w in sorted(OPEN_WORDS, key=len, reverse=True):
            if t.startswith(w + " "):
                rest = t[len(w):].strip()
                if strict and len(rest.split()) > 3:
                    return fail("Сложная команда")
                app = self.find_app(rest)
                if app:
                    return self.open_app(app)
                found = programs.find(rest, limit=1)
                if found:
                    return self.open_program(found[0])
                return fail(f"Не нашёл приложение «{rest}». Добавьте его во вкладке «Приложения»")

        # просто название приложения
        if strict and len(t.split()) > 2:
            return fail("Не понял команду")
        app = self.find_app(t)
        if app:
            return self.open_app(app)
        return fail(f"Не понял команду: «{text}»")
