# -*- coding: utf-8 -*-
"""逐行扫描68600-68750，确认白线间隙"""
from PIL import Image
import numpy as np
Image.MAX_IMAGE_PIXELS = None

out_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_164546.png'
img = Image.open(out_path).convert('RGB')
w, h = img.size
x0, x1 = int(w*0.7368), int(w*0.8184)

prev_cls = ''
for y in range(68600, 68750):
    row = np.array(img.crop((x0, y, x1, y+1)))[0]
    # 主色
    from collections import Counter
    cnt = Counter(map(tuple, row))
    main = cnt.most_common(1)[0]
    c = main[0]
    if c[0] > 245 and c[1] > 245 and c[2] > 245:
        cls = 'W白'
    elif c[2] > 200 and c[0] > 200:
        cls = 'Y黄'
    elif c[1] > 100 and c[1] > c[0] and c[1] > c[2] and c[2] < 150:
        cls = 'G绿'
    elif c[0] > c[1] and c[0] > c[2]:
        cls = 'R红'
    else:
        cls = f'?{tuple(c)}'
    if cls != prev_cls:
        print(f'y={y} 深度≈{2849.1 - (y/114425/0.9737)*2514.2:.2f}m: {cls} 主色{tuple(c)} 占比{main[1]/392*100:.0f}%')
        prev_cls = cls
