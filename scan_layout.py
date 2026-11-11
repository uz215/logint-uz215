# -*- coding: utf-8 -*-
"""扫描大图左侧各道的实际位置和1100-1110m内容"""
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_181212.png').convert('RGB')
w2, h2 = img.size
arr = np.array(img)
print(f'尺寸: {w2}x{h2}')

Y_TOP = int((1-0.9737078243444848)*h2)
H_CURVE = int(0.9737078243444848*h2)
def y_px(md): return Y_TOP + int((md-20)/(2850-20)*H_CURVE)

y_lo, y_hi = y_px(1100.0), y_px(1110.0)

# 每100px一列，检查该列在1100-1110m是否有非白内容
print('\n=== 各x列的内容分布 (1100-1110m) ===')
for x_start in range(0, 2400, 100):
    seg = arr[y_lo:y_hi, x_start:x_start+100].reshape(-1, 3)
    cnt_nonwhite = np.sum(np.any(seg < 245, axis=1))
    frac = cnt_nonwhite / len(seg) * 100
    if frac > 1:
        # 主色统计
        from collections import Counter
        c = Counter(map(tuple, seg[seg.max(axis=1) < 245] if len(seg[seg.max(axis=1) < 245]) else seg))
        top3 = c.most_common(3)
        print(f'x[{x_start},{x_start+100}]: 非白={frac:.0f}% 主色={[f"RGB{c}" for c, n in top3]}')

# 岩性道范围假设0-600px，打印更细
print('\n=== 岩性道区域 (0-600px) 逐100px ===')
for x_start in range(0, 600, 100):
    seg = arr[y_lo:y_hi, x_start:x_start+100].reshape(-1, 3)
    from collections import Counter
    c = Counter(map(tuple, seg))
    total = len(seg)
    yel = sum(n for c2, n in c.items() if int(c2[0]) > 235 and int(c2[1]) > 235 and int(c2[2]) < 40)
    grn = sum(n for c2, n in c.items() if abs(int(c2[0])-47) < 25 and abs(int(c2[1])-180) < 25 and abs(int(c2[2])-114) < 25)
    wht = sum(n for c2, n in c.items() if int(c2[0]) > 240 and int(c2[1]) > 240 and int(c2[2]) > 240)
    print(f'x[{x_start},{x_start+100}]: 黄={yel/total*100:.0f}% 绿={grn/total*100:.0f}% 白={wht/total*100:.0f}%')
