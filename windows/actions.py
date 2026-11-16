"""Низкоуровневые действия Windows: запуск программ, питание, звук, медиа."""
import os
import subprocess
import time
import urllib.parse
import webbrowser

IS_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LWIN = 0x5B
VK_D = 0x44
KEYEVENTF_KEYUP = 0x0002


def _run(cmd: str):
    subprocess.Popen(cmd, shell=True, creationflags=CREATE_NO_WINDOW)


def press_key(vk: int, times: int = 1):
    if not IS_WIN:
        return
    import ctypes
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.015)


def hotkey(*vks: int):
    if not IS_WIN:
        return
    import ctypes
    user32 = ctypes.windll.user32
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


# ---------- программы ----------
def launch(target: str):
    """Запускает .exe, ярлык, URL или URI (steam://, discord://, ms-settings:)."""
    t = os.path.expandvars(target.strip())
    if not t:
        raise ValueError("Не указан путь к программе")
    is_uri = "://" in t or (t.endswith(":") and len(t) > 2)
    if is_uri:
        if IS_WIN:
            os.startfile(t)
        else:
            webbrowser.open(t)
        return
    if t.startswith('"') or " --" in t or " /" in t:
        # команда с аргументами
        subprocess.Popen(t, shell=True, creationflags=CREATE_NO_WINDOW)
        return
    if IS_WIN:
        try:
            os.startfile(t)
        except OSError:
            _run(f'start "" "{t}"')
    else:
        subprocess.Popen([t])


def kill(process: str):
    if process:
        _run(f'taskkill /IM "{process}" /F')


# ---------- питание ----------
def shutdown(delay: int = 5):
    _run(f"shutdown /s /t {delay}")


def restart(delay: int = 5):
    _run(f"shutdown /r /t {delay}")


def cancel_shutdown():
    _run("shutdown /a")


def sleep():
    # Если включена гибернация, Windows может уйти в неё вместо сна
    _run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")


def hibernate():
    _run("shutdown /h")


def lock():
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.LockWorkStation()


# ---------- звук и медиа ----------
def volume_up(steps: int = 5):
    press_key(VK_VOLUME_UP, steps)


def volume_down(steps: int = 5):
    press_key(VK_VOLUME_DOWN, steps)


def mute():
    press_key(VK_VOLUME_MUTE)


def set_volume(percent: int):
    percent = max(0, min(100, percent))
    press_key(VK_VOLUME_DOWN, 50)          # в ноль (1 шаг = 2%)
    press_key(VK_VOLUME_UP, round(percent / 2))


def play_pause():
    press_key(VK_MEDIA_PLAY_PAUSE)


def next_track():
    press_key(VK_MEDIA_NEXT)


def prev_track():
    press_key(VK_MEDIA_PREV)


def show_desktop():
    hotkey(VK_LWIN, VK_D)


# ---------- интернет ----------
def web_search(query: str):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))


def youtube_search(query: str):
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))


def open_url(url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
