# -*- coding: utf-8 -*-
"""给 logknow/bootstrap_knowledge.py 打补丁：
1) 合规粗筛 + 路径派生国别/盆地/井 + 中英双语结构化抽取
2) scan_docs_in_path 归档优先（抽取为空仍归档原件）、PII 只读抽查、超大跳过
3) main() 新增 scanpath <root> 子命令（支持 G: 固定盘）
保持 check/bootstrap/scan 原有行为不变；写一个 UTF-8 BOM + LF 的新文件并原子替换。
"""
import os
from pathlib import Path

P = Path('logknow/bootstrap_knowledge.py')
raw = P.read_bytes()
bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
body = raw[len(bom):].decode('utf-8')

PATCHES = []

# ---- 1. import re ----
PATCHES.append((
    "import hashlib\nimport os\n\ntry:",
    "import hashlib\nimport os\nimport re\n\ntry:",
    1,
))

# ---- 2. 替换 simple_geo_extract（新增合规常量与路径派生） ----
OLD_EXTRACT = '''def simple_geo_extract(raw_text: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    lines = raw_text.splitlines()
    country = ""
    basin = ""
    formation = ""
    method_name = ""
    threshold: Dict[str, Any] = {}
    formula = ""
    condition = ""

    for line in lines:
        l = line.strip()
        if not l:
            continue
        if "国家" in l or "国别" in l:
            if "：" in l:
                country = l.split("：")[-1]
            else:
                country = l
        if "盆地" in l:
            if "：" in l:
                basin = l.split("：")[-1]
            else:
                basin = l
        if "地层" in l or "组" in l:
            formation = l
        if "解释方法" in l or "测井方法" in l:
            if "：" in l:
                method_name = l.split("：")[-1]
            else:
                method_name = l
        if "公式" in l:
            formula = l
        if "适用条件" in l:
            condition = l
        if "阈值" in l:
            threshold["note"] = l

    if country and formation:
        rec = {
            "country": country,
            "basin": basin,
            "sag": "",
            "block": "",
            "oilfield": "",
            "structure": "",
            "well": "",
            "formation": formation,
            "strata_meta": {"raw_source": "document_extract"},
            "method_name": method_name,
            "method_meta": {
                "threshold": threshold,
                "formula": formula,
                "condition": condition
            },
            "gwc": {}
        }
        records.append(rec)
    return records
'''

NEW_EXTRACT = '''# ---------- 收录合规粗筛（K-SYS-003 v2：按内容实质判定，不按文种一刀切） ----------
# 仅排除显式个人隐私 / 纯行政 / 交易凭证类路径；「合同 / 税 / 服务 / 财税政策」
# 属可入档的需求侧专业史料与区域专属知识，不在排除之列。
_SENSITIVE_PATH_KW = (
    '人事任免', '考勤', '薪资', '工资表', '身份证', '护照号', '个人简历', '私人电话',
    '银行账户', '付款凭证', '发票流水', '报销单', '诉讼', '仲裁', '涉密',
    'passport', 'payroll', 'salary', 'resume', 'bank account', 'invoice', 'litigation',
)
_PII_ID_RE = re.compile(r'(?<!\\d)\\d{17}[\\dXx](?!\\d)')
_PII_PHONE_RE = re.compile(r'(?<!\\d)1[3-9]\\d{9}(?!\\d)')


def _safe_name(name: str) -> str:
    s = re.sub(r'[<>:\"/\\\\|?*\\x00-\\x1f]', '_', ensure_str(name))
    return (s[:80] or 'doc')


def _from_path(path_hint: str) -> Tuple[str, str, str]:
    """从 '.../入库整理后/<Country>/<Basin>/<Well>/...' 派生 国别/盆地/井。
    G 盘目录层级本身即权威区域信息，比从英文正文猜国家可靠。"""
    seg = [x for x in ensure_str(path_hint).replace('\\\\', '/').split('/') if x]
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
        'country':   ('country', 'nation', '国别', '国家'),
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
        "strata_meta": {"raw_source": "document_extract", "source_path": path_hint},
        "method_name": method_name,
        "method_meta": {
            "threshold": threshold,
            "formula": formula,
            "condition": condition
        },
        "gwc": {}
    }]
'''
PATCHES.append((OLD_EXTRACT, NEW_EXTRACT, 1))

# ---- 3. 替换 scan_docs_in_path（归档优先 + 合规 + 统计） ----
OLD_SCAN = '''def scan_docs_in_path(root: str) -> Tuple[int, List[str]]:
    root_p = Path(root)
    known_fp = load_fingerprints()
    total_records = 0
    errors: List[str] = []
    exts = {".pdf", ".docx", ".pptx", ".txt", ".md"}
    print(f"[scan] 开始遍历路径：{root_p}")

    for dirpath, _, filenames in os.walk(root_p):
        for fn in filenames:
            fp = Path(dirpath) / fn
            suffix = fp.suffix.lower()
            if suffix not in exts:
                continue
            h = file_sha256(fp)
            if h in known_fp:
                print(f"[skip] 已入库：{fp}")
                continue
            try:
                text = extract_text_from_file(fp)
                if not text or len(text) < 60:
                    print(f"[skip] 文本过短：{fp}")
                    save_fingerprint(h)
                    continue
                recs = simple_geo_extract(text)
                if not recs:
                    print(f"[skip] 抽取无匹配：{fp}")
                    save_fingerprint(h)
                    continue
                dst = DOC_ARCHIVE / f"{h}_{fp.name}"
                dst.write_bytes(fp.read_bytes())
                loader = GeoKnowledgeLoader(DB_PATH)
                loader.connect()
                for r in recs:
                    loader.ingest_single_record(r, f"docs/{fp.name}")
                    total_records += 1
                loader.conn.commit()
                loader.close()
                save_fingerprint(h)
                print(f"[ok] 新增 {len(recs)} 条：{fp}")
            except Exception as e:
                errors.append(f"{fp} | {e}")
                print(f"[err] {fp} -> {e}")
    return total_records, errors
'''

NEW_SCAN = '''def scan_docs_in_path(root: str, stats_out: Optional[dict] = None) -> Tuple[int, List[str]]:
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
            rel = str(fp).replace('\\\\', '/')
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
'''
PATCHES.append((OLD_SCAN, NEW_SCAN, 1))

# ---- 4. main() 提示与 scanpath 子命令 ----
PATCHES.append((
    '        print("subcommand: check | bootstrap | scan")',
    '        print("subcommand: check | bootstrap | scan | scanpath <root>")',
    1,
))
PATCHES.append((
    '''    elif argv[0] == "scan":
        cli_scan()
    else:
        print("unknown cmd")''',
    '''    elif argv[0] == "scan":
        cli_scan()
    elif argv[0] == "scanpath":
        if len(argv) < 2:
            print("usage: bootstrap_knowledge.py scanpath <root>")
            return
        st: Dict[str, Any] = {}
        cnt, errs = scan_docs_in_path(argv[1], stats_out=st)
        print(f"\\n[scanpath] 扫描 {st.get('scanned', 0)} / 归档原件 {st.get('archived', 0)} / "
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
        print("unknown cmd")''',
    1,
))

# ---- 执行替换并校验命中数 ----
for i, (old, new, expect) in enumerate(PATCHES, 1):
    n = body.count(old)
    if n != expect:
        raise SystemExit(f'PATCH {i} 命中数异常: 期望 {expect}, 实际 {n}')
    body = body.replace(old, new, expect)
    print(f'PATCH {i}: OK (命中 {n})')

out = bom + body.encode('utf-8')
tmp = P.with_suffix('.py.tmp')
tmp.write_bytes(out)
os.replace(tmp, P)
print(f'=== 原子替换完成: {P} | {len(out)} bytes ===')
