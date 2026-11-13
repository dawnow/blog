#!/usr/bin/env python3
"""按当次构建实际用到的字符，生成 GenRyuMinTC 的子集。

用法：
    hugo --gc --minify                     # 先构建，产出 public/
    python scripts/subset-genryu.py        # 按页面用字出子集，写入 public/fonts/
    python scripts/subset-genryu.py --force  # 不管覆盖情况，强制重切
    python scripts/subset-genryu.py --check  # 只检查覆盖情况，不改文件
    python scripts/subset-genryu.py --write-static
                                           # 重切的同时，把结果写回
                                           # static/fonts/ 作为兜底快照
                                           # （npm run fonts:sync 就是这个）

源字体在 fonts-src/（完整字库，不参与部署）；输出写 public/fonts/。

每次构建先检查 static/fonts/ 里已提交的子集能否覆盖当次全部用字：
  - 能覆盖（绝大多数构建都如此，写文章用到的新字通常早就在集里）：
    直接把 static/ 的文件搬进 public/，跳过子集化。一次压缩要 30 秒上下，
    而检查覆盖只要 0.3 秒——这是构建速度的关键。
  - 覆盖不了：重新按当次用字切，并提示跑 `npm run fonts:sync` 把结果固化，
    下一次就能回到快路径。不固化也不会出错，只是每次构建都要重切一遍。
  - `--force` 跳过检查，强制重切。

static/fonts/ 里的子集同时也是「没有 fontTools 的构建环境」和 `hugo server`
本地预览的兜底。

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
STATIC_NAMES = ("GenRyuMin2TC-R-subset.woff2", "GenRyuMin2TC-B-subset.woff2")

# GenRyuMinTC 在正文里只是 CJK 的后备（拉丁由 Amstelvar 供货），
# 但 fontFamilyTitle / fontFamilyHeadings 的字体栈是 "'GenRyuMinTC', serif"，
# 也就是说标题、文章标题里的**英文和数字同样由它渲染**。
# 所以除了非 ASCII 字符，ASCII 可打印字符也必须保留，否则标题里的英文
# 会回落到系统衬线体，与中文标题的字形不搭。
# 源字体没有的字符（emoji 等）会在子集化时被自动忽略。

# 排版符号兜底：即使当前页面没用到也保留，避免改 captionPrefix（◎ ↔ ※）、
# 换掉 hr 的三连点（·）或日后写作引入这些符号时突然回落到系统字体。
ALWAYS = set("◎※·→←↑↓①②③④⑤℃°±×÷≠≤≥…—–‘’“”「」『』◆●○")
ASCII = {chr(c) for c in range(0x20, 0x7F)}


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
            chars.update(ch for ch in text if ord(ch) >= 0x80 and ch.isprintable())

    # 只保留源字体真正能提供的字符：emoji 等本来就不在字库里，
    # 留着会让 --check 永远报“缺字”，也会白白参与哈希。
    cmap = TTFont(SRC_R).getBestCmap()
    chars |= ALWAYS
    chars |= ASCII
    chars = {c for c in chars if ord(c) in cmap}
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


def glyph_digest(chars):
    """按「字集内容 + 源字体内容」取哈希。

    不能按输出文件字节取：同样的输入，fontTools / brotli 每次压出来的
    字节可能不同（本地和 Netlify 就不一致），那样每次构建都会换 URL，
    immutable 缓存等于白设。字集不变就应当得到同一个名字。
    """
    h = hashlib.sha256()
    h.update("".join(sorted(chars)).encode("utf-8"))
    for src in (SRC_R, SRC_B):
        with open(src, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()[:8]


def fingerprint_and_patch(pairs, digest):
    """给字体加上按字集算出的哈希，并把 CSS / HTML 里的引用改到新文件名。

    字体带 immutable 缓存头，文件名不变就会一直命中旧缓存，所以必须让
    URL 随内容变。改完再删掉无哈希的旧副本；任何一步出错都保留旧副本，
    退回「无哈希也能用」的状态，不让构建失败。
    """
    mapping = {}
    for old_name in pairs:
        path = os.path.join(OUT_DIR, old_name)
        new_name = f"{old_name[:-len('.woff2')]}.{digest}.woff2"
        shutil.copyfile(path, os.path.join(OUT_DIR, new_name))
        mapping[old_name] = new_name

    # 改写时顺手在内存里确认没有漏改，而不是改完再全量扫一遍。
    # 那个复查很贵：刚写过的文件要被重新打开读取，Windows 上会先等一次杀软扫描，
    # 120 个页面实测多花 7.5 秒，比整个脚本其余部分还慢十几倍。这里校验的是同一份
    # 字符串，结论与复查完全等价。
    leftovers = set()

    def rewrite(path, text):
        for old, new in mapping.items():
            text = text.replace(old, new)
        leftovers.update(old for old in mapping if old in text)
        return text

    patched = 0
    for css in glob.glob(os.path.join(PUBLIC, "css", "*.css")):
        with open(css, encoding="utf-8") as fh:
            text = fh.read()
        if any(old in text for old in mapping):
            text = rewrite(css, text)
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
            text = rewrite(path, text)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            patched += 1

    if leftovers:
        print(f"警告：仍有 {len(leftovers)} 个字体引用未能改写，保留无哈希副本")
        return mapping, False

    for old_name in pairs:
        os.remove(os.path.join(OUT_DIR, old_name))

    # 清掉上一次构建遗留的带哈希文件，避免 public/fonts 越积越多
    keep = set(mapping.values())
    for stray in glob.glob(os.path.join(OUT_DIR, "GenRyuMin2TC-*-subset.*.woff2")):
        if os.path.basename(stray) not in keep:
            os.remove(stray)

    for old, new in mapping.items():
        print(f"{old} -> {new}")
    return mapping, patched > 0


def static_coverage(chars):
    """检查 static/fonts 里已提交的子集能否覆盖当前页面的全部用字。

    返回 (是否全覆盖, 这些子集覆盖的字符集)。两个字体都要覆盖到——粗体缺字同样
    会回落，只是回落在 <strong> 上。
    """
    covered = None
    for name in STATIC_NAMES:
        path = os.path.join(REPO, "static", "fonts", name)
        if not os.path.exists(path):
            return False, set()
        cmap = set(TTFont(path).getBestCmap())
        covered = cmap if covered is None else (covered & cmap)
    missing = {c for c in chars if ord(c) not in covered}
    return (not missing), {chr(o) for o in covered}


def main():
    chars, pages = collect_chars()
    if len(chars) < 500:
        sys.exit(f"只扫到 {len(chars)} 个字，明显不对，停止")

    if "--check" in sys.argv[1:]:
        print(f"扫描 {pages} 个页面，正文用字 {len(chars)} 个")
        sys.exit(check(chars))

    os.makedirs(OUT_DIR, exist_ok=True)
    covered, static_chars = static_coverage(chars)
    reuse = covered and "--force" not in sys.argv[1:]

    if reuse:
        # 快路径：这次构建的用字全都落在已提交的子集里，切分结果必然与上次相同，
        # 没必要再花 40 秒压缩一遍——直接把 static/ 里的文件搬进 public/。
        # 注意哈希取自「静态子集的字集」而不是「本次用字」：后者会随每篇文章的字
        # 缓慢增长，用它算会导致 URL 每次都变，immutable 缓存等于白设。
        total = 0
        for name in STATIC_NAMES:
            src = os.path.join(REPO, "static", "fonts", name)
            dst = os.path.join(OUT_DIR, name)
            shutil.copyfile(src, dst)
            total += os.path.getsize(dst)
        print(
            f"复用 static/fonts 的已有子集（覆盖本次 {len(chars)} 字，"
            f"{total / 1024 / 1024:.2f} MB），跳过子集化"
        )
    else:
        total_before = os.path.getsize(SRC_R) + os.path.getsize(SRC_B)
        total = 0
        for src, out in ((SRC_R, STATIC_NAMES[0]), (SRC_B, STATIC_NAMES[1])):
            dst = os.path.join(OUT_DIR, out)
            size = subset(src, dst, chars)
            total += size
            print(f"{out}: {size / 1024:7.1f} KB")

        print(
            f"页面 {pages} 个，用字 {len(chars)} 个；"
            f"{total_before / 1024 / 1024:.1f} MB -> {total / 1024 / 1024:.2f} MB"
        )
        if not covered:
            print(
                "提示：出现了 static/fonts 子集里没有的字，本次已重新切分。"
                "本地跑一次 `npm run fonts:sync` 可以把结果固化，之后的构建就能走快路径。"
            )

    if "--write-static" in sys.argv[1:]:
        # 兜底快照：给没有 fontTools 的构建环境，以及 `hugo server` 本地预览用。
        # 正文新增了字就要重跑一次，否则这些环境会回落到系统字体。
        # 走快路径时 public/ 里的文件本来就是从 static/ 拷来的，这一步是空转，无害。
        static_dir = os.path.join(REPO, "static", "fonts")
        os.makedirs(static_dir, exist_ok=True)
        for out in STATIC_NAMES:
            shutil.copyfile(os.path.join(OUT_DIR, out), os.path.join(static_dir, out))
            print(f"static/fonts/{out} 已更新")

    # 哈希只取「这次真正提供出去的那份子集」的字集：
    #   快路径 -> 静态子集的字集（不随新文章缓慢变化，URL 也不会每次构建都变）
    #   重切/固化 -> 本次用字（与刚写出去的文件的 cmap 一致）
    digest_chars = chars if ("--write-static" in sys.argv[1:] or not reuse) else static_chars
    try:
        fingerprint_and_patch(STATIC_NAMES, glyph_digest(digest_chars))
    except Exception as exc:  # 不让加哈希的失败拖垮部署
        print(f"警告：加内容哈希失败（{exc}），继续使用无哈希文件名")


if __name__ == "__main__":
    main()
