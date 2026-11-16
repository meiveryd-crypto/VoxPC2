"""Сетевые данные ПК: IP и MAC-адрес (нужен телефону для Wake-on-LAN)."""
import re
import socket
import subprocess
import uuid

from actions import CREATE_NO_WINDOW, IS_WIN

_mac_cache = {}


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # пакет не отправляется, только выбирается интерфейс
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def hostname() -> str:
    return socket.gethostname()


def mac_address(ip: str = None) -> str:
    ip = ip or local_ip()
    if ip in _mac_cache:
        return _mac_cache[ip]
    mac = ""
    if IS_WIN:
        ps = ("(Get-NetAdapter -InterfaceIndex "
              f"(Get-NetIPAddress -IPAddress '{ip}' -ErrorAction Stop).InterfaceIndex).MacAddress")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                                 text=True, timeout=10, creationflags=CREATE_NO_WINDOW).stdout.strip()
            if re.fullmatch(r"([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}", out):
                mac = out.replace("-", ":").upper()
        except Exception:
            pass
    if not mac:
        n = uuid.getnode()
        mac = ":".join(f"{(n >> s) & 0xFF:02X}" for s in range(40, -1, -8))
    _mac_cache[ip] = mac
    return mac
