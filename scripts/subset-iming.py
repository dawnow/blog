#!/usr/bin/env python3
"""I.MingCP 子集化：爬构建产物收集实际用字，生成 woff2 子集。
用法：先 hugo 构建（输出到 public/），再在仓库根目录运行：
    python3 scripts/subset-iming.py
产物：static/fonts/I.MingCP-8.10-subset.woff2
新文章用了生僻字时重跑一遍即可（未覆盖的字会 fallback 到 serif，不会乱码）。
"""
import os
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter, Options

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, 'public')
SRC_FONT = os.path.join(REPO, 'static', 'fonts', 'I.MingCP-8.10.woff2')
OUT_FONT = os.path.join(REPO, 'static', 'fonts', 'I.MingCP-8.10-subset.woff2')

chars = set()
n = 0
for root, _, files in os.walk(BUILD):
    for f in files:
        if f.endswith('.html'):
            n += 1
            with open(os.path.join(root, f), encoding='utf-8', errors='ignore') as fh:
                chars.update(fh.read())
chars = {c for c in chars if c.isprintable() or c in '\n\t'}
print(f'扫描 HTML: {n} 个，收集到 {len(chars)} 个不同字符')

cps = sorted(ord(c) for c in chars)
opts = Options()
opts.flavor = 'woff2'
opts.layout_features = '*'
opts.name_IDs = ['*']
opts.notdef_outline = True
opts.desubroutinize = True
ss = Subsetter(opts)
ss.populate(unicodes=cps)
font = TTFont(SRC_FONT)
ss.subset(font)
font.save(OUT_FONT)
print(f'子集字形数: {len(cps)}，大小: {os.path.getsize(OUT_FONT)/1024/1024:.2f} MB')
print(f'已写入: {OUT_FONT}')
