# -*- coding: utf-8 -*-
"""Masterlog（录井图）PDF 自动解析：深度标定 → 岩性层 + 气测异常/油气显示。

用户口径（2026-10-31）：
- 录井图是岩性真值的重要来源；大段可靠、薄层不一定准；深度与测井有 ±3–5m（≤10m/单根）系统误差；
- 录井图上的**气测异常 / Gas Break / 油气显示**是测井解释的重要证据；很多井没有数字气测，
  只能从录井图上读取 —— 本模块负责自动读取。

输出：
  <well>_masterlog_lith.csv   TOP_MD/BASE_MD/LITH/SOURCE/CONF
  <well>_masterlog_gas.csv    MD_START/MD_END/TYPE/TEXT/CONF
  <well>_masterlog_extract.json 摘要（深度标定质量/统计）
"""
from __future__ import annotations

import json
import os
import re

import numpy as np
import pandas as pd

# 岩性关键词（先长后短，避免 SST 误匹配）
LITH_MAP = [
    ('carbonaceous', 'carbonaceous_shale'),
    ('碳质', 'carbonaceous_shale'),
    ('coal', 'coal'), ('煤', 'coal'),
    ('anhydrite', 'anhydrite'), ('硬石膏', 'anhydrite'),
    ('halite', 'halite'), ('salt', 'halite'), ('盐岩', 'halite'),
    ('dolomite', 'dolomite'), ('白云岩', 'dolomite'),
    ('limestone', 'limestone'), ('石灰岩', 'limestone'), ('灰岩', 'limestone'),
    ('basalt', 'basalt'), ('volcanic', 'basalt'), ('玄武岩', 'basalt'),
    ('sandstone', 'sandstone'), ('sst', 'sandstone'), ('sand', 'sandstone'),
    ('砂岩', 'sandstone'),
    ('shale', 'shale'), ('claystone', 'shale'), ('mudstone', 'shale'),
    ('泥岩', 'shale'),
]
LITH_LEGEND = ('lithology symbols', 'sh - shale', 'sst - sandstone', 'legend')


def _spans(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l.get('spans', []):
                t = str(s.get('text', '')).strip()
                if t:
                    x0, y0, x1, y1 = s['bbox']
                    out.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                                'text': t, 'size': float(s.get('size') or 0)})
    return out


def _num(t):
    try:
        return float(t)
    except Exception:
        return None


def calibrate_depth(spans, page_h, depth_max_hint=None, page_w=None):
    """用边距数字（深度刻度）拟合 y→depth 线性关系。返回 (a,b,quality,fitted_points)。"""
    cands = []
    for s in spans:
        t = s['text']
        if not re.fullmatch(r'\d{2,5}(?:\.\d+)?', t):
            continue
        v = _num(t)
        if v is None:
            continue
        # 深度刻度通常在左右边距（按实际页宽）
        _w = float(page_w or 600.0)
        if s['x0'] < 0.22 * _w or s['x1'] > 0.80 * _w:
            if 0 <= v <= (depth_max_hint or 9000):
                cands.append((s['y0'], v))
    if len(cands) < 5:
        return None
    # 去掉重复 y
    cands = sorted(set((round(y, 1), v) for y, v in cands))
    ys = np.array([c[0] for c in cands], dtype=float)
    vs = np.array([c[1] for c in cands], dtype=float)
    # 只在单调性较好的子集上拟合：按 y 排序，去掉明显跳变
    order = np.argsort(ys)
    ys, vs = ys[order], vs[order]
    keep = [0]
    for i in range(1, len(vs)):
        if vs[i] >= vs[keep[-1]]:
            keep.append(i)
    if len(keep) < 5:
        return None
    ys, vs = ys[keep], vs[keep]
    a, b = np.polyfit(ys, vs, 1)       # depth = a*y + b
    pred = a * ys + b
    resid = np.abs(pred - vs)
    rng = float(vs.max() - vs.min()) or 1.0
    quality = float(1.0 - np.median(resid) / rng)
    return float(a), float(b), round(quality, 3), int(len(ys))


def _lith_of(text):
    low = text.lower()
    for kw, lith in LITH_MAP:
        if kw in low:
            return lith
    return None


def extract_masterlog(pdf_path: str, lith_out: str | None = None,
                      gas_out: str | None = None,
                      conf: float = 0.75, depth_max_hint: float | None = None,
                      depth_range: tuple | None = None) -> dict:
    import fitz
    doc = fitz.open(pdf_path)
    res = {'pdf': pdf_path, 'pages': doc.page_count, 'lith_layers': 0,
           'gas_events': 0, 'depth_calib': [], 'lith_dist': {}, 'gas_types': {}}
    lith_rows, gas_rows = [], []
    for pi in range(doc.page_count):
        page = doc[pi]
        W, H = page.rect.width, page.rect.height
        spans = _spans(page)
        cal = calibrate_depth(spans, H, depth_max_hint, page_w=W)
        # 深度标定可信性检查：斜率应使整页对应合理井段；否则按 hint 线性映射
        _hint_top, _hint_bot = (float(depth_range[0]), float(depth_range[1])) \
            if depth_range else (0.0, float(depth_max_hint or 5000.0))
        _ok_cal = False
        if cal:
            a0, b0, q0, n0 = cal
            _span = abs(a0) * H
            if q0 >= 0.9 and _span >= 0.5 * (_hint_bot - _hint_top) \
                    and _span <= 1.5 * (_hint_bot - _hint_top):
                _ok_cal = True
        if not _ok_cal:
            # 回退：按 hint 均匀映射（masterlog 常 1:500 单页覆盖全井）
            a = (_hint_bot - _hint_top) / max(H, 1.0)
            b = _hint_top - a * 0.0
            q, n = 0.0, 0
            cal = (a, b, q, n)
        a, b, q, n = cal
        res['depth_calib'].append({'page': pi, 'ok': True, 'quality': q, 'points': n,
                                   'top': round(a * 0 + b, 1),
                                   'bottom': round(a * H + b, 1)})
        def dep(y):
            return a * y + b
        # ---- 岩性描述（排除图例/表头）----
        desc = []
        for s in spans:
            t = s['text']
            low = t.lower()
            if any(k in low for k in LITH_LEGEND):
                continue
            if s['y0'] < 0.03 * H:
                continue
            if any(k in low for k in ('legend', 'symbols', 'abbreviation', 'lithology symbols')):
                continue
            lith = _lith_of(t)
            if lith:
                # 描述行通常较长；图例中的短线也命中关键词 → 要求长度或描述符
                if len(t) >= 6 or any(k in t for k in (':', '：', ',')):
                    desc.append((dep(s['y0']), lith, t))
        # 岩性描述点 → 连续层段：取相邻不同岩性描述点之间的深度区间
        desc.sort(key=lambda x: x[0])
        # 去重相邻同深度点
        _dd = []
        for d, lith, txt in desc:
            if not _dd or abs(d - _dd[-1][0]) > 1e-6:
                _dd.append((d, lith, txt))
        for _k in range(len(_dd)):
            d0, lith0, txt0 = _dd[_k]
            d1 = _dd[_k + 1][0] if _k + 1 < len(_dd) else min(_hint_bot, d0 + 20.0)
            if d1 - d0 < 0.5:
                continue
            lith_rows.append({'TOP_MD': d0, 'BASE_MD': d1, 'LITH': lith0,
                              'SOURCE': os.path.basename(pdf_path),
                              'CONF': conf, 'TEXT': txt0[:80]})
        # ---- 气测异常 / 油气显示 ----
        for s in spans:
            t = s['text']
            d = dep(s['y0'])
            # 带深度区间的 Gas Show
            m = re.search(r'(gas\s*show|气测异常|气测显示|全烃异常)\s*[:：]?\s*'
                          r'(\d+(?:\.\d+)?)\s*[-–~至]\s*(\d+(?:\.\d+)?)', t, flags=re.I)
            if m:
                gas_rows.append({'MD_START': float(m.group(2)), 'MD_END': float(m.group(3)),
                                 'TYPE': 'GAS_SHOW', 'TEXT': t[:120], 'CONF': 0.8})
                continue
            tl = t.lower()
            if s['y0'] < 0.03 * H:   # 表头/图例不算事件
                continue
            typ = None
            if 'no oil show' in tl or '无油显示' in t:
                typ = 'NO_OIL_SHOW'
            elif 'gas show' in tl or 'gas break' in tl or '气测异常' in t:
                typ = 'GAS_SHOW'
            elif 'fluorescence' in tl or '荧光' in t:
                typ = 'FLUORESCENCE'
            elif 'oil show' in tl or '油显示' in t:
                typ = 'OIL_SHOW'
            if typ:
                gas_rows.append({'MD_START': round(d, 1), 'MD_END': round(d, 1),
                                 'TYPE': typ, 'TEXT': t[:120], 'CONF': 0.7})
    # 清洗/合并
    lith = pd.DataFrame(lith_rows)
    if len(lith):
        lith = lith[lith['LITH'].notna()]
        # 层厚过滤：<0.5m 视为描述噪声；相邻同岩性再合并
        lith['TH'] = (lith['BASE_MD'] - lith['TOP_MD']).clip(lower=0)
        merged = []
        for _, r in lith.iterrows():
            if merged and r['LITH'] == merged[-1]['LITH'] and \
                    r['TOP_MD'] - merged[-1]['BASE_MD'] <= 3.0:
                merged[-1]['BASE_MD'] = max(merged[-1]['BASE_MD'], r['BASE_MD'])
            else:
                merged.append({'TOP_MD': r['TOP_MD'], 'BASE_MD': r['BASE_MD'],
                               'LITH': r['LITH'], 'SOURCE': r['SOURCE'],
                               'CONF': r['CONF']})
        lith = pd.DataFrame(merged)
        lith = lith[(lith['BASE_MD'] - lith['TOP_MD']) >= 0.5].reset_index(drop=True)
    gas = pd.DataFrame(gas_rows)
    if len(gas):
        gas = gas.drop_duplicates(subset=['MD_START', 'MD_END', 'TYPE']).sort_values('MD_START')
    # ---- 气测异常井段：区间事件按间隔≤1m 合并为井段；点事件仅作提示 ----
    zones = pd.DataFrame()
    if len(gas):
        _iv = gas[(gas['MD_END'] > gas['MD_START']) &
                  gas['TYPE'].isin(['GAS_SHOW', 'FLUORESCENCE'])].sort_values('MD_START')
        _zz = []
        for _, r in _iv.iterrows():
            if _zz and r['MD_START'] - _zz[-1]['MD_END'] <= 1.0:
                _zz[-1]['MD_END'] = max(_zz[-1]['MD_END'], r['MD_END'])
                _zz[-1]['EVENTS'] += 1
            else:
                _zz.append({'MD_START': float(r['MD_START']), 'MD_END': float(r['MD_END']),
                            'EVENTS': 1, 'TYPE': 'GAS_ZONE'})
        zones = pd.DataFrame(_zz)
        if len(zones):
            zones['THICK_M'] = (zones['MD_END'] - zones['MD_START']).round(2)
    # 输出
    out_dir = os.path.dirname(pdf_path)
    well = os.path.splitext(os.path.basename(pdf_path))[0].split('_')[0]
    if lith_out is None:
        lith_out = os.path.join(out_dir, '%s_masterlog_lith.csv' % well)
    if gas_out is None:
        gas_out = os.path.join(out_dir, '%s_masterlog_gas.csv' % well)
    if len(lith):
        lith.to_csv(lith_out, index=False, encoding='utf-8-sig')
    if len(gas):
        gas.to_csv(gas_out, index=False, encoding='utf-8-sig')
    # zones 与 gas/lith 输出同目录、同名井前缀（调用方指定输出路径时以输出文件名为准）
    _zdir = os.path.dirname(gas_out) if gas_out else (os.path.dirname(lith_out) if lith_out else out_dir)
    _zw = well
    if gas_out:
        _zw = os.path.basename(gas_out).replace('_masterlog_gas.csv', '')
    elif lith_out:
        _zw = os.path.basename(lith_out).replace('_masterlog_lith.csv', '')
    zones_out = os.path.join(_zdir, '%s_masterlog_gas_zones.csv' % _zw)
    if len(zones):
        zones.to_csv(zones_out, index=False, encoding='utf-8-sig')
    res.update({'lith_layers': int(len(lith)), 'gas_events': int(len(gas)),
                'lith_file': lith_out if len(lith) else None,
                'gas_file': gas_out if len(gas) else None,
                'lith_dist': {str(k): int(v) for k, v in
                              lith['LITH'].value_counts().items()} if len(lith) else {},
                'gas_types': {str(k): int(v) for k, v in
                              gas['TYPE'].value_counts().items()} if len(gas) else {},
                'gas_zones': int(len(zones)),
                'gas_zone_total_m': round(float(zones['THICK_M'].sum()), 1) if len(zones) else 0.0,
                'gas_zones_file': zones_out if len(zones) else None,
                'gas_zone_range': [round(float(zones['MD_START'].min()), 1),
                                   round(float(zones['MD_END'].max()), 1)] if len(zones) else None,
                'depth_range': [round(float(lith['TOP_MD'].min()), 1),
                                round(float(lith['BASE_MD'].max()), 1)] if len(lith) else None})
    jp = os.path.join(out_dir, '%s_masterlog_extract.json' % well)
    json.dump(res, open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    res['json'] = jp
    return res


def main(argv=None):
    import sys
    if not argv:
        print('用法: python -m logsys.masterlog <masterlog.pdf>')
        return 1
    print(json.dumps(extract_masterlog(argv[0]), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
