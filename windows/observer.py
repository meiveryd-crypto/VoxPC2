"""Наблюдение за ПК для реплик компаньона: активное окно, простой пользователя, полный экран."""
import ctypes
import datetime
import os
import threading
import time

IS_WIN = os.name == "nt"

if IS_WIN:
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def foreground():
    """{'hwnd','process','title','rect','fullscreen'} или None."""
    if not IS_WIN:
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        size = wintypes.DWORD(1024)
        pbuf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            process = os.path.basename(pbuf.value)
        kernel32.CloseHandle(h)
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    full = r.left <= 0 and r.top <= 0 and r.right >= sw and r.bottom >= sh
    return {"hwnd": hwnd, "process": process, "title": buf.value,
            "rect": (r.left, r.top, r.right, r.bottom), "fullscreen": full}


def idle_seconds() -> float:
    if not IS_WIN:
        return 0.0
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (kernel32.GetTickCount() - info.dwTime) / 1000.0


def cursor_pos():
    if not IS_WIN:
        return (0, 0)
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


IGNORED = {"voxpc.exe", "python.exe", "pythonw.exe", "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
           "startmenuexperiencehost.exe", "lockapp.exe", "applicationframehost.exe", "textinputhost.exe"}
QUIET_APPS = ("discord", "teams", "zoom", "obs64", "obs32", "powerpnt", "skype", "telegram")


class Observer:
    """Каждые 2 с проверяет активное окно и простой; сообщает события через on_event(kind, info).

    kind: switch (сменилось приложение), return (вернулся после простоя), tick (обычная проверка).
    """

    def __init__(self, on_event):
        self.on_event = on_event
        self.current = None
        self.app_since = time.time()
        self.session_start = time.time()
        self.away = False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        fg = self.current or {}
        return {
            "process": fg.get("process", ""),
            "title": fg.get("title", ""),
            "fullscreen": fg.get("fullscreen", False),
            "app_minutes": int((time.time() - self.app_since) / 60),
            "session_minutes": int((time.time() - self.session_start) / 60),
            "idle_seconds": int(idle_seconds()),
            "time": datetime.datetime.now().strftime("%H:%M"),
        }

    def _loop(self):
        while not self._stop.is_set():
            try:
                idle = idle_seconds()
                if idle > 300:
                    self.away = True
                elif self.away and idle < 5:
                    self.away = False
                    self.session_start = time.time()
                    self.on_event("return", self.snapshot())
                fg = foreground()
                if fg and fg["process"].lower() not in IGNORED and fg["title"]:
                    prev = self.current
                    if not prev or prev["process"].lower() != fg["process"].lower():
                        self.current = fg
                        self.app_since = time.time()
                        if prev:
                            self.on_event("switch", self.snapshot())
                    else:
                        self.current = fg
                self.on_event("tick", self.snapshot())
            except Exception:
                pass
            self._stop.wait(2.0)
