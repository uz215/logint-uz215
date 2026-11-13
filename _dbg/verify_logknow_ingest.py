# -*- coding: utf-8 -*-
"""临时环境验证 logknow 入档链路（完全不碰主 kb.db / G 盘 / 真实归档目录）。
验证：外文归一中文、中英同国不重复、归档优先、合规跳过、指纹幂等。
"""
import os
import sys
import json
import sqlite3
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, '.')
import logknow.bootstrap_knowledge as m

MAIN_DB = Path('data/kb/kb.db').resolve()
tmp = Path(tempfile.mkdtemp(prefix='logknow_verify_'))
print('临时目录:', tmp)

# 1) 从主库只读取 entity/fact DDL，建临时库（不写主库）
src = sqlite3.connect('file:' + str(MAIN_DB) + '?mode=ro', uri=True)
ddl = [r[0] for r in src.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('entity','fact')")].__iter__()
ddl = list(ddl)
src.close()
assert len(ddl) == 2, '主库缺 entity/fact 表'
tdb = tmp / 'test.db'
cc = sqlite3.connect(tdb)
for d in ddl:
    cc.execute(d)
cc.commit()
cc.close()

# 2) 重定向所有落点到临时目录
m.DB_PATH = tdb
m.DOC_ARCHIVE = tmp / 'docs'
m.DOC_ARCHIVE.mkdir(parents=True, exist_ok=True)
m.FINGERPRINT_DB = tmp / 'fp.txt'

# 3) 造样例（路径含「入库整理后」以触发国别派生）
root = tmp / '入库整理后'
EN = '''Regional log interpretation report for Hassi Messaoud area.
Country: Algeria
Basin: Sahara
Formation: Cambro-Ordovician sandstone reservoir
Interpretation Method: Archie
Threshold: porosity cutoff 6 percent
Formula: Sw = sqrt(a*Rw/(Rt*Phi^m))
Applicable Condition: clean sandstone, water wet
'''
ZH = '''区域测井解释报告（同一国家的中文写法，用于验证去重）。
国家：阿尔及利亚
盆地：撒哈拉
地层：寒武-奥陶系砂岩储层
解释方法：阿尔奇公式
阈值：孔隙度截止值 6%
适用条件：纯净砂岩、水湿
'''
CH = '''Well logging summary for Chad block.
Formation: Lower Cretaceous sandstone
Threshold: VSH cutoff 35 percent
Formula: Vsh = (GR - GRmin)/(GRmax - GRmin)
'''
PLAIN = 'Short file without any structured keywords, but still archived as original.'

files = {
    root / 'Algeria' / 'Hassi' / 'report_en.md': EN,
    root / '阿尔及利亚' / 'Hassi' / 'report_zh.md': ZH,
    root / 'Chad' / 'Doba' / 'report_ch.md': CH,
    root / 'Thailand' / '考勤表.md': 'Sensitive admin file, should be skipped by compliance.',
    root / 'Iraq' / 'plain.md': PLAIN,
}
for p, txt in files.items():
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding='utf-8')

# 4) 首轮入档
st = {}
cnt, errs = m.scan_docs_in_path(str(root), stats_out=st)
print('\n=== 首轮统计 ===')
print(json.dumps({k: v for k, v in st.items() if k not in ('pii_list', 'sensitive_list')},
                 ensure_ascii=False, indent=2))
print('知识记录:', cnt)
print('敏感清单:', [os.path.basename(x) for x in st.get('sensitive_list', [])])

c = sqlite3.connect(tdb)
countries = [r[0] for r in c.execute("SELECT name FROM entity WHERE kind='country' ORDER BY name")]
print('\n=== country 节点 ===', countries)
print('entity 总数:', c.execute('SELECT count(*) FROM entity').fetchone()[0],
      '| fact 总数:', c.execute('SELECT count(*) FROM fact').fetchone()[0])
# 归一追溯
fa = c.execute("SELECT props_json FROM entity WHERE kind='formation'").fetchall()
print('formation props 含 foreign_alias 的条数:',
      sum(1 for (p,) in fa if 'foreign_alias' in (p or '')))
mprops = c.execute("SELECT name, props_json FROM entity WHERE kind='interp_method'").fetchall()
print('解释方法节点:', [(n, json.loads(p or '{}').get('method_name')) for n, p in mprops])
formations = [r[0] for r in c.execute("SELECT name FROM entity WHERE kind='formation' ORDER BY name")]
print('地层节点:', formations)
print('全部 entity name:', [r[0] for r in c.execute("SELECT name FROM entity ORDER BY kind,name")])
c.close()

# 5) 断言
assert st['sensitive'] == 1, '合规跳过数不对'
assert st['archived'] == 4, f"归档数应为4(5文件-1敏感)，实际 {st['archived']}"
assert '阿尔及利亚' in countries, '英文国名未归一成中文'
assert not any(any(ch.isascii() and ch.isalpha() for ch in n) for n in countries), \
    '出现拉丁字母国家节点（中英重复风险）'
assert countries.count('阿尔及利亚') == 1, '中英文同国产生了重复节点'
assert formations.count('寒武-奥陶系砂岩储层') == 1, \
    f'中英文地层写法未合并到同一节点: {formations}'
assert all(not any(ch.isascii() and ch.isalpha() for ch in f) for f in formations), \
    f'地层名仍含外文: {formations}'
assert len([n for n, _ in mprops if n == '阿尔奇公式']) == 1, \
    '外文法 Archie 与中文「阿尔奇公式」应合并为同一方法节点'
assert cnt >= 3, f'结构化知识记录过少: {cnt}'
print('\n[OK] 外文归一中文 / 中英同国不重复 / 地层与方法节点合并 / 归档优先 / 合规跳过 均通过')

# 6) 重跑幂等
st2 = {}
cnt2, _ = m.scan_docs_in_path(str(root), stats_out=st2)
print('\n=== 重跑统计 ===', {k: v for k, v in st2.items() if k not in ('pii_list', 'sensitive_list')})
assert st2['archived'] == 0 and cnt2 == 0, '重跑未跳过已入档文件'
assert st2['skip_known'] == 4, '指纹去重未生效'
print('[OK] 指纹去重幂等通过')

shutil.rmtree(tmp, ignore_errors=True)
print('\n临时目录已清理，主库与 G 盘未被触碰。')
