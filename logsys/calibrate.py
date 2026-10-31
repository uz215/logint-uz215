# -*- coding: utf-8 -*-
"""多井流体判定截止值标定（numpy 预计算加速版）。

相对首版：
- 逐点数组只准备一次，网格内只用 numpy 运算（快 ~50 倍）；
- 网格精简为 ~6.8 万组合（可在 1 分钟内/井）；
- 真值支持：BET-1 SLAM / TrakesKE-1 成果表 / RP-13 RUSH。
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

DEFAULT_CUTOFFS = {
    'por_hc': 0.06, 'por_dry_max': 0.10, 'sw_hc': 0.50, 'sw_deny': 0.65,
    'rt_gas': 50.0, 'rt_oil': 30.0, 'rt_water': 20.0,
}
GRID = {
    'por_hc': [0.03, 0.04, 0.05, 0.06, 0.08, 0.10],
    'por_dry_max': [0.08, 0.10, 0.12],
    'sw_hc': [0.45, 0.50, 0.55, 0.60, 0.65, 0.70],
    'sw_deny': [0.65, 0.75, 0.85],
    'rt_gas': [3.0, 5.0, 10.0, 20.0, 50.0],
    'rt_oil': [1.0, 3.0, 5.0, 7.0, 10.0, 15.0, 30.0],
    'rt_water': [2.0, 3.0, 5.0, 10.0, 20.0, 25.0],
}
TIGHT_LITHS = ('shale', 'coal', 'carbonaceous_shale', 'carbonaceous mudstone', 'casing',
               'halite', 'anhydrite', 'gypsum', 'basement', 'volcanic', 'unknown')


# ----------------------------- 真值读取 ----------------------------- #
def load_truths(path: str, kind: str) -> pd.DataFrame:
    rows = []
    if kind == 'bet1_slam':
        d = pd.read_excel(path, sheet_name='LHResultTable', header=None)
        for i in range(3, len(d)):
            try:
                top, base = float(d.iloc[i, 1]), float(d.iloc[i, 2])
            except Exception:
                continue
            if base > top:
                rows.append((top, base, _map_fluid(str(d.iloc[i, 13]))))
    elif kind == 'trakes_result':
        d = pd.read_excel(path, sheet_name='成果表', header=0)
        for _, r in d.iterrows():
            try:
                top, base = float(r.iloc[2]), float(r.iloc[3])
            except Exception:
                continue
            if base > top:
                rows.append((top, base, _map_fluid(str(r.iloc[16]))))
    elif kind == 'rp13_rush':
        d = pd.read_excel(path, sheet_name=0, header=0)
        for _, r in d.iterrows():
            try:
                top, base = float(r.iloc[1]), float(r.iloc[2])
            except Exception:
                continue
            if base > top:
                rows.append((top, base, _map_fluid(str(r.iloc[13]))))
    else:
        raise ValueError('unknown truth kind: ' + kind)
    out = pd.DataFrame(rows, columns=['TOP', 'BASE', 'FLUID'])
    return out[out['FLUID'] != 'OTHER'].reset_index(drop=True)


def _map_fluid(s: str) -> str:
    s = str(s).upper().replace(' ', '').replace('-', '_')
    if 'GAS&OIL' in s or 'GAS_OIL' in s or 'OIL_GAS' in s:
        return 'GAS_OIL'
    if 'GAS_WATER' in s or 'WATER_GAS' in s or 'GAS_WATER' in s:
        return 'MIXED'
    if 'GAS' in s:
        return 'GAS'
    if 'OIL' in s:
        return 'OIL'
    if 'WATER' in s:
        return 'WATER'
    if 'TIGHT' in s or 'DRY' in s:
        return 'TIGHT'
    return 'OTHER'


# ----------------------------- 逐点数组 ----------------------------- #
def prepare(csv_path: str, truth: pd.DataFrame, lith_tight: bool = False) -> dict:
    d = pd.read_csv(csv_path, low_memory=False)

    def col(*names):
        for n in names:
            if n in d.columns:
                return n
        return None
    md = pd.to_numeric(d[col('MD', 'DEPTH', 'DEPT')], errors='coerce').values
    por = pd.to_numeric(d[col('PHI', 'POR')], errors='coerce').values if col('PHI', 'POR') else np.full(len(d), np.nan)
    sw = pd.to_numeric(d[col('Sw', 'SW')], errors='coerce').values if col('Sw', 'SW') else np.full(len(d), np.nan)
    rt = pd.to_numeric(d[col('RT', 'RD', 'LLD')], errors='coerce').values if col('RT', 'RD', 'LLD') else np.full(len(d), np.nan)
    vsh = pd.to_numeric(d[col('VSH', 'VSHALE')], errors='coerce').values if col('VSH', 'VSHALE') else np.zeros(len(d))
    lith = d[col('LITHOLOGY', 'LITHOLOGY_MC')].astype(str).str.lower().values if col('LITHOLOGY', 'LITHOLOGY_MC') else np.array([''] * len(d))
    plate = d['PLATE_FLUID'].astype(str).str.upper().values if 'PLATE_FLUID' in d.columns else np.array([''] * len(d))

    truth_arr = np.array(['NONE'] * len(d), dtype=object)
    for _, r in truth.iterrows():
        m = (md >= r['TOP']) & (md < r['BASE'])
        truth_arr[m] = r['FLUID']

    valid = (truth_arr != 'NONE') & np.isfinite(por) & np.isfinite(sw)
    step = float(np.nanmedian(np.diff(np.unique(md[np.isfinite(md)])))) if np.isfinite(md).sum() > 1 else 1.0
    # 默认只用 VSH>0.60 判定非储层；岩性名单可开关（承包商真值常把高孔泥岩段也判为水/油层）
    nonres = (np.nan_to_num(vsh, nan=0.0) > 0.60)
    if lith_tight:
        nonres = nonres | np.isin(lith, TIGHT_LITHS)
    return {
        'n': int(valid.sum()),
        'md': md[valid], 'por': por[valid], 'sw': sw[valid], 'rt': rt[valid],
        'nonres': nonres[valid], 'plate': plate[valid], 'truth': truth_arr[valid],
        'step': step,
    }


def score_arr(a: dict, cut: dict, use_plate=False) -> dict:
    por_hc, por_dry = cut['por_hc'], cut['por_dry_max']
    sw_hc, sw_deny = cut['sw_hc'], cut['sw_deny']
    rt_gas, rt_oil, rt_water = cut['rt_gas'], cut['rt_oil'], cut['rt_water']
    por, sw, rt, nonres, plate, truth = a['por'], a['sw'], a['rt'], a['nonres'], a['plate'], a['truth']
    tight = nonres | (por < por_hc)
    gas = (~tight) & (sw < sw_hc) & (sw < sw_deny) & np.isfinite(rt) & (rt > rt_gas)
    if use_plate:
        gas = gas | ((~tight) & (plate == 'GAS'))
    oil = (~tight) & (~gas) & (sw < sw_hc) & np.isfinite(rt) & (rt > rt_oil)
    water = (~tight) & (~gas) & (~oil) & (sw >= sw_hc) & (por >= por_dry) & np.isfinite(rt)
    pred = np.where(tight, 'TIGHT', np.where(gas, 'GAS', np.where(oil, 'OIL',
                    np.where(water, 'WATER', 'TIGHT'))))
    main = truth != 'MIXED'
    acc_all = float((pred[main] == truth[main]).mean())
    hc = np.isin(truth, ['GAS', 'GAS_OIL', 'OIL', 'WATER']) & main
    acc_hc = float((pred[hc] == truth[hc]).mean()) if hc.any() else 0.0
    return {'acc_all': acc_all, 'acc_hc': acc_hc,
            'objective': 0.5 * acc_all + 0.5 * acc_hc,
            'n': int(main.sum())}


def calibrate(a: dict, use_plate=False, grid=None):
    grid = grid or GRID
    best = None
    total = int(np.prod([len(v) for v in grid.values()]))
    for vals in itertools.product(*grid.values()):
        cut = dict(zip(grid.keys(), vals))
        r = score_arr(a, cut, use_plate=use_plate)
        if best is None or r['objective'] > best[0]:
            best = (r['objective'], cut, r)
    return best[1], best[2], total


def run_well(spec: dict, out_dir: str) -> dict:
    truth = load_truths(spec['truth'], spec['truth_kind'])
    a = prepare(spec['proc'], truth, lith_tight=bool(spec.get('lith_tight', False)))
    base = score_arr(a, DEFAULT_CUTOFFS, use_plate=spec.get('use_plate', False))
    best_cut, best_m, total = calibrate(a, use_plate=spec.get('use_plate', False))
    # 诊断：各真值类的特征中位数（判断是 Sw 模型问题还是截止值问题）
    diag = {}
    for t in ('GAS', 'OIL', 'WATER', 'TIGHT'):
        m = a['truth'] == t
        if m.any():
            diag[t] = {'n': int(m.sum()),
                       'POR': round(float(np.nanmedian(a['por'][m])), 4) if np.isfinite(a['por'][m]).any() else None,
                       'SW': round(float(np.nanmedian(a['sw'][m])), 4) if np.isfinite(a['sw'][m]).any() else None,
                       'RT': round(float(np.nanmedian(a['rt'][m])), 3) if np.isfinite(a['rt'][m]).any() else None,
                       'VSH_hi%': round(float(a['nonres'][m].mean()) * 100, 1)}
    res = {'well': spec['well'], 'truth': spec['truth_kind'], 'unit': spec.get('unit', ''),
           'points': a['n'], 'grid_combos': total, 'class_features': diag,
           'default': {'cutoffs': DEFAULT_CUTOFFS, **base},
           'calibrated': {'cutoffs': best_cut, **best_m}}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, spec['well'] + '.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description='多井流体截止值标定')
    ap.add_argument('--registry', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       'calibrate_wells.json'))
    ap.add_argument('--out', default=r'D:\360\src\data\calibration')
    args = ap.parse_args(argv)
    specs = json.load(open(args.registry, encoding='utf-8'))
    results = []
    for s in specs:
        print('==== %s ====' % s['well'], flush=True)
        try:
            results.append(run_well(s, args.out))
        except Exception as e:
            print('  FAILED: %s: %s' % (type(e).__name__, e), flush=True)
    print('\n%-14s %8s %8s %8s %8s' % ('well', 'def_all', 'def_hc', 'cal_all', 'cal_hc'))
    for r in results:
        print('%-14s %7.1f%% %7.1f%% %7.1f%% %7.1f%%' % (
            r['well'], 100 * r['default']['acc_all'], 100 * r['default']['acc_hc'],
            100 * r['calibrated']['acc_all'], 100 * r['calibrated']['acc_hc']))
    print('\ncalibrated cutoffs:')
    for r in results:
        print(' ', r['well'], r['calibrated']['cutoffs'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
