#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pptx import Presentation
from pathlib import Path

ppt_path = Path(r'F:\360\Pythonwork\project\src\AI测井解释工作方法.pptx')
prs = Presentation(ppt_path)

out = open(r'F:\360\Pythonwork\project\src\debug_layout_after.txt', 'w', encoding='utf-8')

for idx in [0, 2, 5, 9, 10, 11, 12, 28, 29]:
    slide = prs.slides[idx]
    out.write(f'=== Slide {idx+1} ===\n')
    for s_i, shape in enumerate(slide.shapes):
        if not shape.has_text_frame:
            continue
        text = shape.text.strip()
        if not text:
            continue
        left = shape.left / 914400
        top = shape.top / 914400
        width = shape.width / 914400
        height = shape.height / 914400
        try:
            font_size = shape.text_frame.paragraphs[0].runs[0].font.size
            font_size_pt = font_size / 12700 if font_size else 'default'
        except:
            font_size_pt = 'unknown'
        out.write(f'Shape {s_i}: pos=({left:.2f},{top:.2f}) size={width:.2f}x{height:.2f}in font={font_size_pt}pt\n')
        out.write(f'  text[:80]: {text[:80]}\n')
    out.write('\n')

out.close()
print('Layout after saved')
