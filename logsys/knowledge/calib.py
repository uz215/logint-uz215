# -*- coding: utf-8 -*-
"""区域标定知识入库：data/calibration/regions/*.json → region_calib 表。"""
from __future__ import annotations

import hashlib
import json
import os


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]


def import_region_calib(conn, src_dir: str) -> int:
    if not os.path.isdir(src_dir):
        return 0
    cols = {r[1] for r in conn.execute('PRAGMA table_info(region_calib)')}
    if not cols:
        raise RuntimeError('region_calib 表不存在（请升级 kb schema）')
    n = 0
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith('.json'):
            continue
        p = os.path.join(src_dir, fn)
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'calibrated' not in d:
            continue
        rid = 'RCAL:' + _sha('%s|%s' % (d.get('country'), d.get('region')))
        conn.execute(
            'INSERT OR REPLACE INTO region_calib(id, country, region, wells, n_wells, n_points,'
            ' cutoffs_json, metrics_json, source_doc, conf) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (rid, d.get('country', ''), d.get('region', ''),
             ','.join(d.get('wells') or []), int(d.get('n_wells') or 0),
             int(d.get('n_points') or 0),
             json.dumps(d['calibrated'].get('cutoffs') or {}, ensure_ascii=False),
             json.dumps({'default_hc': d['default'].get('acc_hc'),
                         'calibrated_hc': d['calibrated'].get('acc_hc'),
                         'default_all': d['default'].get('acc_all'),
                         'calibrated_all': d['calibrated'].get('acc_all')},
                        ensure_ascii=False),
             fn, float(d.get('conf', 0.8))))
        n += 1
    conn.commit()
    return n


def get_region_calib(conn, country: str | None = None, region: str | None = None) -> list:
    sql = 'SELECT country, region, wells, n_wells, n_points, cutoffs_json, metrics_json, conf FROM region_calib'
    where, args = [], []
    if country:
        where.append('country=?')
        args.append(country)
    if region:
        where.append('region LIKE ?')
        args.append('%' + region + '%')
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY n_wells DESC'
    out = []
    for r in conn.execute(sql, args):
        out.append({'country': r[0], 'region': r[1], 'wells': r[2], 'n_wells': r[3],
                    'n_points': r[4], 'cutoffs': json.loads(r[5] or '{}'),
                    'metrics': json.loads(r[6] or '{}'), 'conf': r[7]})
    return out
