import sqlite3
import json
import uuid
import hashlib
import os
from pathlib import Path

DB_PATH = Path(r"F:\360\src\data\kb\kb.db")


def _sha1_file(p: Path):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        while buf := f.read(65536):
            h.update(buf)
    return h.hexdigest()


def _ensure_entity(kind: str, name: str, props: dict = None) -> str:
    if props is None:
        props = {}
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM entity WHERE kind=? AND name=?", (kind, name))
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]
    eid = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO entity(id, kind, name, canonical, region, props_json, source_doc, conf)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        eid, kind, name, name, "",
        json.dumps(props, ensure_ascii=False),
        "bootstrap", 1.0
    ))
    conn.commit()
    conn.close()
    return eid


def _add_fact(subj_id: str, rel: str, obj_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM fact WHERE subj=? AND rel=? AND obj=?", (subj_id, rel, obj_id))
    if cur.fetchone():
        conn.close()
        return
    fid = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO fact(id, subj, rel, obj, props_json, source_doc, source_loc, conf, extractor)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (fid, subj_id, rel, obj_id, "{}", "bootstrap", "", 1.0, "bootstrap"))
    conn.commit()
    conn.close()


def _attach_interp(formation_name: str, method_name: str, method_props: dict):
    from logknow.core.graph_store import GraphStore
    mid = _ensure_entity("interpret_method", method_name, method_props)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM entity WHERE kind='formation' AND name=?", (formation_name,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError(f"地层不存在: {formation_name}")
    fid = row[0]
    _add_fact(fid, "has_interp_method", mid)
    GraphStore().reload()


def _link_of_fm(oilfield_name: str, formation_name: str):
    from logknow.core.graph_store import GraphStore
    of_id = _ensure_entity("oilfield", oilfield_name)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM entity WHERE kind='formation' AND name=?", (formation_name,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError(f"地层不存在: {formation_name}")
    fm_id = row[0]
    _add_fact(of_id, "has_formation", fm_id)
    GraphStore().reload()


def _simple_text_chunk(text: str, chunk_size: int = 1200, overlap: int = 120):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _extract_text(file: Path):
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        txt = []
        with pdfplumber.open(file) as pf:
            for p in pf.pages:
                t = p.extract_text()
                if t:
                    txt.append(t)
        return "\n".join(txt)
    elif suffix == ".docx":
        from docx import Document
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    elif suffix == ".pptx":
        from pptx import Presentation
        prs = Presentation(file)
        txt = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    txt.append(shape.text)
        return "\n".join(txt)
    elif suffix == ".txt":
        return file.read_text(encoding="utf-8", errors="ignore")
    return ""


def _insert_doc_and_chunks(file_path: Path, raw_text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    fp_str = str(file_path)
    cur.execute("SELECT id FROM doc WHERE path=?", (fp_str,))
    exists = cur.fetchone()
    if exists:
        conn.close()
        print(f"跳过已入库：{fp_str}")
        return

    doc_id = str(uuid.uuid4())
    sha1 = _sha1_file(file_path)
    mtime = os.path.getmtime(file_path)
    char_count = len(raw_text)
    meta_json = json.dumps({"source": "g_drive_scan"}, ensure_ascii=False)

    cur.execute("""
        INSERT INTO doc
        (id, path, title, category, region, country, well, sha1, mtime, chars, meta_json, tech_type, tech_minor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        doc_id,
        fp_str,
        file_path.name,
        "",
        "",
        "",
        "",
        sha1,
        mtime,
        char_count,
        meta_json,
        "",
        ""
    ))

    seg_list = _simple_text_chunk(raw_text)
    for idx, seg in enumerate(seg_list):
        cid = str(uuid.uuid4())
        seg_chars = len(seg)
        cur.execute(
            "INSERT INTO chunk(id, doc_id, idx, text, chars) VALUES (?,?,?,?,?)",
            (cid, doc_id, idx, seg, seg_chars)
        )

    conn.commit()
    conn.close()
    print(f"入库成功：{fp_str}")


def scan_drive_and_import(root: str):
    root_p = Path(root)
    suffix_allow = {".pdf", ".docx", ".pptx", ".txt"}
    for f in root_p.rglob("*"):
        if f.suffix.lower() not in suffix_allow:
            continue
        if not f.is_file():
            continue
        try:
            txt = _extract_text(f)
            if not txt.strip():
                print(f"无有效文本：{f}")
                continue
            _insert_doc_and_chunks(f, txt)
        except Exception as e:
            print(f"读取失败 {f} -> {e}")
    from logknow.core.graph_store import GraphStore
    GraphStore().reload()
    print("✅ G盘扫描入库全部完成")


def run_bootstrap():
    method_spec = {
        "formula": "Vsh = (GR - GRmin) / (GRmax - GRmin); Sw = (a * Rw) / (Rt * phi ** m)",
        "threshold": {"GR": {"min": 25, "max": 55}, "RT": {"min": 8, "max": 30},
                      "DEN": {"min": 1.95, "max": 2.70}, "CNL": {"min": 0.0, "max": 0.45}},
        "condition": "Bhuban 上部气组，石英砂岩储层，淡水地层水，背斜构造气藏",
        "source": "24届测井技术年会资料"
    }
    _attach_interp("Bhuban", "Bhuban 气组解释方法", method_spec)
    _link_of_fm("Bhuban 气田", "Bhuban")
    print("bootstrap 基础图谱执行完毕")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "scan":
        scan_drive_and_import(sys.argv[2])
    else:
        run_bootstrap()
