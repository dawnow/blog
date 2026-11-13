#!/usr/bin/env python3
"""重新生成 data/imagedims.json —— 图片宽高表，用于给 <img> 加 width/height。

为什么需要：图片没有尺寸时，浏览器要等下载完才知道占多大空间，页面会往下跳
（CLS）。有了尺寸表，渲染钩子就能提前把位置留好。

用法：
    hugo --gc --minify          # 先构建，确保内容已渲染
    python scripts/image-dims.py

脚本会扫描 content/ 里引用的图床图片（img.thethinningdark.com），逐张调用
COS 的 ?imageInfo 取当前宽高，写入 data/imagedims.json。发新文章、或者替换过
图床原图之后跑一次即可；构建不会自动跑它，因为需要在构建时访问网络。

依赖：Python 3.9+，只用标准库（urllib / json）。
"""

import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HOST = "https://img.thethinningdark.com/images/"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "imagedims.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def collect_urls():
    urls = set()
    for root, _, files in os.walk(os.path.join(REPO, "content")):
        for name in files:
            if not name.endswith(".md"):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for m in re.finditer(r"!\[[^\]]*\]\(\s*<([^>]+)>", text):
                urls.add(m.group(1))
            for m in re.finditer(r"!\[[^\]]*\]\(\s*([^)\s<>]+)", text):
                urls.add(m.group(1))
    return sorted(u for u in urls if u.startswith(HOST))


def fetch_dims(url):
    try:
        # safe 里必须保留 %：content/ 里有些图片名本来就是百分号编码的中文，
        # 再 quote 一次会变成 %25E4%25B8... 的双重编码，COS 直接 404。
        req = urllib.request.Request(urllib.parse.quote(url, safe=":/%") + "?imageInfo")
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return url, int(data["width"]), int(data["height"])
    except Exception:
        return url, 0, 0


def load_previous():
    try:
        with open(OUT, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def main():
    urls = collect_urls()
    if not urls:
        sys.exit("没有在 content/ 里找到图床图片")

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(fetch_dims, urls))

    # 并发跑完后串行补一次：COS 的 ?imageInfo 在并发下偶尔会失败，
    # 一次失败不代表图片真的没了，不能据此把已有条目删掉。
    retried = []
    for url, w, h in rows:
        if w and h:
            retried.append((url, w, h))
            continue
        time.sleep(0.3)
        retried.append(fetch_dims(url))

    previous = load_previous()
    dims = {}
    missing = []
    for url, w, h in retried:
        key = url[len(HOST):]
        if not w or not h:
            missing.append(key)
            # 补不到就沿用上次的尺寸，宁可保留旧数据，也不要静默丢条目
            for k in (key, urllib.parse.unquote(key)):
                if k in previous:
                    dims[k] = previous[k]
            continue
        dims[key] = [w, h]
        decoded = urllib.parse.unquote(key)
        if decoded != key:
            dims[decoded] = [w, h]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(dims, fh, ensure_ascii=False, separators=(",", ":"))

    print(f"URL {len(urls)} 个，写入 {len(dims)} 条，未命中 {len(missing)}")
    for key in missing:
        print(f"  未命中: {key}（已沿用旧尺寸，若确已删除请手动清理）")
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
