# -*- coding: utf-8 -*-
"""知识证据检索：给定井/层段（可选流体），检索相似案例 + 相关标准条款，作为解释证据栈成员。

用法（调试）：
    python -m logsys.knowledge.evidence --db data/kb/kb.db --well BET-1 --top 7653 --base 7677 --fluid MIXED
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .db import connect

BASE = r'D:\360\src'
DEFAULT_DB = os.path.join(BASE, 'data', 'kb', 'kb.db')


def similar_cases(conn, fluid: str | None = None, exclude_well: str | None = None,
                  limit: int = 5) -> list[dict]:
    sql = ('SELECT well_id, top_m, base_m, fluid, source_doc, conf FROM case_layer')
    args = []
    where = []
    if fluid:
        where.append('fluid=?')
        args.append(fluid)
    if exclude_well:
        where.append('well_id<>?')
        args.append(exclude_well)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY conf DESC LIMIT ?'
    args.append(int(limit))
    out = []
    for row in conn.execute(sql, args):
        out.append({'well': row[0], 'top_m': row[1], 'base_m': row[2], 'fluid': row[3],
                    'source': row[4], 'conf': row[5], 'kind': 'case'})
    return out


def relevant_clauses(conn, keywords: list[str], limit: int = 5) -> list[dict]:
    if not keywords:
        return []
    where = ' OR '.join(['section LIKE ? OR text LIKE ?' for _ in keywords])
    args = []
    for k in keywords:
        args += ['%%%s%%' % k, '%%%s%%' % k]
    sql = ('SELECT std_no, section, text, rule_type, rule_json FROM clause WHERE ' + where +
           ' LIMIT ?')
    args.append(int(limit))
    out = []
    for row in conn.execute(sql, args):
        out.append({'std_no': row[0], 'section': row[1], 'text': row[2],
                    'rule_type': row[3], 'rule_json': row[4], 'kind': 'clause'})
    return out


def evidence_for(conn, well: str, top_m: float, base_m: float,
                 fluid: str | None = None, cases_limit: int = 5, clauses_limit: int = 5) -> dict:
    """返回该层段的证据栈成员（案例 + 条款），均带来源与置信度。"""
    fluid = (fluid or '').upper() or None
    cases = similar_cases(conn, fluid=fluid, exclude_well=well, limit=cases_limit)
    kws = ['流体', '气层', '油层', '水层', '层表', '标定']
    if fluid == 'GAS':
        kws = ['气层', '流体', '标定']
    elif fluid == 'OIL':
        kws = ['油层', '流体', '标定']
    elif fluid == 'WATER':
        kws = ['水层', '流体']
    elif fluid in ('MIXED', 'GAS_OIL'):
        kws = ['混合', '流体', '复核']
    clauses = relevant_clauses(conn, kws, limit=clauses_limit)
    return {'well': well, 'top_m': top_m, 'base_m': base_m, 'fluid': fluid,
            'cases': cases, 'clauses': clauses,
            'summary': '案例 %d 条 / 条款 %d 条（来源均可追溯）' % (len(cases), len(clauses))}


def main(argv=None):
    ap = argparse.ArgumentParser(description='知识证据检索')
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--well', required=True)
    ap.add_argument('--top', type=float, required=True)
    ap.add_argument('--base', type=float, required=True)
    ap.add_argument('--fluid', default=None)
    args = ap.parse_args(argv)
    conn = connect(args.db)
    ev = evidence_for(conn, args.well, args.top, args.base, args.fluid)
    print(json.dumps(ev, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
