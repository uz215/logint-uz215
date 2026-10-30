# -*- coding: utf-8 -*-
"""用已知岩性边界反推大图深度映射"""
from PIL import Image
import numpy as np
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_164546.png').convert('RGB')
W, H = img.size
print(f'图片尺寸: {W}x{H}')

# profile道 x范围 3536-3928 (0.7368-0.8184)
x0, x1 = 3536, 3928

arr = np.array(img)
prof = arr[:, x0:x1, :]

def classify(rgb):
    r, g, b = rgb
    if abs(r-255) < 10 and abs(g-255) < 10 and abs(b-0) < 30:
        return 'Y'  # 黄色砂岩
    if abs(r-47) < 25 and abs(g-180) < 25 and abs(b-114) < 25:
        return 'G'  # 绿色泥岩
    if r > 240 and g > 240 and b > 240:
        return 'W'  # 白色
    return 'O'

# 扫描每行中间列的颜色
mid = (x1 - x0) // 2
rows = []
for y in range(H):
    c = classify(arr[y, x0 + mid, :])
    rows.append(c)

# 找颜色变化边界（黄色↔绿色）
print('颜色段（每段至少200行）:')
prev = rows[0]
start = 0
for y in range(1, H):
    if rows[y] != prev:
        if y - start >= 200:
            print(f'  y={start}-{y-1} ({y-start}行) {prev}')
        prev = rows[y]
        start = y
if H - start >= 200:
    print(f'  y={start}-{H-1} ({H-start}行) {prev}')

# 找所有 Y->G 或 G->Y 边界（粗扫：统计每200行的主色）
print('\n每200行主色:')
block = 200
for b0 in range(0, H, block):
    b1 = min(b0 + block, H)
    cnt = {}
    for y in range(b0, b1):
        c = rows[y]
        cnt[c] = cnt.get(c, 0) + 1
    main = max(cnt, key=cnt.get)
    frac = cnt[main] / (b1 - b0)
    print(f'  y={b0}-{b1}: {main} ({frac:.0%})')
