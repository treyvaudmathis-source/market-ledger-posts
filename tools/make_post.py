#!/usr/bin/env python3
"""Render a Market Ledger carousel (PNG slides) and a 9:16 Reel (MP4) from a JSON spec.

Usage: python3 make_post.py spec.json OUTDIR
See spec_example.json for the format. Needs google-chrome, ffmpeg and npm (for fonts).
"""
import html, json, os, subprocess, sys

W, H = 1080, 1350
FONT_DIR = "/tmp/ledger-fonts"
GOLD = ("background:linear-gradient(180deg,#ffe36e 0%,#f5b800 100%);-webkit-background-clip:text;"
        "background-clip:text;color:transparent")
RED, GREEN = "#ff453a", "#30d158"
LOGO = ('<svg width="{s}" height="{s}" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="30" '
        'fill="#e23b2e" stroke="#f4f4f4" stroke-width="3"/><polygon points="32,14 46,34 37,34 37,50 27,50 27,34 '
        '18,34" fill="#ffd23f"/></svg>')


def esc(t):
    return html.escape(str(t), quote=False)


def ensure_fonts():
    base = f"{FONT_DIR}/node_modules/@fontsource"
    if not os.path.exists(base + "/anton/files/anton-latin-400-normal.woff2"):
        os.makedirs(FONT_DIR, exist_ok=True)
        subprocess.run(["npm", "init", "-y"], cwd=FONT_DIR, capture_output=True, check=True)
        subprocess.run(["npm", "i", "@fontsource/anton", "@fontsource/bebas-neue"], cwd=FONT_DIR,
                       capture_output=True, check=True)
    return base


def svg(h, inner):
    return (f'<svg viewBox="0 0 1080 {h}" aria-hidden="true" style="position:absolute;left:0;top:0;'
            f'width:1080px;height:{h}px">{inner}</svg>')


def divider(top, size):
    return (f'<div style="position:absolute;left:60px;right:60px;top:{top}px;display:flex;align-items:center;gap:26px">'
            f'<div style="flex:1;height:2px;background:#8a6d1f"></div>{LOGO.format(s=size)}'
            f'<div style="flex:1;height:2px;background:#8a6d1f"></div></div>')


def fade(top, height):
    return (f'<div style="position:absolute;left:0;top:{top}px;width:1080px;height:{height}px;'
            f'background:linear-gradient(180deg,rgba(5,7,13,0) 0%,#05070d 100%)"></div>')


def defs(c1="#16294f"):
    return (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c1}"/>'
            '<stop offset="1" stop-color="#05070d"/></linearGradient></defs>')


def grid(ys):
    return '<g stroke="#1f2f55" stroke-width="2">' + "".join(
        f'<line x1="0" y1="{y}" x2="1080" y2="{y}"/>' for y in ys) + "</g>"


# ---------- visuals (inner SVG, image area height h) ----------
def v_stat_chart(v, h):
    up = v.get("direction", "up") == "up"
    col = RED if v.get("color", "red") == "red" else GREEN
    base = [(60, 640), (190, 600), (300, 620), (420, 520), (540, 540), (660, 420), (780, 380), (900, 250), (1010, 170)]
    pts = base if up else [(x, 810 - y) for x, y in base]
    p = " ".join(f"{x},{y}" for x, y in pts)
    ex, ey = pts[-1]
    sky = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{860 - y}" fill="#0b1630"/>' for x, y, w in
                  [(0, 640, 90), (100, 590, 70), (180, 670, 110), (300, 560, 80), (390, 620, 100), (500, 520, 70),
                   (580, 610, 120), (710, 570, 80), (800, 650, 100), (910, 600, 80), (1000, 680, 80)])
    tx, ty = (60, 270) if up else (60, 270)
    return (defs("#0f2147") + f'<rect width="1080" height="{h}" fill="url(#bg)"/>' + grid([200, 320, 440, 560]) + sky +
            f'<polyline points="{p}" fill="none" stroke="{col}" stroke-opacity="0.25" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<polyline points="{p}" fill="none" stroke="{col}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{ex}" cy="{ey}" r="30" fill="{col}" fill-opacity="0.3"/><circle cx="{ex}" cy="{ey}" r="14" fill="{col}"/>'
            f'<text x="{tx}" y="{ty}" font-family="Anton, Impact, sans-serif" font-size="210" fill="#ffffff">{esc(v["stat"])}</text>'
            f'<text x="64" y="{ty + 60}" font-family="Bebas Neue, sans-serif" font-size="48" fill="#a9b8d6" letter-spacing="2">{esc(v["label"])}</text>')


def v_bars(v, h):
    items = v["items"]
    n = len(items)
    step = min(220, 560 // n)
    mx = max(i["value"] for i in items)
    out = defs() + f'<rect width="1080" height="{h}" fill="url(#bg)"/>'
    out += ('<defs><linearGradient id="br" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#b3261e"/>'
            '<stop offset="1" stop-color="#ff453a"/></linearGradient></defs>')
    for k, it in enumerate(items):
        y = 110 + step * k
        w = int(900 * it["value"] / mx)
        out += (f'<text x="90" y="{y}" font-family="Bebas Neue, sans-serif" font-size="46" fill="#ffffff" letter-spacing="2">{esc(it["label"])}</text>'
                f'<rect x="90" y="{y + 20}" width="{w}" height="82" rx="6" fill="url(#br)"/>')
    if v.get("footnote"):
        out += (f'<text x="90" y="{110 + step * n - 10}" font-family="Bebas Neue, sans-serif" font-size="32" '
                f'fill="#8592b0" letter-spacing="2">{esc(v["footnote"])}</text>')
    return out


def v_line(v, h):
    pts = v["points"]  # [{"label","value"}]
    vals = [p["value"] for p in pts]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 0.1
    lo, hi = lo - pad, hi + pad
    n = len(pts)
    xs = [120 + i * (840 // max(n - 1, 1)) for i in range(n)]
    ys = [int(190 + (hi - val) / (hi - lo) * 320) for val in vals]
    poly = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    out = defs() + f'<rect width="1080" height="{h}" fill="url(#bg)"/>'
    out += (f'<text x="90" y="85" font-family="Bebas Neue, sans-serif" font-size="50" fill="#ffffff" letter-spacing="3">{esc(v["title"])}</text>')
    if "ref" in v:
        ry = int(190 + (hi - v["ref"]["value"]) / (hi - lo) * 320)
        out += (f'<line x1="90" y1="{ry}" x2="990" y2="{ry}" stroke="#ffd23f" stroke-width="3" stroke-dasharray="14 12"/>'
                f'<text x="990" y="{ry - 12}" text-anchor="end" font-family="Bebas Neue, sans-serif" font-size="38" fill="#ffd23f" letter-spacing="2">{esc(v["ref"]["label"])}</text>')
    out += (f'<polyline points="{poly}" fill="none" stroke="{RED}" stroke-opacity="0.25" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<polyline points="{poly}" fill="none" stroke="{RED}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>')
    for i, (x, y) in enumerate(zip(xs, ys)):
        last = i == n - 1
        out += (f'<circle cx="{x}" cy="{y}" r="13" fill="#ffffff"/>'
                f'<text x="{x}" y="{y - 30}" text-anchor="middle" font-family="Anton, Impact, sans-serif" font-size="50" fill="{"#ffd23f" if last else "#ffffff"}">{esc(pts[i]["text"] if "text" in pts[i] else pts[i]["value"])}</text>'
                f'<text x="{x}" y="600" text-anchor="middle" font-family="Bebas Neue, sans-serif" font-size="38" fill="#a9b8d6" letter-spacing="1">{esc(pts[i]["label"])}</text>')
    return out


def v_big_stat(v, h):
    return (defs("#2a1210") + f'<rect width="1080" height="{h}" fill="url(#bg)"/>'
            '<defs><radialGradient id="gl" cx="0.5" cy="0.45" r="0.55"><stop offset="0" stop-color="#ff7a1a" stop-opacity="0.4"/>'
            '<stop offset="1" stop-color="#ff7a1a" stop-opacity="0"/></radialGradient></defs>'
            f'<rect width="1080" height="{h}" fill="url(#gl)"/>'
            f'<text x="540" y="150" text-anchor="middle" font-family="Bebas Neue, sans-serif" font-size="54" fill="#ffd23f" letter-spacing="4">{esc(v["top"])}</text>'
            f'<text x="540" y="470" text-anchor="middle" font-family="Anton, Impact, sans-serif" font-size="{v.get("size", 250)}" fill="#ffffff">{esc(v["value"])}</text>'
            f'<text x="540" y="580" text-anchor="middle" font-family="Bebas Neue, sans-serif" font-size="48" fill="#a9b8d6" letter-spacing="3">{esc(v.get("caption", ""))}</text>')


def v_candles(v, h):
    cs = [(120, 560, 760, 600, 710, RED), (260, 500, 720, 540, 670, GREEN), (400, 470, 650, 500, 610, RED),
          (540, 380, 620, 420, 570, GREEN), (680, 330, 520, 360, 490, GREEN), (820, 260, 470, 300, 420, RED),
          (960, 170, 380, 210, 350, GREEN)]
    out = (defs() + f'<rect width="1080" height="{h}" fill="url(#bg)"/>' + grid([220, 360, 500, 640]) +
           '<g stroke-width="6" stroke-linecap="round">')
    for x, wt, wb, bt, bb, c in cs:
        out += f'<line x1="{x}" y1="{wt}" x2="{x}" y2="{wb}" stroke="{c}"/><rect x="{x - 28}" y="{bt}" width="56" height="{bb - bt}" fill="{c}"/>'
    return out + "</g>"


def v_columns(v, h):
    cols = "".join(f'<rect x="{x}" y="296" width="62" height="330"/>' for x in [170, 262, 354, 446, 572, 664, 756, 848])
    return (defs() + f'<rect width="1080" height="{h}" fill="url(#bg)"/>'
            '<g fill="#9fb2d6"><polygon points="140,250 540,90 940,250"/>' + cols + "</g>"
            '<polygon points="230,240 540,125 850,240" fill="#0f1c38"/>'
            '<rect x="120" y="250" width="840" height="36" fill="#b7c6e4"/><rect x="120" y="626" width="840" height="30" fill="#b7c6e4"/>'
            '<rect x="90" y="656" width="900" height="30" fill="#8396bd"/><rect x="60" y="686" width="960" height="40" fill="#667aa5"/>'
            f'<text x="540" y="230" text-anchor="middle" font-family="Bebas Neue, sans-serif" font-size="46" fill="#ffd23f" letter-spacing="6">{esc(v.get("label", ""))}</text>')


VIS = {"stat_chart": v_stat_chart, "bars": v_bars, "line": v_line, "big_stat": v_big_stat,
       "candles": v_candles, "columns": v_columns}


# ---------- slide layouts ----------
def page(body):
    return body


def cover(s):
    title = s["title"]
    fs = 100 if len(title) <= 40 else 86
    return (svg(860, VIS["stat_chart"](s["visual"], 860)) + fade(600, 330) + divider(925, 64) +
            f'<div style="position:absolute;left:60px;right:60px;top:1000px;text-align:center;font-family:\'Anton\',Impact,sans-serif;'
            f'font-size:{fs}px;line-height:1.02;text-transform:uppercase;letter-spacing:1px;{GOLD}">{esc(title)}</div>')


def text_slide(s):
    label, body = s["label"], s["body"]
    lf = 128 if len(label) <= 15 else 104 if len(label) <= 19 else 88
    bf = 56 if len(body) <= 175 else 50
    src = (f'<div style="position:absolute;left:60px;right:60px;top:1295px;text-align:center;font-family:\'Bebas Neue\',sans-serif;'
           f'font-size:28px;letter-spacing:2px;color:#8592b0;text-transform:uppercase">{esc(s["source"])}</div>') if s.get("source") else ""
    return (svg(760, VIS[s["visual"]["type"]](s["visual"], 760)) + fade(500, 280) + divider(780, 48) +
            f'<div style="position:absolute;left:50px;right:50px;top:850px;text-align:center;font-family:\'Anton\',Impact,sans-serif;'
            f'font-size:{lf}px;line-height:1;text-transform:uppercase;{GOLD}">{esc(label)}</div>'
            f'<div style="position:absolute;left:60px;right:60px;top:990px;text-align:center;font-family:\'Bebas Neue\',Impact,sans-serif;'
            f'font-size:{bf}px;line-height:1.1;text-transform:uppercase;color:#ffffff">{esc(body)}</div>' + src)


def cta_slide(c):
    return (svg(860, VIS["candles"]({}, 860)) + fade(560, 340) + divider(880, 64) +
            f'<div style="position:absolute;left:50px;right:50px;top:945px;text-align:center;font-family:\'Anton\',Impact,sans-serif;'
            f'font-size:112px;line-height:1.02;text-transform:uppercase;{GOLD}">{esc(c["title"])}</div>'
            f'<div style="position:absolute;left:60px;right:60px;top:1195px;text-align:center;font-family:\'Bebas Neue\',Impact,sans-serif;'
            f'font-size:54px;line-height:1.1;text-transform:uppercase;color:#ffffff">{esc(c["sub"])}</div>')


def main(spec_path, out):
    spec = json.load(open(spec_path, encoding="utf-8"))
    fd = ensure_fonts()
    os.makedirs(out, exist_ok=True)
    css = (f"@font-face{{font-family:'Anton';src:url('file://{fd}/anton/files/anton-latin-400-normal.woff2')}}"
           f"@font-face{{font-family:'Bebas Neue';src:url('file://{fd}/bebas-neue/files/bebas-neue-latin-400-normal.woff2')}}"
           "body{margin:0;background:#05070d}")
    slides = [cover(spec["cover"])] + [text_slide(s) for s in spec["slides"]] + [cta_slide(spec["cta"])]
    for i, body in enumerate(slides, 1):
        p = f"{out}/s{i}.html"
        open(p, "w", encoding="utf-8").write(
            f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>"
            f'<div style="position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#05070d">{body}</div></body></html>')
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                        "--hide-scrollbars", f"--window-size={W},{H}", "--virtual-time-budget=3000",
                        f"--screenshot={out}/slide{i}.png", f"file://{p}"], capture_output=True, check=True)
    # Reel: 3s per slide on a 1080x1920 canvas, silent AAC track
    lst = f"{out}/list.txt"
    with open(lst, "w") as f:
        for i in range(1, len(slides) + 1):
            f.write(f"file 'slide{i}.png'\nduration 3\n")
        f.write(f"file 'slide{len(slides)}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-f", "lavfi", "-i",
                    "anullsrc=r=44100:cl=stereo", "-vf", "pad=1080:1920:0:285:color=0x05070d,format=yuv420p,fps=30",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest", "-movflags",
                    "+faststart", f"{out}/reel.mp4"], capture_output=True, check=True)
    open(f"{out}/caption.txt", "w", encoding="utf-8").write(spec["caption"])
    print("OK", len(slides), "slides ->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
