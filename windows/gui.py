"""Современный интерфейс VoxPC на CustomTkinter."""
import datetime
import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

import brain
import companion as companion_mod
import netinfo
import observer as observer_mod
import persona
import system
import tunnel
from commands import CommandProcessor
from config import APP_NAME, VERSION, data_dir
from server import ApiServer
from voice import Speaker, VoiceListener

BG = "#0B0D12"
PANEL = "#10131B"
CARD = "#171C28"
CARD_HI = "#21283A"
ACCENT = "#7C5CFF"
ACCENT_HI = "#9479FF"
CYAN = "#22D3EE"
TEXT = "#E6E8EF"
MUTED = "#8A93A6"
OK = "#2EE59D"
DANGER = "#FF5C7A"
WARN = "#FFC857"

SOURCE_ICON = {"voice": "🎙", "text": "⌨", "phone": "📱", "system": "⚙", "claude": "🤖", "cat": "🐈‍⬛"}


def F(size=14, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def greeting():
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        return "Доброе утро"
    if 12 <= h < 18:
        return "Добрый день"
    if 18 <= h < 23:
        return "Добрый вечер"
    return "Доброй ночи"


class App(ctk.CTk):
    def __init__(self, cfg, minimized=False):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.cfg = cfg
        self.title(f"{APP_NAME} — голосовое управление ПК")
        self.geometry("1160x720")
        self.minsize(980, 640)
        self.events = queue.Queue()
        self._tray_hint_shown = False

        self.processor = CommandProcessor(cfg)
        self.busy = False
        self.companion = None
        self.speaker = Speaker(lambda: cfg.get("tts"), engine_fn=lambda: cfg.get("tts_engine") or "edge",
                               on_speaking=lambda v: self.events.put(("speaking", v)),
                               settings_fn=lambda: {k: cfg.get(k) for k in
                                                    ("elevenlabs_key", "elevenlabs_voice", "elevenlabs_model")})
        self.observer = observer_mod.Observer(lambda kind, snap: self.events.put(("observer", (kind, snap))))
        self.voice = VoiceListener(
            on_text=lambda t, manual: self.events.put(("voice_text", t)),
            on_state=lambda s, msg="": self.events.put(("voice_state", (s, msg))),
            wake_word_fn=lambda: cfg.get("wake_word"),
        )
        self.brain = brain.ClaudeBrain(cfg)
        self.server = ApiServer(cfg, self.processor,
                                on_event=lambda src, text, res: self.events.put(("result", (src, text, res))),
                                command_handler=self.handle_text,
                                on_show=lambda: self.events.put(("show", None)))
        self.tunnel = tunnel.Tunnel(lambda: cfg.get("port"),
                                    on_status=lambda st, url="": self.events.put(("tunnel", (st, url))))
        self.tray = system.Tray(on_show=lambda: self.events.put(("show", None)),
                                on_quit=lambda: self.events.put(("quit", None)))

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.pages = {
            "home": HomePage(content, self),
            "apps": AppsPage(content, self),
            "settings": SettingsPage(content, self),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
        self.show("home")

        self.server_ok = False
        try:
            self.server.start()
            self.server_ok = True
        except OSError as e:
            self.after(400, lambda: self.home.add_log("system", "Сервер для телефона не запущен",
                                                      {"ok": False, "message": str(e)}))
        self.update_status()
        if self.server_ok and cfg.get("remote_enabled"):
            self.tunnel.start()

        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._poll)
        if cfg.get("always_listen"):
            self.after(800, lambda: self.set_always_listen(True))
        if cfg.get("companion_enabled"):
            self.after(1500, lambda: self.set_companion(True))
        if minimized:
            self.after(60, self.withdraw if self.tray.available else self.iconify)

    @property
    def home(self):
        return self.pages["home"]

    def connector_url(self):
        base = (self.cfg.get("public_url") or "").strip().rstrip("/") or self.tunnel.url
        return f"{base}/mcp/{self.cfg.get('mcp_secret')}" if base else ""

    # ---------- каркас ----------
    def _set_window_icon(self):
        ico = str(data_dir() / "icon.ico")
        try:
            if os.path.exists(ico) or system.save_ico(ico):
                self.after(250, lambda: self.iconbitmap(ico))
        except Exception:
            pass

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, width=240)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(5, weight=1)

        logo = ctk.CTkFrame(bar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 30))
        ctk.CTkLabel(logo, text="●", text_color=ACCENT, font=F(26, "bold")).pack(side="left")
        box = ctk.CTkFrame(logo, fg_color="transparent")
        box.pack(side="left", padx=10)
        ctk.CTkLabel(box, text=APP_NAME, font=F(22, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(box, text="голосовое управление", font=F(12), text_color=MUTED).pack(anchor="w")

        self.nav = {}
        for i, (key, label) in enumerate([("home", "🏠   Главная"), ("apps", "🧩   Приложения"),
                                          ("settings", "⚙   Настройки")]):
            b = ctk.CTkButton(bar, text=label, anchor="w", height=44, corner_radius=12, font=F(15),
                              fg_color="transparent", hover_color=CARD, text_color=TEXT,
                              command=lambda k=key: self.show(k))
            b.grid(row=i + 1, column=0, sticky="ew", padx=14, pady=3)
            self.nav[key] = b

        status = ctk.CTkFrame(bar, fg_color=CARD, corner_radius=16)
        status.grid(row=6, column=0, sticky="ew", padx=14, pady=18)
        row = ctk.CTkFrame(status, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 2))
        self.status_dot = ctk.CTkLabel(row, text="●", font=F(14), text_color=MUTED)
        self.status_dot.pack(side="left")
        self.status_text = ctk.CTkLabel(row, text="Запуск…", font=F(13, "bold"), text_color=TEXT)
        self.status_text.pack(side="left", padx=6)
        self.status_info = ctk.CTkLabel(status, text="", font=F(12), text_color=MUTED, justify="left")
        self.status_info.pack(anchor="w", padx=14, pady=(0, 12))
        ctk.CTkLabel(bar, text=f"v{VERSION}", font=F(11), text_color=MUTED).grid(row=7, column=0, pady=(0, 12))

    def show(self, key):
        for k, page in self.pages.items():
            if k != key:
                page.grid_remove()
        self.pages[key].grid()
        self.pages[key].tkraise()
        for k, b in self.nav.items():
            b.configure(fg_color=ACCENT if k == key else "transparent",
                        hover_color=ACCENT_HI if k == key else CARD)
        if key == "apps":
            self.pages["apps"].refresh()

    def update_status(self):
        ip = netinfo.local_ip()
        port = self.cfg.get("port")
        if self.server_ok:
            self.status_dot.configure(text_color=OK)
            self.status_text.configure(text="Готов к командам")
        else:
            self.status_dot.configure(text_color=DANGER)
            self.status_text.configure(text="Сервер не запущен")
        self.status_info.configure(text=f"IP: {ip}:{port}\nКод: {self.cfg.get('token')}")

    # ---------- события из фоновых потоков ----------
    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "voice_text":
                    self.run_command(payload, "voice")
                elif kind == "voice_state":
                    self.home.set_voice_state(*payload)
                    if self.companion:
                        self.companion.set_listening(payload[0])
                elif kind == "result":
                    source, text, res = payload
                    self.home.add_log(source, text, res)
                    if source in ("voice", "text"):
                        self.speaker.say(res.get("message", ""))
                    if self.companion and source != "claude" and res.get("message"):
                        self.companion.show_result(res["message"], res.get("ok", True))
                elif kind == "speaking":
                    if self.companion:
                        self.companion.set_speaking(payload)
                elif kind == "observer":
                    if self.companion:
                        self.companion.on_observer(*payload)
                elif kind == "companion_say":
                    if self.companion:
                        self.companion.say(payload)
                        self.companion.delivered()
                        self.home.add_log("cat", persona.NAME, {"ok": True, "message": payload})
                elif kind == "thinking":
                    if payload:
                        self.home.set_voice_state("processing", "Claude думает…")
                    else:
                        self.home.set_voice_state("idle", "")
                elif kind == "tunnel":
                    self.pages["settings"].set_tunnel_state(*payload)
                elif kind == "show":
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                elif kind == "quit":
                    self.quit_app()
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def handle_text(self, text):
        """Выполняет фразу: сначала быстрые локальные команды, остальное — через Claude."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "message": "Пустая команда"}
        self.busy = True
        try:
            return self._handle_text(text)
        finally:
            self.busy = False

    def _handle_text(self, text):
        try:
            if not self.cfg.get("brain_enabled"):
                return self.processor.execute(text)
            if self.cfg.get("brain_fast_local"):
                local = self.processor.execute(text, strict=True)
                if local.get("ok"):
                    return local
            self.events.put(("thinking", True))
            try:
                return self.brain.ask(text)
            finally:
                self.events.put(("thinking", False))
        except Exception as e:
            return {"ok": False, "message": f"Ошибка: {e}"}

    def run_command(self, text, source):
        text = (text or "").strip()
        if not text:
            return

        def work():
            res = self.handle_text(text)
            self.events.put(("result", (source, text, res)))

        threading.Thread(target=work, daemon=True).start()

    def run_action(self, action, label):
        def work():
            res = self.processor.action(action)
            self.events.put(("result", ("text", label, res)))
        threading.Thread(target=work, daemon=True).start()

    def set_always_listen(self, on: bool):
        self.cfg.set("always_listen", on)
        if on:
            self.voice.start_continuous()
        else:
            self.voice.stop_continuous()
            self.home.set_voice_state("idle", "")

    def set_companion(self, on: bool):
        self.cfg.set("companion_enabled", on)
        if on and not self.companion:
            try:
                self.companion = companion_mod.Companion(self)
                self.observer.start()
            except Exception as e:
                self.companion = None
                self.home.add_log("system", "Компаньон не запустился", {"ok": False, "message": str(e)})
        elif not on and self.companion:
            self.observer.stop()
            self.companion.destroy()
            self.companion = None
        if "settings" in getattr(self, "pages", {}):
            self.pages["settings"].sync_companion()

    def restart_companion(self):
        if self.companion:
            self.companion.destroy()
            self.companion = None
            self.set_companion(True)

    def on_close(self):
        if self.tray.available:
            self.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify("VoxPC работает в фоне. Откройте его из значка в трее.")
        else:
            if messagebox.askyesno(APP_NAME, "Закрыть VoxPC? Телефон перестанет управлять ПК."):
                self.quit_app()

    def quit_app(self):
        self.voice.stop_continuous()
        self.observer.stop()
        if self.companion:
            self.companion.destroy()
        self.tunnel.stop()
        try:
            self.server.stop()
        except Exception:
            pass
        self.tray.stop()
        self.destroy()


# ======================================================================
class HomePage(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.entries = []
        self._anim_job = None
        self._anim_flag = False
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        ctk.CTkLabel(head, text=greeting(), font=F(30, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(head, text="Скажите команду или нажмите на микрофон. Например: «открой стим».",
                     font=F(14), text_color=MUTED).pack(anchor="w")

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
        left.grid_columnconfigure(0, weight=1)

        # --- микрофон ---
        mic_card = ctk.CTkFrame(left, fg_color=CARD, corner_radius=24)
        mic_card.grid(row=0, column=0, sticky="ew")
        self.mic = ctk.CTkButton(mic_card, text="🎙", width=150, height=150, corner_radius=75,
                                 font=F(54), fg_color=ACCENT, hover_color=ACCENT_HI,
                                 command=self.app.voice.listen_once)
        self.mic.pack(pady=(28, 12))
        self.state_lbl = ctk.CTkLabel(mic_card, text="Нажмите и говорите", font=F(17, "bold"), text_color=TEXT)
        self.state_lbl.pack()
        self.hint_lbl = ctk.CTkLabel(mic_card, text="", font=F(13), text_color=MUTED)
        self.hint_lbl.pack(pady=(2, 10))
        self.listen_var = ctk.BooleanVar(value=bool(app.cfg.get("always_listen")))
        ctk.CTkSwitch(mic_card, text=f"Слушать постоянно (начинайте со слова «{app.cfg.get('wake_word')}»)",
                      variable=self.listen_var, font=F(13), progress_color=ACCENT,
                      command=lambda: app.set_always_listen(self.listen_var.get())).pack(pady=(0, 22))

        # --- ввод текстом ---
        row = ctk.CTkFrame(left, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=14)
        row.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(row, height=46, corner_radius=14, font=F(15), fg_color=CARD,
                                  border_width=0, placeholder_text="Введите команду: открой дискорд, громкость 30…")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self._send_text())
        ctk.CTkButton(row, text="Выполнить", height=46, width=130, corner_radius=14, font=F(14, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI, command=self._send_text).grid(row=0, column=1)

        # --- быстрые команды ---
        chips = ctk.CTkFrame(left, fg_color="transparent")
        chips.grid(row=2, column=0, sticky="ew")
        for txt in ("Открой Steam", "Открой Discord", "Громче", "Тише", "Пауза", "Сверни все окна"):
            ctk.CTkButton(chips, text=txt, height=32, corner_radius=16, font=F(13), fg_color=CARD,
                          hover_color=CARD_HI, text_color=TEXT, width=10,
                          command=lambda t=txt: self.app.run_command(t, "text")).pack(side="left", padx=(0, 8))

        # --- питание ---
        ctk.CTkLabel(left, text="Питание", font=F(16, "bold"), text_color=TEXT).grid(
            row=3, column=0, sticky="w", pady=(22, 8))
        power = ctk.CTkFrame(left, fg_color="transparent")
        power.grid(row=4, column=0, sticky="ew")
        for i in range(4):
            power.grid_columnconfigure(i, weight=1, uniform="p")
        items = [("🔒  Блокировка", "lock", False), ("🌙  Сон", "sleep", True),
                 ("🔄  Перезагрузка", "restart", True), ("⏻  Выключение", "shutdown", True)]
        for i, (label, act, confirm) in enumerate(items):
            ctk.CTkButton(power, text=label, height=52, corner_radius=14, font=F(14),
                          fg_color=CARD, hover_color=DANGER if act == "shutdown" else CARD_HI, text_color=TEXT,
                          command=lambda a=act, l=label, c=confirm: self._power(a, l, c)).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))

        # --- история ---
        right = ctk.CTkFrame(self, fg_color=CARD, corner_radius=24)
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        ctk.CTkLabel(top, text="История", font=F(18, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(top, text="Очистить", width=80, height=28, corner_radius=10, font=F(12),
                      fg_color="transparent", hover_color=CARD_HI, text_color=MUTED,
                      command=self.clear_log).pack(side="right")
        self.log = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.log.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.empty_lbl = ctk.CTkLabel(self.log, text="Здесь появятся ваши команды\nс ПК и с телефона",
                                      font=F(13), text_color=MUTED)
        self.empty_lbl.pack(pady=40)

        if not app.voice.available:
            self.hint_lbl.configure(text="Микрофон не найден — можно вводить команды текстом", text_color=WARN)

    def _send_text(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.app.run_command(text, "text")

    def _power(self, action, label, confirm):
        if confirm and not messagebox.askyesno(APP_NAME, f"{label.split('  ')[-1]}: вы уверены?"):
            return
        self.app.run_action(action, label.split("  ")[-1])

    # --- состояние микрофона ---
    def set_voice_state(self, state, msg):
        texts = {"listening": "Слушаю…", "processing": "Распознаю…",
                 "idle": "Нажмите и говорите", "error": "Ошибка"}
        self.state_lbl.configure(text=texts.get(state, state))
        self.hint_lbl.configure(text=msg or "", text_color=DANGER if state == "error" else MUTED)
        self._stop_anim()
        if state == "listening":
            self._animate(DANGER, "#C9405A")
        elif state == "processing":
            self._animate(CYAN, "#159AB0")
        else:
            self.mic.configure(fg_color=ACCENT)

    def _animate(self, c1, c2):
        self._anim_flag = not self._anim_flag
        self.mic.configure(fg_color=c1 if self._anim_flag else c2)
        self._anim_job = self.after(420, lambda: self._animate(c1, c2))

    def _stop_anim(self):
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    # --- история ---
    def add_log(self, source, text, res):
        if self.empty_lbl.winfo_exists():
            self.empty_lbl.destroy()
        res = res or {}
        card = ctk.CTkFrame(self.log, fg_color=CARD_HI, corner_radius=14)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(top, text=f"{SOURCE_ICON.get(source, '•')}  {text}", font=F(14, "bold"),
                     text_color=TEXT, anchor="w", justify="left", wraplength=300).pack(side="left")
        ctk.CTkLabel(top, text=datetime.datetime.now().strftime("%H:%M"), font=F(11),
                     text_color=MUTED).pack(side="right")
        if res.get("message"):
            ctk.CTkLabel(card, text=res["message"], font=F(13), anchor="w", justify="left", wraplength=320,
                         text_color=OK if res.get("ok") else DANGER).pack(fill="x", padx=12, pady=(2, 10))
        if self.entries:
            card.pack(fill="x", padx=4, pady=(0, 8), before=self.entries[0])
        else:
            card.pack(fill="x", padx=4, pady=(0, 8))
        self.entries.insert(0, card)
        while len(self.entries) > 60:
            self.entries.pop().destroy()

    def clear_log(self):
        for e in self.entries:
            e.destroy()
        self.entries.clear()


# ======================================================================
class AppsPage(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        box = ctk.CTkFrame(head, fg_color="transparent")
        box.pack(side="left")
        ctk.CTkLabel(box, text="Приложения", font=F(30, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(box, text="Голосом: «открой стим», «закрой дискорд». Игры Steam: steam://rungameid/ID",
                     font=F(14), text_color=MUTED).pack(anchor="w")
        ctk.CTkButton(head, text="＋  Добавить", height=44, corner_radius=14, font=F(14, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI, command=lambda: self.edit(None)).pack(side="right")

        self.grid_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_area.grid(row=1, column=0, sticky="nsew")
        for c in range(3):
            self.grid_area.grid_columnconfigure(c, weight=1, uniform="col")

    def refresh(self):
        for w in self.grid_area.winfo_children():
            w.destroy()
        for i, a in enumerate(self.app.cfg.apps):
            self._card(i, a).grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)

    def _card(self, index, a):
        card = ctk.CTkFrame(self.grid_area, fg_color=CARD, corner_radius=20)
        ctk.CTkLabel(card, text=a.get("icon") or "🧩", font=F(34)).pack(anchor="w", padx=18, pady=(16, 0))
        ctk.CTkLabel(card, text=a.get("name", ""), font=F(17, "bold"), text_color=TEXT).pack(anchor="w", padx=18)
        aliases = ", ".join(a.get("aliases", []))
        ctk.CTkLabel(card, text=f"Голосом: {aliases}" if aliases else "", font=F(12), text_color=MUTED,
                     wraplength=240, justify="left", anchor="w").pack(anchor="w", padx=18)
        path = a.get("path", "")
        ctk.CTkLabel(card, text=path if len(path) < 38 else path[:35] + "…", font=F(11),
                     text_color="#5E677A").pack(anchor="w", padx=18, pady=(2, 10))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(row, text="▶  Запустить", height=34, corner_radius=10, font=F(13, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI,
                      command=lambda: self._run(self.app.processor.open_app, a)).pack(side="left", fill="x",
                                                                                       expand=True)
        for txt, cmd, hover in (("■", lambda: self._run(self.app.processor.close_app, a), CARD_HI),
                                ("✎", lambda: self.edit(index), CARD_HI),
                                ("🗑", lambda: self.delete(index), DANGER)):
            ctk.CTkButton(row, text=txt, width=36, height=34, corner_radius=10, font=F(14),
                          fg_color=CARD_HI, hover_color=hover, text_color=TEXT, command=cmd).pack(side="left",
                                                                                                padx=(6, 0))
        return card

    def _run(self, fn, a):
        res = fn(a)
        self.app.home.add_log("text", a.get("name", ""), res)

    def delete(self, index):
        apps = self.app.cfg.apps
        if messagebox.askyesno(APP_NAME, f"Удалить «{apps[index]['name']}»?"):
            apps.pop(index)
            self.app.cfg.set_apps(apps)
            self.refresh()

    def edit(self, index):
        apps = self.app.cfg.apps
        current = apps[index] if index is not None else None

        def save(data):
            new = self.app.cfg.apps
            if index is None:
                new.append(data)
            else:
                new[index] = data
            self.app.cfg.set_apps(new)
            self.refresh()

        AppDialog(self, current, save)


class AppDialog(ctk.CTkToplevel):
    def __init__(self, master, data, on_save):
        super().__init__(master, fg_color=BG)
        self.on_save = on_save
        self.title("Приложение")
        self.geometry("560x520")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.after(150, self.grab_set)
        data = data or {}

        ctk.CTkLabel(self, text="Редактирование" if data else "Новое приложение",
                     font=F(22, "bold"), text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 10))
        self.fields = {}
        spec = [("name", "Название", data.get("name", "")),
                ("icon", "Иконка (эмодзи)", data.get("icon", "🧩")),
                ("aliases", "Как называть голосом (через запятую)", ", ".join(data.get("aliases", []))),
                ("path", "Путь к программе, ярлыку, URL или steam://…", data.get("path", "")),
                ("process", "Имя процесса для закрытия (например, Discord.exe)", data.get("process", ""))]
        for key, label, value in spec:
            ctk.CTkLabel(self, text=label, font=F(13), text_color=MUTED).pack(anchor="w", padx=24, pady=(6, 2))
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=24)
            e = ctk.CTkEntry(row, height=38, corner_radius=10, font=F(14), fg_color=CARD, border_width=0)
            e.insert(0, value)
            e.pack(side="left", fill="x", expand=True)
            if key == "path":
                ctk.CTkButton(row, text="Обзор…", width=90, height=38, corner_radius=10, fg_color=CARD_HI,
                              hover_color=ACCENT, command=self._browse).pack(side="left", padx=(8, 0))
            self.fields[key] = e

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=22, side="bottom")
        ctk.CTkButton(btns, text="Сохранить", height=42, corner_radius=12, font=F(14, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI, command=self._save).pack(side="right")
        ctk.CTkButton(btns, text="Отмена", height=42, corner_radius=12, fg_color=CARD, hover_color=CARD_HI,
                      command=self.destroy).pack(side="right", padx=10)

    def _browse(self):
        path = filedialog.askopenfilename(parent=self, title="Выберите программу",
                                          filetypes=[("Программы и ярлыки", "*.exe *.lnk *.url *.bat"),
                                                     ("Все файлы", "*.*")])
        if not path:
            return
        path = os.path.normpath(path)
        self._set("path", path)
        base = os.path.basename(path)
        stem = os.path.splitext(base)[0]
        if path.lower().endswith(".exe") and not self.fields["process"].get():
            self._set("process", base)
        if not self.fields["name"].get():
            self._set("name", stem)
        if not self.fields["aliases"].get():
            self._set("aliases", stem.lower())

    def _set(self, key, value):
        self.fields[key].delete(0, "end")
        self.fields[key].insert(0, value)

    def _save(self):
        v = {k: e.get().strip() for k, e in self.fields.items()}
        if not v["name"] or not v["path"]:
            messagebox.showwarning(APP_NAME, "Укажите название и путь", parent=self)
            return
        self.on_save({"name": v["name"], "icon": v["icon"] or "🧩",
                      "aliases": [a.strip() for a in v["aliases"].split(",") if a.strip()],
                      "path": v["path"], "process": v["process"]})
        self.destroy()


# ======================================================================
class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        cfg = app.cfg
        # обычная рамка-страница, внутри — прокручиваемая область
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        self.body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.body, text="Настройки", font=F(30, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", pady=(0, 16))

        # --- мозг ---
        c = self._card(1, "🧠  Мозг: Claude",
                       "VoxPC передаёт ваши команды Claude, а Claude сам решает, что сделать, выполняет и отвечает "
                       "голосом. Работает по вашей подписке через Claude Code.")
        self.brain_status = ctk.CTkLabel(c, text="", font=F(13), text_color=MUTED, justify="left")
        self.brain_status.pack(anchor="w", padx=20)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(8, 6))
        self._btn(row, "1. Установить Claude Code", self._brain_install)
        self._btn(row, "2. Войти в аккаунт", self._brain_login)
        self._btn(row, "3. Проверить", self._brain_test, accent=True)
        self.brain_var = ctk.BooleanVar(value=bool(cfg.get("brain_enabled")))
        self._switch(c, "Использовать Claude как мозг VoxPC", self.brain_var,
                     lambda: cfg.set("brain_enabled", self.brain_var.get()))
        self.fast_var = ctk.BooleanVar(value=bool(cfg.get("brain_fast_local")))
        self._switch(c, "Простые команды («открой стим», «громче») выполнять сразу, без Claude — быстрее",
                     self.fast_var, lambda: cfg.set("brain_fast_local", self.fast_var.get()))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 18))
        ctk.CTkLabel(row, text="Модель", font=F(14), text_color=TEXT).pack(side="left")
        names = list(brain.MODELS.values())
        self.model_menu = ctk.CTkOptionMenu(
            row, values=names, width=200, fg_color=CARD_HI, button_color=ACCENT, button_hover_color=ACCENT_HI,
            command=lambda v: cfg.set("brain_model", next(k for k, n in brain.MODELS.items() if n == v)))
        self.model_menu.set(brain.MODELS.get(cfg.get("brain_model"), names[0]))
        self.model_menu.pack(side="left", padx=12)
        self._refresh_brain_status()

        # --- компаньон ---
        c = self._card(2, "🐈‍⬛  Глитч — компаньон на рабочем столе",
                       "Чёрная кибер-кошка живёт поверх окон, отвечает голосом и сама комментирует, что вы делаете.")
        tips = ("Гладьте её по голове кликом, тыкайте в бок, тащите мышкой. Двойной клик — сказать команду,\n"
                "правый клик — меню. С включённым «Мозгом» она понимает, что происходит, и комментирует по сути.")
        ctk.CTkLabel(c, text=tips, font=F(12), text_color=MUTED, justify="left").pack(anchor="w", padx=20)
        self.cat_var = ctk.BooleanVar(value=bool(cfg.get("companion_enabled")))
        self._switch(c, "Показывать Глитч поверх окон", self.cat_var, lambda: app.set_companion(self.cat_var.get()))
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 6))
        self._option(grid, 0, "Размер", {"0.75": "Маленькая", "1.0": "Средняя", "1.3": "Большая"},
                     str(cfg.get("companion_scale") or 1.0),
                     lambda v: (cfg.set("companion_scale", float(v)), app.restart_companion()))
        self._option(grid, 1, "Комментарии", {"off": "Выключены", "rare": "Иногда", "chatty": "Разговорчивая"},
                     cfg.get("companion_comments") or "rare", lambda v: cfg.set("companion_comments", v))
        self._option(grid, 2, "Гулять по экрану", {"1": "раз в минуту", "3": "раз в 3 мин", "10": "раз в 10 мин",
                                                   "30": "раз в 30 мин"},
                     str(int(cfg.get("companion_roam_minutes") or 3)),
                     lambda v: cfg.set("companion_roam_minutes", int(v)))
        self._option(grid, 3, "Голос", {"elevenlabs": "ElevenLabs (голос Глитч)", "edge": "Нейроголос Microsoft",
                                        "sapi": "Голос Windows"},
                     cfg.get("tts_engine") or "edge", lambda v: cfg.set("tts_engine", v))
        for key, text in (("companion_roam", "Сама перемещается и садится на окна"),
                          ("companion_screens", "Смотрит на экран (снимки экрана отправляются Claude для комментариев)"),
                          ("companion_quiet", "Тихие часы 23:00–09:00"),
                          ("companion_hide_fullscreen", "Прятаться, когда открыта полноэкранная игра или видео")):
            var = ctk.BooleanVar(value=bool(cfg.get(key)))
            self._switch(c, text, var, lambda k=key, v=var: cfg.set(k, v.get()))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 18))
        self._btn(row, "Позвать домой", lambda: app.companion and app.companion.go_home())
        self._btn(row, "Скажи что-нибудь", lambda: app.companion and app.companion.initiate("idle", force=True))
        self._btn(row, "Проверить голос", lambda: app.speaker.say("Мрр. Привет, это Глитч!", force=True))

        # ElevenLabs
        ctk.CTkLabel(c, text="ElevenLabs", font=F(15, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(0, 2))
        ctk.CTkLabel(c, text="Вставьте API-ключ (elevenlabs.io → профиль → API Keys) и Voice ID голоса Глитч.",
                     font=F(12), text_color=MUTED).pack(anchor="w", padx=20)
        el = ctk.CTkFrame(c, fg_color="transparent")
        el.pack(fill="x", padx=20, pady=(6, 4))
        ctk.CTkLabel(el, text="API-ключ", font=F(13), text_color=TEXT, width=80, anchor="w").grid(row=0, column=0)
        self.el_key = ctk.CTkEntry(el, width=360, height=34, corner_radius=10, fg_color=CARD_HI, border_width=0,
                                   show="•", placeholder_text="sk_…")
        if cfg.get("elevenlabs_key"):
            self.el_key.insert(0, cfg.get("elevenlabs_key"))
        self.el_key.grid(row=0, column=1, padx=10, pady=3, sticky="w")
        ctk.CTkLabel(el, text="Voice ID", font=F(13), text_color=TEXT, width=80, anchor="w").grid(row=1, column=0)
        self.el_voice = ctk.CTkEntry(el, width=360, height=34, corner_radius=10, fg_color=CARD_HI, border_width=0)
        if cfg.get("elevenlabs_voice"):
            self.el_voice.insert(0, cfg.get("elevenlabs_voice"))
        self.el_voice.grid(row=1, column=1, padx=10, pady=3, sticky="w")
        mgrid = ctk.CTkFrame(c, fg_color="transparent")
        mgrid.pack(fill="x", padx=20, pady=(2, 0))
        self._option(mgrid, 0, "Модель", {"eleven_multilingual_v2": "Multilingual v2 — лучший русский",
                                           "eleven_v3": "Eleven v3 — самая эмоциональная",
                                           "eleven_flash_v2_5": "Flash v2.5 — самая быстрая"},
                     cfg.get("elevenlabs_model") or "eleven_multilingual_v2",
                     lambda v: cfg.set("elevenlabs_model", v))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 4))
        self._btn(row, "Сохранить и проверить", self._eleven_save, accent=True)
        self.el_status = ctk.CTkLabel(c, text="", font=F(12), text_color=MUTED, justify="left")
        self.el_status.pack(anchor="w", padx=20, pady=(0, 18))

        # --- подключение ---
        c = self._card(3, "📱  Подключение телефона",
                       "Нажмите «Найти ПК» в приложении на телефоне или введите эти данные вручную.")
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(4, 18))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="g")
        self.ip_val = self._tile(grid, 0, "IP-адрес ПК", netinfo.local_ip())
        self._tile(grid, 1, "Порт", str(cfg.get("port")))
        self.token_val = self._tile(grid, 2, "Код доступа", cfg.get("token"), CYAN)
        self.mac_val = self._tile(grid, 3, "MAC (для включения)", "определяю…")
        btns = ctk.CTkFrame(c, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 18))
        self._btn(btns, "Скопировать код", lambda: self._copy(cfg.get("token")))
        self._btn(btns, "Сменить код", self._regen)
        self._btn(btns, "Скопировать MAC", lambda: self._copy(self.mac_val.cget("text")))
        threading.Thread(target=self._load_mac, daemon=True).start()

        # --- голос ---
        c = self._card(4, "🎙  Голос", "Ключевое слово нужно в режиме постоянного прослушивания.")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(row, text="Ключевое слово", font=F(14), text_color=TEXT).pack(side="left")
        self.wake = ctk.CTkEntry(row, width=200, height=36, corner_radius=10, fg_color=CARD_HI, border_width=0)
        self.wake.insert(0, cfg.get("wake_word"))
        self.wake.pack(side="left", padx=12)
        self._btn(row, "Сохранить", lambda: (cfg.set("wake_word", self.wake.get().strip().lower() or "компьютер"),
                                             self._toast("Ключевое слово сохранено")))
        self.tts_var = ctk.BooleanVar(value=bool(cfg.get("tts")))
        self._switch(c, "Озвучивать ответы голосом", self.tts_var, lambda: cfg.set("tts", self.tts_var.get()))
        self._btn(c, "Проверить голос", lambda: app.speaker.say("Привет! Я готов к работе."),
                  pack=dict(anchor="w", padx=20, pady=(4, 18)))

        # --- запуск ---
        c = self._card(5, "🚀  Запуск", "Чтобы телефон мог управлять ПК, VoxPC должен работать в фоне.")
        self.auto_var = ctk.BooleanVar(value=system.autostart_enabled() if os.name == "nt" else False)
        self._switch(c, "Запускать вместе с Windows", self.auto_var, self._toggle_autostart)
        self.min_var = ctk.BooleanVar(value=bool(cfg.get("start_minimized")))
        self._switch(c, "Запускать свёрнутым в трей", self.min_var,
                     lambda: cfg.set("start_minimized", self.min_var.get()), last=True)

        # --- WoL ---
        c = self._card(6, "⚡  Удалённое включение (Wake-on-LAN)", "")
        steps = ("1. В BIOS/UEFI включите «Wake on LAN» / «Power On by PCI-E» (и отключите ErP/EuP).\n"
                 "2. Нажмите кнопку ниже — VoxPC сам настроит сетевую карту, отключит «Быстрый запуск»\n"
                 "    и откроет порты в брандмауэре (нужны права администратора).\n"
                 "3. ПК должен быть подключён к роутеру кабелем. Включение работает из выключенного\n"
                 "    состояния, сна и гибернации.\n"
                 "4. Для включения через интернет: на роутере пробросьте UDP-порт 9 и TCP-порт "
                 f"{cfg.get('port')},\n    либо используйте встроенную функцию WoL роутера (Keenetic, ASUS, TP-Link).")
        ctk.CTkLabel(c, text=steps, font=F(13), text_color=MUTED, justify="left").pack(anchor="w", padx=20)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=18)
        self._btn(row, "Настроить Windows автоматически", self._wol, accent=True)
        self._btn(row, "Папка с настройками", system.open_data_dir)

        # --- коннектор Claude ---
        c = self._card(7, "🤖  Коннектор Claude",
                       "Claude управляет ПК прямо из чата и голосового режима — по вашей подписке, без API-ключа.")
        ctk.CTkLabel(c, text="На этом ПК — приложение Claude для Windows", font=F(15, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(4, 0))
        ctk.CTkLabel(c, text="Нажмите кнопку, затем полностью закройте Claude (через трей) и откройте снова.",
                     font=F(13), text_color=MUTED).pack(anchor="w", padx=20)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(8, 4))
        self._btn(row, "Подключить к Claude Desktop", self._install_desktop, accent=True)
        self._btn(row, "Скопировать конфиг", self._copy_desktop_config)
        self.desktop_status = ctk.CTkLabel(c, text="", font=F(12), text_color=MUTED, justify="left")
        self.desktop_status.pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(c, text="Через интернет — с телефона и claude.ai", font=F(15, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(8, 0))
        steps = ("1. Нажмите «Установить cloudflared» (один раз).\n"
                 "2. Включите переключатель ниже и дождитесь адреса.\n"
                 "3. claude.ai → Настройки → Коннекторы → «Добавить свой коннектор» → вставьте адрес.\n"
                 "Бесплатный туннель получает новый адрес после каждого перезапуска VoxPC —\n"
                 "тогда обновите адрес коннектора в Claude (или укажите свой постоянный адрес).")
        ctk.CTkLabel(c, text=steps, font=F(13), text_color=MUTED, justify="left").pack(anchor="w", padx=20)
        self.remote_var = ctk.BooleanVar(value=bool(cfg.get("remote_enabled")))
        self._switch(c, "Доступ через интернет (Cloudflare Tunnel)", self.remote_var, self._toggle_remote)
        self.tunnel_status = ctk.CTkLabel(c, text="Выключен", font=F(13), text_color=MUTED)
        self.tunnel_status.pack(anchor="w", padx=20)
        self.url_entry = ctk.CTkEntry(c, height=38, corner_radius=10, font=F(13), fg_color=CARD_HI, border_width=0)
        self.url_entry.pack(fill="x", padx=20, pady=(6, 6))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 8))
        self._btn(row, "Скопировать адрес", lambda: self._copy(app.connector_url()) if app.connector_url()
                  else self._toast("Адреса пока нет"), accent=True)
        self._btn(row, "Установить cloudflared", tunnel.install_cloudflared)
        self._btn(row, "Сменить секрет", self._regen_secret)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 6))
        ctk.CTkLabel(row, text="Свой постоянный адрес", font=F(13), text_color=TEXT).pack(side="left")
        self.public_entry = ctk.CTkEntry(row, width=300, height=34, corner_radius=10, fg_color=CARD_HI,
                                         border_width=0, placeholder_text="https://my-pc.example.com")
        if cfg.get("public_url"):
            self.public_entry.insert(0, cfg.get("public_url"))
        self.public_entry.pack(side="left", padx=10)
        self._btn(row, "Сохранить", self._save_public_url)
        ctk.CTkLabel(c, text="⚠ Любой, у кого есть этот адрес, сможет управлять ПК. Никому его не показывайте.",
                     font=F(12), text_color=WARN).pack(anchor="w", padx=20, pady=(4, 18))
        self._refresh_url()

    # --- helpers ---
    def _card(self, row, title, subtitle):
        c = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        c.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(c, text=title, font=F(18, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 0))
        if subtitle:
            ctk.CTkLabel(c, text=subtitle, font=F(13), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 10))
        return c

    def _tile(self, parent, col, label, value, color=TEXT):
        t = ctk.CTkFrame(parent, fg_color=CARD_HI, corner_radius=14)
        t.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
        ctk.CTkLabel(t, text=label, font=F(12), text_color=MUTED).pack(anchor="w", padx=14, pady=(10, 0))
        v = ctk.CTkLabel(t, text=value, font=F(18, "bold"), text_color=color)
        v.pack(anchor="w", padx=14, pady=(0, 10))
        return v

    def _btn(self, parent, text, cmd, accent=False, pack=None):
        b = ctk.CTkButton(parent, text=text, height=36, corner_radius=10, font=F(13, "bold" if accent else "normal"),
                          fg_color=ACCENT if accent else CARD_HI, hover_color=ACCENT_HI if accent else ACCENT,
                          text_color=TEXT, command=cmd)
        b.pack(**(pack or dict(side="left", padx=(0, 8))))
        return b

    def _switch(self, parent, text, var, cmd, last=False):
        ctk.CTkSwitch(parent, text=text, variable=var, font=F(14), progress_color=ACCENT,
                      command=cmd).pack(anchor="w", padx=20, pady=(4, 18 if last else 6))

    def _load_mac(self):
        mac = netinfo.mac_address()
        self.after(0, lambda: self.mac_val.configure(text=mac))

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._toast("Скопировано")

    def _regen(self):
        if messagebox.askyesno(APP_NAME, "Сменить код? Его нужно будет ввести на телефоне заново."):
            self.token_val.configure(text=self.app.cfg.regenerate_token())
            self.app.update_status()

    def _toggle_autostart(self):
        try:
            system.set_autostart(self.auto_var.get())
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Не удалось изменить автозапуск: {e}")
            self.auto_var.set(not self.auto_var.get())

    def _wol(self):
        try:
            system.run_wol_setup()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Не удалось запустить настройку: {e}")

    # --- компаньон ---
    def _option(self, parent, row, label, choices, current, on_change):
        ctk.CTkLabel(parent, text=label, font=F(14), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=4)
        names = list(choices.values())
        menu = ctk.CTkOptionMenu(parent, values=names, width=220, fg_color=CARD_HI, button_color=ACCENT,
                                 button_hover_color=ACCENT_HI,
                                 command=lambda v: on_change(next(k for k, n in choices.items() if n == v)))
        menu.set(choices.get(current, names[0]))
        menu.grid(row=row, column=1, sticky="w", padx=12, pady=4)

    def _eleven_save(self):
        cfg = self.app.cfg
        cfg.set("elevenlabs_key", self.el_key.get().strip())
        cfg.set("elevenlabs_voice", self.el_voice.get().strip())
        self.el_status.configure(text="Проверяю…", text_color=WARN)

        def work():
            try:
                self.app.speaker.eleven_synth("Мрр. Проверка голоса, всё отлично слышно.")
                ok, msg = True, "✓ Голос работает. Выбрана озвучка ElevenLabs."
            except Exception as e:
                ok, msg = False, str(e)

            def show():
                self.el_status.configure(text=msg, text_color=OK if ok else DANGER)
                if ok:
                    cfg.set("tts_engine", "elevenlabs")
                    self.app.speaker.say("Мрр. Ну что, как тебе мой новый голос? Только не говори, что "
                                         "скучала по старому.", force=True)
            self.after(0, show)

        threading.Thread(target=work, daemon=True).start()

    def sync_companion(self):
        self.cat_var.set(bool(self.app.cfg.get("companion_enabled")))

    # --- мозг ---
    def _refresh_brain_status(self):
        exe = brain.find_claude()
        if exe:
            self.brain_status.configure(text=f"✓ Claude Code найден: {exe}", text_color=OK)
        else:
            self.brain_status.configure(text="Claude Code не установлен — нажмите «1. Установить Claude Code»",
                                        text_color=WARN)

    def _brain_install(self):
        brain.install_claude_code()
        self.brain_status.configure(text="Идёт установка в отдельном окне. Когда закончится — нажмите "
                                         "«2. Войти в аккаунт».", text_color=WARN)
        self.after(15000, self._refresh_brain_status)

    def _brain_login(self):
        try:
            brain.login_claude_code()
            self.brain_status.configure(
                text="В открывшемся окне войдите через аккаунт Claude (подписка Pro), затем закройте окно\n"
                     "и нажмите «3. Проверить».", text_color=WARN)
        except Exception as e:
            self.brain_status.configure(text=str(e), text_color=DANGER)

    def _brain_test(self):
        self.brain_status.configure(text="Проверяю… (до 30 секунд)", text_color=WARN)

        def work():
            self.app.brain.reset()
            res = self.app.brain.ask("Это проверка связи. Ответь одним словом: Готово.")
            self.app.brain.reset()

            def show():
                if res.get("ok"):
                    self.brain_status.configure(text=f"✓ Claude отвечает: {res['message']}", text_color=OK)
                    if not self.brain_var.get():
                        self.brain_var.set(True)
                        self.app.cfg.set("brain_enabled", True)
                else:
                    self.brain_status.configure(text=res.get("message", "Ошибка"), text_color=DANGER)
            self.after(0, show)

        threading.Thread(target=work, daemon=True).start()

    # --- коннектор ---
    def _install_desktop(self):
        try:
            paths = system.install_claude_desktop()
            self.desktop_status.configure(text="✓ Готово. Перезапустите Claude Desktop.\n" + "\n".join(paths),
                                          text_color=OK)
        except Exception as e:
            self.desktop_status.configure(text=f"Не получилось: {e}", text_color=DANGER)

    def _copy_desktop_config(self):
        import json
        try:
            entry = system.mcp_server_entry()
        except Exception as e:
            self.desktop_status.configure(text=str(e), text_color=DANGER)
            return
        self._copy(json.dumps({"mcpServers": {"voxpc": entry}}, ensure_ascii=False, indent=2))

    def _toggle_remote(self):
        on = self.remote_var.get()
        self.app.cfg.set("remote_enabled", on)
        if on:
            if not self.app.server_ok:
                self.set_tunnel_state("error", "Сервер VoxPC не запущен")
                return
            self.app.tunnel.start()
        else:
            self.app.tunnel.stop()

    def set_tunnel_state(self, state, url):
        texts = {"missing": ("cloudflared не найден — нажмите «Установить cloudflared», потом включите снова", DANGER),
                 "starting": ("Запускаю туннель…", WARN),
                 "running": ("● Работает — скопируйте адрес и добавьте его в Claude", OK),
                 "stopped": ("Выключен", MUTED)}
        text, color = texts.get(state, (url or "Ошибка", DANGER))
        self.tunnel_status.configure(text=text, text_color=color)
        if state in ("missing", "error"):
            self.remote_var.set(False)
            self.app.cfg.set("remote_enabled", False)
        if state == "running":
            self.app.home.add_log("system", "Коннектор Claude доступен через интернет", {"ok": True, "message": url})
        self._refresh_url()

    def _refresh_url(self):
        url = self.app.connector_url()
        self.url_entry.configure(state="normal")
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url or "Адрес появится после запуска туннеля")
        self.url_entry.configure(state="readonly")

    def _save_public_url(self):
        self.app.cfg.set("public_url", self.public_entry.get().strip())
        self._refresh_url()
        self._toast("Адрес сохранён")

    def _regen_secret(self):
        if messagebox.askyesno(APP_NAME, "Сменить секрет? Старый адрес коннектора перестанет работать — "
                                         "его нужно будет обновить в Claude."):
            self.app.cfg.regenerate_mcp_secret()
            self._refresh_url()

    def _toast(self, text):
        self.app.home.hint_lbl.configure(text=text, text_color=OK)
