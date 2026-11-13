# -*- coding: utf-8 -*-
"""G:/入库整理后 9 个新国家 富文本(PDF/PPTX)增量入库 + scope 回填。
仅对新国家(不在 D 盘 kb.db 中的国家)操作，避免与 D 盘镜像重复。
用法: /c/Python314/python.exe _dbg/rich_ingest_new.py
"""
import os, sys, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logsys.knowledge.db import connect
from logsys.knowledge.ingest_rich import ingest_rich_directory

ROOT = "G:/入库整理后"
NEW = ['Algeria','Chad','Iran','Iraq','Kazakhstan','South Sudan','Sudan','Thailand','Turkmenistan']

def main():
    conn = connect('data/kb/kb.db')
    t0 = time.time()
    g_ok = g_skip = g_fail = 0
    for c in NEW:
        d = os.path.join(ROOT, c)
        if not os.path.isdir(d):
            print("跳过(不存在):", c); continue
        try:
            r = ingest_rich_directory(conn, d)
        except Exception as e:
            print("!! 异常", c, type(e).__name__, e); continue
        g_ok += r.get('ok', 0); g_skip += r.get('skip', 0); g_fail += r.get('fail', 0)
        try: conn.commit()
        except Exception: pass
        print(f"[{c}] ok={r.get('ok',0)} skip={r.get('skip',0)} fail={r.get('fail',0)} 累计ok={g_ok}", flush=True)
        if r.get('errors'):
            for err in r['errors'][:5]: print("   失败:", err)
    # scope 回填：富文本 INSERT 未带 scope 列，此处对 G: 来源且 scope 为空的补填
    n_scope = conn.execute(
        "UPDATE doc SET scope='国别' WHERE path LIKE 'G:/%' AND (scope IS NULL OR scope='') AND country IS NOT NULL AND country!=''").rowcount
    n_global = conn.execute(
        "UPDATE doc SET scope='global' WHERE path LIKE 'G:/%' AND (scope IS NULL OR scope='') AND (country IS NULL OR country='')").rowcount
    conn.commit()
    print(f"=== 富文本入库完成: ok={g_ok} skip={g_skip} fail={g_fail} | scope回填 国别={n_scope} global={n_global} 耗时{time.time()-t0:.0f}s ===")
    c2 = sqlite3.connect('data/kb/kb.db')
    print("当前 doc 总数:", c2.execute('select count(*) from doc').fetchone()[0],
          "| G:来源:", c2.execute("select count(*) from doc where path like 'G:/%'").fetchone()[0],
          "| scope空(G:):", c2.execute("select count(*) from doc where path like 'G:/%' and (scope is null or scope='')").fetchone()[0])

if __name__ == '__main__':
    main()
