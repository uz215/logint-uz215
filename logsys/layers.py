# -*- coding: utf-8 -*-
"""层段构建器（layer_builder）：把逐点解释结果聚合成"按层成果表"。

这是"层表"的新实现（旧 logInt 的 _build_interpretation_layers 在当前版本已不存在）。
设计目标：
- 唯一成层入口：点列 → 层表，口径可复现；
- 薄层保护：< min_thick 的薄层不跨流体族吞并；
- 层表与点列同源：均值/多数票均来自同一份点数据，禁止层表独立再判；
- 可追溯到点：每个层记录 POINTS 与 REVIEW_FLAG（灰区/薄层/平票）。

输入（DataFrame，至少含 MD 与 INTERPRETATION；其余列可选）：
    MD, INTERPRETATION, LITHOLOGY, PHI/POR, Sw/SW, RT, LITH_MC_CONF/PLATE_CONF
输出（DataFrame，每层一行）：
    LAYER_ID, TOP_MD, BASE_MD, THICKNESS, LITHOLOGY, INTERPRETATION,
    POINTS, PHI_MEAN, SW_MEAN, RT_MEAN, CONF_MEAN, REVIEW_FLAG, FLUID_FAMILY
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 流体族：薄层合并只在同族内允许（油/气不再互吞）
FLUID_FAMILY = {
    'GAS': 'HC_GAS', 'GAS_POSSIBLE': 'HC_GAS',
    'GAS_OIL': 'HC_GAS_OIL', 'OIL_GAS': 'HC_GAS_OIL',
    'OIL': 'HC_OIL', 'OIL_POSSIBLE': 'HC_OIL',
    'WATER': 'WATER', 'DRY': 'DRY', 'TIGHT': 'DRY',
    'NONRESERVOIR': 'NONRES', 'CASING': 'NONRES', '': 'NONRES',
}
# 平票时的确定性优先序（仅决定标签，不改点数据；并标 REVIEW）
TIE_PRIORITY = ['GAS', 'GAS_OIL', 'OIL', 'WATER', 'DRY', 'TIGHT', 'NonReservoir']
NONRES_LABELS = {'', 'NONRESERVOIR', 'CASING', 'NONE', 'NAN', '数据不足'}


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return None


def _norm_label(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ''
    s = str(v).strip()
    return '' if s.upper() in NONRES_LABELS else s


def build_layers(data: pd.DataFrame, min_thick: float = 0.4,
                 thin_absorb: float = 0.6, gap_break: float = 0.5,
                 depth_col: str = 'MD') -> pd.DataFrame:
    """逐点 → 层表。

    min_thick    : 最小成层厚度（与深度同单位，默认 m）
    thin_absorb  : 小于该厚度的层优先并入同族邻层（不跨族）
    gap_break    : 深度间断超过该值即断层的判据（默认 m）
    """
    if data is None or len(data) == 0 or depth_col not in data.columns:
        return pd.DataFrame()
    if 'INTERPRETATION' not in data.columns:
        return pd.DataFrame()

    df = data.reset_index(drop=True)
    md = pd.to_numeric(df[depth_col], errors='coerce')
    itp = df['INTERPRETATION'].map(_norm_label)
    lith = _col(df, 'LITHOLOGY', 'LITHOLOGY_MC')
    phi = _col(df, 'PHI', 'POR', 'PHI_DISP')
    sw = _col(df, 'Sw', 'SW', 'SW_DISP')
    rt = _col(df, 'RT', 'RD', 'LLD')
    conf = _col(df, 'PLATE_CONF', 'LITH_MC_CONF', 'INTERPRETATION_SCORE')

    # 1) 储层点：有结论且非 NonReservoir/casing
    res = itp.ne('') & md.notna()
    if not res.any():
        return pd.DataFrame()
    _md_sorted = np.sort(md.dropna().unique())
    _gstep = float(np.median(np.diff(_md_sorted))) if len(_md_sorted) > 1 else 0.0

    # 2) 切段：深度间断 / 非储层点 / 流体族变化 → 断点
    fam = itp.map(lambda x: FLUID_FAMILY.get(x.upper(), 'OTHER'))
    brk = res.ne(res.shift(fill_value=False))
    # 浮点容差：ft 井 0.5m≈1.6404199ft 与 gap_break 换算值可能因舍入相差 ~1e-15
    # 而被误判为深度间断（曾把 3 层切成 27 层），故用相对+绝对容差。
    brk |= (md.diff() > gap_break * (1 + 1e-6) + 1e-9)
    brk |= (fam.ne(fam.shift()) & res & res.shift(fill_value=False))
    seg_id = brk.cumsum()

    rows = []
    for sid, idx in df.groupby(seg_id, sort=True).groups.items():
        idx = list(idx)
        if not res.loc[idx].all():
            continue
        md_seg = md.loc[idx]
        top, base = float(md_seg.min()), float(md_seg.max())
        # 采样间隔 → 厚度（末点补一个间隔）
        step = float(np.nanmedian(np.diff(md_seg.values))) if len(idx) > 1 else _gstep
        thick = (base - top) + (step if step > 0 else 0.0)
        rows.append({'idx': idx, 'top': top, 'base': base, 'thick': thick,
                     'step': step if step > 0 else 0.0})

    if not rows:
        return pd.DataFrame()

    # 3) 薄层合并：< thin_absorb 的层并入同族邻层；跨族不合并（只标记）
    merged = []
    for r in rows:
        r['label'] = _majority(itp.loc[r['idx']])[0]
        r['family'] = FLUID_FAMILY.get(r['label'].upper(), 'OTHER')
        if merged:
            prev = merged[-1]
            adjacent = (r['top'] - prev['base']) <= gap_break * (1 + 1e-6) + 1e-9
            if r['thick'] < thin_absorb and adjacent and r['family'] == prev['family']:
                prev['idx'] += r['idx']
                prev['base'] = max(prev['base'], r['base'])
                prev['thick'] = (prev['base'] - prev['top']) + prev['step']
                continue
        merged.append(r)

    # 4) 生成层表字段
    out = []
    for i, r in enumerate(merged, start=1):
        idx = r['idx']
        lab, votes = _majority(itp.loc[idx])
        lith_lab = _majority(lith.loc[idx])[0] if lith is not None else ''
        flags = []
        # THIN = 低于薄层吸收阈值（未能并入邻层，需人工确认）；BELOW_MIN_THICK = 低于最小成层厚度
        if r['thick'] < thin_absorb:
            flags.append('THIN')
        if votes['tie']:
            flags.append('TIE')
        if lab.upper() in ('GAS_POSSIBLE', 'OIL_POSSIBLE'):
            flags.append('POSSIBLE')
        if r['thick'] < min_thick:
            flags.append('BELOW_MIN_THICK')
        out.append({
            'LAYER_ID': i,
            'TOP_MD': round(r['top'], 3),
            # BASE 为"排他下界"（top+thickness），保证单点层也有可查询区间；
            # 原实现 BASE=最后一个点深度，单点层 TOP==BASE，下游按 [TOP,BASE) 取数会取不到。
            'BASE_MD': round(r['top'] + r['thick'], 3),
            'THICKNESS': round(r['thick'], 3),
            'LITHOLOGY': lith_lab,
            'INTERPRETATION': lab,
            'FLUID_FAMILY': r['family'],
            'POINTS': len(idx),
            'PHI_MEAN': _mean(phi, idx),
            'SW_MEAN': _mean(sw, idx),
            'RT_MEAN': _mean(rt, idx),
            'CONF_MEAN': _mean(conf, idx),
            'REVIEW_FLAG': ';'.join(dict.fromkeys(flags)),
        })
    return pd.DataFrame(out)


def _majority(s: pd.Series) -> tuple:
    """返回 (多数标签, {'tie':bool,'counts':dict})；平票按 TIE_PRIORITY 取。"""
    vals = [v for v in s.astype(str) if v and v != 'nan']
    if not vals:
        return '', {'tie': False, 'counts': {}}
    vc = pd.Series(vals).value_counts()
    top = int(vc.max())
    winners = [str(k) for k, v in vc.items() if v == top]
    if len(winners) == 1:
        return winners[0], {'tie': False, 'counts': vc.to_dict()}
    winners.sort(key=lambda x: TIE_PRIORITY.index(x) if x in TIE_PRIORITY else 99)
    return winners[0], {'tie': True, 'counts': vc.to_dict()}


def _mean(col, idx):
    if col is None:
        return np.nan
    s = pd.to_numeric(col.loc[idx], errors='coerce').dropna()
    return round(float(s.mean()), 4) if len(s) else np.nan
