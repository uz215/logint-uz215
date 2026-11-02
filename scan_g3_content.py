# -*- coding: utf-8 -*-
"""检查g3(子集+全井段ylim)图中1080-1130m范围的实际渲染内容"""
import numpy as np
from PIL import Image
from collections import Counter

for name in ['g2_sub_local', 'g3_sub_full', 'g4_full_full']:
    img = Image.open(rf'f:\360\src\exp_{name}.png').convert('RGB')
    w2, h2 = img.size
    arr = np.array(img)
    X0r, X1r = int(w2*0.7368), int(w2*0.8184)
    # 扫描y全范围，找出非白像素分布（每隔200px采样一行）
    nonwhite_rows = []
    for y in range(0, h2, 100):
        row = arr[y, X0r:X1r]
        nw = np.sum(np.any(row < 250, axis=1))
        if nw > 5:
            nonwhite_rows.append(y)
    if nonwhite_rows:
        print(f'{name}: 非白行范围 y={nonwhite_rows[0]}-{nonwhite_rows[-1]} ({len(nonwhite_rows)}个采样)')
        # 子集数据1080-1130m在全井段ylim下应位于: (1080-330)/2520*0.9737*h2 到 (1130-330)/2520*0.9737*h2
        y1080 = int((1080-330)/2520*0.9737*h2)
        y1130 = int((1130-330)/2520*0.9737*h2)
        print(f'  理论范围: y={y1080}-{y1130}')
        # 检查1102.5-1103.1区域像素
        y_lo, y_hi = int((1102.5-330)/2520*0.9737*h2), int((1103.1-330)/2520*0.9737*h2)
        region = arr[y_lo:y_hi, X0r:X1r].reshape(-1, 3)
        cnt = Counter(map(tuple, region))
        total = len(region)
        g = sum(n for c, n in cnt.items() if abs(int(c[0])-47) < 25 and abs(int(c[1])-180) < 25 and abs(int(c[2])-114) < 25)
        yel = sum(n for c, n in cnt.items() if int(c[0]) > 235 and int(c[1]) > 235 and int(c[2]) < 40)
        white = sum(n for c, n in cnt.items() if int(c[0]) > 240 and int(c[1]) > 240 and int(c[2]) > 240)
        black = sum(n for c, n in cnt.items() if int(c[0]) < 60 and int(c[1]) < 60 and int(c[2]) < 60)
        print(f'  1102.5-1103.1m: 绿={g/total*100:.1f}% 黄={yel/total*100:.1f}% 白={white/total*100:.1f}% 黑={black/total*100:.1f}%')
        # 打印前10个非白采样行附近50px的颜色统计
        for y in nonwhite_rows[:2]:
            seg = arr[y-25:y+25, X0r:X1r].reshape(-1, 3)
            c2 = Counter(map(tuple, seg))
            total2 = len(seg)
            g2 = sum(n for c, n in c2.items() if abs(int(c[0])-47) < 25 and abs(int(c[1])-180) < 25 and abs(int(c[2])-114) < 25)
            y2 = sum(n for c, n in c2.items() if int(c[0]) > 235 and int(c[1]) > 235 and int(c[2]) < 40)
            print(f'  y={y}附近: 绿={g2/total2*100:.1f}% 黄={y2/total2*100:.1f}%')
    else:
        print(f'{name}: profile道全白!')
