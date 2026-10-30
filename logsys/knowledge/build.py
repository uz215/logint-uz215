# -*- coding: utf-8 -*-
"""知识库构建 CLI。

用法：
    python -m logsys.knowledge.build --db <kb.db> [--root DIR ...] [--limit N] [--force]
    python -m logsys.knowledge.build --db <kb.db> --stats
    python -m logsys.knowledge.build --db <kb.db> --search "试油 油层"

默认根目录（按存在性自动选取）：
    <项目>/docs
    <项目>/测井解释知识库
    <项目>/data/local            （默认只取 limit 条，避免一次扫 12 万文件）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .db import connect, stats
from .ingest import ingest_directory
from .query import search

BASE = r'D:\360\src'
DEFAULT_ROOTS = [os.path.join(BASE, 'docs'), os.path.join(BASE, '测井解释知识库')]
DEFAULT_DB = os.path.join(BASE, 'data', 'kb', 'kb.db')


def main(argv=None):
    ap = argparse.ArgumentParser(description='kb.db 知识库构建/查询')
    ap.add_argument('--db', default=DEFAULT_DB, help='kb.db 路径')
    ap.add_argument('--root', action='append', default=None, help='待入库目录（可多次）')
    ap.add_argument('--limit', type=int, default=None, help='最多入库文件数（默认全部）')
    ap.add_argument('--force', action='store_true', help='强制重入已存在文档')
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

    roots = args.root or [p for p in DEFAULT_ROOTS if os.path.exists(p)]
    if not roots:
        print('没有可入库目录（--root 指定）', file=sys.stderr)
        return 1
    t0 = time.time()
    total = {'ok': 0, 'fail': 0, 'errors': []}
    for root in roots:
        if not os.path.exists(root):
            print('跳过不存在目录:', root)
            continue
        print('入库:', root, flush=True)
        r = ingest_directory(conn, root, limit=args.limit, force=args.force)
        print('  ok=%d fail=%d %s' % (r.get('ok', 0), r.get('fail', 0),
                                      json.dumps(r.get('errors', [])[:3], ensure_ascii=False)), flush=True)
        total['ok'] += r.get('ok', 0)
        total['fail'] += r.get('fail', 0)
        total['errors'] += r.get('errors', [])
    print('耗时 %.1fs; 累计 ok=%d fail=%d' % (time.time() - t0, total['ok'], total['fail']))
    print(json.dumps(stats(conn), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
