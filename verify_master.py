from pptx import Presentation

# 加载原始母版
master_prs = Presentation("FLAIR解释.pptx")
# 加载生成的PPT
gen_prs = Presentation("output/AI测井解释工作流_母版_20260609_151949.pptx")

print("=== 原始母版信息 ===")
print(f"母版数量: {len(master_prs.slide_masters)}")
print(f"布局数量: {len(master_prs.slide_layouts)}")
for i, layout in enumerate(master_prs.slide_layouts):
    print(f"  布局 {i}: {layout.name}")
    for j, ph in enumerate(layout.placeholders):
        print(f"    占位符 {j}: {ph.name}")

print("\n=== 生成的PPT信息 ===")
print(f"母版数量: {len(gen_prs.slide_masters)}")
print(f"布局数量: {len(gen_prs.slide_layouts)}")
for i, layout in enumerate(gen_prs.slide_layouts):
    print(f"  布局 {i}: {layout.name}")

print("\n=== 生成的PPT幻灯片内容 ===")
for i, slide in enumerate(gen_prs.slides):
    title = slide.shapes.title.text if slide.shapes.title else "无标题"
    print(f"幻灯片 {i+1}: {title}")
    
    # 检查占位符
    for ph in slide.placeholders:
        if ph.has_text_frame and ph.text:
            print(f"  占位符 '{ph.name}': 有内容")

# 检查母版是否相同
print("\n=== 母版对比 ===")
master_name = master_prs.slide_masters[0].name if master_prs.slide_masters else "无"
gen_name = gen_prs.slide_masters[0].name if gen_prs.slide_masters else "无"
print(f"原始母版名称: {master_name}")
print(f"生成PPT母版名称: {gen_name}")
print(f"母版名称相同: {master_name == gen_name}")