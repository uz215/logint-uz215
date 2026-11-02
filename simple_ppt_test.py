# -*- coding: utf-8 -*-
from pptx import Presentation
from pathlib import Path
from datetime import datetime

# 母版文件路径
master_file = "FLAIR解释.pptx"
output_file = f"output/AI测井解释_母版测试_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"

print(f"检查母版文件: {master_file}")
if Path(master_file).exists():
    print("母版文件存在，正在加载...")
    prs = Presentation(master_file)
    print(f"成功加载母版，布局数量: {len(prs.slide_layouts)}")
    
    # 添加封面页
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "AI驱动的智能测井解释工作流"
    slide1.placeholders[1].text = "基于知识图谱与机器学习的新型测井解释系统"
    
    # 添加内容页
    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "技术架构"
    slide2.placeholders[1].text = "logIntKnowledge（知识层）\nlogInt（执行层）\n四层架构设计"
    
    # 保存
    prs.save(output_file)
    print(f"PPT已生成: {output_file}")
else:
    print("母版文件不存在")
