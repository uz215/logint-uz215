# -*- coding: utf-8 -*-
"""扫描最新大图，确认1102.5-1103.1m薄泥岩层 + 颜色分布"""
import numpy as np
from PIL import Image
from collections import Counter

Image.MAX_IMAGE_PIXELS = None

img_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_174052.png'
img = Image.open(img_path).convert('RGB')
w, h = img.size
print(f'Image size: {w}x{h}')
arr = np.array(img)

X0, X1 = int(w * 0.7368), int(w * 0.8184)
K = 111416 / 2520.0
def md_to_y(md): return int((md - 330.0) * K)

def scan(md_lo, md_hi, label):
    y_lo, y_hi = sorted([md_to_y(md_lo), md_to_y(md_hi)])
    region = arr[y_lo:y_hi, X0:X1].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    # 泥岩绿 (47,180,114) 及其附近色
    shale_green = sum(n for c, n in cnt.items()
                      if abs(c[0]-47) < 25 and abs(c[1]-180) < 25 and abs(c[2]-114) < 25)
    yellow = sum(n for c, n in cnt.items() if c[0] > 235 and c[1] > 235 and c[2] < 40)
    white = sum(n for c, n in cnt.items() if c[0] > 240 and c[1] > 240 and c[2] > 240)
    dark = sum(n for c, n in cnt.items() if max(c) < 80)
    print(f'{label}: 泥岩绿={shale_green/total*100:.1f}% 黄={yellow/total*100:.1f}% 白={white/total*100:.1f}% 黑={dark/total*100:.1f}%')

scan(1100, 1102, '1100-1102m 上覆')
scan(1102, 1103, '1102-1103m 薄泥岩区')
scan(1103, 1104, '1103-1104m 石英顶')
scan(2700, 2720, '2700-2720m 泥岩(验证)')

# 细扫1102-1104
print('\n细扫 (每0.1m):')
for md in np.arange(1102.0, 1104.0, 0.1):
    y_lo, y_hi = md_to_y(md), md_to_y(md + 0.1)
    region = arr[y_lo:y_hi, X0:X1].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    shale_green = sum(n for c, n in cnt.items()
                      if abs(c[0]-47) < 25 and abs(c[1]-180) < 25 and abs(c[2]-114) < 25)
    yellow = sum(n for c, n in cnt.items() if c[0] > 235 and c[1] > 235 and c[2] < 40)
    top2 = cnt.most_common(3)
    print(f'md {md:.1f}-{md+0.1:.1f}: 泥岩绿={shale_green/total*100:.0f}% 黄={yellow/total*100:.0f}% top: '
          + ', '.join(f'{tuple(int(v) for v in c)}:{n/total*100:.0f}%' for c, n in top2))
