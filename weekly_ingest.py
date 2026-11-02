# -*- coding: utf-8 -*-
"""从周报PDF提取试油成果动态跟踪表并入库"""
import os, sys, glob
import pdfplumber
import pandas as pd
sys.path.insert(0, r'F:\360\src')
from well_test_store import WellTestIngestor, WellTestExtractor


def extract_weekly_tables(pdf_path, ing, extractor):
    """逐页提取PDF表格, 识别试油成果表(含试油结论/日产量等)入库"""
    n, files_hit = 0, 0
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            try:
                tables = page.extract_tables()
            except Exception:
                continue
            for table in tables:
                if not table:
                    continue
                df = pd.DataFrame(table)
                recs = extractor.extract_dataframe(df, source_file=os.path.basename(pdf_path))
                if recs:
                    files_hit += 1
                    n += ing.ingest_records(recs, source_file=os.path.basename(pdf_path))
    return n, files_hit


def has_text_layer(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = sum(len((p.extract_text() or "")) for p in pdf.pages[:5])
            return total > 100
    except Exception:
        return False


if __name__ == "__main__":
    ing = WellTestIngestor()
    extractor = WellTestExtractor()
    # 只处理有文本层的周报(扫描件需要OCR, 稍后)
    weekly = [
        r'F:\360\海外油气勘探动态周报-2026年-第16期.pdf',
        r'F:\360\Company Profile\海外油气勘探动态周报-2026年-第16期.pdf',
    ]
    for f in weekly:
        if not os.path.exists(f):
            print("[缺失]", f); continue
        if not has_text_layer(f):
            print("[扫描件跳过]", f); continue
        n, hit = extract_weekly_tables(f, ing, extractor)
        print(f"[周报] {os.path.basename(f)}: 入库 {n} 条(命中 {hit} 张表)")
    print("周报表入库完成")
