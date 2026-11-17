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

    Ключевое слово ищется в любом месте фразы с допуском на ошибки распознавания: при фоновом шуме
    (игра, музыка) запись режется на куски, и слово часто оказывается в середине.
    «Вокс, открой стим», «фокс открой стим», «…и тут вокс громче» -> команда после ключевого слова.
    """
    t = norm(text)
    ws = words(setting)
    if not t or not ws:
        return False, t
    toks = t.split()
    best = None
    for w in ws:
        n = len(w.split())
        for start in range(0, len(toks) - n + 1):
            if _similar(" ".join(toks[start:start + n]), w):
                if best is None or start < best[0]:
                    best = (start, n)
                break
    if best is None:
        return False, t
    start, n = best
    return True, " ".join(toks[start + n:])
