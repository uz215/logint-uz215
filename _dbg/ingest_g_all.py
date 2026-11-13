"""G:/入库整理后 全量增量入库（续跑"资料还在更新"）。

- 9 个新国家(与 D 盘无重叠)：纯路径增量，已入自动跳过，新增文件入库。
- 3 个重名国家(Bangladesh/Indonesia/Niger)：入库前按 sha1 与 kb.db 现有全集比对，
  跳过与 D 盘镜像内容重复的文件，只入真正的新内容。
- 末尾幂等回填 scope(国别/ global)。
"""
import os, sys, time, sqlite3, hashlib
sys.path.insert(0, '.')
from logsys.knowledge.db import connect
from logsys.knowledge import ingest as ING
from logsys.knowledge import ingest_rich as RICH

conn = connect('data/kb/kb.db')
ROOT = "G:/入库整理后"
OVERLAP = {'Bangladesh', 'Indonesia', 'Niger'}  # 与 D 盘镜像重名，需 sha1 去重

# 预载 kb.db 现有 sha1 全集（用于重名国家去重）
existing_sha1 = set(r[0] for r in conn.execute(
    "select sha1 from doc where sha1 is not null and sha1!=''"))
print("kb.db 现有 sha1 数:", len(existing_sha1), flush=True)


def file_sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def walk(d):
    for dp, _dn, fn in os.walk(d):
        for f in fn:
            yield os.path.join(dp, f)


MD_DOCX = {'.md', '.docx'}
t0 = time.time()
tot_md = tot_rich = skip_dup = fail = 0
for country in sorted(os.listdir(ROOT)):
    d = os.path.join(ROOT, country)
    if not os.path.isdir(d):
        continue
    is_overlap = country in OVERLAP
    c_md = c_rich = c_skip = c_fail = 0
    for fp in walk(d):
        ext = os.path.splitext(fp)[1].lower()
        try:
            if ext in MD_DOCX:
                if is_overlap and file_sha1(fp) in existing_sha1:
                    c_skip += 1
                    continue
                ING.ingest_file(conn, fp)
                c_md += 1
            elif ext in ('.pdf', '.pptx'):
                if is_overlap and file_sha1(fp) in existing_sha1:
                    c_skip += 1
                    continue
                r = RICH.ingest_rich_file(conn, fp)
                if r == 'SKIP_EXISTING':
                    continue
                c_rich += 1
        except Exception as e:
            c_fail += 1
            if c_fail <= 5:
                print("  FAIL", os.path.basename(fp), type(e).__name__, e, flush=True)
    conn.commit()
    tot_md += c_md; tot_rich += c_rich; skip_dup += c_skip; fail += c_fail
    print(f"[{country}] md+={c_md} rich+={c_rich} skip_dup={c_skip} fail={c_fail} "
          f"| 累计 md={tot_md} rich={tot_rich} skip={skip_dup}", flush=True)

# 幂等回填 scope
n1 = conn.execute("UPDATE doc SET scope='国别' WHERE country IS NOT NULL AND country!='' "
                  "AND (scope IS NULL OR scope!='国别')").rowcount
n2 = conn.execute("UPDATE doc SET scope='global' WHERE (country IS NULL OR country='') "
                  "AND (scope IS NULL OR scope!='global')").rowcount
conn.commit()
print(f"=== 完成: md新增={tot_md} rich新增={tot_rich} 跳过重复={skip_dup} 失败={fail} "
      f"scope回填 国别+{n1}/global+{n2} 耗时{time.time()-t0:.0f}s ===", flush=True)
c2 = sqlite3.connect('data/kb/kb.db')
print("总doc:", c2.execute('select count(*) from doc').fetchone()[0],
      "| 国别:", c2.execute("select count(*) from doc where scope='国别'").fetchone()[0],
      "| global:", c2.execute("select count(*) from doc where scope='global'").fetchone()[0], flush=True)
