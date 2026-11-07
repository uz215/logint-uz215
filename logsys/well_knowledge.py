# -*- coding: utf-8 -*-
"""井目录知识总结：录井/岩心/XRD/XRF → 大致井段岩性+数值范围。

用户口径（2026-11-02/05）：录井与 XRD 不要求和测井深度精确对齐；
按大致井段总结岩性、矿物/元素数值范围，供 logInt/logKnow 调用。
"""
from __future__ import annotations
import io, json, logging
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


def _read_well_info(well_dir, well_name):
    import glob
    wd = Path(str(well_dir))
    cands = [wd / f'{well_name}info.json'] if well_name else []
    cands += [Path(x) for x in glob.glob(str(wd / '*info.json'))]
    for p in cands:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _parse_plt(well_dir):
    import glob
    out = []
    for p in glob.glob(str(Path(well_dir) / '*Plt*')) + glob.glob(str(Path(well_dir) / '*PLT*')):
        if p.lower().endswith('.txt'):
            try:
                raw = io.open(p, 'rb').read()
                try:
                    txt = raw.decode('utf-16')
                except Exception:
                    txt = raw.decode('latin-1', errors='ignore')
                lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                for ln in lines:
                    parts = ln.replace('\t', ' ').split()
                    if len(parts) >= 3:
                        try:
                            a, b = float(parts[0]), float(parts[1])
                            out.append({'file': Path(p).name, 'top': a, 'base': b,
                                        'values': parts[2:]})
                        except Exception:
                            pass
            except Exception:
                pass
    return out


def _gas_anomalies(well_dir, well_name, top_n=20):
    import glob
    try:
        import lasio
    except Exception:
        return []
    res = []
    for p in glob.glob(str(Path(well_dir) / '*.las')):
        if not any(k in Path(p).name.lower() for k in ('gas', 'crom', 'analise')):
            continue
        try:
            las = lasio.read(p)
            df = las.df().reset_index()
            cs = [str(c) for c in df.columns]
            mcol = next((c for c in cs if c.upper() in ('MD', 'DEPT', 'DEPTH')), None)
            gcol = next((c for c in cs if c.upper() in ('C1', 'TGAS', 'TG', 'C1TG', 'TOTALGAS')), None)
            if not mcol or not gcol or len(df) < 20:
                continue
            md = pd.to_numeric(df[mcol], errors='coerce')
            g = pd.to_numeric(df[gcol], errors='coerce')
            v = g.dropna()
            if len(v) < 10:
                continue
            thr = float(np.nanpercentile(v.values, 90))
            m = (g >= thr) & g.notna() & md.notna()
            if not m.any():
                continue
            idx = np.where(m.values)[0]
            groups = []
            start = idx[0]; prev = idx[0]
            for i in idx[1:]:
                if i <= prev + 2:
                    prev = i
                else:
                    groups.append((start, prev)); start = i; prev = i
            groups.append((start, prev))
            for a, b in groups[:top_n]:
                sub = df.iloc[a:b + 1]
                res.append({'file': Path(p).name, 'curve': gcol,
                            'top': round(float(md.iloc[a]), 1),
                            'base': round(float(md.iloc[b]), 1),
                            'max': round(float(g.iloc[a:b + 1].max()), 3),
                            'median': round(float(g.iloc[a:b + 1].median()), 3),
                            'depth_basis': 'gas/mud logging (approx)',
                            'note': f'≥P90 {thr:.3f}'})
        except Exception:
            pass
    return res


def _layers_summary(well_name, results=None):
    import glob
    out = {'layers': 0, 'lithology': {}, 'interpretation': {}, 'fluid_intervals': []}
    cands = []
    if isinstance(results, dict):
        od = results.get('output_dir')
        if od:
            cands += glob.glob(str(Path(od) / '*_interpretation_layers.csv'))
    if not cands:
        cands = glob.glob(str(Path(__file__).resolve().parent.parent / 'output' / well_name / '*_interpretation_layers.csv'))
    if not cands:
        return out
    try:
        df = pd.read_csv(sorted(cands, key=lambda x: Path(x).stat().st_mtime)[-1], encoding='utf-8-sig')
    except Exception:
        return out
    out['layers'] = int(len(df))
    if 'LITHOLOGY' in df.columns:
        out['lithology'] = {str(k): int(v) for k, v in df['LITHOLOGY'].value_counts().items()}
    if 'INTERPRETATION' in df.columns:
        out['interpretation'] = {str(k): int(v) for k, v in df['INTERPRETATION'].value_counts().items()}
        for _, r in df.iterrows():
            if str(r.get('INTERPRETATION')) in ('OIL', 'GAS', 'GAS_OIL', 'WATER', 'DRY'):
                out['fluid_intervals'].append({
                    'top': round(float(r.get('TOP_MD')), 1),
                    'base': round(float(r.get('BASE_MD')), 1),
                    'lith': str(r.get('LITHOLOGY') or ''),
                    'interp': str(r.get('INTERPRETATION') or '')})
    return out


def _scan_geo_docs(well_dir, well_name):
    """从井目录日报/设计/阶段汇报中提取盆地、构造、凹陷及界面证据。"""
    import glob, os, re
    wd = Path(str(well_dir))
    basin_names = ('Santos', 'Campos', 'Espirito Santo', 'Espírito Santo', 'Sergipe', 'Alagoas', 'Potiguar', 'Recôncavo', 'Solimões')
    struct_names = ('Curacao', 'Curaçao', 'Aruba', 'Tortuga', 'Libra', 'BVE')
    out = {'basin': '', 'sag': '', 'structure': '', 'evidence': [],
           'contacts': []}
    files = []
    for p in sorted(wd.rglob('*')):
        if p.suffix.lower() not in ('.pdf', '.pptx'):
            continue
        low = p.name.lower()
        if any(k in low for k in ('日报', '跟踪', '阶段', 'dst', 'drilling', 'design',
                                  'workshop', 'report', '分析', '解释')):
            if '20140225' in str(p):
                continue
            files.append(p)
    for p in files[:12]:
        try:
            txt = ''
            if p.suffix.lower() == '.pdf':
                import fitz
                doc = fitz.open(str(p))
                for i in range(min(5, doc.page_count)):
                    txt += (doc[i].get_text() or '') + '\n'
                doc.close()
            else:
                from pptx import Presentation
                prs = Presentation(str(p))
                for s in list(prs.slides)[:20]:
                    for sh in s.shapes:
                        if hasattr(sh, 'text'):
                            txt += sh.text + '\n'
            if not txt:
                continue
            if well_name not in txt and '1-SPS-108' not in txt and 'Curacao' not in txt and 'Curaçao' not in txt:
                continue
            for name in basin_names:
                if name.lower() in txt.lower() and not out['basin']:
                    out['basin'] = 'Santos' if name.lower() == 'santos' else name
                    for ln in txt.splitlines():
                        if name.lower() in ln.lower():
                            out['evidence'].append(f'{p.name}: {ln.strip()[:200]}')
                            break
            for name in struct_names:
                if name.lower() in txt.lower() and not out['structure']:
                    out['structure'] = 'Curacao' if name.lower() in ('curacao', 'curaçao') else name
                    for ln in txt.splitlines():
                        if name.lower() in ln.lower() and ('构造' in ln or 'structure' in ln.lower()):
                            out['evidence'].append(f'{p.name}: {ln.strip()[:200]}')
                            break
            for pat, typ in (
                (r'(?:OWC|O/W\s*contact|oil[- ]water\s*contact|油水界面)', 'OWC'),
                (r'(?:GWC|G/W\s*contact|gas[- ]water\s*contact|气水界面)', 'GWC')):
                for m in re.finditer(pat, txt, re.I):
                    tail = txt[m.end():m.end() + 120]
                    dm = re.search(r'(-?\d{3,5}(?:\.\d+)?)\s*(m|ft|米|英尺)?', tail)
                    if dm:
                        try:
                            val = float(dm.group(1))
                            unit = (dm.group(2) or 'm').lower()
                            if unit in ('ft', '英尺'):
                                val = val * 0.3048
                            out['contacts'].append({'type': typ, 'depth': round(val, 1),
                                                    'unit': 'm', 'source': p.name,
                                                    'confidence': 0.6,
                                                    'evidence': (m.group(0) + tail[:80]).strip()})
                        except Exception:
                            pass
        except Exception:
            continue
    seen = set(); contacts = []
    for c in out['contacts']:
        k = (c['type'], c['depth'], c['source'])
        if k not in seen:
            seen.add(k); contacts.append(c)
    out['contacts'] = contacts
    return out


def _candidate_contacts(interp):
    """无试油明确界面时，从解释层表生成候选界面（低置信度，明确标注）。"""
    out = {'owc': None, 'gwc': None, 'contacts': []}
    fi = (interp or {}).get('fluid_intervals') or []
    oils = [x for x in fi if x.get('interp') in ('OIL', 'GAS_OIL')]
    gases = [x for x in fi if x.get('interp') in ('GAS', 'GAS_OIL')]
    waters = [x for x in fi if x.get('interp') == 'WATER']
    for name, src in (('owc', oils), ('gwc', gases)):
        if not src or not waters:
            continue
        shal_water = min(waters, key=lambda x: x.get('top') or 1e9)
        _above = [x for x in src if (x.get('base') or 0) <= (shal_water.get('top') or 1e9)]
        if not _above:
            continue
        deep_hc = max(_above, key=lambda x: x.get('base') or 0)
        if (deep_hc.get('base') or 0) <= (shal_water.get('top') or 1e9):
            dz = round(((deep_hc.get('base') or 0) + (shal_water.get('top') or 0)) / 2.0, 1)
            out[name] = {'depth': dz, 'unit': 'm', 'source': 'log_interpretation',
                         'confidence': 'low', 'note': '候选界面，非试油实测'}
            out['contacts'].append({'type': name.upper(), 'depth': dz,
                                    'source': 'log_interpretation(candidate)',
                                    'confidence': 'low'})
    return out


def _read_formation_tops(well_dir):
    """从井数据工作簿 Fm/Formation 表读取地层顶底。"""
    import glob
    try:
        import openpyxl
    except Exception:
        return []
    wd = Path(str(well_dir))
    xls = [p for p in sorted(wd.rglob('*.xlsx')) if '井数据' in p.name]
    if not xls:
        xls = sorted(wd.rglob('*.xlsx'))
    out = []
    for p in xls[:3]:
        try:
            wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
            for ws in wb.worksheets:
                if str(ws.title).lower() not in ('fm', 'formation', 'formations', '地层', '地层表', 'tops'):
                    continue
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
                if not rows:
                    continue
                hdr = [str(x or '').strip().lower() for x in rows[0]]
                def idx(*names):
                    for n in names:
                        if n in hdr:
                            return hdr.index(n)
                    return None
                ti = idx('top'); bi = idx('bottom', 'base'); fi = idx('zonename', 'formation', 'name', '地层')
                if ti is None or fi is None:
                    continue
                for r in rows[1:]:
                    try:
                        top = float(r[ti])
                        base = float(r[bi]) if bi is not None and bi < len(r) and r[bi] is not None else np.nan
                        name = str(r[fi] or '').strip()
                        if name:
                            out.append({'formation': name, 'top': round(top, 1),
                                        'base': (round(base, 1) if np.isfinite(base) else np.nan),
                                        'source': f'{p.name}:{ws.title}'})
                    except Exception:
                        pass
            wb.close()
        except Exception:
            pass
    # 主簿无 Fm 表时，回退地质设计 formation_tops
    if not out:
        try:
            from .well_docs import read_design
            _des = read_design(wd)
            for _x in (_des.get('formation_tops') or []):
                try:
                    out.append({'formation': str(_x.get('formation') or _x.get('name')),
                                'top': float(_x.get('depth') or _x.get('top')),
                                'base': np.nan,
                                'source': f'design:{(_des.get("sources") or [{}])[0].get("file", "design")}'})
                except Exception:
                    pass
        except Exception:
            pass
    # 去重/排序
    seen = set(); res = []
    for x in sorted(out, key=lambda z: z.get('top', 0)):
        k = (x.get('formation'), x.get('top'))
        if k not in seen:
            seen.add(k); res.append(x)
    return res


def _formation_at(depth, tops):
    try:
        d = float(depth)
    except Exception:
        return '未提供'
    hits = [t for t in (tops or []) if t.get('top') is not None and float(t['top']) <= d
            and (not np.isfinite(t.get('base', np.nan)) or d < float(t['base']))]
    return (hits[-1].get('formation') if hits else '未提供')


def build_well_knowledge(well_dir, well_name=None, bin_m=50.0, results=None):
    """读取井目录标定表，生成结构化知识摘要 dict。"""
    from .core_calib import read_well_calibration
    wd = Path(str(well_dir))
    wn = str(well_name or wd.name)
    out = {'well': wn, 'well_dir': str(wd), 'bin_m': bin_m,
           'sources': [], 'depth_note': '', 'lithology_zones': [],
           'xrd_bins': [], 'xrf_bins': [], 'swc_core': [], 'drill_core': [],
           'mudlog': {}, 'usage': [], 'hierarchy': {}, 'basic_data': {},
           'stratigraphy': {}, 'testing': {}, 'log_interpretation': {},
           'gas_show': [], 'oil_gas_show': [], 'engineering': [],
           'categories': {}}
    # 层级/基础数据/试油/气测（优先井信息+井目录文件）
    info = _read_well_info(wd, wn)
    h = info.get('井信息') or {}
    coords = info.get('坐标') or {}
    meas = info.get('测量记录') or {}
    dates = info.get('日期') or {}
    design = info.get('地质设计') or {}
    country = str(h.get('country') or '').strip()
    if country.lower() in ('br', 'brazil'):
        country = 'Brazil'
    _geo = _scan_geo_docs(wd, wn)
    _basin = str(h.get('basin') or design.get('basin') or _geo.get('basin') or '未填写')
    _sag = str(h.get('sag') or design.get('sag') or _geo.get('sag') or '未填写')
    _struct = str(h.get('structure') or design.get('structure') or _geo.get('structure') or '未填写')
    hierarchy = {'country': country or '未填写', 'basin': _basin,
                 'sag': _sag, 'structure': _struct,
                 'field': str(h.get('field_name') or h.get('field') or '未填写'),
                 'well': wn}
    out['hierarchy'] = hierarchy
    out['hierarchy_evidence'] = _geo.get('evidence') or []
    out['geo_scan_contacts'] = _geo.get('contacts') or []
    out['basic_data'] = {
        'country': hierarchy['country'], 'field': hierarchy['field'],
        'well': wn, 'company': h.get('company') or '',
        'coordinates': {k: coords.get(k) for k in ('latitude', 'longitude', 'x_coordinate', 'y_coordinate') if coords.get(k)},
        'bit_size': meas.get('bit_size') or '',
        'bit_program': meas.get('bit_program') or meas.get('bit_size') or '',
        'casing_record': meas.get('casing_record') or '',
        'mud_type': (info.get('泥浆信息') or {}).get('drilling_fluid_type') or '',
        'mud_density': (info.get('泥浆信息') or {}).get('drilling_fluid_density') or '',
        'mud_viscosity': (info.get('泥浆信息') or {}).get('drilling_fluid_viscosity') or '',
        'fluid_loss': (info.get('泥浆信息') or {}).get('drilling_fluid_loss') or '',
        'borehole_record': meas.get('borehole_record') or '',
        'spud_date': dates.get('spud_date') or '', 'td_date': dates.get('td_date') or '',
        'well_type': design.get('well_type') or '',
        'note': '坐标/井别/钻头程序/套管程序/日期等归基础数据；空值表示井信息未提供。'}
    out['testing'] = {'intervals': _parse_plt(wd), 'files': []}
    import glob as _glob
    out['testing']['files'] = [Path(x).name for x in _glob.glob(str(wd / '*'))
                               if any(k in Path(x).name.lower() for k in ('plt', 'dst', 'test', '试油', '试采', 'mdt', 'rft'))]
    _tops = _read_formation_tops(wd)
    out['gas_show'] = _gas_anomalies(wd, wn)
    for _g in out['gas_show']:
        _g['formation'] = _formation_at(_g.get('top'), _tops)
    out['log_interpretation'] = _layers_summary(wn, results)
    _cand = _candidate_contacts(out['log_interpretation'])
    _explicit = out.get('geo_scan_contacts') or []
    _allc = list(_explicit)
    for _c in (_cand.get('contacts') or []):
        if not any(x.get('type') == _c.get('type') and abs(float(x.get('depth', 0)) - _c['depth']) < 2.0
                   for x in _allc):
            _allc.append(_c)
    out['testing']['contacts'] = _allc
    out['testing']['owc'] = next((x for x in _allc if x.get('type') == 'OWC'), None) or _cand.get('owc')
    out['testing']['gwc'] = next((x for x in _allc if x.get('type') == 'GWC'), None) or _cand.get('gwc')
    _tops = _read_formation_tops(wd)
    if not _tops:
        for _src in (info.get('地层顶'), (info.get('地质设计') or {}).get('formation_tops')):
            if isinstance(_src, list):
                for _x in _src:
                    if isinstance(_x, dict) and _x.get('formation') and _x.get('depth') is not None:
                        _tops.append({'formation': str(_x['formation']),
                                      'top': float(_x['depth']), 'base': np.nan,
                                      'source': 'info/design'})
    out['stratigraphy'] = {
        'formation_tops': _tops,
        'target_formation': (info.get('地质设计') or {}).get('target_formation') or '',
        'formation_names': [x.get('formation') for x in _tops],
        'note': ('地层顶来自井数据 Fm/Formation 表或地质设计；逐条岩性知识带 formation；'
                 '无地层顶时标“未提供”。')}
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
                _top = round(float(r['CORE_ZONE_TOP']), 1)
                _base = round(float(r['CORE_ZONE_BASE']), 1)
                _cuts = sorted(set([_top, _base] +
                                   [float(t['top']) for t in (_tops or [])
                                    if _top < float(t['top']) < _base]))
                for _a, _b in zip(_cuts[:-1], _cuts[1:]):
                    if _b <= _a:
                        continue
                    out['lithology_zones'].append({
                        'top': round(_a, 1), 'base': round(_b, 1),
                        'lith': str(r['CORE_ZONE_LITH']),
                        'formation': _formation_at((_a + _b) / 2.0, _tops),
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
                'formation': _formation_at(top + bin_m / 2.0, _tops),
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
        swc = swc.copy()
        swc['_FM'] = swc['MD'].map(lambda d: _formation_at(d, _tops))
        for (lith, fm), g in swc.groupby(['CORE_LITH', '_FM']):
            _t0 = round(float(pd.to_numeric(g['MD'], errors='coerce').min()), 1)
            out['swc_core'].append({'lith': str(lith), 'n': int(len(g)),
                                    'top': _t0,
                                    'base': round(float(pd.to_numeric(g['MD'], errors='coerce').max()), 1),
                                    'formation': str(fm),
                                    'depth_basis': 'logging_depth'})
    if 'DRILL_CORE_LITH' in cal.columns and cal['DRILL_CORE_LITH'].notna().any():
        dc = cal[cal['DRILL_CORE_LITH'].notna()]
        dc = dc.copy()
        dc['_FM'] = dc['MD'].map(lambda d: _formation_at(d, _tops))
        for (lith, fm), g in dc.groupby(['DRILL_CORE_LITH', '_FM']):
            _t0 = round(float(pd.to_numeric(g['MD'], errors='coerce').min()), 1)
            out['drill_core'].append({'lith': str(lith), 'n': int(len(g)),
                                      'top': _t0,
                                      'base': round(float(pd.to_numeric(g['MD'], errors='coerce').max()), 1),
                                      'formation': str(fm),
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
    # 录井图知识（若有 masterlog）：五类知识补充/合并
    try:
        from .well_docs import find_masterlog_file
        from .mudlog_knowledge import extract_mudlog_knowledge
        _mp = find_masterlog_file(wd)
        if _mp:
            _mk = extract_mudlog_knowledge(_mp)
            out['mudlog'] = {'found': True, 'file': Path(_mp).name,
                             'basic_data': _mk.get('basic_data') or {},
                             'lithology': _mk.get('lithology') or [],
                             'gas_show': _mk.get('gas_show') or [],
                             'oil_gas_show': _mk.get('oil_gas_show') or [],
                             'engineering': _mk.get('engineering') or []}
            for _k, _v in (_mk.get('basic_data') or {}).items():
                if _v and not out['basic_data'].get(_k):
                    out['basic_data'][_k] = _v
            for _z in (_mk.get('lithology') or []):
                out['lithology_zones'].append({
                    'top': _z.get('depth'), 'base': _z.get('depth'),
                    'lith': _z.get('lith'),
                    'formation': _formation_at(_z.get('depth'), _tops),
                    'source': 'masterlog'})
            _mg = _mk.get('gas_show') or []
            for _x in _mg:
                _x['formation'] = _formation_at(_x.get('depth') or _x.get('top'), _tops)
            out['gas_show'].extend(_mg)
            _mo = _mk.get('oil_gas_show') or []
            for _x in _mo:
                _x['formation'] = _formation_at(_x.get('depth'), _tops)
            out['oil_gas_show'] = _mo
            _me = _mk.get('engineering') or []
            for _x in _me:
                _x['formation'] = _formation_at(_x.get('depth'), _tops)
            out['engineering'] = _me
    except Exception as _mle:
        logger.warning('录井图知识提取失败（跳过）: %s', _mle)

    out['categories'] = {
        'basic_data': out.get('basic_data') or {},
        'stratigraphy': out.get('stratigraphy') or {},
        'lithology': {'zones': out.get('lithology_zones') or [],
                      'xrd_bins': out.get('xrd_bins') or [],
                      'xrf_bins': out.get('xrf_bins') or [],
                      'swc_core': out.get('swc_core') or [],
                      'drill_core': out.get('drill_core') or []},
        'testing': out.get('testing') or {},
        'log_interpretation': out.get('log_interpretation') or {},
        'gas_show': out.get('gas_show') or [],
        'oil_gas_show': out.get('oil_gas_show') or [],
        'engineering': out.get('engineering') or [],
    }
    out['usage'] = [f'{wn} XRD 方解石/白云石 数值范围', f'{wn} 录井岩性段',
                    f'{wn} 井壁取芯岩性', '巴西 Aram 碳酸盐岩 酸解 CO2']
    return out


def render_well_knowledge_md(k):
    """结构化知识 → 可入库 Markdown。"""
    h = k.get('hierarchy') or {}
    _path = '/'.join(str(h.get(x) or '未分') for x in
                     ('country', 'basin', 'sag', 'structure', 'field', 'well'))
    L = [f"# {h.get('well') or k.get('well')} 井目录知识（{_path}）", '']
    L.append(f"- 知识层级: {_path}")
    if k.get('hierarchy_evidence'):
        L.append(f"- 层级依据: {'；'.join(str(x) for x in (k.get('hierarchy_evidence') or [])[:3])}")
    L.append(f"- 井目录: {k.get('well_dir')}")
    L.append(f"- 来源: {', '.join(k.get('sources') or []) or '标定表'}")
    L.append(f"- 深度说明: {k.get('depth_note')}")
    if k.get('error'):
        L.append(f"- 错误: {k['error']}")
    b = k.get('basic_data') or {}
    if b:
        L += ['', '## 0. 基础数据', '| 项 | 值 |', '|---|---|']
        for _k, _v in b.items():
            if _v not in (None, '', {}, []):
                L.append(f"| {_k} | {_v} |")
    st = k.get('stratigraphy') or {}
    if st:
        L += ['', '## 0b. 地层', f"- {st.get('note') or ''}"]
        if st.get('formation_tops'):
            L += ['| 地层 | 顶 | 底 | 来源 |', '|---|---|---|---|']
            for _t in st.get('formation_tops')[:30]:
                L.append(f"| {_t.get('formation')} | {_t.get('top')} | {_t.get('base')} | {_t.get('source')} |")
    zones = k.get('lithology_zones') or []
    if zones:
        L += ['', '## 1. 大致岩性段（录井/岩性大段）', '| 顶 | 底 | 地层 | 岩性 | 来源 |', '|---|---|---|---|---|']
        for z in zones:
            L.append(f"| {z.get('top')} | {z.get('base')} | {z.get('formation', '未提供')} | {z.get('lith')} | {z.get('source')} |")
    xb = k.get('xrd_bins') or []
    if xb:
        L += ['', '## 2. XRD 矿物（录井深度，按约 %.0fm 段，不强制对齐测井）' % k.get('bin_m', 50),
              '| 顶 | 底 | 地层 | n | 方解石(min/中/max) | 白云石 | 石英 | 推断岩性 |',
              '|---|---|---|---|---|---|---|---|']
        for b in xb:
            m = b.get('minerals') or {}
            def _r(key):
                s = m.get(key) or {}
                return f"{s.get('min')}/{s.get('median')}/{s.get('max')}" if s else '-'
            L.append(f"| {b.get('top')} | {b.get('base')} | {b.get('formation', '未提供')} | {b.get('n')} | {_r('XRD_CAL')} | {_r('XRD_DOL')} | {_r('XRD_QTZ')} | {b.get('lith_inferred')} |")
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
        L += ['', '## 4. 井壁取芯（测井深度）', '| 地层 | 岩性 | 点数 | 顶 | 底 |', '|---|---|---|---|---|']
        for s in k['swc_core']:
            L.append(f"| {s.get('formation', '未提供')} | {s.get('lith')} | {s.get('n')} | {s.get('top')} | {s.get('base')} |")
    if k.get('drill_core'):
        L += ['', '## 5. 钻井取芯（录井深度）', '| 地层 | 岩性 | 点数 | 顶 | 底 |', '|---|---|---|---|---|']
        for s in k['drill_core']:
            L.append(f"| {s.get('formation', '未提供')} | {s.get('lith')} | {s.get('n')} | {s.get('top')} | {s.get('base')} |")
    if k.get('drill_core_phi'):
        p = k['drill_core_phi']
        L += ['', f"## 6. 钻井取芯孔隙度范围: {p.get('min')}–{p.get('max')}（中位 {p.get('median')}，n={p.get('n')}）"]
    tst = k.get('testing') or {}
    if tst and (tst.get('intervals') or tst.get('files')):
        L += ['', '## 6b. 试油/测试', '| 文件 | 顶 | 底 | 数值 |', '|---|---|---|---|']
        for x in (tst.get('intervals') or [])[:20]:
            L.append(f"| {x.get('file')} | {x.get('top')} | {x.get('base')} | {x.get('values')} |")
        if tst.get('files'):
            L.append(f"- 相关文件: {', '.join(tst.get('files')[:10])}")
        for _ck, _cn in (('owc', 'OWC 油水界面'), ('gwc', 'GWC 气水界面')):
            _cv = tst.get(_ck)
            if _cv:
                L.append(f"- {_cn}: {_cv.get('depth')} {_cv.get('unit', 'm')}"
                         f"（来源 {_cv.get('source')}，置信度 {_cv.get('confidence')}）")
    li = k.get('log_interpretation') or {}
    if li:
        L += ['', '## 6c. 测井解释', f"- 层数: {li.get('layers')}；岩性: {li.get('lithology')}；流体: {li.get('interpretation')}"]
        fi = li.get('fluid_intervals') or []
        if fi:
            L.append('| 顶 | 底 | 岩性 | 解释 |')
            L.append('|---|---|---|---|')
            for x in fi[:15]:
                L.append(f"| {x.get('top')} | {x.get('base')} | {x.get('lith')} | {x.get('interp')} |")
    gs = k.get('gas_show') or []
    if gs:
        L += ['', '## 6d. 气测异常（含深度/地层）', '| 地层 | 文件 | 顶 | 底 | 峰值 | 中位 | 依据 |', '|---|---|---|---|---|---|---|']
        for x in gs[:20]:
            L.append(f"| {x.get('formation', '未提供')} | {x.get('file')} | {x.get('top')} | {x.get('base')} | {x.get('max')} | {x.get('median')} | {x.get('note')} |")
    ogs = k.get('oil_gas_show') or []
    if ogs:
        L += ['', '## 6e. 油气显示/油砂/级别', '| 地层 | 深度 | 级别 | 原文 |', '|---|---|---|---|']
        for x in ogs[:20]:
            L.append(f"| {x.get('formation', '未提供')} | {x.get('depth')} | {x.get('grade')} | {x.get('text')} |")
    eng = k.get('engineering') or []
    if eng:
        L += ['', '## 6f. 工程情况', '| 地层 | 深度 | 原文 |', '|---|---|---|']
        for x in eng[:20]:
            L.append(f"| {x.get('formation', '未提供')} | {x.get('depth')} | {x.get('text')} |")
    ml = k.get('mudlog') or {}
    L += ['', '## 7. 录井图']
    if ml.get('found'):
        L.append(f"- 已发现: {ml.get('file')}，岩性层 {ml.get('lith_layers')}，气测事件 {ml.get('gas_events')}")
    else:
        L.append(f"- {ml.get('note', '未发现标准 masterlog')}")
    L += ['', '## 8. logInt 调用提示', '- 查询井名 + 井段/岩性关键词；本摘要用于区域/本井先验，不替代测井点级标定。']
    return '\n'.join(L)


def save_well_knowledge(well_dir, well_name=None, bin_m=50.0,
                        out_dir=None, write_well_dir=False, results=None):
    """生成并保存 JSON/Markdown，返回 (dict, md_path, json_path)。"""
    k = build_well_knowledge(well_dir, well_name, bin_m, results=results)
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
    # 按国家/盆地/凹陷/构造/油田/井 + 分类落盘
    try:
        h = k.get('hierarchy') or {}
        _clean = lambda x: ''.join(ch for ch in str(x or '未分')
                                   if ch not in '\\/:*?"<>|').strip() or '未分'
        tax = out_dir.joinpath(*[_clean(h.get(x)) for x in
                                ('country', 'basin', 'sag', 'structure', 'field', 'well')])
        tax.mkdir(parents=True, exist_ok=True)
        _cats = k.get('categories') or {}
        for cname, cval in _cats.items():
            if not cval:
                continue
            (tax / f'{cname}.md').write_text(
                f"# {wn} / {cname}\n\n```json\n" +
                json.dumps(cval, ensure_ascii=False, indent=2)[:20000] + "\n```\n",
                encoding='utf-8')
        (tax / 'taxonomy.json').write_text(
            json.dumps({'hierarchy': h, 'categories': list(_cats.keys()),
                        'summary': str(mp)}, ensure_ascii=False, indent=2),
            encoding='utf-8')
    except Exception:
        pass
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


def ingest_well_knowledge_db(well_dir, well_name=None, results=None,
                             db_path=None, md_path=None):
    """把井目录知识摘要写入 kb.db（文档/FTS/实体），并更新 manifest。"""
    import hashlib, json, os, time
    from .knowledge.db import connect
    from .knowledge.ingest import ingest_markdown
    if md_path:
        mp = Path(md_path)
        k = load_well_knowledge(well_name) or {}
    else:
        k, mp, jp = save_well_knowledge(well_dir, well_name=well_name, results=results)
    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent / 'data' / 'kb' / 'kb.db'
    conn = connect(str(db_path))
    doc_id = ingest_markdown(conn, str(mp), force=True)
    conn.commit()
    try:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except Exception:
        pass
    try:
        _st = {
            'doc': int(conn.execute('SELECT count(*) FROM doc').fetchone()[0]),
            'chunk': int(conn.execute('SELECT count(*) FROM chunk').fetchone()[0]),
            'entity': int(conn.execute('SELECT count(*) FROM entity').fetchone()[0]),
            'fact': int(conn.execute('SELECT count(*) FROM fact').fetchone()[0]),
            'case_layer': int(conn.execute('SELECT count(*) FROM case_layer').fetchone()[0]),
            'clause': int(conn.execute('SELECT count(*) FROM clause').fetchone()[0]),
            'doubt': int(conn.execute('SELECT count(*) FROM doubt').fetchone()[0]),
        }
    except Exception:
        _st = {}
    conn.close()
    # manifest 在 DB 关闭后计算，确保 hash 是最终文件
    try:
        man = Path(__file__).resolve().parent.parent / 'data' / 'kb' / 'kb_manifest.json'
        data = json.loads(man.read_text(encoding='utf-8')) if man.exists() else {}
        p = Path(db_path)
        data['size_bytes'] = p.stat().st_size
        data['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        data['generated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        data['doc_count'] = _st.get('doc')
        if _st:
            data['stats'] = _st
        man.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        logger.warning('kb_manifest 更新失败: %s', e)
    return doc_id, k, mp
