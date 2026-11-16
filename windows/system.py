"""Автозапуск с Windows, значок в трее, настройка Wake-on-LAN."""
import os
import sys

from config import APP_NAME, data_dir, resource_path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------- автозапуск ----------
def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{pyw}" "{main}" --minimized'


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------- Wake-on-LAN ----------
def run_wol_setup():
    """Запускает setup_wol.ps1 с правами администратора."""
    import ctypes
    script = resource_path("setup_wol.ps1")
    args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 1)


def open_data_dir():
    os.startfile(str(data_dir()))


# ---------- иконка ----------
try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def make_icon_image(size: int = 256):
    if Image is None:
        return None
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, s - 1, s - 1), fill=(124, 92, 255, 255))
    d.ellipse((s * .08, s * .08, s * .92, s * .92), fill=(108, 74, 245, 255))
    w = max(2, s // 14)
    d.rounded_rectangle((s * .39, s * .2, s * .61, s * .56), radius=s * .11, fill="white")
    d.arc((s * .28, s * .32, s * .72, s * .68), 0, 180, fill="white", width=w)
    d.line((s * .5, s * .68, s * .5, s * .78), fill="white", width=w)
    d.line((s * .38, s * .78, s * .62, s * .78), fill="white", width=w)
    return img


def save_ico(path: str) -> bool:
    img = make_icon_image(256)
    if img is None:
        return False
    img.save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return True


# ---------- трей ----------
try:
    import pystray
except ImportError:  # pragma: no cover
    pystray = None


class Tray:
    def __init__(self, on_show, on_quit):
        self.icon = None
        if pystray is None or Image is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Открыть VoxPC", lambda icon, item: on_show(), default=True),
            pystray.MenuItem("Выход", lambda icon, item: on_quit()),
        )
        self.icon = pystray.Icon(APP_NAME, make_icon_image(64), "VoxPC — голосовое управление ПК", menu)
        self.icon.run_detached()

    @property
    def available(self) -> bool:
        return self.icon is not None

    def notify(self, text: str):
        try:
            if self.icon:
                self.icon.notify(text, APP_NAME)
        except Exception:
            pass

    def stop(self):
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
