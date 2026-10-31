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
    ap.add_argument('--out-root', default=None, help='输出根目录（doseo 模式必填）')
    ap.add_argument('--well', default=None, help='只导出指定井')
    ap.add_argument('--kind', default='doseo', choices=['doseo', 'offset_summary'])
    ap.add_argument('--out-dir', default=None, help='offset_summary 输出目录')
    args = ap.parse_args(argv)
    if args.kind == 'offset_summary':
        full, facts, n = parse_offset_summary(args.src, args.out_dir or args.out_root)
        print('rows:', n); print('full  ->', full); print('facts ->', facts)
        return 0
    if not args.out_root:
        print('doseo 模式需要 --out-root'); return 1
    df = parse_doseo(args.src, args.well)
    if len(df) == 0:
        print('未解析到试油层段'); return 1
    print('解析 %d 段 / %d 井' % (len(df), df['WELL'].nunique()))
    for p in write_well_truth(df, args.out_root, os.path.basename(args.src)):
        print(' ->', p)
    return 0




# --------------------------------------------------------------------------- #
# 邻井试油测试汇总（如 BET-1 supportdata 的「试油测试资料汇总.xlsx」）
# --------------------------------------------------------------------------- #
OFFSET_CONCL_MAP = {
    '产油': 'OIL', '产气': 'GAS', '含水': 'WATER', '水率': 'WATER',
    '抽汲估算油': 'OIL', '抽汲油': 'OIL', '仅抽汲': 'OTHER', '无测试文件': 'OTHER',
    '无产量': 'OTHER', '干层': 'TIGHT', '油水': 'OIL_WATER', '气水': 'MIXED',
}


def parse_offset_summary(src: str, out_dir: str, source_name: str | None = None):
    """解析「试油测试汇总」sheet → 全量 CSV + 事实 CSV（供 offset_tests 入库）。"""
    import os
    import pandas as pd
    d = pd.read_excel(src, sheet_name='试油测试汇总', header=0)
    cols = list(d.columns)
    def col(*keys):
        for c in cols:
            for k in keys:
                if k in str(c):
                    return c
        return None
    c_well = col('井名'); c_block = col('区块'); c_form = col('层位')
    c_type = col('测试类型'); c_top = col('顶深'); c_bot = col('底深')
    c_lith = col('岩性'); c_oil = col('产油'); c_gas = col('产气')
    c_water = col('含水'); c_fluid = col('流体性质'); c_concl = col('测试结论')
    c_src = col('资料来源'); c_note = col('备注')
    src_name = source_name or os.path.basename(src)
    rows = []
    for _, r in d.iterrows():
        well = str(r.get(c_well) or '').strip() if c_well else ''
        if not well:
            continue
        concl = str(r.get(c_concl) or '').strip() if c_concl else ''
        kind = 'OTHER'
        for k, v in OFFSET_CONCL_MAP.items():
            if k in concl:
                kind = v
                break
        rows.append({
            'WELL': well,
            'BLOCK': str(r.get(c_block) or '').strip() if c_block else '',
            'FORMATION': str(r.get(c_form) or '').strip() if c_form else '',
            'TEST_TYPE': str(r.get(c_type) or '').strip() if c_type else '',
            'TOP_FT': r.get(c_top), 'BOT_FT': r.get(c_bot),
            'LITHOLOGY': str(r.get(c_lith) or '').strip() if c_lith else '',
            'OIL_BOPD': r.get(c_oil), 'GAS_MMSCFD': r.get(c_gas), 'WATER_BWPD': r.get(c_water),
            'FLUID_PROPS': str(r.get(c_fluid) or '').strip() if c_fluid else '',
            'CONCLUSION_RAW': concl, 'RESULT_KIND': kind,
            'SOURCE': '试油表: ' + src_name,
            'NOTE': str(r.get(c_note) or '').strip() if c_note else '',
            'CONF': 0.7,
        })
    full = pd.DataFrame(rows)
    import os as _os
    _os.makedirs(out_dir, exist_ok=True)
    full_path = _os.path.join(out_dir, 'offset_test_summary.csv')
    full.to_csv(full_path, index=False, encoding='utf-8-sig')
    _bot = pd.to_numeric(full['BOT_FT'], errors='coerce')
    _top = pd.to_numeric(full['TOP_FT'], errors='coerce')
    facts = pd.DataFrame({
        'ZONE': full['FORMATION'].replace('', '未定'),
        'WELL': full['WELL'],
        'DST_RESULT_RAW': full['CONCLUSION_RAW'],
        'RESULT_KIND': full['RESULT_KIND'],
        'TOP_FT': _top, 'BOT_FT': _bot,
        'DEPTH_CLASS': [('SHALLOW' if (pd.notna(b) and b <= 6900)
                         else ('MID' if (pd.notna(b) and b <= 8000)
                               else ('SHALLOW_INFERRED'
                                     if any(k in (str(f) + str(blk) + str(nt)).upper()
                                            for k in ('TAF', '浅', '<6900', '6900'))
                                     else 'UNKNOWN')))
                        for b, f, blk, nt in zip(_bot, full['FORMATION'],
                                                 full['BLOCK'], full['NOTE'])],
        'SOURCE': full['SOURCE'],
        'CONF': full['CONF'],
    })
    facts_path = _os.path.join(out_dir, 'offset_test_facts.csv')
    facts.to_csv(facts_path, index=False, encoding='utf-8-sig')
    return full_path, facts_path, len(full)


def _offset_cli():
    import argparse, sys
    ap = argparse.ArgumentParser(description='邻井试油测试汇总 → CSV')
    ap.add_argument('--src', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()
    full, facts, n = parse_offset_summary(args.src, args.out_dir)
    print('rows:', n)
    print('full  ->', full)
    print('facts ->', facts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
