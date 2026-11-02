# -*- coding: utf-8 -*-
"""缩小裁剪图以便查看"""
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

img = Image.open(r'f:\360\src\crop_1100_1400.png')
print(f'原始尺寸: {img.size}')
# 缩小到高度 ~2000
h = 2000
w = int(img.width * h / img.height)
small = img.resize((w, h), Image.LANCZOS)
small.save(r'f:\360\src\crop_1100_1400_small.png')
print(f'缩小后: {small.size}')
