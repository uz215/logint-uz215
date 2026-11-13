# -*- coding: utf-8 -*-
"""批量: 检测全部周报PDF文本层 + 提取试油成果表入库"""
import os, sys, glob
sys.path.insert(0, r'F:\360\src')
from weekly_ingest import extract_weekly_tables, has_text_layer
from well_test_store import WellTestIngestor, WellTestExtractor

# 已知周报PDF(含试油/动态)
WEEKLY = [
    r'F:\360\海外油气勘探动态周报-2026年-第16期.pdf',
    r'F:\360\Company Profile\海外油气勘探动态周报-2026年-第16期.pdf',
    r'F:\360\测井项目研究\核磁处理\海外油气勘探动态周报-2026年-第16期-7.pdf',
    r'F:\360\2021年项目\周报\海外油气勘探动态周报-2021年第52期.pdf',
    r'F:\360\2021年项目\周报\海外油气勘探动态周报-2021年第53期-1.pdf',
    r'F:\360\2021年项目\海外油气勘探动态周报-2021年第39期.pdf',
    r'F:\360\2021年项目\海外油气勘探动态周报-2021年第51期.pdf',
    r'F:\360\Brasil\4-SPS-112\海外油气勘探动态周报-2025年第12期.pdf',
    r'F:\360\Brasil\4-SPS-112\海外油气勘探动态周报-2025年第17期.pdf',
    r'F:\360\Brasil\Curacao-1\第11期—古拉绍-1井试油进展周报20221005.pdf',
    r'F:\360\Brasil\Curacao-2\海外油气勘探动态周报-2023年第24期.pdf',
    r'F:\360\Brasil\Curacao-2\海外油气勘探动态周报-2023年第36期.pdf',
    r'F:\360\Brasil\CuraCao-4A\海外油气勘探动态周报-2025年第43期.pdf',
    r'F:\360\Indonesia\NEB base-3\海外油气勘探动态周报-2024年第28期.pdf',
    r'F:\360\Indonesia\NEB base-3\海外油气勘探动态周报-2024年第29期.pdf',
    r'F:\360\Kazakhstan\海外油气勘探动态周报-2026年-第23期.pdf，BAK-8井试油，斜坡带典型例子.pdf',
    r'F:\360\四个平台\平台3：工作记录报表\3汇报\3客户汇报材料\1CNODC周报\CPL海外测井技术支持项目周报2015年第十九期.pdf',
]

ing = WellTestIngestor(); ex = WellTestExtractor()
text_ok, scan_only = [], []
for f in WEEKLY:
    if not os.path.exists(f):
        print("[缺失]", os.path.basename(f)); continue
    if has_text_layer(f):
        n, hit = extract_weekly_tables(f, ing, ex)
        print(f"[文本层] {os.path.basename(f)}: 入库 {n} 条({hit}表)")
        text_ok.append(f)
    else:
        print(f"[扫描件] {os.path.basename(f)}: 需OCR")
        scan_only.append(f)
print(f"\n汇总: 文本层 {len(text_ok)} 份, 扫描件 {len(scan_only)} 份(暂未处理)")
