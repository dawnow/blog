#!/usr/bin/env python3
"""按当次构建实际用到的字符，生成 GenRyuMinTC 的分片与粗体子集，并为全站 woff2 / CSS 加指纹。

用法：
    hugo --gc --minify                     # 先构建，产出 public/
    python scripts/subset-genryu.py        # 按页面用字出子集/分片，写入 public/fonts/
    python scripts/subset-genryu.py --force  # 不管覆盖情况，强制重切
    python scripts/subset-genryu.py --check  # 只检查覆盖情况，不改文件
    python scripts/subset-genryu.py --write-static
                                           # 重切的同时，把分片与 _genryu-faces.scss 写回仓库
                                           # 作为兜底快照与快路径基准（npm run fonts:sync）

设计要点：
  1. Regular（400）按页面使用频次切为 6 片（GenRyuMin2TC-R-s0..s5.woff2）：
       - s0 专放首页用字 + 导航 + ASCII + 常用排版符号（仅 ~25-35 KB），首页冷启动只下这一片；
       - s1 放全站最高频的 500 字；
       - s2..s5 按频次由高到低均分其余字符。
     通过精确的 CSS unicode-range，浏览器仅下载当前页实际命中的分片。
  2. Bold（700）独立按全站粗体元素（h1-h6 / strong / b / th / dt / .post-subtitle 等）
     实际用字切为单文件 GenRyuMin2TC-B-subset.woff2，大幅缩减文章页首开体积。
  3. 快路径：先检查 static/fonts/ 里已提交的 Regular 分片与 Bold 子集能否覆盖本次构建全部用字
     （且 s0 覆盖首页用字）。能覆盖则跳过 fontTools 重切，直接复用并加哈希；
     若出现新字则实时重切并原地替换主 CSS 里的 /* ! genryu-faces:start..end */ 区块。
  4. 哈希与缓存一致：所有 woff2 均带 8 位内容哈希，改写完主 CSS 后重算 CSS 哈希并同步回写 HTML。
"""

import glob
import hashlib
import os
import re
import shutil
import sys
from collections import Counter
from html.parser import HTMLParser

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

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
STATIC_FONTS = os.path.join(REPO, "static", "fonts")
SCSS_FACES = os.path.join(REPO, "assets", "scss", "custom", "_genryu-faces.scss")

REG_SLICE_COUNT = 6
S1_SIZE = 500
REG_NAMES = tuple(f"GenRyuMin2TC-R-s{i}.woff2" for i in range(REG_SLICE_COUNT))
BOLD_NAME = "GenRyuMin2TC-B-subset.woff2"
LEGACY_REG_NAME = "GenRyuMin2TC-R-subset.woff2"

# 排版符号兜底：即使当前页面没用到也保留，避免改 captionPrefix（◎ ↔ ※）、
# 换掉 hr 的三连点（·）或日后写作引入这些符号时突然回落到系统字体。
ALWAYS = set("◎※·→←↑↓①②③④⑤℃°±×÷≠≤≥…—–‘’“”「」『』◆●○")
ASCII = {chr(c) for c in range(0x20, 0x7F)}

BOLD_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "th", "dt"}
BOLD_CLASSES = {"post-subtitle", "gh", "gi", "gu"}
SKIP_TAGS = {"script", "style"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

HASHED_WOFF2_RE = re.compile(r"\.[0-9a-f]{8}\.woff2$")
HASHED_CSS_RE = re.compile(r"^(?P<prefix>.+?)\.(?P<digest>[0-9a-f]{8,64})\.css$")
FACES_BLOCK_RE = re.compile(r"/\*!\s*genryu-faces:start\s*\*/.*?/\*!\s*genryu-faces:end\s*\*/", re.S)


class PageCharCollector(HTMLParser):
    """准确提取页面可见字符，同时区分粗体元素内出现的字符。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.all_chars = set()
        self.bold_chars = set()
        self._skip_depth = 0
        self._bold_stack = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in VOID_TAGS:
            return
        if t in SKIP_TAGS:
            self._skip_depth += 1
            return
        is_bold = t in BOLD_TAGS
        if not is_bold:
            for k, v in attrs:
                if k == "class" and v:
                    if BOLD_CLASSES.intersection(v.split()):
                        is_bold = True
                        break
        self._bold_stack.append(is_bold)

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in VOID_TAGS:
            return
        if t in SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._bold_stack:
            self._bold_stack.pop()

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        in_bold = any(self._bold_stack)
        for ch in data:
            if ord(ch) >= 0x80 and ch.isprintable():
                self.all_chars.add(ch)
                if in_bold:
                    self.bold_chars.add(ch)


def collect_chars():
    if not os.path.isdir(PUBLIC):
        sys.exit("public/ 不存在，请先跑 `hugo --gc --minify`")

    doc_freq = Counter()
    all_chars = set()
    bold_chars = set()
    home_chars = set()
    pages = 0

    home_path = os.path.normcase(os.path.join(PUBLIC, "index.html"))
    for root, _, files in os.walk(PUBLIC):
        for name in files:
            if not name.endswith(".html"):
                continue
            pages += 1
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="ignore") as fh:
                parser = PageCharCollector()
                parser.feed(fh.read())
                parser.close()
            all_chars.update(parser.all_chars)
            bold_chars.update(parser.bold_chars)
            for ch in parser.all_chars:
                doc_freq[ch] += 1
            if os.path.normcase(path) == home_path:
                home_chars.update(parser.all_chars)

    # 只保留源字体真正能提供的字符：emoji 等本来就不在字库里，
    # 留着会让 --check 永远报“缺字”，也会白白参与哈希。
    cmap_r = TTFont(SRC_R).getBestCmap()
    cmap_b = TTFont(SRC_B).getBestCmap()

    reg_chars = {c for c in (all_chars | ALWAYS | ASCII) if ord(c) in cmap_r}
    home_core = {c for c in (home_chars | ALWAYS | ASCII) if ord(c) in cmap_r}
    bold_set = {c for c in (bold_chars | ALWAYS | ASCII) if ord(c) in cmap_b}

    return reg_chars, bold_set, home_core, doc_freq, pages


def partition_regular(reg_chars, home_core, doc_freq):
    """将 Regular 字符集划分为 6 片：s0 首页核心，s1 高频 500 字，s2..s5 按频次均分。"""
    s0 = set(home_core) & reg_chars
    rest = sorted(reg_chars - s0, key=lambda c: (-doc_freq[c], ord(c)))

    slices = [s0]
    s1 = set(rest[:S1_SIZE])
    slices.append(s1)

    tail = rest[S1_SIZE:]
    rem_buckets = REG_SLICE_COUNT - 2  # s2..s5 共 4 片
    for i in range(rem_buckets):
        start = len(tail) * i // rem_buckets
        end = len(tail) * (i + 1) // rem_buckets
        slices.append(set(tail[start:end]))

    return slices


def format_unicode_range(chars):
    """将字符集编码为紧凑的 CSS unicode-range 值。"""
    cps = sorted(ord(c) for c in chars)
    if not cps:
        return ""
    ranges = []
    start = prev = cps[0]
    for cp in cps[1:]:
        if cp == prev + 1:
            prev = cp
        else:
            ranges.append(f"U+{start:X}" if start == prev else f"U+{start:X}-{prev:X}")
            start = prev = cp
    ranges.append(f"U+{start:X}" if start == prev else f"U+{start:X}-{prev:X}")
    return ",".join(ranges)


def render_faces_block(reg_entries, bold_entry, url_prefix="#{$baseRelURL}/fonts", compressed=False):
    """生成 GenRyuMinTC 的 @font-face 规则块（SCSS 模板版或压缩 CSS 版）。"""
    blocks = []
    for fname, chars in reg_entries:
        ur = format_unicode_range(chars)
        if compressed:
            blocks.append(
                f"@font-face{{font-family:'GenRyuMinTC';font-display:swap;"
                f"src:url(\"{url_prefix}/{fname}\") format(\"woff2\");"
                f"font-weight:400;font-style:normal;unicode-range:{ur}}}"
            )
        else:
            blocks.append(
                "@font-face {\n"
                "    font-family: 'GenRyuMinTC';\n"
                "    font-display: swap;\n"
                f"    src: url('{url_prefix}/{fname}') format('woff2');\n"
                "    font-weight: 400;\n"
                "    font-style: normal;\n"
                f"    unicode-range: {ur};\n"
                "}"
            )

    b_name, b_chars = bold_entry
    b_ur = format_unicode_range(b_chars)
    if compressed:
        blocks.append(
            f"@font-face{{font-family:'GenRyuMinTC';font-display:swap;"
            f"src:url(\"{url_prefix}/{b_name}\") format(\"woff2\");"
            f"font-weight:700;font-style:normal;unicode-range:{b_ur}}}"
        )
        return "/*! genryu-faces:start */" + "".join(blocks) + "/*! genryu-faces:end */"

    blocks.append(
        "@font-face {\n"
        "    font-family: 'GenRyuMinTC';\n"
        "    font-display: swap;\n"
        f"    src: url('{url_prefix}/{b_name}') format('woff2');\n"
        "    font-weight: 700;\n"
        "    font-style: normal;\n"
        f"    unicode-range: {b_ur};\n"
        "}"
    )
    return (
        "// 由 `npm run fonts:sync`（scripts/subset-genryu.py --write-static）自动生成，请勿手动编辑。\n"
        "/*! genryu-faces:start */\n"
        + "\n".join(blocks)
        + "\n/*! genryu-faces:end */\n"
    )


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


def file_digest(path):
    """按文件字节取 8 位 SHA-256 哈希，供非动态子集化的静态字体使用。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()[:8]


def glyph_digest(chars, src_path):
    """按「字集内容 + 源字体内容」取 8 位 SHA-256 哈希（跨平台/环境稳定）。"""
    h = hashlib.sha256()
    h.update("".join(sorted(chars)).encode("utf-8"))
    with open(src_path, "rb") as fh:
        h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()[:8]


def inspect_static_coverage(reg_chars, bold_chars, home_core):
    """检查 static/fonts 下已提交的分片与粗体子集能否覆盖当前构建的全部用字。"""
    reg_cmaps = []
    for name in REG_NAMES:
        path = os.path.join(STATIC_FONTS, name)
        if not os.path.exists(path):
            return False, None, None, f"缺少 {name}"
        reg_cmaps.append((name, {chr(o) for o in TTFont(path).getBestCmap()}))

    bold_path = os.path.join(STATIC_FONTS, BOLD_NAME)
    if not os.path.exists(bold_path):
        return False, None, None, f"缺少 {BOLD_NAME}"
    bold_cmap = {chr(o) for o in TTFont(bold_path).getBestCmap()}

    reg_union = set().union(*(c for _, c in reg_cmaps))
    s0_chars = reg_cmaps[0][1]

    miss_reg = sorted(reg_chars - reg_union)
    miss_home = sorted(home_core - s0_chars)
    miss_bold = sorted(bold_chars - bold_cmap)

    if miss_reg or miss_home or miss_bold:
        reasons = []
        if miss_reg:
            reasons.append(f"Regular 缺 {len(miss_reg)} 字({''.join(miss_reg[:20])})")
        if miss_home:
            reasons.append(f"s0 首页分片缺 {len(miss_home)} 字({''.join(miss_home[:20])})")
        if miss_bold:
            reasons.append(f"Bold 缺 {len(miss_bold)} 字({''.join(miss_bold[:20])})")
        return False, reg_cmaps, (BOLD_NAME, bold_cmap), "；".join(reasons)

    # 同时确认 _genryu-faces.scss 已包含全部 6 个分片声明
    if not os.path.exists(SCSS_FACES):
        return False, reg_cmaps, (BOLD_NAME, bold_cmap), "缺少 _genryu-faces.scss"
    with open(SCSS_FACES, encoding="utf-8") as fh:
        scss_text = fh.read()
    if not all(name in scss_text for name in (*REG_NAMES, BOLD_NAME)):
        return False, reg_cmaps, (BOLD_NAME, bold_cmap), "_genryu-faces.scss 分片声明不完整"

    return True, reg_cmaps, (BOLD_NAME, bold_cmap), ""


def fingerprint_and_patch(genryu_digests, faces_override=None):
    """给 public/fonts 下所有 woff2 加上内容哈希，并回写 CSS / HTML；主 CSS 重算指纹。"""
    font_mapping = {}
    hashed_stems = {}

    for old_name, digest in genryu_digests.items():
        path = os.path.join(OUT_DIR, old_name)
        stem = old_name[:-len(".woff2")]
        new_name = f"{stem}.{digest}.woff2"
        shutil.copyfile(path, os.path.join(OUT_DIR, new_name))
        font_mapping[old_name] = new_name
        hashed_stems[stem] = new_name

    # 顺手为其余静态 woff2 加内容哈希，使 /fonts/* 的 immutable 响应头全部名副其实
    for path in sorted(glob.glob(os.path.join(OUT_DIR, "*.woff2"))):
        old_name = os.path.basename(path)
        if old_name in font_mapping or old_name == LEGACY_REG_NAME or HASHED_WOFF2_RE.search(old_name):
            continue
        stem = old_name[:-len(".woff2")]
        d = file_digest(path)
        new_name = f"{stem}.{d}.woff2"
        shutil.copyfile(path, os.path.join(OUT_DIR, new_name))
        font_mapping[old_name] = new_name
        hashed_stems[stem] = new_name

    # 清理可能残留的旧单文件 Regular 副本
    legacy_pub = os.path.join(OUT_DIR, LEGACY_REG_NAME)
    if os.path.exists(legacy_pub):
        os.remove(legacy_pub)

    leftovers = set()

    def rewrite(text, mapping):
        for old, new in mapping.items():
            text = text.replace(old, new)
        leftovers.update(old for old in mapping if old in text)
        return text

    patched = 0
    css_mapping = {}
    for css in sorted(glob.glob(os.path.join(PUBLIC, "css", "*.css"))):
        with open(css, encoding="utf-8") as fh:
            text = fh.read()
        changed = False
        if faces_override is not None and FACES_BLOCK_RE.search(text):
            text = FACES_BLOCK_RE.sub(lambda _: faces_override, text, count=1)
            changed = True
        if any(old in text for old in font_mapping):
            text = rewrite(text, font_mapping)
            changed = True
        if not changed:
            continue

        old_css_name = os.path.basename(css)
        m = HASHED_CSS_RE.match(old_css_name)
        if m:
            new_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[: len(m.group("digest"))]
            new_css_name = f"{m.group('prefix')}.{new_digest}.css"
            new_css_path = os.path.join(os.path.dirname(css), new_css_name)
            with open(new_css_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            if new_css_name != old_css_name:
                os.remove(css)
                css_mapping[old_css_name] = new_css_name
        else:
            with open(css, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        patched += 1

    html_mapping = {**font_mapping, **css_mapping}
    for root, _, files in os.walk(PUBLIC):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if not any(old in text for old in html_mapping):
                continue
            text = rewrite(text, html_mapping)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            patched += 1

    if leftovers:
        print(f"警告：仍有 {len(leftovers)} 个资源引用未能改写，保留无哈希副本")
        return html_mapping, False

    for old_name in font_mapping:
        old_path = os.path.join(OUT_DIR, old_name)
        if os.path.exists(old_path):
            os.remove(old_path)

    for stem, keep_name in hashed_stems.items():
        for stray in glob.glob(os.path.join(OUT_DIR, f"{stem}.*.woff2")):
            if os.path.basename(stray) != keep_name:
                os.remove(stray)

    for old, new in html_mapping.items():
        print(f"{old} -> {new}")
    return html_mapping, patched > 0


def main():
    args = sys.argv[1:]
    reg_chars, bold_chars, home_core, doc_freq, pages = collect_chars()
    if len(reg_chars) < 500:
        sys.exit(f"只扫到 {len(reg_chars)} 个字，明显不对，停止")

    covered, static_reg, static_bold, reason = inspect_static_coverage(reg_chars, bold_chars, home_core)

    if "--check" in args:
        print(
            f"扫描 {pages} 个页面，Regular 用字 {len(reg_chars)} 个"
            f"（首页核心 {len(home_core)} 个），Bold 用字 {len(bold_chars)} 个"
        )
        if covered:
            print("static/fonts 分片与 Bold 子集覆盖完整")
            sys.exit(0)
        print(f"覆盖不完整：{reason}")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    write_static = "--write-static" in args
    force = "--force" in args
    reuse = covered and not force and not write_static

    faces_override = None
    if reuse:
        total = 0
        for name, _ in (*static_reg, static_bold):
            src = os.path.join(STATIC_FONTS, name)
            dst = os.path.join(OUT_DIR, name)
            shutil.copyfile(src, dst)
            total += os.path.getsize(dst)
        print(
            f"复用 static/fonts 已有分片与粗体子集（Regular {len(reg_chars)} 字 / Bold {len(bold_chars)} 字，"
            f"共 {total / 1024:.1f} KB），跳过子集化"
        )
        active_reg = static_reg
        active_bold = static_bold
    else:
        slices = partition_regular(reg_chars, home_core, doc_freq)
        active_reg = []
        reg_total = 0
        for name, chars in zip(REG_NAMES, slices):
            dst = os.path.join(OUT_DIR, name)
            size = subset(SRC_R, dst, chars)
            reg_total += size
            active_reg.append((name, chars))
            print(f"{name}: {size / 1024:7.1f} KB（{len(chars)} 字）")

        bold_dst = os.path.join(OUT_DIR, BOLD_NAME)
        bold_size = subset(SRC_B, bold_dst, bold_chars)
        active_bold = (BOLD_NAME, bold_chars)
        print(f"{BOLD_NAME}: {bold_size / 1024:7.1f} KB（{len(bold_chars)} 字）")

        total_before = os.path.getsize(SRC_R) + os.path.getsize(SRC_B)
        total_after = reg_total + bold_size
        print(
            f"页面 {pages} 个；{total_before / 1024 / 1024:.1f} MB -> "
            f"{total_after / 1024:.1f} KB（Regular 6 片 {reg_total / 1024:.1f} KB + Bold {bold_size / 1024:.1f} KB）"
        )

        # 慢路径（未固化进 _genryu-faces.scss）时，直接用最新 unicode-range 覆写 public CSS 中的 @font-face 区块
        faces_override = render_faces_block(active_reg, active_bold, url_prefix="/fonts", compressed=True)

        if not covered and not write_static:
            print(
                f"提示：{reason}，本次已重新切分。"
                "本地跑一次 `npm run fonts:sync` 可将分片与 _genryu-faces.scss 固化，之后回到快路径。"
            )

    if write_static:
        os.makedirs(STATIC_FONTS, exist_ok=True)
        for name, _ in (*active_reg, active_bold):
            shutil.copyfile(os.path.join(OUT_DIR, name), os.path.join(STATIC_FONTS, name))
            print(f"static/fonts/{name} 已更新")
        legacy_static = os.path.join(STATIC_FONTS, LEGACY_REG_NAME)
        if os.path.exists(legacy_static):
            os.remove(legacy_static)
            print(f"已移除旧单文件 static/fonts/{LEGACY_REG_NAME}")

        scss_content = render_faces_block(active_reg, active_bold, url_prefix="#{$baseRelURL}/fonts", compressed=False)
        with open(SCSS_FACES, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(scss_content)
        print(f"assets/scss/custom/_genryu-faces.scss 已更新")

    genryu_digests = {name: glyph_digest(chars, SRC_R) for name, chars in active_reg}
    genryu_digests[active_bold[0]] = glyph_digest(active_bold[1], SRC_B)

    try:
        fingerprint_and_patch(genryu_digests, faces_override=faces_override)
    except Exception as exc:
        print(f"警告：加内容哈希失败（{exc}），继续使用无哈希文件名")


if __name__ == "__main__":
    main()
