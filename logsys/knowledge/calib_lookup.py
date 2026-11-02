# -*- coding: utf-8 -*-
"""区域标定查询/应用：从 kb.db region_calib 取某国家/区块的标定截止值。"""
from __future__ import annotations

import json
import os

BASE = r'D:\360\src'
DEFAULT_DB = os.path.join(BASE, 'data', 'kb', 'kb.db')


def region_cutoffs(conn, country: str | None = None, field: str | None = None) -> dict | None:
    """按国家+区块名（模糊）匹配区域标定；返回 {'cutoffs':..,'region':..,'n_wells':..} 或 None。"""
    if not country and not field:
        return None
    sql = ('SELECT country, region, wells, n_wells, cutoffs_json, metrics_json, conf '
           'FROM region_calib')
    where, args = [], []
    if country:
        where.append('country=?')
        args.append(country)
    if field:
        where.append('region LIKE ?')
        args.append('%' + str(field).split()[0] + '%')
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY n_wells DESC, n_points DESC'
    row = conn.execute(sql, args).fetchone()
    if row is None and country:
        row = conn.execute(
            'SELECT country, region, wells, n_wells, cutoffs_json, metrics_json, conf '
            'FROM region_calib WHERE country=? ORDER BY n_wells DESC', (country,)).fetchone()
    if row is None:
        return None
    try:
        cut = json.loads(row[4] or '{}')
    except Exception:
        return None
    if not cut:
        return None
    return {'cutoffs': cut, 'country': row[0], 'region': row[1], 'wells': row[2],
            'n_wells': row[3], 'metrics': json.loads(row[5] or '{}'), 'conf': row[6]}


def lookup_for_well(country: str | None, field: str | None,
                    db_path: str = DEFAULT_DB) -> dict | None:
    if not os.path.exists(db_path):
        return None
    try:
        from .db import connect
        conn = connect(db_path)
        return region_cutoffs(conn, country, field)
    except Exception:
        return None
