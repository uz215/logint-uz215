# -*- coding: utf-8 -*-
"""gen_kb_reports.py 取数容错：新增资料里出现 category/tech_type/tech_minor 为 NULL，
导致 domains 含 None、' · '.join(domains) 崩溃。全部改为 COALESCE(...,'') 归一为空串分组。
只改 SQL 字符串，不碰数据、不改报告逻辑。
"""
import os
from pathlib import Path

P = Path('gen_kb_reports.py')
raw = P.read_bytes()
bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
body = raw[len(bom):].decode('utf-8')

PAIRS = [
    # domains / domain_counts（同串出现 2 次）
    ('''"SELECT category, COUNT(*) FROM doc GROUP BY category ORDER BY 2 DESC"''',
     '''"SELECT COALESCE(category,'') AS category, COUNT(*) FROM doc GROUP BY COALESCE(category,'') ORDER BY 2 DESC"''',
     2),
    # dmin：三级明细
    ('''"SELECT category, tech_type, tech_minor, COUNT(*) FROM doc "
    "GROUP BY category, tech_type, tech_minor ORDER BY 1, 2, 4 DESC"''',
     '''"SELECT COALESCE(category,'') AS category, COALESCE(tech_type,'') AS tech_type, "
    "COALESCE(tech_minor,'') AS tech_minor, COUNT(*) FROM doc "
    "GROUP BY COALESCE(category,''), COALESCE(tech_type,''), COALESCE(tech_minor,'') "
    "ORDER BY 1, 2, 4 DESC"''',
     1),
    # 国别×领域 matrix（中间带 WHERE 行）
    ('''"SELECT country, category, COUNT(*) FROM doc "
    "WHERE country IS NOT NULL AND country!='' "
    "GROUP BY country, category"''',
     '''"SELECT country, COALESCE(category,'') AS category, COUNT(*) FROM doc "
    "WHERE country IS NOT NULL AND country!='' "
    "GROUP BY country, COALESCE(category,'')"''',
     1),
    # 合规正向清单明细
    ('''"SELECT title, category, tech_type FROM doc WHERE " + _c_like''',
     '''"SELECT title, COALESCE(category,'') AS category, COALESCE(tech_type,'') AS tech_type "
     "FROM doc WHERE " + _c_like''',
     1),
    # scope=global
    ('''"SELECT category, COUNT(*) FROM doc WHERE scope='global' GROUP BY category ORDER BY 2 DESC"''',
     '''"SELECT COALESCE(category,'') AS category, COUNT(*) FROM doc WHERE scope='global' "
     "GROUP BY COALESCE(category,'') ORDER BY 2 DESC"''',
     1),
    # scope=国别
    ('''"SELECT country, category, COUNT(*) FROM doc WHERE scope='国别' GROUP BY country, category"''',
     '''"SELECT country, COALESCE(category,'') AS category, COUNT(*) FROM doc "
     "WHERE scope='国别' GROUP BY country, COALESCE(category,'')"''',
     1),
    # scopes / scope_counts（同串出现 2 次）
    ('''"SELECT scope, COUNT(*) FROM doc GROUP BY scope ORDER BY 2 DESC"''',
     '''"SELECT COALESCE(scope,'') AS scope, COUNT(*) FROM doc "
     "GROUP BY COALESCE(scope,'') ORDER BY 2 DESC"''',
     2),
]

for i, (old, new, expect) in enumerate(PAIRS, 1):
    n = body.count(old)
    if n != expect:
        raise SystemExit(f'PATCH {i} 命中数异常: 期望 {expect}, 实际 {n}\n  锚点: {old[:70]}')
    body = body.replace(old, new)
    print(f'PATCH {i}: OK (命中 {n})')

out = bom + body.encode('utf-8')
tmp = P.with_suffix('.py.tmp')
tmp.write_bytes(out)
os.replace(tmp, P)
print(f'=== gen_kb_reports.py 原子替换完成: {len(out)} bytes ===')
