# -*- coding: utf-8 -*-
"""批量重出图：从已有 <井>_processed.csv + <井>info.json 直接生成 quicklook PDF（不重跑解释）。

用于补历史成果缺失的 PDF（如 3-SPS-111D / XIMENIA-5 / TITAS-31），也可作为出图批处理工具。

用法：
    python -m logsys.rerender --well 3-SPS-111D --dir D:/360/src/output/3-SPS-111D --unit m
    python -m logsys.rerender --all --root D:/360/src/output
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

BASE = r'D:\360\src'


def render_one(well: str, d: str, unit: str = 'm') -> dict:
    import logvis
    proc = os.path.join(d, well + '_processed.csv')
    if not os.path.exists(proc):
        return {'well': well, 'ok': False, 'reason': '无 processed.csv'}
    info = os.path.join(d, well + 'info.json')
    data = pd.read_csv(proc, low_memory=False)
    results = {
        'well_name': well, 'output_dir': d, 'well_dir': d,
        'well_info_json': info if os.path.exists(info) else None,
        'depth_unit': unit,
        'las_info': {'well': {'well_name': well, 'depth_unit': unit}},
    }
    try:
        pdf = logvis.visualize_quicklook_log(data, results, gas_data=None, quicklook_config=None)
        return {'well': well, 'ok': bool(pdf), 'pdf': pdf,
                'size': os.path.getsize(pdf) if pdf and os.path.exists(pdf) else 0}
    except Exception as e:
        return {'well': well, 'ok': False, 'reason': '%s: %s' % (type(e).__name__, e)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='从成果 CSV 批量重出 quicklook 图')
    ap.add_argument('--well', default=None)
    ap.add_argument('--dir', default=None)
    ap.add_argument('--unit', default='m')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--root', action='append', default=None)
    args = ap.parse_args(argv)
    if args.well and args.dir:
        r = render_one(args.well, args.dir, args.unit)
        print(r)
        return 0 if r.get('ok') else 1
    roots = args.root or [os.path.join(BASE, 'output')]
    wells = []
    for root in roots:
        if os.path.isdir(root):
            for d in sorted(os.listdir(root)):
                p = os.path.join(root, d)
                if os.path.isdir(p) and glob.glob(os.path.join(p, '*_processed.csv')):
                    wells.append((d, p))
    ok = 0
    for well, d in wells:
        r = render_one(well, d, args.unit)
        print('%-14s %s %s' % (well, 'OK' if r.get('ok') else 'FAIL', r.get('reason', r.get('size'))))
        ok += 1 if r.get('ok') else 0
    print('完成 %d/%d' % (ok, len(wells)))
    return 0 if ok == len(wells) else 1


if __name__ == '__main__':
    sys.exit(main())
