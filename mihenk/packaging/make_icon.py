# -*- coding: utf-8 -*-
"""assets/agfo-mihenk.ico dosyasini uretir (yalnizca standart kutuphane).

Simge ozgun ve basit tutuldu: koyu bir mihenk tasi ve uzerinde altin bir ciz.
Ikonu degistirmek gerekirse renkleri ve cizgiyi buradan duzenleyip

    python packaging/make_icon.py

komutunu calistirmak yeterli. Uretilen dosya depoya islenir, derleme sirasinda
yeniden uretilmez.
"""
from __future__ import annotations

import pathlib
import struct

SIZES = (16, 24, 32, 48, 64, 128, 256)

STONE_DARK = (26, 32, 40)
STONE_LIGHT = (47, 57, 70)
GOLD = (214, 168, 70)
GOLD_SOFT = (236, 201, 120)


def blend(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def draw(size: int):
    """Tek bir kare icin RGBA piksel listesi uretir."""
    pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
    radius = size * 0.22
    margin = size * 0.06
    left, top = margin, margin
    right, bottom = size - margin, size - margin

    for y in range(size):
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            if not _inside_round_rect(px, py, left, top, right, bottom, radius):
                continue
            shade = blend(STONE_LIGHT, STONE_DARK, (py - top) / max(1.0, bottom - top))
            pixels[y][x] = shade + (255,)

    # Altin ciz: tasin uzerine surulen metalin birakitigi iz.
    thickness = max(1.0, size * 0.085)
    start = (size * 0.30, size * 0.70)
    end = (size * 0.70, size * 0.28)
    for y in range(size):
        for x in range(size):
            if pixels[y][x][3] == 0:
                continue
            distance = _segment_distance(x + 0.5, y + 0.5, start, end)
            if distance > thickness:
                continue
            t = min(1.0, distance / thickness)
            tone = blend(GOLD_SOFT, GOLD, t)
            alpha = 255 if distance <= thickness * 0.75 else int(255 * (1.0 - (t - 0.75) / 0.25))
            base = pixels[y][x]
            mix = blend(base[:3], tone, alpha / 255.0)
            pixels[y][x] = mix + (255,)

    # Ciz'in ucundaki kucuk isaret noktasi.
    dot_r = max(1.0, size * 0.055)
    cx, cy = size * 0.735, size * 0.245
    for y in range(size):
        for x in range(size):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= dot_r * dot_r:
                pixels[y][x] = GOLD_SOFT + (255,)
    return pixels


def _inside_round_rect(px, py, left, top, right, bottom, radius) -> bool:
    if px < left or px > right or py < top or py > bottom:
        return False
    # Kose yuvarlamasi: yalnizca kose kutularinda dairesel sinir uygulanir.
    for cx, cy in ((left + radius, top + radius), (right - radius, top + radius),
                   (left + radius, bottom - radius), (right - radius, bottom - radius)):
        in_corner_x = (px < left + radius) if cx == left + radius else (px > right - radius)
        in_corner_y = (py < top + radius) if cy == top + radius else (py > bottom - radius)
        if in_corner_x and in_corner_y:
            return (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius
    return True


def _segment_distance(px, py, start, end) -> float:
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    nx, ny = ax + t * dx, ay + t * dy
    return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5


def png_bytes(pixels, size: int) -> bytes:
    """Kare icin PNG uretir (ICO icinde PNG saklanabilir)."""
    import binascii
    import zlib
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack('>I', len(payload)) + tag + payload +
                struct.pack('>I', binascii.crc32(tag + payload) & 0xffffffff))

    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
            chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def build(target: pathlib.Path) -> pathlib.Path:
    frames = []
    for size in SIZES:
        frames.append((size, png_bytes(draw(size), size)))

    offset = 6 + 16 * len(frames)
    directory = b''
    payload = b''
    for size, data in frames:
        dimension = 0 if size >= 256 else size
        directory += struct.pack('<BBBBHHII', dimension, dimension, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack('<HHH', 0, 1, len(frames)) + directory + payload)
    return target


if __name__ == '__main__':
    here = pathlib.Path(__file__).resolve().parents[1]
    path = build(here / 'assets' / 'agfo-mihenk.ico')
    print('yazildi:', path, path.stat().st_size, 'bayt')
