import os
import sqlite3
import json
from pathlib import Path


def _default_db_path() -> Path:
    """知识库默认路径。

    历史实现硬编码 F:\\360\\src\\data\\kb\\kb.db，换机/换盘（D:\\360\\src）即报
    "unable to open database file"，并让 logknow 整个包不可导入。
    改为：环境变量优先 → 仓库相对定位。
    """
    for env in ("LOGINT_KB", "LOGKNOW_KB"):
        val = os.environ.get(env)
        if val:
            return Path(val)
    # <repo>/logknow/core/graph_store.py -> <repo>/data/kb/kb.db
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "kb" / "kb.db"


class GraphStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = _default_db_path()
        self.db_path = Path(db_path)
        self.entities = dict()
        self.facts = []
        self._idx = dict()
        self.reload()

    def reload(self):
        self.entities.clear()
        self.facts.clear()
        self._idx.clear()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, kind, name, canonical, region, props_json, source_doc, conf FROM entity")
        for row in cur.fetchall():
            eid, kind, name, canonical, region, props_json, source_doc, conf = row
            ent = {
                "id": eid,
                "kind": kind,
                "name": name,
                "canonical": canonical,
                "region": region,
                "props": json.loads(props_json),
                "source_doc": source_doc,
                "conf": conf
            }
            self.entities[eid] = ent
            self._idx[(kind, name)] = eid

        cur.execute("SELECT id, subj, rel, obj, props_json, source_doc, source_loc, conf, extractor FROM fact")
        for row in cur.fetchall():
            fid, subj, rel, obj, props_json, source_doc, source_loc, conf, extractor = row
            self.facts.append({
                "id": fid,
                "src": subj,
                "rel": rel,
                "dst": obj,
                "props": json.loads(props_json),
                "source_doc": source_doc,
                "source_loc": source_loc,
                "conf": conf,
                "extractor": extractor
            })
        conn.close()

    def lookup(self, kind: str, name: str):
        eid = self._idx.get((kind, name))
        if eid is None:
            return None
        return self.entities[eid]

    def get_outgoing(self, eid: str, rel: str):
        res = []
        for f in self.facts:
            if f["src"] == eid and f["rel"] == rel:
                res.append(f["dst"])
        return res
