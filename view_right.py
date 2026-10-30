# -*- coding: utf-8 -*-
"""裁剪大图右侧 0.55-1.0 区域（最后几道）查看道布局"""
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_164546.png').convert('RGB')
W, H = img.size

# 裁剪右侧 0.55-1.0（含最后4-5道）以及深度 1300-1420m（y=65950-69950 附近）
y_top = int((2849.1 - 1420) / 2514.2 * 114425)  # 1420m
y_bot = int((2849.1 - 1280) / 2514.2 * 114425)   # 1280m
crop = img.crop((int(W*0.55), y_top, W, y_bot))
print(f'裁剪: {crop.size}')
# 缩小到高度 1600
h = 1600
w = int(crop.width * h / crop.height)
small = crop.resize((w, h), Image.LANCZOS)
small.save(r'f:\360\src\right_tracks.png')
print(f'保存: {small.size}')
