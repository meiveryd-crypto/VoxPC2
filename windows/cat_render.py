"""Процедурная отрисовка Глитч — чёрной кибер-кошки-подростка (оригинальный персонаж VoxPC).

Кадр рисуется с 3-кратным сглаживанием на фоне цвета-ключа (KEY), который окно делает прозрачным.
"""
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

KEY = (1, 2, 3)                 # прозрачный цвет окна
W, H = 200, 230                 # логический размер кадра
SS = 3                          # сглаживание

FUR = (20, 20, 27)
FUR_HI = (36, 36, 48)
FUR_LO = (11, 11, 15)
INNER_EAR = (70, 36, 54)
EYE_A = (255, 214, 64)
EYE_B = (255, 138, 22)
NEON = (34, 211, 238)
NEON_SOFT = (20, 120, 140)
METAL = (150, 156, 170)
NOSE = (96, 52, 66)
MOUTH = (120, 28, 44)
WHISKER = (120, 124, 138)


class CatState:
    """Параметры кадра. Значения 0..1, если не сказано иное."""

    def __init__(self):
        self.t = 0.0            # время, сек
        self.blink = 0.0        # 1 — глаза закрыты
        self.mouth = 0.0        # открытость рта (речь)
        self.mood = "neutral"   # neutral | happy | annoyed | surprised | sleep | love | smug
        self.pose = "sit"       # sit | sleep
        self.look = (0.0, 0.0)  # направление взгляда −1..1
        self.ear_twitch = 0.0
        self.glitch = 0.0       # эффект телепорта
        self.purr = 0.0         # дрожание при мурлыкании


def _bezier(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        u = i / n
        a = (1 - u) ** 3
        b = 3 * u * (1 - u) ** 2
        c = 3 * u * u * (1 - u)
        d = u ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _thick_curve(draw, pts, w0, w1, color):
    """Рисует кривую переменной толщины кружками (хвост)."""
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        r = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


class CatRenderer:
    def __init__(self, scale: float = 1.0):
        self.scale = scale

    @property
    def size(self):
        return int(W * self.scale), int(H * self.scale)

    def render(self, s: CatState) -> Image.Image:
        k = SS * self.scale
        img = Image.new("RGB", (int(W * k), int(H * k)), KEY)
        d = ImageDraw.Draw(img)

        def P(x, y):
            return x * k, y * k

        def E(cx, cy, rx, ry, **kw):
            d.ellipse((P(cx - rx, cy - ry)) + P(cx + rx, cy + ry), **kw)

        def poly(points, **kw):
            d.polygon([P(x, y) for x, y in points], **kw)

        def line(points, width, **kw):
            d.line([P(x, y) for x, y in points], width=max(1, int(width * k)), **kw)

        breathe = math.sin(s.t * 2.2) * 1.4
        jitter = math.sin(s.t * 60) * 0.5 * s.purr

        if s.pose == "sleep":
            self._sleep_pose(s, P, E, poly, line, d, k, breathe)
        else:
            self._sit_pose(s, P, E, poly, line, d, k, breathe, jitter)

        img = img.resize(self.size, Image.LANCZOS)
        img = self._rim(img)
        if s.glitch > 0:
            img = self._glitch(img, s.glitch)
        return img

    # ------------------------------------------------------------------ сидит
    def _sit_pose(self, s, P, E, poly, line, d, k, breathe, jitter):
        # хвост (позади тела)
        sway = math.sin(s.t * 1.3) * 14 + math.sin(s.t * 3.1) * 3
        base = (128, 200)
        pts = _bezier(base, (172, 205), (182 + sway * 0.3, 160), (168 + sway, 112 + abs(sway) * 0.3))
        tw = [k * v for v in (15, 8)]
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            r = (tw[0] + (tw[1] - tw[0]) * i / (n - 1)) / 2
            d.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=FUR)
        tip = pts[-3]
        E(tip[0], tip[1], 5.5, 5.5, outline=NEON, width=max(1, int(1.6 * k)))  # кибер-кольцо на хвосте

        # тело
        by = 160 - breathe * 0.5
        E(100 + jitter, by, 41, 53 + breathe * 0.4, fill=FUR)
        # пушистая грудка
        cx = 100 + jitter
        poly([(cx - 16, by - 34), (cx - 10, by - 24), (cx - 6, by - 31), (cx - 1, by - 20), (cx + 4, by - 30),
              (cx + 9, by - 22), (cx + 15, by - 33), (cx + 12, by - 12), (cx, by - 4), (cx - 12, by - 12)],
             fill=(28, 28, 38))
        # лапки
        for x in (82, 118):
            E(x + jitter, 206, 13, 9, fill=FUR)
            E(x + jitter, 204, 10, 5, fill=FUR_HI)
            for dx in (-5, 0, 5):
                line([(x + dx + jitter, 207), (x + dx + jitter, 212)], 0.8, fill=FUR_LO)
        # ошейник с LED
        cy = 122 - breathe * 0.3
        d.arc((P(66, cy - 14) + P(134, cy + 14)), 15, 165, fill=(46, 48, 60), width=int(5 * k))
        glow = 0.6 + 0.4 * math.sin(s.t * 3)
        led = tuple(int(c * glow + n * (1 - glow)) for c, n in zip(NEON, NEON_SOFT))
        E(100, cy + 13, 3.2, 3.2, fill=led)

        self._head(s, P, E, poly, line, d, k, 100 + jitter, 86 + breathe * 0.6)

    # ------------------------------------------------------------------ голова
    def _head(self, s, P, E, poly, line, d, k, hx, hy):
        tw = s.ear_twitch
        # уши
        left = [(hx - 46, hy - 8), (hx - 36, hy - 66), (hx - 8, hy - 36)]
        right = [(hx + 46, hy - 8), (hx + 36 + tw * 8, hy - 66 + tw * 10), (hx + 8, hy - 36)]
        poly(left, fill=FUR)
        poly(right, fill=FUR)
        poly([(hx - 40, hy - 14), (hx - 35, hy - 54), (hx - 16, hy - 34)], fill=INNER_EAR)
        poly([(hx + 40, hy - 14), (hx + 35 + tw * 7, hy - 54 + tw * 9), (hx + 16, hy - 34)], fill=INNER_EAR)
        # кибер-имплант на левом ухе: неоновая линия и два кольца
        line([(hx - 44, hy - 14), (hx - 37, hy - 58)], 1.4, fill=NEON)
        for yy in (hy - 40, hy - 30):
            E(hx - 43.5 + (hy - yy) * 0.02, yy, 2.6, 2.6, outline=METAL, width=max(1, int(1.1 * k)))

        # голова (широкие щёки)
        E(hx, hy, 50, 43, fill=FUR)
        E(hx, hy - 8, 42, 36, fill=FUR)
        # чёлка-пучок
        poly([(hx - 10, hy - 40), (hx - 2, hy - 50), (hx + 2, hy - 41), (hx + 9, hy - 49), (hx + 10, hy - 38)],
             fill=FUR)

        # кибер-схема на правой щеке
        line([(hx + 26, hy + 8), (hx + 36, hy + 8), (hx + 41, hy + 14)], 1.1, fill=NEON_SOFT)
        E(hx + 42, hy + 15, 1.8, 1.8, fill=NEON)

        self._eyes(s, P, E, poly, line, d, k, hx, hy)

        # нос и рот
        ny = hy + 14
        poly([(hx - 5, ny - 3), (hx + 5, ny - 3), (hx, ny + 3)], fill=NOSE)
        if s.mouth > 0.08 or s.mood == "surprised":
            m = max(s.mouth, 0.5 if s.mood == "surprised" else 0)
            E(hx, ny + 10 + m * 3, 6 + m * 2, 3 + m * 7, fill=MOUTH)
            poly([(hx - 4, ny + 6), (hx - 2, ny + 6), (hx - 3, ny + 10)], fill=(230, 230, 236))  # клычок
        else:
            if s.mood in ("happy", "love", "smug"):
                d.arc(P(hx - 10, ny - 2) + P(hx, ny + 8), 20, 160, fill=FUR_HI, width=int(1.6 * k))
                d.arc(P(hx, ny - 2) + P(hx + 10, ny + 8), 20, 160, fill=FUR_HI, width=int(1.6 * k))
            elif s.mood == "annoyed":
                line([(hx - 6, ny + 8), (hx + 6, ny + 7)], 1.4, fill=FUR_HI)
            else:
                d.arc(P(hx - 8, ny) + P(hx, ny + 7), 10, 170, fill=FUR_HI, width=int(1.4 * k))
                d.arc(P(hx, ny) + P(hx + 8, ny + 7), 10, 170, fill=FUR_HI, width=int(1.4 * k))
        # усы
        for i, dy in enumerate((-2, 3, 8)):
            line([(hx - 18, ny + dy), (hx - 52, ny + dy - 6 + i * 5)], 0.8, fill=WHISKER)
            line([(hx + 18, ny + dy), (hx + 52, ny + dy - 6 + i * 5)], 0.8, fill=WHISKER)
        if s.mood == "love":
            for sx in (-1, 1):
                E(hx + sx * 30, hy + 12, 7, 3.5, fill=(110, 40, 70))

    def _eyes(self, s, P, E, poly, line, d, k, hx, hy):
        lx, ly = s.look
        for side in (-1, 1):
            ex, ey = hx + side * 20, hy + 1
            mood = s.mood
            closed = s.blink > 0.85 or mood == "sleep"
            if mood in ("happy", "love") and s.blink < 0.5:
                # глаза-дуги ^ ^
                d.arc(P(ex - 11, ey - 4) + P(ex + 11, ey + 12), 200, 340, fill=EYE_B, width=int(2.6 * k))
                continue
            if closed:
                d.arc(P(ex - 11, ey - 6) + P(ex + 11, ey + 6), 20, 160, fill=EYE_B, width=int(2 * k))
                continue
            ry = 11.5 * (1 - s.blink)
            rx = 13
            if mood == "surprised":
                rx, ry = 14, 13
            # свечение
            E(ex, ey, rx + 3, ry + 3, fill=(60, 40, 10))
            E(ex, ey, rx, ry, fill=EYE_B)
            E(ex, ey - ry * 0.25, rx * 0.86, ry * 0.7, fill=EYE_A)
            # зрачок
            px, py = ex + lx * 4.5, ey + ly * 3
            if mood == "surprised":
                E(px, py, 6, 6.5, fill=(8, 6, 4))
            else:
                E(px, py, 2.6, max(1, ry * 0.85), fill=(8, 6, 4))
            E(px + 3.5, py - ry * 0.4, 2.2, 2.2, fill=(255, 250, 230))  # блик
            # веко
            if mood == "annoyed":
                poly([(ex - rx - 2, ey - ry - 2), (ex + rx + 2, ey - ry - 2),
                      (ex + rx + 2, ey - ry * 0.15 + side * 2.5), (ex - rx - 2, ey - ry * 0.15 - side * 2.5)],
                     fill=FUR)
            elif mood == "smug":
                poly([(ex - rx - 2, ey - ry - 2), (ex + rx + 2, ey - ry - 2),
                      (ex + rx + 2, ey - ry * 0.35), (ex - rx - 2, ey - ry * 0.35)], fill=FUR)

    # ------------------------------------------------------------------ спит
    def _sleep_pose(self, s, P, E, poly, line, d, k, breathe):
        cy = 190
        # хвост вокруг
        pts = _bezier((150, 195), (190, 210), (120, 226), (52, 214))
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            r = k * (14 - 6 * i / n) / 2
            d.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=FUR)
        E(100, cy, 62, 30 + breathe * 0.7, fill=FUR)
        E(100, cy - 4, 52, 20 + breathe * 0.5, fill=FUR_HI)
        E(100, cy - 2, 48, 18, fill=FUR)
        # голова лежит
        hx, hy = 64, cy - 14
        poly([(hx - 30, hy - 4), (hx - 26, hy - 40), (hx - 6, hy - 22)], fill=FUR)
        poly([(hx + 28, hy - 6), (hx + 26, hy - 42), (hx + 6, hy - 24)], fill=FUR)
        poly([(hx - 26, hy - 8), (hx - 24, hy - 32), (hx - 12, hy - 20)], fill=INNER_EAR)
        line([(hx - 29, hy - 6), (hx - 25, hy - 36)], 1.3, fill=NEON)
        E(hx, hy, 34, 26, fill=FUR)
        for side in (-1, 1):
            d.arc(P(hx + side * 13 - 8, hy - 4) + P(hx + side * 13 + 8, hy + 6), 20, 160, fill=EYE_B,
                  width=int(1.8 * k))
        poly([(hx - 3, hy + 8), (hx + 3, hy + 8), (hx, hy + 12)], fill=NOSE)
        glow = 0.5 + 0.5 * math.sin(s.t * 1.5)
        E(hx + 30, hy + 18, 2.6, 2.6, fill=tuple(int(c * glow) for c in NEON))

    @staticmethod
    def _rim(img):
        """Тонкий светлый контур, чтобы чёрная кошка была видна на тёмном фоне."""
        key = Image.new("RGB", img.size, KEY)
        diff = ImageChops.difference(img, key).convert("L").point(lambda v: 255 if v > 6 else 0)
        grown = diff.filter(ImageFilter.MaxFilter(3))
        rim = ImageChops.subtract(grown, diff)
        out = img.copy()
        out.paste((64, 70, 96), mask=rim)
        return out

    # ------------------------------------------------------------------ сбой
    @staticmethod
    def _glitch(img, amount):
        w, h = img.size
        out = img.copy()
        rnd = random.Random(int(amount * 1000))
        for _ in range(int(3 + amount * 10)):
            y = rnd.randrange(0, h)
            hh = rnd.randrange(2, max(3, int(h * 0.08)))
            dx = int((rnd.random() - 0.5) * w * 0.35 * amount)
            band = img.crop((0, y, w, min(h, y + hh)))
            out.paste(KEY, (0, y, w, min(h, y + hh)))
            out.paste(band, (dx, y))
        if amount > 0.3:
            r, g, b = out.split()
            r = ImageChops.offset(r, int(4 * amount), 0)
            b = ImageChops.offset(b, -int(4 * amount), 0)
            out = Image.merge("RGB", (r, g, b))
        return out
