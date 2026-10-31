# -*- coding: utf-8 -*-
"""岩性井内标定（lithcal）：用承包商岩性解释剖面训练/验证/应用岩性分类。

用户 2026-10-31：流体规则先冻结，岩性单独推进。
做法与 wellcal 类似：ExtraTrees，5 段分块 CV（按深度），输出诚实精度；
apply 时全井预测 + 深度多数票平滑，生成 LITHOLOGY_ML 列（写 processed_lithML.csv）。

用法：
    python -m logsys.lithcal fit   --well TrakesKE-1
    python -m logsys.lithcal apply --well TrakesKE-1
    python -m logsys.lithcal all   --wells TrakesKE-1
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score, confusion_matrix

from .lith_validate import WELL_PROFILES, load_profile, norm_lith, MERGE_LITH

BASE = r'D:\360\src'
MODEL_DIR = os.path.join(BASE, 'data', 'calibration', 'lith_models')
OUT_DIR = os.path.join(BASE, 'data', 'calibration', 'lith_out')

BASE_FEATS = ['GR', 'VSH', 'VSH_GR', 'RHOB', 'CNL', 'PE', 'DT', 'SP', 'CAL', 'PHI', 'POR',
             'PERM', 'SW', 'SGR', 'CGR', 'THOR', 'URAN', 'POTA', 'LITH_MC_CONF']
# 滚动窗口（±5 点均值/标准差、±15 点均值）——2026-10-31 验证点级 CV +0.5pp
ROLL_BASE = ('GR', 'VSH', 'RHOB', 'CNL', 'PE', 'DT')


def _features(d: pd.DataFrame) -> tuple:
    """构造特征矩阵：基础曲线 + 滚动窗口统计，返回 (X, 列名)。"""
    feats = [c for c in BASE_FEATS if c in d.columns]
    X = d[feats].apply(pd.to_numeric, errors='coerce').copy()
    for c in ROLL_BASE:
        if c not in X.columns:
            continue
        s = X[c]
        X[c + '_M11'] = s.rolling(11, center=True, min_periods=3).mean()
        X[c + '_S11'] = s.rolling(11, center=True, min_periods=3).std()
        X[c + '_M31'] = s.rolling(31, center=True, min_periods=5).mean()
    return X, list(X.columns)
MERGE = MERGE_LITH


def _load_data(proc_csv: str, prof_xlsx: str):
    d = pd.read_csv(proc_csv, low_memory=False)
    md = pd.to_numeric(d['MD'], errors='coerce')
    prof = load_profile(prof_xlsx)
    truth = np.array([''] * len(d), dtype=object)
    for _, r in prof.iterrows():
        m = (md >= r['TOP']) & (md < r['BASE'])
        truth[m.values] = r['LITH']
    y = np.array([MERGE.get(t, t) if t else '' for t in truth], dtype=object)
    X, feats = _features(d)
    valid = (y != '') & (np.char.str_len(y.astype(str)) > 0)
    Xv = X[valid].fillna(X[valid].median()).values
    return d, md, y, Xv, feats, valid


def fit_well(well: str, prof_xlsx: str, proc_csv: str) -> dict:
    d, md, y, X, feats, valid = _load_data(proc_csv, prof_xlsx)
    yv = y[valid]; mdv = md[valid].values
    order = np.argsort(mdv)
    folds = np.array_split(order, 5)
    oof = np.array([''] * len(yv), dtype=object)
    for i in range(5):
        te = folds[i]
        tr = np.concatenate([folds[j] for j in range(5) if j != i])
        clf = ExtraTreesClassifier(n_estimators=500, max_depth=None, min_samples_leaf=2,
                                   class_weight='balanced', random_state=0, n_jobs=-1)
        clf.fit(X[tr], yv[tr])
        oof[te] = clf.predict(X[te])
    acc = float(accuracy_score(yv, oof))
    labels = sorted(set(yv))
    cm = confusion_matrix(yv, oof, labels=labels).tolist()
    # 全量训练最终模型
    clf = ExtraTreesClassifier(n_estimators=500, max_depth=None, min_samples_leaf=2,
                               class_weight='balanced', random_state=0, n_jobs=-1)
    clf.fit(X, yv)
    os.makedirs(MODEL_DIR, exist_ok=True)
    import joblib
    mp = os.path.join(MODEL_DIR, well + '.joblib')
    joblib.dump({'model': clf, 'features': feats, 'medians': dict(
        zip(feats, np.nanmedian(X, axis=0))), 'classes': labels}, mp)
    meta = {'well': well, 'n_points': int(len(yv)), 'features': feats,
            'cv5_acc': round(acc, 4), 'labels': labels,
            'confusion': cm, 'model_path': mp,
            'classes_found': {k: int(v) for k, v in pd.Series(yv).value_counts().items()}}
    json.dump(meta, open(os.path.join(MODEL_DIR, well + '.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('  %-12s 点=%d CV5岩性一致=%.1f%% -> %s' % (well, len(yv), 100 * acc, mp), flush=True)
    return meta


def set_data():
    """兼容占位（保持模块接口与 wellcal 一致）。"""
    return None


def _smooth(pred: np.ndarray, win: int = 11) -> np.ndarray:
    if win <= 1 or len(pred) < win:
        return pred
    classes = sorted(set(pred))
    idx = {c: i for i, c in enumerate(classes)}
    code = np.array([idx[p] for p in pred], dtype=int)
    out = code.copy()
    half = win // 2
    for i in range(len(code)):
        seg = code[max(0, i - half): min(len(code), i + half + 1)]
        vals, cnt = np.unique(seg, return_counts=True)
        out[i] = vals[np.argmax(cnt)]
    return np.array([classes[i] for i in out], dtype=object)


def apply_well(well: str, proc_csv: str, out_dir: str = OUT_DIR) -> dict:
    import joblib
    mp = os.path.join(MODEL_DIR, well + '.joblib')
    if not os.path.exists(mp):
        return {'well': well, 'ok': False, 'reason': '无模型（先 fit）'}
    pack = joblib.load(mp)
    clf, feats, med = pack['model'], pack['features'], pack['medians']
    d = pd.read_csv(proc_csv, low_memory=False)
    X, _ = _features(d)
    X = X[feats].fillna(pd.Series(med)).values
    pred = clf.predict(X)
    pred = _smooth(np.asarray(pred, dtype=object), win=11)
    # 区域岩性约束（用户 2026-10-31）：不在区域允许集内的类别 → unknown
    try:
        from .region_lith import constrain, region_of_well
        _reg = region_of_well(well)
        if _reg:
            _before = len(set(pred))
            pred = constrain(pred, _reg)
            print('  区域约束(%s): 类别 %d -> %d' % (_reg, _before, len(set(pred))), flush=True)
    except Exception:
        pass
    out = d.copy()
    out['LITHOLOGY_ML'] = pred
    os.makedirs(out_dir, exist_ok=True)
    op = os.path.join(out_dir, well + '_processed_lithML.csv')
    out.to_csv(op, index=False, encoding='utf-8-sig')
    d_ = out['LITHOLOGY_ML'].value_counts().to_dict()
    print('  %-12s 应用点=%d 分布=%s -> %s' % (well, len(out), d_, op), flush=True)
    return {'well': well, 'ok': True, 'points': int(len(out)),
            'dist': {str(k): int(v) for k, v in d_.items()}, 'csv': op}


def evaluate_well(well: str, prof_xlsx: str, proc_lithML: str) -> dict:
    d = pd.read_csv(proc_lithML, low_memory=False)
    if 'LITHOLOGY_ML' not in d.columns:
        return {'well': well, 'ok': False, 'reason': '无 LITHOLOGY_ML'}
    md = pd.to_numeric(d['MD'], errors='coerce')
    prof = load_profile(prof_xlsx)
    step = float(np.nanmedian(np.diff(np.unique(md.dropna().values))))
    total = good = 0.0
    for _, r in prof.iterrows():
        m = (md >= r['TOP']) & (md < r['BASE'])
        if not m.any():
            continue
        w = float(m.sum()) * step
        vc = d.loc[m.values, 'LITHOLOGY_ML'].value_counts()
        pred = str(vc.index[0]) if len(vc) else ''
        total += w
        if MERGE.get(r['LITH'], r['LITH']) == pred:
            good += w
    acc = good / total if total else None
    print('  %-12s 岩性一致(ML) = %.1f%%（覆盖 %.0f m）' % (well, 100 * (acc or 0), total), flush=True)
    return {'well': well, 'ok': True, 'lith_accuracy': round(float(acc), 4) if acc else None,
            'overlap_m': round(total, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='岩性井内标定（fit/apply/all）')
    ap.add_argument('cmd', choices=['fit', 'apply', 'all'])
    ap.add_argument('--wells', default='TrakesKE-1')
    ap.add_argument('--out', default=OUT_DIR)
    args = ap.parse_args(argv)
    results = []
    for well in [w.strip() for w in args.wells.split(',') if w.strip()]:
        spec = WELL_PROFILES.get(well)
        if not spec:
            print(well, '未配置岩性剖面'); continue
        proc = next((p for p in spec['proc'] if os.path.exists(p)), None)
        if not proc:
            print(well, '无 processed.csv'); continue
        if args.cmd in ('fit', 'all'):
            fit_well(well, spec['profile'], proc)
        if args.cmd in ('apply', 'all'):
            r = apply_well(well, proc, args.out)
            if r.get('ok'):
                e = evaluate_well(well, spec['profile'], r['csv'])
                r.update(e)
                results.append(r)
    return 0


if __name__ == '__main__':
    sys.exit(main())
