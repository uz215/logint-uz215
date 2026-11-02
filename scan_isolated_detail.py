# -*- coding: utf-8 -*-
"""精确扫描 isolated_profile.png: 确认 1103-1373m 区域颜色"""
from PIL import Image
import numpy as np

Image.MAX_IMAGE_PIXELS = None
img = Image.open(r'f:\360\src\isolated_profile.png').convert('RGB')
W, H = img.size
print("尺寸:", W, "x", H)

arr = np.array(img)

# 图像 y 像素 → 深度（ylim 330-2850，从上到下）
# 先找实际绘制区域：扫描非白行的 y 范围
nonwhite_rows = np.where((arr != 255).any(axis=(1, 2)))[0]
print("非白行 y 范围:", nonwhite_rows.min(), "-", nonwhite_rows.max())

# 使用整个图像高度映射（假设绘制区占满，bbox tight 已裁剪）
px_per_m = H / (2850 - 330)
print(f"每米像素: {px_per_m:.2f}")

def md_to_y(md):
    return int((2850 - md) * px_per_m)

def y_to_md(y):
    return 2850 - y / px_per_m

# PROFILE 道 x 范围（ax 是 subplot(111)，后 set_position([x0, 0, w, 0.9737])）
# 道在图中 x 范围 = ax 宽度，需要从图里找。先看整体：扫描中间 x=W//2
mid_x = W // 2
print("\n中间列 x=%d 颜色段:" % mid_x)
prev = None
start = 0
segments = []
for y in range(0, H, 4):
    c = tuple(arr[y, mid_x])
    if c != prev:
        if prev is not None:
            segments.append((start, y, prev))
        prev = c
        start = y
segments.append((start, H, prev))

for s0, s1, c in segments:
    if s1 - s0 < 50:
        continue
    md0, md1 = y_to_md(s1), y_to_md(s0)
    print(f"  y[{s0}-{s1}] md[{md0:.1f}-{md1:.1f}] 颜色={c}")

# 直接扫描 1103-1373m 区域的颜色统计
print("\n=== 1103-1373m 颜色统计（中间列附近 x=W/2±20） ===")
from collections import Counter
cnt = Counter()
for y in range(md_to_y(1373), md_to_y(1103)):
    for x in range(mid_x - 20, mid_x + 21):
        cnt[tuple(arr[y, x])] += 1
for c, n in cnt.most_common(8):
    print(f"  {c}: {n}")

# 1290-1310m（应纯石英储层）
print("\n=== 1290-1310m 颜色统计 ===")
cnt = Counter()
for y in range(md_to_y(1310), md_to_y(1290)):
    for x in range(mid_x - 20, mid_x + 21):
        cnt[tuple(arr[y, x])] += 1
for c, n in cnt.most_common(8):
    print(f"  {c}: {n}")

# 2700-2720m（应泥岩绿色）
print("\n=== 2700-2720m 颜色统计 ===")
cnt = Counter()
for y in range(md_to_y(2720), md_to_y(2700)):
    for x in range(mid_x - 20, mid_x + 21):
        cnt[tuple(arr[y, x])] += 1
for c, n in cnt.most_common(8):
    print(f"  {c}: {n}")
