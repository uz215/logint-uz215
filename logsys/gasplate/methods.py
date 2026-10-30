# -*- coding: utf-8 -*-
"""气测解释图版方法库。

纯函数实现，输入 DataFrame（需含 C1..C5 中的若干列；单位一致即可，比值法不受单位影响），
输出逐点判别结果。所有阈值来自 config/gas_plate_default.json（源：气测解释图版.xls）。

方法：
- pixler_ratios / pixler_classify   皮克斯勒比值图版（图版已完整录入）
- ratio_c1_heavy                    轻重烃比值法 C1/(C2+C3+C4+C5)（图版已录入）
- ratio_c2c3                        乙烷甲烷比值法 C2/C3*10（图版已录入）
- three_h                          3H 法（公式已录入，阈值为空 → 默认停用，待试油井标定）
- gas_eval_zones                    气体评价法 A/B/C/D 区（区名已录入，阈值待确认 → 默认停用）

图版口径校正（2026-10-30）：
  Excel「轻重烃比值法」行标注为 C1/∑C，但其计算值为 2.98（以样品 C1=74.65、C2=14.14… 反算），
  实际公式为 C1/(C2+C3+C4+C5)，故本模块按后者实现，分带（<5 … >25）原样引用。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HYDROCARBONS = ['C1', 'C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5']
LABELS = ('GAS', 'OIL', 'DRY', 'UNDEFINED')


def _num(df, name):
    if name not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype='float64')
    return pd.to_numeric(df[name], errors='coerce')


def _ratio(a, b):
    out = a / b
    return out.where((b > 0) & b.notna())


def _in_range(v, rng, closed_right=False):
    if rng is None:
        return pd.Series(False, index=v.index)
    lo, hi = rng
    ok = v.notna()
    if lo is not None:
        ok = ok & (v >= lo)
    if hi is not None:
        ok = ok & ((v <= hi) if closed_right else (v < hi))
    return ok


# --------------------------------------------------------------------------- #
# 1) Pixler 图版
# --------------------------------------------------------------------------- #
def pixler_ratios(df: pd.DataFrame) -> pd.DataFrame:
    c1, c2, c3 = _num(df, 'C1'), _num(df, 'C2'), _num(df, 'C3')
    ic4, nc4 = _num(df, 'IC4'), _num(df, 'NC4')
    c4 = ic4.fillna(0) + nc4.fillna(0)
    has_c4 = ic4.notna() | nc4.notna()
    return pd.DataFrame({
        'C1/C2': _ratio(c1, c2),
        'C1/C3': _ratio(c1, c3),
        'C1/C4': _ratio(c1, c4.where(has_c4)),
    }, index=df.index)


def pixler_classify(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """逐点 Pixler 判别（strict / majority 两种判读口径，见配置 policy）。"""
    p = cfg.get('pixler', {})
    oil_cfg, gas_cfg = p.get('oil', {}), p.get('gas', {})
    policy = p.get('policy', 'majority')

    r = pixler_ratios(df)
    n_valid = r.notna().sum(axis=1)
    oil_hits = pd.Series(0, index=df.index, dtype='int64')
    gas_hits = pd.Series(0, index=df.index, dtype='int64')
    for key in ('C1/C2', 'C1/C3', 'C1/C4'):
        v = r[key]
        # 区间口径：油区右开（2–10 不含 10），气区右闭（10–35 含 35），
        # 边界值唯一归属气区，避免 10/14/21 同时落入两区。
        oil_hits += _in_range(v, oil_cfg.get(key), False).astype(int)
        gas_hits += _in_range(v, gas_cfg.get(key), True).astype(int)

    label = pd.Series('UNDEFINED', index=df.index, dtype=object)
    conf = pd.Series(0.0, index=df.index)
    enough = n_valid >= 2

    if policy == 'strict':
        gas_ok = enough & (gas_hits == n_valid)
        oil_ok = enough & (oil_hits == n_valid)
        label[gas_ok] = 'GAS'
        label[oil_ok] = 'OIL'
        conf[gas_ok | oil_ok] = 1.0
        dry = enough & ~gas_ok & ~oil_ok
        label[dry] = 'DRY'
        conf[dry] = 0.5
    else:
        gas_ok = enough & (gas_hits >= 2) & (gas_hits > oil_hits)
        oil_ok = enough & (oil_hits >= 2) & (oil_hits > gas_hits)
        label[gas_ok] = 'GAS'
        label[oil_ok] = 'OIL'
        # 置信度 = (0.5 + 0.45*落区比例) × 有效比分数因子（仅 2 项有效时下调）
        avail = pd.Series(np.where(n_valid >= 3, 1.0, 0.8), index=df.index)
        conf[gas_ok] = (0.5 + 0.45 * gas_hits[gas_ok] / n_valid[gas_ok]) * avail[gas_ok]
        conf[oil_ok] = (0.5 + 0.45 * oil_hits[oil_ok] / n_valid[oil_ok]) * avail[oil_ok]
        dry = enough & ~gas_ok & ~oil_ok
        label[dry] = 'DRY'
        conf[dry] = 0.4

    why = (r['C1/C2'].round(2).astype(str) + ' / ' + r['C1/C3'].round(2).astype(str)
           + ' / ' + r['C1/C4'].round(2).astype(str))
    return pd.DataFrame({
        'PIXLER': label, 'PIXLER_CONF': conf,
        'PIXLER_HITS': gas_hits - oil_hits,
        'PIXLER_VALID': n_valid, 'PIXLER_WHY': why,
    }, index=df.index)


# --------------------------------------------------------------------------- #
# 2) 比值法
# --------------------------------------------------------------------------- #
def _band_label(value, bands):
    out = pd.Series('UNDEFINED', index=value.index, dtype=object)
    for lo, hi, name in bands:
        ok = value.notna()
        if lo is not None:
            ok = ok & (value >= lo)
        if hi is not None:
            ok = ok & (value < hi)
        out[ok] = name
    return out


def ratio_c1_heavy(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """轻重烃比值法：C1/(C2+C3+C4+C5)，分带 <5 油相关气 … >25 甚干气。"""
    rc = cfg.get('ratio_c1_heavy', {})
    if not rc.get('enabled', True):
        return pd.Series('UNDEFINED', index=df.index, dtype=object)
    c1 = _num(df, 'C1')
    heavy = sum(_num(df, c).fillna(0) for c in ['C2', 'C3', 'IC4', 'NC4', 'IC5', 'NC5'])
    val = _ratio(c1, heavy)
    return _band_label(val, rc['bands'])


def ratio_c2c3(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """乙烷甲烷比值法：C2/C3*10，分带 <20 伴生气→油 … >50 甚干气。"""
    rc = cfg.get('ratio_c2c3', {})
    if not rc.get('enabled', True):
        return pd.Series('UNDEFINED', index=df.index, dtype=object)
    val = _ratio(_num(df, 'C2'), _num(df, 'C3')) * float(rc.get('scale', 10))
    return _band_label(val, rc['bands'])


# --------------------------------------------------------------------------- #
# 3) 3H 法（默认停用）
# --------------------------------------------------------------------------- #
def three_h(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    c1, c2, c3 = _num(df, 'C1'), _num(df, 'C2'), _num(df, 'C3')
    ic4, nc4, ic5, nc5 = _num(df, 'IC4'), _num(df, 'NC4'), _num(df, 'IC5'), _num(df, 'NC5')
    c4, c5 = ic4.fillna(0) + nc4.fillna(0), ic5.fillna(0) + nc5.fillna(0)
    total = c1.fillna(0) + c2.fillna(0) + c3.fillna(0) + c4 + c5
    k = float(cfg.get('three_h', {}).get('K', 100))
    out['WH'] = _ratio((c2.fillna(0) + c3.fillna(0) + c4 + c5) * k, total)
    out['BH'] = _ratio(c1.fillna(0) + c2.fillna(0), c3.fillna(0) + c4 + c5)
    out['CH'] = _ratio(c4 + c5, c3)
    th = cfg.get('three_h', {})
    label = pd.Series('UNDEFINED', index=df.index, dtype=object)
    if th.get('enabled'):
        oil, gas = th.get('oil', {}), th.get('gas', {})
        oil_ok = _in_range(out['WH'], oil.get('WH'), True) & (out['CH'] >= oil.get('CH_min', 0))
        oil_ok &= out['BH'] <= out['WH'] * oil.get('BH_max_ratio', 1e9)
        gas_ok = _in_range(out['WH'], gas.get('WH'), True) & ~oil_ok
        label[gas_ok] = 'GAS'
        label[oil_ok] = 'OIL'
    out['THREE_H'] = label
    return out


# --------------------------------------------------------------------------- #
# 4) 气体评价法（默认停用）
# --------------------------------------------------------------------------- #
def gas_eval_zones(df: pd.DataFrame, cfg: dict) -> pd.Series:
    ge = cfg.get('gas_eval', {})
    label = pd.Series('UNDEFINED', index=df.index, dtype=object)
    if not ge.get('enabled'):
        return label
    r = pixler_ratios(df)
    for z, spec in ge.get('zones', {}).items():
        ok = pd.Series(True, index=df.index)
        if spec.get('c1c2'):
            ok &= _in_range(r['C1/C2'], spec['c1c2'], True)
        if spec.get('c1c3'):
            ok &= _in_range(r['C1/C3'], spec['c1c3'], True)
        label[ok & (label == 'UNDEFINED')] = z
    return label
