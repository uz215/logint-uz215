#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 AI测井解释工作方法.pptx
根据 logInt.py 和 logIntKnowledge.py 的实际功能，调整PPT内容
"""

from pptx import Presentation
from pathlib import Path
import shutil


def set_text(shape, text):
    """设置 shape 的完整文本"""
    if shape.has_text_frame:
        shape.text_frame.text = text
        return True
    return False


def clear_text(shape):
    """清空 shape 中的文本（文本框或表格）"""
    if shape.has_text_frame:
        shape.text_frame.text = ''
    if shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                cell.text = ''


def main():
    src_dir = Path(r'F:\360\Pythonwork\project\src')
    ppt_path = src_dir / 'AI测井解释工作方法.pptx'
    backup_path = src_dir / 'AI测井解释工作方法.pptx.bak'

    # 备份原文件
    if not backup_path.exists():
        shutil.copy2(ppt_path, backup_path)
        print(f'已创建备份: {backup_path}')

    prs = Presentation(ppt_path)
    slides = list(prs.slides)

    # ------------------------------
    # 幻灯片 1：标题页
    # shape 0 = 标题，shape 1 = 副标题，shape 2 = 空
    # ------------------------------
    slide = slides[0]
    set_text(slide.shapes[1],
             '基于 logInt 解释引擎与 logIntKnowledge 知识库系统\n'
             '数据驱动 + 知识驱动 + 模型驱动 三位一体的智能测井解释工作方法')

    # ------------------------------
    # 幻灯片 3：汇报提纲
    # shape 0 = 标题，shape 1 = 内容
    # ------------------------------
    slide = slides[2]
    set_text(slide.shapes[1],
             '【一、传统方法的局限性】\n'
             '问题分析 | 效率瓶颈 | 知识碎片化\n\n'
             '【二、新方法的核心思想】\n'
             'logInt 数据解释 + logIntKnowledge 知识推理 双引擎驱动\n\n'
             '【三、logInt 解释引擎】\n'
             '数据加载 | 质量检查 | 多矿物分析 | 图版识别 | 成果输出\n\n'
             '【四、logIntKnowledge 知识库】\n'
             '知识采集 | 全文检索 | 项目知识管理 | 智能问答支撑\n\n'
             '【五、图版方法详解】\n'
             '岩性交汇图 | 特殊岩性图版 | 流体识别模板 | 匹配算法\n\n'
             '【六、应用案例分析】\n'
             '砂岩储层 | 低阻油层 | 碳酸盐岩 | 沉积相分析\n\n'
             '【七、方法优势与总结】\n'
             '效率对比 | 准确性评估 | 知识沉淀')

    # ------------------------------
    # 幻灯片 6：核心业务流程图
    # ------------------------------
    slide = slides[5]
    # 说明文本
    set_text(slide.shapes[3],
             '本页展示 logInt 与 logIntKnowledge 协同的核心业务流程。\n'
             '左侧为 logIntKnowledge 知识库支撑层，负责资料知识、公式知识、地质知识、'
             '方案知识、试油知识的采集、索引与检索；\n'
             '右侧为 logInt 解释引擎执行层，负责数据加载、质量控制、多矿物分析、'
             '图版识别、沉积相分析与成果输出。')
    # 流程节点
    set_text(slide.shapes[10], '导入测井数据\n(LAS/DLIS/CSV/Excel)')
    set_text(slide.shapes[14], 'logInt 数据加载与井信息提取')
    set_text(slide.shapes[19], '数据质量检查与异常报告')
    set_text(slide.shapes[28], '调用 logIntKnowledge 检索区域知识与解释方案')
    set_text(slide.shapes[32], '多矿物分析与岩性识别')
    set_text(slide.shapes[37], '图版匹配、流体识别与沉积相分析\n异常返回重新检索')
    set_text(slide.shapes[46], '生成解释剖面、参数表与可视化成果')
    set_text(slide.shapes[50], 'HTML/文本报告生成与用户确认')
    set_text(slide.shapes[55], '解释结论归档与知识库更新')

    # ------------------------------
    # 幻灯片 10：知识库架构
    # shape 0 = 标题，shape 1 = 空，shape 2 = 内容，shape 3/4 = 表格
    # ------------------------------
    slide = slides[9]
    set_text(slide.shapes[2],
             '【logIntKnowledge 知识库架构】\n\n'
             '测井解释知识库系统由以下核心模块组成：\n'
             '• ProjectKnowledgeManager：项目/地区知识库管理，支持按项目组织文档与索引\n'
             '• DocumentConverter：多格式文档转换（PPT/PDF/DOC/Excel/图片/OCR）\n'
             '• WellLogDataParser：测井数据文件解析（LAS/DLIS/CSV/Excel）\n'
             '• WhooshIndexer：基于中文分词（jieba）的全文检索与相似度搜索\n'
             '• EnhancedCrawler：网络知识自动爬取与模拟知识生成\n'
             '• Translator：中英双语测井术语翻译支持')
    clear_text(slide.shapes[3])
    clear_text(slide.shapes[4])

    # ------------------------------
    # 幻灯片 11：公式知识与测井地质知识
    # ------------------------------
    slide = slides[10]
    set_text(slide.shapes[2],
             '【公式知识（logInt 配置驱动）】\n'
             '• 阿尔奇公式参数：a、m、n、Rw、Rsh（支持 logint.json 配置）\n'
             '• 泥质含量计算：GR 分位数法 + 密度-中子交汇法（可配置权重）\n'
             '• 孔隙度计算：密度法、中子法、声波时差法、多矿物最优化法\n'
             '• 渗透率估算：Timur/Coates 经验公式与机器学习预测\n\n'
             '【测井地质知识（logIntKnowledge 支撑）】\n'
             '• 测井-地质对应关系：GR 形态与沉积环境识别（钟形/漏斗形/箱形/锯齿形）\n'
             '• 岩性-测井曲线对应关系：砂岩、泥岩、灰岩、白云岩、火山岩响应特征\n'
             '• 区域经验知识：松辽、渤海湾、鄂尔多斯、塔里木等盆地测井响应库')

    # ------------------------------
    # 幻灯片 12：解决方案知识与试油知识
    # ------------------------------
    slide = slides[11]
    set_text(slide.shapes[2],
             '【解决方案知识】\n'
             '• 复杂砂岩、低阻油层、碳酸盐岩缝洞型储层解释方案\n'
             '• 多矿物模型选择：砂泥岩剖面 / 碳酸盐岩剖面 / 混合剖面自动判定\n'
             '• 成像测井、核磁测井、元素测井等特殊资料处理流程\n\n'
             '【试油知识】\n'
             '• 试油方法与试油结论结构化存储\n'
             '• 地区/井/井段试油数据与测井解释结论对比\n'
             '• 解释符合率统计与模型参数反馈标定\n\n'
             '【知识更新机制】\n'
             '• 本地 Markdown/PDF/DOC/PPT 文档批量导入与增量索引\n'
             '• 网络知识自动爬取（SPE、OnePetro、百度百科、微信公众号等）\n'
             '• 测井数据文件自动解析并生成知识条目')

    # ------------------------------
    # 幻灯片 13：图版方法详解
    # ------------------------------
    slide = slides[12]
    set_text(slide.shapes[2],
             '【图版类型（logInt 内置）】\n'
             '• 岩性交汇图版：密度-声波时差、PE-密度、CNL-密度（K-means 聚类）\n'
             '• 特殊岩性图版：TAS 火山岩分类图版、PQF 石英成因图版\n'
             '• 流体识别模板：GAS / OIL / WATER / DRY 四类模板（基于 Sw/Vsh/RT/POR）\n\n'
             '【图版构建流程】\n'
             '测井数据加载 → 岩性交汇图聚类 → 动态骨架参数估算 → 多矿物最优化 → 专家验证\n\n'
             '【匹配算法】\n'
             '• 欧氏距离相似度：用于岩性聚类与流体模板匹配\n'
             '• K-means 无监督聚类：自动识别本井主要岩性群体\n'
             '• 多矿物最优化（SLSQP/trust-constr/L-BFGS-B）：计算矿物含量与孔隙度\n'
             '• 曲线形态识别：箱形/钟形/漏斗形/指状/锯齿形，辅助沉积相判断')

    # ------------------------------
    # 幻灯片 29：方法优势与价值
    # ------------------------------
    slide = slides[28]
    set_text(slide.shapes[2],
             '【效率提升】\n'
             '  传统方法: 单井周期 3 天\n'
             '  logInt:   数据加载→质量控制→多矿物分析→图版匹配→报告生成自动化\n\n'
             '【准确性】\n'
             '  传统方法: 符合率 70-80%\n'
             '  logInt:   多矿物最优化 + 动态骨架参数 + 图版迭代核验，符合率 85% 以上\n\n'
             '【一致性】\n'
             '  传统方法: 依赖专家经验，结果差异大\n'
             '  logInt + logIntKnowledge: 标准化流程 + 可复用知识库，解释一致性高\n\n'
             '【知识传承】\n'
             '  传统方法: 知识碎片化、难以传承\n'
             '  logIntKnowledge: 本地文档/网络知识/测井数据统一索引，支持全文检索与项目复用')

    # ------------------------------
    # 幻灯片 30：总结
    # ------------------------------
    slide = slides[29]
    set_text(slide.shapes[2],
             '【方法核心】\n'
             'logInt 解释引擎 + logIntKnowledge 知识库双轮驱动\n\n'
             '【关键技术】\n'
             '• logInt：数据加载（LAS/DLIS/CSV/Excel）、质量检查、多矿物最优化、'
             '岩性/流体识别、沉积相分析、可视化与报告\n'
             '• logIntKnowledge：文档转换、网络爬取、全文检索、项目管理、'
             '测井数据解析、知识问答支撑\n\n'
             '【应用前景】\n'
             '适用于砂岩、低阻油层、碳酸盐岩、火山岩、致密储层等复杂储层类型\n\n'
             '【下一步工作】\n'
             '• 深化深度学习模型在岩性识别与流体预测中的应用\n'
             '• 扩展多井对比与地层对比功能\n'
             '• 构建基于大模型的智能测井解释问答助手')

    # 保存
    prs.save(ppt_path)
    print(f'PPT 更新完成: {ppt_path}')


if __name__ == '__main__':
    main()
