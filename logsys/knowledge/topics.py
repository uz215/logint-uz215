# -*- coding: utf-8 -*-
"""知识库专题：按主题聚合文档/案例/标准，生成可读专题报告。

- 主题定义：topics.json（关键词 + 说明）；
- 输出：data/kb/topics/<主题>.md（命中数、文档清单、片段）与 index.md；
- 用法：python -m logsys.knowledge.topics [--out data/kb/topics]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from .db import connect, stats

BASE = r'D:\360\src'
DEFAULT_TOPICS = os.path.join(BASE, 'logsys', 'knowledge', 'topics.json')
DEFAULT_OUT = os.path.join(BASE, 'data', 'kb', 'topics')


def load_topics(path: str = DEFAULT_TOPICS) -> list:
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding='utf-8'))
        except Exception:
            pass
    return []


def _like_any(col: str, kws: list):
    cond = ' OR '.join(['%s LIKE ?' % col] * len(kws))
    return cond, ['%' + k + '%' for k in kws]


def topic_docs(conn, kws: list, limit: int = 200):
    """按标题/正文关键词检索文档，返回 (命中总数, 前 limit 篇)。"""
    cond_t, a_t = _like_any('d.title', kws)
    cond_b, a_b = _like_any('c.text', kws)
    sql = ("SELECT d.id, d.title, d.path, COUNT(c.id) AS hits "
           "FROM doc d JOIN chunk c ON c.doc_id=d.id "
           "WHERE (%s) OR (%s) GROUP BY d.id ORDER BY hits DESC" % (cond_t, cond_b))
    try:
        rows = conn.execute(sql, a_t + a_b).fetchall()
    except Exception:
        return 0, []
    docs = [{'id': r[0], 'title': r[1], 'path': r[2], 'hits': r[3]} for r in rows]
    # 同文多路径（不同根目录/斜杠）按标题去重，保留命中块数最多者
    _seen, _uniq = set(), []
    for dd in docs:
        _k = str(dd['title']).strip().lower()
        if _k in _seen:
            continue
        _seen.add(_k)
        _uniq.append(dd)
    return len(_uniq), _uniq[:limit]


def topic_snippets(conn, doc_ids: list, kws: list, max_snips: int = 3) -> dict:
    out = {}
    for did in doc_ids:
        cond, args = _like_any('text', kws)
        row = conn.execute('SELECT text FROM chunk WHERE doc_id=? AND (%s) LIMIT 1' % cond,
                           [did] + args).fetchone()
        if row:
            t = re.sub(r'\s+', ' ', str(row[0]))
            kw = next((k for k in kws if k in t), kws[0])
            i = max(0, t.find(kw) - 60)
            out[did] = '…' + t[i:i + 180] + '…'
    return out


def topic_cases(conn, kws: list, limit: int = 30) -> list:
    """按层位/岩性/井名关键词检索案例层。"""
    cond, args = _like_any('formation', kws)
    try:
        rows = conn.execute(
            "SELECT well_id, top_m, base_m, fluid, formation, conf FROM case_layer "
            "WHERE (%s) ORDER BY conf DESC LIMIT ?" % cond, args + [limit])
        return [dict(zip(('well', 'top', 'base', 'fluid', 'formation', 'conf'), r)) for r in rows]
    except Exception:
        return []


def render_topic(conn, spec: dict) -> str:
    kws = spec.get('keywords') or []
    n_total, docs = topic_docs(conn, kws)
    snips = topic_snippets(conn, [d['id'] for d in docs[:12]], kws)
    cases = topic_cases(conn, spec.get('case_keywords') or kws)
    md = ['# 知识库专题：%s' % spec.get('name', ''),
          '', '> %s' % spec.get('desc', ''), '',
          '- 关键词：%s' % '、'.join(kws),
          '- 命中文档：**%d** 篇（下展示前 %d）' % (n_total, len(docs)),
          '- 命中案例层：**%d** 条' % len(cases), '',
          '## 文档清单（按命中块数）', '']
    for d in docs[:30]:
        md.append('- **%s**（%d 块）`%s`' % (d['title'], d['hits'], d['path']))
        if d['id'] in snips:
            md.append('  > %s' % snips[d['id']])
    if not docs:
        md.append('- （无命中）')
    md += ['', '## 相关案例层', '']
    if cases:
        md += ['| 井 | 顶深 | 底深 | 流体 | 层位 | 置信 |', '|---|---|---|---|---|---|']
        for c in cases[:20]:
            md.append('| %s | %.1f | %.1f | %s | %s | %.2f |' % (
                c['well'], c['top'] or 0, c['base'] or 0, c['fluid'], c['formation'] or '', c['conf'] or 0))
    else:
        md.append('- （无命中）')
    return '\n'.join(md) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description='知识库专题报告')
    ap.add_argument('--topics', default=DEFAULT_TOPICS)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--db', default=os.path.join(BASE, 'data', 'kb', 'kb.db'))
    args = ap.parse_args(argv)
    topics = load_topics(args.topics)
    if not topics:
        print('无专题定义:', args.topics); return 1
    conn = connect(args.db)
    os.makedirs(args.out, exist_ok=True)
    st = stats(conn)
    idx = ['# 知识库专题索引', '',
           '> 知识库：%d 文档 / %d 块 / %d 实体 / %d 事实 / %d 案例 / %d 条款' % (
               st.get('docs', 0), st.get('chunks', 0), st.get('entities', 0),
               st.get('facts', 0), st.get('cases', 0), st.get('clauses', 0)), '',
           '| 专题 | 关键词 | 文档 | 案例 |', '|---|---|---|---|']
    results = []
    for spec in topics:
        md = render_topic(conn, spec)
        name = spec.get('name', 'topic')
        fn = re.sub(r'[\\/:*?"<>|]', '_', name) + '.md'
        open(os.path.join(args.out, fn), 'w', encoding='utf-8').write(md)
        n_docs = int(md.split('命中文档：**')[1].split('**')[0]) if '命中文档：**' in md else 0
        n_cases = int(md.split('命中案例层：**')[1].split('**')[0]) if '命中案例层：**' in md else 0
        idx.append('| [%s](%s) | %s | %d | %d |' % (name, fn, '、'.join(spec.get('keywords') or [])[:40],
                                                     n_docs, n_cases))
        results.append({'name': name, 'file': fn, 'docs': n_docs, 'cases': n_cases})
    open(os.path.join(args.out, 'index.md'), 'w', encoding='utf-8').write('\n'.join(idx) + '\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print('saved:', os.path.join(args.out, 'index.md'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
