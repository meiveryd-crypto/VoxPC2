"""Поиск установленных программ по ярлыкам меню «Пуск» и рабочего стола."""
import difflib
import os
import re
import time
from pathlib import Path

_EXT = {".lnk", ".url", ".appref-ms"}
_SKIP = re.compile(r"uninstall|удал|readme|help|справк|documentation|license|лиценз|website|сайт", re.I)
_cache = {"t": 0.0, "items": []}

_TR = dict(zip("абвгдеёзийклмнопрстуфхцы", ["a", "b", "v", "g", "d", "e", "e", "z", "i", "i", "k", "l", "m", "n",
                                             "o", "p", "r", "s", "t", "u", "f", "h", "c", "y"]))
_TR.update({"ж": "zh", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ь": "", "э": "e", "ю": "yu", "я": "ya"})


def translit(s: str) -> str:
    return "".join(_TR.get(ch, ch) for ch in s.lower())


def _norm(s: str) -> str:
    s = translit(s.lower().replace("ё", "е"))
    s = s.replace("ph", "f").replace("w", "v").replace("x", "ks").replace("ck", "k")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _dirs():
    env = os.environ
    return [
        Path(env.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(env.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path.home() / "Desktop",
        Path(env.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]


def all_programs():
    if time.time() - _cache["t"] < 60 and _cache["items"]:
        return _cache["items"]
    items, seen = [], set()
    for d in _dirs():
        if not d.is_dir():
            continue
        for root, _, files in os.walk(d):
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() not in _EXT or _SKIP.search(p.stem):
                    continue
                key = p.stem.lower()
                if key in seen:
                    continue
                seen.add(key)
                items.append({"name": p.stem, "path": str(p)})
    _cache.update(t=time.time(), items=items)
    return items


def find(query: str, limit: int = 5, min_score: float = 0.62):
    q = _norm(query)
    if not q:
        return []
    scored = []
    for item in all_programs():
        n = _norm(item["name"])
        if not n:
            continue
        if q == n:
            score = 1.0
        elif re.search(rf"\b{re.escape(q)}\b", n):
            score = 0.95 - min(0.2, (len(n) - len(q)) / 100)
        else:
            score = max([difflib.SequenceMatcher(None, q, n).ratio()] +
                        [difflib.SequenceMatcher(None, q, w).ratio() for w in n.split()])
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [dict(item, score=round(s, 2)) for s, item in scored[:limit]]
