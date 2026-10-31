# -*- coding: utf-8 -*-
"""知识库构建 CLI（文档 + 案例层）。

用法：
    python -m logsys.knowledge.build --db <kb.db> [--root DIR ...] [--limit N] [--force]
    python -m logsys.knowledge.build --db <kb.db> --sources logsys/knowledge/kb_sources.json
    python -m logsys.knowledge.build --db <kb.db> --stats
    python -m logsys.knowledge.build --db <kb.db> --search "试油 油层"

默认根目录（按存在性自动选取）：<项目>/docs、<项目>/测井解释知识库。
kb_sources.json 可追加 roots（本地知识目录）与 cases（真值层表 → case_layer）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .db import connect, stats, dedupe_entities
from .ingest import ingest_directory
from .query import search
from .cases import import_cases

BASE = r'D:\360\src'
DEFAULT_ROOTS = [os.path.join(BASE, 'docs'), os.path.join(BASE, '测井解释知识库')]
DEFAULT_DB = os.path.join(BASE, 'data', 'kb', 'kb.db')
DEFAULT_SOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb_sources.json')


def main(argv=None):
    ap = argparse.ArgumentParser(description='kb.db 知识库构建/查询')
    ap.add_argument('--db', default=DEFAULT_DB, help='kb.db 路径')
    ap.add_argument('--root', action='append', default=None, help='待入库目录（可多次）')
    ap.add_argument('--sources', default=DEFAULT_SOURCES, help='kb_sources.json（roots+cases）')
    ap.add_argument('--limit', type=int, default=None, help='最多入库文件数（默认全部）')
    ap.add_argument('--force', action='store_true', help='强制重入已存在文档')
    ap.add_argument('--no-cases', action='store_true', help='只入文档，不入案例层')
    ap.add_argument('--cases-only', action='store_true', help='只入案例层，不扫文档')
    ap.add_argument('--stats', action='store_true', help='只打印统计')
    ap.add_argument('--search', default=None, help='检索关键词')
    args = ap.parse_args(argv)

    conn = connect(args.db)
    if args.stats:
        print(json.dumps(stats(conn), ensure_ascii=False, indent=2))
        return 0
    if args.search:
        for r in search(conn, args.search, limit=10):
            print('[%.3f] %s | %s' % (r['rank'], r['title'], os.path.basename(r['path'])))
            print('    ', r['snippet'])
        return 0

    cfg = {}
    if args.sources and os.path.exists(args.sources):
        cfg = json.load(open(args.sources, encoding='utf-8'))
    roots = args.root or [p for p in (cfg.get('roots') or DEFAULT_ROOTS) if os.path.exists(p)]
    t0 = time.time()
    total = {'ok': 0, 'fail': 0, 'errors': []}

    if not args.cases_only:
        if not roots:
            print('没有可入库目录（--root 指定）', file=sys.stderr)
        for root in roots:
            print('入库:', root, flush=True)
            r = ingest_directory(conn, root, limit=args.limit, force=args.force)
            print('  ok=%d fail=%d %s' % (r.get('ok', 0), r.get('fail', 0),
                                          json.dumps(r.get('errors', [])[:3], ensure_ascii=False)), flush=True)
            total['ok'] += r.get('ok', 0)
            total['fail'] += r.get('fail', 0)
            total['errors'] += r.get('errors', [])

    if not args.no_cases:
        specs = cfg.get('cases') or []
        if specs:
            print('案例层入库:', flush=True)
            rc = import_cases(conn, specs)
            print('  案例 ok=%d fail=%d wells=%d' % (rc['ok'], rc['fail'], rc['wells']), flush=True)
            total['errors'] += rc['errors']
        else:
            print('kb_sources.json 无 cases 配置')

    if not args.no_cases:
        cl = cfg.get('clauses')
        if cl:
            try:
                from .clauses import import_clauses
                _n = import_clauses(conn, cl)
                print('标准条款入库: %d 条' % _n, flush=True)
            except Exception as _cle:
                print('条款入库失败: %s: %s' % (type(_cle).__name__, _cle), flush=True)

    try:
        _dd = dedupe_entities(conn)
        if _dd:
            print('实体去重: 删除 %d 条重复' % _dd, flush=True)
    except Exception as _de:
        print('实体去重失败: %s' % _de, flush=True)

    print('耗时 %.1fs; 累计 ok=%d fail=%d' % (time.time() - t0, total['ok'], total['fail']))
    print(json.dumps(stats(conn), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
