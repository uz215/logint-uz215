# -*- coding: utf-8 -*-
"""区域邻井试油结论入库：GTO/RUSH 等成果表中提取的 DST 结论 → fact/entity。

输入 CSV 列：ZONE, WELL, DST_RESULT_RAW, RESULT_KIND, SOURCE, CONF
产出：
  entity Formation（层位）
  fact  subj=WELL:<井> rel=DST_RESULT obj=FORMATION:<层>:<类型> props={raw,source}
"""
from __future__ import annotations

import json
import os
import re


def _sha(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]


def import_offset_dst(conn, csv_path: str, default_country: str = 'Bangladesh') -> dict:
    import pandas as pd
    if not os.path.exists(csv_path):
        return {'ok': 0, 'fail': 1, 'error': 'not found'}
    d = pd.read_csv(csv_path, low_memory=False)
    n = 0
    for _, r in d.iterrows():
        zone = str(r.get('ZONE') or '').strip()
        well = str(r.get('WELL') or '').strip()
        raw = str(r.get('DST_RESULT_RAW') or '').strip()
        kind = str(r.get('RESULT_KIND') or '').strip() or 'OTHER'
        src = str(r.get('SOURCE') or '').strip()
        conf = float(r.get('CONF') or 0.8)
        if not zone or not well or not raw:
            continue
        # 过滤压缩噪声（长度过短/无意义）
        if len(raw) < 4:
            continue
        well_id = 'WELL:' + re.sub(r'[\s_]+', '-', well).upper()
        zone_id = 'FRM:' + re.sub(r'[\s/]+', '_', zone).upper()
        conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json,'
                     ' source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                     (zone_id, 'Formation', zone, zone_id, default_country, '{}', src, conf))
        fid = 'FACT:%s:DST:%s:%s' % (_sha(well_id)[:8], _sha(zone)[:8], kind)
        props = json.dumps({'raw': raw, 'result_kind': kind, 'country': default_country},
                           ensure_ascii=False)
        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, source_doc,'
                     ' source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                     (fid, well_id, 'DST_RESULT', '%s:%s' % (zone_id, kind), props,
                      src, 'p13 Table 4', conf, 'gto_table4'))
        n += 1
    conn.commit()
    return {'ok': n, 'fail': 0}


def get_dst_facts(conn, formation: str | None = None, kind: str | None = None) -> list:
    sql = "SELECT subj, obj, props_json, source_doc, conf FROM fact WHERE rel='DST_RESULT'"
    args = []
    if formation:
        sql += ' AND obj LIKE ?'
        args.append('%' + formation.upper() + '%')
    if kind:
        sql += ' AND obj LIKE ?'
        args.append('%:' + kind.upper())
    out = []
    for r in conn.execute(sql, args):
        props = json.loads(r[2] or '{}')
        out.append({'well': r[0], 'obj': r[1], 'raw': props.get('raw', ''),
                    'source': r[3], 'conf': r[4]})
    return out
