# -*- coding: utf-8 -*-
"""报告黄金回归：固定决策报告的结构与关键内容（模板/契约回归）。

检查：
  1) 必备章节存在（基础数据/决策结论/知识使用/参数/结论与分布/逐层解释依据/交汇图/准确率/录井图/清洗QC）；
  2) 层表行数、交汇图数量、内嵌图片数、气测异常井段表行数；
  3) PDF 存在、页数≥1、大小>100KB。

用法：
  python -m logsys.golden_report --well TrakesKE-1 --update
  python -m logsys.golden_report --well TrakesKE-1 --check
"""
import argparse
import glob
import json
import os
import re
import sys

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'
GOLD_DIR = os.path.join(BASE, 'tests', 'golden')

SECTIONS = ['0. 基础数据', '1. 决策结论', '2. 知识使用', '3. 参数选择',
            '4. 结论与分布', '4.1 逐层解释依据', '4.2 交汇图', '5. 准确率与指标',
            '6. 录井图（masterlog）证据', '7. 数据清洗与 QC']


def resolve_dir(well: str, d: str | None) -> str | None:
    cands = [d] if d else [os.path.join(WS, 'output', well), os.path.join(BASE, 'output', well)]
    return next((x for x in cands if x and os.path.isdir(x)), None)


def fingerprint(well: str, d: str) -> dict:
    hp = os.path.join(d, '%s_decision_report.html' % well)
    pp = os.path.join(d, '%s_decision_report.pdf' % well)
    fp = {'well': well, 'dir': d, 'html_exists': os.path.exists(hp),
          'pdf_exists': os.path.exists(pp), 'sections': {}, 'images': 0,
          'xplots': 0, 'layer_rows': 0, 'gas_zone_rows': 0, 'pdf_pages': 0,
          'pdf_size': os.path.getsize(pp) if os.path.exists(pp) else 0}
    if fp['html_exists']:
        h = open(hp, encoding='utf-8').read()
        for s in SECTIONS:
            fp['sections'][s] = (s in h)
        fp['images'] = int(h.count('data:image/png;base64,'))
        fp['xplots'] = len(glob.glob(os.path.join(d, '%s_xplot_*.png' % well)))
        # 逐层依据表行数（tr 行，排除表头）
        m = re.search(r'4\.1 逐层解释依据.*?<table>(.*?)</table>', h, flags=re.S)
        if m:
            fp['layer_rows'] = m.group(1).count('<tr>') - 1
        # 气测异常井段表行数
        m2 = re.search(r'气测异常井段顶.*?<table>(.*?)</table>', h, flags=re.S)
        if m2:
            fp['gas_zone_rows'] = m2.group(1).count('<tr>') - 1
    if fp['pdf_exists']:
        try:
            import fitz
            fp['pdf_pages'] = int(fitz.open(pp).page_count)
        except Exception:
            pass
    return fp


def compare(cur: dict, gold: dict) -> list:
    out = []
    for s in SECTIONS:
        out.append(('章节: ' + s, cur['sections'].get(s) == gold['sections'].get(s),
                    (cur['sections'].get(s), gold['sections'].get(s))))
    for k in ('images', 'xplots', 'layer_rows', 'gas_zone_rows'):
        out.append((k, cur.get(k) == gold.get(k), (cur.get(k), gold.get(k))))
    out.append(('pdf 存在', cur.get('pdf_exists') == gold.get('pdf_exists'),
                (cur.get('pdf_exists'), gold.get('pdf_exists'))))
    out.append(('pdf 页数', cur.get('pdf_pages', 0) >= 1,
                cur.get('pdf_pages')))
    out.append(('pdf 大小>100KB', cur.get('pdf_size', 0) > 100 * 1024, cur.get('pdf_size')))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='决策报告黄金回归')
    ap.add_argument('--well', required=True)
    ap.add_argument('--dir', default=None)
    ap.add_argument('--update', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    d = resolve_dir(args.well, args.dir)
    if not d:
        print('输出目录不存在:', args.well); return 2
    cur = fingerprint(args.well, d)
    gp = os.path.join(GOLD_DIR, 'report_%s.json' % args.well)
    if args.update:
        os.makedirs(GOLD_DIR, exist_ok=True)
        json.dump(cur, open(gp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('基线已更新:', gp)
        return 0
    if not os.path.exists(gp):
        print('基线不存在，请先 --update:', gp); return 2
    gold = json.load(open(gp, encoding='utf-8'))
    res = compare(cur, gold)
    ok = sum(1 for _, k, _ in res if k)
    for name, k, det in res:
        print(('  PASS  ' if k else '  FAIL  ') + name + ' | ' + str(det))
    print('\n结果: %d 通过, %d 失败（%s）' % (ok, len(res) - ok, d))
    return 0 if ok == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
