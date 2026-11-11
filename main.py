#!/usr/bin/env python3
"""Draw one original kitten illustration and write it to entry.png.

The grader (make.fun cutest-cat-01, harness program/v1) runs this file with
Python 3.13, standard library only, no network, and a writable output
directory. Locally:

    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

In the sandbox the same program writes /output/entry.png. Both runs must
produce the same bytes. The picture is a whole PNG, at most 1024 by 1024
pixels and at most 1 MiB.

Nothing here is copied from the kit starter or from another entry. The
kitten is constructed from ellipses, rounded triangles, and strokes.
"""

from __future__ import annotations

import math
import os
import struct
import zlib

WIDTH = 1024
HEIGHT = 1024

# Image-space light, toward the upper left (+y is down).
_LL = math.hypot(-0.34, -0.94)
LIGHT = (-0.34 / _LL, -0.94 / _LL)

STYLE_FUR = 0
STYLE_FLAT = 1
STYLE_GLOW = 2


def clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def clamp_byte(v: float) -> int:
    if v < 0.0:
        return 0
    if v > 255.0:
        return 255
    return int(v + 0.5)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = clamp(t, 0.0, 1.0)
    return (
        clamp_byte(a[0] + (b[0] - a[0]) * t),
        clamp_byte(a[1] + (b[1] - a[1]) * t),
        clamp_byte(a[2] + (b[2] - a[2]) * t),
    )


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def cov_from_sd(sd: float, soft: float) -> float:
    if sd <= -soft:
        return 1.0
    if sd >= soft:
        return 0.0
    t = (soft - sd) / (2.0 * soft)
    return t * t * (3.0 - 2.0 * t)


def fur_rgb(
    base: tuple[int, int, int],
    shadow: tuple[int, int, int],
    highlight: tuple[int, int, int],
    ndot: float,
    sd: float,
    shine: float,
) -> tuple[int, int, int]:
    """Matte fur: colored shadow, cream highlight, a crisp rim."""
    st = clamp((0.22 - ndot) / 1.2, 0.0, 1.0)
    st *= st
    ht = clamp((ndot - 0.02) / 0.98, 0.0, 1.0)
    ht *= ht
    r = base[0] + (shadow[0] - base[0]) * st * 0.92 + (highlight[0] - base[0]) * ht * 0.72
    g = base[1] + (shadow[1] - base[1]) * st * 0.92 + (highlight[1] - base[1]) * ht * 0.72
    b = base[2] + (shadow[2] - base[2]) * st * 0.92 + (highlight[2] - base[2]) * ht * 0.72
    if sd > -3.2:
        k = clamp((sd + 3.2) / 3.2, 0.0, 1.0)
        dark = k * clamp(-ndot, 0.0, 1.0)
        r = r * (1.0 - 0.38 * dark) + shadow[0] * 0.38 * dark
        g = g * (1.0 - 0.38 * dark) + shadow[1] * 0.38 * dark
        b = b * (1.0 - 0.38 * dark) + shadow[2] * 0.38 * dark
        lit = k * clamp(ndot, 0.0, 1.0) * 0.28
        r = r * (1.0 - lit) + highlight[0] * lit
        g = g * (1.0 - lit) + highlight[1] * lit
        b = b * (1.0 - lit) + highlight[2] * lit
    if shine > 0.0 and ndot > 0.0:
        spec = (ndot ** 12) * shine
        r = r * (1.0 - spec) + 255.0 * spec
        g = g * (1.0 - spec) + 255.0 * spec
        b = b * (1.0 - spec) + 255.0 * spec
    return clamp_byte(r), clamp_byte(g), clamp_byte(b)


def sd_ellipse(lx: float, ly: float, rx: float, ry: float) -> tuple[float, float, float]:
    """First-order signed distance and an outward normal in local space."""
    gx = lx / (rx * rx)
    gy = ly / (ry * ry)
    g = math.hypot(gx, gy)
    if g < 1e-8:
        return -min(rx, ry), 0.0, -1.0
    ex = lx / rx
    ey = ly / ry
    sd = (ex * ex + ey * ey - 1.0) / (2.0 * g)
    return sd, gx / g, gy / g


def sd_capsule(
    px: float, py: float, ax: float, ay: float, bx: float, by: float, rad: float
) -> tuple[float, float, float]:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab2 = abx * abx + aby * aby
    t = 0.0 if ab2 <= 1e-8 else clamp((apx * abx + apy * aby) / ab2, 0.0, 1.0)
    cx = ax + abx * t
    cy = ay + aby * t
    dx = px - cx
    dy = py - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-8:
        return -rad, 0.0, -1.0
    return dist - rad, dx / dist, dy / dist


def sd_triangle(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
) -> float:
    """Inigo Quilez signed distance. Negative inside. Any winding."""
    e0x, e0y = bx - ax, by - ay
    e1x, e1y = cx - bx, cy - by
    e2x, e2y = ax - cx, ay - cy
    v0x, v0y = px - ax, py - ay
    v1x, v1y = px - bx, py - by
    v2x, v2y = px - cx, py - cy

    def dot(x: float, y: float, u: float, v: float) -> float:
        return x * u + y * v

    d0 = dot(e0x, e0y, e0x, e0y) or 1.0
    d1 = dot(e1x, e1y, e1x, e1y) or 1.0
    d2 = dot(e2x, e2y, e2x, e2y) or 1.0
    t0 = clamp(dot(v0x, v0y, e0x, e0y) / d0, 0.0, 1.0)
    t1 = clamp(dot(v1x, v1y, e1x, e1y) / d1, 0.0, 1.0)
    t2 = clamp(dot(v2x, v2y, e2x, e2y) / d2, 0.0, 1.0)
    q0x, q0y = v0x - e0x * t0, v0y - e0y * t0
    q1x, q1y = v1x - e1x * t1, v1y - e1y * t1
    q2x, q2y = v2x - e2x * t2, v2y - e2y * t2
    c0 = dot(q0x, q0y, q0x, q0y)
    c1 = dot(q1x, q1y, q1x, q1y)
    c2 = dot(q2x, q2y, q2x, q2y)
    s = 1.0 if (e0x * e2y - e0y * e2x) > 0.0 else -1.0
    x0, y0 = c0, s * (v0x * e0y - v0y * e0x)
    x1, y1 = c1, s * (v1x * e1y - v1y * e1x)
    x2, y2 = c2, s * (v2x * e2y - v2y * e2x)
    mx = x0 if x0 < x1 else x1
    my = y0 if y0 < y1 else y1
    if x2 < mx:
        mx = x2
    if y2 < my:
        my = y2
    sign = 1.0 if my > 0.0 else (-1.0 if my < 0.0 else 0.0)
    return -math.sqrt(mx) * sign


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _sad(buf: bytes | bytearray) -> int:
    total = 0
    for b in buf:
        total += b if b < 128 else 256 - b
    return total


def encode_png(width: int, height: int, rgb: bytearray) -> bytes:
    """Truecolor PNG, adaptive scanline filters, one IDAT. Deterministic."""
    stride = width * 3
    raw = bytearray()
    prev = bytearray(stride)
    for y in range(height):
        row = rgb[y * stride : (y + 1) * stride]
        best_tag = 0
        best_score = 10**18
        best: bytearray | None = None
        for filt in range(5):
            line = bytearray(stride)
            if filt == 0:
                line[:] = row
            elif filt == 1:
                line[0:3] = row[0:3]
                for i in range(3, stride):
                    line[i] = (row[i] - row[i - 3]) & 255
            elif filt == 2:
                for i in range(stride):
                    line[i] = (row[i] - prev[i]) & 255
            elif filt == 3:
                for i in range(stride):
                    left = row[i - 3] if i >= 3 else 0
                    line[i] = (row[i] - ((left + prev[i]) // 2)) & 255
            else:
                for i in range(stride):
                    left = row[i - 3] if i >= 3 else 0
                    up_left = prev[i - 3] if i >= 3 else 0
                    line[i] = (row[i] - _paeth(left, prev[i], up_left)) & 255
            score = _sad(line)
            if score < best_score:
                best_score = score
                best_tag = filt
                best = line
        raw.append(best_tag)
        raw += best if best is not None else row
        prev = bytearray(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(data, zlib.crc32(tag)) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


class Raster:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.buf = bytearray(width * height * 3)

    def _put(self, x: int, y: int, r: int, g: int, b: int, cover: float) -> None:
        if cover <= 0.0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        ai = 255 if cover >= 0.999 else int(cover * 255.0 + 0.5)
        if ai <= 0:
            return
        i = (y * self.w + x) * 3
        buf = self.buf
        if ai >= 255:
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            return
        inv = 255 - ai
        buf[i] = (r * ai + buf[i] * inv + 127) // 255
        buf[i + 1] = (g * ai + buf[i + 1] * inv + 127) // 255
        buf[i + 2] = (b * ai + buf[i + 2] * inv + 127) // 255

    def background(self) -> None:
        w, h = self.w, self.h
        buf = self.buf
        top = (234, 226, 242)
        bot = (255, 214, 198)
        hot = (255, 250, 247)
        span = h - 1
        for y in range(h):
            t = y / span
            t = t * t * (3.0 - 2.0 * t)
            br = top[0] + (bot[0] - top[0]) * t
            bg = top[1] + (bot[1] - top[1]) * t
            bb = top[2] + (bot[2] - top[2]) * t
            row = y * w * 3
            for x in range(w):
                sdx = (x - 500) / 390.0
                sdy = (y - 400) / 400.0
                spot = math.exp(-(sdx * sdx + sdy * sdy) * 1.55)
                r = br + (hot[0] - br) * spot * 0.7
                g = bg + (hot[1] - bg) * spot * 0.7
                b = bb + (hot[2] - bb) * spot * 0.7
                vd = math.hypot((x + 0.5) / w - 0.5, (y + 0.5) / h - 0.46)
                vig = clamp(1.0 - max(0.0, vd - 0.42) * 0.34, 0.9, 1.0)
                i = row + x * 3
                buf[i] = clamp_byte(r * vig)
                buf[i + 1] = clamp_byte(g * vig)
                buf[i + 2] = clamp_byte(b * vig)

    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        rot: float,
        color: tuple[int, int, int],
        shadow: tuple[int, int, int] | None = None,
        highlight: tuple[int, int, int] | None = None,
        alpha: int = 255,
        soft: float = 1.8,
        style: int = STYLE_FUR,
        shine: float = 0.0,
        shader=None,
    ) -> None:
        if rx <= 0.2 or ry <= 0.2 or alpha <= 0:
            return
        cos_r = math.cos(rot)
        sin_r = math.sin(rot)
        pad = soft + 2.0
        if style == STYLE_GLOW:
            pad += max(rx, ry) * 1.15
        ext_x = abs(cos_r) * rx + abs(sin_r) * ry + pad
        ext_y = abs(sin_r) * rx + abs(cos_r) * ry + pad
        x0 = max(0, int(cx - ext_x))
        x1 = min(self.w, int(cx + ext_x) + 1)
        y0 = max(0, int(cy - ext_y))
        y1 = min(self.h, int(cy + ext_y) + 1)
        base = color
        sh = shadow if shadow is not None else mix(color, (160, 96, 78), 0.45)
        hi = highlight if highlight is not None else mix(color, (255, 255, 255), 0.55)
        alpha_f = alpha / 255.0
        lx_l, ly_l = LIGHT
        put = self._put
        for y in range(y0, y1):
            dy = y + 0.5 - cy
            for x in range(x0, x1):
                dx = x + 0.5 - cx
                lx = cos_r * dx + sin_r * dy
                ly = -sin_r * dx + cos_r * dy
                ex = lx / rx
                ey = ly / ry
                e2 = ex * ex + ey * ey
                if style == STYLE_GLOW:
                    if e2 > 4.6:
                        continue
                    cover = math.exp(-e2 * 2.15) * alpha_f
                    put(x, y, base[0], base[1], base[2], cover)
                    continue
                if e2 > 1.45:
                    continue
                sd, nx, ny = sd_ellipse(lx, ly, rx, ry)
                cover = cov_from_sd(sd, soft) * alpha_f
                if cover <= 0.0:
                    continue
                inx = cos_r * nx - sin_r * ny
                iny = sin_r * nx + cos_r * ny
                ndot = inx * lx_l + iny * ly_l
                if shader is not None:
                    rgb = shader(ex, ey, ndot, sd)
                elif style == STYLE_FLAT:
                    rgb = base
                else:
                    rgb = fur_rgb(base, sh, hi, ndot, sd, shine)
                put(x, y, rgb[0], rgb[1], rgb[2], cover)

    def capsule(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        rad: float,
        color: tuple[int, int, int],
        shadow: tuple[int, int, int] | None = None,
        highlight: tuple[int, int, int] | None = None,
        alpha: int = 255,
        soft: float = 1.35,
        style: int = STYLE_FLAT,
        shine: float = 0.0,
    ) -> None:
        if rad <= 0.2 or alpha <= 0:
            return
        pad = rad + soft + 1.5
        xa = max(0, int(min(x0, x1) - pad))
        xb = min(self.w, int(max(x0, x1) + pad) + 1)
        ya = max(0, int(min(y0, y1) - pad))
        yb = min(self.h, int(max(y0, y1) + pad) + 1)
        sh = shadow if shadow is not None else mix(color, (160, 96, 78), 0.45)
        hi = highlight if highlight is not None else mix(color, (255, 255, 255), 0.5)
        alpha_f = alpha / 255.0
        lx_l, ly_l = LIGHT
        put = self._put
        for y in range(ya, yb):
            py = y + 0.5
            for x in range(xa, xb):
                px = x + 0.5
                sd, nx, ny = sd_capsule(px, py, x0, y0, x1, y1, rad)
                if sd > soft:
                    continue
                cover = cov_from_sd(sd, soft) * alpha_f
                if cover <= 0.0:
                    continue
                if style == STYLE_FLAT:
                    rgb = color
                else:
                    ndot = nx * lx_l + ny * ly_l
                    rgb = fur_rgb(color, sh, hi, ndot, sd, shine)
                put(x, y, rgb[0], rgb[1], rgb[2], cover)

    def triangle(
        self,
        pts: list[tuple[float, float]],
        roundness: float,
        color: tuple[int, int, int],
        shadow: tuple[int, int, int] | None = None,
        highlight: tuple[int, int, int] | None = None,
        alpha: int = 255,
        soft: float = 1.6,
        style: int = STYLE_FUR,
        shine: float = 0.0,
    ) -> None:
        if alpha <= 0:
            return
        (ax, ay), (bx, by), (cx, cy) = pts
        pad = roundness + soft + 2.0
        xa = max(0, int(min(ax, bx, cx) - pad))
        xb = min(self.w, int(max(ax, bx, cx) + pad) + 1)
        ya = max(0, int(min(ay, by, cy) - pad))
        yb = min(self.h, int(max(ay, by, cy) + pad) + 1)
        sh = shadow if shadow is not None else mix(color, (176, 104, 96), 0.4)
        hi = highlight if highlight is not None else mix(color, (255, 255, 255), 0.45)
        span = max(1.0, max(ay, by, cy) - min(ay, by, cy))
        min_y = min(ay, by, cy)
        alpha_f = alpha / 255.0
        put = self._put
        for y in range(ya, yb):
            py = y + 0.5
            for x in range(xa, xb):
                px = x + 0.5
                sd = sd_triangle(px, py, ax, ay, bx, by, cx, cy) - roundness
                if sd > soft:
                    continue
                cover = cov_from_sd(sd, soft) * alpha_f
                if cover <= 0.0:
                    continue
                if style == STYLE_FLAT:
                    rgb = color
                else:
                    t = (py - min_y) / span
                    fake = 0.9 - 1.35 * t
                    rgb = fur_rgb(color, sh, hi, fake, sd, shine)
                put(x, y, rgb[0], rgb[1], rgb[2], cover)


def rot(x: float, y: float, ang: float, origin: tuple[float, float]) -> tuple[float, float]:
    ox, oy = origin
    dx, dy = x - ox, y - oy
    c = math.cos(ang)
    s = math.sin(ang)
    return ox + c * dx - s * dy, oy + s * dx + c * dy


def cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    n: int,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    steps = n - 1
    for i in range(n):
        t = i / steps
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3 * u * u * t
        b2 = 3 * u * t * t
        b3 = t * t * t
        pts.append(
            (
                b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
            )
        )
    return pts


def arc_points(
    cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    steps = n - 1
    for i in range(n):
        a = a0 + (a1 - a0) * (i / steps)
        pts.append((cx + math.cos(a) * rx, cy + math.sin(a) * ry))
    return pts


# Palette. Warm apricot kitten, lilac air, sage rug. No pure black.
FUR = (255, 214, 176)
FUR_SH = (214, 140, 106)
FUR_HI = (255, 242, 226)
CREAM = (255, 248, 240)
CHEST = (255, 246, 238)
MUZZLE = (255, 244, 236)
EAR = (244, 174, 136)
EAR_SH = (214, 128, 110)
EAR_HI = (255, 224, 202)
EAR_IN = (255, 188, 194)
EAR_IN_SH = (236, 146, 162)
EAR_IN_HI = (255, 226, 228)
BLUSH = (255, 146, 158)
NOSE = (242, 126, 146)
NOSE_SH = (214, 96, 118)
NOSE_HI = (255, 210, 214)
MOUTH = (186, 104, 114)
IRIS_IN = (255, 220, 112)
IRIS_OUT = (186, 104, 42)
IRIS_RIM = (122, 68, 40)
PUPIL = (68, 44, 40)
PUPIL_CORE = (108, 72, 62)
SCLERA = (255, 250, 246)
LID = (236, 176, 146)
COLLAR = (224, 112, 128)
COLLAR_HI = (255, 176, 184)
BELL = (248, 214, 128)
BELL_SH = (196, 146, 62)
BELL_HI = (255, 248, 220)
YARN = (232, 142, 162)
YARN_SH = (196, 104, 128)
YARN_HI = (255, 214, 222)
YARN_BAND = (255, 236, 232)
WHISKER = (108, 74, 68)
RUG = (214, 224, 208)
RUG_RIM = (186, 200, 182)
RUG_IN = (232, 238, 226)

HEAD = (512, 420)
TILT = -0.30  # Crown moves left, viewer's-left ear drops.


def paint(img: Raster) -> None:
    img.background()
    _bokeh(img)
    _rug(img)
    _tail(img)
    _body(img)
    _ears(img)
    _head(img)
    _face(img)
    _collar(img)
    _paws_and_yarn(img)


def _bokeh(img: Raster) -> None:
    spots = (
        (150, 170, 108, (255, 255, 255), 42),
        (890, 150, 126, (255, 228, 238), 40),
        (120, 860, 140, (255, 236, 224), 34),
        (930, 900, 120, (226, 232, 236), 32),
        (512, 96, 70, (255, 255, 255), 28),
    )
    for cx, cy, rad, color, alpha in spots:
        img.ellipse(cx, cy, rad, rad * 0.92, 0.0, color, alpha=alpha, style=STYLE_GLOW)


def _rug(img: Raster) -> None:
    cx, cy = 530, 868
    img.ellipse(cx, cy + 8, 390, 108, 0.0, RUG_RIM, style=STYLE_FLAT, soft=2.2)
    img.ellipse(cx, cy, 372, 96, 0.0, RUG, shadow=(196, 208, 190), highlight=RUG_IN, soft=2.0, shine=0.0)
    img.ellipse(cx, cy - 6, 250, 58, 0.0, RUG_IN, alpha=90, style=STYLE_FLAT, soft=10)
    # Contact shadow sits on the rug, under the kitten.
    img.ellipse(524, 846, 196, 36, 0.04, (186, 132, 112), alpha=54, style=STYLE_FLAT, soft=8)


def _stroke(img: Raster, pts: list[tuple[float, float]], rad: float, color: tuple[int, int, int], alpha: int = 255, soft: float = 1.3) -> None:
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        img.capsule(x0, y0, x1, y1, rad, color, alpha=alpha, soft=soft, style=STYLE_FLAT)


def _tail(img: Raster) -> None:
    # One flat tube. Per-segment highlights read as rings, so the body of the
    # tail is a single color and only the tip lightens.
    pts = cubic((500, 800), (340, 940), (176, 790), (300, 662), 34)
    for i in range(len(pts) - 1):
        t = i / (len(pts) - 2)
        color = mix(FUR_SH, FUR, min(1.0, t / 0.55))
        if t > 0.74:
            color = mix(FUR, CREAM, (t - 0.74) / 0.26)
        rad = 34.0 * (1.0 - t) + 22.0 * t
        if t > 0.8:
            rad += ((t - 0.8) / 0.2) * 14.0
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        img.capsule(x0, y0, x1, y1, rad, color, soft=2.6, style=STYLE_FLAT)
    tip = pts[-1]
    img.ellipse(tip[0], tip[1], 40, 36, -0.5, CREAM, shadow=FUR, highlight=(255, 252, 248), soft=3.0, shine=0.02)


def _body(img: Raster) -> None:
    # Wide hips under a smaller torso: a sitting kitten, hind legs folded in.
    img.ellipse(528, 778, 214, 108, 0.04, FUR, FUR_SH, FUR_HI, soft=2.4, shine=0.04)
    img.ellipse(524, 688, 176, 148, 0.05, FUR, FUR_SH, FUR_HI, soft=2.2, shine=0.06)
    img.ellipse(518, 578, 92, 74, TILT * 0.25, FUR, FUR_SH, FUR_HI, soft=2.2, shine=0.05)


def _ears(img: Raster) -> None:
    # Tall ellipses, bases tucked under the skull. Triangles left a straight
    # outer edge on the raised ear; a curve stays soft when the head tilts.
    for cx, cy, lean in ((366, 286, -0.46), (658, 280, 0.48)):
        _head_ellipse(
            img, cx, cy, 52, 136, lean,
            color=EAR, shadow=EAR_SH, highlight=EAR_HI, soft=1.8, shine=0.05,
        )
        _head_ellipse(
            img, cx, cy - 22, 26, 74, lean,
            color=EAR_IN, shadow=EAR_IN_SH, highlight=EAR_IN_HI, soft=1.6, shine=0.03,
        )


def _head_ellipse(img: Raster, cx: float, cy: float, rx: float, ry: float, extra: float = 0.0, **kwargs) -> None:
    x, y = rot(cx, cy, TILT, HEAD)
    img.ellipse(x, y, rx, ry, TILT + extra, **kwargs)


def _head(img: Raster) -> None:
    # Cheek and chin puffs break the oval before the skull covers their centers.
    _head_ellipse(img, 348, 468, 58, 48, 0.2, color=FUR, shadow=FUR_SH, highlight=FUR_HI, soft=2.4, shine=0.04)
    _head_ellipse(img, 676, 470, 56, 46, -0.25, color=FUR, shadow=FUR_SH, highlight=FUR_HI, soft=2.4, shine=0.04)
    _head_ellipse(img, 512, 548, 74, 42, 0.0, color=FUR, shadow=FUR_SH, highlight=FUR_HI, soft=2.2, shine=0.04)
    _head_ellipse(img, 512, 420, 214, 198, 0.0, color=FUR, shadow=FUR_SH, highlight=FUR_HI, soft=2.0, shine=0.07)
    # Soft forehead shine. No brow marks: those read as a frown.
    _head_ellipse(img, 512, 348, 40, 18, 0.0, color=FUR_HI, alpha=90, style=STYLE_FLAT, soft=7)
    # White blaze from the chin down over the chest.
    _head_ellipse(img, 514, 600, 46, 78, 0.0, color=CHEST, shadow=(244, 214, 202), highlight=(255, 252, 248), alpha=235, soft=6, shine=0.03)
    img.ellipse(530, 748, 70, 86, 0.06, CHEST, (244, 220, 210), (255, 252, 248), alpha=230, soft=8, shine=0.03)


def _eye_shader(ex: float, ey: float, _ndot: float, sd: float) -> tuple[int, int, int]:
    # +ey is down in the eye. Iris sits a little high so a crescent of sclera shows.
    sclera = mix(SCLERA, (240, 214, 210), clamp(ey, 0.0, 1.0) * 0.45)
    col = sclera
    ix = ex / 0.84
    iy = (ey + 0.10) / 0.76
    ir = math.hypot(ix, iy)
    iris_amt = smoothstep(1.02, 0.90, ir)
    if iris_amt > 0.0:
        u = clamp(ir, 0.0, 1.0)
        iris = mix(IRIS_IN, IRIS_OUT, u ** 0.8)
        iris = mix(iris, IRIS_RIM, smoothstep(0.62, 1.0, u))
        # A cooler inner ring keeps the gold from looking flat.
        iris = mix(iris, (255, 236, 170), clamp(1.0 - u / 0.45, 0.0, 1.0) * 0.35)
        px = ex / 0.40
        py = (ey + 0.14) / 0.52
        pr = math.hypot(px, py)
        if pr < 1.15:
            core = mix(PUPIL_CORE, PUPIL, clamp(pr / 0.65, 0.0, 1.0))
            iris = mix(core, iris, smoothstep(0.78, 1.02, pr))
        # A thin lid only. A heavier one reads as worried.
        lid = smoothstep(-0.42, -0.78, ey)
        iris = mix(iris, LID, lid * 0.55)
        crease = math.exp(-((ey + 0.34) ** 2) / 0.012)
        iris = mix(iris, (176, 112, 100), crease * 0.22)
        # Warm bounce along the lower iris.
        bounce = math.exp(-((ey - 0.42) ** 2) / 0.02) * clamp(1.0 - abs(ex) / 0.7, 0.0, 1.0)
        iris = mix(iris, (255, 186, 140), bounce * 0.28)
        col = mix(col, iris, iris_amt)
        # Catchlights stay in the same local corner of each eye (one light).
        c1 = math.hypot((ex + 0.28) / 0.23, (ey + 0.28) / 0.19)
        if c1 < 1.15:
            col = mix(col, (255, 255, 255), smoothstep(1.05, 0.35, c1) * 0.96)
        c2 = math.hypot((ex - 0.22) / 0.09, (ey + 0.02) / 0.08)
        if c2 < 1.2:
            col = mix(col, (255, 255, 255), smoothstep(1.1, 0.2, c2) * 0.75)
    if sd > -2.4:
        edge = clamp((sd + 2.4) / 2.4, 0.0, 1.0)
        col = mix(col, (132, 84, 74), edge * 0.62)
    return col


def _face(img: Raster) -> None:
    _head_ellipse(img, 512, 508, 96, 66, 0.0, color=MUZZLE, shadow=(244, 214, 204), highlight=(255, 252, 248), alpha=245, soft=5, shine=0.02)
    _head_ellipse(img, 392, 512, 44, 26, 0.2, color=BLUSH, alpha=88, style=STYLE_FLAT, soft=8)
    _head_ellipse(img, 632, 514, 44, 26, -0.2, color=BLUSH, alpha=88, style=STYLE_FLAT, soft=8)

    for cx, cy in ((424, 436), (600, 436)):
        _head_ellipse(
            img, cx, cy, 68, 72, 0.0,
            color=SCLERA, soft=1.2, style=STYLE_FLAT, shader=_eye_shader,
        )

    nose = [rot(x, y, TILT, HEAD) for x, y in ((494, 500), (530, 500), (512, 526))]
    img.triangle(nose, 8.0, NOSE, NOSE_SH, NOSE_HI, soft=1.15, shine=0.4)
    hx, hy = rot(507, 506, TILT, HEAD)
    img.ellipse(hx, hy, 7.0, 4.4, TILT, (255, 236, 236), alpha=210, style=STYLE_FLAT, soft=1.2)

    # A shallow smile. A vertical stroke under the nose read as a cross.
    smile = (
        (478, 546),
        (496, 558),
        (512, 562),
        (528, 558),
        (546, 546),
    )
    placed = [rot(x, y, TILT, HEAD) for x, y in smile]
    for i in range(len(placed) - 1):
        x0, y0 = placed[i]
        x1, y1 = placed[i + 1]
        img.capsule(x0, y0, x1, y1, 3.1, MOUTH, soft=1.35, style=STYLE_FLAT)

    _whiskers(img)


def _whiskers(img: Raster) -> None:
    fans = (
        ((456, 524), (292, 492), (278, 534), (308, 578)),
        ((568, 524), (732, 490), (748, 534), (714, 580)),
    )
    for origin, *tips in fans:
        ox, oy = rot(origin[0], origin[1], TILT, HEAD)
        for tip in tips:
            tx, ty = rot(tip[0], tip[1], TILT, HEAD)
            # A short break at the root so whiskers start in the fur, not on the nose.
            mx = ox * 0.72 + tx * 0.28
            my = oy * 0.72 + ty * 0.28
            img.capsule(mx, my, tx, ty, 2.7, WHISKER, alpha=185, soft=1.15, style=STYLE_FLAT)
def _bow_loop(img: Raster, cx: float, cy: float, turn: float) -> None:
    x, y = rot(cx, cy, TILT, HEAD)
    img.ellipse(x, y, 30, 18, TILT + turn, COLLAR, (186, 78, 98), COLLAR_HI, soft=1.4, shine=0.16)
    # A lighter inner fold so the loop is not a flat disc.
    ix, iy = rot(cx + (8 if turn > 0 else -8), cy - 1, TILT, HEAD)
    img.ellipse(ix, iy, 12, 7, TILT + turn, COLLAR_HI, alpha=170, style=STYLE_FLAT, soft=1.5)


def _collar(img: Raster) -> None:
    # A small bow instead of a disc. The disc read as a plate on the chest.
    _bow_loop(img, 476, 628, 0.55)
    _bow_loop(img, 548, 630, -0.55)
    for tip in ((448, 678), (572, 682)):
        a = rot(512, 646, TILT, HEAD)
        b = rot(tip[0], tip[1], TILT, HEAD)
        img.capsule(a[0], a[1], b[0], b[1], 6.5, COLLAR, shadow=(186, 78, 98), highlight=COLLAR_HI, soft=1.3, style=STYLE_FUR, shine=0.08)
    kx, ky = rot(512, 636, TILT, HEAD)
    img.ellipse(kx, ky, 12, 11, TILT, (196, 78, 98), (150, 54, 74), COLLAR_HI, soft=1.2, shine=0.2)
    bx, by = rot(512, 668, TILT, HEAD)
    img.ellipse(bx, by, 15, 16, TILT, BELL, BELL_SH, BELL_HI, soft=1.2, shine=0.7)
    img.ellipse(bx - 4, by - 5, 5.0, 3.8, TILT, (255, 255, 246), alpha=230, style=STYLE_FLAT, soft=1.1)
    img.capsule(bx, by - 1, bx, by + 8, 1.35, (120, 78, 48), soft=0.7)
    img.ellipse(bx, by + 4, 5.5, 4.0, TILT, (168, 112, 52), alpha=170, style=STYLE_FLAT, soft=1.0)


def _paw(img: Raster, cx: float, cy: float, rx: float, ry: float, rot_a: float) -> None:
    # Toe tips first. The mitt is drawn over them so only three bumps remain.
    c = math.cos(rot_a)
    s = math.sin(rot_a)
    for ang in (-0.42, 0.0, 0.42):
        dx = math.sin(ang) * rx * 0.62
        dy = -ry * 0.95
        px = cx + c * dx - s * dy
        py = cy + s * dx + c * dy
        img.ellipse(px, py, rx * 0.30, ry * 0.48, rot_a + ang * 0.25, FUR, FUR_SH, FUR_HI, soft=1.7, shine=0.04)
    img.ellipse(cx, cy, rx, ry, rot_a, FUR, FUR_SH, FUR_HI, soft=1.7, shine=0.05)


def _paws_and_yarn(img: Raster) -> None:
    # Short kitten legs. The yarn stays clear of the paw; a strand joins them.
    img.ellipse(500, 760, 50, 52, 0.12, FUR, FUR_SH, FUR_HI, soft=2.1, shine=0.04)
    img.ellipse(640, 768, 52, 56, 0.22, FUR, FUR_SH, FUR_HI, soft=2.1, shine=0.04)
    _yarn(img)
    img.ellipse(456, 828, 46, 13, -0.05, (176, 120, 104), alpha=42, style=STYLE_FLAT, soft=4)
    img.ellipse(688, 836, 50, 14, 0.15, (176, 120, 104), alpha=42, style=STYLE_FLAT, soft=4)
    _paw(img, 456, 812, 60, 36, -0.08)
    _paw(img, 688, 822, 64, 38, 0.16)


def _yarn(img: Raster) -> None:
    cx, cy, rad = 868, 852, 54
    img.ellipse(cx + 6, cy + 10, rad * 0.86, rad * 0.42, 0.15, (186, 120, 112), alpha=40, style=STYLE_FLAT, soft=5)
    img.ellipse(cx, cy, rad, rad * 0.96, 0.15, YARN, YARN_SH, YARN_HI, soft=1.6, shine=0.1)
    bands = (
        (-0.5, 2.15, 36, 30, YARN_BAND),
        (1.15, 3.6, 32, 38, (206, 112, 136)),
        (2.5, 4.7, 40, 24, YARN_BAND),
        (-1.3, 0.45, 24, 32, (255, 228, 226)),
    )
    for a0, a1, rx, ry, color in bands:
        pts = arc_points(cx, cy, rx, ry, a0, a1, 9)
        _stroke(img, pts, 3.6, color, alpha=220, soft=1.2)
    strand = cubic((cx - 30, cy + 8), (790, 910), (760, 860), (742, 838), 14)
    _stroke(img, strand, 3.6, YARN, alpha=235, soft=1.25)
    end = strand[-1]
    img.ellipse(end[0] - 2, end[1], 7, 6, 0.6, YARN_SH, style=STYLE_FLAT, soft=1.1)


def main() -> None:
    img = Raster(WIDTH, HEIGHT)
    paint(img)
    data = encode_png(WIDTH, HEIGHT, img.buf)
    directory = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "entry.png")
    with open(path, "wb") as handle:
        handle.write(data)


if __name__ == "__main__":
    main()
