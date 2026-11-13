import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import ctypes
import string
import time
import hashlib
import os
import re

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from docx import Document
except ImportError:
    Document = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

BASE = Path(__file__).parent
STATIC_GEO = BASE / "static_geo"
DB_PATH = BASE.parent / "data" / "kb" / "kb.db"

VALID_GEO_DIRS = {"asia", "africa", "europe", "north_america", "south_america", "oceania", "global"}

DRIVE_UNKNOWN     = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE   = 2
DRIVE_FIXED       = 3
DRIVE_REMOTE      = 4
DRIVE_CDROM       = 5
DRIVE_RAMDISK     = 6

DOC_ARCHIVE = STATIC_GEO / "docs"
FINGERPRINT_DB = STATIC_GEO / "doc_fingerprints.txt"
DOC_ARCHIVE.mkdir(parents=True, exist_ok=True)
STATIC_GEO.mkdir(parents=True, exist_ok=True)


def ensure_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def ensure_dict(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    return {}


def normalize_name(name: str) -> str:
    s = ensure_str(name)
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def file_sha256(fp: Path) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text_from_file(fp: Path) -> str:
    suffix = fp.suffix.lower()
    text = ""
    if suffix in (".txt", ".md"):
        text = fp.read_text(encoding="utf-8-sig", errors="ignore")
    elif suffix == ".pdf" and PyPDF2 is not None:
        with open(fp, "rb") as f:
            r = PyPDF2.PdfReader(f)
            for page in r.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    elif suffix == ".docx" and Document is not None:
        doc = Document(fp)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif suffix == ".pptx" and Presentation is not None:
        prs = Presentation(fp)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
    return text


# ---------- 收录合规粗筛（K-SYS-003 v2：按内容实质判定，不按文种一刀切） ----------
# 仅排除显式个人隐私 / 纯行政 / 交易凭证类路径；「合同 / 税 / 服务 / 财税政策」
# 属可入档的需求侧专业史料与区域专属知识，不在排除之列。
_SENSITIVE_PATH_KW = (
    '人事任免', '考勤', '薪资', '工资表', '身份证', '护照号', '个人简历', '私人电话',
    '银行账户', '付款凭证', '发票流水', '报销单', '诉讼', '仲裁', '涉密',
    'passport', 'payroll', 'salary', 'resume', 'bank account', 'invoice', 'litigation',
)
_PII_ID_RE = re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)')
_PII_PHONE_RE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')


# ---------- 外文 -> 中文归一（用户定调：扫描外文识别成中文入库，不产生中英重复节点） ----------
_NORMALIZER = None


def _get_normalizer():
    """懒加载 RegionNormalizer；yaml/依赖缺失时降级为不归一（不阻断入档）。"""
    global _NORMALIZER
    if _NORMALIZER is None:
        try:
            from logknow.region_normalizer import RegionNormalizer
            _NORMALIZER = RegionNormalizer()
        except Exception:
            try:
                from region_normalizer import RegionNormalizer
                _NORMALIZER = RegionNormalizer()
            except Exception:
                _NORMALIZER = False
    return _NORMALIZER or None


def _cn(raw: str, kind: str = 'country'):
    """外文实体名 -> 中文规范名。返回 (入库名, 原文别名)；未命中则原样返回。
    kind='country' 用国别正典，'term' 用测井/地质术语表。国别归一后 canonical
    与既有 182 个中文国家节点一致，INSERT OR REPLACE 直接合并而非新建。"""
    s = ensure_str(raw)
    if not s:
        return '', ''
    rn = _get_normalizer()
    if rn is None:
        return s, ''
    if kind == 'country':
        target = rn.normalize_country(s)
    elif kind == 'phrase':
        target = rn.normalize_term(s) or rn.normalize_phrase(s)
    else:
        target = rn.normalize_term(s)
    if target and target != s:
        return target, s
    return s, ''


def _safe_name(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', ensure_str(name))
    return (s[:80] or 'doc')


def _from_path(path_hint: str) -> Tuple[str, str, str]:
    """从 '.../入库整理后/<Country>/<Basin>/<Well>/...' 派生 国别/盆地/井。
    G 盘目录层级本身即权威区域信息，比从英文正文猜国家可靠。"""
    seg = [x for x in ensure_str(path_hint).replace('\\', '/').split('/') if x]
    try:
        seg = seg[seg.index('入库整理后') + 1:]
    except ValueError:
        pass
    country = seg[0] if len(seg) >= 1 else ''
    basin = seg[1] if len(seg) >= 2 else ''
    well = ''
    for s in seg[2:]:
        if any(ch.isdigit() for ch in s) and ('-' in s or s.lower().startswith('well') or '井' in s):
            well = s
            break
    return country, basin, well


def _field(line: str) -> str:
    """从 'Key: Value' / 'Key：Value' / 'Key = Value' 取 Value。"""
    for sep in ('：', ':', '='):
        if sep in line:
            return line.split(sep, 1)[1].strip()
    return ''


def simple_geo_extract(raw_text: str, path_hint: str = "") -> List[Dict[str, Any]]:
    """中英双语轻量抽取：国别/盆地/井优先由路径派生，地层/解释方法/公式/阈值/
    适用条件由正文关键词抽取。path_hint 为空时退化为纯中文关键词抽取（兼容旧行为）。"""
    p_country, p_basin, p_well = _from_path(path_hint)
    country, basin, well = p_country, p_basin, p_well
    formation = method_name = formula = condition = ''
    threshold: Dict[str, Any] = {}

    KW = {
        'country':   ('country', '国别', '国家'),
        'basin':     ('basin', '盆地'),
        'formation': ('formation', 'stratigraph', 'strata', '地层', '层组'),
        'method':    ('interpretation method', 'logging method', 'log interpretation',
                      '解释方法', '测井方法', '解释模型'),
        'formula':   ('formula', 'equation', '公式', '计算式'),
        'condition': ('applicable', 'condition', '适用条件', '适用范围'),
        'threshold': ('threshold', 'cutoff', 'cut-off', '阈值', '截止值', '界限'),
    }
    for line in raw_text.splitlines():
        l = line.strip()
        if not l or len(l) > 300:
            continue
        low = l.lower()
        val = _field(l)
        if any(k in low for k in KW['country']) and not p_country:
            country = val or country
        elif any(k in low for k in KW['basin']) and not p_basin:
            basin = val or basin
        elif any(k in low for k in KW['formation']):
            formation = val or l
        elif any(k in low for k in KW['method']):
            method_name = val or l
        elif any(k in low for k in KW['formula']):
            formula = val or l
        elif any(k in low for k in KW['condition']):
            condition = val or l
        elif any(k in low for k in KW['threshold']):
            threshold['note'] = val or l

    # 外文 -> 中文规范名：与既有 182 个中文国家节点合并，杜绝中英重复节点
    aliases: Dict[str, str] = {}
    country, _a = _cn(country, 'country')
    if _a:
        aliases['country'] = _a
    basin, _a = _cn(basin, 'phrase')
    if _a:
        aliases['basin'] = _a
    formation, _a = _cn(formation, 'phrase')
    if _a:
        aliases['formation'] = _a
    method_name, _a = _cn(method_name, 'phrase')
    if _a:
        aliases['method_name'] = _a

    if not (country and formation):
        return []
    return [{
        "country": country,
        "basin": basin,
        "sag": "",
        "block": "",
        "oilfield": "",
        "structure": "",
        "well": well,
        "formation": formation,
        "strata_meta": {"raw_source": "document_extract", "source_path": path_hint,
                        "foreign_alias": aliases},
        "method_name": method_name,
        "method_meta": {
            "threshold": threshold,
            "formula": formula,
            "condition": condition
        },
        "gwc": {}
    }]


def load_fingerprints() -> set[str]:
    if not FINGERPRINT_DB.exists():
        return set()
    raw = FINGERPRINT_DB.read_text(encoding="utf-8")
    return set(raw.splitlines())


def save_fingerprint(fp_hash: str):
    with FINGERPRINT_DB.open("a", encoding="utf-8") as f:
        f.write(fp_hash + "\n")


def get_removable_drives() -> list[str]:
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            root = f"{letter}:\\"
            dtype = ctypes.windll.kernel32.GetDriveTypeW(root)
            if dtype == DRIVE_REMOVABLE:
                drives.append(root)
        bitmask >>= 1
    return drives


class GeoKnowledgeLoader:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def add_entity(self, kind: str, name: str, canonical: str, region: str, props: Dict[str, Any], source_doc: str, conf: float = 1.0):
        if not self.conn:
            raise RuntimeError("db not connected")
        cur = self.conn.cursor()
        eid = f"{kind}:{canonical}"
        cur.execute("""
            INSERT OR REPLACE INTO entity
            (id, kind, name, canonical, region, props_json, source_doc, conf)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            eid,
            kind,
            name,
            canonical,
            region,
            json.dumps(props, ensure_ascii=False),
            source_doc,
            conf
        ))
        return eid

    def add_fact(self, subj: str, rel: str, obj: str, props: Optional[Dict] = None, source_doc: str = "", conf: float = 1.0):
        if not self.conn:
            raise RuntimeError("db not connected")
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO fact
            (id, subj, rel, obj, props_json, source_doc, source_loc, conf, extractor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"fact:{subj}#{rel}#{obj}",
            subj,
            rel,
            obj,
            json.dumps(props or {}, ensure_ascii=False),
            source_doc,
            "",
            conf,
            "bootstrap_geo"
        ))

    def ingest_single_record(self, rec: Dict[str, Any], fname: str):
        source = f"static_geo/{fname}"
        # 双保险：任何来源入库前国别都归一为中文正典，canonical 一致 -> 不产生中英重复节点
        country, _ = _cn(ensure_str(rec.get("country")), 'country')
        basin = ensure_str(rec.get("basin"))
        sag = ensure_str(rec.get("sag"))
        block = ensure_str(rec.get("block"))
        oilfield = ensure_str(rec.get("oilfield"))
        structure = ensure_str(rec.get("structure"))
        well = ensure_str(rec.get("well"))
        formation = ensure_str(rec.get("formation"))
        method_name = ensure_str(rec.get("method_name"))

        cid = None
        if country:
            cid = self.add_entity("country", country, normalize_name(country), country, {}, source)

        bid = None
        if basin and country:
            bid = self.add_entity("basin", basin, normalize_name(f"{country}|{basin}"), country, {}, source)
            if cid:
                self.add_fact(cid, "contains_basin", bid, source_doc=source)

        sid = None
        if sag and basin:
            sid = self.add_entity("sag", sag, normalize_name(f"{country}|{basin}|{sag}"), f"{country}/{basin}", {}, source)
            if bid:
                self.add_fact(bid, "contains_sag", sid, source_doc=source)

        blkid = None
        if block and sag:
            blkid = self.add_entity("block", block, normalize_name(f"{country}|{basin}|{sag}|{block}"), f"{country}/{basin}/{sag}", {}, source)
            if sid:
                self.add_fact(sid, "contains_block", blkid, source_doc=source)

        ofid = None
        if oilfield and block:
            ofid = self.add_entity("oilfield", oilfield, normalize_name(f"{country}|{basin}|{sag}|{block}|{oilfield}"), f"{country}/{basin}/{sag}/{block}", {}, source)
            if blkid:
                self.add_fact(blkid, "contains_oilfield", ofid, source_doc=source)

        stid = None
        if structure and oilfield:
            stid = self.add_entity("structure", structure, normalize_name(f"{country}|{basin}|{sag}|{block}|{oilfield}|{structure}"), f"{country}/{basin}/{sag}/{block}/{oilfield}", {}, source)
            if ofid:
                self.add_fact(ofid, "contains_structure", stid, source_doc=source)

        wid = None
        if well and structure:
            wid = self.add_entity("well", well, normalize_name(f"{country}|{basin}|{sag}|{block}|{oilfield}|{structure}|{well}"), f"{country}/{basin}/{sag}/{block}/{oilfield}/{structure}", {}, source)
            if stid:
                self.add_fact(stid, "contains_well", wid, source_doc=source)

        fmid = None
        if formation:
            fm_props = {
                "strata_meta": ensure_dict(rec.get("strata_meta")),
                "gwc": ensure_dict(rec.get("gwc")),
                "country": country,
                "basin": basin,
                "formation_raw": formation
            }
            fmid = self.add_entity(
                "formation",
                formation,
                normalize_name(f"{country}|{basin}|{formation}"),
                f"{country}/{basin}",
                fm_props,
                source
            )
            if wid:
                self.add_fact(wid, "has_formation", fmid, source_doc=source)

        if method_name and fmid:
            m_props = ensure_dict(rec.get("method_meta"))
            mid = self.add_entity(
                "interp_method",
                method_name,
                normalize_name(f"{country}|{basin}|{formation}|{method_name}"),
                f"{country}/{basin}/{formation}",
                m_props,
                source
            )
            self.add_fact(fmid, "recommend_interp_method", mid, source_doc=source)

    def scan_all(self) -> List[str]:
        errors: List[str] = []
        for subdir in STATIC_GEO.iterdir():
            if not subdir.is_dir() or subdir.name not in VALID_GEO_DIRS:
                continue
            for f in subdir.glob("*.json"):
                try:
                    raw = json.loads(f.read_text(encoding="utf-8-sig"))
                    fname = f.relative_to(STATIC_GEO).as_posix()
                    if isinstance(raw, list):
                        for item in raw:
                            self.ingest_single_record(item, fname)
                    else:
                        self.ingest_single_record(raw, fname)
                except Exception as e:
                    errors.append(f"{f.name} | {e}")
        return errors

    def run(self):
        self.connect()
        errs = self.scan_all()
        self.conn.commit()
        self.close()
        return errs


def scan_docs_in_path(root: str, stats_out: Optional[dict] = None) -> Tuple[int, List[str]]:
    """目录扫描入档（logknow 正统流程）：原件归档 + 结构化知识入 entity/fact 图谱。

    - 判重：文件内容 sha256（doc_fingerprints.txt），增量可断点续跑。
    - 归档优先：只要文件有效即归档原件到 static_geo/docs/，与抽取成功率解耦
      （原实现在「抽取无匹配」时连原件都不归档，英文资料等于零入档）。
    - 合规：显式敏感/纯行政路径跳过；正文 PII 仅只读记录不阻断（K-SYS-003 v2）。
    """
    root_p = Path(root)
    known_fp = load_fingerprints()
    total_records = 0
    errors: List[str] = []
    pii_list: List[str] = []
    stat = {'scanned': 0, 'archived': 0, 'with_records': 0, 'skip_known': 0,
            'skip_no_text': 0, 'sensitive': 0, 'pii_text': 0, 'too_large': 0}
    exts = {".pdf", ".docx", ".pptx", ".txt", ".md"}
    print(f"[scan] 开始遍历路径：{root_p}")

    for dirpath, _, filenames in os.walk(root_p):
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.suffix.lower() not in exts:
                continue
            stat['scanned'] += 1
            rel = str(fp).replace('\\', '/')
            low_rel = rel.lower()

            # 收录合规粗筛：仅显式敏感路径跳过，合同/税/服务类不误杀
            if any(k.lower() in low_rel for k in _SENSITIVE_PATH_KW):
                stat['sensitive'] += 1
                errors.append(f"[敏感跳过] {fp}")
                continue
            try:
                if fp.stat().st_size > 200 * 1024 * 1024:
                    stat['too_large'] += 1
                    errors.append(f"[超大跳过] {fp}")
                    continue
                h = file_sha256(fp)
            except Exception as e:
                errors.append(f"{fp} | {e}")
                continue
            if h in known_fp:
                stat['skip_known'] += 1
                continue

            text = ''
            try:
                text = extract_text_from_file(fp) or ''
            except Exception as e:
                errors.append(f"[解析失败] {fp} | {e}")

            # 正文 PII 只读抽查：只留清单供人工复核，不自动删改、不阻断归档
            if _PII_ID_RE.search(text) or _PII_PHONE_RE.search(text):
                stat['pii_text'] += 1
                pii_list.append(rel)

            # 归档优先：原件落 static_geo/docs/
            dst = DOC_ARCHIVE / f"{h[:24]}_{_safe_name(fp.name)}"
            try:
                if not dst.exists():
                    dst.write_bytes(fp.read_bytes())
                stat['archived'] += 1
            except Exception as e:
                errors.append(f"[归档失败] {fp} | {e}")

            # 结构化抽取尽力而为
            recs: List[Dict[str, Any]] = []
            if len(text.strip()) >= 60:
                try:
                    recs = simple_geo_extract(text, rel)
                except Exception as e:
                    errors.append(f"[抽取失败] {fp} | {e}")
            else:
                stat['skip_no_text'] += 1

            if recs:
                try:
                    loader = GeoKnowledgeLoader(DB_PATH)
                    loader.connect()
                    for r in recs:
                        loader.ingest_single_record(r, f"docs/{fp.name}")
                        total_records += 1
                    loader.conn.commit()
                    loader.close()
                    stat['with_records'] += 1
                except Exception as e:
                    errors.append(f"[入图谱失败] {fp} | {e}")

            save_fingerprint(h)
            known_fp.add(h)
            if stat['scanned'] % 200 == 0:
                print(f"[scan] 已扫描 {stat['scanned']} / 归档 {stat['archived']} / 知识记录 {total_records}",
                      flush=True)

    if stats_out is not None:
        stats_out.update(stat)
        stats_out['records'] = total_records
        stats_out['pii_list'] = pii_list
        stats_out['sensitive_list'] = [e for e in errors if e.startswith('[敏感跳过]')]
    return total_records, errors


def auto_scan_removable_docs(once: bool = True):
    drives = get_removable_drives()
    print(f"[drive] 识别移动盘列表：{drives}")
    if not drives:
        print("[warn] 没有识别到任何移动驱动器！")
        return 0, []
    known_drives = set(drives)
    total = 0
    all_errs = []

    def scan_drive(drive: str):
        cnt, errs = scan_docs_in_path(drive)
        return cnt, errs

    if once:
        for d in known_drives:
            c, e = scan_drive(d)
            total += c
            all_errs.extend(e)
        return total, all_errs

    try:
        while True:
            current = set(get_removable_drives())
            new_drives = current - known_drives
            for nd in new_drives:
                print(f"[auto] 检测移动盘 {nd}，开始文档抽取入库")
                c, e = scan_drive(nd)
                total += c
                all_errs.extend(e)
            known_drives = current
            time.sleep(3)
    except KeyboardInterrupt:
        pass
    return total, all_errs


def lookup_interp_method(country: str, basin: str, formation: str):
    cn = normalize_name(country)
    bn = normalize_name(basin)
    fn = normalize_name(formation)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT e.id, e.name, e.props_json, e.region
        FROM entity e
        WHERE e.kind = 'formation'
    """)
    form_map: Dict[str, Dict[str, Any]] = {}
    for row in cur.fetchall():
        props = json.loads(row["props_json"])
        form_map[row["id"]] = {
            "name": row["name"],
            "props": props
        }

    cur.execute("""
        SELECT f.subj, f.obj, e.name, e.props_json
        FROM fact f
        JOIN entity e ON f.obj = e.id
        WHERE f.rel = 'recommend_interp_method' AND e.kind = 'interp_method'
    """)

    candidates = []
    for row in cur.fetchall():
        fid = row["subj"]
        fm = form_map.get(fid, {})
        fm_props = fm.get("props", {})
        m_props = json.loads(row["props_json"])

        f_country = normalize_name(fm_props.get("country", ""))
        f_basin = normalize_name(fm_props.get("basin", ""))
        f_form = normalize_name(fm_props.get("formation_raw", ""))

        score = 0
        if f_country == cn:
            score += 40
        if f_basin == bn:
            score += 35
        if f_form == fn:
            score += 25

        if score > 0:
            candidates.append({
                "score": score,
                "country": fm_props.get("country", ""),
                "basin": fm_props.get("basin", ""),
                "formation": fm_props.get("formation_raw", ""),
                "method_name": row["name"],
                "threshold": m_props.get("threshold", {}),
                "formula": m_props.get("formula", ""),
                "condition": m_props.get("condition", ""),
                "full_meta": m_props
            })
    conn.close()

    if not candidates:
        return {
            "ok": False,
            "msg": "未找到该【国家+盆地+地层】对应的解释方法",
            "country": country,
            "basin": basin,
            "formation": formation
        }

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[0]
    return {
        "ok": True,
        "match_score": top["score"],
        "country": top["country"],
        "basin": top["basin"],
        "formation": top["formation"],
        "method_name": top["method_name"],
        "threshold": top["threshold"],
        "formula": top["formula"],
        "condition": top["condition"],
        "alternatives": candidates[1:3]
    }


def cli_scan():
    cnt, err = auto_scan_removable_docs(once=True)
    print(f"\n本次新增知识记录：{cnt}")
    for e in err:
        print(e)


def main():
    import sys
    argv = sys.argv[1:]
    loader = GeoKnowledgeLoader(DB_PATH)
    if not argv:
        print("subcommand: check | bootstrap | scan | scanpath <root>")
        return
    if argv[0] == "check":
        errs = loader.run()
        if errs:
            print("\n==== 错误列表 ====")
            for e in errs:
                print(f"ERR: {e}")
        else:
            print("✅ 全部静态 geo 文件校验通过，无异常")
    elif argv[0] == "bootstrap":
        errs = loader.run()
        if errs:
            print(f"入库过程存在 {len(errs)} 条错误：")
            for e in errs:
                print(e)
        else:
            print("✅ bootstrap 入库完成")
    elif argv[0] == "scan":
        cli_scan()
    elif argv[0] == "scanpath":
        if len(argv) < 2:
            print("usage: bootstrap_knowledge.py scanpath <root>")
            return
        st: Dict[str, Any] = {}
        cnt, errs = scan_docs_in_path(argv[1], stats_out=st)
        print(f"\n[scanpath] 扫描 {st.get('scanned', 0)} / 归档原件 {st.get('archived', 0)} / "
              f"含结构化知识 {st.get('with_records', 0)} / 知识记录 {cnt}")
        print(f"[scanpath] 跳过：已入 {st.get('skip_known', 0)} / 无有效文本 {st.get('skip_no_text', 0)} / "
              f"敏感路径 {st.get('sensitive', 0)} / 超大 {st.get('too_large', 0)}；"
              f"PII 待复核 {st.get('pii_text', 0)}")
        real_err = [e for e in errs if not e.startswith('[敏感跳过]')]
        print(f"[scanpath] 失败 {len(real_err)} 条")
        for e in real_err[:15]:
            print("   ", e)
        if st.get('pii_list'):
            print("[scanpath] PII 待复核示例：", st['pii_list'][:3])
    else:
        print("unknown cmd")


if __name__ == "__main__":
    main()
