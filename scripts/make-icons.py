# -*- coding: utf-8 -*-
"""生成 the thinning dark 的全套站点图标。

设计（作者稿，2026-11）：纸白 #FDFAF6 满幅底，左下角天蓝「海」，右上角杏色「日」，
两者在地平线 y=270 相切；圆贴上边与右边、海贴左边与下边，右侧留 78 纸边。

导出：
    favicon.svg / favicon.ico(16,32,48) / 96 / apple-touch 180(缩 0.85) /
    web-app-manifest 192,512 / maskable 192,512(缩 0.68)

用法：
    python scripts/make-icons.py            # 写入 ../static
    python scripts/make-icons.py --out DIR  # 写到别处（预览用）
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

S = 600                       # 设计基准画布
PAPER = (253, 250, 246)       # #FDFAF6
BLUE = (74, 155, 218)         # #4A9BDA
PEACH = (232, 160, 116)       # #E8A074

SEA = (0, 270, 522, 600)      # x0, y0, x1, y1（贴左、贴下）
SUN = (465, 135, 135)         # cx, cy, r（贴上、贴右）

SS = 8                        # 超采样倍率


def draw(d, f, scale=1.0):
    """在 f = 画布像素 / 600 的画布上绘制；scale 为绕中心的内容缩放。"""
    cx = cy = S / 2

    def X(x):
        return (cx + (x - cx) * scale) * f

    def Y(y):
        return (cy + (y - cy) * scale) * f

    x0, y0, x1, y1 = SEA
    d.rectangle([X(x0), Y(y0), X(x1), Y(y1)], fill=BLUE)
    sx, sy, r = SUN
    d.ellipse([X(sx - r), Y(sy - r), X(sx + r), Y(sy + r)], fill=PEACH)


def icon(size, scale=1.0):
    """满幅纸底；scale=1 为原稿，<1 用于 maskable / apple 的留边。"""
    w = size * SS
    img = Image.new("RGB", (w, w), PAPER)
    draw(ImageDraw.Draw(img), w / S, scale)
    return img.resize((size, size), Image.LANCZOS)


FAVICON_SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}" role="img" aria-label="the thinning dark">
  <title>the thinning dark</title>
  <rect width="{S}" height="{S}" fill="#FDFAF6"/>
  <rect x="{SEA[0]}" y="{SEA[1]}" width="{SEA[2] - SEA[0]}" height="{SEA[3] - SEA[1]}" fill="#4A9BDA"/>
  <circle cx="{SUN[0]}" cy="{SUN[1]}" r="{SUN[2]}" fill="#E8A074"/>
</svg>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "static"))
    args = ap.parse_args()
    out = Path(args.out)
    (out / "icons").mkdir(parents=True, exist_ok=True)

    def save(size, rel, scale=1.0):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        icon(size, scale).save(p)
        print(f"{rel:52s} {p.stat().st_size:>8d} B")

    p = out / "icons/favicon.svg"
    p.write_text(FAVICON_SVG, encoding="utf-8")
    print(f"{'icons/favicon.svg':52s} {p.stat().st_size:>8d} B")

    save(512, "icons/web-app-manifest-512x512.png")
    save(192, "icons/web-app-manifest-192x192.png")
    save(512, "icons/web-app-manifest-maskable-512x512.png", 0.68)
    save(192, "icons/web-app-manifest-maskable-192x192.png", 0.68)
    save(96, "icons/favicon-96x96.png")
    save(180, "icons/apple-touch-icon.png", 0.85)

    ico = icon(256)
    ico.save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"{'favicon.ico':52s} {(out / 'favicon.ico').stat().st_size:>8d} B")


if __name__ == "__main__":
    main()
