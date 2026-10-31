# -*- coding: utf-8 -*-
"""流体分带扩展：支持多段式（如 111D：>6640 油、6640-6670 油水同层、<6670 水）。

配置两种写法：
  A) 单界（浅层/深层）：
     {"转换深度": 7677, "单位": "ft", "浅层": "GAS", "深层": "OIL"}
  B) 多段（推荐）：
     {"单位": "m", "分带": [
        {"流体": "OIL", "上界": null, "下界": 6640},
        {"流体": "OIL_WATER", "上界": 6640, "下界": 6670},
        {"流体": "WATER", "上界": 6670, "下界": null}]}

只整饰"流体类"点（GAS/GAS_OIL/OIL/OIL_WATER/WATER），非储层/干层/致密不改；
改动写入 FLUID_ZONE（段名）与 FLUID_ZONE_FROM（原结论），可追溯。
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

FT_TO_M = 0.3048
FLUID_LABELS = {'GAS', 'GAS_OIL', 'OIL', 'OIL_WATER', 'WATER'}


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
    cfg = (regional or {}).get('流体分带') or {}
    if not cfg:
        return {'applied': False, 'reason': '未配置流体分带'}
    if 'MD' not in processed_data.columns or 'INTERPRETATION' not in processed_data.columns:
        return {'applied': False, 'reason': 'processed_data 缺 MD/INTERPRETATION'}
    md = pd.to_numeric(processed_data['MD'], errors='coerce')
    itp = processed_data['INTERPRETATION'].astype(str).str.upper()
    unit = cfg.get('单位', 'm')

    bands = cfg.get('分带')
    if isinstance(bands, list) and bands:
        bands_c = []
        for b in bands:
            lo = b.get('上界')
            hi = b.get('下界')
            bands_c.append({
                'fluid': str(b.get('流体') or '').upper(),
                'lo': _to_unit(lo, unit, depth_unit) if lo not in (None, '') else None,
                'hi': _to_unit(hi, unit, depth_unit) if hi not in (None, '') else None,
            })
    else:
        boundary = cfg.get('转换深度')
        if boundary is None or str(boundary).strip() == '':
            return {'applied': False, 'reason': '未配置转换深度/分带'}
        b = _to_unit(float(boundary), unit, depth_unit)
        bands_c = [{'fluid': str(cfg.get('浅层', 'GAS')).upper(), 'lo': None, 'hi': b},
                   {'fluid': str(cfg.get('深层', 'OIL')).upper(), 'lo': b, 'hi': None}]

    new = itp.copy()
    zone = pd.Series('', index=processed_data.index)
    counts = {}
    for bc in bands_c:
        if not bc['fluid']:
            continue
        m = md.notna()
        if bc['lo'] is not None:
            m = m & (md >= bc['lo'])
        if bc['hi'] is not None:
            m = m & (md < bc['hi'])
        m = m & itp.isin(list(FLUID_LABELS))
        n = int(m.sum())
        if n:
            new[m] = bc['fluid']
            counts[bc['fluid']] = counts.get(bc['fluid'], 0) + n
        zone[m] = bc['fluid']

    changed = int(((new != itp) & itp.isin(list(FLUID_LABELS))).sum())
    processed_data['FLUID_ZONE'] = zone
    processed_data['FLUID_ZONE_FROM'] = itp.where(itp.isin(list(FLUID_LABELS)), '')
    processed_data['INTERPRETATION'] = new
    return {'applied': True, 'unit': depth_unit, 'bands': [
        {'fluid': b['fluid'], 'lo': b['lo'], 'hi': b['hi']} for b in bands_c],
        'counts': counts, 'changed': changed}


def main(argv=None):
    ap = argparse.ArgumentParser(description='流体分带整饰（多段/单界）')
    ap.add_argument('--csv', required=True)
    ap.add_argument('--band', action='append', default=None,
                    help='格式 fluid:lo:hi（lo/hi 空=开区间），可多次')
    ap.add_argument('--unit', default='m')
    ap.add_argument('--unit-out', default='m')
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)
    bands = []
    for spec in (args.band or []):
        parts = spec.split(':')
        fl = parts[0]
        lo = parts[1] if len(parts) > 1 and parts[1] else None
        hi = parts[2] if len(parts) > 2 and parts[2] else None
        bands.append({'流体': fl, '上界': lo, '下界': hi})
    d = pd.read_csv(args.csv, low_memory=False)
    r = apply_zonation(d, {'流体分带': {'单位': args.unit, '分带': bands}}, args.unit_out)
    print(r)
    if args.out:
        d.to_csv(args.out, index=False, encoding='utf-8')
        print('written', args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
