#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Genera l'icona dell'app candy_app: oblò stilizzato con bolle.
Salva un PNG 1024x1024 da usare come sorgente per flutter_launcher_icons."""

import math
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# --- Sfondo: gradiente radiale navy -> nero ---
bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
dbg = ImageDraw.Draw(bg)
cx = cy = SIZE // 2
for r in range(SIZE // 2, 0, -1):
    # interpolazione tra #0f172a (centro) e #020617 (bordo)
    t = 1 - (r / (SIZE / 2))
    col = (
        int(15 + (2 - 15) * (1 - t)),
        int(23 + (6 - 23) * (1 - t)),
        int(42 + (23 - 42) * (1 - t)),
        255,
    )
    dbg.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
img = Image.alpha_composite(img, bg)
d = ImageDraw.Draw(img)

# --- Cornice cromata (anello esterno) ---
door_r = 360
ring_outer = door_r + 40
# gradiente cromato
for i in range(ring_outer, door_r, -1):
    t = (ring_outer - i) / (ring_outer - door_r)
    col = (
        int(148 + (30 - 148) * t),
        int(163 + (41 - 163) * t),
        int(184 + (59 - 184) * t),
    )
    d.ellipse([cx - i, cy - i, cx + i, cy + i], outline=col + (255,), width=1)

# --- Vetro scuro (interno oblò) ---
d.ellipse([cx - door_r, cy - door_r, cx + door_r, cy + door_r], fill=(8, 15, 30, 255))

# --- Acqua sul fondo (azzurra, semi-trasparente) ---
water_level = cy + door_r * 0.30
water_img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
wd = ImageDraw.Draw(water_img)
# ritaglia dentro il cerchio del vetro
mask = Image.new("L", (SIZE, SIZE), 0)
md = ImageDraw.Draw(mask)
md.ellipse([cx - door_r + 4, cy - door_r + 4, cx + door_r - 4, cy + door_r - 4], fill=255)
# onda sinusoidale
import math as m
wave = []
points = []
for x in range(cx - door_r, cx + door_r + 1, 2):
    y = water_level + m.sin((x - cx) / 40) * 6
    points.append((x, y))
points.append((cx + door_r, cy + door_r))
points.append((cx - door_r, cy + door_r))
wd.polygon(points, fill=(56, 189, 248, 110))
water_img.putalpha(mask)
img = Image.alpha_composite(img, water_img)
d = ImageDraw.Draw(img)

# --- Cestello: fori concentrici ---
hole_r = 7
for ring_idx, (rr, n) in enumerate([(110, 8), (180, 14), (250, 20)]):
    for k in range(n):
        a = (k / n) * 2 * m.pi + ring_idx * 0.4
        px = cx + m.cos(a) * rr
        py = cy + m.sin(a) * rr
        d.ellipse([px - hole_r, py - hole_r, px + hole_r, py + hole_r], fill=(0, 0, 0, 200))

# asse centrale + 3 bracci
for i in range(3):
    a = (i / 3) * 2 * m.pi
    x2 = cx + m.cos(a) * 220
    y2 = cy + m.sin(a) * 220
    d.line([(cx, cy), (x2, y2)], fill=(71, 85, 105, 255), width=18)
d.ellipse([cx - 45, cy - 45, cx + 45, cy + 45], fill=(51, 65, 85, 255))

# --- Bolle (piccoli cerchi azzurri flottanti sopra l'acqua) ---
import random
random.seed(42)
for _ in range(14):
    bx = cx + random.randint(-door_r + 30, door_r - 30)
    by = cy + random.randint(-door_r + 30, int(water_level) - 10)
    br = random.randint(8, 22)
    # evita le bolle troppo vicino al centro (cestello)
    if m.hypot(bx - cx, by - cy) < 90:
        continue
    d.ellipse([bx - br, by - br, bx + br, by + br], outline=(186, 230, 253, 200), width=2)
    # riflesso (in alto a sinistra della bolla)
    rrx0, rry0 = bx - br // 2, by - br // 2
    rrx1, rry1 = bx, by - br // 4
    if rrx1 > rrx0 and rry1 > rry0:
        d.ellipse([rrx0, rry0, rrx1, rry1], fill=(255, 255, 255, 90))

# --- Riflesso sul vetro (mezzaluna in alto a sinistra) ---
reflect = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
rd = ImageDraw.Draw(reflect)
rd.pieslice(
    [cx - door_r + 30, cy - door_r + 30, cx + door_r - 30, cy + door_r - 30],
    start=200, end=290, fill=(255, 255, 255, 45),
)
reflect = reflect.filter(ImageFilter.GaussianBlur(12))
# ritaglia al cerchio
reflect.putalpha(mask)
img = Image.alpha_composite(img, reflect)

# --- Salvataggio ---
out = "C:/xampp/candy/flutter_app/assets/icon/icon.png"
img.convert("RGB").save(out, "PNG")
print("Icona salvata:", out)
