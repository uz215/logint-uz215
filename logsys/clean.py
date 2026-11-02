# -*- coding: utf-8 -*-
"""数据清洗（第二道）：单位归一 + 缺测/非法值清理 + 深度去重排序 + 清洗报告。

与 logInt.sanitize_null_markers 分工：
  - sanitize_null_markers：已知缺测标记（-999/-9999 等）与负值合法性（SP/中子例外）；
  - 本模块：**单位归一**（CAL/BS mm→in、NPHI 分数→百分、RHOB kg/m3→g/cc）、
    物理量非法值裁剪、深度重复/乱序处理，并输出可追溯的清洗报告。

设计原则：保守——只在有把握时转换；检测到的修正写入报告，不静默丢数据。
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 单位归一候选列（按列名前缀/包含匹配）
CAL_COLS = ('CAL', 'CALI', 'CALX', 'CALY', 'CALS', 'HCAL', 'BS', 'BIT', 'DIA')
NEUTRON_COLS = ('NPHI', 'CNL', 'CNCF', 'PHIN', 'TNPH', 'NEUT')
DENSITY_COLS = ('RHOB', 'DEN', 'ZDEN', 'RHO')


def _num(s):
    return pd.to_numeric(s, errors='coerce')


def normalize_units(data: pd.DataFrame, report: dict) -> pd.DataFrame:
    """单位归一（保守规则，命中才转换）。"""
    data = data.copy()
    rep = report.setdefault('unit_fixes', {})
    # 1) 井径/钻头：mm → inch（中位数 > 50 视为 mm）
    for c in data.columns:
        cu = str(c).upper()
        if not any(k in cu for k in CAL_COLS):
            continue
        v = _num(data[c])
        med = v.median(skipna=True)
        if pd.notna(med) and med > 50:
            data[c] = v / 25.4
            rep[c] = 'mm→in (中位 %.1f)' % med
    # 2) 中子：分数 → 百分（中位 0<median<1.5）
    for c in data.columns:
        cu = str(c).upper()
        if not any(k in cu for k in NEUTRON_COLS):
            continue
        v = _num(data[c])
        med = v.median(skipna=True)
        if pd.notna(med) and 0 < med < 1.5 and v.max(skipna=True) <= 1.5:
            data[c] = v * 100.0
            rep[c] = 'fraction→percent (中位 %.3f)' % med
    # 3) 声波：us/m → us/ft（中位 > 250；程序内部按 us/ft 使用）
    for c in data.columns:
        cu = str(c).upper()
        if not (cu == 'DT' or cu.startswith(('DT_', 'DTC', 'DTCO', 'AC'))):
            continue
        v = _num(data[c])
        med = v.median(skipna=True)
        if pd.notna(med) and med > 250:
            data[c] = v / 3.28084
            rep[c] = 'us/m→us/ft (中位 %.0f)' % med
    # 4) 密度：kg/m3 → g/cc（中位 > 100）
    for c in data.columns:
        cu = str(c).upper()
        if not any(k in cu for k in DENSITY_COLS):
            continue
        v = _num(data[c])
        med = v.median(skipna=True)
        if pd.notna(med) and med > 100:
            data[c] = v / 1000.0
            rep[c] = 'kg/m3→g/cc (中位 %.0f)' % med
    return data


def clean_values(data: pd.DataFrame, report: dict) -> pd.DataFrame:
    """非法物理值清理（NaN 化，不删除行）。"""
    data = data.copy()
    rep = report.setdefault('value_fixes', {})
    # 通用：无穷大（布尔列跳过，避免 NaN 写入 bool）
    for c in data.columns:
        s = data[c]
        if pd.api.types.is_bool_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            f = s.astype(float)
            n_inf = int(np.isinf(f).sum())
            if n_inf:
                data.loc[np.isinf(f), c] = np.nan
                rep[c] = rep.get(c, 0) + n_inf
    # 曲线族裁剪（宽松上限，仅拦明显非法）
    bounds = {
        'GR': (0, 300), 'SGR': (0, 300), 'CGR': (0, 300), 'GRX': (0, 300),
        'RHOB': (0.8, 3.2), 'DEN': (0.8, 3.2), 'ZDEN': (0.8, 3.2),
        'CNL': (-20, 120), 'NPHI': (-20, 120), 'CNCF': (-20, 120),
        'PE': (0, 20), 'PEF': (0, 20),
        'DT': (30, 300), 'DTC': (30, 300),
        'RT': (1e-3, 1e6), 'LLD': (1e-3, 1e6), 'RD': (1e-3, 1e6),
        'SP': (-300, 600),
        'CAL': (3, 40), 'BS': (3, 40),
    }
    n_total = 0
    for c in data.columns:
        cu = str(c).upper()
        lo_hi = None
        for k, lh in bounds.items():
            if cu == k or cu.startswith(k + '_'):
                lo_hi = lh
                break
        if not lo_hi or pd.api.types.is_bool_dtype(data[c]):
            continue
        v = _num(data[c])
        bad = v.notna() & ((v < lo_hi[0]) | (v > lo_hi[1]))
        if bad.any():
            n_total += int(bad.sum())
            data.loc[bad, c] = np.nan
            rep[c] = rep.get(c, 0) + int(bad.sum())
    report['value_total'] = n_total
    return data


def clean_depth(data: pd.DataFrame, report: dict) -> pd.DataFrame:
    """深度去重/排序/非正深度处理。"""
    if 'MD' not in data.columns:
        return data
    data = data.copy()
    md = _num(data['MD'])
    n_nan = int(md.isna().sum())
    data = data.loc[~md.isna()].copy()
    md = md.loc[~md.isna()]
    if n_nan:
        report['depth_nan_dropped'] = n_nan
    # 非正深度 → NaN 行保留？深度非正无意义 → 丢弃
    npos = int((md <= 0).sum())
    if npos:
        data = data.loc[md > 0].copy()
        md = md.loc[md > 0]
        report['depth_nonpos_dropped'] = npos
    dup = int(md.duplicated().sum())
    if dup:
        keep = ~md.duplicated(keep='last')
        data = data.loc[keep.values].copy()
        md = md.loc[keep.values]
        report['depth_dup_dropped'] = dup
    if not md.is_monotonic_increasing:
        order = np.argsort(md.values, kind='mergesort')
        data = data.iloc[order].reset_index(drop=True)
        report['depth_sorted'] = True
    return data


_VENDOR_RESULT_COLS = ('POR', 'PORA', 'PORD', 'PORT', 'PORF', 'PORW', 'PORN',
                      'SW', 'SWIR', 'SH', 'SWT', 'SO')


def quarantine_vendor_results(data: pd.DataFrame, report: dict) -> pd.DataFrame:
    """隔离厂家"成果类"退化列：若 POR 中位≤0.02 或 SW 中位≥95（明显退化），
    且存在可自算的原始曲线（DEN/CNL/DT 或 RT），把厂家列改名 *_VENDOR，
    交由程序用原始曲线重算 PHI/Sw（用户 2026-10-31：RT 用最深阵列 RAL1）。
    """
    if data is None or len(data) == 0:
        return data
    rep = report.setdefault('vendor_quarantine', {})
    def _cov(c):
        return float(pd.to_numeric(data[c], errors='coerce').notna().mean()) if c in data.columns else 0.0
    _raw_ok = (_cov('DEN') + _cov('CNL') + _cov('DT') + _cov('RT')) > 0.20
    if not _raw_ok:
        return data
    deg = []
    if 'POR' in data.columns:
        v = pd.to_numeric(data['POR'], errors='coerce')
        nv = int(v.notna().sum())
        # 占比按**有效值**计算（全列含缺失会把占比稀释而漏判）
        if nv >= 10 and float(v.median()) <= 0.02 and float((v <= 0.02).sum()) / nv >= 0.70:
            deg.append('POR(中位%.3f)' % float(v.median()))
    if 'SW' in data.columns:
        v = pd.to_numeric(data['SW'], errors='coerce')
        nv = int(v.notna().sum())
        if nv >= 10 and float(v.median()) >= 95.0 and float((v >= 95).sum()) / nv >= 0.70:
            deg.append('SW(中位%.0f)' % float(v.median()))
    if not deg:
        return data
    data = data.copy()
    renamed = []
    for c in list(data.columns):
        cu = str(c).upper()
        if cu in _VENDOR_RESULT_COLS or (cu.startswith('POR') and cu not in ('POROSITY_VALID',)):
            data = data.rename(columns={c: str(c) + '_VENDOR'})
            renamed.append(str(c))
    rep['degenerate'] = deg
    rep['renamed'] = renamed
    logger.info('厂家成果列隔离: %s；改名 %s → 程序用原始曲线重算', deg, renamed[:8])
    return data


def clean_well(data: pd.DataFrame, context: str = '') -> tuple:
    """清洗入口：返回 (cleaned_data, report)。异常不中断主流程。"""
    report = {'context': context, 'rows_in': int(len(data))}
    try:
        data = normalize_units(data, report)
        data = quarantine_vendor_results(data, report)
        data = clean_values(data, report)
        data = clean_depth(data, report)
    except Exception as e:
        report['error'] = '%s: %s' % (type(e).__name__, e)
        logger.warning('数据清洗失败（返回原数据）: %s', e)
        return data, report
    report['rows_out'] = int(len(data))
    report['ok'] = True
    logger.info('数据清洗: %s → %d 行；单位修正 %s；非法值 %d；深度修正 %s',
                report.get('rows_in'), report.get('rows_out'),
                list((report.get('unit_fixes') or {}).keys())[:6],
                report.get('value_total', 0),
                {k: report[k] for k in ('depth_dup_dropped', 'depth_sorted',
                                        'depth_nonpos_dropped', 'depth_nan_dropped')
                 if k in report})
    return data, report


def dump_report(report: dict, out_dir: str, well: str) -> str | None:
    try:
        import os
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, '%s_data_clean_report.json' % well)
        json.dump(report, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        return p
    except Exception:
        return None
