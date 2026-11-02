# -*- coding: utf-8 -*-
"""真岩性来源与方法（用户 2026-10-31 口径）：

来源分级（置信度/深度容差由高到低）：
  1) 岩石分析数据（CT/薄片/孔渗等）：岩性最可靠，深度准（±1m）；
  2) 元素测井矿物含量（ECS/LithoScanner）：代表岩性，深度准（±2m）；
  3) 录井图 masterlog：大段岩性可靠，薄层不一定准；深度与测井有系统误差，
     一般上下 3–5m，绝不超过 10m（一根单根），需按容差对齐。
用途：
  - 判定**剖面类型**（砂泥岩/碳酸盐岩/蒸发岩-火成岩/混合），
  - 推荐**最优岩性计算矿物组合**，
  - 以"大段优先"评估测井岩性准确性（薄层单独统计），
  - 深度对齐（-10..+10m 搜索最优偏移）。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .lith_validate import load_profile

# 来源规格：conf=置信度；tol=建议深度容差(m)；max_tol=最大容差(m)
SOURCE_SPECS = {
    'core_analysis': {'label': '岩石分析(CT/薄片/孔渗)', 'conf': 0.95, 'tol': 1.0, 'max_tol': 2.0,
                      'thin_reliable': True},
    'element_log': {'label': '元素测井矿物含量', 'conf': 0.90, 'tol': 2.0, 'max_tol': 3.0,
                    'thin_reliable': True},
    'masterlog': {'label': '录井图 Masterlog', 'conf': 0.80, 'tol': 5.0, 'max_tol': 10.0,
                  'thin_reliable': False},
    # PDF 自动解析结果（程序 masterlog.py 提取；证据置信度略低）
    'masterlog_pdf': {'label': '录井图 Masterlog(PDF解析)', 'conf': 0.75, 'tol': 5.0,
                      'max_tol': 10.0, 'thin_reliable': False},
}

# 剖面类型判定（按真岩性厚度占比）
PROFILE_TYPES = {
    'sand_shale': {'label': '砂泥岩剖面', 'minerals': ['QZ', 'ILL', 'CAL'],
                   'classes': ['sandstone', 'shale', 'coal', 'carbonaceous_shale']},
    'carbonate': {'label': '碳酸盐岩剖面', 'minerals': ['CAL', 'DOL', 'ANH'],
                  'classes': ['limestone', 'dolomite', 'sandstone', 'shale']},
    'evaporite_igneous': {'label': '蒸发岩-火成岩剖面',
                          'minerals': ['CAL', 'DOL', 'ANH', 'HAL', 'BAS'],
                          'classes': ['limestone', 'dolomite', 'anhydrite', 'halite',
                                      'basalt', 'sandstone', 'shale']},
    'mixed': {'label': '混合剖面', 'minerals': ['QZ', 'ILL', 'CAL', 'DOL'],
              'classes': []},
}

CARBONATE_LITHS = {'limestone', 'dolomite'}
EVAP_IGN_LITHS = {'anhydrite', 'halite', 'basalt'}


def source_meta(source: str) -> dict:
    s = SOURCE_SPECS.get(source, SOURCE_SPECS['masterlog'])
    return dict(s, key=source)


def profile_type(truth: pd.DataFrame, min_frac: float = 0.15) -> str:
    """按真岩性层厚度占比判定剖面类型。"""
    if truth is None or len(truth) == 0:
        return 'mixed'
    d = truth.copy()
    d['TH'] = (pd.to_numeric(d['BASE'], errors='coerce') -
               pd.to_numeric(d['TOP'], errors='coerce')).clip(lower=0)
    tot = float(d['TH'].sum()) or 1.0
    by = d.groupby('LITH')['TH'].sum()
    frac = by / tot
    carb = sum(float(frac.get(k, 0)) for k in CARBONATE_LITHS)
    evig = sum(float(frac.get(k, 0)) for k in EVAP_IGN_LITHS)
    sand = float(frac.get('sandstone', 0)) + float(frac.get('shale', 0))
    if carb + evig >= min_frac and evig >= 0.05:
        return 'evaporite_igneous'
    if carb >= min_frac:
        return 'carbonate'
    if sand >= min_frac:
        return 'sand_shale'
    return 'mixed'


def recommended_minerals(ptype: str) -> list:
    return list(PROFILE_TYPES.get(ptype, PROFILE_TYPES['mixed'])['minerals'])


def recommended_classes(ptype: str) -> list:
    return list(PROFILE_TYPES.get(ptype, PROFILE_TYPES['mixed'])['classes'])


def align_depth(log_md: np.ndarray, pred_lith: np.ndarray, truth: pd.DataFrame,
                max_shift: float | None = 10.0, step: float = 0.5) -> dict:
    """搜索最优深度偏移（-max..+max），返回 {shift, acc}；用于评估录井/测井系统误差。"""
    md = pd.to_numeric(pd.Series(log_md), errors='coerce').values
    pred = np.asarray(pred_lith, dtype=object)
    ok = np.isfinite(md) & (pred != '')
    md, pred = md[ok], pred[ok]
    if len(md) == 0 or truth is None or len(truth) == 0:
        return {'shift': 0.0, 'acc': None}
    max_shift = max_shift if max_shift is not None else 10.0
    best = {'shift': 0.0, 'acc': -1.0}
    for sh in np.arange(-max_shift, max_shift + 1e-9, step):
        md2 = md + sh
        tot = good = 0.0
        for _, r in truth.iterrows():
            m = (md2 >= r['TOP']) & (md2 < r['BASE'])
            if not m.any():
                continue
            w = float(m.sum())
            vc = pd.Series(pred[m]).value_counts()
            p = str(vc.index[0]) if len(vc) else ''
            tot += w
            if p == r['LITH']:
                good += w
        if tot > 0 and good / tot > best['acc']:
            best = {'shift': round(float(sh), 2), 'acc': round(good / tot, 4)}
    return best


def evaluate_by_thickness(pred_lith: np.ndarray, log_md: np.ndarray, truth: pd.DataFrame,
                          large_min: float = 2.0) -> dict:
    """按真值层厚加权评估：全体 vs 大段(≥large_min) vs 薄层，并给出厚度占比。"""
    md = pd.to_numeric(pd.Series(log_md), errors='coerce').values
    pred = np.asarray(pred_lith, dtype=object)
    res = {'all': None, 'large': None, 'thin': None,
           'large_frac': None, 'layers': int(len(truth))}
    tot = good = 0.0
    lt = lg = lgood = th = tgood = 0.0
    for _, r in truth.iterrows():
        top, bot = float(r['TOP']), float(r['BASE'])
        m = (md >= top) & (md < bot)
        if not m.any():
            continue
        w = float(bot - top)
        vc = pd.Series(pred[m]).value_counts()
        p = str(vc.index[0]) if len(vc) else ''
        tot += w
        if p == r['LITH']:
            good += w
        if w >= large_min:
            lt += w
            if p == r['LITH']:
                lg += w
        else:
            th += w
            if p == r['LITH']:
                tgood += w
    if total := tot:
        res['all'] = round(good / total, 4)
        res['large_frac'] = round(lt / total, 4) if total else None
    if lt:
        res['large'] = round(lg / lt, 4)
    if th:
        res['thin'] = round(tgood / th, 4)
    return res


def summarize_well(profile_path: str, source: str | None = None) -> dict:
    """汇总真岩性来源信息（概率/容差/剖面类型/推荐矿物）。支持 masterlog PDF。"""
    if source is None:
        low = str(profile_path).lower()
        source = ('element_log' if 'mineral' in low else
                  'core_analysis' if any(k in low for k in ('core', 'ct', 'thin')) else
                  'masterlog_pdf' if low.endswith('.pdf') else 'masterlog')
    # PDF：先用 masterlog.py 解析出岩性 CSV
    if str(profile_path).lower().endswith('.pdf'):
        try:
            import tempfile
            from .well_docs import read_masterlog_file
            _td = tempfile.mkdtemp(prefix='mdlith_')
            _r = read_masterlog_file(str(profile_path), out_dir=_td, depth_range=(0, 8000))
            if _r.get('lith_file') and os.path.exists(_r['lith_file']):
                profile_path = _r['lith_file']
        except Exception:
            pass
    truth = load_profile(profile_path)
    pt = profile_type(truth)
    meta = source_meta(source)
    return {'path': profile_path, 'source': source, 'source_meta': meta,
            'profile_type': pt,
            'profile_label': PROFILE_TYPES[pt]['label'],
            'minerals': recommended_minerals(pt),
            'classes': recommended_classes(pt),
            'layers': int(len(truth)),
            'thickness_m': round(float((truth['BASE'] - truth['TOP']).clip(lower=0).sum()), 1)}


def main(argv=None):
    import sys
    p = argv[0] if argv else None
    if not p:
        print('用法: python -m logsys.truth_lith <真岩性剖面 xlsx/csv>')
        return 1
    import json
    print(json.dumps(summarize_well(p), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
