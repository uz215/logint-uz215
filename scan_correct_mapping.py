# -*- coding: utf-8 -*-
"""用正确映射(330-2850)扫描大图profile道"""
from PIL import Image
import numpy as np
Image.MAX_IMAGE_PIXELS = None

path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_170824.png'
img = Image.open(path).convert('RGB')
arr = np.array(img)
W, H = arr.shape[1], arr.shape[0]

# 深度轴: 330-2850, axes高 0.9737*H
DEPTH_TOP, DEPTH_BOT = 2850.0, 330.0
AXES_H = int(0.9737 * H)
px_per_m = AXES_H / (DEPTH_TOP - DEPTH_BOT)

def md_to_y(md):
    return int((DEPTH_TOP - md) * px_per_m)

# profile道 x范围
x0, x1 = 3536, 3928
mid = (x0 + x1) // 2

# 已知段：
# 1103.46-1373.53 黄色砂岩段
# 1374.03-1374.54 绿色Clay段
y_1374 = md_to_y(1374.0)
y_1103 = md_to_y(1103.0)
y_1300 = md_to_y(1300.0)
print(f'y_1103={y_1103}, y_1300={y_1300}, y_1374={y_1374}')

# 1. Clay段 (1374.03-1374.54)
print('\n=== Clay段 (1374.03-1374.54) y=65200-65260 ===')
for y in range(md_to_y(1374.54), md_to_y(1374.03), 5):
    px = arr[y, mid, :]
    print(f'  y={y}: {px}')

# 2. 黄色砂岩段边界 (1103.46, 1373.53)
print('\n=== 砂岩段边界附近 (y=65240-65300, y=77180-77240) ===')
for y in range(65240, 65300, 10):
    px = arr[y, mid, :]
    print(f'  y={y}: {px}')
for y in range(77180, 77240, 10):
    px = arr[y, mid, :]
    print(f'  y={y}: {px}')

# 3. 1300m附近
print('\n=== 1300m附近 (y=68490-68590) ===')
for y in range(68490, 68590, 10):
    px = arr[y, mid, :]
    print(f'  y={y}: {px}')

# 4. 统计 1103-1373m (y=65259-77217) 每500行的主色
print('\n=== 1103-1373m 每500行主色 ===')
y0, y1 = md_to_y(1373.53), md_to_y(1103.46)
for b0 in range(y0, y1, 500):
    b1 = min(b0 + 500, y1)
    block = arr[b0:b1, x0:x1, :].reshape(-1, 3).astype(int)
    green = ((abs(block[:,0]-47)<35)&(abs(block[:,1]-180)<35)&(abs(block[:,2]-114)<35)).mean()
    yellow = ((abs(block[:,0]-255)<20)&(abs(block[:,1]-255)<20)&(block[:,2]<60)).mean()
    white = ((block[:,0]>240)&(block[:,1]>240)&(block[:,2]>240)).mean()
    md = 2850 - (b0 + b1)/2 * (DEPTH_TOP-DEPTH_BOT)/AXES_H
    print(f'  md~{md:.0f}m y={b0}-{b1}: 绿={green:.0%} 黄={yellow:.0%} 白={white:.0%}')
