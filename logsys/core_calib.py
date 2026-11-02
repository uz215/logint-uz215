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
                    if di is None or li is None: continue
                    for r in srows[1:]:
                        dep = _num(r[di]) if di < len(r) else np.nan
                        lith = normalize_core_lith(r[li] if li < len(r) else '')
                        if np.isfinite(dep) and lith:
                            rows.append({'MD': dep, 'CORE_LITH': lith,
                                         'CORE_SOURCE': sname})
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
                                         'CORE_SOURCE': 'lithall'})
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
                rec = {'MD': _num(parts[0])}
                for j, h in enumerate(hdr[1:], 1):
                    if j < len(parts):
                        rec['CORE_' + h.strip().upper()] = _num(parts[j])
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
                  'XRD_SOURCE', 'XRF_SOURCE', 'Remarks'}
    for c in df.columns:
        if c == 'MD':
            continue
        if c in _text_cols or not pd.api.types.is_numeric_dtype(df[c]):
            agg[c] = lambda s: next(
                (str(x) for x in s if str(x or '').strip() not in ('', 'nan', 'None')), '')
        else:
            agg[c] = 'mean'
    df = df.groupby(df['MD'].round(3), as_index=False).agg(agg)
    df = df.rename(columns={'MD': 'MD'})
    # 文本空串统一为 NaN，避免“有标定”假计数
    for _c in ('CORE_LITH', 'CORE_SOURCE', 'CORE_ZONE_LITH', 'XRD_SOURCE', 'XRF_SOURCE'):
        if _c in df.columns:
            df[_c] = df[_c].replace('', np.nan)
    return df


def attach_core_calibration(data, well_dir, tolerance=0.30):
    """按深度把岩心/XRD/XRF 标定挂到测井 DataFrame。"""
    if data is None or len(data) == 0 or 'MD' not in data.columns:
        return data
    try:
        cal = read_well_calibration(well_dir)
    except Exception:
        return data
    if cal is None or cal.empty:
        return data
    # 只保留岩性/标定数值行，按 MD 排序
    cal = cal.dropna(subset=['MD']).sort_values('MD')
    d = data.copy()
    d['_MD_ORG'] = pd.to_numeric(d['MD'], errors='coerce')
    left = d[['_MD_ORG']].rename(columns={'_MD_ORG': 'MD'}).sort_values('MD')
    merged = pd.merge_asof(left, cal, on='MD', direction='nearest',
                           tolerance=float(tolerance))
    for c in cal.columns:
        if c == 'MD': continue
        if c not in merged.columns: continue
        d[c] = merged[c].values
    d = d.drop(columns=['_MD_ORG'])
    n_core = int(d['CORE_LITH'].notna().sum()) if 'CORE_LITH' in d.columns else 0
    if n_core:
        logger = __import__('logging').getLogger('logInt')
        logger.info('岩心标定挂接: %d/%d 点有井壁取芯岩性；XRD/XRF 列已附加', n_core, len(d))
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
