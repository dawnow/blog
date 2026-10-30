#!/usr/bin/env python3
"""按当次构建实际用到的字符，重新生成 GenRyuMinTC 的子集。

用法：
    hugo --gc --minify                     # 先构建，产出 public/
    python scripts/subset-genryu.py        # 按页面用字重切，写入 public/fonts/
    python scripts/subset-genryu.py --check  # 只检查覆盖情况，不改文件

源字体在 fonts-src/（完整字库，不参与部署）；输出只写 public/fonts/，
因此每次构建都会按当次页面用字重新切，发新文章不用手动处理。

若 public/ 不存在，说明还没构建，脚本直接报错退出。
"""

import os
import re
import sys
import html as htmllib

from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter, Options

# Windows 控制台默认不是 UTF-8，避免中文日志变乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(REPO, "public")
SRC_R = os.path.join(REPO, "fonts-src", "GenRyuMin2TC-R.woff2")
SRC_B = os.path.join(REPO, "fonts-src", "GenRyuMin2TC-B.woff2")
OUT_DIR = os.path.join(PUBLIC, "fonts")

# 需要 GenRyuMinTC 供货的字面：CJK 统一表意文字、兼容区、注音/标点、全角形式、扩展 B 及以后
CJK = re.compile(
    "[\u2e80-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef\u3000-\u303f"
    "\U00020000-\U0002ffff]"
)


def collect_chars():
    if not os.path.isdir(PUBLIC):
        sys.exit("public/ 不存在，请先跑 `hugo --gc --minify`")

    chars = set()
    pages = 0
    for root, _, files in os.walk(PUBLIC):
        for name in files:
            if not name.endswith(".html"):
                continue
            pages += 1
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", "", text)
            text = htmllib.unescape(text)
            chars.update(CJK.findall(text))
    return chars, pages


def build_options():
    opts = Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["BASE", "VORG"]
    return opts


def subset(src, dst, chars):
    font = TTFont(src)
    ss = Subsetter(build_options())
    ss.populate(unicodes=[ord(c) for c in chars])
    ss.subset(font)
    font.save(dst)
    return os.path.getsize(dst)


def check(chars):
    """检查 static/fonts 里已提交的子集是否覆盖当前页面的用字。"""
    bad = False
    for name in ("GenRyuMin2TC-R-subset.woff2", "GenRyuMin2TC-B-subset.woff2"):
        src = os.path.join(REPO, "static", "fonts", name)
        if not os.path.exists(src):
            print(f"{name}: 不存在")
            bad = True
            continue
        cmap = TTFont(src).getBestCmap()
        missing = sorted(c for c in chars if ord(c) not in cmap)
        if missing:
            bad = True
            print(f"{name}: 缺 {len(missing)} 个字 -> {''.join(missing[:40])}")
        else:
            print(f"{name}: 覆盖完整 ({len(chars)} 字)")
    return 1 if bad else 0


def main():
    chars, pages = collect_chars()
    if len(chars) < 500:
        sys.exit(f"只扫到 {len(chars)} 个字，明显不对，停止")

    if "--check" in sys.argv[1:]:
        print(f"扫描 {pages} 个页面，正文用字 {len(chars)} 个")
        sys.exit(check(chars))

    os.makedirs(OUT_DIR, exist_ok=True)
    total_before = os.path.getsize(SRC_R) + os.path.getsize(SRC_B)
    total_after = 0
    for src, out in (
        (SRC_R, "GenRyuMin2TC-R-subset.woff2"),
        (SRC_B, "GenRyuMin2TC-B-subset.woff2"),
    ):
        dst = os.path.join(OUT_DIR, out)
        size = subset(src, dst, chars)
        total_after += size
        print(f"{out}: {size / 1024:7.1f} KB")

    print(
        f"页面 {pages} 个，用字 {len(chars)} 个；"
        f"{total_before / 1024 / 1024:.1f} MB -> {total_after / 1024 / 1024:.2f} MB"
    )


if __name__ == "__main__":
    main()
