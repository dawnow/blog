# -*- coding: utf-8 -*-
"""生成 the thinning dark 的全套站点图标（Zima Blue / 瓷砖底版）。

设计（作者稿）：纸色/透明画布上，一个圆角 64 的半透明瓷砖 #FBC6A4（33%），
中间是实色 Zima Blue #55B4E5 的旋转矩形（菱形）。

- 浏览器图标（svg / ico / 96）：透明底，瓷砖随标签栏明暗变化
- 应用图标（apple / maskable）：叠在纸色 #FDFAF6 上的不透明版本
  （iOS/Android 不接受透明底；maskable 满幅铺瓷砖色并缩到 68%）
- og-image：不透明纸色版本（社交平台对透明 PNG 的合成不可控）

用法：
    python scripts/make-icons.py            # 写入 ../static
    python scripts/make-icons.py --out DIR  # 写到别处（预览用）
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

S = 600
RADIUS = 64
PAPER = (253, 250, 246)
PEACH = (251, 198, 164, 84)   # #FBC6A4 @ 33%
BLUE = (85, 180, 229)         # #55B4E5
# 旋转矩形（-135°）四个角
DIAMOND = [(350.509, 512.469), (88.314, 250.274), (250.684, 87.904), (512.879, 350.099)]

SS = 8


def _scale_pts(scale):
    return [(300 + (x - 300) * scale, 300 + (y - 300) * scale) for x, y in DIAMOND]


def icon(size, opaque=False, scale=1.0, full_bleed=False):
    """opaque=False 时透明底；True 时纸色底。full_bleed=True 时瓷砖铺满（maskable）。"""
    w = size * SS
    f = w / S
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    if opaque:
        img.paste(Image.new("RGBA", (w, w), PAPER + (255,)), (0, 0))

    tile = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    if full_bleed:
        td.rectangle([0, 0, w, w], fill=PEACH)
    else:
        td.rounded_rectangle([0, 0, w - 1, w - 1], radius=RADIUS * f, fill=PEACH)
    img = Image.alpha_composite(img, tile)

    d = ImageDraw.Draw(img)
    d.polygon([(x * f, y * f) for x, y in _scale_pts(scale)], fill=BLUE + (255,))
    return img.resize((size, size), Image.LANCZOS)


FAVICON_SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}" role="img" aria-label="the thinning dark">
  <title>the thinning dark</title>
  <rect width="{S}" height="{S}" rx="{RADIUS}" fill="#FBC6A4" fill-opacity="0.33"/>
  <polygon points="{' '.join(f'{x:g},{y:g}' for x, y in DIAMOND)}" fill="#55B4E5"/>
</svg>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "static"))
    args = ap.parse_args()
    out = Path(args.out)
    (out / "icons").mkdir(parents=True, exist_ok=True)

    def text(rel, data):
        p = out / rel
        p.write_text(data, encoding="utf-8")
        print(f"{rel:52s} {p.stat().st_size:>8d} B")

    def save(img, rel):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        print(f"{rel:52s} {p.stat().st_size:>8d} B")

    text("icons/favicon.svg", FAVICON_SVG)

    # 浏览器：透明底
    save(icon(96), "icons/favicon-96x96.png")
    # PWA any：透明底（桌面/任务栏能透出背后的光）
    save(icon(192), "icons/web-app-manifest-192x192.png")
    save(icon(512), "icons/web-app-manifest-512x512.png")
    # 应用图标：不透明纸底
    save(icon(180, opaque=True), "icons/apple-touch-icon.png")
    save(icon(512, opaque=True, scale=0.68, full_bleed=True),
         "icons/web-app-manifest-maskable-512x512.png")
    save(icon(192, opaque=True, scale=0.68, full_bleed=True),
         "icons/web-app-manifest-maskable-192x192.png")
    # 社交卡片用不透明版本（透明 PNG 在部分平台会被合成到黑底）
    save(icon(512, opaque=True), "icons/og-image.png")

    # ICO：16/32/48 透明底
    ico = icon(256)
    ico.save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"{'favicon.ico':52s} {(out / 'favicon.ico').stat().st_size:>8d} B")


if __name__ == "__main__":
    main()
