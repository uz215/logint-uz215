# -*- coding: utf-8 -*-
"""数据充分性门禁（P1 诊断项）。

诊断报告指出：RASHIDPUR_13 输入仅约 15.7% 覆盖，程序仍“成功”出成果。
本模块对裸眼段/目标井段做充分性评估，输出 OK / DEGRADED / INSUFFICIENT，
并给出必需曲线缺失与覆盖率，供 run_status、决策报告与批量回归使用。

阈值（可配置）：
  OK：核心曲线覆盖率 ≥ 0.80（GR、RT、孔隙度组）
  DEGRADED：核心覆盖率 ≥ 0.50
  INSUFFICIENT：< 0.50
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

CORE = {
    'GR': ['GR', 'GRX', 'SGR', 'CGR'],
    'RT': ['RT', 'LLD', 'RD', 'RAL5', 'RAL1', 'M2RX', 'ILD'],
    'POROSITY': ['PHI', 'POR', 'RHOB', 'DEN', 'CNL', 'NPHI', 'DT'],
}


def _coverage(data: pd.DataFrame, names: list) -> float:
    if data is None or len(data) == 0:
        return 0.0
    for c in names:
        if c in data.columns:
            v = pd.to_numeric(data[c], errors='coerce')
            cov = float(v.notna().mean())
            if cov > 0:
                return cov
    return 0.0


def evaluate(data: pd.DataFrame, interval: dict | None = None,
             ok_thr: float = 0.80, degraded_thr: float = 0.50) -> dict:
    out = {'ok_thr': ok_thr, 'degraded_thr': degraded_thr,
           'curve_coverage': {}, 'missing': [], 'rows': 0,
           'depth_range': None, 'coverage_rows': None, 'status': 'INSUFFICIENT',
           'reasons': []}
    if data is None or len(data) == 0:
        out['reasons'].append('无数据')
        return out
    d = data
    if interval and interval.get('top') is not None and 'MD' in d.columns:
        md = pd.to_numeric(d['MD'], errors='coerce')
        d = d[(md >= float(interval['top'])) & (md <= float(interval['bottom']))]
        out['interval'] = interval
    out['rows'] = int(len(d))
    if out['rows'] == 0:
        out['reasons'].append('目标井段无数据点')
        return out
    md = pd.to_numeric(d['MD'], errors='coerce') if 'MD' in d.columns else pd.Series(dtype=float)
    out['depth_range'] = [round(float(md.min()), 1), round(float(md.max()), 1)] if md.notna().any() else None
    # 逐组覆盖率
    for g, names in CORE.items():
        cov = _coverage(d, names)
        out['curve_coverage'][g] = round(cov, 3)
        if cov <= 0:
            out['missing'].append(g)
    # 核心点覆盖率：同时具备 GR、RT、孔隙度组
    def _valid(names):
        for c in names:
            if c in d.columns:
                v = pd.to_numeric(d[c], errors='coerce').notna()
                if v.any():
                    return v
        return pd.Series(False, index=d.index)
    vgr = _valid(CORE['GR']); vrt = _valid(CORE['RT']); vpor = _valid(CORE['POROSITY'])
    core = (vgr & vrt & vpor)
    out['coverage_rows'] = round(float(core.mean()), 4)
    # 状态
    min_cov = min(out['curve_coverage'].values()) if out['curve_coverage'] else 0.0
    if core.mean() >= ok_thr and min_cov >= ok_thr:
        out['status'] = 'OK'
    elif core.mean() >= degraded_thr:
        out['status'] = 'DEGRADED'
        if out['missing']:
            out['reasons'].append('缺少核心曲线组: %s' % out['missing'])
        out['reasons'].append('核心点覆盖率 %.1f%% < %.0f%%' % (100 * core.mean(), 100 * ok_thr))
    else:
        out['status'] = 'INSUFFICIENT'
        if out['missing']:
            out['reasons'].append('缺少核心曲线组: %s' % out['missing'])
        out['reasons'].append('核心点覆盖率 %.1f%% < %.0f%%（数据不足，结论仅供参考）' % (
            100 * core.mean(), 100 * degraded_thr))
    return out


def write(report: dict, out_dir: str, well: str) -> str | None:
    try:
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, '%s_data_sufficiency.json' % well)
        json.dump(report, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        return p
    except Exception:
        return None
