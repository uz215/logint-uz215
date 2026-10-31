# -*- coding: utf-8 -*-
"""区域标定矩阵：同一国家/油田/构造的井合并标定，井越多越稳；结果入知识库。

实现：
1. registry 井配置增加 country / region（油田或构造）；
2. 逐井取真值点 → 按 (country, region) 分组 → 合并点集 → 网格标定 7 个截止值；
3. 输出 data/calibration/regions/<country>|<region>.json（井数/点数/默认 vs 标定/参数）；
4. 知识库表 region_calib 入库（来源、置信度、井清单）。

用法：
    python -m logsys.calibrate --regional      # 生成区域矩阵（同时仍跑逐井）
    python -m logsys.knowledge.build --cases-only   # 入库（kb_sources.json 指定目录）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

from .knowledge.db import connect as kb_connect
from .knowledge.calib import import_region_calib
from .calibrate import (DEFAULT_CUTOFFS, GRID, load_truths, prepare, score_arr,
                        calibrate, _map_fluid)

BASE = r'D:\360\src'
REGION_DIR = os.path.join(BASE, 'data', 'calibration', 'regions')


def _concat_arrays(arrs: list) -> dict:
    keys = ['por', 'sw', 'rt', 'nonres', 'plate', 'truth']
    out = {}
    for k in keys:
        out[k] = np.concatenate([a[k] for a in arrs]) if k != 'nonres' else np.concatenate([a[k] for a in arrs])
    out['n'] = int(len(out['por']))
    return out


def regional(specs: list, out_dir: str = REGION_DIR) -> list:
    groups = {}
    for spec in specs:
        country = str(spec.get('country') or '未知国家')
        region = str(spec.get('region') or '未知区块')
        key = '%s|%s' % (country, region)
        g = groups.setdefault(key, {'country': country, 'region': region,
                                    'wells': [], 'ref_wells': [], 'arrs': [],
                                    'bounds': {}})
        g['wells'].append(spec['well'])
        for k, b in (spec.get('cutoff_bounds') or {}).items():
            g['bounds'][k] = b  # 区域内硬约束（如 BET-1 por_hc>=0.10）
        if spec.get('reference'):
            g['ref_wells'].append(spec['well'])
            continue
        try:
            truth = load_truths(spec['truth'], spec['truth_kind'])
            a = prepare(spec['proc'], truth, lith_tight=bool(spec.get('lith_tight', False)))
            if a['n'] > 0:
                g['arrs'].append(a)
        except Exception as e:
            print('  %s 取点失败: %s: %s' % (spec['well'], type(e).__name__, e), flush=True)

    os.makedirs(out_dir, exist_ok=True)
    results = []
    for key, g in groups.items():
        if not g['arrs']:
            print('  %-40s 无可标定点（仅参考井或数据缺失），跳过' % key, flush=True)
            continue
        pooled = _concat_arrays(g['arrs'])
        base = score_arr(pooled, DEFAULT_CUTOFFS)
        best_cut, best_m, total = calibrate(pooled, bounds=g.get('bounds') or None)
        rec = {'country': g['country'], 'region': g['region'],
               'wells': g['wells'], 'reference_wells': g['ref_wells'],
               'n_wells': len(g['arrs']), 'n_points': int(pooled['n']),
               'grid_combos': total,
               'bounds': g.get('bounds') or {},
               'default': {'cutoffs': DEFAULT_CUTOFFS, **base},
               'calibrated': {'cutoffs': best_cut, **best_m}}
        safe = key.replace('|', '_').replace('/', '_').replace(' ', '_')
        path = os.path.join(out_dir, safe + '.json')
        json.dump(rec, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        results.append(rec)
        print('  %-40s 井=%d 点=%5d 默认HC=%5.1f%% 标定HC=%5.1f%%' % (
            key, rec['n_wells'], rec['n_points'],
            100 * base['acc_hc'], 100 * best_m['acc_hc']), flush=True)
    return results


def build_matrix(regions: list) -> str:
    lines = ['# 区域标定矩阵（自动生成）', '',
             '> 说明：同一国家/油田/构造的井越多，合并标定越稳定；参考井不参与拟合。', '',
             '| 国家 | 油田/构造 | 井数 | 点样本 | 默认 气/油/水 | 标定 气/油/水 | 标定参数 |',
             '|---|---|---|---|---|---|---|']
    for r in regions:
        c = r['calibrated']['cutoffs']
        lines.append('| %s | %s | %d | %d | %.1f%% | %.1f%% | %s |' % (
            r['country'], r['region'], r['n_wells'], r['n_points'],
            100 * r['default']['acc_hc'], 100 * r['calibrated']['acc_hc'],
            ', '.join('%s=%s' % (k, v) for k, v in c.items())))
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description='区域标定矩阵')
    ap.add_argument('--registry', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       'calibrate_wells.json'))
    ap.add_argument('--out', default=REGION_DIR)
    args = ap.parse_args(argv)
    specs = json.load(open(args.registry, encoding='utf-8'))
    print('区域标定矩阵:', flush=True)
    regions = regional(specs, args.out)
    md = build_matrix(regions)
    md_path = os.path.join(args.out, 'README.md')
    open(md_path, 'w', encoding='utf-8').write(md)
    print(md)
    # 入库
    try:
        conn = kb_connect(os.path.join(BASE, 'data', 'kb', 'kb.db'))
        n = import_region_calib(conn, args.out)
        print('知识库 region_calib 入库: %d 条' % n)
    except Exception as e:
        print('入库失败（不中断）: %s: %s' % (type(e).__name__, e))
    return 0


if __name__ == '__main__':
    sys.exit(main())
