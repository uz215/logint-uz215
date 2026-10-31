# -*- coding: utf-8 -*-
"""井内流体标定（wellcal）：用该井真值层表训练模型 → 保存 → 应用到全井 → 生成层表。

设计（对应用户"不限图版，只要分清油气水"+ 按井标定）：
  fit  : 真值层表(试油/分层成果) + 成果 CSV → 随机森林/决策树，5 段分块 CV 报告精度
         → 模型保存 data/calibration/models/<well>.joblib，元数据 <well>.json（特征/中位数/规则/CV）
  apply: 加载模型 → 预测全井逐点 → FLUID_ML / FLUID_ML_CONF
         → logsys.layers.build_layers 聚合 → <well>_ML_layers.csv
  eval : 用分块 CV 的 out-of-fold 预测做层级对比（避免训练泄漏）

用法：
  python -m logsys.wellcal fit   --well BET-1
  python -m logsys.wellcal apply --well BET-1
  python -m logsys.wellcal all   --wells BET-1,TrakesKE-1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.tree import DecisionTreeClassifier, export_text

from .calibrate import load_truths
from .layers import build_layers

CAND_FEATS = ['GR', 'PHI', 'SW_COMP', 'SW_LOG', 'LOG_RT', 'VSH', 'LOG_TG', 'PLATE_NUM']
FEATS = ['GR', 'PHI', 'SW_COMP', 'SW_LOG', 'LOG_RT', 'VSH']  # 兼容旧模型
LABELS = ['GAS', 'OIL', 'WATER', 'TIGHT']
CLASS_TO_LAYER = {'GAS': 'GAS', 'OIL': 'OIL', 'WATER': 'WATER', 'TIGHT': 'NonReservoir'}


def postprocess(pred: np.ndarray, raw: pd.DataFrame, proba=None) -> np.ndarray:
    """证据后处理：把明显的水/气从"默认 OIL"中纠出来。

    raw 需含列：SW_LOG、LOG_TG、PLATE_NUM、PHI（可缺，缺则跳过对应规则）。
    """
    out = np.array(pred, dtype=object)
    def col(name):
        return raw[name].values if name in raw.columns else np.full(len(out), np.nan)
    sw_log = col('SW_LOG'); log_tg = col('LOG_TG'); plate = col('PLATE_NUM'); phi = col('PHI')
    sw_log = np.where(np.isnan(sw_log), 0.0, sw_log)
    log_tg = np.where(np.isnan(log_tg), 0.0, log_tg)  # 0 = 无气测
    has_tg = col('LOG_TG') == col('LOG_TG')
    tg = np.where(has_tg, 10 ** np.nan_to_num(log_tg), -1.0)
    is_oil_like = out == 'OIL'
    # 水层：可动水饱和度高 + 气测很低（<5000ppm）
    water = is_oil_like & (sw_log >= 0.85) & (tg >= 0) & (tg < 5000)
    # 气层：图版判 GAS（PLATE_NUM=2）
    gas = is_oil_like & (plate == 2.0)
    out[water] = 'WATER'
    out[gas] = 'GAS'
    return out
MODEL_DIR = os.path.join(r'D:\360\src', 'data', 'calibration', 'models')


# --------------------------------------------------------------------- #
# 数据
# --------------------------------------------------------------------- #
def load_all_points(csv_path: str) -> pd.DataFrame:
    d = pd.read_csv(csv_path, low_memory=False)

    def num(*names):
        for n in names:
            if n in d.columns:
                s = pd.to_numeric(d[n], errors='coerce')
                if s.notna().sum() > 10:
                    return s
        return pd.Series(np.nan, index=d.index)

    md = num('MD', 'DEPTH', 'DEPT')
    sw_log = num('SW')
    sw_log = np.where(sw_log > 1.5, sw_log / 100.0, sw_log)
    out = pd.DataFrame({
        'MD': md,
        'GR': num('GR', 'GR_NOU', 'CGR'),
        'PHI': num('PHI', 'POR'),
        'SW_COMP': num('Sw'),
        'SW_LOG': pd.Series(sw_log, index=d.index),
        'RT': num('RT', 'RD', 'LLD'),
        'VSH': num('VSH', 'VSHALE'),
        'LITHOLOGY': d['LITHOLOGY'].astype(str) if 'LITHOLOGY' in d.columns else '',
    })
    out['LOG_RT'] = np.log10(out['RT'].clip(lower=1e-3))
    # 气测 TG（可来自成果 CSV 或 registry 指定气测文件）
    tg = None
    if 'TG' in d.columns:
        tg = pd.to_numeric(d['TG'], errors='coerce')
    out['LOG_TG'] = np.log10(pd.Series(tg, index=d.index).clip(lower=1.0)) if tg is not None else np.nan
    # 图版证据（PLATE_FLUID → 数值）
    if 'PLATE_FLUID' in d.columns:
        pmap = {'GAS': 2.0, 'OIL': 1.0, 'DRY': 0.0}
        out['PLATE_NUM'] = d['PLATE_FLUID'].astype(str).str.upper().map(pmap)
    else:
        out['PLATE_NUM'] = np.nan
    out['_ROW'] = np.arange(len(out))
    return out


def attach_gas_tg(pts: pd.DataFrame, gas_file: str) -> pd.DataFrame:
    """按 MD 最近邻把气测 TG 合并到逐点表（仅当 CSV 无 TG 时使用）。"""
    try:
        g = pd.read_csv(gas_file, sep='\t', header=0, low_memory=False)
    except Exception:
        try:
            g = pd.read_csv(gas_file, sep=r'\s+', header=0, low_memory=False)
        except Exception:
            return pts
    cols = {str(c).strip().upper(): c for c in g.columns}
    md_c = next((cols[k] for k in cols if k.startswith('MD') or 'DEPTH' in k), None)
    tg_c = next((cols[k] for k in cols if k.startswith('TG')), None)
    if tg_c is None:
        tg_c = next((cols[k] for k in cols if k == 'C1'), None)
    if not md_c or not tg_c:
        return pts
    g = pd.DataFrame({'MD': pd.to_numeric(g[md_c], errors='coerce').astype(float),
                      'TG': pd.to_numeric(g[tg_c], errors='coerce')}).dropna(subset=['MD']).sort_values('MD')
    left = pts[['MD']].copy()
    left['_i'] = np.arange(len(left))
    left['MD'] = pd.to_numeric(left['MD'], errors='coerce').astype(float)
    left = left.dropna(subset=['MD']).sort_values('MD')
    merged = pd.merge_asof(left, g, on='MD', direction='nearest', tolerance=1.0)
    out = pts.copy()
    out['LOG_TG'] = np.nan
    idx = merged['_i'].values
    out.loc[idx, 'LOG_TG'] = np.log10(merged['TG'].clip(lower=1.0).values)
    return out


def label_by_truth(pts: pd.DataFrame, truth: pd.DataFrame) -> pd.Series:
    lab = np.array(['NONE'] * len(pts), dtype=object)
    md = pts['MD'].values
    for _, r in truth.iterrows():
        m = (md >= r['TOP']) & (md < r['BASE'])
        lab[m] = r['FLUID']
    return pd.Series(lab, index=pts.index)


def _impute(df: pd.DataFrame, medians: dict) -> pd.DataFrame:
    out = df[FEATS].copy()
    for c in FEATS:
        out[c] = out[c].fillna(medians.get(c, 0.0))
    return out


# --------------------------------------------------------------------- #
# fit / apply
# --------------------------------------------------------------------- #
def fit_well(spec: dict) -> dict:
    pts = load_all_points(spec['proc'])
    if spec.get('gas_file') and pts['LOG_TG'].notna().sum() < 10:
        pts = attach_gas_tg(pts, spec['gas_file'])
    truth = load_truths(spec['truth'], spec['truth_kind'])
    pts['TRUTH'] = label_by_truth(pts, truth)
    mixed_as = str(spec.get('mixed_as') or '').upper()
    if mixed_as in ('GAS', 'OIL', 'WATER'):
        pts.loc[pts['TRUTH'] == 'MIXED', 'TRUTH'] = mixed_as
    train = pts[(pts['TRUTH'] != 'NONE') & (pts['TRUTH'] != 'MIXED')].copy()
    if len(train) < 30:
        raise RuntimeError('样本太少: %d' % len(train))
    # 类权重：balanced × 指定倍数（少数类补强）
    boost = {str(k).upper(): float(v) for k, v in (spec.get('class_boost') or {}).items()}
    counts = train['TRUTH'].value_counts().to_dict()
    n_all = len(train); k_cls = max(len(counts), 1)
    cap = float(spec.get('weight_cap', 2.0))
    class_weight = {}
    for c, cnt in counts.items():
        w = (n_all / (k_cls * cnt)) * boost.get(c, 1.0)
        if cnt < 20:          # 极小类不可靠，不加权
            w = 1.0
        class_weight[c] = min(w, cap * max(boost.get(c, 1.0), 1.0))
    print('  类权重:', {k: round(v, 2) for k, v in class_weight.items()}, flush=True)

    # 动态特征选择：覆盖率 >=30% 且非常数
    feats = []
    for c in CAND_FEATS:
        if c not in train.columns:
            continue
        cov = float(train[c].notna().mean())
        if cov >= 0.30 and float(train[c].std(skipna=True) or 0.0) > 1e-9:
            feats.append(c)
    if 'GR' not in feats:
        feats.insert(0, 'GR')
    print('  特征:', feats, flush=True)
    medians = {c: float(train[c].median()) if np.isfinite(train[c].median()) else 0.0 for c in feats}
    X = _impute(train[feats].assign(**{c: train[c] for c in feats if c not in train.columns}), medians) \
        if False else train[feats].fillna(pd.Series(medians))
    y = train['TRUTH'].values
    n = len(train)

    # ---- 5 段分块 CV（按深度切，防泄漏）----
    order = np.argsort(train['MD'].values)
    folds = np.array_split(order, 5)
    oof = np.array([''] * n, dtype=object)
    for i in range(5):
        te = folds[i]
        tr = np.concatenate([folds[j] for j in range(5) if j != i])
        m = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=20,
                                   class_weight=class_weight, random_state=0, n_jobs=-1)
        m.fit(X.iloc[tr], y[tr])
        _raw_te = train.iloc[te][[c for c in ('SW_LOG', 'LOG_TG', 'PLATE_NUM', 'PHI') if c in train.columns]]
        oof[te] = postprocess(m.predict(X.iloc[te]), _raw_te)
    mask = oof != ''
    acc_all = accuracy_score(y[mask], oof[mask])
    hc = np.isin(y, ['GAS', 'OIL', 'WATER'])
    acc_hc = accuracy_score(y[mask & hc], oof[mask & hc]) if (mask & hc).any() else float('nan')
    cm = confusion_matrix(y[mask], oof[mask], labels=LABELS).tolist()

    # ---- 全量训练最终模型 ----
    model = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=20,
                                   class_weight=class_weight, random_state=0, n_jobs=-1)
    model.fit(X, y)
    dt = DecisionTreeClassifier(max_depth=6, min_samples_leaf=25,
                                class_weight=class_weight, random_state=0)
    dt.fit(X, y)
    rules = export_text(dt, feature_names=feats, decimals=3)

    os.makedirs(MODEL_DIR, exist_ok=True)
    import joblib
    model_path = os.path.join(MODEL_DIR, spec['well'] + '.joblib')
    oof_map = {int(train['_ROW'].iloc[i]): str(oof[i]) for i in range(n)}
    joblib.dump({'model': model, 'features': feats, 'medians': medians,
                 'oof': oof_map}, model_path)
    meta = {'well': spec['well'], 'n_train': int(n), 'features': feats, 'medians': medians,
            'cv5': {'acc_all': round(float(acc_all), 4), 'acc_hc': round(float(acc_hc), 4),
                    'confusion': cm, 'labels': LABELS},
            'rules_dt': rules, 'model_path': model_path}
    meta_path = os.path.join(MODEL_DIR, spec['well'] + '.json')
    json.dump(meta, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('  %-12s 训练点=%d  CV5 总体=%.1f%% 气/油/水=%.1f%%  -> %s' % (
        spec['well'], n, 100 * acc_all, 100 * acc_hc, model_path), flush=True)
    return meta


def _smooth_labels(pred: np.ndarray, win: int = 5) -> np.ndarray:
    """多数票平滑（窗口 5）：避免逐点抖动导致层表爆炸。"""
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


def apply_well(spec: dict, out_dir: str, use_oof: bool = False) -> dict:
    import joblib
    model_path = os.path.join(MODEL_DIR, spec['well'] + '.joblib')
    if not os.path.exists(model_path):
        raise RuntimeError('模型不存在，请先 fit: ' + model_path)
    pack = joblib.load(model_path)
    model, medians = pack['model'], pack['medians']

    pts = load_all_points(spec['proc'])
    feats = pack.get('features') or FEATS
    X = pts[feats].fillna(pd.Series(medians))
    pred = model.predict(X)
    raw_cols = [c for c in ('SW_LOG', 'LOG_TG', 'PLATE_NUM', 'PHI') if c in pts.columns]
    pred = postprocess(pred, pts[raw_cols])
    if use_oof:
        oof = pack.get('oof', {})
        n_oof = 0
        for i in range(len(pred)):
            r = int(pts['_ROW'].iloc[i])
            if r in oof:
                pred[i] = oof[r]
                n_oof += 1
        print('  (eval 模式：使用 %d 个 out-of-fold 预测)' % n_oof, flush=True)
    pred = _smooth_labels(pred, win=5)
    proba = model.predict_proba(X).max(axis=1) if hasattr(model, 'predict_proba') else np.ones(len(X))
    # 关键特征缺失的点不外推（避免在无数据段凭空造层）：标 UNKNOWN，层表跳过
    valid = pts[['PHI', 'SW_COMP']].notna().any(axis=1).values & pts['MD'].notna().values
    pred = np.where(valid, pred, 'UNKNOWN')

    out = pts.copy()
    out['FLUID_ML'] = pred
    out['FLUID_ML_CONF'] = np.round(proba, 3)
    out['INTERPRETATION_ML'] = [CLASS_TO_LAYER.get(p, '') for p in pred]

    # ---- 层表 ----
    lay_input = out[['MD', 'INTERPRETATION_ML']].rename(columns={'INTERPRETATION_ML': 'INTERPRETATION'})
    layers = build_layers(lay_input, min_thick=0.4 if spec.get('unit', 'm') == 'm' else 1.3,
                          thin_absorb=0.6 if spec.get('unit', 'm') == 'm' else 2.0,
                          gap_break=0.5 if spec.get('unit', 'm') == 'm' else 1.6)
    os.makedirs(out_dir, exist_ok=True)
    lp = os.path.join(out_dir, spec['well'] + '_ML_layers.csv')
    if len(layers):
        layers.to_csv(lp, index=False, encoding='utf-8-sig')
    pp = os.path.join(out_dir, spec['well'] + '_ML_points.csv')
    out[['MD', 'FLUID_ML', 'FLUID_ML_CONF']].to_csv(pp, index=False, encoding='utf-8-sig')
    dist = pd.Series(pred).value_counts().to_dict()
    print('  %-12s 应用点=%d 分布=%s 层数=%d -> %s' % (
        spec['well'], len(out), dist, len(layers), lp), flush=True)
    return {'well': spec['well'], 'points': int(len(out)), 'layers': int(len(layers)),
            'dist': {k: int(v) for k, v in dist.items()}, 'layers_csv': lp}


# --------------------------------------------------------------------- #
# 层级评估（与真值重叠加权）
# --------------------------------------------------------------------- #
def eval_layers(spec: dict, layers_csv: str) -> dict:
    truth = load_truths(spec['truth'], spec['truth_kind'])
    ours = pd.read_csv(layers_csv)
    ours['O'] = ours['INTERPRETATION'].astype(str).str.upper().replace(
        {'NONRESERVOIR': 'TIGHT', 'DRY': 'TIGHT'})
    total = 0.0
    good = 0.0
    for _, tr in truth.iterrows():
        ov = np.minimum(tr['BASE'], ours['BASE_MD']) - np.maximum(tr['TOP'], ours['TOP_MD'])
        ov = ov.clip(lower=0)
        if len(ov) == 0:
            continue
        w = float(ov.max())
        if w <= 0:
            continue
        total += w
        o = ours.iloc[int(ov.idxmax())]['O']
        if o == tr['FLUID']:
            good += w
    return {'well': spec['well'], 'overlap_ft_or_m': round(total, 1),
            'layer_agree': round(good / total, 4) if total else 0.0}


def main(argv=None):
    ap = argparse.ArgumentParser(description='井内流体标定（fit/apply/eval/all）')
    ap.add_argument('cmd', choices=['fit', 'apply', 'eval', 'all'])
    ap.add_argument('--registry', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       'calibrate_wells.json'))
    ap.add_argument('--wells', default=None, help='逗号分隔；缺省=registry 全部')
    ap.add_argument('--out', default=r'D:\360\src\data\calibration\out')
    ap.add_argument('--eval', action='store_true', help='apply 时用 out-of-fold 预测做诚实评估')
    args = ap.parse_args(argv)
    specs = json.load(open(args.registry, encoding='utf-8'))
    if args.wells:
        want = [w.strip() for w in args.wells.split(',') if w.strip()]
        specs = [s for s in specs if s['well'] in want]

    results = []
    for s in specs:
        print('==== %s ====' % s['well'], flush=True)
        try:
            if args.cmd in ('fit', 'all'):
                fit_well(s)
            if args.cmd in ('apply', 'all'):
                r = apply_well(s, args.out, use_oof=args.eval)
                e = eval_layers(s, r['layers_csv'])
                r.update(e)
                results.append(r)
        except Exception as e:
            print('  FAILED: %s: %s' % (type(e).__name__, e), flush=True)
    if results:
        print('\n%-14s %8s %10s %12s' % ('well', 'layers', 'layer一致', 'overlap'))
        for r in results:
            print('%-14s %8d %9.1f%% %12.1f' % (
                r['well'], r['layers'], 100 * r.get('layer_agree', 0), r.get('overlap_ft_or_m', 0)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
