# -*- coding: utf-8 -*-
"""检索与知识 API（供 logInt / logGraph / 复核界面调用）。

接口：
    search(conn, q, limit)           全文检索（FTS5 + bm25 + snippet）
    get_cases(conn, region, well, limit)  相似井案例层
    get_facts(conn, subj=None, rel=None)  事实三元组
    get_entities(conn, kind, region)      实体
    stats(conn)                          资产统计
"""
from __future__ import annotations

from .db import stats  # noqa: F401
from .ingest import tokenize


def _fts_query(q: str) -> str:
    toks = [t for t in tokenize(q).split() if t.strip()]
    if not toks:
        return ''
    return ' '.join('"%s"' % t.replace('"', '""') for t in toks)


def search(conn, q: str, limit: int = 10, region: str | None = None) -> list:
    fq = _fts_query(q)
    if not fq:
        return []
    sql = """SELECT d.id, d.path, d.title, d.region, d.well,
                    snippet(doc_fts, 2, '[', ']', '…', 14) AS snip,
                    bm25(doc_fts) AS rank
             FROM doc_fts JOIN doc d ON d.id = doc_fts.doc_id
             WHERE doc_fts MATCH ?"""
    args = [fq]
    if region:
        sql += ' AND (d.region=? OR d.region LIKE ?)'
        args += [region, '%' + region + '%']
    sql += ' ORDER BY rank LIMIT ?'
    args.append(int(limit))
    rows = conn.execute(sql, args).fetchall()
    return [{'doc_id': r[0], 'path': r[1], 'title': r[2], 'region': r[3],
             'well': r[4], 'snippet': r[5], 'rank': round(float(r[6]), 4)} for r in rows]


def get_cases(conn, region: str | None = None, well: str | None = None, limit: int = 20) -> list:
    sql = 'SELECT id, well_id, top_m, base_m, formation, lithology, fluid, conf, source_doc FROM case_layer WHERE 1=1'
    args = []
    if well:
        sql += ' AND well_id LIKE ?'
        args.append('%' + well + '%')
    if region:
        sql += ' AND id IN (SELECT id FROM entity WHERE region=? AND kind="Case")'
        args.append(region)
    sql += ' ORDER BY conf DESC LIMIT ?'
    args.append(int(limit))
    return conn.execute(sql, args).fetchall()


def get_facts(conn, subj: str | None = None, rel: str | None = None, limit: int = 100) -> list:
    sql = 'SELECT subj, rel, obj, conf, source_doc FROM fact WHERE 1=1'
    args = []
    if subj:
        sql += ' AND subj LIKE ?'
        args.append('%' + subj + '%')
    if rel:
        sql += ' AND rel=?'
        args.append(rel)
    sql += ' ORDER BY conf DESC LIMIT ?'
    args.append(int(limit))
    return conn.execute(sql, args).fetchall()


def get_entities(conn, kind: str | None = None, region: str | None = None, limit: int = 200) -> list:
    sql = 'SELECT id, kind, name, canonical, region, conf FROM entity WHERE 1=1'
    args = []
    if kind:
        sql += ' AND kind=?'
        args.append(kind)
    if region:
        sql += ' AND region LIKE ?'
        args.append('%' + region + '%')
    sql += ' ORDER BY conf DESC LIMIT ?'
    args.append(int(limit))
    return conn.execute(sql, args).fetchall()


def browse_docs(conn, category: str | None = None, tech_major: str | None = None,
                tech_minor: str | None = None, limit: int = 200) -> list:
    """按知识体系（领域 × 大类 × 小类）浏览文档。任一条件为空表示不限制。"""
    sql = 'SELECT id, title, path, category, tech_type, tech_minor, country FROM doc WHERE 1=1'
    args = []
    if category:
        sql += ' AND category=?'
        args.append(category)
    if tech_major:
        sql += ' AND tech_type=?'
        args.append(tech_major)
    if tech_minor:
        sql += ' AND tech_minor=?'
        args.append(tech_minor)
    sql += ' ORDER BY category, tech_type, tech_minor, title LIMIT ?'
    args.append(int(limit))
    return conn.execute(sql, args).fetchall()


def taxonomy_stats(conn) -> dict:
    """统计各领域 × 大类 × 小类 的文档数，便于校验分类结构。"""
    rows = conn.execute(
        "SELECT category, tech_type, tech_minor, COUNT(*) FROM doc "
        "GROUP BY category, tech_type, tech_minor ORDER BY category, tech_type, tech_minor"
    ).fetchall()
    return [{'category': r[0], 'tech_major': r[1], 'tech_minor': r[2], 'n': r[3]} for r in rows]


def open_docs(conn, doc_id: str) -> dict:
    d = conn.execute('SELECT id, path, title, region, well, category FROM doc WHERE id=?', (doc_id,)).fetchone()
    if not d:
        return {}
    chunks = conn.execute('SELECT idx, text FROM chunk WHERE doc_id=? ORDER BY idx', (doc_id,)).fetchall()
    return {'id': d[0], 'path': d[1], 'title': d[2], 'region': d[3], 'well': d[4],
            'category': d[5], 'chunks': [{'idx': c[0], 'text': c[1]} for c in chunks]}
