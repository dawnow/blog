#!/usr/bin/env python3
"""生成 Amstelvar 的「钉轴 + 拉丁子集」版本，写入 static/fonts/。

为什么需要：Amstelvar 是 12 轴的可变字体，Roman 697 KB / Italic 713 KB，
而站点只用到其中四个轴，其中三个还是固定值（见 assets/scss/custom/_custom.scss）：

    wdth 90 · opsz 40 · YTLC 460        ← 固定，永远不变
    wght 100–900                        ← 保留成可变轴，正文字重和 <strong> 都用它

其余九个轴（GRAD/XTRA/XOPQ/YOPQ/YTUC/YTAS/YTDE/YTFI）站点从没设置过，永远停在
默认值，却要跟着文件一起下载。把它们连同另外三个固定轴一起烘进轮廓，
再按拉丁常用字符子集化，697 KB -> 约 110 KB，字形观感不变。

用法：
    python scripts/subset-amstelvar.py           # 重新生成 static/fonts/
    python scripts/subset-amstelvar.py --check   # 只检查现有文件覆盖了哪些字符

源字体在 fonts-src/，是上游完整 VF，不参与部署。这个脚本不像
subset-genryu.py 那样每次构建都跑：拉丁字符集是稳定的，生成一次提交进仓库即可。
只有改动下面 PINS / LATIN 里的内容，或者要升级上游字体时才需要重跑。
"""

import io
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.subset import Options, Subsetter
from fontTools.varLib import instancer

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO, "fonts-src")
OUT_DIR = os.path.join(REPO, "static", "fonts")

# 必须与 assets/scss/custom/_custom.scss 里 body 的
# font-variation-settings 保持一致。改了那边就要重跑这个脚本。
PINS = {"wdth": 90, "opsz": 40, "YTLC": 460}

# 英文正文、标题、引文、代码注释用得上的字符：
#   基本拉丁 + 拉丁补充（带重音的西欧字符）+ 拉丁扩展 A（Welsh/Esperanto 等）
#   + 常用通用标点（弯引号、破折号、省略号、项目符号、商标、欧元）
LATIN = (
    set(range(0x20, 0x7F))
    | set(range(0xA0, 0x100))
    | set(range(0x100, 0x180))
    | set(range(0x2000, 0x2070))
    | {0x2032, 0x2033, 0x20AC, 0x2122}
)

# 数学与度量符号：正文里会出现（「≥」就用在讲排版的那几篇里），且 GenRyuMin 并不都收，
# 一旦丢掉就会回落到系统字体，和周围的拉丁字形对不上。原 VF 有的一并保留。
SYMBOLS = set("≥≤≠±×÷≈∆π°‰′″")

LATIN |= {ord(c) for c in SYMBOLS}

FILES = (
    ("Amstelvar-Roman-VF.woff2", "Amstelvar-Roman-VF.woff2"),
    ("Amstelvar-Italic-VF.woff2", "Amstelvar-Italic-VF.woff2"),
)


def build_options():
    opts = Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["BASE", "VORG"]
    return opts


def build(src, dst):
    font = TTFont(src)
    font.flavor = None

    cmap = font.getBestCmap()
    chars = sorted(c for c in LATIN if c in cmap)

    # 顺序很重要：必须「先子集、后实例化」。
    # 反过来时 fontTools 会崩在 HVAR 子集化上（KeyError: 'softhyphen'）——
    # 实例化后的可变表里少了某些字形记录，而子集还要按字形列表去取。
    # 先子集则可变表只保留实际用到的 300 多个字形，实例化时不会再碰到缺失项。
    subsetter = Subsetter(build_options())
    subsetter.populate(unicodes=chars)
    subsetter.subset(font)

    # 除 wght 之外的每一个轴都钉死：本站用到的三个用 PINS 里的值，剩下的用字体自己的
    # 默认值。只钉 PINS 是不够的——instancer 会原样保留未指定的轴，那八个轴带着各自的
    # 变化数据留在文件里，白占体积；它们从没被 CSS 设置过，钉在默认值上观感不变。
    # 钉完之后只剩 wght 一个可变轴（约 58 KB），@font-face 的 font-weight: 100 900 仍有效。
    axes = {}
    for axis in font["fvar"].axes:
        if axis.axisTag == "wght":
            continue
        axes[axis.axisTag] = PINS.get(axis.axisTag, axis.defaultValue)

    font = instancer.instantiateVariableFont(font, axes, inplace=False)

    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    data = buf.getvalue()
    with open(dst, "wb") as fh:
        fh.write(data)
    return len(data), len(chars)


def check():
    bad = False
    for _, out_name in FILES:
        path = os.path.join(OUT_DIR, out_name)
        if not os.path.exists(path):
            print(f"{out_name}: 不存在")
            bad = True
            continue
        font = TTFont(path)
        axes = [a.axisTag for a in font["fvar"].axes] if "fvar" in font else []
        cmap = font.getBestCmap()
        covered = sum(1 for c in LATIN if c in cmap)
        print(
            f"{out_name}: {os.path.getsize(path) / 1024:6.1f} KB, "
            f"轴 {axes or '（无，已是静态）'}, 覆盖 {covered}/{len(LATIN)} 字符"
        )
    return 1 if bad else 0


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(check())

    os.makedirs(OUT_DIR, exist_ok=True)
    before = after = 0
    for src_name, out_name in FILES:
        src = os.path.join(SRC_DIR, src_name)
        if not os.path.exists(src):
            sys.exit(f"缺少源字体 {src}")
        dst = os.path.join(OUT_DIR, out_name)
        size, chars = build(src, dst)
        src_size = os.path.getsize(src)
        before += src_size
        after += size
        kept = []
        written = TTFont(dst)
        if "fvar" in written:
            kept = [a.axisTag for a in written["fvar"].axes]
        print(
            f"{out_name}: {src_size / 1024:6.1f} KB -> {size / 1024:6.1f} KB"
            f"（{chars} 字符，留下的可变轴 {kept}）"
        )
    print(
        f"合计 {before / 1024:6.1f} KB -> {after / 1024:6.1f} KB，"
        f"省 {(1 - after / before) * 100:.0f}%"
    )


if __name__ == "__main__":
    main()
