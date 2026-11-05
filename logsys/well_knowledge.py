# -*- coding: utf-8 -*-
"""井目录知识总结：录井/岩心/XRD/XRF → 大致井段岩性+数值范围。

用户口径（2026-11-02/05）：录井与 XRD 不要求和测井深度精确对齐；
按大致井段总结岩性、矿物/元素数值范围，供 logInt/logKnow 调用。
"""
from __future__ import annotations
import json, logging
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger('logInt')


def _stats(s):
    x = pd.to_numeric(s, errors='coerce').dropna()
    if len(x) == 0:
        return None
    return {'n': int(len(x)), 'min': round(float(x.min()), 4),
            'median': round(float(x.median()), 4),
            'max': round(float(x.max()), 4)}


def _bins(top, base, bin_m=50.0):
    if not np.isfinite(top) or not np.isfinite(base):
        return []
    a = np.floor(top / bin_m) * bin_m
    b = np.ceil(base / bin_m) * bin_m
    return list(np.arange(a, b + 1e-6, bin_m))


def _xrd_type(cal, dol, qtz):
    if not np.isfinite(cal) or not np.isfinite(dol):
        return ''
    carb = cal + dol
    if carb >= 0.50:
        if dol > cal * 1.10:
            return 'dolomite'
        if cal > dol * 1.10:
            return 'limestone'
        return 'carbonate(mixed)'
    if np.isfinite(qtz) and qtz >= 0.35:
        return 'clastic(quartz-rich)'
    return 'mixed'


def build_well_knowledge(well_dir, well_name=None, bin_m=50.0):
    """读取井目录标定表，生成结构化知识摘要 dict。"""
    from .core_calib import read_well_calibration
    wd = Path(str(well_dir))
    wn = str(well_name or wd.name)
    out = {'well': wn, 'well_dir': str(wd), 'bin_m': bin_m,
           'sources': [], 'depth_note': '', 'lithology_zones': [],
           'xrd_bins': [], 'xrf_bins': [], 'swc_core': [], 'drill_core': [],
           'mudlog': {}, 'usage': []}
    try:
        cal = read_well_calibration(wd)
    except Exception as e:
        out['error'] = f'标定表读取失败: {e}'
        return out
    if cal is None or cal.empty:
        out['error'] = '未找到井目录标定表（SWC/XRD/XRF/Coredata）'
        return out
    out['sources'] = sorted(set(str(x) for x in cal.get('DEPTH_BASIS', [])
                                if str(x).strip()))
    # 1) 岩性大段（lithall）
    if 'CORE_ZONE_LITH' in cal.columns:
        z = cal[cal['CORE_ZONE_LITH'].notna()].copy()
        for _, r in z.iterrows():
            try:
                out['lithology_zones'].append({
                    'top': round(float(r['CORE_ZONE_TOP']), 1),
                    'base': round(float(r['CORE_ZONE_BASE']), 1),
                    'lith': str(r['CORE_ZONE_LITH']),
                    'source': 'lithall/录井-岩性大段'})
            except Exception:
                pass
    # 2) XRD 按录井深度 50m 段汇总（不做测井深度强制对齐）
    _mud = cal[cal.get('DEPTH_BASIS', 'LOG').eq('MUD')].copy() if 'DEPTH_BASIS' in cal else cal
    _xrd_cols = [c for c in ('XRD_CAL', 'XRD_DOL', 'XRD_QTZ', 'XRD_KFD', 'XRD_PLG')
                 if c in _mud.columns]
    if _xrd_cols:
        xrd = _mud[_mud[_xrd_cols].apply(pd.to_numeric, errors='coerce').notna().any(axis=1)]
        md = pd.to_numeric(xrd['MD'], errors='coerce')
        for top in _bins(float(md.min()), float(md.max()), bin_m):
            sub = xrd[(md >= top) & (md < top + bin_m)]
            if sub.empty:
                continue
            st = {c: _stats(sub[c]) for c in _xrd_cols if c in sub.columns}
            if not st:
                continue
            _cal = st.get('XRD_CAL', {}).get('median', np.nan)
            _dol = st.get('XRD_DOL', {}).get('median', np.nan)
            _qtz = st.get('XRD_QTZ', {}).get('median', np.nan)
            out['xrd_bins'].append({
                'top': round(float(top), 1), 'base': round(float(top + bin_m), 1),
                'n': int(len(sub)), 'minerals': st,
                'lith_inferred': _xrd_type(_cal, _dol, _qtz),
                'depth_basis': 'mud_logging(approx)'})
    # 3) XRF 按录井深度 50m 段汇总
    _xrf_cols = [c for c in ('XRF_AL', 'XRF_FE', 'XRF_K', 'XRF_CA', 'XRF_SI')
                 if c in _mud.columns]
    if _xrf_cols:
        xrf = _mud[_mud[_xrf_cols].apply(pd.to_numeric, errors='coerce').notna().any(axis=1)]
        md = pd.to_numeric(xrf['MD'], errors='coerce')
        for top in _bins(float(md.min()), float(md.max()), bin_m):
            sub = xrf[(md >= top) & (md < top + bin_m)]
            if sub.empty:
                continue
            st = {c: _stats(sub[c]) for c in _xrf_cols if c in sub.columns}
            if st:
                out['xrf_bins'].append({
                    'top': round(float(top), 1), 'base': round(float(top + bin_m), 1),
                    'n': int(len(sub)), 'elements': st,
                    'depth_basis': 'mud_logging(approx)'})
    # 4) 井壁取芯 SWC（测井深度）与钻井取芯（录井深度）
    swc = cal[cal.get('DEPTH_BASIS', 'LOG').eq('LOG') & cal.get('CORE_LITH').notna()] \
        if 'CORE_LITH' in cal.columns else pd.DataFrame()
    if not swc.empty:
        for lith, g in swc.groupby('CORE_LITH'):
            out['swc_core'].append({'lith': str(lith), 'n': int(len(g)),
                                    'top': round(float(pd.to_numeric(g['MD'], errors='coerce').min()), 1),
                                    'base': round(float(pd.to_numeric(g['MD'], errors='coerce').max()), 1),
                                    'depth_basis': 'logging_depth'})
    if 'DRILL_CORE_LITH' in cal.columns and cal['DRILL_CORE_LITH'].notna().any():
        dc = cal[cal['DRILL_CORE_LITH'].notna()]
        for lith, g in dc.groupby('DRILL_CORE_LITH'):
            out['drill_core'].append({'lith': str(lith), 'n': int(len(g)),
                                      'top': round(float(pd.to_numeric(g['MD'], errors='coerce').min()), 1),
                                      'base': round(float(pd.to_numeric(g['MD'], errors='coerce').max()), 1),
                                      'depth_basis': 'mud_logging'})
    if 'DRILL_CORE_PHIE' in cal.columns:
        out['drill_core_phi'] = _stats(cal['DRILL_CORE_PHIE'])
    # 5) 录井图（若有）
    try:
        from .well_docs import find_masterlog_file, read_masterlog
        mp = find_masterlog_file(wd)
        if mp:
            mres = read_masterlog(wd)
            out['mudlog'] = {'found': True, 'file': Path(mp).name,
                             'lith_layers': len((mres or {}).get('lith') or []),
                             'gas_events': len((mres or {}).get('gas') or [])}
        else:
            out['mudlog'] = {'found': False,
                             'note': '井目录未发现标准 masterlog/录井图；岩性段以 lithall/SWC/XRD 近似。'}
    except Exception as e:
        out['mudlog'] = {'found': False, 'note': f'录井图读取跳过: {e}'}
    out['depth_note'] = ('录井/XRD/XRF 为录井深度，本摘要按大致井段统计，不强制与测井深度对齐；'
                         'SWC 为测井深度。用于 logInt 检索时按井段/岩性/数值范围引用。')
    out['usage'] = [f'{wn} XRD 方解石/白云石 数值范围', f'{wn} 录井岩性段',
                    f'{wn} 井壁取芯岩性', '巴西 Aram 碳酸盐岩 酸解 CO2']
    return out


def render_well_knowledge_md(k):
    """结构化知识 → 可入库 Markdown。"""
    L = [f"# {k.get('well')} 井目录知识摘要（录井/岩心/XRD/XRF）", '']
    L.append(f"- 井目录: {k.get('well_dir')}")
    L.append(f"- 来源: {', '.join(k.get('sources') or []) or '标定表'}")
    L.append(f"- 深度说明: {k.get('depth_note')}")
    if k.get('error'):
        L.append(f"- 错误: {k['error']}")
    zones = k.get('lithology_zones') or []
    if zones:
        L += ['', '## 1. 大致岩性段（录井/岩性大段）', '| 顶 | 底 | 岩性 | 来源 |', '|---|---|---|---|']
        for z in zones:
            L.append(f"| {z.get('top')} | {z.get('base')} | {z.get('lith')} | {z.get('source')} |")
    xb = k.get('xrd_bins') or []
    if xb:
        L += ['', '## 2. XRD 矿物（录井深度，按约 %.0fm 段，不强制对齐测井）' % k.get('bin_m', 50),
              '| 顶 | 底 | n | 方解石(min/中/max) | 白云石 | 石英 | 推断岩性 |',
              '|---|---|---|---|---|---|---|']
        for b in xb:
            m = b.get('minerals') or {}
            def _r(key):
                s = m.get(key) or {}
                return f"{s.get('min')}/{s.get('median')}/{s.get('max')}" if s else '-'
            L.append(f"| {b.get('top')} | {b.get('base')} | {b.get('n')} | {_r('XRD_CAL')} | {_r('XRD_DOL')} | {_r('XRD_QTZ')} | {b.get('lith_inferred')} |")
    xf = k.get('xrf_bins') or []
    if xf:
        L += ['', '## 3. XRF 元素（录井深度，按约 %.0fm 段）' % k.get('bin_m', 50),
              '| 顶 | 底 | n | Al(min/中/max) | Fe | K | Ca |',
              '|---|---|---|---|---|---|---|']
        for b in xf:
            e = b.get('elements') or {}
            def _r2(key):
                s = e.get(key) or {}
                return f"{s.get('min')}/{s.get('median')}/{s.get('max')}" if s else '-'
            L.append(f"| {b.get('top')} | {b.get('base')} | {b.get('n')} | {_r2('XRF_AL')} | {_r2('XRF_FE')} | {_r2('XRF_K')} | {_r2('XRF_CA')} |")
    if k.get('swc_core'):
        L += ['', '## 4. 井壁取芯（测井深度）', '| 岩性 | 点数 | 顶 | 底 |', '|---|---|---|---|']
        for s in k['swc_core']:
            L.append(f"| {s.get('lith')} | {s.get('n')} | {s.get('top')} | {s.get('base')} |")
    if k.get('drill_core'):
        L += ['', '## 5. 钻井取芯（录井深度）', '| 岩性 | 点数 | 顶 | 底 |', '|---|---|---|---|']
        for s in k['drill_core']:
            L.append(f"| {s.get('lith')} | {s.get('n')} | {s.get('top')} | {s.get('base')} |")
    if k.get('drill_core_phi'):
        p = k['drill_core_phi']
        L += ['', f"## 6. 钻井取芯孔隙度范围: {p.get('min')}–{p.get('max')}（中位 {p.get('median')}，n={p.get('n')}）"]
    ml = k.get('mudlog') or {}
    L += ['', '## 7. 录井图']
    if ml.get('found'):
        L.append(f"- 已发现: {ml.get('file')}，岩性层 {ml.get('lith_layers')}，气测事件 {ml.get('gas_events')}")
    else:
        L.append(f"- {ml.get('note', '未发现标准 masterlog')}")
    L += ['', '## 8. logInt 调用提示', '- 查询井名 + 井段/岩性关键词；本摘要用于区域/本井先验，不替代测井点级标定。']
    return '\n'.join(L)


def save_well_knowledge(well_dir, well_name=None, bin_m=50.0,
                        out_dir=None, write_well_dir=False):
    """生成并保存 JSON/Markdown，返回 (dict, md_path, json_path)。"""
    k = build_well_knowledge(well_dir, well_name, bin_m)
    md = render_well_knowledge_md(k)
    if out_dir is None:
        out_dir = Path(__file__).resolve().parent.parent / 'data' / 'kb' / 'well_knowledge'
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wn = k.get('well') or 'well'
    jp = out_dir / f'{wn}_knowledge_summary.json'
    mp = out_dir / f'{wn}_knowledge_summary.md'
    jp.write_text(json.dumps(k, ensure_ascii=False, indent=2), encoding='utf-8')
    mp.write_text(md, encoding='utf-8')
    if write_well_dir:
        try:
            Path(well_dir, f'{wn}_knowledge_summary.md').write_text(md, encoding='utf-8')
        except Exception:
            pass
    return k, mp, jp


def load_well_knowledge(well_name, root=None):
    """读取已生成的井目录知识摘要 JSON（供 logInt 直接调用）。"""
    if not well_name:
        return None
    if root is None:
        root = Path(__file__).resolve().parent.parent / 'data' / 'kb' / 'well_knowledge'
    p = Path(root) / f'{well_name}_knowledge_summary.json'
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None


def query_well_knowledge(well_name, keyword=''):
    """按井名/关键词返回知识摘要 Markdown（logInt 检索入口）。"""
    k = load_well_knowledge(well_name)
    if not k:
        return ''
    md = render_well_knowledge_md(k)
    if keyword and str(keyword) not in md:
        return ''
    return md
