# -*- coding: utf-8 -*-
"""运行清单（run manifest）：全流程可追溯（支柱④）。

每口井解释完成后写出 <井>_run_manifest.json：
  - 输入：LAS/气测/info.json 路径 + 大小 + mtime + sha256(前 64KB)；
  - 配置快照：解释截止值、区域知识（分带/剖面类型）、模型路径与 mtime；
  - 软件版本：python/numpy/pandas/lasio/matplotlib/fitz；
  - 产物：CSV/LAS/PDF/报告/层表/ML层表 路径+大小；层数/分布/复核率。
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time


def _file_fp(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        st = os.stat(path)
        h = hashlib.sha256(open(path, 'rb').read(65536)).hexdigest()[:16]
        return {'path': str(path), 'size': st.st_size, 'mtime': st.st_mtime, 'sha256_head': h}
    except Exception:
        return {'path': str(path)}


def _versions() -> dict:
    v = {'python': sys.version.split()[0]}
    for m in ('numpy', 'pandas', 'lasio', 'matplotlib', 'fitz', 'sklearn'):
        try:
            v[m] = getattr(__import__(m), '__version__', '?')
        except Exception:
            pass
    return v


def write_run_manifest(well_name: str, out_dir: str, results: dict,
                       config: dict | None = None) -> str | None:
    """写 <井>_run_manifest.json；异常返回 None（不中断主流程）。"""
    try:
        os.makedirs(out_dir, exist_ok=True)
        results = results or {}
        las = results.get('las_path') or (results.get('las_info') or {}).get('las_path')
        gas = results.get('gas_file') or results.get('gas_path')
        # 产物清单
        outs = {}
        for pat in ('*_processed.csv', '*_interpreted.LAS', '*_report.html',
                    '*_quicklook_*.pdf', '*_interpretation_layers.csv',
                    '*_interpretation_layers_ML.csv'):
            fs = sorted(glob.glob(os.path.join(out_dir, pat)), key=os.path.getmtime)
            if fs:
                outs[pat] = _file_fp(fs[-1])
        # 层表统计
        layers = {}
        for kind, key in (('rules', 'layers_path'), ('ml', 'ml_fluid')):
            p = results.get(key) if kind == 'rules' else (results.get('ml_fluid') or {}).get('layers_path')
            if p and os.path.exists(p):
                try:
                    import pandas as pd
                    d = pd.read_csv(p)
                    layers[kind] = {'path': p, 'n': int(len(d)),
                                    'dist': {str(k): int(v) for k, v in
                                             d['INTERPRETATION'].value_counts().items()}}
                except Exception:
                    layers[kind] = {'path': p}
        region = None
        try:
            region = results.get('fluid_zonation')
        except Exception:
            pass
        manifest = {
            'well': str(well_name),
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'inputs': {
                'las': _file_fp(las),
                'gas': _file_fp(gas),
                'info_json': _file_fp(os.path.join(out_dir, str(well_name) + 'info.json')),
            },
            'config_snapshot': {
                'cutoffs': (results.get('cutoffs') or config or {}),
                'region_calib': results.get('region_calib'),
                'fluid_zonation': region,
                'gas_oil_split': results.get('gas_oil_split'),
                'ml_model': _file_fp(os.path.join(r'D:\360\src\data\calibration\models',
                                                  str(well_name) + '.joblib')),
            },
            'versions': _versions(),
            'outputs': outs,
            'layers': layers,
        }
        p = os.path.join(out_dir, str(well_name) + '_run_manifest.json')
        json.dump(manifest, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        return p
    except Exception:
        return None


def backfill(root_dirs: list, force: bool = False) -> dict:
    """为已有输出目录回填运行清单（无法追溯配置/输入指纹的部分标 source=backfill）。

    扫描 <root>/<井>/ 下 processed/layers/ML/PDF/report，生成最小清单；
    已有清单默认不覆盖（force=True 覆盖）。
    """
    res = {'ok': 0, 'skip': 0, 'fail': 0, 'files': []}
    for root in root_dirs:
        if not os.path.isdir(root):
            continue
        for well_dir in sorted(os.listdir(root)):
            d = os.path.join(root, well_dir)
            if not os.path.isdir(d):
                continue
            try:
                csvs = sorted(glob.glob(os.path.join(d, '*_processed.csv')), key=os.path.getmtime)
                if not csvs:
                    continue
                well = os.path.basename(csvs[-1])[:-len('_processed.csv')]
                mp = os.path.join(d, well + '_run_manifest.json')
                if os.path.exists(mp) and not force:
                    res['skip'] += 1
                    continue
                outs, layers = {}, {}
                for pat in ('*_processed.csv', '*_interpreted.LAS', '*_report.html',
                            '*_quicklook_*.pdf', '*_interpretation_layers.csv',
                            '*_interpretation_layers_ML.csv', '*_composite_log_*.pdf'):
                    fs = sorted(glob.glob(os.path.join(d, pat)), key=os.path.getmtime)
                    if fs:
                        outs[pat] = _file_fp(fs[-1])
                for kind, pat in (('rules', '*_interpretation_layers.csv'),
                                  ('ml', '*_interpretation_layers_ML.csv')):
                    fs = sorted(glob.glob(os.path.join(d, pat)), key=os.path.getmtime)
                    if fs:
                        try:
                            import pandas as pd
                            t = pd.read_csv(fs[-1])
                            layers[kind] = {'path': fs[-1], 'n': int(len(t)),
                                            'dist': {str(k): int(v) for k, v in
                                                     t['INTERPRETATION'].value_counts().items()}}
                        except Exception:
                            pass
                manifest = {
                    'well': well, 'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'backfill',
                    'inputs': {'las': _file_fp(next(iter(glob.glob(os.path.join(d, '*.LAS')))
                                                  if glob.glob(os.path.join(d, '*.LAS')) else '')),
                               'info_json': _file_fp(os.path.join(d, well + 'info.json'))},
                    'config_snapshot': {'note': 'backfill：历史产物无配置快照'},
                    'versions': _versions(), 'outputs': outs, 'layers': layers,
                }
                json.dump(manifest, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
                res['ok'] += 1
                res['files'].append(mp)
            except Exception:
                res['fail'] += 1
    return res


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description='运行清单：回填已有输出')
    ap.add_argument('--backfill', required=True, help='输出根目录，逗号分隔')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    roots = [x.strip() for x in args.backfill.split(',') if x.strip()]
    r = backfill(roots, force=args.force)
    print(json.dumps({k: (v if k != 'files' else len(v)) for k, v in r.items()},
                     ensure_ascii=False))
    for f in r['files']:
        print(' +', f)
    return 0


if __name__ == '__main__':
    import sys as _sys
    _sys.exit(_cli())
