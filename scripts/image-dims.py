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
        req = urllib.request.Request(urllib.parse.quote(url, safe=":/") + "?imageInfo")
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return url, int(data["width"]), int(data["height"])
    except Exception:
        return url, 0, 0


def main():
    urls = collect_urls()
    if not urls:
        sys.exit("没有在 content/ 里找到图床图片")

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(fetch_dims, urls))

    dims = {}
    missing = 0
    for url, w, h in rows:
        if not w or not h:
            missing += 1
            continue
        key = url[len(HOST):]
        dims[key] = [w, h]
        decoded = urllib.parse.unquote(key)
        if decoded != key:
            dims[decoded] = [w, h]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(dims, fh, ensure_ascii=False, separators=(",", ":"))

    print(f"URL {len(urls)} 个，写入 {len(dims)} 条，未命中 {missing}")
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
