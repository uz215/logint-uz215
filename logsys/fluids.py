# -*- coding: utf-8 -*-
"""含烃饱和度 Sg/So 计算（用户定案 2026-11-01）：

- GAS_OIL = 油气同层（测试油气同出、比例大体相当）：默认 Sg/So 各半（0.5/0.5）；
  如实际测试比例不同，可在井 info.json「解释参数.气油比例」显式指定（如 0.4=气占40%，仅示例，不是固定规则）；
  不再用气测组分自动推断饱和度比例（气测组分≠地下含烃比例）；
- 干层 DRY：**不是不含油气**，只是物性/可采性差；仍按 1-Sw 计算含烃饱和度；
  气/油分配：气测图版 GAS/OIL 优先，否则用气油比例；
- 守恒：SG + SO + SW_EFF = 1（SW_EFF = 1 - SG - SO；Sw 实测值保留在 SW 列）。

输出列：SG、SO、SW_EFF（0..1，保留 4 位）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = ('GAS', 'OIL', 'GAS_OIL', 'OIL_GAS', 'DRY', 'WATER', 'OIL_WATER', 'GAS_WATER')


def _sw_col(df):
    for c in ('SW_COMP', 'Sw', 'SW', 'SWIR'):
        if c in df.columns:
            return c
    return None


def _constant_ratio(df, ratio=0.5):
    """GAS_OIL 默认气占烃比例：0.5（油气同层、比例相当）。仅作默认值。"""
    return pd.Series(float(ratio), index=df.index)


def compute_sg_so(df: pd.DataFrame, gas_data=None, gas_oil_ratio=None,
                  dry_hc=True, default_ratio=0.5) -> tuple[pd.DataFrame, dict]:
    """计算 SG/SO/SW_EFF。返回 (df, stats)。

    gas_oil_ratio: 0..1 的气占烃比例（None=按气测组分/默认）。
    dry_hc: 干层是否计算含烃（用户口径 True）。
    """
    out = df.copy()
    stats = {'rows': int(len(out)), 'dry_hc': bool(dry_hc),
             'gas_oil_ratio': gas_oil_ratio, 'max_conservation_residual': 0.0,
             'class_counts': {}, 'mean_sg': None, 'mean_so': None}
    swc = _sw_col(out)
    if len(out) == 0 or swc is None or 'INTERPRETATION' not in out.columns:
        out['SG'] = 0.0
        out['SO'] = 0.0
        out['SW_EFF'] = 1.0
        return out, stats
    sw = pd.to_numeric(out[swc], errors='coerce').clip(0, 1)
    itp = out['INTERPRETATION'].astype(str).str.upper()
    # GAS_OIL 默认各半；只有井配置显式指定比例时才改（气测组分不用于推断饱和度比例）
    f_gas = _constant_ratio(out, default_ratio)
    if gas_oil_ratio is not None:
        try:
            f_gas = pd.Series(float(gas_oil_ratio), index=out.index).clip(0.0, 1.0)
        except Exception:
            pass
    # 气测图版优先（干层分配用）
    plate = out['PLATE_FLUID'].astype(str).str.upper() if 'PLATE_FLUID' in out.columns else None
    sg = pd.Series(0.0, index=out.index)
    so = pd.Series(0.0, index=out.index)
    hc = (1.0 - sw).clip(lower=0)
    m_gas = itp.isin(['GAS'])
    m_oil = itp.isin(['OIL'])
    m_go = itp.isin(['GAS_OIL', 'OIL_GAS'])
    m_dry = itp.eq('DRY')
    sg = sg.where(~m_gas, hc)
    so = so.where(~m_oil, hc)
    sg = sg.where(~m_go, hc * f_gas)
    so = so.where(~m_go, hc * (1.0 - f_gas))
    if dry_hc:
        _f_dry = f_gas.copy()
        if plate is not None:
            _f_dry = _f_dry.where(~plate.eq('GAS'), 1.0)
            _f_dry = _f_dry.where(~plate.eq('OIL'), 0.0)
        sg = sg.where(~m_dry, hc * _f_dry)
        so = so.where(~m_dry, hc * (1.0 - _f_dry))
    sg = sg.clip(0, 1).round(4)
    so = so.clip(0, 1).round(4)
    sw_eff = (1.0 - sg - so).clip(0, 1).round(4)
    out['SG'] = sg
    out['SO'] = so
    out['SW_EFF'] = sw_eff
    _valid = itp.isin(LABELS) & sw.notna()
    if _valid.any():
        _resid = (sg + so + sw_eff - 1.0).abs()
        stats['max_conservation_residual'] = round(float(_resid[_valid].max()), 6)
        stats['mean_sg'] = round(float(sg[_valid].mean()), 4)
        stats['mean_so'] = round(float(so[_valid].mean()), 4)
        stats['class_counts'] = {k: int((itp[_valid] == k).sum())
                                 for k in LABELS if (itp[_valid] == k).any()}
        if (m_dry & sw.notna()).any():
            stats['dry_mean_sg'] = round(float(sg[m_dry & sw.notna()].mean()), 4)
            stats['dry_mean_so'] = round(float(so[m_dry & sw.notna()].mean()), 4)
    return out, stats

