# -*- coding: utf-8 -*-
"""试油表导入：通用"试油结论表 → 标准化真值 CSV"（支持多段合试、产量单位方）。

已适配：乍得 Doseo2023 试油表（`Doseo试油2023.xlsx`，列：序号/井名/试油层数/试油层号/井段/试油时间/日产量(方)/试油结论）。

用法：
    python -m logsys.truth_import --src "D:\\360\\Chad\\Doseo试油2023.xlsx" --out-root "D:\\360\\Chad"
    python -m logsys.truth_import --src ... --well "Ximenia-5"   # 只导一口井
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd

CONCL_MAP = {
    '油层': 'OIL', '干层': 'TIGHT', '致密层': 'TIGHT', '水层': 'WATER',
    '含油水层': 'OIL_WATER', '油水同层': 'OIL_WATER', '含水油层': 'OIL_WATER',
    '气层': 'GAS', '含气层': 'GAS', '含气水层': 'MIXED', '气水同层': 'MIXED',
    '含油层': 'OIL', '油水层': 'OIL_WATER', '水淹层': 'WATER',
}
RANGE_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?)\s*[-–~至]\s*([0-9]+(?:\.[0-9]+)?)')


def parse_doseo(src: str, well_filter: str | None = None) -> pd.DataFrame:
    d = pd.read_excel(src, sheet_name=0, header=None)
    rows = []
    well = ''
    for i in range(2, len(d)):
        r = d.iloc[i]
        w = r.iloc[1]
        if isinstance(w, str) and w.strip():
            well = w.strip()
        seg = str(r.iloc[4] or '')
        concl = str(r.iloc[9] or '').strip()
        if not well or not seg or not concl:
            continue
        if well_filter and well.upper().replace(' ', '') != well_filter.upper().replace(' ', ''):
            continue
        for top_s, base_s in RANGE_RE.findall(seg):
            top, base = float(top_s), float(base_s)
            if base <= top:
                continue
            rows.append({'WELL': well, 'TEST_NO': str(r.iloc[3] or '').strip(),
                         'TOP_MD': top, 'BASE_MD': base,
                         'FLUID_CN': concl, 'FLUID': CONCL_MAP.get(concl, 'MIXED'),
                         'OIL_M3': r.iloc[6], 'GAS_M3': r.iloc[7], 'WATER_M3': r.iloc[8],
                         'TEST_DATE': r.iloc[5], 'RAW_SEG': seg.replace('\n', ' ').strip()[:80]})
    return pd.DataFrame(rows)


def write_well_truth(df: pd.DataFrame, out_root: str, src_name: str) -> list:
    written = []
    for well, g in df.groupby('WELL'):
        safe = re.sub(r'[^\w\-]', '_', well.upper())
        g = g.sort_values('TOP_MD').reset_index(drop=True)
        g['THICKNESS'] = (g['BASE_MD'] - g['TOP_MD']).round(3)
        g['SOURCE'] = '试油表: ' + src_name
        g['CONF'] = 0.9
        g['NOTE'] = '试油结论（多段合试已拆为多区间同结论；产量单位=方）'
        out_dir = os.path.join(out_root, well)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, safe + '_truth.csv')
        g[['TOP_MD', 'BASE_MD', 'THICKNESS', 'FLUID', 'FLUID_CN', 'TEST_NO',
           'OIL_M3', 'GAS_M3', 'WATER_M3', 'TEST_DATE', 'RAW_SEG',
           'SOURCE', 'CONF', 'NOTE']].to_csv(path, index=False, encoding='utf-8-sig')
        written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description='试油表 → 标准化真值 CSV')
    ap.add_argument('--src', required=True, help='试油表 xlsx')
    ap.add_argument('--out-root', required=True, help='输出根目录（每井一子目录）')
    ap.add_argument('--well', default=None, help='只导出指定井')
    args = ap.parse_args(argv)
    df = parse_doseo(args.src, args.well)
    if len(df) == 0:
        print('未解析到试油层段'); return 1
    print('解析 %d 段 / %d 井' % (len(df), df['WELL'].nunique()))
    for p in write_well_truth(df, args.out_root, os.path.basename(args.src)):
        print(' ->', p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
