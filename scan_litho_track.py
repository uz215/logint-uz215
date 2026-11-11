# -*- coding: utf-8 -*-
"""扫描大图岩性道 1103-1373m 的显示效果"""
from PIL import Image
import numpy as np
from collections import Counter

Image.MAX_IMAGE_PIXELS = None
img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_170824.png').convert('RGB')
W, H = img.size
arr = np.array(img)
curve_px = int(H * 0.9737)

def md_to_y(md):
    return int((md - 330) * curve_px / 2520)

# 岩性道 x: 0.5737-0.6553
x0, x1 = int(0.5737 * W), int(0.6553 * W)
print(f"岩性道 x: {x0}-{x1}")

y0, y1 = md_to_y(1103), md_to_y(1373)
cnt = Counter()
for y in range(y0, y1, 2):
    for x in range(x0, x1):
        cnt[tuple(arr[y, x])] += 1
total = sum(cnt.values())
print(f"\n=== 岩性道 1103-1373m 颜色统计 ===")
for c, n in cnt.most_common(8):
    print(f"  {c}: {n} ({100*n/total:.1f}%)")

# 黑色像素分布（圆点或方块）
black = (arr[:, :, 0] < 60) & (arr[:, :, 1] < 60) & (arr[:, :, 2] < 60)
print(f"\n黑色像素总数: {black[y0:y1, x0:x1].sum()}")

# 在特定深度行查看黑色像素的 x 分布（判断是点还是方块/纹理）
print("\n采样行黑色像素 x 范围:")
for md in [1105, 1150, 1200, 1250, 1300, 1350]:
    y = md_to_y(md)
    xs = np.where(black[y, x0:x1])[0]
    if len(xs):
        # 分组连续段
        groups = []
        start = xs[0]
        prev = xs[0]
        for v in xs[1:]:
            if v - prev > 2:
                groups.append((start, prev))
                start = v
            prev = v
        groups.append((start, prev))
        print(f"  md={md}: {len(groups)} 组黑段 → {[(g0+x0, g1+x0) for g0, g1 in groups[:8]]}")
    else:
        print(f"  md={md}: 无黑色")

# 裁一小块 1290-1310m 岩性道看看（保存局部图）
crop = arr[md_to_y(1290):md_to_y(1310), x0:x1]
img_crop = Image.fromarray(crop)
img_crop = img_crop.resize((x1 - x0, 400))
img_crop.save(r'f:\360\src\diag_litho_track_crop.png')
print("\n已保存 diag_litho_track_crop.png")
