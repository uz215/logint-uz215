# -*- coding: utf-8 -*-
"""扫描 isolated_profile.png 的 1103-1373m 区域（y 117190-138660）"""
from PIL import Image
import numpy as np
from collections import Counter

Image.MAX_IMAGE_PIXELS = None
img = Image.open(r'f:\360\src\isolated_profile.png').convert('RGB')
W, H = img.size
arr = np.array(img)
px_per_m = H / (2850 - 330)
print(f"尺寸 {W}x{H}, 每米 {px_per_m:.2f}px")

def md_to_y(md):
    return int((2850 - md) * px_per_m)

def y_to_md(y):
    return 2850 - y / px_per_m

# x=771 中间列，1103-1373m 颜色段（细粒度，步长1）
y0, y1 = md_to_y(1373.6), md_to_y(1102.0)
print(f"\n中间列 x=771: y[{y0}-{y1}] = md[1102-1373.6] 颜色段（合并相邻相同色）:")
prev = None
start = 0
segs = []
for y in range(y0, y1):
    c = tuple(arr[y, 771])
    if c != prev:
        if prev is not None:
            segs.append((start, y, prev))
        prev = c
        start = y
segs.append((start, y1, prev))

# 合并相邻相同颜色段
merged = []
for s0, s1, c in segs:
    if merged and merged[-1][2] == c and s0 - merged[-1][1] < 3:
        merged[-1] = (merged[-1][0], s1, c)
    else:
        merged.append((s0, s1, c))

for s0, s1, c in merged:
    if s1 - s0 < 10:
        continue
    print(f"  y[{s0}-{s1}] ({s1-s0}px) md[{y_to_md(s1):.1f}-{y_to_md(s0):.1f}] 颜色={c}")

# 颜色统计
cnt = Counter()
for y in range(y0, y1):
    for x in range(700, 843):
        cnt[tuple(arr[y, x])] += 1
total = sum(cnt.values())
print(f"\n1103-1373m 道内(x700-842)颜色统计, 总 {total}px:")
for c, n in cnt.most_common(8):
    print(f"  {c}: {n} ({100*n/total:.1f}%)")
