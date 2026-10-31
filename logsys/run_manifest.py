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
