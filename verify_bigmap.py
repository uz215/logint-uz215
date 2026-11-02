# -*- coding: utf-8 -*-
"""重新生成大图，捕获profile道真实ylim/位置，用正确公式扫描薄泥岩层"""
import sys
sys.path.insert(0, r'f:\360\src')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # 解除大图像素限制
from collections import Counter

import log_visualizer as lv

captured = {}
orig = lv._setup_profile_track
def wrapped(ax, data, depth, depth_min, depth_max, *args, **kwargs):
    result = orig(ax, data, depth, depth_min, depth_max, *args, **kwargs)
    captured['ylim'] = tuple(float(v) for v in ax.get_ylim())
    captured['pos'] = tuple(float(v) for v in ax.get_position().bounds)
    return result
lv._setup_profile_track = wrapped

csv_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv'
data = pd.read_csv(csv_path)
results = {'well_name': 'XIMENIA-5', 'output_dir': r'f:\360\src\output\XIMENIA-5', 'las_info': {}, 'processed_data': data}
print('Generating...')
out_path = lv.visualize_composite_log(data, results)
print('ylim:', captured.get('ylim'))
print('pos:', captured.get('pos'))
if not out_path:
    print('FAILED')
    sys.exit(1)

img = Image.open(out_path).convert('RGB')
w2, h2 = img.size
arr = np.array(img)
print(f'大图: {w2}x{h2}')

# 从捕获的pos计算扫描映射
x0, y0, w_frac, h_frac = captured['pos']
ylim_bottom, ylim_top = captured['ylim']  # get_ylim返回(bottom, top)
d_top, d_bot = ylim_top, ylim_bottom  # 20在顶部(浅), 2850在底部(深)
print(f'映射: 顶部={d_top}m 底部={d_bot}m 曲线区高={h_frac:.4f}')

X0r, X1r = int(w2*x0), int(w2*(x0+w_frac))
print(f'profile道 x: {X0r}-{X1r}')

def y_px_from_top(md):
    """md -> 从顶部数的像素行"""
    frac = (md - d_top) / (d_bot - d_top)  # 顶部=d_top
    return int((1.0 - h_frac) * h2 + frac * h_frac * h2)

shale_green = lambda c: abs(int(c[0])-47) < 25 and abs(int(c[1])-180) < 25 and abs(int(c[2])-114) < 25

# 1. 精确扫描1102.0-1104.0m
print('\n=== 1102.0-1104.0m 逐0.1m ===')
for md_start in np.arange(1102.0, 1104.0, 0.1):
    y_lo, y_hi = y_px_from_top(md_start), y_px_from_top(md_start+0.1)
    region = arr[y_lo:y_hi, X0r:X1r].reshape(-1, 3)
    if len(region) == 0:
        continue
    cnt = Counter(map(tuple, region))
    total = len(region)
    g = sum(n for c, n in cnt.items() if shale_green(c))
    yel = sum(n for c, n in cnt.items() if int(c[0]) > 235 and int(c[1]) > 235 and int(c[2]) < 40)
    white = sum(n for c, n in cnt.items() if int(c[0]) > 240 and int(c[1]) > 240 and int(c[2]) > 240)
    print(f'  {md_start:.1f}-{md_start+0.1:.1f}m: 绿={g/total*100:5.1f}% 黄={yel/total*100:5.1f}% 白={white/total*100:5.1f}%')

# 2. 对照：已知厚泥岩段（2700-2720m数据）
print('\n=== 对照2700-2720m ===')
for md_start in [2700.0, 2705.0, 2710.0, 2715.0]:
    y_lo, y_hi = y_px_from_top(md_start), y_px_from_top(md_start+5.0)
    region = arr[y_lo:y_hi, X0r:X1r].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    g = sum(n for c, n in cnt.items() if shale_green(c))
    print(f'  {md_start:.0f}-{md_start+5:.0f}m: 绿={g/total*100:.1f}%')

# 3. 保存裁剪图
crop = img.crop((int(w2*0.70), y_px_from_top(1100.0)-5, int(w2*0.85), y_px_from_top(1106.0)+5))
crop_big = crop.resize((crop.size[0]*8, crop.size[1]*8), Image.NEAREST)
crop_big.save(r'f:\360\src\bigmap_crop_1100_1106.png')
print(f'\nSaved: bigmap_crop_1100_1106.png ({crop_big.size})')
print(f'大图保存: {out_path}')
