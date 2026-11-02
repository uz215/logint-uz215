# -*- coding: utf-8 -*-
"""数据驱动流体分类（用户指示：不限图版/方法，只要分清油气水）。

做法：
  1. 用有真值层表的井（BET-1 / TrakesKE-1 / RASHIDPUR_13）构造逐点样本；
  2. 特征只用解释流程可获得的列：GR、PHI、Sw(计算)、SW(测井)、RT、log10(RT)、VSH；
  3. 决策树（可解释）训练，并做**留一井验证**（train 2 wells → test 1 well），
     衡量跨井泛化能力（比单井自标定更接近验收要求）；
  4. 导出树规则文本，便于人工审阅/转成规则配置。

用法：
  python -m logsys.fluidml --registry logsys/calibrate_wells.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix

from .calibrate import load_truths, DEFAULT_CUTOFFS

FEATS = ['GR', 'PHI', 'SW_COMP', 'SW_LOG', 'LOG_RT', 'VSH']
LABELS = ['GAS', 'OIL', 'WATER', 'TIGHT']


def load_well(spec: dict) -> pd.DataFrame:
    d = pd.read_csv(spec['proc'], low_memory=False)

    def num(*names):
        for n in names:
            if n in d.columns:
                s = pd.to_numeric(d[n], errors='coerce')
                if s.notna().sum() > 10:
                    return s
        return pd.Series(np.nan, index=d.index)

    md = num('MD', 'DEPTH', 'DEPT')
    gr = num('GR', 'GR_NOU', 'CGR')
    phi = num('PHI', 'POR')
    sw_comp = num('Sw')
    sw_log = num('SW')
    # SW 列可能是百分数
    sw_log = np.where(sw_log > 1.5, sw_log / 100.0, sw_log)
    sw_log = pd.Series(sw_log, index=d.index)
    rt = num('RT', 'RD', 'LLD')
    vsh = num('VSH', 'VSHALE')
    out = pd.DataFrame({'MD': md, 'GR': gr, 'PHI': phi, 'SW_COMP': sw_comp,
                        'SW_LOG': sw_log, 'RT': rt, 'VSH': vsh})
    out['LOG_RT'] = np.log10(out['RT'].clip(lower=1e-3))

    truth = load_truths(spec['truth'], spec['truth_kind'])
    lab = np.array(['NONE'] * len(out), dtype=object)
    mdv = out['MD'].values
    for _, r in truth.iterrows():
        m = (mdv >= r['TOP']) & (mdv < r['BASE'])
        lab[m] = r['FLUID']
    out['TRUTH'] = lab
    out['WELL'] = spec['well']
    out = out[(out['TRUTH'] != 'NONE') & (out['TRUTH'] != 'MIXED')].copy()
    # 特征缺失用该井中位数填充，避免整行丢弃
    for c in FEATS:
        med = out[c].median()
        out[c] = out[c].fillna(med if np.isfinite(med) else 0.0)
    return out


def build(specs: list) -> pd.DataFrame:
    parts = []
    for s in specs:
        try:
            parts.append(load_well(s))
            print('  %s: %d labeled points' % (s['well'], len(parts[-1])), flush=True)
        except Exception as e:
            print('  %s FAILED: %s: %s' % (s['well'], type(e).__name__, e), flush=True)
    return pd.concat(parts, ignore_index=True)


def evaluate_loo(df: pd.DataFrame, model_factory=None):
    model_factory = model_factory or (lambda: DecisionTreeClassifier(
        max_depth=6, min_samples_leaf=25, class_weight='balanced', random_state=0))
    wells = sorted(df['WELL'].unique())
    rows = []
    for w in wells:
        tr = df[df['WELL'] != w]
        te = df[df['WELL'] == w]
        if te['TRUTH'].nunique() < 1:
            continue
        m = model_factory()
        m.fit(tr[FEATS], tr['TRUTH'])
        pred = m.predict(te[FEATS])
        acc = accuracy_score(te['TRUTH'], pred)
        hc = te['TRUTH'].isin(['GAS', 'OIL', 'WATER'])
        acc_hc = accuracy_score(te.loc[hc, 'TRUTH'], pred[hc.values]) if hc.any() else float('nan')
        cm = confusion_matrix(te['TRUTH'], pred, labels=LABELS)
        rows.append({'well': w, 'n': int(len(te)), 'acc_all': round(float(acc), 4),
                     'acc_hc': round(float(acc_hc), 4),
                     'truth_dist': te['TRUTH'].value_counts().to_dict(),
                     'cm': cm.tolist()})
    return rows




def evaluate_per_well_cv(df: pd.DataFrame, model_factory=None, k: int = 5):
    """井内分块交叉验证（按深度切成 k 段，train k-1 段 → test 1 段）。

    比随机切分更严格（避免同层泄漏），衡量"同一口井标定后可达到的精度"。
    """
    model_factory = model_factory or (lambda: DecisionTreeClassifier(
        max_depth=6, min_samples_leaf=25, class_weight='balanced', random_state=0))
    rows = []
    for w in sorted(df['WELL'].unique()):
        sub = df[df['WELL'] == w].sort_values('MD').reset_index(drop=True)
        if len(sub) < 50:
            continue
        folds = np.array_split(np.arange(len(sub)), k)
        pred = pd.Series(index=sub.index, dtype=object)
        for i in range(k):
            te_idx = folds[i]
            tr_idx = np.concatenate([folds[j] for j in range(k) if j != i])
            tr, te = sub.iloc[tr_idx], sub.iloc[te_idx]
            if te['TRUTH'].nunique() < 1:
                continue
            m = model_factory()
            m.fit(tr[FEATS], tr['TRUTH'])
            pred.loc[te_idx] = m.predict(te[FEATS])
        mask = pred.notna()
        acc = accuracy_score(sub.loc[mask, 'TRUTH'], pred[mask])
        hc = sub.loc[mask, 'TRUTH'].isin(['GAS', 'OIL', 'WATER'])
        acc_hc = accuracy_score(sub.loc[mask & hc, 'TRUTH'], pred[mask & hc]) if hc.any() else float('nan')
        rows.append({'well': w, 'n': int(mask.sum()), 'acc_all': round(float(acc), 4),
                     'acc_hc': round(float(acc_hc), 4)})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description='跨井留一验证的流体决策树')
    ap.add_argument('--registry', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       'calibrate_wells.json'))
    ap.add_argument('--out', default=r'D:\360\src\data\calibration')
    args = ap.parse_args(argv)
    specs = json.load(open(args.registry, encoding='utf-8'))
    print('构建数据集...', flush=True)
    df = build(specs)
    print('总样本 %d，分布 %s' % (len(df), df['TRUTH'].value_counts().to_dict()), flush=True)

    res = {}
    for name, factory in (('decision_tree', None),
                          ('random_forest', lambda: RandomForestClassifier(
                              n_estimators=200, max_depth=8, min_samples_leaf=20,
                              class_weight='balanced', random_state=0, n_jobs=-1))):
        rows = evaluate_loo(df, factory)
        res[name] = rows
        print('\n=== %s（留一井）===' % name)
        print('%-14s %6s %9s %9s' % ('held-out井', 'n', '总体', '气/油/水'))
        for r in rows:
            print('%-14s %6d %8.1f%% %8.1f%%' % (r['well'], r['n'], 100 * r['acc_all'], 100 * r['acc_hc']))
        avg = float(np.mean([r['acc_hc'] for r in rows])) if rows else 0
        print('平均气/油/水一致率: %.1f%%' % (100 * avg))

    print('\n=== 井内分块交叉验证（每口井单独标定）===')
    print('%-14s %6s %9s %9s' % ('井', 'n', '总体', '气/油/水'))
    cv_res = {}
    for name, factory in (('decision_tree', None),
                          ('random_forest', lambda: RandomForestClassifier(
                              n_estimators=200, max_depth=8, min_samples_leaf=20,
                              class_weight='balanced', random_state=0, n_jobs=-1))):
        rows = evaluate_per_well_cv(df, factory)
        cv_res[name] = rows
        print('-- %s' % name)
        for r in rows:
            print('%-14s %6d %8.1f%% %8.1f%%' % (r['well'], r['n'], 100 * r['acc_all'], 100 * r['acc_hc']))
    res['per_well_cv'] = cv_res

    # 全量训练 + 规则导出（供人工审阅/转规则）
    m = DecisionTreeClassifier(max_depth=6, min_samples_leaf=25, class_weight='balanced', random_state=0)
    m.fit(df[FEATS], df['TRUTH'])
    rules = export_text(m, feature_names=FEATS, decimals=3)
    print('\n=== 决策树规则（全量训练）===')
    print(rules)

    os.makedirs(args.out, exist_ok=True)
    json.dump({'samples': int(len(df)), 'features': FEATS, 'loo': res,
               'rules': rules}, open(os.path.join(args.out, 'fluidml.json'), 'w',
                                     encoding='utf-8'), ensure_ascii=False, indent=2)
    print('\nsaved:', os.path.join(args.out, 'fluidml.json'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
