# -*- coding: utf-8 -*-
"""文档入库：markdown/docx → doc/chunk/FTS + 轻量实体/事实抽取。

- 中文 FTS：用 jieba 预分词后写入 doc_fts.body（同时保留原文 chunk.text）；
- frontmatter 字段（category/region/country/well_name/depth_range/title）解析入列；
- 实体抽取（MVP）：井名正则、国家/区块词典；事实：well LOCATED_IN country/region；
- 幂等：按 path 去重（重跑不会重复入库，除非 --force）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from .db import connect
try:
    from .entities import (extract_entities, canon_well, canon_field, canon_formation)
except Exception:
    extract_entities = None

try:
    import jieba
    jieba.setLogLevel(60)
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

WELL_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:[-\s][A-Za-z0-9]+){0,3}[-\s](?:\d{1,3}[A-Za-z]?))\b')
COUNTRIES = ['Chad', '乍得', 'Brazil', '巴西', 'Uzbekistan', '乌兹别克', 'Indonesia', '印尼',
             'Bangladesh', '孟加拉', 'Niger', '尼日尔', 'Kazakhstan', '哈萨克', 'Sudan', '苏丹',
             'Venezuela', '委内瑞拉', 'Peru', '秘鲁', 'Canada', '加拿大', 'Australia', '澳洲']

# 路径/标题国别推导：规范中文名 <- 中文名/别名/英文名（最长匹配，避免 印度⊂印度尼西亚、南苏丹⊂苏丹 误判）
# 覆盖图谱 90 国。英文用整词边界，中文用子串。
_COUNTRY_EN = {'中国': 'China', '乌克兰': 'Ukraine', '乌兹别克斯坦': 'Uzbekistan', '乍得': 'Chad',
    '也门': 'Yemen', '伊拉克': 'Iraq', '伊朗': 'Iran', '俄罗斯': 'Russia', '保加利亚': 'Bulgaria',
    '克罗地亚': 'Croatia', '刚果（布）': 'Congo-Brazzaville', '刚果（金）': 'DR Congo', '利比亚': 'Libya',
    '利比里亚': 'Liberia', '加拿大': 'Canada', '加纳': 'Ghana', '南苏丹': 'South Sudan', '卡塔尔': 'Qatar',
    '印度尼西亚': 'Indonesia', '危地马拉': 'Guatemala', '厄瓜多尔': 'Ecuador', '叙利亚': 'Syria',
    '古巴': 'Cuba', '哈萨克斯坦': 'Kazakhstan', '哥伦比亚': 'Colombia', '喀麦隆': 'Cameroon',
    '土库曼斯坦': 'Turkmenistan', '圭亚那': 'Guyana', '坦桑尼亚': 'Tanzania', '埃及': 'Egypt',
    '塞内加尔': 'Senegal', '塞尔维亚': 'Serbia', '墨西哥': 'Mexico', '孟加拉国': 'Bangladesh',
    '安哥拉': 'Angola', '尼日利亚': 'Nigeria', '尼日尔': 'Niger', '巴基斯坦': 'Pakistan',
    '巴布亚新几内亚': 'Papua New Guinea', '巴拿马': 'Panama', '巴西': 'Brazil', '布基纳法索': 'Burkina Faso',
    '意大利': 'Italy', '挪威': 'Norway', '摩洛哥': 'Morocco', '斯里兰卡': 'Sri Lanka',
    '新西兰': 'New Zealand', '智利': 'Chile', '柬埔寨': 'Cambodia', '格鲁吉亚': 'Georgia',
    '毛里塔尼亚': 'Mauritania', '沙特阿拉伯': 'Saudi Arabia', '澳大利亚': 'Australia',
    '特立尼达和多巴哥': 'Trinidad and Tobago', '玻利维亚': 'Bolivia', '科威特': 'Kuwait',
    '科特迪瓦': 'Cote dIvoire', '秘鲁': 'Peru', '突尼斯': 'Tunisia', '索马里': 'Somalia',
    '约旦': 'Jordan', '缅甸': 'Myanmar', '罗马尼亚': 'Romania', '美国': 'United States',
    '肯尼亚': 'Kenya', '苏丹': 'Sudan', '苏里南': 'Suriname', '英国': 'United Kingdom',
    '西班牙': 'Spain', '越南': 'Vietnam', '阿塞拜疆': 'Azerbaijan', '阿尔及利亚': 'Algeria',
    '阿尔巴尼亚': 'Albania', '阿曼': 'Oman', '阿根廷': 'Argentina', '阿联酋': 'UAE',
    '马来西亚': 'Malaysia', '马达加斯加': 'Madagascar', '东帝汶': 'Timor-Leste', '乌拉圭': 'Uruguay',
    '加蓬': 'Gabon', '印度': 'India', '埃塞俄比亚': 'Ethiopia', '塞浦路斯': 'Cyprus', '文莱': 'Brunei',
    '泰国': 'Thailand', '纳米比亚': 'Namibia', '菲律宾': 'Philippines', '土耳其': 'Turkey',
    '乌干达': 'Uganda'}
# 额外常见别名
_COUNTRY_EXTRA = {'孟加拉': '孟加拉国', '哈萨克': '哈萨克斯坦', '印尼': '印度尼西亚', '阿联': '阿联酋',
    '阿拉伯联合酋长国': '阿联酋', '刚果共和国': '刚果（布）', '刚果民主共和国': '刚果（金）',
    'UAE': '阿联酋', 'USA': '美国', 'UK': '英国'}

_COUNTRY_PATH_MAP = {}  # alias(lower) -> canonical zh
for _cn, _en in _COUNTRY_EN.items():
    _COUNTRY_PATH_MAP[_cn.lower()] = _cn
    _COUNTRY_PATH_MAP[_en.lower()] = _cn
for _a, _cn in _COUNTRY_EXTRA.items():
    _COUNTRY_PATH_MAP[_a.lower()] = _cn
_CN_ALIASES = [a for a in _COUNTRY_PATH_MAP if re.search(r'[\u4e00-\u9fff]', a)]
_EN_ALIASES = [(a, c) for a, c in _COUNTRY_PATH_MAP.items() if not re.search(r'[\u4e00-\u9fff]', a)]


def detect_country(path: str, title: str = '') -> str:
    """从文件路径/标题推导国别（规范中文名）。无命中返回空串。"""
    blob = '%s %s' % (path or '', title or '')
    low = blob.lower()
    hits = []
    for a in _CN_ALIASES:
        if a in blob:
            hits.append((len(a), _COUNTRY_PATH_MAP[a]))
    for a, c in _EN_ALIASES:
        if re.search(r'(?<![a-z])' + re.escape(a) + r'(?![a-z])', low):
            hits.append((len(a), c))
    if not hits:
        return ''
    hits.sort(reverse=True)
    return hits[0][1]


def tokenize(text: str) -> str:
    """中文预分词（供 FTS5 unicode61 使用）。"""
    if not text:
        return ''
    if _HAS_JIEBA:
        return ' '.join(t for t in jieba.lcut(text) if t.strip())
    return re.sub(r'([\u4e00-\u9fff])', r' \1 ', text)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8', 'replace')).hexdigest()


def _split_frontmatter(text: str):
    if text.startswith('---'):
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n?', text, re.S)
        if m:
            fm = {}
            for line in m.group(1).splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip()
            return fm, text[m.end():]
    return {}, text


def _chunks(text: str):
    n = len(text)
    if n <= CHUNK_SIZE:
        return [text]
    out, i = [], 0
    while i < n:
        out.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return out


WELL_NOISE_PREFIX = ('layer', 'step', 'swab', 'section', 'table', 'figure', 'fig', 'eq',
                      'well', 'no.', 'test', 'sample', 'zone', 'unit', 'block', 'page',
                      'phase', 'stage', 'case', 'run', 'point', 'interval', 'depth',
                      'ltaf', 'taf', 'utaf', 'gumai', 'sokor', 'baturaja', 'talang',
                      'e1-', 'e2-', 'e3-', 'e5-', 'rop', 'tg', 'gr', 'rt', 'sw', 'por',
                      'perm', 'p10', 'p50', 'p90', 'wob', 'rpm', 'trpm', 'yp', 'pv')


WELL_WHITELIST = set()
try:
    import json as _json
    _wl = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'well_whitelist.json')
    if os.path.exists(_wl):
        WELL_WHITELIST = {re.sub(r'[\s_]+', '-', str(x)).upper()
                          for x in _json.load(open(_wl, encoding='utf-8'))}
except Exception:
    WELL_WHITELIST = set()

STRICT_WELL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9]*?(?:-[A-Za-z0-9]+)*-\d{1,3}[A-Za-z]?$')
STRICT_WELL_RE2 = re.compile(r'^[A-Za-z0-9]+-[A-Za-z0-9]+-\d{1,3}[A-Za-z]?$')


def valid_well_name(name: str) -> bool:
    """井名校验：白名单优先，或严格"字母-NN"格式；拒绝 Layer 3/GR 156/SW 100 等噪声。"""
    n = str(name or '').strip()
    if not (3 <= len(n) <= 25):
        return False
    low = n.lower()
    if any(low.startswith(p) for p in WELL_NOISE_PREFIX):
        return False
    if not re.search(r'\d', n):
        return False
    if canon_well(n) in WELL_WHITELIST:
        return True
    return bool(STRICT_WELL_RE.match(n) or STRICT_WELL_RE2.match(n))


def canon_well(name: str) -> str:
    return re.sub(r'[\s_]+', '-', str(name or '').strip()).upper()


def _find_entities(text: str, fm: dict):
    wells = set()
    for m in WELL_RE.finditer(text[:20000]):
        w = m.group(1).strip()
        if valid_well_name(w):
            wells.add(w)
    if fm.get('well_name') and valid_well_name(str(fm['well_name'])):
        wells.add(str(fm['well_name']).strip())
    countries = {c for c in COUNTRIES if c in text[:5000]}
    if fm.get('country'):
        countries.add(str(fm['country']).strip())
    return wells, countries


def ingest_markdown(conn, path: str, force: bool = False) -> str:
    """入库一个 md 文件；返回 doc_id（已存在且未 force 时返回原 id）。"""
    mtime = os.path.getmtime(path)
    raw = open(path, encoding='utf-8', errors='replace').read()
    sha1 = _sha1(raw)
    row = conn.execute('SELECT id, sha1, mtime FROM doc WHERE path=?', (path,)).fetchone()
    if row and not force and row[1] == sha1:
        return row[0]
    doc_id = 'DOC:' + hashlib.sha1(path.encode('utf-8', 'replace')).hexdigest()[:16]
    fm, body = _split_frontmatter(raw)
    title = fm.get('title') or os.path.splitext(os.path.basename(path))[0]
    region = fm.get('region') or fm.get('detected_region') or ''
    country = fm.get('country') or detect_country(path, title)
    well = fm.get('well_name') or ''
    category = fm.get('category') or fm.get('file_type') or ''

    conn.execute('DELETE FROM chunk WHERE doc_id=?', (doc_id,))
    conn.execute('DELETE FROM doc_fts WHERE doc_id=?', (doc_id,))
    conn.execute('INSERT OR REPLACE INTO doc(id, path, title, category, region, country, well, '
                 'sha1, mtime, chars, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                 (doc_id, path, title, category, region, country, well, sha1, mtime, len(body),
                  json.dumps(fm, ensure_ascii=False)[:4000]))
    for i, ch in enumerate(_chunks(body)):
        cid = '%s#%03d' % (doc_id, i)
        conn.execute('INSERT OR REPLACE INTO chunk(id, doc_id, idx, text, chars) VALUES(?,?,?,?,?)',
                     (cid, doc_id, i, ch, len(ch)))
        conn.execute('INSERT INTO doc_fts(doc_id, title, body, region, well) VALUES(?,?,?,?,?)',
                     (doc_id, tokenize(title), tokenize(ch), region, well))

    # 轻量实体/事实（Well/Field/Formation 归一化；先清本文档旧抽取结果）
    conn.execute('DELETE FROM entity WHERE source_doc=?', (doc_id,))
    conn.execute('DELETE FROM fact WHERE source_doc=?', (doc_id,))
    if extract_entities is not None:
        countries = {c for c in COUNTRIES if c in body[:5000]}
        if fm.get('country'):
            countries.add(str(fm['country']).strip())
        ents = extract_entities(body, fm)
        primary_field = next(iter(ents['Field']), '')
        _fm_well = canon_well(str(fm.get('well_name') or ''))
        for kind, items in ents.items():
            for canon, info in list(items.items())[:30]:
                pref = {'Well': 'WELL', 'Field': 'FIELD', 'Formation': 'FRM'}[kind]
                eid = '%s:%s' % (pref, canon)
                conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, '
                             'props_json, source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                             (eid, kind, info['name'], canon, region,
                              json.dumps({'aliases': sorted(info['aliases'])}, ensure_ascii=False),
                              doc_id, float(info['conf'])))
                if kind == 'Well':
                    if country:
                        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                     'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                     ('FACT:%s:LOCATED_IN:%s' % (eid, _sha1(country)[:8]),
                                      eid, 'LOCATED_IN', 'COUNTRY:%s' % country, '{}',
                                      doc_id, 'frontmatter', 0.8, 'rule:frontmatter'))
                    _single_well = (len(ents['Well']) == 1) or bool(str(fm.get('well_name') or '').strip())
                    _assign_field = bool(primary_field) and _single_well and \
                        (len(ents['Well']) == 1 or canon == _fm_well)
                    if _assign_field:
                        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                     'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                     ('FACT:%s:IN_FIELD:%s' % (eid, _sha1(primary_field)[:8]),
                                      eid, 'IN_FIELD', 'FIELD:%s' % primary_field, '{}',
                                      doc_id, 'entity', 0.7, 'rule:entity'))
                if kind == 'Field' and country:
                    conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                 'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                 ('FACT:%s:LOCATED_IN:%s' % (eid, _sha1(country)[:8]),
                                  eid, 'LOCATED_IN', 'COUNTRY:%s' % country, '{}',
                                  doc_id, 'entity', 0.7, 'rule:entity'))
        # 国家实体保留
        for c in list(countries)[:5]:
            cid = 'COUNTRY:%s' % c
            conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json, '
                         'source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                         (cid, 'Country', c, cid, c, '{}', doc_id, 0.7))
    else:
        # 兜底：旧逻辑
        wells, countries = _find_entities(body, fm)
        for w in list(wells)[:20]:
            cn = canon_well(w)
            eid = 'WELL:%s' % cn
            conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json, '
                         'source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                         (eid, 'Well', w, cn, region, '{}', doc_id, 0.6))
    conn.commit()
    return doc_id


def ingest_file(conn, path: str, force=False) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.md':
        return ingest_markdown(conn, path, force=force)
    if ext == '.docx':
        return _ingest_docx(conn, path, force=force)
    raise ValueError('unsupported: ' + path)


def _ingest_docx(conn, path: str, force=False) -> str:
    """docx → 文本 → 复用 md 入库逻辑（临时不落盘：直接调用内部函数）。"""
    from docx import Document
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    # 表格文本
    for t in doc.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                paras.append(' | '.join(cells))
    body = '\n'.join(paras)
    doc_id = 'DOC:' + hashlib.sha1(path.encode('utf-8', 'replace')).hexdigest()[:16]
    row = conn.execute('SELECT id, sha1 FROM doc WHERE path=?', (path,)).fetchone()
    sha1 = _sha1(body)
    if row and not force and row[1] == sha1:
        return row[0]
    conn.execute('DELETE FROM chunk WHERE doc_id=?', (doc_id,))
    conn.execute('DELETE FROM doc_fts WHERE doc_id=?', (doc_id,))
    conn.execute('INSERT OR REPLACE INTO doc(id, path, title, category, region, country, well, '
                 'sha1, mtime, chars, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                 (doc_id, path, os.path.splitext(os.path.basename(path))[0], 'docx', '', '', '',
                  sha1, os.path.getmtime(path), len(body), '{}'))
    for i, ch in enumerate(_chunks(body)):
        cid = '%s#%03d' % (doc_id, i)
        conn.execute('INSERT OR REPLACE INTO chunk(id, doc_id, idx, text, chars) VALUES(?,?,?,?,?)',
                     (cid, doc_id, i, ch, len(ch)))
        conn.execute('INSERT INTO doc_fts(doc_id, title, body, region, well) VALUES(?,?,?,?,?)',
                     (doc_id, tokenize(os.path.basename(path)), tokenize(ch), '', ''))
    conn.commit()
    return doc_id


def ingest_directory(conn, root: str, limit: int | None = None, force=False,
                     exts=('.md', '.docx')) -> dict:
    """递归入库目录（默认 md/docx），返回统计。"""
    ok, fail = 0, []
    n = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ('__pycache__', '.git', 'node_modules')]
        for f in sorted(fn):
            if f.startswith('~$') or f.startswith('.'):
                continue
            if not f.lower().endswith(exts):
                continue
            p = os.path.join(dp, f)
            try:
                ingest_file(conn, p, force=force)
                ok += 1
            except Exception as e:
                fail.append((p, '%s: %s' % (type(e).__name__, e)))
            n += 1
            if limit and n >= limit:
                return {'ok': ok, 'fail': len(fail), 'errors': fail[:10], 'stopped_at_limit': limit}
    return {'ok': ok, 'fail': len(fail), 'errors': fail[:10]}
