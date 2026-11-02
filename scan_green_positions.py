# -*- coding: utf-8 -*-
"""扫描g4(全井段)图中所有Shale绿色段的位置，换算md与数据对比"""
import sys
sys.path.insert(0, r'f:\360\src')
import numpy as np
import pandas as pd
from PIL import Image

img = Image.open(r'f:\360\src\exp_g4_full_full.png').convert('RGB')
w2, h2 = img.size
arr = np.array(img)
X0r, X1r = int(w2*0.7368), int(w2*0.8184)
print(f'尺寸 {w2}x{h2}, profile道 x={X0r}-{X1r}')

def md2y(md): return int((md-330.0)/2520.0 * 0.9737 * h2)
def y2md(y): return 330.0 + (y / (0.9737 * h2)) * 2520.0

# 逐行扫描：该行是否有浅绿(47,180,114)像素
green_rows = []
for y in range(0, h2):
    row = arr[y, X0r:X1r]
    # 快速判断：行内任意像素接近(47,180,114)
    mask = (np.abs(row[:, 0].astype(int) - 47) < 25) & \
           (np.abs(row[:, 1].astype(int) - 180) < 25) & \
           (np.abs(row[:, 2].astype(int) - 114) < 25)
    if mask.any():
        green_rows.append(y)

# 合并连续行
segments = []
if green_rows:
    start = prev = green_rows[0]
    for y in green_rows[1:]:
        if y - prev > 3:
            segments.append((start, prev))
            start = y
        prev = y
    segments.append((start, prev))

print(f'\n=== 全井段渲染中 Shale绿色段位置 ===')
for s, e in segments:
    md_s, md_e = y2md(s), y2md(e)
    h_px = e - s
    # 如果段宽>3px，说明有连续绿色（非孤立像素）
    tag = '连续' if h_px > 3 else '孤立'
    print(f'y[{s},{e}] h={h_px}px  md[{md_s:.1f},{md_e:.1f}]  {tag}')

# 数据中的泥岩段
csv_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv'
df = pd.read_csv(csv_path).sort_values('MD').reset_index(drop=True)
shale = df[df['LITHOLOGY'].str.lower().str.strip() == 'shale']
print(f'\n=== 数据中 shale 段 ===')
if len(shale) > 0:
    segs = []
    start = prev_md = shale['MD'].iloc[0]
    for md in shale['MD'].iloc[1:]:
        if md - prev_md > 0.3:
            segs.append((start, prev_md))
            start = md
        prev_md = md
    segs.append((start, prev_md))
    for s, e in segs:
        print(f'md[{s:.1f},{e:.1f}] 厚{e-s:.1f}m')
else:
    print('无shale段')
