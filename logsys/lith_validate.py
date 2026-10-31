# -*- coding: utf-8 -*-
"""岩性一致率验证：承包商"岩性解释剖面" xlsx vs 本系统 processed.csv 的 LITHOLOGY。

真值格式（如 Trakes KE-1 岩性解释剖面.xlsx）：列 顶深(m)/底深(m)/厚度(m)/岩性(中文)。
输出：厚度加权一致率、混淆矩阵、各类召回。

用法：
    python -m logsys.lith_validate --profile "D:\\...\\Trakes KE-1 岩性解释剖面.xlsx" \
        --proc output/TrakesKE-1/TrakesKE-1_processed.csv
    python -m logsys.lith_validate --well TrakesKE-1   # 用内置井映射
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'

# 井 → (剖面 xlsx, processed csv 候选)
WELL_PROFILES = {
    'TrakesKE-1': {
        'profile': r'D:\360\Niger\Trakes KE-1\Trakes KE-1 岩性解释剖面.xlsx',
        'proc': [os.path.join(WS, 'output', 'TrakesKE-1', 'TrakesKE-1_processed.csv'),
                 os.path.join(BASE, 'output', 'TrakesKE-1', 'TrakesKE-1_processed.csv')],
    },
}

# 类别归并（砾岩并入砂岩、碳质页岩并入泥岩；岩性标定 lithcal 也用它）
MERGE_LITH = {'conglomerate': 'sandstone', 'carbonaceous_shale': 'shale'}

# 中文岩性 → 程序标准类别（与 layers/LITHOLOGY 英文口径对齐）
def norm_lith(s: str) -> str:
    s = str(s or '').strip()
    if not s:
        return ''
    if '碳质' in s and ('页岩' in s or '泥' in s):
        return 'carbonaceous_shale'
    if '煤' in s:
        return 'coal'
    if '砾' in s:
        return 'conglomerate'
    if '白云' in s:
        return 'dolomite'
    if '灰岩' in s:
        return 'limestone'
    if '膏' in s or '硬石膏' in s:
        return 'anhydrite'
    if '盐' in s:
        return 'halite'
    if '玄武' in s or '火山' in s:
        return 'volcanic'
    if '砂岩' in s:      # 泥质细砂岩/灰质细砂岩等仍属砂岩
        return 'sandstone'
    if '散沙' in s or ('沙' in s and '泥' not in s):
        return 'sandstone'
    if '砂质泥岩' in s or '砂质页岩' in s:
        return 'shale'
    if '泥' in s or '页岩' in s:
        return 'shale'
    if '砂' in s:
        return 'sandstone'
    return s


def load_profile(xlsx: str) -> pd.DataFrame:
    d = pd.read_excel(xlsx, sheet_name=0, header=None)
    rows = []
    for i in range(2, len(d)):
        try:
            top, base = float(d.iloc[i, 0]), float(d.iloc[i, 1])
        except Exception:
            continue
        lith = d.iloc[i, 3]
        if not (base > top) or not isinstance(lith, str) or not lith.strip():
            continue
        rows.append({'TOP': top, 'BASE': base, 'LITH_CN': lith.strip(),
                     'LITH': norm_lith(lith)})
    return pd.DataFrame(rows)


def evaluate(proc_csv: str, truth: pd.DataFrame, col: str = 'LITHOLOGY') -> dict:
    truth = truth.copy()
    truth['LITH'] = truth['LITH'].map(lambda x: MERGE_LITH.get(x, x))
    d = pd.read_csv(proc_csv, low_memory=False)
    md = pd.to_numeric(d['MD'], errors='coerce')
    our = d[col].astype(str).str.lower().str.strip() if col in d.columns \
        else pd.Series([''] * len(d))
    our = our.map(lambda x: MERGE_LITH.get(x, x))
    step = float(np.nanmedian(np.diff(np.unique(md.dropna().values)))) if md.notna().sum() > 1 else 1.0
    labels = sorted({str(x) for x in set(truth['LITH']) | set(our.astype(str).unique())})
    cm = {t: {p: 0.0 for p in labels} for t in labels}
    total = good = 0.0
    for _, r in truth.iterrows():
        m = (md >= r['TOP']) & (md < r['BASE'])
        if not m.any():
            continue
        w = float(m.sum()) * step
        total += w
        preds = our[m.values]
        # 取该层内最多的预测类别
        vc = preds.value_counts()
        pred = str(vc.index[0]) if len(vc) else ''
        if pred not in cm.get(r['LITH'], {}):
            cm.setdefault(r['LITH'], {}).setdefault(pred, 0.0)
            for t2 in cm:
                cm[t2].setdefault(pred, 0.0)
        cm.setdefault(r['LITH'], {}).setdefault(pred, 0.0)
        cm[r['LITH']][pred] = cm[r['LITH']].get(pred, 0.0) + w
        if pred == r['LITH']:
            good += w
    recall = {}
    for t in truth['LITH'].unique():
        tot = sum(cm.get(t, {}).values())
        recall[t] = round(cm[t].get(t, 0.0) / tot, 4) if tot else None
    return {'layers': int(len(truth)), 'overlap_len_m': round(total, 1),
            'lith_accuracy': round(good / total, 4) if total else None,
            'recall': recall,
            'confusion': {k: {kk: round(vv, 1) for kk, vv in v.items() if vv} for k, v in cm.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description='岩性一致率验证')
    ap.add_argument('--well', default=None)
    ap.add_argument('--profile', default=None)
    ap.add_argument('--proc', default=None)
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'acceptance'))
    ap.add_argument('--col', default='LITHOLOGY', help='LITHOLOGY 或 LITHOLOGY_ML')
    args = ap.parse_args(argv)
    if args.well:
        spec = WELL_PROFILES.get(args.well)
        if not spec:
            print('未知井:', args.well); return 1
        prof = spec['profile']
        proc = args.proc or next((p for p in spec['proc'] if os.path.exists(p)), None)
    else:
        prof, proc = args.profile, args.proc
    if not prof or not proc or not os.path.exists(prof) or not os.path.exists(proc):
        print('缺文件: profile=%s proc=%s' % (prof, proc)); return 1
    truth = load_profile(prof)
    res = evaluate(proc, truth, col=args.col)
    res['well'] = args.well or os.path.basename(prof)
    print(json.dumps({k: v for k, v in res.items() if k != 'confusion'}, ensure_ascii=False, indent=2))
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'lith_%s.json' % (args.well or 'well'))
    json.dump(res, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('saved:', path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
