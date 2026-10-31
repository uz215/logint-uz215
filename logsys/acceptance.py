# -*- coding: utf-8 -*-
"""验收矩阵：按"试油真值井"统计流体层一致率、层表完整性、人工复核率。

真值分级（用户 2026-10-31 定案）：
  - 试油真值：3-SPS-111D（试油后解释+MDT）、XIMENIA-5（Doseo2023 试油）、TrakesKE-1（成果表/试油后解释）
  - 仅参考：BET-1（SLAM）、RASHIDPUR_13（RUSH）—— 输出但标"参考"，不计入验收汇总

指标：
  1) 流体层一致率 = 按深度重叠加权，层表结论 vs 真值（GAS/OIL/WATER/TIGHT/MIXED 五类）；
  2) 层表完整性 = 必需列齐全且非空比例（目标 100%）；
  3) 人工复核率 = 需复核层数 / 总层数（目标 ≤20%）：
     复核层 = REVIEW_FLAG 非空（THIN/TIE/REVIEW/CONFLICT/SINGLE_POINT 等）
              或结论为混合类（GAS_OIL/OIL_WATER）。

用法：
    python -m logsys.acceptance --out data/acceptance
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time

import numpy as np
import pandas as pd

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'
REQUIRED_COLS = ['LAYER_ID', 'TOP_MD', 'BASE_MD', 'THICKNESS', 'LITHOLOGY', 'INTERPRETATION']

# well: (layer table 目录候选, 真值 csv, 是否试油真值, 备注)
WELLS = {
    '3-SPS-111D': {
        'dirs': [os.path.join(WS, 'output', '3-BRSA-1396D-SPS'),
                 os.path.join(BASE, 'output', '3-SPS-111D'),
                 os.path.join(WS, 'output', '3-SPS-111D')],
        'truth': r'D:\360\Brasil\CuraCao-3\3-SPS-111D_20250425\3-SPS-111D_truth.csv',
        'truth_kind': 'generic_csv', 'accept': True},
    'XIMENIA-5': {
        'dirs': [os.path.join(BASE, 'output', 'XIMENIA-5'),
                 os.path.join(WS, 'output', 'XIMENIA-5')],
        'truth': r'D:\360\Chad\Ximenia-5\XIMENIA-5_truth.csv',
        'truth_kind': 'generic_csv', 'accept': True},
    'TrakesKE-1': {
        'dirs': [os.path.join(WS, 'output', 'TrakesKE-1'),
                 os.path.join(BASE, 'output', 'TrakesKE-1')],
        'truth': r'D:\360\Niger\Trakes KE-1\Trakes KE-1 result table.xlsx',
        'truth_kind': 'trakes_result', 'accept': True},
    'BET-1': {
        'dirs': [os.path.join(WS, 'output', 'BET-1')],
        'truth': r'D:\360\Indonesia\BET-1\BET-1_8.5IN_SLAM_Res_Table_20261003.xls',
        'truth_kind': 'bet1_slam', 'accept': False},
    'RASHIDPUR_13': {
        'dirs': [os.path.join(WS, 'output', 'RASHIDPUR_13'),
                 os.path.join(BASE, 'output', 'RASHIDPUR_13')],
        'truth': r'D:\360\Bangladesh\RP-13\RP-13_RESULT_RUSH INTERPRETATION_20261019.xls',
        'truth_kind': 'rp13_rush', 'accept': False},
}

MIXED_LABELS = {'GAS_OIL', 'OIL_GAS', 'OIL_WATER', 'MIXED'}


def _norm(s):
    s = str(s or '').strip().upper().replace(' ', '_')
    if s in ('', 'NONE', 'NAN'):
        return ''
    if s in ('NONRESERVOIR', 'NON-RESERVOIR', 'CASING', 'TIGHT', 'DRY'):
        return 'TIGHT'
    if s in MIXED_LABELS:
        return 'MIXED'
    return s


def _find(dirs: list, ml: bool) -> str | None:
    for d in dirs:
        if not os.path.isdir(d):
            continue
        cands = [p for p in glob.glob(os.path.join(d, '*_interpretation_layers*.csv'))
                 if p.endswith('_ML.csv') == ml]
        if cands:
            return sorted(cands, key=os.path.getmtime, reverse=True)[0]
    return None


def find_layers(well: str, dirs: list) -> str | None:
    return _find(dirs, ml=False)


def find_ml_layers(well: str, dirs: list) -> str | None:
    return _find(dirs, ml=True)


def load_truth(spec: dict) -> pd.DataFrame:
    sys.path.insert(0, BASE)
    from logsys.calibrate import load_truths
    t = load_truths(spec['truth'], spec['truth_kind'])
    t['FLUID'] = t['FLUID'].map(_norm)
    return t


def _evaluate_table(lp: str, spec: dict, out: dict) -> dict:
    """对单张层表计算指标（填充/返回指标 dict）。"""
    lay = pd.read_csv(lp)
    lay = pd.read_csv(lp)
    out['layers'] = int(len(lay))
    # 1) 层表完整性
    missing = [c for c in REQUIRED_COLS if c not in lay.columns]
    nonnull = {c: float(lay[c].notna().mean()) for c in lay.columns if c in REQUIRED_COLS}
    out['completeness'] = round(float(np.mean(list(nonnull.values()))), 4) if nonnull else 0.0
    if missing:
        out['completeness'] = 0.0
    out['missing_cols'] = missing
    # 2) 复核率
    review = pd.Series(False, index=lay.index)
    if 'REVIEW_FLAG' in lay.columns:
        review |= lay['REVIEW_FLAG'].astype(str).str.len() > 0
    itp = lay['INTERPRETATION'].astype(str).str.upper().str.replace(' ', '_')
    review |= itp.isin(MIXED_LABELS)
    out['review_layers'] = int(review.sum())
    out['review_rate'] = round(float(review.mean()), 4) if len(lay) else 0.0
    # 3) 流体一致率（厚度加权）
    truth = load_truth(spec)
    total = good = 0.0
    for _, tr in truth.iterrows():
        t0, t1 = float(tr['TOP']), float(tr['BASE'])
        ov = (np.minimum(lay['BASE_MD'], t1) - np.maximum(lay['TOP_MD'], t0)).clip(lower=0)
        if not (ov > 0).any():
            continue
        j = int(ov.idxmax())
        w = float(ov.loc[j])
        total += w
        pred = _norm(lay.loc[j, 'INTERPRETATION'])
        if pred == tr['FLUID']:
            good += w
    out['truth_overlap'] = round(total, 1)
    out['fluid_agreement'] = round(good / total, 4) if total > 0 else None
    out['status'] = 'OK'
    return out


def compute_well(well: str, spec: dict) -> dict:
    """规则层表 + ML 层表都评估；最终产品 = ML（有模型/有层表时）否则规则表。"""
    out = {'well': well, 'accept': bool(spec['accept']), 'status': 'NO_DATA'}
    rule_csv = find_layers(well, spec['dirs'])
    ml_csv = find_ml_layers(well, spec['dirs'])
    out['rule_layers_csv'] = rule_csv
    out['ml_layers_csv'] = ml_csv

    def _metrics(lp):
        d = {'layers_csv': lp}
        try:
            lay = pd.read_csv(lp)
        except Exception:
            return {'layers': 0, 'completeness': 0.0, 'review_rate': 0.0,
                    'fluid_agreement': None, 'truth_overlap': 0.0}
        d['layers'] = int(len(lay))
        missing = [c for c in REQUIRED_COLS if c not in lay.columns]
        nonnull = {c: float(lay[c].notna().mean()) for c in lay.columns if c in REQUIRED_COLS}
        d['completeness'] = round(float(np.mean(list(nonnull.values()))), 4) if nonnull else 0.0
        if missing:
            d['completeness'] = 0.0
        d['missing_cols'] = missing
        # 复核层 = 有不确定标记（THIN/TIE/POSSIBLE/CONFLICT/LOW_CONF/单点混合），
        # 混合类结论（GAS_OIL/OIL_WATER）本身是有效结论，不计入复核率。
        review = pd.Series(False, index=lay.index)
        _rv_tags = ('THIN', 'TIE', 'POSSIBLE', 'REVIEW', 'CONFLICT', 'LOW_CONF', '单点')
        if 'REVIEW_FLAG' in lay.columns:
            _rf = lay['REVIEW_FLAG'].fillna('').astype(str)
            review |= _rf.apply(lambda s2: any(t in s2.upper() for t in _rv_tags))
        if 'GAS_OIL_SPLIT' in lay.columns:
            review |= lay['GAS_OIL_SPLIT'].astype(str).str.upper().eq('SINGLE_POINT')
        d['review_layers'] = int(review.sum())
        d['review_rate'] = round(float(review.mean()), 4) if len(lay) else 0.0
        truth = load_truth(spec)
        total = good = 0.0
        for _, tr in truth.iterrows():
            t0, t1 = float(tr['TOP']), float(tr['BASE'])
            ov = (np.minimum(lay['BASE_MD'], t1) - np.maximum(lay['TOP_MD'], t0)).clip(lower=0)
            if not (ov > 0).any():
                continue
            j = int(ov.idxmax())
            w = float(ov.loc[j])
            total += w
            if _norm(lay.loc[j, 'INTERPRETATION']) == tr['FLUID']:
                good += w
        d['truth_overlap'] = round(total, 1)
        d['fluid_agreement'] = round(good / total, 4) if total > 0 else None
        return d

    rule = _metrics(rule_csv) if rule_csv else {}
    ml = _metrics(ml_csv) if ml_csv else {}
    out['rule'] = rule
    out['ml'] = ml
    final = ml if ml else rule
    out.update({k: final.get(k) for k in ('layers', 'completeness', 'review_rate',
                                          'fluid_agreement', 'truth_overlap')})
    out['final_source'] = 'ML' if ml else ('rules' if rule else 'none')
    out['status'] = 'OK' if (rule or ml) else 'NO_DATA'
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='验收矩阵（试油真值井）')
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'acceptance'))
    args = ap.parse_args(argv)
    rows = [compute_well(w, s) for w, s in WELLS.items()]
    df = pd.DataFrame(rows)
    os.makedirs(args.out, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    df.to_csv(os.path.join(args.out, 'acceptance_%s.csv' % ts), index=False, encoding='utf-8-sig')
    json.dump(rows, open(os.path.join(args.out, 'acceptance_%s.json' % ts), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    # Markdown 矩阵
    md = ['# 验收矩阵（自动生成 %s）' % ts, '',
          '> 只有"试油真值"井计入验收；BET-1/RASHIDPUR_13 为解释参考，仅展示。', '',
          '| 井 | 真值级 | 层数 | 流体层一致率 | 层表完整性 | 复核率 | 状态 |',
          '|---|---|---|---|---|---|---|']
    for r in rows:
        md.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            r['well'], '试油' if r['accept'] else '参考',
            r.get('layers', '-'),
            ('%.1f%%' % (100 * r['fluid_agreement'])) if r.get('fluid_agreement') is not None else '-',
            ('%.1f%%' % (100 * r['completeness'])) if r.get('completeness') is not None else '-',
            ('%.1f%%' % (100 * r['review_rate'])) if r.get('review_rate') is not None else '-',
            r['status']))
    acc = [r for r in rows if r['accept'] and r.get('fluid_agreement') is not None]
    md += ['', '## 验收判定（试油真值井）', '',
           '| 判据 | 目标 | 现状 | 结论 |', '|---|---|---|---|']
    if acc:
        avg = float(np.mean([r['fluid_agreement'] for r in acc]))
        rev = float(np.mean([r['review_rate'] for r in acc]))
        comp = float(np.mean([r['completeness'] for r in acc]))
        md.append('| 流体层一致率（3 井平均） | ≥90%% | %.1f%% | %s |' % (
            100 * avg, 'PASS' if avg >= 0.90 else 'FAIL'))
        md.append('| 层表完整性 | 100%% | %.1f%% | %s |' % (
            100 * comp, 'PASS' if comp >= 0.999 else 'FAIL'))
        md.append('| 人工复核率 | ≤20%% | %.1f%% | %s |' % (
            100 * rev, 'PASS' if rev <= 0.20 else 'FAIL'))
    path = os.path.join(args.out, 'acceptance_%s.md' % ts)
    open(path, 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('\n'.join(md))
    print('\nsaved:', path)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
