#!/usr/bin/env python3
"""Market Ledger explainer video generator (vertical 1080x1920, voice-over, hand-drawn paper style).
Usage: python3 -I make_explainer_video.py spec.json OUT.mp4 [--models DIR] [--preview DIR [--preview-only]]
"""
import json, math, os, random, subprocess, sys, shutil, urllib.request, wave
from multiprocessing import Pool

import numpy as np
import skia

W, H, FPS = 1080, 1920, 30
LEAD, TAIL = 0.35, 0.65            # silence before / after the narration of each scene
MARGIN = 90
CW = W - 2 * MARGIN
PAPER = (250, 248, 242)
INK = (28, 27, 26)
CRIMSON = (155, 27, 42)
TEAL = (24, 128, 130)
GOLD = (201, 162, 39)
GREEN = (24, 130, 70)
GRAY = (125, 125, 120)
NAMED = {"ink": INK, "crimson": CRIMSON, "red": CRIMSON, "teal": TEAL, "gold": GOLD, "green": GREEN, "gray": GRAY}

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def col(c, default=INK):
    if c is None:
        return default
    if isinstance(c, str):
        if c in NAMED:
            return NAMED[c]
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c)


def sk(c, a=1.0):
    return skia.Color(c[0], c[1], c[2], int(255 * max(0, min(1, a))))


# ---------------------------------------------------------------- fonts
def find_font(names):
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
    for n in names:
        for d in dirs:
            for root, _, files in os.walk(d):
                if n in files:
                    return os.path.join(root, n)
    return None


_F = {}


def font(kind, size):
    key = (kind, size)
    if key in _F:
        return _F[key]
    spec = {
        "serif": (["Lora-Variable.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"], False),
        "serifi": (["Lora-Italic-Variable.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf"], False),
        "serifb": (["Lora-Variable.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"], True),
        "sans": (["LiberationSans-Regular.ttf", "DejaVuSans.ttf"], False),
        "sansb": (["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"], False),
    }[kind]
    path = find_font(spec[0])
    tf = skia.Typeface.MakeFromFile(path) if path else skia.Typeface.MakeDefault()
    f = skia.Font(tf, size)
    f.setSubpixel(True)
    if spec[1]:
        f.setEmbolden(True)
    _F[key] = f
    return f


def ease(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


# ---------------------------------------------------------------- drawing primitives
def paint(c, a=1.0, stroke=0, cap=True):
    p = skia.Paint(AntiAlias=True, Color=sk(c, a))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap(skia.Paint.kRound_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def wob_line(cv, x0, y0, x1, y1, c, w, seed, a=1.0, amp=1.6):
    r = random.Random(seed)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    o = r.uniform(-amp, amp)
    path = skia.Path()
    path.moveTo(x0 + r.uniform(-1, 1), y0 + r.uniform(-1, 1))
    path.quadTo(mx + nx * o, my + ny * o, x1 + r.uniform(-1, 1), y1 + r.uniform(-1, 1))
    cv.drawPath(path, paint(c, a, w))


def wob_rect(cv, x, y, w, h, c, sw, seed, a=1.0):
    wob_line(cv, x, y, x + w, y, c, sw, seed, a)
    wob_line(cv, x + w, y, x + w, y + h, c, sw, seed + 1, a)
    wob_line(cv, x + w, y + h, x, y + h, c, sw, seed + 2, a)
    wob_line(cv, x, y + h, x, y, c, sw, seed + 3, a)


def hatch_rect(cv, x, y, w, h, c, a=1.0, tint=0.18, gap=11):
    if w <= 1 or h <= 1:
        return
    cv.save()
    cv.clipRect(skia.Rect.MakeXYWH(x, y, w, h), doAntiAlias=True)
    cv.drawRect(skia.Rect.MakeXYWH(x, y, w, h), paint(c, a * tint))
    hp = paint(c, a * 0.75, 2.2)
    k = -h
    while k < w + h:
        cv.drawLine(x + k, y + h, x + k + h, y, hp)
        k += gap
    cv.restore()


def hatch_circle(cv, cx, cy, r, c, a=1.0):
    path = skia.Path()
    path.addCircle(cx, cy, r)
    cv.save()
    cv.clipPath(path, doAntiAlias=True)
    cv.drawCircle(cx, cy, r, paint(c, a * 0.2))
    hp = paint(c, a * 0.7, 2)
    k = -2 * r
    while k < 2 * r:
        cv.drawLine(cx + k - r, cy + r, cx + k + r, cy - r, hp)
        k += 9
    cv.restore()
    cv.drawCircle(cx, cy, r, paint(c, a, 3))


def text_w(s, f):
    return f.measureText(s)


def draw_text(cv, s, x, y, kind, size, c, a=1.0, align="left"):
    f = font(kind, size)
    w = text_w(s, f)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    cv.drawString(s, x, y, f, paint(c, a))
    return w


def parse_rich(s):
    """'The [[evening]] before' -> [(word, accent)]; punctuation glued to a word stays with it"""
    out, acc, i = [], False, 0
    buf, tok_acc = "", False
    while i < len(s):
        if s.startswith("[[", i):
            if buf:
                out.append((buf, tok_acc)); buf = ""
            acc = True; i += 2; continue
        if s.startswith("]]", i):
            acc = False; i += 2; continue
        ch = s[i]
        if ch == " ":
            if buf:
                out.append((buf, tok_acc)); buf = ""
        elif ch == "\n":
            if buf:
                out.append((buf, tok_acc)); buf = ""
            out.append(("\n", False))
        else:
            if not buf:
                tok_acc = acc
            buf += ch
        i += 1
    if buf:
        out.append((buf, tok_acc))
    return out


def layout_rich(s, size, maxw, accent_col=CRIMSON, kind="serif", acc_kind="serifi"):
    toks = parse_rich(s)
    fn, fa = font(kind, size), font(acc_kind, size)
    space = fn.measureText(" ")
    lines, cur, curw = [], [], 0
    for wd, acc in toks:
        if wd == "\n":
            lines.append((cur, curw)); cur, curw = [], 0; continue
        w = (fa if acc else fn).measureText(wd)
        add = w + (space if cur else 0)
        if cur and curw + add > maxw:
            lines.append((cur, curw)); cur, curw = [], 0; add = w
        cur.append((wd, acc, w))
        curw += add
    if cur:
        lines.append((cur, curw))
    return lines, space


def rich_height(s, size, maxw, lh=1.2, **kw):
    lines, _ = layout_rich(s, size, maxw, **kw)
    return int(len(lines) * size * lh)


def draw_rich(cv, s, x, y, size, maxw, c=INK, a=1.0, align="left", lh=1.2, accent=CRIMSON,
              kind="serif", acc_kind="serifi", reveal=1.0):
    lines, space = layout_rich(s, size, maxw, kind=kind, acc_kind=acc_kind)
    total_words = sum(len(l) for l, _ in lines)
    shown = reveal * total_words
    n = 0
    for i, (ln, lw) in enumerate(lines):
        px = x if align == "left" else x + (maxw - lw) / 2 if align == "center" else x + maxw - lw
        py = y + size * (0.95 + lh * i)
        for wd, acc, w in ln:
            fa = clamp(shown - n)
            n += 1
            if fa <= 0:
                px += w + space; continue
            f = font(acc_kind if acc else kind, size)
            cv.drawString(wd, px, py + (1 - fa) * 14, f, paint(accent if acc else c, a * fa))
            px += w + space
    return int(len(lines) * size * lh)


# ---------------------------------------------------------------- elements
def fmt_num(v, el):
    d = el.get("decimals", 0)
    s = f"{v:,.{d}f}"
    return f"{el.get('prefix', '')}{s}{el.get('suffix', '')}"


def h_text(el):
    return rich_height(el["text"], el.get("size", 50), CW) + 24


def d_text(cv, el, x, y, p, seed):
    size = el.get("size", 50)
    kind, ak = ("serifi", "serifi") if el.get("italic") else ("serif", "serifi")
    draw_rich(cv, el["text"], x, y + (1 - ease(p)) * 24, size, CW, col(el.get("color")), ease(p),
              el.get("align", "left"), kind=kind, acc_kind=ak)


def h_bignum(el):
    return int(el.get("size", 190) * 1.25) + 70


def d_bignum(cv, el, x, y, p, seed):
    size = el.get("size", 190)
    c = col(el.get("color"), CRIMSON)
    v = el["value"] * ease(p * 1.1)
    s = fmt_num(v, el)
    draw_text(cv, s, W / 2, y + size * 0.95, "serif", size, c, clamp(p * 3), "center")
    if el.get("label"):
        draw_text(cv, el["label"], W / 2, y + size * 1.25 + 34, "sansb", 34, GRAY, clamp(p * 2), "center")


def h_bars(el):
    return el.get("height", 640) + 110


def d_bars(cv, el, x, y, p, seed):
    items = el["items"]
    n = len(items)
    hh = el.get("height", 640)
    top = y + 60
    base = top + hh - 60
    vmax = el.get("max") or max(i["value"] for i in items)
    slot = CW / n
    bw = min(190, slot * 0.62)
    wob_line(cv, x, base, x + CW, base, INK, 4, seed)
    for i, it in enumerate(items):
        c = col(it.get("color"), TEAL)
        q = ease(clamp(p * (n + 0.8) - i * 0.9))
        bh = (hh - 130) * it["value"] / vmax * q
        bx = x + slot * i + (slot - bw) / 2
        hatch_rect(cv, bx, base - bh, bw, bh, c, 1.0)
        if bh > 4:
            wob_rect(cv, bx, base - bh, bw, bh, c, 3.5, seed + i * 7)
        if q > 0.55:
            draw_text(cv, it.get("display", str(it["value"])), bx + bw / 2, base - bh - 18, "serifb", 46, c,
                      clamp((q - .55) * 3), "center")
        lab = it.get("label", "")
        for k, part in enumerate(lab.split("\n")):
            draw_text(cv, part, bx + bw / 2, base + 46 + k * 36, "sansb", 30, GRAY, clamp(q * 2), "center")


def h_line(el):
    return el.get("height", 640) + 120


def d_line(cv, el, x, y, p, seed):
    pts = el["points"]
    n = len(pts)
    hh = el.get("height", 640)
    c = col(el.get("color"), CRIMSON)
    top = y + 70
    base = top + hh - 70
    if el.get("title"):
        draw_text(cv, el["title"], x, y + 28, "sansb", 30, GRAY, clamp(p * 3))
    lo = el.get("min", min(pts)); hi = el.get("max", max(pts))
    pad = (hi - lo) * 0.08
    lo -= pad; hi += pad
    X = lambda i: x + 20 + (CW - 60) * i / (n - 1)
    Y = lambda v: base - (base - top - 40) * (v - lo) / (hi - lo)
    wob_line(cv, x, base + 14, x + CW, base + 14, INK, 3.5, seed)
    ref = el.get("ref")
    if ref:
        ry = Y(ref["value"])
        k = 0
        while k < CW:
            cv.drawLine(x + k, ry, x + min(k + 18, CW), ry, paint(TEAL, 0.9, 3))
            k += 32
        draw_text(cv, ref["label"], x + CW, ry - 14, "sansb", 30, TEAL, 1, "right")
    path = skia.Path()
    total = (n - 1) * clamp(p / 0.85)
    path.moveTo(X(0), Y(pts[0]))
    for i in range(1, n):
        if i <= total:
            path.lineTo(X(i), Y(pts[i]))
        elif i - 1 < total:
            f = total - (i - 1)
            path.lineTo(X(i - 1) + (X(i) - X(i - 1)) * f, Y(pts[i - 1]) + (Y(pts[i]) - Y(pts[i - 1])) * f)
    cv.drawPath(path, paint(c, 1.0, 8))
    labels = el.get("labels")
    if labels:
        for i, lb in enumerate(labels):
            if lb and i <= total + 0.2:
                draw_text(cv, lb, X(i), base + 62, "sansb", 28, GRAY, 1, "center")
    if el.get("dots"):
        for i in range(n):
            if i <= total:
                cv.drawCircle(X(i), Y(pts[i]), 9, paint(c, 1.0))
                if el.get("point_labels") and el["point_labels"][i]:
                    draw_text(cv, el["point_labels"][i], X(i), Y(pts[i]) - 24, "sansb", 30, INK, 1, "center")
    if el.get("end_label") and p > 0.9:
        a = clamp((p - 0.9) * 10)
        ex, ey = X(n - 1), Y(pts[-1])
        cv.drawCircle(ex, ey, 12, paint(c, a))
        draw_text(cv, el["end_label"], ex - 10, ey - 30, "serifb", 54, c, a, "right")


def h_tags(el):
    return len(el["items"]) * 120 + 20


def d_tags(cv, el, x, y, p, seed):
    items = el["items"]
    n = len(items)
    for i, it in enumerate(items):
        q = ease(clamp(p * n - i))
        if q <= 0:
            continue
        c = col(it.get("color"), TEAL)
        tx = x - (1 - q) * 500
        ty = y + i * 120
        w, h = 560, 96
        path = skia.Path()
        path.moveTo(tx + 44, ty); path.lineTo(tx + w, ty); path.lineTo(tx + w, ty + h); path.lineTo(tx + 44, ty + h)
        path.lineTo(tx, ty + h / 2); path.close()
        cv.save(); cv.clipPath(path, doAntiAlias=True)
        hatch_rect(cv, tx, ty, w, h, c, q, tint=0.22, gap=10)
        cv.restore()
        cv.drawPath(path, paint(c, q, 4))
        cv.drawCircle(tx + 40, ty + h / 2, 7, paint(c, q, 3))
        draw_text(cv, it["text"], tx + 90, ty + 66, "serifb", 52, INK, q)


def h_dots(el):
    cols = el.get("cols", 20)
    rows = math.ceil(el["n"] / cols)
    sq = CW / cols
    return int(rows * sq) + 100


def d_dots(cv, el, x, y, p, seed):
    n = el["n"]; cols = el.get("cols", 20); hl = el.get("hl", 0)
    sq = CW / cols
    c = col(el.get("color"), GOLD)
    build = clamp(p / 0.55)
    for i in range(n):
        if i > build * n:
            break
        r, k = divmod(i, cols)
        gx, gy = x + k * sq + 3, y + r * sq + 3
        is_hl = i >= n - hl and p > 0.6
        if is_hl:
            hatch_rect(cv, gx, gy, sq - 6, sq - 6, c, 1.0, tint=0.35, gap=7)
        cv.drawRect(skia.Rect.MakeXYWH(gx, gy, sq - 6, sq - 6), paint(c if is_hl else INK, 0.9 if is_hl else 0.5, 2))
    if el.get("label"):
        rows = math.ceil(n / cols)
        draw_text(cv, el["label"], W / 2, y + rows * sq + 56, "sansb", 32, GRAY, clamp(p * 2), "center")


def h_coins(el):
    per = el.get("per_row", 10)
    return math.ceil(el["n"] / per) * 74 + 90


def d_coins(cv, el, x, y, p, seed):
    n = el["n"]; per = el.get("per_row", 10)
    c = col(el.get("color"), GOLD)
    r = 33
    shown = int(n * clamp(p / 0.85))
    for i in range(shown):
        rr, k = divmod(i, per)
        cx = x + 40 + k * (CW - 80) / (per - 1)
        cy = y + 40 + rr * 74
        hatch_circle(cv, cx, cy, r, c)
        draw_text(cv, el.get("symbol", "$"), cx, cy + 12, "serifb", 34, c, 1, "center")
    if el.get("label"):
        rows = math.ceil(n / per)
        draw_text(cv, el["label"], W / 2, y + rows * 74 + 50, "serifb", 46, col(el.get("label_color"), CRIMSON),
                  clamp((p - 0.8) * 5), "center")


def h_steps(el):
    return sum(max(1, rich_height(s, el.get("size", 46), CW - 110) // 1) + 44 for s in el["items"])


def d_steps(cv, el, x, y, p, seed):
    items = el["items"]; n = len(items); size = el.get("size", 46)
    yy = y
    for i, s in enumerate(items):
        q = ease(clamp(p * n - i))
        hh = rich_height(s, size, CW - 110)
        if q > 0:
            cv.drawCircle(x + 36, yy + 42, 34, paint(CRIMSON, q, 4))
            draw_text(cv, str(i + 1), x + 36, yy + 58, "serifi", 44, CRIMSON, q, "center")
            draw_rich(cv, s, x + 100, yy + (1 - q) * 20 + 8, size, CW - 110, INK, q)
        yy += hh + 44


def h_compare(el):
    return 300


def d_compare(cv, el, x, y, p, seed):
    for side, cx in (("left", x + CW * 0.25), ("right", x + CW * 0.75)):
        it = el[side]
        c = col(it.get("color"), CRIMSON if side == "right" else GRAY)
        q = ease(clamp(p * 1.3 - (0.25 if side == "right" else 0)))
        v = it["value"] * q
        draw_text(cv, it.get("title", ""), cx, y + 30, "sansb", 32, GRAY, clamp(q * 3), "center")
        draw_text(cv, fmt_num(v, it), cx, y + 175, "serifb", it.get("size", 104), c, clamp(q * 3), "center")
        if it.get("sub"):
            draw_text(cv, it["sub"], cx, y + 235, "sansb", 32, c, clamp(q * 2), "center")
    draw_text(cv, el.get("mid", "vs"), x + CW / 2, y + 160, "serifi", 54, GRAY, clamp(p * 3), "center")


def h_callout(el):
    return rich_height(el["text"], el.get("size", 50), CW - 80) + 60


def d_callout(cv, el, x, y, p, seed):
    q = ease(p)
    hh = rich_height(el["text"], el.get("size", 50), CW - 80) + 24
    hatch_rect(cv, x, y, 18, hh, GOLD, q, tint=0.5, gap=7)
    wob_line(cv, x + 18, y, x + 18, y + hh, GOLD, 3, seed, q)
    draw_rich(cv, el["text"], x + 50, y + 8 + (1 - q) * 20, el.get("size", 50), CW - 80, INK, q)


# ---------------------------------------------------------------- hand-drawn illustrations
class Sk:
    """Collects wobbly ink strokes and hatched fills for one illustration in a 100x100 unit box."""
    def __init__(self, ox, oy, size, seed):
        self.ox, self.oy, self.s = ox, oy, size / 100.0
        self.r = random.Random(seed)
        self.ink, self.fills = [], []

    def P(self, x, y, j=0.5):
        return (self.ox + (x + self.r.uniform(-j, j)) * self.s, self.oy + (y + self.r.uniform(-j, j)) * self.s)

    def line(self, x0, y0, x1, y1):
        a, b = self.P(x0, y0), self.P(x1, y1)
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        o = self.r.uniform(-1, 1) * self.s
        path = skia.Path()
        path.moveTo(*a)
        path.quadTo((a[0] + b[0]) / 2 - dy / L * o, (a[1] + b[1]) / 2 + dx / L * o, *b)
        self.ink.append(path)

    def poly(self, pts, close=False):
        for i in range(len(pts) - (0 if close else 1)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            self.line(x0, y0, x1, y1)

    def rect(self, x, y, w, h):
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)

    def ellipse(self, cx, cy, rx, ry, n=18, a0=0.0, a1=2 * math.pi, closed=True):
        pts = []
        for i in range(n + (0 if closed else 1)):
            a = a0 + (a1 - a0) * i / n
            k = 1 + self.r.uniform(-0.015, 0.015)
            pts.append(self.P(cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k, 0.2))
        path = skia.Path()
        if closed:
            mids = [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2) for i in range(n)]
            path.moveTo(*mids[-1])
            for i in range(n):
                path.quadTo(pts[i][0], pts[i][1], *mids[i])
        else:
            path.moveTo(*pts[0])
            for q in pts[1:]:
                path.lineTo(*q)
        self.ink.append(path)

    def circle(self, cx, cy, r):
        self.ellipse(cx, cy, r, r)

    def arc(self, cx, cy, rx, ry, a0, a1):
        self.ellipse(cx, cy, rx, ry, 10, math.radians(a0), math.radians(a1), False)

    def fill_poly(self, pts, c):
        path = skia.Path()
        path.moveTo(*self.P(*pts[0], 0))
        for q in pts[1:]:
            path.lineTo(*self.P(*q, 0))
        path.close()
        self.fills.append((path, c))

    def fill_rect(self, x, y, w, h, c):
        self.fill_poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], c)

    def fill_ellipse(self, cx, cy, rx, ry, c):
        self.fill_poly([(cx + math.cos(a * math.pi / 8) * rx, cy + math.sin(a * math.pi / 8) * ry) for a in range(16)], c)


def hatch_path(cv, path, c, a, gap):
    b = path.getBounds()
    l, t, r, bt = b.left(), b.top(), b.right(), b.bottom()
    cv.save()
    cv.clipPath(path, doAntiAlias=True)
    cv.drawPath(path, paint(c, a * 0.22))
    hp = paint(c, a * 0.8, 2.2)
    k = -(bt - t)
    while k < (r - l) + (bt - t):
        cv.drawLine(l + k, bt, l + k + (bt - t), t, hp)
        k += gap
    cv.restore()


def cyl(b, cx, top, rx, ry, h, ridges, c):
    b.ellipse(cx, top, rx, ry)
    b.line(cx - rx, top, cx - rx, top + h)
    b.line(cx + rx, top, cx + rx, top + h)
    b.arc(cx, top + h, rx, ry, 0, 180)
    for i in range(1, ridges):
        b.arc(cx, top + h * i / ridges, rx, ry, 0, 180)
    b.fill_rect(cx - rx + 1, top, 2 * rx - 2, h, c)


def ill_bank(b, c, p):
    b.poly([(6, 34), (50, 8), (94, 34)], True)
    b.line(8, 38, 92, 38)
    b.circle(50, 24, 5)
    for x in (18, 34, 50, 66, 82):
        b.rect(x - 5, 44, 10, 34)
    b.rect(8, 78, 84, 6)
    b.rect(3, 84, 94, 7)
    b.fill_poly([(14, 33), (50, 12), (86, 33)], c)
    b.fill_rect(9, 79, 82, 4, c)


def ill_coins(b, c, p):
    cyl(b, 30, 38, 18, 6, 44, 5, c)
    cyl(b, 72, 62, 16, 5.5, 20, 3, c)
    b.ellipse(30, 38, 11, 3.6)
    b.ellipse(72, 62, 9.5, 3.2)


def ill_house(b, c, p):
    b.poly([(8, 46), (50, 12), (92, 46)], True)
    b.rect(18, 46, 64, 42)
    b.rect(44, 62, 14, 26)
    b.rect(25, 56, 12, 12)
    b.rect(63, 56, 12, 12)
    b.rect(68, 18, 9, 16)
    b.fill_poly([(12, 45), (50, 16), (88, 45)], c)
    b.fill_rect(45, 63, 12, 24, c)


def ill_thermo(b, c, p):
    b.line(41, 14, 41, 68)
    b.line(59, 14, 59, 68)
    b.arc(50, 14, 9, 9, 180, 360)
    b.circle(50, 81, 14)
    for i, y in enumerate((22, 32, 42, 52, 62)):
        b.line(26 if i % 2 == 0 else 30, y, 36, y)
    lvl = 66 - 50 * clamp(p / 0.9)
    b.fill_rect(46, lvl, 8, 72 - lvl, c)
    b.fill_ellipse(50, 81, 9.5, 9.5, c)


def ill_scale(b, c, p):
    b.line(50, 16, 50, 86)
    b.rect(32, 86, 36, 5)
    b.circle(50, 14, 3.5)
    b.line(12, 30, 88, 22)
    for (x, y) in ((12, 30), (88, 22)):
        b.line(x, y, x - 10, y + 26)
        b.line(x, y, x + 10, y + 26)
        b.arc(x, y + 26, 10, 7, 0, 180)
    b.fill_poly([(2, 56), (22, 56), (12, 63)], c)
    b.fill_poly([(78, 48), (98, 48), (88, 55)], c)


def ill_chart(b, c, p, down=False):
    b.line(10, 8, 10, 88)
    b.line(10, 88, 94, 88)
    hs = (46, 34, 22, 12) if down else (14, 28, 42, 58)
    for i, h in enumerate(hs):
        x = 22 + i * 18
        b.rect(x, 88 - h, 11, h)
        b.fill_rect(x + 1, 89 - h, 9, h - 1, c)
    if down:
        b.poly([(14, 22), (36, 36), (54, 30), (88, 64)])
        b.line(88, 64, 76, 62)
        b.line(88, 64, 86, 52)
    else:
        b.poly([(14, 62), (36, 48), (54, 54), (88, 18)])
        b.line(88, 18, 76, 20)
        b.line(88, 18, 86, 30)


def ill_chart_down(b, c, p):
    ill_chart(b, c, p, True)


def ill_barrel(b, c, p):
    b.line(26, 40, 26, 86)
    b.line(74, 40, 74, 86)
    b.ellipse(50, 40, 24, 7)
    b.arc(50, 86, 24, 7, 0, 180)
    b.arc(50, 56, 24, 7, 0, 180)
    b.arc(50, 72, 24, 7, 0, 180)
    b.fill_rect(27, 40, 46, 46, c)
    b.poly([(50, 2), (58, 14), (60, 20), (56, 26), (50, 28), (44, 26), (40, 20), (42, 14)], True)
    b.fill_poly([(50, 6), (56, 15), (56, 22), (50, 26), (44, 22), (44, 15)], INK)


def ill_jar(b, c, p):
    b.rect(28, 10, 44, 8)
    b.poly([(32, 18), (32, 28), (22, 38), (22, 86), (78, 86), (78, 38), (68, 28), (68, 18)])
    for (x, y, rx) in ((38, 80, 11), (60, 80, 11), (49, 73, 11), (38, 66, 10), (60, 66, 10)):
        b.ellipse(x, y, rx, 3.6)
        b.fill_ellipse(x, y, rx - 1, 3, c)
    q = clamp(p)
    cy = -26 + 36 * q
    if q < 0.98:
        b.circle(50, cy, 7)
        b.fill_ellipse(50, cy, 6, 6, c)


def ill_cart(b, c, p):
    b.poly([(6, 14), (20, 14), (30, 62)])
    b.poly([(22, 30), (90, 30), (80, 62), (30, 62)], True)
    for x in (40, 54, 68):
        b.line(x, 30, x - 2, 62)
    b.line(24, 46, 85, 46)
    b.circle(38, 76, 6)
    b.circle(72, 76, 6)
    b.fill_poly([(23, 31), (89, 31), (79, 61), (31, 61)], c)


def ill_ballot(b, c, p):
    b.rect(18, 46, 64, 42)
    b.line(34, 54, 66, 54)
    b.rect(36, 12, 28, 36)
    b.line(42, 20, 58, 20)
    b.poly([(42, 33), (48, 40), (59, 26)])
    b.fill_rect(19, 47, 62, 40, c)


def ill_envelope(b, c, p):
    b.rect(10, 24, 80, 54)
    b.poly([(10, 24), (50, 54), (90, 24)])
    b.rect(66, 58, 16, 14)
    b.fill_rect(67, 59, 14, 12, c)


def ill_clock(b, c, p):
    b.circle(50, 50, 38)
    b.circle(50, 50, 33)
    for i in range(12):
        a = math.radians(i * 30)
        b.line(50 + math.sin(a) * 28, 50 - math.cos(a) * 28, 50 + math.sin(a) * 32, 50 - math.cos(a) * 32)
    b.line(50, 50, 50, 26)
    b.line(50, 50, 66, 58)
    b.circle(50, 50, 3)
    b.fill_ellipse(50, 50, 6, 6, c)
    b.fill_poly([(50, 50), (50, 26), (56, 27), (66, 58)], c)


def ill_calendar(b, c, p):
    b.rect(12, 18, 76, 70)
    b.rect(12, 18, 76, 16)
    b.line(32, 10, 32, 26)
    b.line(68, 10, 68, 26)
    b.fill_rect(13, 19, 74, 14, c)
    for r in range(3):
        for k in range(4):
            if (r, k) != (2, 2):
                b.circle(26 + k * 16, 48 + r * 13, 2)
    b.circle(58, 74, 8.5)


def ill_globe(b, c, p):
    b.circle(50, 50, 38)
    b.ellipse(50, 50, 16, 38)
    b.line(12, 50, 88, 50)
    b.arc(50, 50, 38, 14, 0, 180)
    b.arc(50, 50, 38, 14, 180, 360)
    b.fill_ellipse(50, 50, 14, 36, c)


def ill_bill(b, c, p):
    b.rect(6, 26, 88, 48)
    b.rect(12, 32, 76, 36)
    b.circle(50, 50, 12)
    b.circle(22, 50, 4)
    b.circle(78, 50, 4)
    b.fill_ellipse(50, 50, 10, 10, c)


def ill_skyline(b, c, p):
    r = random.Random(7)
    b.windows = []
    b.anim = [("cloud", 31)]
    x = 0
    spec = [(11, 30), (9, 42), (13, 34), (8, 50), (12, 38), (10, 56), (9, 44), (13, 32), (11, 48), (10, 36)]
    for i, (w, h) in enumerate(spec):
        top = 96 - h
        b.rect(x, top, w, h)
        if i % 3 == 1:
            b.line(x + w / 2, top, x + w / 2, top - 7)
        for yy in range(int(top + 4), 92, 6):
            for xx in (x + 2, x + w / 2 - 0.8, x + w - 3.6):
                if r.random() < 0.8:
                    b.windows.append((xx, yy, 1.6, 2.6))
        if i % 2 == 0:
            b.fill_rect(x + 0.5, top + 0.5, w - 1, h - 1, c)
        x += w + 1
    b.line(0, 97, 100, 97)
    b.line(0, 99, 100, 99)


def bd_port(b, c, p):
    b.windows = []
    b.anim = [("wave", 91, 0, 100), ("hook", 80, 56, 76), ("cloud", 31)]
    b.poly([(3, 90), (62, 90), (68, 78), (0, 78)], True)
    b.fill_poly([(4, 89), (61, 89), (66, 79), (2, 79)], c)
    for k, (x, col_) in enumerate(((8, 1), (22, 0), (36, 1), (50, 0))):
        b.rect(x, 66, 12, 12)
        b.line(x + 4, 66, x + 4, 78)
        b.line(x + 8, 66, x + 8, 78)
        if col_:
            b.fill_rect(x + 0.5, 66.5, 11, 11, c)
    for x in (10, 24, 38):
        b.rect(x, 54, 12, 12)
        b.line(x + 6, 54, x + 6, 66)
    b.rect(70, 46, 4, 44)
    b.rect(92, 46, 4, 44)
    b.rect(54, 42, 46, 4)
    b.line(54, 42, 40, 52)
    b.line(54, 46, 40, 52)
    b.line(70, 56, 96, 56)
    b.line(70, 72, 96, 72)
    b.rect(76, 76, 9, 7)
    b.rect(86, 83, 9, 7)
    b.rect(76, 83, 9, 7)
    b.fill_rect(76.5, 76.5, 8, 6, c)
    b.line(0, 91, 100, 91)


def bd_oil(b, c, p):
    b.windows = []
    b.anim = [("beam", 26, 66, 20, 12), ("beam", 62, 70, 16, 12), ("cloud", 31)]
    b.line(0, 97, 100, 97)
    for (x, hh) in ((26, 31), (62, 27)):
        b.poly([(x - 8, 97), (x, 97 - hh), (x + 8, 97)], True)
        b.line(x - 5, 97 - hh * 0.35, x + 5, 97 - hh * 0.35)
        b.circle(x, 97 - hh - 2, 2)
    b.poly([(84, 97), (88, 50), (92, 97)])
    for yy in (60, 72, 84):
        b.line(86 - (84 - yy) * 0, yy, 90, yy + 0)
    b.line(85, 84, 91, 72)
    b.line(91, 84, 85, 72)
    cyl(b, 44, 78, 8, 3, 19, 3, c)
    cyl(b, 10, 82, 7, 2.6, 15, 3, c)


def bd_suburb(b, c, p):
    r = random.Random(11)
    b.windows = []
    b.anim = [("smoke", 29, 56), ("cloud", 31)]
    x = 0
    for i, (w, h) in enumerate(((22, 24), (18, 30), (24, 26), (20, 32))):
        top = 97 - h
        b.rect(x + 2, top, w - 4, h)
        b.poly([(x, top), (x + w / 2, top - 10), (x + w, top)], True)
        b.rect(x + w / 2 - 2, 97 - 12, 4, 12)
        if i == 1:
            b.rect(x + w - 6, top - 8, 3, 8)
        b.windows.append((x + 4, top + 6, 3, 4))
        b.windows.append((x + w - 8, top + 6, 3, 4))
        if i % 2 == 0:
            b.fill_poly([(x + 1, top - 0.5), (x + w / 2, top - 9), (x + w - 1, top - 0.5)], c)
        x += w + 3
    b.line(0, 97, 100, 97)
    b.circle(97, 82, 6)
    b.line(97, 88, 97, 97)


def bd_factory(b, c, p):
    b.windows = []
    b.anim = [("smoke", 18, 38), ("smoke", 34, 44), ("cloud", 31)]
    b.line(0, 97, 100, 97)
    for x in (15, 31):
        b.rect(x, 48, 6, 49)
        b.line(x, 54, x + 6, 54)
        b.fill_rect(x + 0.5, 48.5, 5, 5, c)
    b.poly([(46, 97), (46, 70), (58, 80), (58, 70), (70, 80), (70, 70), (82, 80), (82, 70), (94, 80), (94, 97)], True)
    b.fill_rect(47, 82, 46, 14, c)
    for x in (50, 64, 78):
        b.windows.append((x, 86, 6, 4))
        b.rect(x, 86, 6, 4)
    b.rect(4, 82, 20, 15)
    b.rect(36, 88, 8, 9)


def bd_farm(b, c, p):
    b.windows = []
    b.anim = [("cloud", 31), ("cloud2", 35)]
    b.circle(84, 18, 7)
    for a in range(8):
        an = a * math.pi / 4
        b.line(84 + math.cos(an) * 10, 18 + math.sin(an) * 10, 84 + math.cos(an) * 14, 18 + math.sin(an) * 14)
    b.rect(14, 58, 26, 22)
    b.poly([(10, 60), (27, 46), (44, 60)], True)
    b.rect(23, 66, 8, 14)
    b.fill_poly([(11, 59), (27, 47), (43, 59)], c)
    cyl(b, 54, 54, 6, 2.2, 30, 5, c)
    for i, y in enumerate((84, 88, 92, 96)):
        b.line(0, y, 100, y - 2 + (i % 2) * 2)
    for xx in range(6, 98, 9):
        b.line(xx, 97, xx + 3, 90)
        b.line(xx + 3, 97, xx + 6, 91)


ILL = {
    "bank": (ill_bank, GOLD), "coins": (ill_coins, GOLD), "house": (ill_house, GOLD), "thermometer": (ill_thermo, CRIMSON),
    "scale": (ill_scale, GOLD), "chart": (ill_chart, GOLD), "chart_down": (ill_chart_down, CRIMSON),
    "barrel": (ill_barrel, TEAL), "jar": (ill_jar, GOLD), "cart": (ill_cart, TEAL), "ballot": (ill_ballot, TEAL),
    "envelope": (ill_envelope, GOLD), "clock": (ill_clock, TEAL), "calendar": (ill_calendar, CRIMSON),
    "globe": (ill_globe, TEAL), "bill": (ill_bill, GREEN), "skyline": (ill_skyline, GRAY), "bd_port": (bd_port, GRAY), "bd_oil": (bd_oil, GRAY), "bd_suburb": (bd_suburb, GRAY), "bd_factory": (bd_factory, GRAY), "bd_farm": (bd_farm, GRAY),
}


def draw_sketch(cv, name, cx, top, size, p, seed, t=0.0, color=None, ink_w=None, alpha=0.95):
    fn, dc = ILL[name]
    c = col(color, dc) if color else dc
    bob = math.sin(t * 2.2) * size * 0.012 if p >= 1 else 0
    b = Sk(cx - size / 2, top + bob, size, seed)
    fn(b, c, p)
    meas = []
    for pa in b.ink:
        meas.append(skia.PathMeasure(pa, False).getLength())
    total = sum(meas) or 1
    upto = total * clamp(p / 0.72)
    ink = paint(INK, alpha, ink_w or max(2.6, size * 0.011))
    acc = 0.0
    for pa, L in zip(b.ink, meas):
        if acc >= upto:
            break
        rem = upto - acc
        if rem >= L:
            cv.drawPath(pa, ink)
        else:
            dst = skia.Path()
            skia.PathMeasure(pa, False).getSegment(0, rem, dst, True)
            cv.drawPath(dst, ink)
        acc += L
    fa = clamp((p - 0.5) / 0.35)
    if fa > 0:
        for path, fc in b.fills:
            hatch_path(cv, path, fc, fa, max(7, size * 0.024))
    return b


def h_sketch(el):
    return int(el.get("size", 380) * 0.97) + (60 if el.get("caption") else 20)


def d_sketch(cv, el, x, y, p, seed):
    size = el.get("size", 380)
    draw_sketch(cv, el["name"], W / 2, y, size, p, seed, el.get("_t", 0), el.get("color"))
    if el.get("caption"):
        draw_text(cv, el["caption"], W / 2, y + size * 0.97 + 38, "sansb", 32, GRAY, clamp((p - 0.5) * 3), "center")


ELS = {
    "text": (h_text, d_text), "bignum": (h_bignum, d_bignum), "bars": (h_bars, d_bars), "line": (h_line, d_line),
    "tags": (h_tags, d_tags), "dots": (h_dots, d_dots), "coins": (h_coins, d_coins), "steps": (h_steps, d_steps),
    "compare": (h_compare, d_compare), "callout": (h_callout, d_callout),
    "sketch": (h_sketch, d_sketch),
}
ELDUR = {"line": 1.8, "bars": 1.6, "dots": 2.2, "coins": 2.2, "tags": 1.4, "steps": 1.6, "bignum": 1.4, "compare": 1.4, "sketch": 2.4}

# ---------------------------------------------------------------- scenes
_BG = None


def bg_image():
    global _BG
    if _BG is None:
        s = skia.Surface(W, H)
        c = s.getCanvas()
        c.clear(sk(PAPER))
        lp = paint((205, 214, 226), 0.55, 2)
        for yy in range(150, H, 64):
            c.drawLine(0, yy, W, yy, lp)
        c.drawLine(MARGIN - 30, 0, MARGIN - 30, H, paint((225, 160, 160), 0.35, 2))
        _BG = s.makeImageSnapshot()
    return _BG


def brand_tag(cv, text, x, y, a=1.0):
    f = font("serifi", 34)
    w = text_w(text, f) + 40
    hatch_rect(cv, x, y, w, 58, GOLD, a, tint=0.5, gap=8)
    wob_rect(cv, x, y, w, 58, GOLD, 3, 5, a)
    cv.drawString(text, x + 20, y + 40, f, paint(INK, a))


def plan_scene(sc, dur_audio):
    """Return list of (element, start_time)"""
    els = sc.get("elements", [])
    say = sc.get("say", "")
    n = len(els)
    plan = []
    for i, el in enumerate(els):
        cue = el.get("cue")
        if "at" in el:
            t = el["at"]
        elif cue and cue.lower() in say.lower():
            frac = say.lower().index(cue.lower()) / max(1, len(say))
            t = LEAD + 0.15 + frac * dur_audio
        else:
            t = LEAD + 0.5 + (0.1 + 0.62 * i / max(1, n)) * dur_audio
        plan.append((el, t))
    return plan


def draw_backdrop(cv, name, t):
    zt = 1.0 + 0.05 * clamp(t / 7.0)
    cv.save()
    cv.translate(W / 2, 1590)
    cv.scale(zt, zt)
    cv.translate(-W / 2, -1590)
    bb = draw_sketch(cv, name, W / 2, 1590 - 1080 * 0.99, 1080, clamp((t - 0.05) / 1.6), 4242, t, "gray", ink_w=2.2, alpha=0.7)
    X = lambda x: bb.ox + x * bb.s
    Y = lambda y: bb.oy + y * bb.s
    if t > 1.4:
        for (wx, wy, ww, wh) in bb.windows:
            ph = (wx * 7.3 + wy * 3.1) % 6.28
            if math.sin(t * 1.6 + ph) > 0.55:
                cv.drawRect(skia.Rect.MakeXYWH(X(wx), Y(wy), ww * bb.s, wh * bb.s), paint(GOLD, 0.85))
        gp = paint(GRAY, 0.75, 2.2)
        for an in bb.anim:
            k = an[0]
            if k == "smoke":
                for j in range(4):
                    ph = ((t * 0.35 + j * 0.25) % 1.0)
                    cv.drawCircle(X(an[1] + math.sin(ph * 5 + j) * 2 + ph * 6), Y(an[2] - ph * 24), (1.4 + ph * 3.2) * bb.s, paint(GRAY, 0.7 * (1 - ph), 2.2))
            elif k == "wave":
                for j in range(3):
                    pa = skia.Path()
                    for i in range(0, 41):
                        xx = an[2] + (an[3] - an[2]) * i / 40
                        yy = an[1] + j * 2.4 + math.sin(xx * 0.5 + t * 2 + j) * 0.7
                        (pa.moveTo if i == 0 else pa.lineTo)(X(xx), Y(yy))
                    cv.drawPath(pa, gp)
            elif k == "hook":
                yy = an[2] + (an[3] - an[2]) * (0.5 + 0.5 * math.sin(t * 1.1))
                cv.drawLine(X(an[1]), Y(46), X(an[1]), Y(yy), gp)
                cv.drawRect(skia.Rect.MakeXYWH(X(an[1]) - 3 * bb.s, Y(yy), 6 * bb.s, 4 * bb.s), paint(GOLD, 0.9))
            elif k == "beam":
                ang = math.sin(t * 2.2) * math.radians(an[4])
                px, py, L = an[1], an[2], an[3]
                ex, ey = px + math.cos(ang) * L, py - 5 + math.sin(ang) * L * 0.5
                bx, by = px - math.cos(ang) * L * 0.5, py - 5 - math.sin(ang) * L * 0.25
                cv.drawLine(X(bx), Y(by), X(ex), Y(ey), paint(INK, 0.8, 3.2))
                cv.drawLine(X(ex), Y(ey), X(ex), Y(ey + 9 + math.sin(ang) * 3), gp)
            elif k in ("cloud", "cloud2"):
                cx = ((t * (2.2 if k == "cloud" else 1.5)) % 130) - 15
                cy = an[1]
                for dx, dy, r in ((0, 0, 4.5), (5, -1.5, 5.5), (10.5, 0, 4.2)):
                    cv.drawCircle(X(cx + dx), Y(cy + dy), r * bb.s, paint(GRAY, 0.5, 2.0))
    cv.restore()


def draw_scene_frame(cv, sc, idx, t, dur_audio, frame):
    cv.drawImage(bg_image(), 0, 0)
    seed = idx * 1000 + frame // 6
    kind = sc.get("type", "content")
    brand = sc.get("brand", "Market Ledger  ·  explained")
    art = sc.get("art")
    say = sc.get("say", "")
    if kind == "title":
        a = ease(t / 0.3)
        brand_tag(cv, brand, MARGIN, 250, a)
        y = 340
        hook = sc.get("hook")
        t_title = 0.0
        if hook:
            hs = 50
            hh_ = draw_rich(cv, hook, MARGIN, y, hs, CW, INK, 1.0, lh=1.22, reveal=clamp((t - 0.15) / 1.7))
            y += hh_ + 50
            cue = sc.get("title_cue", "")
            frac = say.lower().index(cue.lower()) / max(1, len(say)) if cue and cue.lower() in say.lower() else 0.45
            t_title = LEAD + frac * dur_audio
        ta = ease((t - t_title) / 0.3)
        size = sc.get("size", 112 if hook else 124)
        hh = rich_height(sc["h"], size, CW, 1.12)
        draw_rich(cv, sc["h"], MARGIN, y + (1 - ta) * 30, size, CW, INK, ta, lh=1.12, reveal=clamp((t - t_title) / 0.5))
        ysub = y + hh + 20
        if sc.get("sub"):
            draw_text(cv, sc["sub"], MARGIN, ysub + 40, "sans", 40, GRAY, ease((t - t_title - 0.3) / 0.3))
            ysub += 50
        bdn = sc.get("backdrop", "city")
        if art and bdn:
            name = {"city": "skyline", "true": "skyline"}.get(str(bdn).lower(), "bd_" + str(bdn))
            if name not in ILL:
                name = "skyline"
            # one animation at a time: the backdrop plays first, fades out, then the illustration is drawn
            bd_end = max(t_title, 2.6) if hook else 2.6
            bd_a = 1 - clamp((t - (bd_end - 0.6)) / 0.5)
            if bd_a > 0:
                cv.saveLayer(None, skia.Paint(Alpha=int(255 * bd_a)))
                draw_backdrop(cv, name, t)
                cv.restore()
        if art:
            top = ysub + 40
            sz = min(sc.get("art_size", 500), 1500 - top)
            art_start = (max(t_title, 2.6) if hook else 2.6) + 0.1 if bdn else (t_title if hook else 0) + 0.1
            draw_sketch(cv, art, W / 2, top, sz, clamp((t - art_start) / 1.1), seed, t, sc.get("art_color"))
        else:
            q = ease((t - 0.6) / 1.8)
            pts = [(MARGIN, 1330), (270, 1290), (410, 1310), (560, 1210), (700, 1230), (850, 1110), (990, 1040)]
            path = skia.Path(); path.moveTo(*pts[0])
            total = (len(pts) - 1) * q
            for i in range(1, len(pts)):
                if i <= total:
                    path.lineTo(*pts[i])
                elif i - 1 < total:
                    f = total - (i - 1)
                    path.lineTo(pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f)
            wob_line(cv, MARGIN, 1380, W - MARGIN, 1380, INK, 4, seed)
            cv.drawPath(path, paint(CRIMSON, 1.0, 9))
    else:
        a = ease(t / 0.45)
        brand_tag(cv, brand, MARGIN, 250, a * 0.9)
        hs = sc.get("hsize", 88 if art else 96)
        elist = plan_scene(sc, dur_audio)
        used = sum(ELS[e["type"]][0](e) + e.get("gap", 36) for e, _ in elist)
        hh_full = rich_height(sc["h"], hs, CW, 1.14) if sc.get("h") else 0
        y0 = 340 + hh_full + 70
        free = max(0, 1500 - (y0 + used))
        big = bool(art) and kind != "outro" and free >= 330
        if big:
            sz = int(min(480, free - 90))
            elist.append(({"type": "sketch", "name": art, "size": sz, "gap": 20, "color": sc.get("art_color")}, LEAD + 0.8))
        hw = CW if (big or not art or kind == "outro") else CW - 250
        hh = draw_rich(cv, sc["h"], MARGIN, 340 + (1 - a) * 24, hs, hw, INK, a, lh=1.14,
                       reveal=clamp(t / 0.7)) if sc.get("h") else 0
        y = 340 + (hh or 0) + 70
        if art and not big:
            if kind == "outro":
                draw_sketch(cv, art, W / 2, y - 20, 380, clamp((t - 0.2) / 2.2), seed, t, sc.get("art_color"))
                y += 380
            else:
                draw_sketch(cv, art, W - MARGIN - 112, 300, 224, clamp((t - 0.15) / 1.9), seed, t, sc.get("art_color"))
                y = max(y, 560)
        used = sum(ELS[e["type"]][0](e) + e.get("gap", 36) for e, _ in elist)
        free = max(0, 1500 - (y + used))
        extra = 0
        if kind == "outro":
            y += 10
        elif elist and not big:
            y += free * 0.3
            extra = min(110, free * 0.5 / len(elist))
        for el, st in elist:
            hfn, dfn = ELS[el["type"]]
            p = clamp((t - st) / ELDUR.get(el["type"], 0.7))
            ey = y + el.get("dy", 0)
            if p > 0:
                if el["type"] == "sketch":
                    el = dict(el, _t=t)
                dfn(cv, el, MARGIN, ey, p if el["type"] in ("line", "bars", "dots", "coins", "tags", "steps", "bignum", "compare", "sketch") else ease(p), seed)
            y += hfn(el) + el.get("gap", 36) + extra
    note = sc.get("note")
    if note:
        draw_text(cv, note, MARGIN, 1485, "sans", 24, GRAY, ease(t / 0.8))


def render_scene(args):
    sc, idx, dur, dur_audio, out = args
    surface = skia.Surface(W, H)
    cv = surface.getCanvas()
    n = int(round(dur * FPS))
    tmp = out + ".tmp.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-g", "60", "-r", str(FPS), tmp]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(n):
        draw_scene_frame(cv, sc, idx, f / FPS, dur_audio, f)
        pr.stdin.write(surface.makeImageSnapshot().tobytes())
    pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on scene {idx}")
    os.replace(tmp, out)
    return out


def png_preview(sc, idx, t, dur_audio, path):
    surface = skia.Surface(W, H)
    draw_scene_frame(surface.getCanvas(), sc, idx, t, dur_audio, int(t * FPS))
    surface.makeImageSnapshot().save(path, skia.kPNG)


# ---------------------------------------------------------------- audio
def ensure_models(d):
    os.makedirs(d, exist_ok=True)
    for name, remote in (("kokoro.onnx", "kokoro-v1.0.int8.onnx"), ("voices.bin", "voices-v1.0.bin")):
        p = os.path.join(d, name)
        if not os.path.exists(p) or os.path.getsize(p) < 1_000_000:
            subprocess.check_call(["curl", "-sL", "--fail", "-o", p + ".part", MODEL_URL + remote])
            os.replace(p + ".part", p)
    return os.path.join(d, "kokoro.onnx"), os.path.join(d, "voices.bin")


def synth(spec, wd, models):
    from kokoro_onnx import Kokoro
    import soundfile as sf
    m, v = ensure_models(models)
    k = Kokoro(m, v)
    voice = spec.get("voice", "am_liam")
    lang = "en-gb" if voice.startswith("b") else "en-us"
    speed = spec.get("speed", 0.88)
    durs = []
    for i, sc in enumerate(spec["scenes"]):
        samples, sr = k.create(sc["say"], voice=voice, speed=speed, lang=lang)
        sf.write(os.path.join(wd, f"a{i}.wav"), samples, sr)
        durs.append(len(samples) / sr)
    return durs, sr


def write_scene_audio(i, dur_audio, sr, dur, wd):
    import soundfile as sf
    x, _ = sf.read(os.path.join(wd, f"a{i}.wav"))
    out = np.zeros(int(round(dur * sr)), dtype=np.float32)
    s0 = int(LEAD * sr)
    out[s0:s0 + len(x)] = x
    sf.write(os.path.join(wd, f"s{i}.wav"), out, sr)


def main():
    a = sys.argv[1:]
    spec_path, out = a[0], a[1]
    models = a[a.index("--models") + 1] if "--models" in a else "/tmp/kokoro"
    prev = a[a.index("--preview") + 1] if "--preview" in a else None
    spec = json.load(open(spec_path))
    wd = "/tmp/mlv_work"
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    if prev:
        os.makedirs(prev, exist_ok=True)
    da, sr = synth(spec, wd, models)
    durs = [LEAD + d + TAIL for d in da]
    total = sum(durs)
    print(f"voice-over {sum(da):.1f}s, video {total:.1f}s, scenes: " + ", ".join(f"{d:.1f}" for d in durs))
    if total > 80:
        print(f"WARNING: video is {total:.0f}s, target is 60-75s - shorten the script")
    if prev:
        for i, sc in enumerate(spec["scenes"]):
            png_preview(sc, i, durs[i] - 0.8, da[i], os.path.join(prev, f"scene{i + 1}.png"))
        png_preview(spec["scenes"][0], 0, 1.6, da[0], os.path.join(prev, "cover.png"))
        if "--preview-only" in a:
            return
    if total < 60:
        sys.exit(f"ERROR: video is {total:.0f}s, must be at least 60s - write a longer script")
    for i in range(len(durs)):
        write_scene_audio(i, da[i], sr, durs[i], wd)
    jobs = [(sc, i, durs[i], da[i], os.path.join(wd, f"v{i}.mp4")) for i, sc in enumerate(spec["scenes"])]
    with Pool(max(1, min(2, os.cpu_count() or 1))) as pool:
        files = pool.map(render_scene, jobs)
    with open(os.path.join(wd, "list.txt"), "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    with open(os.path.join(wd, "wl.txt"), "w") as f:
        for i in range(len(durs)):
            f.write(f"file '{os.path.join(wd, f's{i}.wav')}'\n")
    subprocess.check_call(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(wd, "wl.txt"),
                           "-c:a", "aac", "-b:a", "192k", os.path.join(wd, "audio.m4a")])
    subprocess.check_call(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(wd, "list.txt"),
                           "-i", os.path.join(wd, "audio.m4a"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
                           "-movflags", "+faststart", "-shortest", out + ".tmp.mp4"])
    os.replace(out + ".tmp.mp4", out)
    print("OK", out, f"{total:.1f}s")


if __name__ == "__main__":
    main()
