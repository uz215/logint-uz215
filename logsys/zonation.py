# -*- coding: utf-8 -*-
"""流体分带（浅层气/深层油）：按 <井>info.json「区域知识.流体分带」对点结论做分带整饰。

配置示例（BET-1info.json）：
    "区域知识": {"流体分带": {"转换深度": 7677, "单位": "ft", "浅层": "GAS", "深层": "OIL",
                            "_说明": "浅层气、深层油"}}

规则（仅当"转换深度"非空时生效）：
  - MD < 转换深度（浅层）：OIL/GAS_OIL → GAS（记 ZONE_GAS）
  - MD >= 转换深度（深层）：GAS/GAS_OIL → OIL（记 ZONE_OIL）
说明：这是区域地质约束（用户 2026-10-31 口径），用于层表/点结论整饰；
      置信度与复核仍由证据栈给出，改动会记录在 FLUID_ZONE 列便于追溯。
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

FT_TO_M = 0.3048


def _to_unit(value: float, from_unit: str, to_unit: str) -> float:
    fu = (from_unit or 'm').lower()
    tu = (to_unit or 'm').lower()
    if fu == tu:
        return float(value)
    if fu == 'ft' and tu == 'm':
        return float(value) * FT_TO_M
    if fu == 'm' and tu == 'ft':
        return float(value) / FT_TO_M
    return float(value)


def apply_zonation(processed_data: pd.DataFrame, regional: dict, depth_unit: str = 'm') -> dict:
    """就地修改 processed_data['INTERPRETATION']，返回统计（不可用/未配置则 applied=False）。"""
    cfg = (regional or {}).get('流体分带') or {}
    boundary = cfg.get('转换深度')
    if boundary is None or str(boundary).strip() == '':
        return {'applied': False, 'reason': '未配置转换深度'}
    try:
        boundary = float(boundary)
    except Exception:
        return {'applied': False, 'reason': '转换深度非数值: %r' % boundary}
    boundary = _to_unit(boundary, cfg.get('单位', 'm'), depth_unit)
    if 'MD' not in processed_data.columns or 'INTERPRETATION' not in processed_data.columns:
        return {'applied': False, 'reason': 'processed_data 缺 MD/INTERPRETATION'}
    md = pd.to_numeric(processed_data['MD'], errors='coerce')
    itp = processed_data['INTERPRETATION'].astype(str).str.upper()
    shallow = md < boundary
    deep = md >= boundary
    n_shallow = int(((itp.isin(['OIL', 'GAS_OIL'])) & shallow).sum())
    n_deep = int(((itp.isin(['GAS', 'GAS_OIL'])) & deep).sum())
    itp_new = itp.copy()
    itp_new[(itp == 'OIL') & shallow] = 'GAS'
    itp_new[(itp == 'GAS_OIL') & shallow] = 'GAS'
    itp_new[(itp == 'GAS') & deep] = 'OIL'
    itp_new[(itp == 'GAS_OIL') & deep] = 'OIL'
    processed_data['INTERPRETATION'] = itp_new.where(itp != '', processed_data['INTERPRETATION'])
    zone = pd.Series('', index=processed_data.index)
    zone[shallow] = 'GAS'
    zone[deep] = 'OIL'
    processed_data['FLUID_ZONE'] = zone
    return {'applied': True, 'boundary': round(boundary, 3), 'unit': depth_unit,
            'shallow_to_gas': n_shallow, 'deep_to_oil': n_deep,
            'shallow_label': cfg.get('浅层', 'GAS'), 'deep_label': cfg.get('深层', 'OIL')}


def main(argv=None):
    ap = argparse.ArgumentParser(description='流体分带整饰（浅层气/深层油）')
    ap.add_argument('--csv', required=True, help='processed.csv')
    ap.add_argument('--boundary', type=float, required=True)
    ap.add_argument('--unit', default='m')
    ap.add_argument('--boundary-unit', default='m')
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)
    d = pd.read_csv(args.csv, low_memory=False)
    regional = {'流体分带': {'转换深度': args.boundary, '单位': args.boundary_unit}}
    r = apply_zonation(d, regional, args.unit)
    print(r)
    if args.out:
        d.to_csv(args.out, index=False, encoding='utf-8')
        print('written', args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
