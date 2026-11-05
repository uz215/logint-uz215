# -*- coding: utf-8 -*-
"""岩心/XRD/XRF 标定读取与挂接（内部库，无独立入口）。

用户口径（2026-11-02）：井壁取芯描述（带深度）、XRD、XRF 是最好的标定材料；
岩心岩性优先级最高，用于校正点级岩性/剖面，并给出标定统计。
"""
from __future__ import annotations
import io, re, json
from pathlib import Path
import numpy as np
import pandas as pd

CORE_LITH_MAP = (
    ('dolomit', 'dolomite'), ('dolom', 'dolomite'), ('白云', 'dolomite'),
    ('anhydr', 'anhydrite'), ('硬石膏', 'anhydrite'),
    ('grainstone', 'limestone'), ('packstone', 'limestone'),
    ('wackestone', 'limestone'), ('mudstone', 'limestone'),
    ('stromatolite', 'limestone'), ('spherulitite', 'limestone'),
    ('boundstone', 'limestone'), ('floatstone', 'limestone'),
    ('rudstone', 'limestone'), ('breccia', 'limestone'),
    ('calcite', 'limestone'), ('carbonate', 'limestone'),
    ('limestone', 'limestone'), ('灰岩', 'limestone'),
    ('sandstone', 'sandstone'), ('砂岩', 'sandstone'),
    ('shale', 'shale'), ('泥岩', 'shale'),
)


def normalize_core_lith(value):
    s = str(value or '').strip().lower()
    if not s or s in ('nan', 'none', '-'):
        return ''
    for key, lith in CORE_LITH_MAP:
        if key in s:
            return lith
    return ''


def _num(v):
    try:
        return float(str(v).replace(',', '.'))
    except Exception:
        return np.nan


def _read_xlsx_sheets(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        out[ws.title] = rows
    wb.close()
    return out


def read_well_calibration(well_dir):
    """读井目录下的井壁取芯/XRD/XRF 标定表，返回按深度排序的 DataFrame。"""
    wd = Path(str(well_dir))
    rows = []
    # 1) 井数据工作簿：SWC Lithology / SWC&Core Final / XRD / XRF / lithall
    # 读取所有井数据/标定工作簿（主簿 SWC + XRD/XRF，可能分多个 xlsx）
    xlsx_files = [p for p in sorted(wd.rglob('*.xlsx'))
                  if ('井数据' in p.name or 'xrd_xrf' in p.name.lower())]
    # 主工作簿（井数据）已含 SWC+XRD+XRF；避免同时读取 xrd_xrf 附表导致重复
    _main_xlsx = [p for p in xlsx_files if '井数据' in p.name]
    if _main_xlsx:
        xlsx_files = _main_xlsx
    for xlsx in xlsx_files:
        try:
            sheets = _read_xlsx_sheets(xlsx)
            for sname, srows in sheets.items():
                low = sname.lower()
                if low in ('swc lithology', 'swc&core final'):
                    if not srows: continue
                    hdr = [str(x or '').strip() for x in srows[0]]
                    # 深度列：优先“深度”列（第二列），其次第一个数值列
                    di = None
                    for j, h in enumerate(hdr):
                        if h == '深度':
                            di = j
                            break
                    li = None
                    for j, h in enumerate(hdr):
                        if '岩性-English' in h or h == '岩性':
                            li = j
                            break
                    ti = None
                    for j, h in enumerate(hdr):
                        if str(h).strip().lower() == 'type':
                            ti = j
                            break
                    if di is None or li is None: continue
                    _is_core_final = ('core final' in low)
                    for r in srows[1:]:
                        dep = _num(r[di]) if di < len(r) else np.nan
                        lith = normalize_core_lith(r[li] if li < len(r) else '')
                        if not (np.isfinite(dep) and lith):
                            continue
                        _typ = (str(r[ti]).strip().lower()
                                if ti is not None and ti < len(r) else '')
                        # SWC=井壁取芯=测井深度；plug/空类型=钻井取芯=录井深度
                        _is_swc = (not _is_core_final) or ('swc' in _typ)
                        if _is_swc:
                            rows.append({'MD': dep, 'CORE_LITH': lith,
                                         'CORE_SOURCE': sname,
                                         'DEPTH_BASIS': 'LOG'})
                        else:
                            rows.append({'MD': dep,
                                         'DRILL_CORE_LITH': lith,
                                         'DRILL_CORE_SOURCE': sname + ':' + (_typ or 'core'),
                                         'DEPTH_BASIS': 'MUD'})
                elif low == 'xrd':
                    if not srows: continue
                    hdr = [str(x or '').strip() for x in srows[0]]
                    for r in srows[1:]:
                        dep = _num(r[0]) if r else np.nan
                        if not np.isfinite(dep): continue
                        rec = {'MD': dep}
                        for j, h in enumerate(hdr):
                            if j == 0 or j >= len(r): continue
                            v = _num(r[j])
                            if not np.isfinite(v): continue
                            key = ('XRD_' + h.upper().replace(' ', '_'))
                            rec[key] = v / 100.0 if h.upper() not in ('DEPTH',) else v
                        rec['XRD_SOURCE'] = sname
                        rec['DEPTH_BASIS'] = 'MUD'
                        rows.append(rec)
                elif low == 'xrf':
                    if not srows: continue
                    hdr = [str(x or '').strip() for x in srows[0]]
                    for r in srows[1:]:
                        dep = _num(r[0]) if r else np.nan
                        if not np.isfinite(dep): continue
                        rec = {'MD': dep}
                        for j, h in enumerate(hdr):
                            if j == 0 or j >= len(r): continue
                            hu = h.upper()
                            if hu in ('AL', 'FE', 'K', 'CA', 'SI', 'MG', 'TI', 'S'):
                                v = _num(r[j])
                                if np.isfinite(v):
                                    # 主量元素表头单位 %，其余 ppm；此处统一保留原值
                                    rec['XRF_' + hu] = v
                        rec['XRF_SOURCE'] = sname
                        rec['DEPTH_BASIS'] = 'MUD'
                        rows.append(rec)
                elif low == 'lithall':
                    if not srows: continue
                    hdr = [str(x or '').strip().lower() for x in srows[0]]
                    try:
                        ti, bi, ji = hdr.index('top'), hdr.index('bottom'), hdr.index('lith')
                    except ValueError:
                        continue
                    for r in srows[1:]:
                        try:
                            top, base = _num(r[ti]), _num(r[bi])
                        except Exception:
                            continue
                        if np.isfinite(top) and np.isfinite(base):
                            rows.append({'MD': top, 'CORE_ZONE_TOP': top,
                                         'CORE_ZONE_BASE': base,
                                         'CORE_ZONE_LITH': str(r[ji] or ''),
                                         'CORE_SOURCE': 'lithall',
                                         'DEPTH_BASIS': 'LOG'})
        except Exception:
            pass
    df = pd.DataFrame(rows)
    # 2) Coredata.txt：岩心孔隙度/骨架密度
    for p in wd.rglob('*oredata*.txt'):
        try:
            txt = io.open(p, encoding='utf-8', errors='ignore').read().splitlines()
            hdr = txt[0].strip().split('\t')
            recs = []
            for ln in txt[1:]:
                parts = ln.strip().split('\t')
                if len(parts) < 3: continue
                rec = {'MD': _num(parts[0]), 'DEPTH_BASIS': 'MUD'}
                for j, h in enumerate(hdr[1:], 1):
                    if j < len(parts):
                        rec['DRILL_CORE_' + h.strip().upper()] = _num(parts[j])
                if np.isfinite(rec.get('MD', np.nan)): recs.append(rec)
            if recs:
                df = pd.concat([df, pd.DataFrame(recs)], ignore_index=True, sort=False)
        except Exception:
            pass
    if df.empty:
        return df
    df = df.sort_values('MD').reset_index(drop=True)
    # 同一深度多行合并：岩性优先取非空，数值取均值
    agg = {}
    _text_cols = {'CORE_LITH', 'CORE_SOURCE', 'CORE_ZONE_LITH',
                  'DRILL_CORE_LITH', 'DRILL_CORE_SOURCE',
                  'XRD_SOURCE', 'XRF_SOURCE', 'Remarks'}
    if 'DEPTH_BASIS' not in df.columns:
        df['DEPTH_BASIS'] = 'LOG'
    df['DEPTH_BASIS'] = df['DEPTH_BASIS'].fillna('LOG')
    for c in df.columns:
        if c in ('MD', 'DEPTH_BASIS'):
            continue
        if c in _text_cols or not pd.api.types.is_numeric_dtype(df[c]):
            agg[c] = lambda s: next(
                (str(x) for x in s if str(x or '').strip() not in ('', 'nan', 'None')), '')
        else:
            agg[c] = 'mean'
    df = df.groupby([df['MD'].round(3), 'DEPTH_BASIS'], as_index=False).agg(agg)
    df = df.rename(columns={'MD': 'MD'})
    # 文本空串统一为 NaN，避免“有标定”假计数
    for _c in ('CORE_LITH', 'CORE_SOURCE', 'CORE_ZONE_LITH', 'DRILL_CORE_LITH',
               'DRILL_CORE_SOURCE', 'XRD_SOURCE', 'XRF_SOURCE'):
        if _c in df.columns:
            df[_c] = df[_c].replace('', np.nan)
    return df


def _pair_corr(data, xrd, xcol, dcol, shift, max_dt=0.5):
    """XRD 深度+shift 后与测井元素列配对，返回 (corr, n)。"""
    if xcol not in xrd.columns or dcol not in data.columns:
        return np.nan, 0
    x = xrd[['MD', xcol]].dropna()
    if len(x) < 10:
        return np.nan, 0
    md = pd.to_numeric(data['MD'], errors='coerce').values
    yv = pd.to_numeric(data[dcol], errors='coerce').values
    ok = np.isfinite(md) & np.isfinite(yv)
    md, yv = md[ok], yv[ok]
    if len(md) < 10:
        return np.nan, 0
    order = np.argsort(md)
    md, yv = md[order], yv[order]
    xs, ys = [], []
    for _, r in x.iterrows():
        target = float(r['MD']) + shift
        j = int(np.searchsorted(md, target))
        j = min(max(j, 0), len(md) - 1)
        if abs(md[j] - target) > max_dt:
            continue
        v = float(r[xcol])
        if np.isfinite(v) and np.isfinite(yv[j]):
            xs.append(v); ys.append(yv[j])
    if len(xs) < 6:
        return np.nan, 0
    a, b = np.asarray(xs), np.asarray(ys)
    if np.nanstd(a) < 1e-9 or np.nanstd(b) < 1e-9:
        return np.nan, 0
    return float(np.corrcoef(a, b)[0, 1]), len(a)


def _best_shift_for_xrd_subset(data, xrd, max_shift=10.0, step=0.25):
    """对一段 XRD 样本估计最佳位移；返回 (score, shift, details) 或 None。"""
    specs = [('XRD_CAL', ('CALCITE_QE', 'CALC_LIME_CO2')),
             ('XRD_DOL', ('DOLOMITE_QE', 'CALC_DOL_CO2')),
             ('XRD_QTZ', ('QUARTZ_QE', 'VOL_QUARTZ'))]
    active = []
    for xcol, dcols in specs:
        dcol = next((c for c in dcols if c in data.columns), None)
        if xcol in xrd.columns and dcol:
            active.append((xcol, dcol))
    if not active or len(xrd) < 6:
        return None
    best = None
    for shift in np.arange(-max_shift, max_shift + 1e-9, step):
        vals = []
        for xcol, dcol in active:
            r, n = _pair_corr(data, xrd, xcol, dcol, shift)
            if np.isfinite(r) and n >= 6:
                vals.append((max(-1.0, min(1.0, r)), n, xcol, dcol))
        if not vals:
            continue
        wsum = sum(v[1] for v in vals)
        score = sum(v[0] * v[1] for v in vals) / wsum if wsum else np.nan
        # 先验（用户定案）：通常 3–5m；超 5m 明显惩罚、过小也惩罚，
        # 避免弱相关噪声把位移选到 -10/+6
        _mag = abs(shift)
        score -= 0.15 * max(0.0, _mag - 5.0)
        score -= 0.03 * max(0.0, 3.0 - _mag)
        if np.isfinite(score) and (best is None or score > best[0]):
            best = (score, float(shift), vals)
    if best is None or best[0] < 0.12:
        return None
    details = {'score': round(best[0], 3), 'shift_m': best[1],
               'n_xrd': int(len(xrd)),
               'pairs': [{'xrd': v[2], 'log': v[3],
                          'corr': round(v[0], 3), 'n': v[1]} for v in best[2]]}
    return details


def estimate_xrd_depth_shifts(data, xrd, window_m=100.0,
                              max_shift=10.0, step=0.25,
                              anchor_m=150.0):
    """XRD/XRF 录井深度→测井深度：逐样本局部配准 + 分段锚点约束。

    用户 2026-11-02 定案：误差不是全井固定值，也不只换钻具时变；
    **起下钻一次都可能变**。故：
    - 每个样本在 ±window_m/2 窗内估局部偏移；
    - 同时按 anchor_m 计算局部锚点（稳定基线）；
    - 局部偏移必须在锚点附近（|Δ|≤1.0m）或局部相关性很强（score≥0.65）
      才允许采用，否则回退锚点；再做相邻中值平滑，防止噪声乱跳；
    - 通常 3–5m、上限 10m。
    返回 (shift_series, details)，shift 与 xrd 原索引对齐。
    """
    xrd = xrd.copy().sort_values('MD')
    orig_index = xrd.index
    xrd = xrd.reset_index(drop=True)
    md = pd.to_numeric(xrd['MD'], errors='coerce').values
    shifts = np.full(len(xrd), np.nan, dtype=float)
    scores = np.full(len(xrd), np.nan, dtype=float)
    details = {'mode': 'per_sample_local_anchored', 'window_m': window_m,
               'anchor_m': anchor_m, 'max_shift_m': max_shift,
               'samples': [], 'anchors': []}
    if len(xrd) < 6:
        return pd.Series(np.zeros(len(xrd)), index=orig_index), details
    # 1) 分段锚点（稳定基线；段间可不同，不假设全井固定）
    lo, hi = float(np.nanmin(md)), float(np.nanmax(md))
    edges = list(np.arange(lo, hi + anchor_m, anchor_m))
    if edges and edges[-1] < hi:
        edges.append(hi + 0.01)
    anchors = []
    for k in range(len(edges) - 1):
        a, b = edges[k], edges[k + 1]
        sub = xrd[(md >= a) & (md < b)]
        if len(sub) < 6:
            continue
        det = _best_shift_for_xrd_subset(data, sub, max_shift, step)
        anchors.append({'top': float(a), 'base': float(b),
                        'shift_m': (det['shift_m'] if det else np.nan),
                        'score': (det['score'] if det else np.nan),
                        'n': int(len(sub))})
    anchors = [x for x in anchors if np.isfinite(x['shift_m'])]
    details['anchors'] = anchors
    def _anchor_for(dd):
        for a in anchors:
            if a['top'] <= dd < a['base']:
                return a
        if anchors:
            return min(anchors, key=lambda a: min(abs(dd - a['top']),
                                                  abs(dd - a['base'])))
        return None
    # 2) 逐样本局部估计 + 锚点约束
    for i in range(len(xrd)):
        if not np.isfinite(md[i]):
            continue
        w = float(window_m)
        for _try in range(3):
            sub = xrd[(np.abs(md - md[i]) <= w / 2.0)]
            if len(sub) >= 6:
                break
            w *= 2.0
        det = _best_shift_for_xrd_subset(data, sub, max_shift, step)
        anc = _anchor_for(float(md[i]))
        _loc = det['shift_m'] if det else np.nan
        _sc = det['score'] if det else np.nan
        _use = np.nan
        if np.isfinite(_loc):
            if anc is None:
                _use = _loc
            elif abs(_loc - anc['shift_m']) <= 1.0:
                _use = _loc
            elif np.isfinite(_sc) and _sc >= 0.65:
                _use = _loc
            else:
                _use = anc['shift_m']
        elif anc is not None:
            _use = anc['shift_m']
        if np.isfinite(_use):
            shifts[i] = _use
            scores[i] = _sc if np.isfinite(_sc) else np.nan
            details['samples'].append({
                'idx': int(i), 'md': round(float(md[i]), 2),
                'n': int(len(sub)), 'local_shift': (round(_loc, 2)
                if np.isfinite(_loc) else None),
                'used_shift': round(float(_use), 2),
                'local_score': (round(_sc, 3) if np.isfinite(_sc) else None),
                'anchor_shift': (anc['shift_m'] if anc else None)})
    # 3) 插值 + 相邻中值平滑（保留持续跳变、抑制单点噪声）
    if np.isfinite(shifts).any():
        shifts = pd.Series(shifts).interpolate(limit_direction='both').values
        shifts = (pd.Series(shifts).rolling(3, center=True, min_periods=1)
                  .median().values)
    else:
        det = _best_shift_for_xrd_subset(data, xrd, max_shift, step)
        shifts[:] = det['shift_m'] if det is not None else 0.0
        details['global_fallback'] = det or {'shift_m': 0.0}
    shifts = np.clip(shifts, -max_shift, max_shift)
    details['shift_min'] = float(np.nanmin(shifts)) if len(shifts) else 0.0
    details['shift_max'] = float(np.nanmax(shifts)) if len(shifts) else 0.0
    details['n_estimated'] = int(np.isfinite(shifts).sum())
    return pd.Series(shifts, index=orig_index), details


def attach_core_calibration(data, well_dir, tolerance=0.30):
    """按深度挂接：取芯按测井深度直挂；XRD/XRF（录井深度）先配准再挂。"""
    if data is None or len(data) == 0 or 'MD' not in data.columns:
        return data
    try:
        cal = read_well_calibration(well_dir)
    except Exception:
        return data
    if cal is None or cal.empty:
        return data
    logger = __import__('logging').getLogger('logInt')
    d = data.copy()
    d['_MD_ORG'] = pd.to_numeric(d['MD'], errors='coerce')
    # 1) 取芯/岩心/大段：录井深度=测井深度，直接挂
    core = cal[cal.get('DEPTH_BASIS', 'LOG').eq('LOG')].dropna(subset=['MD'])
    if not core.empty:
        core = core.sort_values('MD')
        left = d[['_MD_ORG']].rename(columns={'_MD_ORG': 'MD'}).sort_values('MD')
        merged = pd.merge_asof(left, core, on='MD', direction='nearest',
                               tolerance=float(tolerance))
        for c in core.columns:
            if c in ('MD', 'DEPTH_BASIS'):
                continue
            if merged[c].notna().any():
                d[c] = merged[c].values
        n_core = int(d['CORE_LITH'].notna().sum()) if 'CORE_LITH' in d.columns else 0
        if n_core:
            logger.info('取芯标定挂接: %d/%d 点有井壁取芯SWC岩性（测井深度直挂）',
                        n_core, len(d))
    # 2) XRD/XRF：录井深度，分段局部配准后再挂（不是全井固定偏移）
    xrd = cal[cal.get('DEPTH_BASIS', 'MUD').eq('MUD')].dropna(subset=['MD']).copy()
    if not xrd.empty:
        try:
            _shifts, _det = estimate_xrd_depth_shifts(d, xrd)
            xrd = xrd.reset_index(drop=True)
            _shifts = pd.Series(_shifts.values, index=xrd.index)
            xrd['MD_LOG'] = pd.to_numeric(xrd['MD'], errors='coerce') + _shifts
            xrd = xrd.dropna(subset=['MD_LOG']).sort_values('MD_LOG').reset_index(drop=True)
            _xmd = pd.to_numeric(xrd['MD_LOG'], errors='coerce').values
            _dmd = pd.to_numeric(d['MD'], errors='coerce').values
            _pos = np.searchsorted(_xmd, _dmd)
            _pos = np.clip(_pos, 1, max(len(_xmd) - 1, 1))
            _left = np.clip(_pos - 1, 0, len(_xmd) - 1)
            _right = np.clip(_pos, 0, len(_xmd) - 1)
            _use = np.where(np.abs(_xmd[_left] - _dmd) <= np.abs(_xmd[_right] - _dmd),
                            _left, _right)
            _ok = np.abs(_xmd[_use] - _dmd) <= 0.75
            for c in xrd.columns:
                if c in ('MD', 'MD_LOG', 'DEPTH_BASIS') or not (
                        c.startswith('XRD_') or c.startswith('XRF_')
                        or c.startswith('DRILL_CORE_')):
                    continue
                _arr = pd.to_numeric(xrd[c], errors='coerce').values
                d[c] = np.where(_ok, _arr[_use], np.nan)
            _shift_arr = _shifts.values
            d['XRD_DEPTH_SHIFT'] = np.where(_ok, _shift_arr[_use], np.nan)
            logger.info('XRD/XRF 逐样本局部配准: %d段锚点，偏移 %.2f~%.2fm（%s）',
                        len(_det.get('segments') or []),
                        _det.get('shift_min', 0.0), _det.get('shift_max', 0.0),
                        _det.get('mode', ''))
            _n_dc = int(d['DRILL_CORE_LITH'].notna().sum()) if 'DRILL_CORE_LITH' in d.columns else 0
            if _n_dc:
                logger.info('钻井取芯挂接: %d 点 DRILL_CORE_LITH（录井深度，已局部配准）', _n_dc)
            try:
                d.attrs['xrd_depth_shift_details'] = _det
            except Exception:
                pass
        except Exception as _e_xrd:
            logger.warning('XRD/XRF 深度配准失败（跳过XRD/XRF挂接）: %s', _e_xrd)
    return d

def apply_core_lithology(data):
    """岩心岩性为最高优先级证据：有 CORE_LITH 的点直接改判并留痕。"""
    if data is None or 'CORE_LITH' not in data.columns:
        return data, 0
    m = data['CORE_LITH'].astype(str).str.strip().isin(
        ('limestone', 'dolomite', 'sandstone', 'shale', 'anhydrite'))
    n = int(m.sum())
    if n == 0:
        return data, 0
    old = data.loc[m, 'LITHOLOGY'].astype(str) if 'LITHOLOGY' in data.columns else None
    data.loc[m, 'LITHOLOGY'] = data.loc[m, 'CORE_LITH'].values
    if 'LITHOLOGY_MC' in data.columns:
        data.loc[m, 'LITHOLOGY_MC'] = data.loc[m, 'CORE_LITH'].values
    if 'LITH_MC_WHY' in data.columns:
        data.loc[m, 'LITH_MC_WHY'] = ('岩心标定: ' +
            (old[m].astype(str) + '→' + data.loc[m, 'CORE_LITH'].astype(str)
             if old is not None else data.loc[m, 'CORE_LITH'].astype(str)))
    if 'LITH_MC_CONF' in data.columns:
        data.loc[m, 'LITH_MC_CONF'] = 9.0
    return data, n
