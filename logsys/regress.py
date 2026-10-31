# -*- coding: utf-8 -*-
"""批量回归：产物完整性 + 层表契约 + 黄金图回归。

用法：
    python -m logsys.regress                                  # 默认检查 workspace/output 下的 BET-1/TrakesKE-1
    python -m logsys.regress --wells BET-1,TrakesKE-1 --skip-golden
    python -m logsys.regress --root D:/360/src/output --out data/regress

检查项（每口井）：
  1) <井>_interpretation_layers.csv 存在、行数>0、必需列齐全（层表契约）；
  2) <井>_interpretation_layers_ML.csv 若存在则报告层数（不强制）；
  3) quicklook PDF 存在且 >0 字节；
  4) 黄金图回归（默认执行一次，与 tests/golden 基线比对）。
输出：JSON 报告 + 控制台汇总；有 FAIL 时退出码 1。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

BASE = r'D:\360\src'
DEFAULT_ROOTS = [r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace\output',
                 os.path.join(BASE, 'output')]
REQUIRED_COLS = ['LAYER_ID', 'TOP_MD', 'BASE_MD', 'THICKNESS', 'LITHOLOGY', 'INTERPRETATION']


def check_well(root: str, well: str, out: dict) -> dict:
    d = os.path.join(root, well)
    r = {'well': well, 'dir': d, 'checks': [], 'status': 'PASS'}
    if not os.path.isdir(d):
        r['checks'].append({'name': 'well_dir', 'status': 'FAIL', 'detail': '目录不存在'})
        r['status'] = 'FAIL'
        return r
    r['checks'].append({'name': 'well_dir', 'status': 'PASS'})

    # 1) 规则层表契约
    lp = os.path.join(d, well + '_interpretation_layers.csv')
    if not os.path.exists(lp):
        r['checks'].append({'name': 'layers_csv', 'status': 'FAIL', 'detail': '缺失'})
        r['status'] = 'FAIL'
    else:
        try:
            import pandas as pd
            df = pd.read_csv(lp)
            missing = [c for c in REQUIRED_COLS if c not in df.columns]
            ok = len(df) > 0 and not missing and df['INTERPRETATION'].notna().all()
            r['checks'].append({'name': 'layer_contract', 'status': 'PASS' if ok else 'FAIL',
                                'detail': '层数=%d 缺列=%s 结论空=%d' % (
                                    len(df), missing, int(df['INTERPRETATION'].isna().sum()))})
            if not ok:
                r['status'] = 'FAIL'
            r['layers'] = int(len(df))
        except Exception as e:
            r['checks'].append({'name': 'layer_contract', 'status': 'FAIL', 'detail': str(e)})
            r['status'] = 'FAIL'

    # 2) ML 层表（可选）
    mp = os.path.join(d, well + '_interpretation_layers_ML.csv')
    if os.path.exists(mp):
        try:
            import pandas as pd
            r['ml_layers'] = int(len(pd.read_csv(mp)))
            r['checks'].append({'name': 'ml_layers', 'status': 'PASS',
                                'detail': '层数=%d' % r['ml_layers']})
        except Exception as e:
            r['checks'].append({'name': 'ml_layers', 'status': 'WARN', 'detail': str(e)})

    # 3) quicklook PDF
    pdfs = sorted(glob.glob(os.path.join(d, well + '_quicklook_*.pdf')))
    if pdfs and os.path.getsize(pdfs[-1]) > 0:
        r['checks'].append({'name': 'quicklook_pdf', 'status': 'PASS',
                            'detail': os.path.basename(pdfs[-1])})
        r['pdf_size'] = os.path.getsize(pdfs[-1])
    else:
        r['checks'].append({'name': 'quicklook_pdf', 'status': 'FAIL', 'detail': '缺失'})
        r['status'] = 'FAIL'
    return r


def check_golden(out: dict, tol: float = 4.0) -> dict:
    g = {'name': 'golden_qlpt', 'status': 'PASS'}
    try:
        from logsys.golden import render, fingerprint, compare, GOLD_JSON
        pdf = render(os.path.join(BASE, 'data', 'golden_out'))
        cur = fingerprint(pdf)
        if not os.path.exists(GOLD_JSON):
            g.update(status='WARN', detail='基线不存在')
        else:
            gold = json.load(open(GOLD_JSON, encoding='utf-8'))
            diffs = compare(cur, gold, tol)
            g.update(status='PASS' if not diffs else 'FAIL', diffs=diffs,
                     detail='; '.join(diffs) if diffs else '页数/尺寸/文本/栅格一致')
    except Exception as e:
        g.update(status='FAIL', detail='%s: %s' % (type(e).__name__, e))
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description='批量回归（产物+层表契约+黄金图）')
    ap.add_argument('--wells', default='BET-1,TrakesKE-1')
    ap.add_argument('--root', action='append', default=None, help='输出根目录（可多次）')
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'regress'))
    ap.add_argument('--skip-golden', action='store_true')
    ap.add_argument('--tol', type=float, default=4.0)
    args = ap.parse_args(argv)
    roots = args.root or [r for r in DEFAULT_ROOTS if os.path.isdir(r)]
    wells = [w.strip() for w in args.wells.split(',') if w.strip()]
    report = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'roots': roots, 'wells': [],
              'golden': None, 'summary': {}}
    overall = True
    for w in wells:
        got = None
        for root in roots:
            if os.path.isdir(os.path.join(root, w)):
                got = check_well(root, w, report)
                break
        if got is None:
            got = {'well': w, 'status': 'FAIL', 'checks': [{'name': 'find', 'status': 'FAIL',
                                                             'detail': '在 %r 下未找到' % roots}]}
        if got['status'] != 'PASS':
            overall = False
        report['wells'].append(got)
    if not args.skip_golden:
        g = check_golden(report, args.tol)
        report['golden'] = g
        if g['status'] == 'FAIL':
            overall = False
    report['summary'] = {'status': 'PASS' if overall else 'FAIL',
                         'wells': len(report['wells']),
                         'failed': sum(1 for w in report['wells'] if w['status'] != 'PASS'),
                         'golden': (report.get('golden') or {}).get('status')}
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'regress_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    json.dump(report, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    print('%-14s %8s %8s %12s %s' % ('well', 'layers', 'ML层', 'PDF', 'status'))
    for w in report['wells']:
        print('%-14s %8s %8s %12s %s' % (w['well'], w.get('layers', '-'), w.get('ml_layers', '-'),
                                         w.get('pdf_size', '-'), w['status']))
    if report['golden']:
        print('golden_qlpt:', report['golden']['status'], '-', report['golden'].get('detail'))
    print('REGRESS:', report['summary']['status'], '->', path)
    return 0 if overall else 1


if __name__ == '__main__':
    sys.exit(main())
