# -*- coding: utf-8 -*-
"""大范围扫描PROFILE道颜色分布（md 950-1400逐5m），校准公式"""
import numpy as np
from PIL import Image
from collections import Counter
Image.MAX_IMAGE_PIXELS = None

img_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_174052.png'
img = Image.open(img_path).convert('RGB')
w, h = img.size
arr = np.array(img)

H_CURVE = int(h * 0.9737)
Y_TOP = h - H_CURVE

def md_to_y(md):
    return Y_TOP + int((md - 330.0) * H_CURVE / 2520.0)

def shale_ratio(y_lo, y_hi):
    region = arr[y_lo:y_hi, 3536:3928].reshape(-1, 3)
    cnt = Counter(map(tuple, region))
    total = len(region)
    g = sum(n for c, n in cnt.items()
            if abs(int(c[0])-47) < 25 and abs(int(c[1])-180) < 25 and abs(int(c[2])-114) < 25)
    return g/total*100, cnt.most_common(1)[0] if cnt else ((0,0,0), 0)

print('md区间 | Shale绿% | 主色')
for md in range(950, 1400, 5):
    y_lo, y_hi = md_to_y(md), md_to_y(md+5)
    g, (c, n) = shale_ratio(y_lo, y_hi)
    bar = '#' * int(g/5)
    print(f'{md:4d}-{md+5:4d}m | {g:5.1f}% | RGB{c} {n} {bar}')
