# -*- coding: utf-8 -*-
"""案例层（case_layer）入库：把本地真值层表（SLAM / 成果表 / RUSH）自动转成区域知识案例。

对应 kb.db 的 case_layer 表：well_id / top_m / base_m / formation / lithology / fluid /
evidence_json / source_doc / conf。同时补 entity（Well）与 fact（井-国家 LOCATED_IN）。
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from ..calibrate import load_truths

FT_TO_M = 0.3048


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def upsert_well_cases(conn, well_id: str, truth_file: str, kind: str, unit: str = 'm',
                      conf: float = 0.9, country: str = '', region: str = '') -> dict:
    truth = load_truths(truth_file, kind)
    if len(truth) == 0:
        return {'ok': 0, 'fail': 1, 'error': 'empty truth'}
    if unit.lower() == 'ft':
        truth['TOP'] = truth['TOP'] * FT_TO_M
        truth['BASE'] = truth['BASE'] * FT_TO_M
    src = os.path.basename(truth_file)
    n_ok = 0
    for _, r in truth.iterrows():
        top, base = float(r['TOP']), float(r['BASE'])
        fluid = str(r['FLUID'])
        lid = 'case_%s_%s' % (_sha1(well_id)[:8], _sha1('%s|%.3f|%.3f|%s' % (well_id, top, base, fluid))[:12])
        ev = json.dumps({'source_kind': kind, 'unit': unit, 'truth_file': truth_file},
                        ensure_ascii=False)
        try:
            conn.execute(
                'INSERT OR REPLACE INTO case_layer(id, well_id, top_m, base_m, formation, lithology,'
                ' fluid, evidence_json, source_doc, conf) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (lid, well_id, round(top, 3), round(base, 3), '', '', fluid, ev, src, float(conf)))
            n_ok += 1
        except Exception:
            continue
    # 井实体 + 国家事实（可追溯）
    import re as _re
    _canon = _re.sub(r'[\s_]+', '-', str(well_id).strip()).upper()
    eid = 'WELL:' + _canon
    conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json,'
                 ' source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                 (eid, 'Well', well_id, well_id, region or country,
                  json.dumps({'country': country}, ensure_ascii=False), src, float(conf)))
    if country:
        fid = 'fact_' + _sha1('%s|LOCATED_IN|%s' % (well_id, country))[:12]
        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, source_doc,'
                     ' source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                     (fid, well_id, 'LOCATED_IN', country, '{}', src, '', float(conf), 'case_import'))
    conn.commit()
    return {'ok': n_ok, 'fail': 0, 'layers': int(len(truth))}


def import_cases(conn, case_specs: list) -> dict:
    """case_specs: [{'well','truth','kind','unit','conf','country','region'}]"""
    total = {'ok': 0, 'fail': 0, 'wells': 0, 'errors': []}
    for spec in case_specs:
        well = spec['well']
        try:
            r = upsert_well_cases(conn, well, spec['truth'], spec['kind'],
                                  unit=spec.get('unit', 'm'), conf=float(spec.get('conf', 0.9)),
                                  country=spec.get('country', ''), region=spec.get('region', ''))
            total['ok'] += r['ok']
            total['fail'] += r['fail']
            total['wells'] += 1
            print('  案例 %-14s %d 层' % (well, r['ok']), flush=True)
        except Exception as e:
            total['fail'] += 1
            total['errors'].append('%s: %s' % (well, e))
            print('  案例 %-14s FAILED %s: %s' % (well, type(e).__name__, e), flush=True)
    return total
