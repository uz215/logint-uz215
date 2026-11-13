#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重写幻灯片 8：传统方法的局限性
基于传统测井解释流程，从 6 个方面展开分析
"""

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Pt
from pathlib import Path


def set_text(shape, text):
    if shape.has_text_frame:
        shape.text_frame.text = text


def clear_text(shape):
    if shape.has_text_frame:
        shape.text_frame.text = ''
    if shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                cell.text = ''


def format_shape(shape, size_pt=14, line_spacing=1.25, bold=False):
    if not shape.has_text_frame:
        return
    tf = shape.text_frame
    tf.word_wrap = True
    for p in tf.paragraphs:
        p.line_spacing = line_spacing
        p.alignment = PP_ALIGN.LEFT
        for run in p.runs:
            run.font.name = 'Microsoft YaHei'
            run.font.size = Pt(size_pt)
            run.font.bold = bold


def main():
    src_dir = Path(r'F:\360\Pythonwork\project\src')
    ppt_path = src_dir / 'AI测井解释工作方法.pptx'
    prs = Presentation(ppt_path)
    slides = list(prs.slides)
    slide = slides[7]

    # 保留标题 shape 0，清空其他占位形状
    title = slide.shapes[0]
    for shape in slide.shapes:
        if shape is title:
            continue
        clear_text(shape)

    # 将完整内容写入 shape 2（最大的内容框）
    content = slide.shapes[2]
    new_text = (
        '【基于传统测井解释流程的六大局限性】\n\n'
        '1. 数据采集与准备阶段\n'
        '• 多源数据格式繁杂（LAS/DLIS/CSV/Excel），需手动导入与格式转换\n'
        '• 井信息、区域背景依赖人工录入，易出错且难以统一\n\n'
        '2. 数据预处理与质量控制\n'
        '• 环境校正、深度匹配依赖个人经验参数，缺乏统一标准\n'
        '• 人工逐点核对曲线质量，工作量大且易遗漏异常\n\n'
        '3. 解释建模与参数计算\n'
        '• 阿尔奇参数、骨架值、泥质含量计算依赖专家经验\n'
        '• 手工查表、重复计算多，参数选择主观性强\n\n'
        '4. 岩性识别与图版匹配\n'
        '• 岩性判断与流体识别多凭经验，不同人员结果差异大\n'
        '• 解释图版分散存储，缺乏系统化管理和动态更新\n\n'
        '5. 综合评价与流程协同\n'
        '• 流程环节多、涉及岗位多，沟通成本高、协同效率低\n'
        '• 审核复核环节多，单井解释周期长达 3 天以上\n\n'
        '6. 成果输出与知识沉淀\n'
        '• 报告撰写、排版、入库以手工为主，效率低下\n'
        '• 解释经验、图版、参数分散在个人手中，难以传承与复用'
    )
    set_text(content, new_text)
    format_shape(content, size_pt=13, line_spacing=1.2)

    # 格式化标题
    title_tf = title.text_frame
    title_tf.word_wrap = True
    for p in title_tf.paragraphs:
        p.alignment = PP_ALIGN.LEFT
        for run in p.runs:
            run.font.name = 'Microsoft YaHei'
            run.font.bold = True

    prs.save(ppt_path)
    print(f'幻灯片 8 更新完成: {ppt_path}')


if __name__ == '__main__':
    main()
