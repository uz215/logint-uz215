# -*- coding: utf-8 -*-
"""从周报正文提取"井试油详细过程"叙述, 生成知识块入库(支持语义检索)"""
import os, re, sys
import pdfplumber
sys.path.insert(0, r'F:\360\src')

KNOWLEDGE_DIR = r'F:\360\src\data\local\well_test'

WEEKLY = [
    r'F:\360\海外油气勘探动态周报-2026年-第16期.pdf',
    r'F:\360\测井项目研究\核磁处理\海外油气勘探动态周报-2026年-第16期-7.pdf',
    r'F:\360\2021年项目\周报\海外油气勘探动态周报-2021年第52期.pdf',
    r'F:\360\2021年项目\周报\海外油气勘探动态周报-2021年第53期-1.pdf',
    r'F:\360\2021年项目\海外油气勘探动态周报-2021年第51期.pdf',
    r'F:\360\Brasil\4-SPS-112\海外油气勘探动态周报-2025年第12期.pdf',
    r'F:\360\Brasil\4-SPS-112\海外油气勘探动态周报-2025年第17期.pdf',
    r'F:\360\Brasil\Curacao-1\第11期—古拉绍-1井试油进展周报20221005.pdf',
    r'F:\360\Brasil\CuraCao-4A\海外油气勘探动态周报-2025年第43期.pdf',
    r'F:\360\Kazakhstan\海外油气勘探动态周报-2026年-第23期.pdf，BAK-8井试油，斜坡带典型例子.pdf',
]


def extract_text(pdf_path):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text() or ""
            out.append(t)
    return "\n".join(out)


def weekly_blocks(text):
    """按井/主题切出含试油过程的段落"""
    blocks = []
    for para in re.split(r"\n{2,}", text):
        p = para.strip()
        if not p or ("试油" not in p and "测试" not in p):
            continue
        # 只保留含井名线索的过程性段落
        if len(p) > 60 and re.search(r"(井|Test|测试|射孔|放喷|气举|抽汲|产量|油压|套压)", p):
            blocks.append(p)
    return blocks


def write_kb(pdf_path, blocks):
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    base = os.path.basename(pdf_path)
    m = re.search(r"(\d{4}年?第?\d+期|\d{4}年第\d+期|\d+期)", base)
    tag = m.group(1) if m else os.path.splitext(base)[0][:12]
    src = os.path.splitext(base)[0][:40]
    src = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", src)
    fname = "周报_%s_试油进展.md" % src
    fname = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", fname)
    path = os.path.join(KNOWLEDGE_DIR, fname)
    lines = [
        "---",
        "title: %s 海外油气勘探动态周报 试油进展" % tag,
        "category: well_test_weekly",
        "source_file: " + base,
        "---",
        "",
        "# %s 周报 试油进展" % tag,
        "",
    ]
    for i, b in enumerate(blocks, 1):
        lines.append("## 试油进展 %d" % i)
        lines.append("")
        lines.append(b.replace("\n", ""))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


if __name__ == "__main__":
    n_kb = 0
    for f in WEEKLY:
        if not os.path.exists(f):
            continue
        try:
            text = extract_text(f)
        except Exception as e:
            print("[失败]", os.path.basename(f), e); continue
        if len(text) < 100:
            print("[扫描件跳过]", os.path.basename(f)); continue
        blocks = weekly_blocks(text)
        if not blocks:
            print("[无试油叙述]", os.path.basename(f)); continue
        p = write_kb(f, blocks)
        n_kb += 1
        print("[知识块] %s: %d 段 -> %s" % (os.path.basename(f), len(blocks), os.path.basename(p)))
    print("共生成 %d 篇周报试油进展知识块" % n_kb)
