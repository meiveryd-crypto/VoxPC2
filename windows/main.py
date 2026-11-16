"""VoxPC — голосовое управление ПК. Точка входа."""
import os
import sys

_mutex = None


def already_running() -> bool:
    global _mutex
    if os.name != "nt":
        return False
    import ctypes
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "VoxPC_SingleInstance_Mutex")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    if already_running():
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "VoxPC уже запущен — ищите значок в трее.", "VoxPC", 0x40)
        return

    from config import Config
    from gui import App

    cfg = Config()
    minimized = "--minimized" in sys.argv or bool(cfg.get("start_minimized"))
    App(cfg, minimized=minimized).mainloop()


if __name__ == "__main__":
    main()
