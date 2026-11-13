# -*- coding: utf-8 -*-
"""扫描大图 y=68650 (约1340m) 行的完整像素，确认道内容"""
from PIL import Image
import numpy as np
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_170355.png').convert('RGB')
arr = np.array(img)
W, H = arr.shape[1], arr.shape[0]

y = 68650
print(f'扫描 y={y}')
row = arr[y, :, :].astype(int)

# 分段显示 x=2700-4400 的颜色
print('=== x=2700-4400 每20px ===')
prev = None
for x in range(2700, 4400, 20):
    px = row[x]
    print(f'  x={x}: {px}')

# 找黄色/绿色的x范围（精确）
print('\n=== 精确边界 ===')
def find_runs(cond, x0, x1):
    runs = []
    in_run = False
    for x in range(x0, x1):
        c = cond(row[x])
        if c and not in_run:
            start = x
            in_run = True
        elif not c and in_run:
            runs.append((start, x-1))
            in_run = False
    if in_run:
        runs.append((start, x1-1))
    return runs

yellow = find_runs(lambda p: abs(p[0]-255) < 20 and abs(p[1]-255) < 20 and p[2] < 60, 2700, 4400)
green = find_runs(lambda p: abs(p[0]-47) < 35 and abs(p[1]-180) < 35 and abs(p[2]-114) < 35, 2700, 4400)
dark = find_runs(lambda p: p[0] < 60 and p[1] < 60 and p[2] < 60, 2700, 4400)
white = find_runs(lambda p: p[0] > 240 and p[1] > 240 and p[2] > 240, 2700, 4400)
print(f'黄色段: {yellow}')
print(f'绿色段: {green}')
print(f'深色段: {dark}')
print(f'白色段: {white}')

# 看道边界竖线附近的颜色
for bx in [2753, 3144, 3536, 3927, 4319]:
    print(f'x={bx}: {row[bx]}, x={bx+5}: {row[bx+5]}, x={bx-5}: {row[bx-5]}')
