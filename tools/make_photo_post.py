#!/usr/bin/env python3
"""Photo-style carousel (stockregion look): full-bleed photo, big gold headline, few words, flashy numbers.

Usage: python3 make_photo_post.py spec_photo.json OUTDIR
Spec: {"cover":{"title":"... [[24-YEAR]] ...","photo":"photos/x.jpg","pos":"50% 30%","hl":"red"},
       "slides":[{"photo","pos","label","body","color"} x4]  (a slide may have "chart":{...} instead of "photo": same visual specs as make_post.py: line/bars/columns/big_stat)  (body: [[5.3%]] or [[red|5.3%]] = flashy number),
       "cta":{"photo","title","sub"}, "caption":"..."}
[[...]] inside the cover title is painted in the flash colour hl. Photo paths are relative to the repo root.
"""
import html, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_post import ensure_fonts, esc, GOLD, LOGO, W, H, VIS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLASH = {"green": "#2cff6b", "red": "#ff3b30", "orange": "#ff9f0a", "yellow": "#ffe600", "cyan": "#19e3ff", "pink": "#ff2d95"}
FONT_A = "font-family:'Anton',Impact,sans-serif"
FONT_B = "font-family:'Bebas Neue',Impact,sans-serif"
SHADOW = "text-shadow:0 4px 18px rgba(0,0,0,.85)"


def bg(photo, pos, top=0, height=H, dim=0.0):
    p = os.path.join(ROOT, photo)
    return (f'<div style="position:absolute;left:0;top:{top}px;width:{W}px;height:{height}px;'
            f'background:url(\'file://{p}\') {pos or "50% 50%"}/cover no-repeat"></div>'
            + (f'<div style="position:absolute;left:0;top:{top}px;width:{W}px;height:{height}px;background:rgba(5,7,13,{dim})"></div>' if dim else ""))


def grad(top, height, a0=0.0, a1=1.0):
    return (f'<div style="position:absolute;left:0;top:{top}px;width:{W}px;height:{height}px;'
            f'background:linear-gradient(180deg,rgba(5,7,13,{a0}) 0%,rgba(5,7,13,{a1}) 100%)"></div>')


def divider(top, size=64):
    return (f'<div style="position:absolute;left:60px;right:60px;top:{top}px;display:flex;align-items:center;gap:26px">'
            f'<div style="flex:1;height:2px;background:#d9a91f"></div>{LOGO.format(s=size)}'
            f'<div style="flex:1;height:2px;background:#d9a91f"></div></div>')


def cover(s):
    col = FLASH.get(s.get("hl", "red"), s.get("hl"))
    t = esc(s["title"])
    t = re.sub(r"\[\[(.+?)\]\]", lambda m: f'<span style="color:{col};-webkit-text-fill-color:{col}">{m.group(1)}</span>', t)
    n = len(re.sub(r"\[\[|\]\]", "", s["title"]))
    fs = 150 if n <= 22 else 124 if n <= 34 else 108
    return (bg(s["photo"], s.get("pos")) + grad(380, 520, 0, 0.96) + grad(900, 450, 0.96, 1.0) + divider(905) +
            f'<div style="position:absolute;left:40px;right:40px;top:985px;text-align:center;{FONT_A};font-size:{fs}px;'
            f'line-height:1.0;text-transform:uppercase;letter-spacing:1px;{GOLD}">{t}</div>')


def flash(text, default):
    """[[+4%]] or [[green|+4%]] -> flashy coloured number."""
    def rep(m):
        c, t = (m.group(1) or "").rstrip("|"), m.group(2)
        col = FLASH.get(c, default) if c else default
        return f'<span style="color:{col};text-shadow:0 0 22px {col}88">{t}</span>'
    return re.sub(r"\[\[(?:(\w+)\|)?(.+?)\]\]", rep, esc(text))


def framed(photo, pos):
    p = os.path.join(ROOT, photo)
    return (f'<div style="position:absolute;left:60px;top:60px;width:960px;height:560px;border-radius:26px;'
            f'border:4px solid #d9a91f;box-sizing:border-box;box-shadow:0 12px 40px rgba(0,0,0,.6);'
            f'background:url(\'file://{p}\') {pos or "50% 50%"}/cover no-repeat"></div>')


def chart_frame(v):
    """Chart in the same framed box as the photos. v = {"type": "line"|"bars"|"columns"|"big_stat", ...} (see make_post.py visuals)."""
    h = 630
    v = {k: x for k, x in v.items() if k != "footnote"}
    inner = VIS[v["type"]](v, h)
    return (f'<div style="position:absolute;left:60px;top:60px;width:960px;height:560px;border-radius:26px;overflow:hidden;'
            f'border:4px solid #d9a91f;box-sizing:border-box;box-shadow:0 12px 40px rgba(0,0,0,.6);'
            f'background:linear-gradient(180deg,#16294f 0%,#05070d 100%)">'
            f'<svg viewBox="0 20 1080 630" style="position:absolute;left:0;top:0;width:100%;height:100%" preserveAspectRatio="xMidYMid meet">{inner}</svg></div>')


def text_slide(s):
    col = FLASH.get(s.get("color", "green"), s.get("color"))
    label, body = s["label"], s["body"]
    lf = 128 if len(label) <= 15 else 104 if len(label) <= 19 else 88
    plain = re.sub(r"\[\[(?:\w+\|)?|\]\]", "", body)
    bf = 78 if len(plain) <= 105 else 70 if len(plain) <= 135 else 62 if len(plain) <= 170 else 54
    top = chart_frame(s["chart"]) if s.get("chart") else framed(s["photo"], s.get("pos"))
    return (top + divider(672, 56) +
            f'<div style="position:absolute;left:50px;right:50px;top:760px;text-align:center;{FONT_A};font-size:{lf}px;line-height:1;'
            f'text-transform:uppercase;{GOLD}">{esc(label)}</div>'
            f'<div style="position:absolute;left:60px;right:60px;top:925px;text-align:center;{FONT_B};font-size:{bf}px;line-height:1.1;'
            f'text-transform:uppercase;color:#fff">{flash(body, col)}</div>')


def cta_slide(c):
    return (framed(c["photo"], c.get("pos")) + divider(672, 56) +
            f'<div style="position:absolute;left:50px;right:50px;top:760px;text-align:center;{FONT_A};font-size:128px;line-height:1.0;'
            f'text-transform:uppercase;{GOLD}">{esc(c["title"])}</div>'
            f'<div style="position:absolute;left:60px;right:60px;top:1115px;text-align:center;{FONT_B};font-size:68px;line-height:1.1;'
            f'text-transform:uppercase;color:#fff">{esc(c["sub"])}</div>')


def main(spec_path, out):
    spec = json.load(open(spec_path, encoding="utf-8"))
    fd = ensure_fonts()
    os.makedirs(out, exist_ok=True)
    css = (f"@font-face{{font-family:'Anton';src:url('file://{fd}/anton/files/anton-latin-400-normal.woff2')}}"
           f"@font-face{{font-family:'Bebas Neue';src:url('file://{fd}/bebas-neue/files/bebas-neue-latin-400-normal.woff2')}}"
           "body{margin:0;background:#05070d}")
    used = [spec["cover"]["photo"]] + [x["photo"] for x in spec["slides"] if not x.get("chart")] + [spec["cta"]["photo"]]
    if len(set(used)) != len(used):
        sys.exit("ERROR: the same photo is used twice - every slide needs its own different photo")
    slides = [cover(spec["cover"])] + [text_slide(s) for s in spec["slides"]] + [cta_slide(spec["cta"])]
    for i, body in enumerate(slides, 1):
        p = f"{out}/s{i}.html"
        open(p, "w", encoding="utf-8").write(
            f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>"
            f'<div style="position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#05070d">{body}</div></body></html>')
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                        "--hide-scrollbars", f"--window-size={W},{H}", "--virtual-time-budget=3000",
                        f"--screenshot={out}/slide{i}.png", f"file://{p}"], capture_output=True, check=True)
    open(f"{out}/caption.txt", "w", encoding="utf-8").write(spec["caption"])
    print("OK", len(slides), "slides ->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
