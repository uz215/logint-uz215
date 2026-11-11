# -*- coding: utf-8 -*-
"""kb.db 模式与连接（SQLite + FTS5）。

设计（对应建设方案 L3 知识层）：
  doc        文档（来源可追溯：path/hash/mtime）
  chunk      文档块（正文保留原文；FTS 用 jieba 预分词）
  entity     实体（kind: Country/Basin/Block/Field/Well/Formation/Lithology/Fluid/Param/Clause/Case）
  fact       事实三元组（subj-rel-obj + source_doc/source_loc/conf）
  case_layer 案例层（井×层×岩性×流体×证据）
  clause     标准条款（可机读 rule_json）
  doubt      待审核/冲突队列
  meta       版本与构建信息
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);

CREATE TABLE IF NOT EXISTS doc(
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE,
    title TEXT,
    category TEXT,
    region TEXT,
    country TEXT,
    well TEXT,
    tech_type TEXT,
    sha1 TEXT,
    mtime REAL,
    chars INTEGER,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS chunk(
    id TEXT PRIMARY KEY,
    doc_id TEXT,
    idx INTEGER,
    text TEXT,
    chars INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunk(doc_id);

CREATE TABLE IF NOT EXISTS entity(
    id TEXT PRIMARY KEY,
    kind TEXT,
    name TEXT,
    canonical TEXT,
    region TEXT,
    props_json TEXT,
    source_doc TEXT,
    conf REAL
);
CREATE INDEX IF NOT EXISTS idx_entity_kind ON entity(kind);
CREATE INDEX IF NOT EXISTS idx_entity_name ON entity(name);

CREATE TABLE IF NOT EXISTS fact(
    id TEXT PRIMARY KEY,
    subj TEXT,
    rel TEXT,
    obj TEXT,
    props_json TEXT,
    source_doc TEXT,
    source_loc TEXT,
    conf REAL,
    extractor TEXT
);
CREATE INDEX IF NOT EXISTS idx_fact_subj ON fact(subj);
CREATE INDEX IF NOT EXISTS idx_fact_rel ON fact(rel);

CREATE TABLE IF NOT EXISTS case_layer(
    id TEXT PRIMARY KEY,
    well_id TEXT,
    top_m REAL,
    base_m REAL,
    formation TEXT,
    lithology TEXT,
    fluid TEXT,
    evidence_json TEXT,
    source_doc TEXT,
    conf REAL
);
CREATE INDEX IF NOT EXISTS idx_case_well ON case_layer(well_id);

CREATE TABLE IF NOT EXISTS region_calib(
    id TEXT PRIMARY KEY,
    country TEXT,
    region TEXT,
    wells TEXT,
    n_wells INTEGER,
    n_points INTEGER,
    cutoffs_json TEXT,
    metrics_json TEXT,
    source_doc TEXT,
    conf REAL
);
CREATE INDEX IF NOT EXISTS idx_rcal_region ON region_calib(region);

CREATE TABLE IF NOT EXISTS clause(
    id TEXT PRIMARY KEY,
    std_no TEXT,
    section TEXT,
    text TEXT,
    rule_type TEXT,
    rule_json TEXT,
    source_doc TEXT
);

CREATE TABLE IF NOT EXISTS doubt(
    id TEXT PRIMARY KEY,
    kind TEXT,
    subject TEXT,
    detail TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'open'
);

CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
    doc_id UNINDEXED, title, body, region, well, tokenize='unicode61'
);
"""


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(DDL)
    _ensure_columns(conn)
    conn.execute('INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)',
                 ('schema_version', str(SCHEMA_VERSION)))
    conn.execute('INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)',
                 ('created_at', time.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """为旧库补齐新增列（幂等；SQLite 不支持 ADD COLUMN IF NOT EXISTS）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(doc)")}
    if 'tech_type' not in cols:
        conn.execute('ALTER TABLE doc ADD COLUMN tech_type TEXT')


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        'docs': q('SELECT COUNT(*) FROM doc'),
        'chunks': q('SELECT COUNT(*) FROM chunk'),
        'entities': q('SELECT COUNT(*) FROM entity'),
        'facts': q('SELECT COUNT(*) FROM fact'),
        'cases': q('SELECT COUNT(*) FROM case_layer'),
        'clauses': q('SELECT COUNT(*) FROM clause'),
        'doubts': q('SELECT COUNT(*) FROM doubt'),
        'schema_version': q("SELECT v FROM meta WHERE k='schema_version'"),
    }


def set_meta(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)', (key, json.dumps(value, ensure_ascii=False)))


def dedupe_entities(conn) -> int:
    """按 canonical 合并重复实体（保留 conf 最高者）。返回删除条数。"""
    rows = conn.execute('SELECT id, canonical, conf FROM entity ORDER BY conf DESC').fetchall()
    seen = set()
    deleted = 0
    for eid, canon, conf in rows:
        key = str(canon or '').strip().upper()
        if not key:
            continue
        if key in seen:
            conn.execute('DELETE FROM entity WHERE id=?', (eid,))
            deleted += 1
        else:
            seen.add(key)
    conn.commit()
    return deleted
