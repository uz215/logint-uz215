# -*- coding: utf-8 -*-
"""扫描最新大图，确认1102.5-1103.1m薄泥岩层在profile道是否可见"""
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

img_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_173401.png'
img = Image.open(img_path).convert('RGB')
w, h = img.size
print(f'Image size: {w}x{h}')

arr = np.array(img)

# PROFILE道像素范围: Axes[8] x0=0.7368 x1=0.8184
X0 = int(w * 0.7368)
X1 = int(w * 0.8184)
print(f'PROFILE道 x: {X0}-{X1}')

# y -> md: md = 330 + y * 2520 / 111416
# md -> y: y = (md - 330) * 111416 / 2520
K = 111416 / 2520.0

def md_to_y(md):
    return int((md - 330.0) * K)

def scan_range(md_lo, md_hi, label):
    y_lo = md_to_y(md_lo)
    y_hi = md_to_y(md_hi)
    y_lo, y_hi = sorted([y_lo, y_hi])
    region = arr[y_lo:y_hi, X0:X1]
    total = region.shape[0] * region.shape[1]
    # 绿色 #228B22 = (34,139,34)
    green = np.sum((np.abs(region[:, :, 0].astype(int) - 34) < 30) &
                   (np.abs(region[:, :, 1].astype(int) - 139) < 30) &
                   (np.abs(region[:, :, 2].astype(int) - 34) < 30))
    yellow = np.sum((np.abs(region[:, :, 0].astype(int) - 255) < 20) &
                    (np.abs(region[:, :, 1].astype(int) - 255) < 20) &
                    (region[:, :, 2].astype(int) < 40))
    white = np.sum((region[:, :, 0] > 240) & (region[:, :, 1] > 240) & (region[:, :, 2] > 240))
    black = np.sum(region.max(axis=2) < 100)
    print(f'{label} md[{md_lo}-{md_hi}] y[{y_lo}-{y_hi}] '
          f'绿={green/total*100:.2f}% 黄={yellow/total*100:.2f}% 白={white/total*100:.2f}% 黑={black/total*100:.2f}%')

# 已知泥岩段验证公式: 2700-2720m 应为绿色
scan_range(2700, 2720, '已知泥岩段2700-2720m')
# 薄泥岩层
scan_range(1100, 1102, '1100-1102m (上覆层)')
scan_range(1102, 1103, '1102-1103m (薄泥岩区)')
scan_range(1103, 1104, '1103-1104m (石英储层顶)')
scan_range(1104, 1108, '1104-1108m (石英储层)')

# 逐0.1m细扫1102.0-1104.0，找到绿色位置
print('\n逐0.1m扫描 (绿色占比):')
for md in np.arange(1102.0, 1104.0, 0.1):
    y_lo = md_to_y(md)
    y_hi = md_to_y(md + 0.1)
    region = arr[y_lo:y_hi, X0:X1]
    total = region.shape[0] * region.shape[1]
    green = np.sum((np.abs(region[:, :, 0].astype(int) - 34) < 30) &
                   (np.abs(region[:, :, 1].astype(int) - 139) < 30) &
                   (np.abs(region[:, :, 2].astype(int) - 34) < 30))
    yellow = np.sum((np.abs(region[:, :, 0].astype(int) - 255) < 20) &
                    (np.abs(region[:, :, 1].astype(int) - 255) < 20) &
                    (region[:, :, 2].astype(int) < 40))
    print(f'md {md:.1f}-{md+0.1:.1f}: 绿={green/total*100:.1f}% 黄={yellow/total*100:.1f}%')
