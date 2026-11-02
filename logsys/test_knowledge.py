# -*- coding: utf-8 -*-
"""知识库 MVP 自检：建库 → 入库(docs/docx/语料抽样) → 检索 → 幂等 → 统计。"""
import os
import random
import sys

sys.path.insert(0, r'D:\360\src')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'
DB = os.path.join(WS, 'scratch', 'lead', 'kb_test.db')

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


def main():
    from logsys.knowledge import connect, ingest_directory, stats, search, get_facts, get_entities
    if os.path.exists(DB):
        os.remove(DB)
    for suffix in ('-wal', '-shm'):
        if os.path.exists(DB + suffix):
            os.remove(DB + suffix)
    conn = connect(DB)
    print('db:', DB)

    # 1) 入库项目 docs（2 个 md）
    r = ingest_directory(conn, r'D:\360\src\docs')
    print('docs ingest:', r)
    check('docs 入库成功', r['ok'] >= 2 and r['fail'] == 0, r)

    # 2) 入库 测井解释知识库 docx
    r2 = ingest_directory(conn, r'D:\360\src\测井解释知识库')
    print('docx ingest:', r2)
    check('docx 入库成功', r2['ok'] >= 1, r2)

    # 3) 语料抽样 300 个 md（data/local）
    local = r'D:\360\src\data\local'
    if os.path.isdir(local):
        names = [e.name for e in os.scandir(local) if e.is_file() and e.name.lower().endswith('.md')]
        random.seed(20261030)
        random.shuffle(names)
        ok = 0
        from logsys.knowledge import ingest_markdown
        for n in names[:300]:
            try:
                ingest_markdown(conn, os.path.join(local, n))
                ok += 1
            except Exception:
                pass
        print('corpus sample ingested:', ok)
        check('语料抽样入库 >=250', ok >= 250, ok)

    # 4) 统计
    st = stats(conn)
    print('stats:', st)
    check('文档数 >= 300', st['docs'] >= 300, st['docs'])
    check('块数 > 文档数', st['chunks'] > st['docs'], st['chunks'])
    check('实体数 > 0', st['entities'] > 0, st['entities'])
    check('事实数 > 0', st['facts'] > 0, st['facts'])

    # 5) 检索（中文/英文）
    for q in ('解释逻辑', '试油', 'Archie', '岩性符号'):
        hits = search(conn, q, limit=3)
        print('  search %-8s -> %d 条；top=%s' % (
            q, len(hits), hits[0]['title'] if hits else '—'))
    check('检索"解释逻辑"命中', len(search(conn, '解释逻辑', limit=3)) > 0)
    check('检索"试油"命中', len(search(conn, '试油', limit=3)) > 0)

    # 6) 幂等：重复入库 docs 不增加文档
    before = stats(conn)['docs']
    ingest_directory(conn, r'D:\360\src\docs')
    after = stats(conn)['docs']
    check('重复入库幂等', before == after, (before, after))

    # 7) API
    facts = get_facts(conn, rel='LOCATED_IN', limit=5)
    print('  facts(LOCATED_IN):', facts[:3])
    wells = get_entities(conn, kind='Well', limit=5)
    print('  entities(Well):', wells[:3])
    check('事实/实体 API 可调用', isinstance(facts, list) and isinstance(wells, list))

    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
