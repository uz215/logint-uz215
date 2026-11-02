# -*- coding: utf-8 -*-
"""油气同层顺序整饰：GAS_OIL 必须"气在上、油在下"（重力分异，用户 2026-10-31 口径）。

做法：
- 对每段连续 GAS_OIL 点，用气测证据（PLATE_FLUID=GAS、TG 高值）寻找气/油分界：
  最大化"上部气指数均值 − 下部气指数均值"；
- 上部 → GAS，下部 → OIL（两段），并记 FLUID_MIX_ORDER='GAS_ABOVE_OIL'；
- 证据无明显梯度时按中点拆分并标 'INFERRED'（仍遵守气上油下）；
- 输出统计：splits / evidence / inferred / points。

与绘图一致：logvis GAS_OIL 斜对角本来就是"气上半、油下半"。
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd


def _gas_score(df: pd.DataFrame) -> np.ndarray:
    n = len(df)
    score = np.zeros(n, dtype=float)
    if 'PLATE_FLUID' in df.columns:
        plate = df['PLATE_FLUID'].astype(str).str.upper()
        score += np.where(plate == 'GAS', 2.0, 0.0)
        score += np.where(plate == 'DRY', -1.0, 0.0)
    for col in ('TG', 'C1'):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors='coerce').values
            v = np.where(np.isfinite(v), v, np.nan)
            if np.isfinite(v).sum() > 5:
                med = np.nanmedian(v)
                if med > 0:
                    score += 0.5 * np.log10(np.clip(v, 1e-3, None) / med)
            break
    return np.nan_to_num(score, nan=0.0)


def split_gas_oil(df: pd.DataFrame, depth_col: str = 'MD', min_run: int = 2) -> dict:
    """就地拆分 GAS_OIL 段为 GAS(上)+OIL(下)；返回统计。"""
    if 'INTERPRETATION' not in df.columns or depth_col not in df.columns:
        return {'applied': False, 'reason': '缺列'}
    itp = df['INTERPRETATION'].astype(str).str.upper()
    mask = itp.eq('GAS_OIL').values
    if not mask.any():
        return {'applied': True, 'splits': 0, 'points': 0}
    score = _gas_score(df)
    df['FLUID_MIX_ORDER'] = df.get('FLUID_MIX_ORDER', '')
    df['GAS_OIL_SPLIT'] = df.get('GAS_OIL_SPLIT', '')
    md = pd.to_numeric(df[depth_col], errors='coerce').values
    n = len(df)
    new = itp.copy()
    i = 0
    splits = 0
    evidence = inferred = 0
    points = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and mask[j + 1]:
            j += 1
        idx = np.arange(i, j + 1)
        # 只处理深度连续的段
        if len(idx) >= min_run:
            s = score[idx]
            best_k, best_gain = None, -1e9
            for k in range(1, len(idx)):
                gain = s[:k].mean() - s[k:].mean()
                if gain > best_gain:
                    best_gain, best_k = gain, k
            if best_gain <= 1e-9:
                best_k = len(idx) // 2
                inferred += 1
                tag = 'INFERRED'
            else:
                evidence += 1
                tag = 'EVIDENCE'
            up = idx[:best_k]
            dn = idx[best_k:]
            new.iloc[up] = 'GAS'
            new.iloc[dn] = 'OIL'
            df.loc[df.index[up], 'FLUID_MIX_ORDER'] = 'GAS_ABOVE_OIL'
            df.loc[df.index[dn], 'FLUID_MIX_ORDER'] = 'GAS_ABOVE_OIL'
            df.loc[df.index[up], 'GAS_OIL_SPLIT'] = tag
            df.loc[df.index[dn], 'GAS_OIL_SPLIT'] = tag
            splits += 1
            points += len(idx)
        else:
            # 单点混合：无上下可分 → 标 REVIEW，保持 GAS_OIL
            df.loc[df.index[idx], 'FLUID_MIX_ORDER'] = 'GAS_ABOVE_OIL'
            df.loc[df.index[idx], 'GAS_OIL_SPLIT'] = 'SINGLE_POINT'
        i = j + 1
    df['INTERPRETATION'] = new
    return {'applied': True, 'splits': splits, 'points': int(points),
            'evidence': int(evidence), 'inferred': int(inferred)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='油气同层顺序整饰（气上油下）')
    ap.add_argument('--csv', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)
    d = pd.read_csv(args.csv, low_memory=False)
    r = split_gas_oil(d)
    print(r)
    print('AFTER:', d['INTERPRETATION'].value_counts().to_dict())
    if args.out:
        d.to_csv(args.out, index=False, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
