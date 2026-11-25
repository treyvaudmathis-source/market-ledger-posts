#!/usr/bin/env python3
"""Photo-style carousel (stockregion look): full-bleed photo, big gold headline, few words, flashy numbers.

Usage: python3 make_photo_post.py spec_photo.json OUTDIR
Spec: {"cover":{"title":"... [[24-YEAR]] ...","photo":"photos/x.jpg","pos":"50% 30%","hl":"red"},
       "slides":[{"photo","pos","kicker","number","color","line","source"} x4],
       "cta":{"photo","title","sub"}, "caption":"..."}
[[...]] inside the cover title is painted in the flash colour hl. Photo paths are relative to the repo root.
"""
import html, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_post import ensure_fonts, esc, GOLD, LOGO, W, H

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


def text_slide(s):
    col = FLASH.get(s.get("color", "green"), s.get("color"))
    num = s["number"]
    nf = 330 if len(num) <= 5 else 270 if len(num) <= 7 else 210
    src = (f'<div style="position:absolute;left:60px;right:60px;top:1288px;text-align:center;{FONT_B};font-size:30px;'
           f'letter-spacing:2px;color:#b9c2d9;text-transform:uppercase;{SHADOW}">{esc(s["source"])}</div>') if s.get("source") else ""
    return (bg(s["photo"], s.get("pos"), dim=0.62) + grad(0, 420, 0.55, 0) + grad(700, 650, 0, 0.92) +
            f'<div style="position:absolute;left:50px;right:50px;top:250px;text-align:center;{FONT_A};font-size:92px;line-height:1;'
            f'text-transform:uppercase;letter-spacing:2px;color:#fff;{SHADOW}">{esc(s["kicker"])}</div>'
            f'<div style="position:absolute;left:30px;right:30px;top:360px;text-align:center;{FONT_A};font-size:{nf}px;line-height:1;'
            f'color:{col};text-shadow:0 0 40px {col}88,0 6px 24px rgba(0,0,0,.9)">{esc(num)}</div>' + divider(850, 56) +
            f'<div style="position:absolute;left:60px;right:60px;top:945px;text-align:center;{FONT_B};font-size:84px;line-height:1.05;'
            f'text-transform:uppercase;color:#fff;{SHADOW}">{esc(s["line"])}</div>' + src)


def cta_slide(c):
    return (bg(c["photo"], c.get("pos"), dim=0.35) + grad(380, 520, 0, 0.96) + grad(900, 450, 0.96, 1.0) + divider(870) +
            f'<div style="position:absolute;left:50px;right:50px;top:945px;text-align:center;{FONT_A};font-size:140px;line-height:1.0;'
            f'text-transform:uppercase;{GOLD}">{esc(c["title"])}</div>'
            f'<div style="position:absolute;left:60px;right:60px;top:1235px;text-align:center;{FONT_B};font-size:60px;line-height:1.1;'
            f'text-transform:uppercase;color:#fff">{esc(c["sub"])}</div>')


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
    open(f"{out}/caption.txt", "w", encoding="utf-8").write(spec["caption"])
    print("OK", len(slides), "slides ->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
