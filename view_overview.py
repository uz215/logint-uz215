# -*- coding: utf-8 -*-
"""缩小大图查看整体布局"""
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_composite_log_20260814_164546.png').convert('RGB')
W, H = img.size
print(f'尺寸: {W}x{H}')

# 缩小到高度 2500
h = 2500
w = int(W * h / H)
small = img.resize((w, h), Image.LANCZOS)
small.save(r'f:\360\src\overview_small.png')
print(f'缩小后: {small.size}')
