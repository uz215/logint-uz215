# -*- coding: utf-8 -*-
"""知识库扩展入库：PDF / PPTX 文本抽取 → doc/chunk/FTS/实体（带来源路径）。

- PDF：PyMuPDF 抽文本（跳过扫描空页），限制页数与字符数；
- PPTX：python-pptx 抽文本框与表格；
- 复用 ingest 的 chunk/FTS/实体逻辑（本模块独立实现存储，保持来源为原始文件路径）。
"""
from __future__ import annotations

import hashlib
import json
import os

from .db import connect
from .ingest import tokenize, _chunks, _sha1, detect_country, classify_knowledge
try:
    from .entities import extract_entities, canon_well
except Exception:
    extract_entities = None

MAX_FILE_MB = 15
MAX_PAGES = 40
MAX_CHARS = 300_000


def _path_doc_id(path: str) -> str:
    return 'DOC:' + hashlib.sha1(path.encode('utf-8', 'replace')).hexdigest()[:16]


def _store(conn, path: str, title: str, body: str, ext: str) -> str:
    sha1 = hashlib.sha1(body.encode('utf-8', 'replace')).hexdigest()
    doc_id = _path_doc_id(path)
    mtime = os.path.getmtime(path) if os.path.exists(path) else 0
    country = detect_country(path, title)
    # 全部文档按知识技术分类（领域 + 技术细类）；国别由 country 列单独承载。
    # 国别文档同样打标 -> 实现"国别知识总结提升为专业知识的方法技术归类"。
    domain, tech_type = classify_knowledge(path, title, ext)
    cat = domain
    conn.execute('DELETE FROM chunk WHERE doc_id=?', (doc_id,))
    conn.execute('DELETE FROM doc_fts WHERE doc_id=?', (doc_id,))
    conn.execute('INSERT OR REPLACE INTO doc(id, path, title, category, region, country, well, '
                 'tech_type, sha1, mtime, chars, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                 (doc_id, path, title, cat, '', country, '', tech_type, sha1, mtime, len(body),
                  json.dumps({'source': path, 'ext': ext}, ensure_ascii=False)))
    for i, ch in enumerate(_chunks(body)):
        cid = '%s#%03d' % (doc_id, i)
        conn.execute('INSERT OR REPLACE INTO chunk(id, doc_id, idx, text, chars) VALUES(?,?,?,?,?)',
                     (cid, doc_id, i, ch, len(ch)))
        conn.execute('INSERT INTO doc_fts(doc_id, title, body, region, well) VALUES(?,?,?,?,?)',
                     (doc_id, tokenize(title), tokenize(ch), '', ''))
    if extract_entities is not None:
        try:
            ents = extract_entities(body, {})
            conn.execute('DELETE FROM entity WHERE source_doc=?', (doc_id,))
            for kind, items in ents.items():
                pref = {'Well': 'WELL', 'Field': 'FIELD', 'Formation': 'FRM'}[kind]
                for canon, info in list(items.items())[:20]:
                    eid = '%s:%s' % (pref, canon)
                    conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, '
                                 'props_json, source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                                 (eid, kind, info['name'], canon, '',
                                  json.dumps({'aliases': sorted(info['aliases'])}, ensure_ascii=False),
                                  doc_id, float(info['conf'])))
        except Exception:
            pass
    conn.commit()
    return doc_id


def extract_pdf(path: str) -> str:
    import fitz
    out = []
    d = fitz.open(path)
    for i in range(min(d.page_count, MAX_PAGES)):
        try:
            t = d[i].get_text()
        except Exception:
            continue
        if t and t.strip():
            out.append(t.strip())
        if sum(len(x) for x in out) > MAX_CHARS:
            break
    return '\n'.join(out)[:MAX_CHARS]


def extract_pptx(path: str) -> str:
    from pptx import Presentation
    prs = Presentation(path)
    out = []
    for slide in prs.slides:
        for sh in slide.shapes:
            try:
                if sh.has_text_frame and sh.text_frame.text.strip():
                    out.append(sh.text_frame.text.strip())
                if getattr(sh, 'has_table', False):
                    for row in sh.table.rows:
                        out.append(' | '.join(c.text.strip() for c in row.cells))
            except Exception:
                continue
    return '\n'.join(out)[:MAX_CHARS]


def ingest_rich_file(conn, path: str) -> str:
    if conn.execute('SELECT 1 FROM doc WHERE id=?', (_path_doc_id(path),)).fetchone():
        return 'SKIP_EXISTING'
    ext = os.path.splitext(path)[1].lower()
    if os.path.getsize(path) > MAX_FILE_MB * 1024 * 1024:
        return 'SKIP_TOO_LARGE'
    if ext == '.pdf':
        body = extract_pdf(path)
    elif ext == '.pptx':
        body = extract_pptx(path)
    else:
        raise ValueError('unsupported: ' + path)
    if len(body.strip()) < 200:
        return 'SKIP_NO_TEXT'
    title = os.path.splitext(os.path.basename(path))[0]
    return _store(conn, path, title, body, ext.lstrip('.'))


def ingest_rich_directory(conn, root: str, limit: int | None = None,
                          pattern=('.pdf', '.pptx')) -> dict:
    """入库目录下 PDF/PPTX；已入库文件跳过（可续跑），limit 只计**新增**文档数。"""
    res = {'ok': 0, 'skip': 0, 'fail': 0, 'errors': [], 'files': []}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(tuple(pattern)):
                continue
            p = os.path.join(dirpath, fn)
            try:
                r = ingest_rich_file(conn, p)
                if r.startswith('SKIP'):
                    res['skip'] += 1
                else:
                    res['ok'] += 1
                    res['files'].append(p)
            except Exception as e:
                res['fail'] += 1
                res['errors'].append('%s: %s' % (fn, e))
            if limit and res['ok'] >= limit:
                return res
    return res
