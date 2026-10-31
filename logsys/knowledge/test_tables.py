# -*- coding: utf-8 -*-
"""试油动态表/潜山试油表 → 每井真值 CSV（TOP_MD/BASE_MD/FLUID），用于知识库案例。

支持：
  1) 尼日尔重点井试油动态表（顶深/底深/层位/试油方法/油嘴/油方/气万方/水方/API）
  2) 乍得潜山钻井试油统计（潜山或地区/井号/试油井段/试油类型/产量）
输出：
  <out_dir>/<井>_test_truth.csv  （列：TOP_MD,BASE_MD,FLUID,LAYER,TEST_NO,UNIT,SOURCE,CONF）
"""
from __future__ import annotations

import argparse
import os
import re

import pandas as pd


def _fluid(oil: float, gas: float, water: float) -> str:
    o = oil if oil == oil and oil > 0 else 0.0
    g = gas if gas == gas and gas > 0 else 0.0
    w = water if water == water and water > 0 else 0.0
    if o > 0 and w > 0:
        return 'OIL_WATER'
    if o > 0:
        return 'OIL'
    if g > 0:
        return 'GAS'
    if w > 0:
        return 'WATER'
    return ''


def _num(x):
    try:
        v = float(str(x).replace(',', '').strip())
        return v if v == v else None
    except Exception:
        return None


def _intervals_from_text(txt: str):
    m = re.findall(r'(\d+(?:\.\d+)?)\s*[-~—]\s*(\d+(?:\.\d+)?)', str(txt))
    out = []
    for a, b in m:
        try:
            t, b2 = float(a), float(b)
            if b2 > t:
                out.append((t, b2))
        except Exception:
            pass
    return out


def parse_niger_dynamic(xls: str, out_dir: str) -> dict:
    """尼日尔重点井试油动态表（header 2 行，井号为合并单元格需前向填充）。"""
    d = pd.read_excel(xls, sheet_name=0, header=None)
    rows, well = [], None
    for i in range(2, len(d)):
        r = d.iloc[i]
        w = r.iloc[0]
        if isinstance(w, str) and w.strip():
            well = w.strip()
        top, bot = _num(r.iloc[2]), _num(r.iloc[3])
        if not well or top is None or bot is None or bot <= top:
            continue
        oil = _num(r.iloc[7]) or 0.0
        gas = _num(r.iloc[8]) or 0.0
        water = _num(r.iloc[9]) or 0.0
        fl = _fluid(oil, gas, water)
        if not fl:
            continue
        rows.append({'WELL': well, 'TOP_MD': top, 'BASE_MD': bot, 'FLUID': fl,
                     'LAYER': str(r.iloc[4]).strip() if pd.notna(r.iloc[4]) else '',
                     'TEST_NO': '', 'OIL_M3': oil, 'GAS_104M3': gas, 'WATER_M3': water,
                     'SOURCE': os.path.basename(xls), 'CONF': 0.8})
    return _write(rows, out_dir)


def parse_chad_buried(xls: str, out_dir: str) -> dict:
    """乍得潜山钻井试油统计（Sheet2，第 4 行起；地区/井号前向填充；井段为区间文本）。"""
    d = pd.read_excel(xls, sheet_name='Sheet2', header=None)
    rows, well = [], None
    for i in range(4, len(d)):
        r = d.iloc[i]
        w = r.iloc[1]
        if isinstance(w, str) and w.strip():
            well = w.strip()
        if not well:
            continue
        seg = r.iloc[10]
        ints = _intervals_from_text(seg) if pd.notna(seg) else []
        oil = _num(r.iloc[14]) or 0.0
        gas = _num(r.iloc[15]) or 0.0
        water = _num(r.iloc[16]) or 0.0
        fl = _fluid(oil, gas, water)
        if not ints or not fl:
            continue
        top, bot = ints[0]
        rows.append({'WELL': well, 'TOP_MD': top, 'BASE_MD': bot, 'FLUID': fl,
                     'LAYER': str(r.iloc[11]).strip() if pd.notna(r.iloc[11]) else '',
                     'TEST_NO': '', 'OIL_M3': oil, 'GAS_104M3': gas, 'WATER_M3': water,
                     'SOURCE': os.path.basename(xls), 'CONF': 0.8})
    return _write(rows, out_dir)


def _write(rows: list, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    if not rows:
        return {'wells': 0, 'segments': 0, 'files': []}
    d = pd.DataFrame(rows)
    # 同一井同一井段（多油嘴多行）→ 取有产量的一行；同井段去重
    d = d.sort_values(['WELL', 'TOP_MD', 'BASE_MD'])
    d = d.drop_duplicates(subset=['WELL', 'TOP_MD', 'BASE_MD'], keep='first')
    files = []
    for well, g in d.groupby('WELL'):
        g2 = g.copy()
        g2['UNIT'] = 'm'
        p = os.path.join(out_dir, '%s_test_truth.csv' % re.sub(r'[\\/:*?"<>|]', '_', well))
        g2.to_csv(p, index=False, encoding='utf-8-sig')
        files.append((well, p, len(g2)))
    return {'wells': len(files), 'segments': int(len(d)),
            'files': [{'well': w, 'path': p, 'segments': n} for w, p, n in files]}


def main(argv=None):
    ap = argparse.ArgumentParser(description='试油动态表 → 每井真值 CSV')
    ap.add_argument('--kind', required=True, choices=['niger_dynamic', 'chad_buried'])
    ap.add_argument('--src', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args(argv)
    fn = parse_niger_dynamic if args.kind == 'niger_dynamic' else parse_chad_buried
    r = fn(args.src, args.out_dir)
    print('wells=%d segments=%d' % (r['wells'], r['segments']))
    for f in r['files']:
        print('  %-16s %4d 段 -> %s' % (f['well'], f['segments'], f['path']))
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
