# =============================================================================
# AI测井解释工作方法PPT生成器
# 使用FLAIR解释.pptx母版文件生成PPT
# 增强版：添加丰富的视觉效果和样式
# =============================================================================

import os
import sys
from pathlib import Path
from datetime import datetime

try:
    from pptx import Presentation
    from pptx.util import Cm, Pt, Inches
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.dml.color import RGBColor
    from pptx.enum.dml import MSO_THEME_COLOR
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.util import Cm, Pt
    PPTX_AVAILABLE = True
except ImportError:
    print("提示: python-pptx未安装")
    PPTX_AVAILABLE = False


# ==================== 配色方案 ====================
COLORS = {
    'primary': RGBColor(0, 51, 102),      # 深蓝色 - 主色调
    'secondary': RGBColor(0, 153, 204),   # 亮蓝色 - 强调色
    'accent': RGBColor(0, 102, 153),      # 蓝绿色 - 辅助色
    'text': RGBColor(51, 51, 51),         # 深灰色 - 正文
    'light_text': RGBColor(102, 102, 102),# 灰色 - 次要文字
    'background': RGBColor(248, 249, 250),# 浅灰 - 背景
    'highlight': RGBColor(255, 204, 0),   # 金色 - 高亮
    'success': RGBColor(0, 153, 102),     # 绿色 - 成功
    'warning': RGBColor(255, 153, 0),     # 橙色 - 警告
}


def add_title_slide(prs, title, subtitle, presenter="", date=""):
    """创建封面幻灯片（增强版）"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(248, 249, 250)
    
    # 添加装饰背景图形
    # 顶部渐变条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(1.5))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['primary']
    top_bar.line.fill.background()
    
    # 底部渐变条
    bottom_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(24.5), Cm(28), Cm(1))
    bottom_bar.fill.solid()
    bottom_bar.fill.fore_color.rgb = COLORS['secondary']
    bottom_bar.line.fill.background()
    
    # 添加装饰圆形
    circle1 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Cm(22), Cm(18), Cm(5), Cm(5))
    circle1.fill.solid()
    circle1.fill.fore_color.rgb = RGBColor(0, 153, 204)
    circle1.fill.transparency = 0.15
    circle1.line.fill.background()
    
    circle2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Cm(24), Cm(20), Cm(3), Cm(3))
    circle2.fill.solid()
    circle2.fill.fore_color.rgb = RGBColor(0, 102, 153)
    circle2.fill.transparency = 0.2
    circle2.line.fill.background()
    
    # 设置标题区域
    title_box = slide.shapes.add_textbox(Cm(2), Cm(5), Cm(24), Cm(5))
    title_frame = title_box.text_frame
    title_frame.word_wrap = True
    title_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.2
    
    # 添加标题下划线装饰
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(7), Cm(9.8), Cm(14), Cm(0.2))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 设置副标题区域
    subtitle_box = slide.shapes.add_textbox(Cm(2), Cm(11), Cm(24), Cm(5))
    subtitle_frame = subtitle_box.text_frame
    subtitle_frame.word_wrap = True
    subtitle_frame.vertical_anchor = MSO_ANCHOR.TOP
    
    paragraphs = subtitle.split('\n')
    for idx, p_text in enumerate(paragraphs):
        if not p_text.strip():
            continue
        p = subtitle_frame.add_paragraph()
        p.text = p_text
        p.font.size = Pt(16)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['light_text']
        p.alignment = PP_ALIGN.CENTER
        if idx > 0:
            p.space_before = Pt(8)
    
    # 添加作者和日期信息
    if presenter or date:
        info_box = slide.shapes.add_textbox(Cm(2), Cm(19), Cm(24), Cm(4))
        info_frame = info_box.text_frame
        info_frame.word_wrap = True
        
        if presenter:
            p = info_frame.add_paragraph()
            p.text = f"汇报人：{presenter}"
            p.font.size = Pt(14)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.alignment = PP_ALIGN.CENTER
        
        if date:
            p = info_frame.add_paragraph()
            p.text = f"日期：{date}"
            p.font.size = Pt(14)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.alignment = PP_ALIGN.CENTER
    
    return slide


def add_section_divider(prs, section_number, section_title):
    """创建章节分隔页"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加左侧装饰条
    left_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(1.5), Cm(25.4))
    left_bar.fill.solid()
    left_bar.fill.fore_color.rgb = COLORS['primary']
    left_bar.line.fill.background()
    
    # 添加章节编号
    number_box = slide.shapes.add_textbox(Cm(3), Cm(8), Cm(8), Cm(6))
    number_frame = number_box.text_frame
    p = number_frame.add_paragraph()
    p.text = f"0{section_number}"
    p.font.size = Pt(72)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = RGBColor(200, 220, 240)
    p.alignment = PP_ALIGN.LEFT
    
    # 添加章节标题
    title_box = slide.shapes.add_textbox(Cm(3), Cm(11), Cm(22), Cm(6))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = section_title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.LEFT
    p.line_spacing = 1.3
    
    # 添加装饰线
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(3), Cm(14.5), Cm(8), Cm(0.15))
    line.fill.solid()
    line.fill.fore_color.rgb = COLORS['secondary']
    line.line.fill.background()
    
    return slide


def add_content_slide(prs, title, content_items, highlight_color=None):
    """创建内容幻灯片（优化版）"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题区域
    title_box = slide.shapes.add_textbox(Cm(2), Cm(0.8), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    title_frame.word_wrap = True
    title_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(9), Cm(3), Cm(6), Cm(0.15))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 设置内容区域
    content_box = slide.shapes.add_textbox(Cm(2), Cm(4), Cm(24), Cm(14))
    content_frame = content_box.text_frame
    content_frame.word_wrap = True
    content_frame.vertical_anchor = MSO_ANCHOR.TOP
    
    for idx, item in enumerate(content_items):
        if isinstance(item, dict):
            subtitle = item.get('subtitle', '')
            content = item.get('content', '')
            
            # 添加小标题
            if subtitle:
                p = content_frame.add_paragraph()
                p.text = subtitle
                p.font.size = Pt(15)
                p.font.bold = True
                p.font.name = '微软雅黑'
                p.font.color.rgb = COLORS['accent']
                p.space_before = Pt(12) if idx > 0 else Pt(5)
                p.alignment = PP_ALIGN.CENTER
            
            # 添加内容
            if content:
                content_lines = content.split('\n')
                non_empty_lines = [line for line in content_lines if line.strip()]
                
                if len(non_empty_lines) <= 4:
                    # 单行或少量行显示
                    for line in non_empty_lines:
                        p = content_frame.add_paragraph()
                        p.text = line
                        p.font.size = Pt(13)
                        p.font.name = '微软雅黑'
                        p.font.color = COLORS['text']
                        p.alignment = PP_ALIGN.CENTER
                        p.line_spacing = 1.3
                else:
                    # 分两列显示
                    half = (len(non_empty_lines) + 1) // 2
                    col1 = non_empty_lines[:half]
                    col2 = non_empty_lines[half:]
                    
                    # 左列
                    left_box = slide.shapes.add_textbox(Cm(3), Cm(5.5 + idx * 3), Cm(10), Cm(8))
                    left_frame = left_box.text_frame
                    for line in col1:
                        p = left_frame.add_paragraph()
                        p.text = line
                        p.font.size = Pt(12)
                        p.font.name = '微软雅黑'
                        p.font.color.rgb = COLORS['text']
                        p.line_spacing = 1.2
                    
                    # 右列
                    right_box = slide.shapes.add_textbox(Cm(15), Cm(5.5 + idx * 3), Cm(10), Cm(8))
                    right_frame = right_box.text_frame
                    for line in col2:
                        p = right_frame.add_paragraph()
                        p.text = line
                        p.font.size = Pt(12)
                        p.font.name = '微软雅黑'
                        p.font.color.rgb = COLORS['text']
                        p.line_spacing = 1.2
                    
        else:
            # 普通文本
            p = content_frame.add_paragraph()
            p.text = item
            p.font.size = Pt(13)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.line_spacing = 1.3
            p.alignment = PP_ALIGN.CENTER
            p.space_before = Pt(8)
    
    return slide


def add_diagram_slide(prs, title, diagram_type, data):
    """创建图表/图示幻灯片（增强版）"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(0.8), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(9), Cm(3), Cm(6), Cm(0.1))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 根据图表类型添加内容
    content_box = slide.shapes.add_textbox(Cm(2), Cm(4), Cm(24), Cm(14))
    content_frame = content_box.text_frame
    content_frame.word_wrap = True
    content_frame.vertical_anchor = MSO_ANCHOR.TOP
    
    if diagram_type == 'flow':
        # 流程图样式
        for i, step in enumerate(data):
            p = content_frame.add_paragraph()
            p.text = f"{'◆' if i == 0 else '◇'} {step}"
            p.font.size = Pt(14)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['accent'] if i == 0 else COLORS['text']
            p.space_before = Pt(10)
            p.alignment = PP_ALIGN.CENTER
            
            # 添加箭头指示
            if i < len(data) - 1:
                p = content_frame.add_paragraph()
                p.text = "    ↓"
                p.font.size = Pt(16)
                p.alignment = PP_ALIGN.CENTER
    
    elif diagram_type == 'table':
        # 表格样式
        for row in data:
            p = content_frame.add_paragraph()
            p.text = row
            p.font.size = Pt(13)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.space_before = Pt(5)
            p.alignment = PP_ALIGN.CENTER
    
    elif diagram_type == 'comparison':
        # 对比样式
        for item in data:
            label = item['label']
            before = item['before']
            after = item['after']
            
            p = content_frame.add_paragraph()
            p.text = f"【{label}】"
            p.font.size = Pt(15)
            p.font.bold = True
            p.font.color.rgb = COLORS['accent']
            p.space_before = Pt(12)
            p.alignment = PP_ALIGN.CENTER
            
            # 创建左右对比布局
            row_box = slide.shapes.add_textbox(Cm(3), Cm(5 + data.index(item) * 4), Cm(22), Cm(3))
            row_frame = row_box.text_frame
            
            p = row_frame.add_paragraph()
            p.text = f"传统方法: {before}"
            p.font.size = Pt(13)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['light_text']
            p.alignment = PP_ALIGN.LEFT
            
            p = row_frame.add_paragraph()
            p.text = f"新方法:   {after}"
            p.font.size = Pt(13)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['success']
            p.font.bold = True
            p.alignment = PP_ALIGN.RIGHT
    
    elif diagram_type == 'algorithm':
        # 算法流程图
        for i, step in enumerate(data):
            p = content_frame.add_paragraph()
            p.text = f"{i+1}. {step}"
            p.font.size = Pt(13)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.space_before = Pt(8)
            p.alignment = PP_ALIGN.LEFT
    
    return slide


def add_log_curve_slide(prs, title, curve_data):
    """创建测井曲线展示幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(0.8), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(9), Cm(3), Cm(6), Cm(0.1))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 创建测井曲线示意区域
    # 深度道
    depth_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0.5), Cm(4), Cm(3), Cm(14))
    depth_track.fill.solid()
    depth_track.fill.fore_color.rgb = RGBColor(240, 240, 240)
    depth_track.line.color.rgb = COLORS['primary']
    depth_track.line.width = Pt(1)
    
    # GR道
    gr_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(3.8), Cm(4), Cm(4), Cm(14))
    gr_track.fill.solid()
    gr_track.fill.fore_color.rgb = RGBColor(245, 245, 245)
    gr_track.line.color.rgb = COLORS['primary']
    gr_track.line.width = Pt(1)
    
    # DEN道
    den_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(8.1), Cm(4), Cm(4), Cm(14))
    den_track.fill.solid()
    den_track.fill.fore_color.rgb = RGBColor(245, 245, 245)
    den_track.line.color.rgb = COLORS['primary']
    den_track.line.width = Pt(1)
    
    # CNL道
    cnl_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(12.4), Cm(4), Cm(4), Cm(14))
    cnl_track.fill.solid()
    cnl_track.fill.fore_color.rgb = RGBColor(245, 245, 245)
    cnl_track.line.color.rgb = COLORS['primary']
    cnl_track.line.width = Pt(1)
    
    # RT道
    rt_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(16.7), Cm(4), Cm(4), Cm(14))
    rt_track.fill.solid()
    rt_track.fill.fore_color.rgb = RGBColor(245, 245, 245)
    rt_track.line.color.rgb = COLORS['primary']
    rt_track.line.width = Pt(1)
    
    # 岩性道
    litho_track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(21), Cm(4), Cm(6), Cm(14))
    litho_track.fill.solid()
    litho_track.fill.fore_color.rgb = RGBColor(245, 245, 245)
    litho_track.line.color.rgb = COLORS['primary']
    litho_track.line.width = Pt(1)
    
    # 添加道名称
    track_names = ['深度(m)', 'GR(API)', 'DEN(g/cc)', 'CNL(%)', 'RT(Ω·m)', '岩性']
    positions = [1.5, 5.8, 10.1, 14.4, 18.7, 24]
    
    for i, name in enumerate(track_names):
        name_box = slide.shapes.add_textbox(Cm(positions[i]-1), Cm(3.5), Cm(2), Cm(1))
        name_frame = name_box.text_frame
        p = name_frame.add_paragraph()
        p.text = name
        p.font.size = Pt(10)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['primary']
        p.alignment = PP_ALIGN.CENTER
    
    # 添加深度刻度
    for i in range(5):
        depth = 1000 + i * 50
        y_pos = Cm(4 + i * 3.5)
        # 刻度线
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0.5), y_pos, Cm(3), Cm(0.05))
        line.fill.solid()
        line.fill.fore_color.rgb = COLORS['light_text']
        
        # 刻度数字
        num_box = slide.shapes.add_textbox(Cm(0.5), y_pos - Cm(0.4), Cm(3), Cm(0.8))
        num_frame = num_box.text_frame
        p = num_frame.add_paragraph()
        p.text = str(depth)
        p.font.size = Pt(9)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['text']
        p.alignment = PP_ALIGN.CENTER
    
    # 添加模拟曲线
    # GR曲线（红色）
    gr_points = [(0.2, 0.15), (0.35, 0.3), (0.25, 0.5), (0.6, 0.65), (0.4, 0.85)]
    for i in range(len(gr_points)-1):
        x1 = Cm(3.8 + gr_points[i][0] * 4)
        y1 = Cm(4 + gr_points[i][1] * 14)
        x2 = Cm(3.8 + gr_points[i+1][0] * 4)
        y2 = Cm(4 + gr_points[i+1][1] * 14)
        line = slide.shapes.add_shape(MSO_SHAPE.LINE, x1, y1, x2 - x1, y2 - y1)
        line.line.color.rgb = RGBColor(255, 102, 102)
        line.line.width = Pt(1.5)
    
    # DEN曲线（蓝色）
    den_points = [(0.7, 0.15), (0.65, 0.3), (0.72, 0.5), (0.68, 0.65), (0.7, 0.85)]
    for i in range(len(den_points)-1):
        x1 = Cm(8.1 + (1 - den_points[i][0]) * 4)
        y1 = Cm(4 + den_points[i][1] * 14)
        x2 = Cm(8.1 + (1 - den_points[i+1][0]) * 4)
        y2 = Cm(4 + den_points[i+1][1] * 14)
        line = slide.shapes.add_shape(MSO_SHAPE.LINE, x1, y1, x2 - x1, y2 - y1)
        line.line.color.rgb = RGBColor(0, 102, 204)
        line.line.width = Pt(1.5)
    
    # CNL曲线（绿色）
    cnl_points = [(0.3, 0.15), (0.35, 0.3), (0.28, 0.5), (0.45, 0.65), (0.35, 0.85)]
    for i in range(len(cnl_points)-1):
        x1 = Cm(12.4 + (1 - cnl_points[i][0]) * 4)
        y1 = Cm(4 + cnl_points[i][1] * 14)
        x2 = Cm(12.4 + (1 - cnl_points[i+1][0]) * 4)
        y2 = Cm(4 + cnl_points[i+1][1] * 14)
        line = slide.shapes.add_shape(MSO_SHAPE.LINE, x1, y1, x2 - x1, y2 - y1)
        line.line.color.rgb = RGBColor(0, 153, 102)
        line.line.width = Pt(1.5)
    
    # RT曲线（紫色）
    rt_points = [(0.15, 0.15), (0.12, 0.3), (0.08, 0.5), (0.18, 0.65), (0.25, 0.85)]
    for i in range(len(rt_points)-1):
        x1 = Cm(16.7 + rt_points[i][0] * 4)
        y1 = Cm(4 + rt_points[i][1] * 14)
        x2 = Cm(16.7 + rt_points[i+1][0] * 4)
        y2 = Cm(4 + rt_points[i+1][1] * 14)
        line = slide.shapes.add_shape(MSO_SHAPE.LINE, x1, y1, x2 - x1, y2 - y1)
        line.line.color.rgb = RGBColor(153, 102, 204)
        line.line.width = Pt(1.5)
    
    # 添加岩性图例
    legend_box = slide.shapes.add_textbox(Cm(22), Cm(3.5), Cm(4), Cm(3))
    legend_frame = legend_box.text_frame
    
    # 砂岩图例
    sand_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(22.2), Cm(4.2), Cm(1.5), Cm(0.5))
    sand_rect.fill.solid()
    sand_rect.fill.fore_color.rgb = RGBColor(255, 204, 153)
    sand_rect.line.fill.background()
    
    p = legend_frame.add_paragraph()
    p.text = "  砂岩"
    p.font.size = Pt(9)
    p.font.name = '微软雅黑'
    
    # 泥岩图例
    shale_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(22.2), Cm(5), Cm(1.5), Cm(0.5))
    shale_rect.fill.solid()
    shale_rect.fill.fore_color.rgb = RGBColor(153, 102, 51)
    shale_rect.line.fill.background()
    
    p = legend_frame.add_paragraph()
    p.text = "  泥岩"
    p.font.size = Pt(9)
    p.font.name = '微软雅黑'
    
    # 油层图例
    oil_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(22.2), Cm(5.8), Cm(1.5), Cm(0.5))
    oil_rect.fill.solid()
    oil_rect.fill.fore_color.rgb = RGBColor(255, 102, 0)
    oil_rect.line.fill.background()
    
    p = legend_frame.add_paragraph()
    p.text = "  油层"
    p.font.size = Pt(9)
    p.font.name = '微软雅黑'
    
    return slide


def add_table_slide(prs, title, headers, rows):
    """创建表格幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(0.8), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(9), Cm(3), Cm(6), Cm(0.1))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 创建表格
    num_rows = len(rows) + 1
    num_cols = len(headers)
    
    left = Cm(2)
    top = Cm(4)
    width = Cm(24)
    height = Cm(14)
    
    table = slide.shapes.add_table(num_rows, num_cols, left, top, width, height).table
    
    # 设置表头
    for i, header in enumerate(headers):
        cell = table.cell(0, i)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLORS['primary']
        
        p = cell.text_frame.add_paragraph()
        p.text = header
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.name = '微软雅黑'
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER
        p.vertical_anchor = MSO_ANCHOR.MIDDLE
    
    # 设置表格内容
    for row_idx, row in enumerate(rows):
        for col_idx, cell_content in enumerate(row):
            cell = table.cell(row_idx + 1, col_idx)
            
            # 交替行背景色
            if row_idx % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(248, 250, 252)
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(255, 255, 255)
            
            p = cell.text_frame.add_paragraph()
            p.text = str(cell_content)
            p.font.size = Pt(11)
            p.font.name = '微软雅黑'
            p.font.color.rgb = COLORS['text']
            p.alignment = PP_ALIGN.CENTER
            p.vertical_anchor = MSO_ANCHOR.MIDDLE
    
    # 设置表格边框
    for row in range(num_rows):
        for col in range(num_cols):
            cell = table.cell(row, col)
            cell.left_edge.color.rgb = RGBColor(200, 200, 200)
            cell.right_edge.color.rgb = RGBColor(200, 200, 200)
            cell.top_edge.color.rgb = RGBColor(200, 200, 200)
            cell.bottom_edge.color.rgb = RGBColor(200, 200, 200)
    
    return slide


def add_conclusion_slide(prs, title, key_points, highlights=None):
    """创建总结/结论幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(248, 249, 250)
    
    # 添加装饰背景
    bottom_decor = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(20), Cm(28), Cm(5.4))
    bottom_decor.fill.solid()
    bottom_decor.fill.fore_color.rgb = COLORS['primary']
    bottom_decor.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(24), Cm(3))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(9), Cm(3.5), Cm(6), Cm(0.15))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 添加主要要点
    content_box = slide.shapes.add_textbox(Cm(3), Cm(5), Cm(22), Cm(12))
    content_frame = content_box.text_frame
    content_frame.word_wrap = True
    
    for i, point in enumerate(key_points):
        p = content_frame.add_paragraph()
        p.text = f"◆ {point}"
        p.font.size = Pt(15)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['text']
        p.space_before = Pt(10)
        p.line_spacing = 1.4
    
    # 添加亮点/关键数据
    if highlights:
        highlight_box = slide.shapes.add_textbox(Cm(2), Cm(21), Cm(24), Cm(3))
        highlight_frame = highlight_box.text_frame
        
        highlight_text = " | ".join([f"{k}: {v}" for k, v in highlights.items()])
        p = highlight_frame.add_paragraph()
        p.text = highlight_text
        p.font.size = Pt(14)
        p.font.name = '微软雅黑'
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER
    
    return slide


def add_references_slide(prs):
    """创建参考文献幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = "参考文献"
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(10), Cm(3), Cm(4), Cm(0.1))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 添加参考文献列表
    refs = [
        "[1] 王贵文, 吴胜和. 测井地质学[M]. 北京: 石油工业出版社, 2015.",
        "[2] 熊琦华, 李舟波. 测井资料综合解释[M]. 北京: 石油大学出版社, 2001.",
        "[3] Archie G E. The Electrical Resistivity Log as an Aid in Determining Some Reservoir Characteristics[J]. Transactions of the AIME, 1942, 146(1): 54-62.",
        "[4] 中国石油天然气集团公司. 测井资料解释规范[M]. 北京: 石油工业出版社, 2019.",
        "[5] 赵培华. 复杂储层测井评价技术[M]. 北京: 科学出版社, 2018."
    ]
    
    content_box = slide.shapes.add_textbox(Cm(3), Cm(4), Cm(22), Cm(14))
    content_frame = content_box.text_frame
    
    for ref in refs:
        p = content_frame.add_paragraph()
        p.text = ref
        p.font.size = Pt(11)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['text']
        p.space_before = Pt(8)
        p.line_spacing = 1.3
    
    return slide


def add_appendix_slide(prs):
    """创建附录幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLORS['background']
    
    # 添加顶部装饰条
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(0.3))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = COLORS['secondary']
    top_bar.line.fill.background()
    
    # 设置标题
    title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(24), Cm(2.5))
    title_frame = title_box.text_frame
    p = title_frame.add_paragraph()
    p.text = "附录：常用测井曲线符号说明"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    
    # 添加标题下划线
    title_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(7), Cm(3), Cm(8), Cm(0.1))
    title_line.fill.solid()
    title_line.fill.fore_color.rgb = COLORS['secondary']
    title_line.line.fill.background()
    
    # 添加曲线符号说明
    curve_info = [
        ("GR", "自然伽马", "API", "识别泥质含量"),
        ("DEN/RHOB", "密度", "g/cm³", "计算孔隙度"),
        ("NPHI/CNL", "中子孔隙度", "%", "计算孔隙度"),
        ("AC/DT", "声波时差", "μs/ft", "计算孔隙度"),
        ("RT/LLD", "深电阻率", "Ω·m", "判断流体性质"),
        ("RXO/LLS", "浅电阻率", "Ω·m", "判断冲洗带"),
        ("SP", "自然电位", "mV", "识别渗透层"),
        ("PE", "光电吸收截面", "b/e", "识别岩性"),
        ("CAL", "井径", "in", "井眼扩大校正"),
        ("VSH", "泥质含量", "%", "泥质含量指示"),
        ("POR/PHI", "孔隙度", "%", "储层物性"),
        ("SW", "含水饱和度", "%", "含油性指示")
    ]
    
    # 创建两列布局
    left_box = slide.shapes.add_textbox(Cm(3), Cm(4), Cm(10), Cm(14))
    left_frame = left_box.text_frame
    
    right_box = slide.shapes.add_textbox(Cm(15), Cm(4), Cm(10), Cm(14))
    right_frame = right_box.text_frame
    
    for i, (symbol, name, unit, desc) in enumerate(curve_info):
        if i % 2 == 0:
            frame = left_frame
        else:
            frame = right_frame
        
        p = frame.add_paragraph()
        p.text = f"【{symbol}】{name}"
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['accent']
        
        p = frame.add_paragraph()
        p.text = f"    单位: {unit} | {desc}"
        p.font.size = Pt(11)
        p.font.name = '微软雅黑'
        p.font.color.rgb = COLORS['text']
        p.space_before = Pt(2)
    
    return slide


def add_thank_you_slide(prs):
    """创建致谢幻灯片"""
    slide_layout = prs.slide_layouts[2]
    slide = prs.slides.add_slide(slide_layout)
    
    # 设置背景
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(248, 249, 250)
    
    # 添加装饰背景
    top_decor = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(0), Cm(28), Cm(2))
    top_decor.fill.solid()
    top_decor.fill.fore_color.rgb = COLORS['primary']
    top_decor.line.fill.background()
    
    bottom_decor = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(0), Cm(23.4), Cm(28), Cm(2))
    bottom_decor.fill.solid()
    bottom_decor.fill.fore_color.rgb = COLORS['primary']
    bottom_decor.line.fill.background()
    
    # 添加装饰圆形
    circle1 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Cm(11), Cm(7), Cm(6), Cm(6))
    circle1.fill.solid()
    circle1.fill.fore_color.rgb = COLORS['secondary']
    circle1.fill.transparency = 0.1
    circle1.line.fill.background()
    
    circle2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Cm(12), Cm(8), Cm(4), Cm(4))
    circle2.fill.solid()
    circle2.fill.fore_color.rgb = COLORS['accent']
    circle2.fill.transparency = 0.15
    circle2.line.fill.background()
    
    # 添加感谢文字
    thank_box = slide.shapes.add_textbox(Cm(2), Cm(12), Cm(24), Cm(6))
    thank_frame = thank_box.text_frame
    thank_frame.word_wrap = True
    
    p = thank_frame.add_paragraph()
    p.text = "谢谢观看！"
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['primary']
    p.alignment = PP_ALIGN.CENTER
    p.space_before = Pt(20)
    
    p = thank_frame.add_paragraph()
    p.text = "敬请批评指正"
    p.font.size = Pt(18)
    p.font.name = '微软雅黑'
    p.font.color.rgb = COLORS['light_text']
    p.alignment = PP_ALIGN.CENTER
    p.space_before = Pt(10)
    
    return slide


def generate_ppt():
    """生成AI测井解释工作方法PPT（增强版）"""
    if not PPTX_AVAILABLE:
        print("错误: python-pptx未安装")
        return None
    
    master_path = Path("FLAIR解释.pptx")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not master_path.exists():
        print("错误: FLAIR解释.pptx 不存在")
        return None
    
    print("✓ 加载母版文件...")
    prs = Presentation(str(master_path))
    
    # 删除所有现有幻灯片（保留母版样式）
    print("✓ 删除现有幻灯片...")
    for i in range(len(prs.slides)-1, -1, -1):
        rId = prs.slides._sldIdLst[i].rId
        prs.part.drop_rel(rId)
        del prs.slides._sldIdLst[i]
    
    # 添加新幻灯片
    print("✓ 创建新幻灯片...")
    
    # 1. 封面
    add_title_slide(prs, "AI驱动的智能测井解释工作方法", 
                    "一种新型测井资料解释流程与技术方法\n基于知识库与图版匹配的智能解释体系",
                    presenter="测井解释研发团队",
                    date=datetime.now().strftime("%Y年%m月%d日"))
    print("  幻灯片 1: 封面")
    
    # 2. 目录
    add_content_slide(prs, "汇报提纲", [
        {"subtitle": "【一、传统方法的局限性】", "content": "问题分析 | 效率低下 | 流程冗长"},
        {"subtitle": "【二、新方法的核心思想】", "content": "数据驱动 + 知识驱动 双轮驱动"},
        {"subtitle": "【三、知识库设计与形成】", "content": "架构设计 | 知识类型 | 知识更新"},
        {"subtitle": "【四、图版方法详解】", "content": "图版类型 | 匹配算法 | 应用流程"},
        {"subtitle": "【五、测井曲线展示】", "content": "曲线类型 | 响应特征 | 综合图"},
        {"subtitle": "【六、应用案例分析】", "content": "砂岩储层 | 低阻油层 | 碳酸盐岩"},
        {"subtitle": "【七、方法优势与总结】", "content": "效率对比 | 准确性评估"}
    ])
    print("  幻灯片 2: 目录")
    
    # 3. 章节分隔页1
    add_section_divider(prs, 1, "传统方法的局限性")
    print("  幻灯片 3: 章节分隔页1")
    
    # 4. 传统方法的局限性
    add_content_slide(prs, "一、传统方法的局限性", [
        {"subtitle": "【依赖专家经验】", "content": "• 解释结果高度依赖人员经验水平\n• 主观性强，不同人员解释结果差异大\n• 专家知识难以传承和复用"},
        {"subtitle": "【流程冗长复杂】", "content": "• 流程环节多，涉及多个岗位\n• 需要多人协同配合，沟通成本高\n• 审核复核环节多，等待时间长"},
        {"subtitle": "【效率低下】", "content": "• 数据加载：手动导入LAS/DLIS\n• 软件操作：手工操作，步骤繁琐\n• 质量检查：人工逐点核对\n• 参数计算：手工查表计算"}
    ])
    print("  幻灯片 4: 传统方法的局限性")
    
    # 5. 传统方法的局限性（续）
    add_content_slide(prs, "一、传统方法的局限性（续）", [
        {"subtitle": "【时间分配分析】", "content": "• 数据处理与解释：1天\n• 审核与校对：1天\n• 复核与入库：1天\n• 单井周期：至少3天"},
        {"subtitle": "【知识碎片化】", "content": "• 解释图版、经验参数分散存储\n• 缺乏系统性知识管理体系\n• 难以实现知识复用和共享"}
    ])
    print("  幻灯片 5: 传统方法的局限性（续）")
    
    # 6. 章节分隔页2
    add_section_divider(prs, 2, "新方法的核心思想")
    print("  幻灯片 6: 章节分隔页2")
    
    # 7. 新方法的核心思想
    add_diagram_slide(prs, "二、新方法的核心思想", 'flow', [
        "数据采集 → 质量控制 → 环境校正",
        "参数计算 → 图版匹配 → 智能解释",
        "知识库支撑 → 知识推理 → 成果输出"
    ])
    print("  幻灯片 7: 新方法的核心思想")
    
    # 8. 章节分隔页3
    add_section_divider(prs, 3, "知识库设计与形成")
    print("  幻灯片 8: 章节分隔页3")
    
    # 9. 知识库设计与形成
    add_content_slide(prs, "三、知识库设计与形成", [
        {"subtitle": "【知识库架构】", "content": "┌─────────────────────────────────┐\n│       测井解释知识库            │\n├─────────────┬───────────────────┤\n│ 资料知识   │ 区域/油田/构造/井  │\n├─────────────┼───────────────────┤\n│ 公式知识   │ 公式参数选择       │\n├─────────────┼───────────────────┤\n│ 地质知识   │ 测井-地质对应关系  │\n├─────────────┼───────────────────┤\n│ 方案知识   │ 综合解决方案       │\n├─────────────┼───────────────────┤\n│ 试油知识   │ 试油数据与结论     │\n└─────────────┴───────────────────┘"},
        {"subtitle": "【资料知识】", "content": "• 区域/油田/构造/井的基础信息\n• 采集的资料类型与资料特征\n• 地区特定储层的测井采集方案"}
    ])
    print("  幻灯片 9: 知识库设计与形成")
    
    # 10. 知识库设计与形成（续）
    add_content_slide(prs, "三、知识库设计与形成（续）", [
        {"subtitle": "【公式知识】", "content": "• 测井计算公式库\n• 区域/油田参数选择知识\n• 公式适用条件与范围"},
        {"subtitle": "【测井地质知识】", "content": "• 地质现象的测井响应特征\n• 测井特征代表的地质含义\n• 岩性-测井曲线对应关系"},
        {"subtitle": "【解决方案知识】", "content": "• 地质问题综合解决方法\n• 工程问题解决方案\n• 具体实施步骤与做法"}
    ])
    print("  幻灯片 10: 知识库设计与形成（续）")
    
    # 11. 知识更新机制
    add_content_slide(prs, "三、知识库设计与形成（续二）", [
        {"subtitle": "【试油知识】", "content": "• 试油方法与试油结论\n• 地区/井/井段试油数据\n• 试油-测井对应关系"},
        {"subtitle": "【知识更新机制】", "content": "• 网络知识自动搜集\n• 本地知识库增量更新\n• 知识质量评估与验证"},
        {"subtitle": "【知识推理流程】", "content": "输入数据 → 知识匹配 → 推理决策 → 结果输出"}
    ])
    print("  幻灯片 11: 知识更新机制")
    
    # 12. 章节分隔页4
    add_section_divider(prs, 4, "图版方法详解")
    print("  幻灯片 12: 章节分隔页4")
    
    # 13. 图版方法详解
    add_content_slide(prs, "四、图版方法详解", [
        {"subtitle": "【图版类型】", "content": "• 交会图版：DEN-CNL、GR-PE等\n• 解释模板：油层、气层、水层模板\n• 标准曲线：典型储层特征曲线"},
        {"subtitle": "【图版构建流程】", "content": "岩心数据标定 → 统计分析拟合 → 专家验证确认"},
        {"subtitle": "【图版匹配算法】", "content": "• 欧几里得距离度量\n• 动态时间规整(DTW)\n• 加权相似度评分"}
    ])
    print("  幻灯片 13: 图版方法详解")
    
    # 14. 算法流程
    add_diagram_slide(prs, "四、图版匹配算法流程", 'algorithm', [
        "输入测井曲线数据（GR, DEN, CNL, RT等）",
        "数据预处理：质量检查、环境校正",
        "提取特征：计算VSH, PHI, SW等参数",
        "构建特征向量：[VSH, PHI, SW, RT, GR]",
        "与知识库中图版模板进行相似度匹配",
        "计算欧几里得距离：d = Σ(xi - yi)²",
        "选择最小距离对应的解释类型",
        "输出解释结论（油层/气层/水层/干层）"
    ])
    print("  幻灯片 14: 算法流程")
    
    # 15. 章节分隔页5
    add_section_divider(prs, 5, "测井曲线展示")
    print("  幻灯片 15: 章节分隔页5")
    
    # 16. 测井曲线综合图
    add_log_curve_slide(prs, "五、测井曲线综合图展示", {})
    print("  幻灯片 16: 测井曲线综合图")
    
    # 17. 曲线特征分析
    add_content_slide(prs, "五、测井曲线特征分析", [
        {"subtitle": "【自然伽马(GR)】", "content": "• 泥岩：高值（>100API）\n• 砂岩：低值（<50API）\n• 用于识别泥质含量"},
        {"subtitle": "【密度(DEN)】", "content": "• 砂岩：~2.65g/cm³\n• 泥岩：~2.55g/cm³\n• 孔隙度增加，密度降低"},
        {"subtitle": "【中子(CNL)】", "content": "• 砂岩：低值（~-2%）\n• 泥岩：高值（~35%）\n• 对含氢物质敏感"}
    ])
    print("  幻灯片 17: 曲线特征分析")
    
    # 18. 章节分隔页6
    add_section_divider(prs, 6, "应用案例分析")
    print("  幻灯片 18: 章节分隔页6")
    
    # 19. 应用案例分析（一）
    add_content_slide(prs, "六、应用案例分析（一）", [
        {"subtitle": "【案例1：复杂砂岩储层解释】", "content": "井位：X油田K16井 | 深度：1200-2350m\n曲线：GR, DEN, CNL, AC, RT"},
        {"subtitle": "【处理流程】", "content": "1. 数据加载：LAS格式，9条曲线\n2. 质量控制：缺失值补全，异常值标记\n3. 环境校正：井眼扩大校正\n4. 参数计算：Vsh=15%, φ=22%, Sw=35%\n5. 图版匹配：DEN-CNL交会图匹配油层模板"},
        {"subtitle": "【验证结果】", "content": "解释结论：油层12层，气层3层\n与试油结果符合率：85%"}
    ])
    print("  幻灯片 19: 应用案例分析（一）")
    
    # 20. 应用案例分析（二）
    add_content_slide(prs, "六、应用案例分析（二）", [
        {"subtitle": "【案例2：低阻油层识别】", "content": "井位：Agadem区块A12井\n挑战：泥质含量高(25-35%)，电阻率低(10-20Ω·m)"},
        {"subtitle": "【传统方法难点】", "content": "• 电阻率低易误判为水层\n• 泥质影响难以准确计算"},
        {"subtitle": "【新方法处理】", "content": "• 多矿物模型精细计算\n• 泥质校正后的饱和度计算\n• 低阻油层图版匹配\n• 知识推理综合判断"},
        {"subtitle": "【成果】", "content": "成功识别低阻油层6层，符合率80%"}
    ])
    print("  幻灯片 20: 应用案例分析（二）")
    
    # 21. 应用案例分析（三）
    add_content_slide(prs, "六、应用案例分析（三）", [
        {"subtitle": "【案例3：碳酸盐岩储层评价】", "content": "井位：阿姆河区块B8井\n挑战：裂缝发育，非均质性强"},
        {"subtitle": "【处理流程】", "content": "1. 成像测井裂缝识别\n2. 密度-中子交会分析\n3. 裂缝孔隙度计算\n4. 知识图谱推理"},
        {"subtitle": "【成果】", "content": "裂缝识别符合率：90%\n储层评价精度：88%"}
    ])
    print("  幻灯片 21: 应用案例分析（三）")
    
    # 22. 应用案例分析（四）- 非常规油气
    add_content_slide(prs, "六、应用案例分析（四）", [
        {"subtitle": "【案例4：页岩气储层评价】", "content": "井位：四川盆地Y1井\n目标层位：龙马溪组"},
        {"subtitle": "【关键参数】", "content": "• 总有机碳含量(TOC)\n• 脆性指数(BI)\n• 孔隙度与渗透率\n• 含气量估算"},
        {"subtitle": "【AI分析结果】", "content": "识别优质页岩层段3层\n预测含气量：2.5-3.2 m³/t\n与实验室分析符合率：92%"}
    ])
    print("  幻灯片 22: 应用案例分析（四）")
    
    # 23. 章节分隔页7
    add_section_divider(prs, 7, "方法优势与总结")
    print("  幻灯片 23: 章节分隔页7")
    
    # 24. 方法优势对比
    add_diagram_slide(prs, "七、方法优势对比", 'comparison', [
        {"label": "效率提升", "before": "单井周期3天", "after": "单井周期4小时（提升18倍）"},
        {"label": "准确性", "before": "符合率70-80%", "after": "符合率85%以上"},
        {"label": "一致性", "before": "较差", "after": "高"},
        {"label": "知识传承", "before": "难以传承", "after": "可复用知识体系"}
    ])
    print("  幻灯片 24: 方法优势对比")
    
    # 25. 效果对比表格
    add_table_slide(prs, "七、方法效果对比表", 
                    ["对比指标", "传统方法", "AI智能方法", "提升幅度"],
                    [
                        ["单井解释周期", "3天", "4小时", "18倍"],
                        ["解释符合率", "75%", "85%", "+10%"],
                        ["知识复用率", "30%", "90%", "+60%"],
                        ["人工干预次数", "频繁", "少量", "-80%"],
                        ["报告生成时间", "2小时", "10分钟", "12倍"]
                    ])
    print("  幻灯片 25: 效果对比表格")
    
    # 26. 总结
    add_conclusion_slide(prs, "七、总结", 
        [
            "基于知识库与图版匹配的智能解释方法是测井解释领域的创新突破",
            "核心技术包括：知识库设计、知识推理、图版匹配算法",
            "应用案例验证了方法的有效性和可靠性",
            "显著提升了解释效率和准确性，具有广泛应用前景"
        ],
        highlights={
            "效率提升": "18倍",
            "符合率": "85%+",
            "知识复用率": "90%",
            "单井周期": "4小时"
        })
    print("  幻灯片 26: 总结")
    
    # 27. 未来展望
    add_content_slide(prs, "七、未来展望", [
        {"subtitle": "【下一步工作】", "content": "• 深化AI模型应用（深度学习）\n• 扩展多井对比分析功能\n• 构建智能决策支持系统"},
        {"subtitle": "【技术发展方向】", "content": "• 引入大语言模型增强知识推理\n• 开发实时测井解释系统\n• 构建跨油田知识共享平台"},
        {"subtitle": "【应用拓展】", "content": "• 非常规油气资源评价\n• 智能完井方案优化\n• 储层动态监测分析"}
    ])
    print("  幻灯片 27: 未来展望")
    
    # 28. 附录
    add_appendix_slide(prs)
    print("  幻灯片 28: 附录")
    
    # 29. 参考文献
    add_references_slide(prs)
    print("  幻灯片 29: 参考文献")
    
    # 30. 致谢
    add_thank_you_slide(prs)
    print("  幻灯片 30: 致谢")
    
    # 保存文件
    output_path = output_dir / f"AI测井解释工作方法_增强版_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
    prs.save(output_path)
    
    print(f"\n✓ PPT生成成功: {output_path}")
    return str(output_path)


if __name__ == "__main__":
    print("="*60)
    print("  AI测井解释工作方法PPT生成器（增强版）")
    print("  使用FLAIR解释.pptx母版")
    print("="*60)
    print()
    
    generate_ppt()