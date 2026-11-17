"""Публикация текущего адреса туннеля, чтобы телефон нашёл ПК вне дома.

Адрес отправляется в ntfy.sh под секретным именем канала (из секрета VoxPC). Сам адрес без кода
доступа бесполезен: все команды требуют код, а неверные попытки ограничены.
"""
import hashlib
import threading
import time
import urllib.request

NTFY = "https://ntfy.sh"


def remote_id(config) -> str:
    secret = str(config.get("mcp_secret") or "")
    return "voxpc-" + hashlib.sha256(("remote:" + secret).encode()).hexdigest()[:24]


class Relay:
    def __init__(self, config):
        self.config = config
        self.url = ""
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def publish(self, url: str):
        self.url = url or ""
        threading.Thread(target=self._send, daemon=True).start()

    def _send(self):
        if not self.url or not self.config.get("remote_api"):
            return
        try:
            req = urllib.request.Request(f"{NTFY}/{remote_id(self.config)}", data=self.url.encode(),
                                         method="POST", headers={"Title": "VoxPC", "Cache": "yes"})
            urllib.request.urlopen(req, timeout=15).read()
        except Exception:
            pass

    def _loop(self):
        while not self._stop.wait(6 * 3600):  # ntfy хранит сообщения ~12 ч — обновляем заранее
            self._send()

    def stop(self):
        self._stop.set()
