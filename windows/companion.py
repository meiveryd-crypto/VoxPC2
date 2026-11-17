"""Глитч — анимированный компаньон VoxPC поверх всех окон.

Окно без рамки с прозрачным цветом-ключом: видна только кошка, клики по пустому месту проходят насквозь.
Умеет: моргать, следить глазами за курсором, говорить (рот двигается под голос), мурчать при поглаживании,
перетаскиваться, спать, «телепортироваться» сбоем по экрану, сидеть на верхней кромке активного окна,
прятаться в полноэкранных играх и сама комментировать происходящее (через Claude или готовые реплики).
"""
import math
import os
import random
import threading
import time
import tkinter as tk

from PIL import ImageTk

import actions
import observer as obs
import persona
from cat_render import KEY, CatRenderer, CatState

KEY_HEX = "#%02x%02x%02x" % KEY
FPS_MS = 50

MODES = {  # мин. пауза между репликами (сек), максимум в час
    "off": None,
    "rare": (360, 10),
    "chatty": (120, 30),
}


def work_area(root):
    if obs.IS_WIN:
        import ctypes
        r = obs.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
        return r.left, r.top, r.right, r.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def window_rect(hwnd):
    if not obs.IS_WIN or not hwnd:
        return None
    import ctypes
    u = ctypes.windll.user32
    if not u.IsWindow(hwnd) or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
        return None
    r = obs.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class Bubble:
    """Облачко с репликой над кошкой."""

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY_HEX)
        try:
            self.win.attributes("-transparentcolor", KEY_HEX)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.win.withdraw()
        self._hide_job = None

    def show(self, text, anchor_x, anchor_y, seconds):
        c = self.canvas
        c.delete("all")
        pad, maxw = 14, 280
        tid = c.create_text(pad, pad, text=text, anchor="nw", width=maxw, fill="#E6E8EF",
                            font=("Segoe UI", 11))
        x0, y0, x1, y1 = c.bbox(tid)
        w, h = x1 + pad, y1 + pad
        r = 14
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        c.create_polygon(pts, smooth=True, fill="#151926", outline="#22D3EE", width=2)
        tail_x = w / 2
        c.create_polygon(tail_x - 9, h - 1, tail_x + 9, h - 1, tail_x, h + 12, fill="#151926", outline="#22D3EE",
                         width=2)
        c.create_line(tail_x - 8, h - 1, tail_x + 8, h - 1, fill="#151926", width=3)
        c.tag_raise(tid)
        c.configure(width=w + 2, height=h + 14)
        sw = self.win.winfo_screenwidth()
        x = int(min(max(4, anchor_x - w / 2), sw - w - 6))
        y = int(max(4, anchor_y - h - 16))
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        if self._hide_job:
            self.win.after_cancel(self._hide_job)
        self._hide_job = self.win.after(int(seconds * 1000), self.hide)

    def hide(self):
        self._hide_job = None
        self.win.withdraw()


class Companion:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.root = app
        dpi = self.root.winfo_fpixels("1i") / 96.0
        self.renderer = CatRenderer(float(self.cfg.get("companion_scale") or 1.0) * dpi)
        self.w, self.h = self.renderer.size
        self.state = CatState()

        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY_HEX)
        try:
            self.win.attributes("-transparentcolor", KEY_HEX)
        except tk.TclError:
            pass
        self.label = tk.Label(self.win, bg=KEY_HEX, bd=0, highlightthickness=0, cursor="hand2")
        self.label.pack()
        self.bubble = Bubble(self.root)

        self.x, self.y = self._home()
        pos = self.cfg.get("companion_pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.x, self.y = int(pos[0]), int(pos[1])
        self._place()

        now = time.time()
        self._last = now
        self._next_blink = now + 2
        self._blink_start = 0
        self._twitch = 0
        self._mood_until = 0
        self.speaking = False
        self.sleeping = False
        self.hidden = False
        self.perch_hwnd = None
        self._teleport = None
        self._drag = None
        self._click_job = None
        self._last_interaction = now
        self._next_roam = now + self._roam_interval()
        # инициатива
        self.recent_lines = []
        self.comment_times = []
        self._next_comment = now + random.uniform(45, 70)
        self._pending_game = None
        self._generating = False

        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._motion)
        self.label.bind("<ButtonRelease-1>", self._release)
        self.label.bind("<Double-Button-1>", self._double)
        self.label.bind("<Button-3>", self._menu)

        self._tick()
        self.win.after(1200, lambda: self.say(persona.line("greet"), mood="happy"))

    # ------------------------------------------------------------ геометрия
    def _home(self):
        l, t, r, b = work_area(self.root)
        return r - self.w - 40, b - int(self.h * 0.97)

    def _place(self):
        l, t, r, b = work_area(self.root)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.x = int(min(max(-self.w * 0.3, self.x), sw - self.w * 0.7))
        self.y = int(min(max(-self.h * 0.2, self.y), sh - self.h * 0.6))
        self.win.geometry(f"{self.w}x{self.h}+{self.x}+{self.y}")

    def _roam_interval(self):
        minutes = float(self.cfg.get("companion_roam_minutes") or 3)
        return minutes * 60 * random.uniform(0.8, 1.2)

    # ------------------------------------------------------------ анимация
    def _tick(self):
        try:
            self._update()
        except Exception:
            pass
        self.win.after(FPS_MS, self._tick)

    def _update(self):
        now = time.time()
        dt = min(0.2, now - self._last)
        self._last = now
        s = self.state
        s.t += dt

        if now >= self._next_blink:
            self._blink_start = now
            self._next_blink = now + random.uniform(2.5, 6.5)
        b = (now - self._blink_start) / 0.16
        s.blink = (1 - abs(1 - b * 2)) if 0 <= b <= 1 else 0.0

        if self.speaking:
            s.mouth = max(0.15, abs(math.sin(s.t * 13 + math.sin(s.t * 4) * 2))) * random.uniform(0.6, 1.0)
        else:
            s.mouth = max(0.0, s.mouth - dt * 6)

        cx, cy = obs.cursor_pos()
        dx = (cx - (self.x + self.w / 2)) / 350
        dy = (cy - (self.y + self.h * 0.37)) / 350
        s.look = (max(-1, min(1, dx)), max(-1, min(1, dy)))

        if random.random() < dt * 0.12:
            self._twitch = now
        s.ear_twitch = max(0.0, 1 - (now - self._twitch) / 0.3) if now - self._twitch < 0.3 else 0.0
        s.purr = max(0.0, s.purr - dt * 0.35)

        if self._mood_until and now > self._mood_until:
            self._mood_until = 0
            s.mood = "sleep" if self.sleeping else "neutral"

        if self._teleport:
            self._teleport_step(now)

        if self.perch_hwnd and int(s.t * 4) % 2 == 0:
            self._follow_perch()

        if not self.hidden and self.cfg.get("companion_roam") and not self.sleeping and not self._drag \
                and now > self._next_roam and now - self._last_interaction > 20 and not self.speaking:
            self._next_roam = now + self._roam_interval()
            self.roam()

        if not self.hidden:
            self.photo = ImageTk.PhotoImage(self.renderer.render(s))
            self.label.configure(image=self.photo)

    def set_mood(self, mood, seconds=4.0):
        if self.sleeping and mood not in ("sleep",):
            self.wake(quiet=True)
        self.state.mood = mood
        self._mood_until = time.time() + seconds

    # ------------------------------------------------------------ речь
    def say(self, text, mood=None, speak=True, seconds=None):
        if not text or self.hidden:
            return
        if mood:
            self.set_mood(mood, 5)
        self.recent_lines = (self.recent_lines + [text])[-6:]
        dur = seconds or max(4.0, min(14.0, len(text) / 11))
        self.bubble.show(text, self.x + self.w / 2, self.y + self.h * 0.05, dur)
        if speak:
            self.app.speaker.say(text)

    def show_result(self, text, ok=True):
        """Ответ на команду пользователя (голос озвучивает само приложение)."""
        self.say(text, mood="happy" if ok else "annoyed", speak=False)

    def set_speaking(self, value):
        self.speaking = value

    def set_listening(self, state):
        if state == "listening":
            self.set_mood("surprised", 8)
        elif state == "processing":
            self.set_mood("smug", 10)
        elif self.state.mood in ("surprised", "smug"):
            self.set_mood("neutral", 0.1)

    # ------------------------------------------------------------ взаимодействия
    def _press(self, e):
        self._drag = {"x": e.x_root, "y": e.y_root, "wx": self.x, "wy": self.y, "moved": False, "ey": e.y}
        self._last_interaction = time.time()

    def _motion(self, e):
        d = self._drag
        if not d:
            return
        if abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) > 6:
            d["moved"] = True
            self.perch_hwnd = None
            self.x = d["wx"] + e.x_root - d["x"]
            self.y = d["wy"] + e.y_root - d["y"]
            self.win.geometry(f"+{self.x}+{self.y}")
            self.state.mood = "surprised"

    def _release(self, e):
        d, self._drag = self._drag, None
        self._last_interaction = time.time()
        if d and d["moved"]:
            self._place()
            self.cfg.set("companion_pos", [self.x, self.y])
            self.set_mood("smug", 2)
            return
        rel_y = (d["ey"] if d else e.y) / self.h
        if self._click_job:
            self.win.after_cancel(self._click_job)
        self._click_job = self.win.after(260, lambda: self._click(rel_y))

    def _click(self, rel_y):
        self._click_job = None
        if self.sleeping:
            self.wake()
            return
        if rel_y < 0.52:      # голова — погладили
            self.state.purr = 1.0
            self.set_mood(random.choice(["happy", "love"]), 3.5)
            self.say(persona.line("pat"), speak=random.random() < 0.5, seconds=3)
        else:                 # тело/хвост — тыкнули
            self.set_mood(random.choice(["annoyed", "surprised"]), 2.5)
            self.say(persona.line("poke"), speak=random.random() < 0.5, seconds=3)

    def _double(self, e):
        if self._click_job:
            self.win.after_cancel(self._click_job)
            self._click_job = None
        self.set_mood("surprised", 6)
        self.say("Слушаю!", speak=False, seconds=2)
        self.app.voice.listen_once()

    def _menu(self, e):
        m = tk.Menu(self.win, tearoff=0, bg="#151926", fg="#E6E8EF", activebackground="#7C5CFF",
                    activeforeground="white", bd=0, font=("Segoe UI", 10))
        m.add_command(label="🎙  Сказать команду", command=self.app.voice.listen_once)
        m.add_command(label="⌨  Написать…", command=self._ask_text)
        m.add_command(label="💬  Скажи что-нибудь", command=lambda: self.initiate("idle", force=True))
        m.add_separator()
        m.add_command(label="☀  Проснуться" if self.sleeping else "🌙  Поспать",
                      command=self.wake if self.sleeping else self.sleep)
        m.add_command(label="⚡  Переместиться", command=self.roam)
        m.add_command(label="🏠  Домой", command=self.go_home)
        m.add_separator()
        m.add_command(label="Открыть VoxPC", command=lambda: self.app.events.put(("show", None)))
        m.add_command(label="Спрятать Глитч", command=lambda: self.app.set_companion(False))
        m.tk_popup(e.x_root, e.y_root)

    def _ask_text(self):
        import customtkinter as ctk
        text = ctk.CTkInputDialog(text="Что сделать?", title=persona.NAME).get_input()
        if text and text.strip():
            self.app.run_command(text.strip(), "text")

    # ------------------------------------------------------------ сон и перемещения
    def sleep(self):
        self.sleeping = True
        self.state.pose = "sleep"
        self.state.mood = "sleep"
        self.say(persona.line("sleep"), speak=False, seconds=3)

    def wake(self, quiet=False):
        if not self.sleeping:
            return
        self.sleeping = False
        self.state.pose = "sit"
        self.state.mood = "neutral"
        if not quiet:
            self.set_mood("annoyed", 3)
            self.say(persona.line("wake"), speak=random.random() < 0.6, seconds=3)

    def go_home(self):
        self.perch_hwnd = None
        self.teleport(*self._home())
        self.cfg.set("companion_pos", None)

    def teleport(self, x, y):
        self._teleport = {"start": time.time(), "target": (int(x), int(y)), "moved": False}

    def _teleport_step(self, now):
        tp = self._teleport
        p = (now - tp["start"]) / 0.55
        if p < 0.5:
            self.state.glitch = p * 2
        else:
            if not tp["moved"]:
                tp["moved"] = True
                self.x, self.y = tp["target"]
                self._place()
            self.state.glitch = max(0.0, 2 - p * 2)
        if p >= 1:
            self.state.glitch = 0
            self._teleport = None

    def roam(self):
        fg = obs.foreground()
        l, t, r, b = work_area(self.root)
        if fg and not fg["fullscreen"] and random.random() < 0.6:
            wl, wt, wr, wb = fg["rect"]
            if wr - wl > self.w + 80 and wt - self.h * 0.9 > t - self.h * 0.2:
                self.perch_hwnd = fg["hwnd"]
                x = random.randint(wl + 30, wr - self.w - 30)
                self._perch_dx = x - wl
                self.teleport(x, wt - int(self.h * 0.94))
                self._maybe_teleport_line()
                return
        self.perch_hwnd = None
        x = random.randint(l + 20, max(l + 21, r - self.w - 20))
        self.teleport(x, b - int(self.h * 0.97))
        self._maybe_teleport_line()

    def _maybe_teleport_line(self):
        if random.random() < 0.25:
            self.win.after(700, lambda: self.say(persona.line("teleport"), speak=False, seconds=2))

    def _follow_perch(self):
        rect = window_rect(self.perch_hwnd)
        if not rect:
            self.perch_hwnd = None
            self.go_home()
            return
        x = rect[0] + getattr(self, "_perch_dx", 40)
        y = rect[1] - int(self.h * 0.94)
        if (x, y) != (self.x, self.y) and not self._teleport:
            self.x, self.y = x, y
            self.win.geometry(f"+{self.x}+{self.y}")

    def set_hidden(self, hidden):
        if hidden == self.hidden:
            return
        self.hidden = hidden
        if hidden:
            self.win.withdraw()
            self.bubble.hide()
        else:
            self.win.deiconify()
            self.win.attributes("-topmost", True)

    def destroy(self):
        for w in (self.bubble.win, self.win):
            try:
                w.destroy()
            except tk.TclError:
                pass

    # ------------------------------------------------------------ наблюдение и инициатива
    def on_observer(self, kind, snap):
        """Вызывается в главном потоке по событиям Observer."""
        if self.cfg.get("companion_hide_fullscreen"):
            proc = (snap.get("process") or "").lower()
            self.set_hidden(bool(snap.get("fullscreen")) and proc not in ("voxpc.exe",))
        idle = snap.get("idle_seconds", 0)
        if idle > 900 and not self.sleeping and not self.speaking:
            self.sleep()
        if kind == "return":
            if self.sleeping:
                self.wake(quiet=True)
            self.initiate("return")
        elif kind == "switch":
            self._pending_game = (time.time() + random.uniform(20, 40), snap.get("process"))
        elif kind == "tick":
            pg = self._pending_game
            if pg and time.time() > pg[0]:
                self._pending_game = None
                if (snap.get("process") or "") == pg[1]:
                    self.initiate("game" if persona.is_game(pg[1], snap.get("title")) else "app")
            elif time.time() > self._next_comment:
                self.initiate("spontaneous")

    def _mode(self):
        return MODES.get(self.cfg.get("companion_comments") or "rare")

    def _allowed(self, force=False):
        mode = self._mode()
        if not mode:
            return force
        if force:
            return True
        min_gap, per_hour = mode
        now = time.time()
        self.comment_times = [t for t in self.comment_times if now - t < 3600]
        if len(self.comment_times) >= per_hour:
            return False
        if self.comment_times and now - self.comment_times[-1] < min_gap:
            return False
        hour = time.localtime().tm_hour
        if self.cfg.get("companion_quiet") and (hour >= 23 or hour < 9):
            return False
        if self.hidden or self.sleeping or self.speaking or self._generating or self.app.busy:
            return False
        proc = (self.app.observer.snapshot().get("process") or "").lower()
        if any(q in proc for q in obs.QUIET_APPS):
            return False
        return True

    def initiate(self, kind, force=False):
        mode = self._mode()
        if kind == "spontaneous" and mode:
            self._next_comment = time.time() + mode[0] * random.uniform(1.0, 1.2)
        if not self._allowed(force):
            return
        self._generating = True
        snap = self.app.observer.snapshot()
        shot_allowed = bool(self.cfg.get("companion_screens"))

        def work():
            text = None
            try:
                if self.app.brain.installed and self.cfg.get("brain_enabled"):
                    shot = None
                    if shot_allowed and kind in ("game", "app", "spontaneous", "idle"):
                        try:
                            shot = actions.screenshot_jpeg(1280)
                        except Exception:
                            shot = None
                    text = self.app.brain.comment(self._context(kind, snap), shot)
                    if text is None and kind == "return":
                        text = persona.line("return")
                else:
                    text = self._canned(kind, snap)
                if not text and force:
                    text = persona.line("idle")
            finally:
                self._generating = False
            if text:
                self.app.events.put(("companion_say", text))

        threading.Thread(target=work, daemon=True).start()

    def delivered(self):
        self.comment_times.append(time.time())

    def _canned(self, kind, snap):
        title = (snap.get("title") or "").split(" - ")[0].split(" — ")[0].strip()
        app_name = title if 0 < len(title) <= 32 else (os.path.splitext(snap.get("process") or "")[0] or "это")
        hour = time.localtime().tm_hour
        if kind == "return":
            return persona.line("return")
        if kind in ("game", "app"):
            return persona.line(kind, app=app_name)
        if hour >= 1 and hour < 5:
            return persona.line("late")
        if snap.get("session_minutes", 0) > 120 and random.random() < 0.5:
            return persona.line("long_session")
        return persona.line("idle") if random.random() < 0.6 else None

    def _context(self, kind, snap):
        events = {
            "return": "Пользователь только что вернулся к компьютеру после перерыва.",
            "game": "Пользователь только что запустил игру и играет в неё.",
            "app": "Пользователь переключился на другое приложение.",
            "spontaneous": "Ничего особенного не произошло — просто захотелось что-то сказать.",
            "idle": "Пользователь попросил тебя что-нибудь сказать.",
        }
        recent = " | ".join(self.recent_lines[-4:]) or "—"
        return (f"Время: {snap.get('time')}. Активное окно: {snap.get('process')} — «{snap.get('title')}» "
                f"(уже {snap.get('app_minutes')} мин). За компьютером без перерыва: {snap.get('session_minutes')} мин. "
                f"Событие: {events.get(kind, kind)} Твои последние реплики: {recent}")
