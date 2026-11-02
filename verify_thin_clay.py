# -*- coding: utf-8 -*-
"""高dpi验证：全井段渲染 profile 道，精确检查 1102.0-1104.0m 薄泥岩层像素"""
import sys
sys.path.insert(0, r'f:\360\src')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from collections import Counter
from log_visualizer import _setup_profile_track

csv_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv'
df = pd.read_csv(csv_path).sort_values('MD').reset_index(drop=True)
depth = df['MD']
depth_min = 330
depth_max = 2850

# ===== 实验A: 全井段渲染（高dpi 200）=====
fig = plt.figure(figsize=(4, 120))
ax = fig.add_axes([0.7368, 0.0, 0.0816, 0.9737])
_setup_profile_track(ax, df, depth, depth_min, depth_max, 1.0, 0.9737, 0.997, True)
print(f'ylim: {ax.get_ylim()}')
fig.savefig(r'f:\360\src\verify_full_hi.png', dpi=200)
plt.close(fig)
print('Saved: verify_full_hi.png')

img = Image.open(r'f:\360\src\verify_full_hi.png').convert('RGB')
w2, h2 = img.size
arr = np.array(img)
print(f'尺寸: {w2}x{h2}')
X0r, X1r = int(w2*0.7368), int(w2*0.8184)

def md2y(md): return int((md-330.0)/2520.0 * 0.9737 * h2)

# 逐0.1m统计 1101.0-1105.0m 的像素
print('\n=== 全井段渲染: 1101.0-1105.0m 逐0.1m颜色统计 ===')
shale_green = lambda c: abs(int(c[0])-47) < 25 and abs(int(c[1])-180) < 25 and abs(int(c[2])-114) < 25
for md_start in np.arange(1101.0, 1105.0, 0.1):
    y_lo, y_hi = md2y(md_start), md2y(md_start+0.1)
    if y_hi <= y_lo:
        continue
    region = arr[y_lo:y_hi, X0r:X1r].reshape(-1, 3)
    if len(region) == 0:
        continue
    cnt = Counter(map(tuple, region))
    total = len(region)
    g = sum(n for c, n in cnt.items() if shale_green(c))
    yel = sum(n for c, n in cnt.items() if int(c[0]) > 235 and int(c[1]) > 235 and int(c[2]) < 40)
    white = sum(n for c, n in cnt.items() if int(c[0]) > 240 and int(c[1]) > 240 and int(c[2]) > 240)
    if total > 0:
        print(f'  {md_start:.1f}-{md_start+0.1:.1f}m: 绿={g/total*100:5.1f}% 黄={yel/total*100:5.1f}% 白={white/total*100:5.1f}%')

# 保存1100-1106m裁剪放大
crop = img.crop((int(w2*0.70), md2y(1100.0)-5, int(w2*0.85), md2y(1106.0)+5))
crop_big = crop.resize((crop.size[0]*6, crop.size[1]*6), Image.NEAREST)
crop_big.save(r'f:\360\src\verify_crop_1100_1106.png')
print('Saved: verify_crop_1100_1106.png')
