# -*- coding: utf-8 -*-
"""气测图版引擎：逐点判别 → 按层聚合 → 与测井规则结论融合。

对外接口：
    load_config(path=None) -> dict
    evaluate_points(gas_df, cfg, depth_col='MD') -> DataFrame
    evaluate_layers(gas_df, layers, cfg, depth_col='MD') -> DataFrame
    fuse_with_log(plate_label, log_label, cfg) -> dict
    summarize(layer_df) -> dict

设计约束（2026-10-30 用户决策）：
- 气/油判定以气测解释图版为准，REG 不再作为终审；
- 图版无依据（缺重烃/缺数据）时**不强行把 GAS 改 OIL**，保留测井结论并标 REVIEW；
- 图版只回答"气/油/干"，水层与储层性仍由测井解释负责。
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from . import methods

_CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'gas_plate_default.json')


def load_config(path: str | None = None) -> dict:
    with open(path or _CFG_PATH, encoding='utf-8') as f:
        return json.load(f)


def evaluate_points(gas_df: pd.DataFrame, cfg: dict, depth_col: str = 'MD') -> pd.DataFrame:
    """逐点图版判别；返回与输入同索引的结果表。"""
    if gas_df is None or len(gas_df) == 0:
        return pd.DataFrame()
    df = gas_df
    missing = [c for c in cfg.get('required', ['C1', 'C2', 'C3']) if c not in df.columns]

    p = methods.pixler_classify(df, cfg)
    ratios = methods.pixler_ratios(df)
    th = methods.three_h(df, cfg)

    out = pd.DataFrame(index=df.index)
    if depth_col in df.columns:
        out[depth_col] = pd.to_numeric(df[depth_col], errors='coerce')
    out['PLATE_PIXLER'] = p['PIXLER']
    out['PLATE_CONF'] = p['PIXLER_CONF']
    out['PLATE_WHY'] = p['PIXLER_WHY']
    out['PLATE_VALID_RATIOS'] = p['PIXLER_VALID']
    out['PLATE_C1_C2'] = ratios['C1/C2']
    out['PLATE_C1_C3'] = ratios['C1/C3']
    out['PLATE_C1_C4'] = ratios['C1/C4']
    out['PLATE_RATIO_C1HEAVY'] = methods.ratio_c1_heavy(df, cfg)
    out['PLATE_RATIO_C2C3'] = methods.ratio_c2c3(df, cfg)
    out['PLATE_WH'] = th['WH']
    out['PLATE_BH'] = th['BH']
    out['PLATE_CH'] = th['CH']
    out['PLATE_THREE_H'] = th['THREE_H']
    out['PLATE_GAS_EVAL'] = methods.gas_eval_zones(df, cfg)
    out['PLATE_MISSING_CURVES'] = ','.join(missing)

    # 综合标签：Pixler 为主；3H 启用且一致时提升置信度
    label = out['PLATE_PIXLER'].copy()
    if cfg.get('three_h', {}).get('enabled'):
        agree = (label == out['PLATE_THREE_H']) & (label != 'UNDEFINED')
        out.loc[agree, 'PLATE_CONF'] = np.minimum(1.0, out.loc[agree, 'PLATE_CONF'] + 0.1)
    out['PLATE_FLUID'] = label
    return out


def _median_curve(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return np.nan
    s = pd.to_numeric(df[col], errors='coerce').dropna()
    return float(s.median()) if len(s) else np.nan


def evaluate_layers(gas_df: pd.DataFrame, layers, cfg: dict, depth_col: str = 'MD') -> pd.DataFrame:
    """按层聚合气测并判别。

    layers: DataFrame（含 TOP/BASE 或 top_m/base_m，否则取前两列）或 [(top, base), ...]。
    返回每层：中位烃组分、比值、PLATE_FLUID/PLATE_CONF/投票数/REVIEW。
    """
    if gas_df is None or len(gas_df) == 0:
        return pd.DataFrame()

    if isinstance(layers, pd.DataFrame):
        cols = list(layers.columns)
        top_col = 'TOP' if 'TOP' in cols else ('top_m' if 'top_m' in cols else cols[0])
        base_col = 'BASE' if 'BASE' in cols else ('base_m' if 'base_m' in cols else cols[1])
        segs = list(zip(pd.to_numeric(layers[top_col], errors='coerce'),
                        pd.to_numeric(layers[base_col], errors='coerce')))
        src_index = list(layers.index)
    else:
        segs = list(layers)
        src_index = list(range(len(segs)))

    if depth_col not in gas_df.columns:
        return pd.DataFrame()
    md = pd.to_numeric(gas_df[depth_col], errors='coerce')

    rows = []
    for (top, base), idx in zip(segs, src_index):
        if not (np.isfinite(top) and np.isfinite(base)) or base <= top:
            rows.append({'LAYER': idx, 'TOP': top, 'BASE': base, 'POINTS': 0,
                         'PLATE_FLUID': 'UNDEFINED', 'PLATE_CONF': 0.0, 'REVIEW': True,
                         'REVIEW_REASON': 'INVALID_INTERVAL'})
            continue
        m = (md >= top) & (md < base)
        sub = gas_df.loc[m]
        row = {'LAYER': idx, 'TOP': top, 'BASE': base, 'POINTS': int(m.sum())}
        for c in methods.HYDROCARBONS:
            row[f'MEDIAN_{c}'] = _median_curve(sub, c)

        # 逐点判别 + 层内多数票（优先）；层中位数只在逐点无法判别时兜底。
        # 原因（真实数据验证 2026-10-30）：中位数的比值 ≠ 比值的中位数
        # （如 C3 中位=0 会使 C1/C3 除零），直接用层中位数会把整层判成 UNDEFINED。
        sub_pt = evaluate_points(sub, cfg, depth_col=depth_col) if len(sub) else pd.DataFrame()
        label, conf = 'UNDEFINED', 0.0
        if len(sub_pt):
            valid = sub_pt['PLATE_FLUID'].isin(['GAS', 'OIL', 'DRY'])
            n_valid = int(valid.sum())
            if n_valid >= 3:
                vc = sub_pt.loc[valid, 'PLATE_FLUID'].value_counts()
                label = str(vc.idxmax())
                share = float(vc.max()) / n_valid
                _c = pd.to_numeric(sub_pt.loc[valid, 'PLATE_CONF'], errors='coerce').mean()
                _c = float(_c) if np.isfinite(_c) else 0.6
                conf = round(_c * (0.5 + 0.5 * share), 3)
                row['POINT_AGREE'] = round(share, 3)
            elif n_valid > 0:
                vc = sub_pt.loc[valid, 'PLATE_FLUID'].value_counts()
                label = str(vc.idxmax())
                conf = 0.3
            for k, lab in (('VOTE_GAS', 'GAS'), ('VOTE_OIL', 'OIL'),
                           ('VOTE_DRY', 'DRY'), ('VOTE_UNDEF', 'UNDEFINED')):
                row[k] = int((sub_pt['PLATE_FLUID'] == lab).sum())
        if label == 'UNDEFINED':
            # 兜底：层中位数判别（逐点全部无重烃/无数据时）
            med = pd.DataFrame({c: [row[f'MEDIAN_{c}']] for c in methods.HYDROCARBONS})
            pt = evaluate_points(med, cfg, depth_col=depth_col)
            if len(pt):
                label = str(pt['PLATE_FLUID'].iloc[0])
                conf = float(pt['PLATE_CONF'].iloc[0])
        row['PLATE_FLUID'] = label
        row['PLATE_CONF'] = conf
        row['REVIEW'] = bool(label == 'UNDEFINED' or conf < 0.5)
        row['REVIEW_REASON'] = ('NO_GAS_PLATE_EVIDENCE' if label == 'UNDEFINED'
                               else ('LOW_CONF' if conf < 0.5 else ''))
        rows.append(row)
    return pd.DataFrame(rows)


def fuse_with_log(plate_label: str, log_label: str, cfg: dict) -> dict:
    """图版 × 测井规则融合（用户决策：图版决定气/油）。

    plate GAS       → 提升/保持 GAS
    plate OIL       → 原判 GAS 改 OIL（图版权威）
    plate DRY       → 保留测井结论 + REVIEW(NO_GAS_SHOW)
    plate UNDEFINED → 保留测井结论 + REVIEW(NO_GAS_DATA)，禁止强制改 OIL
    """
    rv = cfg.get('review', {})
    log_label = (log_label or '').upper()
    plate_label = (plate_label or 'UNDEFINED').upper()

    if plate_label == 'GAS':
        if log_label in ('GAS', 'OIL', 'OIL_POSSIBLE', 'GAS_POSSIBLE'):
            return {'final': 'GAS', 'action': 'promote_gas', 'flag': '', 'conf': 0.90}
        return {'final': 'GAS', 'action': 'promote_gas',
                'flag': rv.get('conflict_flag', 'GAS_PLATE_CONFLICT'), 'conf': 0.60}
    if plate_label == 'OIL':
        if log_label in ('GAS', 'GAS_POSSIBLE'):
            return {'final': 'OIL', 'action': 'demote_to_oil', 'flag': '', 'conf': 0.85}
        if log_label in ('OIL', 'OIL_POSSIBLE'):
            return {'final': 'OIL', 'action': 'keep', 'flag': '', 'conf': 0.85}
        return {'final': log_label or 'OIL', 'action': 'keep',
                'flag': rv.get('conflict_flag', 'GAS_PLATE_CONFLICT'), 'conf': 0.50}
    if plate_label == 'DRY':
        flag = 'NO_GAS_SHOW' if log_label in ('GAS', 'GAS_POSSIBLE') else ''
        return {'final': log_label, 'action': 'keep', 'flag': flag, 'conf': 0.50}
    flag = rv.get('no_gas_data_flag', 'NO_GAS_DATA') if log_label in ('GAS', 'GAS_POSSIBLE') else ''
    return {'final': log_label, 'action': 'keep', 'flag': flag, 'conf': 0.30}


def summarize(layer_df: pd.DataFrame) -> dict:
    if layer_df is None or len(layer_df) == 0:
        return {'layers': 0}
    return {
        'layers': int(len(layer_df)),
        'gas': int((layer_df['PLATE_FLUID'] == 'GAS').sum()),
        'oil': int((layer_df['PLATE_FLUID'] == 'OIL').sum()),
        'dry': int((layer_df['PLATE_FLUID'] == 'DRY').sum()),
        'undefined': int((layer_df['PLATE_FLUID'] == 'UNDEFINED').sum()),
        'review': int(layer_df['REVIEW'].sum()) if 'REVIEW' in layer_df else 0,
    }
