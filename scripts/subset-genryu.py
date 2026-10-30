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

import hashlib
import os
import re
import shutil
import sys
import glob
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


def fingerprint_and_patch(pairs):
    """给字体加内容哈希，并把 CSS / HTML 里的引用改到新文件名。

    字体带 immutable 缓存头，文件名不变就会一直命中旧缓存，所以必须让
    URL 随内容变。改完再删掉无哈希的旧副本；任何一步出错都保留旧副本，
    退回「无哈希也能用」的状态，不让构建失败。
    """
    mapping = {}
    for old_name in pairs:
        path = os.path.join(OUT_DIR, old_name)
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()[:8]
        new_name = f"{old_name[:-len('.woff2')]}.{digest}.woff2"
        shutil.copyfile(path, os.path.join(OUT_DIR, new_name))
        mapping[old_name] = new_name

    patched = 0
    for css in glob.glob(os.path.join(PUBLIC, "css", "*.css")):
        with open(css, encoding="utf-8") as fh:
            text = fh.read()
        if any(old in text for old in mapping):
            for old, new in mapping.items():
                text = text.replace(old, new)
            with open(css, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            patched += 1

    for root, _, files in os.walk(PUBLIC):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if not any(old in text for old in mapping):
                continue
            for old, new in mapping.items():
                text = text.replace(old, new)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            patched += 1

    # 确认没有漏改的引用，才删旧副本
    leftovers = []
    for root, _, files in os.walk(PUBLIC):
        for fn in files:
            if not (fn.endswith(".html") or fn.endswith(".css")):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            leftovers += [old for old in mapping if old in text]
    if leftovers:
        print(f"警告：仍有 {len(set(leftovers))} 个字体的旧引用，保留无哈希副本")
        return mapping, False

    for old_name in pairs:
        os.remove(os.path.join(OUT_DIR, old_name))

    for old, new in mapping.items():
        print(f"{old} -> {new}")
    return mapping, patched > 0


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

    try:
        fingerprint_and_patch(("GenRyuMin2TC-R-subset.woff2", "GenRyuMin2TC-B-subset.woff2"))
    except Exception as exc:  # 不让加哈希的失败拖垮部署
        print(f"警告：加内容哈希失败（{exc}），继续使用无哈希文件名")


if __name__ == "__main__":
    main()
