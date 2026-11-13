# -*- coding: utf-8 -*-
"""正确公式扫描：md = 330 + (y - y_top) * 2520 / H_curve，y_top = 3009, H_curve = 111416"""
import numpy as np
from PIL import Image
from collections import Counter

Image.MAX_IMAGE_PIXELS = None

img_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_174052.png'
img = Image.open(img_path).convert('RGB')
w, h = img.size
arr = np.array(img)

# PROFILE道: Axes[8] x0=0.7368 x1=0.8184
X0, X1 = int(w * 0.7368), int(w * 0.8184)
# 曲线区: y1=0.9737 → 曲线区高度 = 0.9737*h, 顶部偏移 = h - H_curve
H_CURVE = int(h * 0.9737)
Y_TOP = h - H_CURVE
print(f'Image {w}x{h}, 曲线区 y[{Y_TOP}-{h}], 高度 {H_CURVE}')

def md_to_y(md):
    return Y_TOP + int((md - 330.0) * H_CURVE / 2520.0)

def scan(md_lo, md_hi, label):
    y_lo, y_hi = sorted([md_to_y(md_lo), md_to_y(md_hi)])
    region = arr[y_lo:y_hi, X0:X1].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    shale_green = sum(n for c, n in cnt.items()
                      if abs(c[0]-47) < 25 and abs(c[1]-180) < 25 and abs(c[2]-114) < 25)
    fill_green = sum(n for c, n in cnt.items()
                     if abs(c[0]-34) < 15 and abs(c[1]-139) < 15 and abs(c[2]-34) < 15)
    yellow = sum(n for c, n in cnt.items() if c[0] > 235 and c[1] > 235 and c[2] < 40)
    white = sum(n for c, n in cnt.items() if c[0] > 240 and c[1] > 240 and c[2] > 240)
    dark = sum(n for c, n in cnt.items() if max(c) < 80)
    print(f'{label} md[{md_lo}-{md_hi}] y[{y_lo}-{y_hi}]: '
          f'Shale绿={shale_green/total*100:.1f}% fill绿={fill_green/total*100:.1f}% '
          f'黄={yellow/total*100:.1f}% 白={white/total*100:.1f}% 黑={dark/total*100:.1f}%')

# 验证公式: 石英大段 1103-1373 应为黄; 泥岩大段 1800-1890 应为 Shale绿
scan(1100, 1102, '1100-1102m 上覆石英')
scan(1102, 1103, '1102-1103m 薄泥岩区')
scan(1103, 1104, '1103-1104m 石英顶')
scan(1104, 1110, '1104-1110m 石英')
scan(1800, 1810, '1800-1810m (混合)')
scan(2700, 2720, '2700-2720m 泥岩验证')

print('\n细扫 1102.0-1104.0 每0.1m:')
for md in np.arange(1102.0, 1104.0, 0.1):
    y_lo, y_hi = md_to_y(md), md_to_y(md + 0.1)
    region = arr[y_lo:y_hi, X0:X1].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    shale_green = sum(n for c, n in cnt.items()
                      if abs(c[0]-47) < 25 and abs(c[1]-180) < 25 and abs(c[2]-114) < 25)
    yellow = sum(n for c, n in cnt.items() if c[0] > 235 and c[1] > 235 and c[2] < 40)
    top2 = cnt.most_common(3)
    print(f'md {md:.1f}-{md+0.1:.1f}: Shale绿={shale_green/total*100:.0f}% 黄={yellow/total*100:.0f}% top: '
          + ', '.join(f'{tuple(int(v) for v in c)}:{n/total*100:.0f}%' for c, n in top2))
