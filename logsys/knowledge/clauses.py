# -*- coding: utf-8 -*-
"""标准条款入库：clauses.json → clause 表（可机读 rule_json，带来源）。"""
from __future__ import annotations

import hashlib
import json
import os


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]


def import_clauses(conn, src) -> int:
    """src: list[dict] 或 json 路径；返回入库条数。"""
    if isinstance(src, str):
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        items = json.load(open(src, encoding='utf-8'))
        source_doc = os.path.basename(src)
    else:
        items = src
        source_doc = 'inline'
    n = 0
    for it in items:
        std_no = str(it.get('std_no') or '')
        text = str(it.get('text') or '')
        if not std_no or not text:
            continue
        conn.execute('DELETE FROM clause WHERE std_no=?', (std_no,))
        cid = 'CLAUSE:' + _sha1(std_no + '|' + text)
        conn.execute(
            'INSERT OR REPLACE INTO clause(id, std_no, section, text, rule_type, rule_json, source_doc)'
            ' VALUES(?,?,?,?,?,?,?)',
            (cid, std_no, str(it.get('section') or ''), text, str(it.get('rule_type') or ''),
             json.dumps(it.get('rule_json') or {}, ensure_ascii=False), source_doc))
        n += 1
    conn.commit()
    return n
