"""Ключевые слова: несколько вариантов через запятую и нечёткое совпадение с распознанной речью."""
import difflib
import re


def norm(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"[^\w\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def words(setting: str):
    """«vox, вокс, вок» -> ['vox', 'вокс', 'вок'] (самые длинные первыми)."""
    items = [norm(w) for w in re.split(r"[,;/|]+", setting or "")]
    return sorted({w for w in items if w}, key=len, reverse=True)


def _similar(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 3:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def split(text: str, setting: str):
    """Возвращает (найдено ли ключевое слово, остаток фразы без него).

    Ключевое слово ищется в начале фразы (первые одно-два слова) с допуском на ошибки распознавания:
    «Вокс, открой стим», «фокс открой стим», «эй вокс открой стим».
    """
    t = norm(text)
    ws = words(setting)
    if not t or not ws:
        return False, t
    toks = t.split()
    for w in ws:
        wt = w.split()
        n = len(wt)
        for start in (0, 1):                     # допускаем «эй/ну/слушай» перед словом
            chunk = toks[start:start + n]
            if len(chunk) == n and _similar(" ".join(chunk), w):
                return True, " ".join(toks[start + n:])
    return False, t
