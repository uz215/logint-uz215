# -*- coding: utf-8 -*-
"""用正确映射扫描大图 170824.png 的 PROFILE 道"""
from PIL import Image
import numpy as np
from collections import Counter

Image.MAX_IMAGE_PIXELS = None
img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_170824.png').convert('RGB')
W, H = img.size
arr = np.array(img)
print(f"大图 {W}x{H}")

# 正确映射：ylim(2850, 330)，330m 在顶部（y=0）
# md = 330 + y * 2520 / H_img，其中 H_img 是曲线区高度
# 曲线区: AXES_H = 0.9737 → 曲线区像素高 = 0.9737*H
curve_px = int(H * 0.9737)
def y_to_md(y):
    return 330 + y * 2520 / curve_px

def md_to_y(md):
    return int((md - 330) * curve_px / 2520)

# PROFILE 道 x 范围: 0.7368-0.8184 → 像素
x0, x1 = int(0.7368 * W), int(0.8184 * W)
print(f"PROFILE 道 x: {x0}-{x1}")

# 扫描 1103-1373m
y0, y1 = md_to_y(1103), md_to_y(1373)
print(f"1103-1373m → y[{y0}-{y1}]")

cnt = Counter()
for y in range(y0, y1, 2):
    for x in range(x0, x1):
        cnt[tuple(arr[y, x])] += 1
total = sum(cnt.values())
print(f"\n=== 1103-1373m PROFILE道颜色统计（{total}px）===")
for c, n in cnt.most_common(8):
    print(f"  {c}: {n} ({100*n/total:.1f}%)")

# 绿色阈值（Shale 底 47,180,114）
def is_green(c):
    return c[1] > 100 and c[0] < 100 and c[2] < 150
def is_yellow(c):
    return c[0] > 200 and c[1] > 200 and c[2] < 100

# 绿色行分布
green_rows = [y for y in range(y0, y1) if any(is_green(tuple(arr[y, x])) for x in range(x0, x1, 4))]
print(f"\n绿色行数: {len(green_rows)} / {y1-y0}")

# 找绿色行分段
if green_rows:
    groups = []
    start = prev = green_rows[0]
    for r in green_rows[1:]:
        if r - prev > 3:
            groups.append((start, prev))
            start = r
        prev = r
    groups.append((start, prev))
    print("绿色行分段（→深度）:")
    for g0, g1 in groups[:30]:
        print(f"  y[{g0}-{g1}] md[{y_to_md(g0):.1f}-{y_to_md(g1):.1f}]")

# 采样：1290-1310m
y0, y1 = md_to_y(1290), md_to_y(1310)
cnt = Counter()
for y in range(y0, y1, 2):
    for x in range(x0, x1):
        cnt[tuple(arr[y, x])] += 1
total = sum(cnt.values())
print(f"\n=== 1290-1310m PROFILE道颜色统计 ===")
for c, n in cnt.most_common(6):
    print(f"  {c}: {n} ({100*n/total:.1f}%)")

# 采样：1800-1890m（之前 y=68650 绿色区域）
y0, y1 = md_to_y(1800), md_to_y(1890)
cnt = Counter()
for y in range(y0, y1, 2):
    for x in range(x0, x1):
        cnt[tuple(arr[y, x])] += 1
total = sum(cnt.values())
print(f"\n=== 1800-1890m PROFILE道颜色统计 ===")
for c, n in cnt.most_common(6):
    print(f"  {c}: {n} ({100*n/total:.1f}%)")
