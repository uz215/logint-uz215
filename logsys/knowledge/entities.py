# -*- coding: utf-8 -*-
"""实体抽取/归一化：Well / Field / Formation 三类 + 黑名单。

设计目标（用户要求"实体归一化 + 黑名单按 Field/Well/Formation 规范化"）：
- 每类都有：噪声前缀黑名单、格式校验、canonical 规范化、别名表；
- Well：白名单 + 严格"字母-NN"格式（沿用 ingest.py 既有逻辑并集中到此）；
- Field：区块/田词典（含从各井 info.json 自动收集的 field_name）+ "Xxx Block/Field/Basin" 正则；
- Formation：地层词典（LTAF/UTAF/TAF/BRF/GUF/...）+ 别名归一（LTAF-1/LTAF1 → LTAF-1？见下）；
- 输出 {kind: {canonical: {'name':..., 'aliases': set}}} 供入库。
"""
from __future__ import annotations

import glob
import json
import os
import re

BASE = r'D:\360\src'

# --------------------------------------------------------------------------- #
# 黑名单
# --------------------------------------------------------------------------- #
WELL_NOISE_PREFIX = (
    'layer', 'step', 'swab', 'section', 'table', 'figure', 'fig', 'eq', 'well',
    'no.', 'test', 'sample', 'zone', 'unit', 'block', 'page', 'phase', 'stage',
    'case', 'run', 'point', 'interval', 'depth', 'ltaf', 'taf', 'utaf', 'gumai',
    'sokor', 'baturaja', 'talang', 'e1-', 'e2-', 'e3-', 'e5-', 'rop', 'tg', 'gr',
    'rt', 'sw', 'por', 'perm', 'p10', 'p50', 'p90', 'wob', 'rpm', 'trpm', 'yp', 'pv',
)
FIELD_NOISE = {'block', 'field', 'basin', 'area', 'region', 'formation', 'zone',
               'reservoir', 'prospect', 'play', 'trend', 'structure', 'target',
               'gas block', 'oil block', 'gas field', 'oil field', 'the block',
               'this block', 'the field', 'this field'}
FORMATION_NOISE = {'formation', 'member', 'group', 'sand', 'shale', 'limestone',
                   'dolomite', 'coal', 'tight', 'reservoir', 'zone', 'interval',
                   'section', 'layer', 'unit', 'top', 'base', 'e1', 'e2', 'e3', 'e5'}

# 地层词典：canonical → aliases（大小写不敏感匹配；别名按词界）
FORMATION_LEXICON = {
    'LTAF': ['LTAF', 'Lower Talang Akar', '下 Talang Akar', '下 Talangakar'],
    'LTAF-1': ['LTAF-1', 'LTAF1', 'LTAF-1 段'],
    'LTAF-2': ['LTAF-2', 'LTAF2', 'LTAF-2 段'],
    'UTAF': ['UTAF', 'Upper Talang Akar', '上 Talang Akar'],
    'TAF': ['TAF', 'Talang Akar', 'Talangakar'],
    'BRF': ['BRF', 'Baturaja'],
    'GUF': ['GUF', 'Gumai'],
    'Lahat': ['Lahat'],
    'Kasai': ['Kasai'],
    'Sokor': ['Sokor', 'Sokor Shales'],
    'Bilma': ['Bilma'],
}

# 区块/田词典：canonical → aliases（动态部分从各井 info.json 补充）
FIELD_LEXICON = {
    'Jabung Tengah Block': ['Jabung Tengah Block', 'Jabung Tengah', 'Jabung'],
    'Bilma Block': ['Bilma Block', 'Bilma'],
    'Rashidpur': ['Rashidpur', 'RASHIDPUR'],
    'CuraCao': ['CuraCao', 'Curaçao'],
    'Titas': ['Titas'],
}

FIELD_RE = re.compile(r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s+(Block|Field|Basin)\b')
WELL_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:[-\s][A-Za-z0-9]+){0,3}[-\s](?:\d{1,3}[A-Za-z]?))\b')
STRICT_WELL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9]*?(?:-[A-Za-z0-9]+)*-\d{1,3}[A-Za-z]?$')
STRICT_WELL_RE2 = re.compile(r'^[A-Za-z0-9]+-[A-Za-z0-9]+-\d{1,3}[A-Za-z]?$')


def _load_whitelist() -> set:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'well_whitelist.json')
    try:
        return {canon_well(x) for x in json.load(open(p, encoding='utf-8'))}
    except Exception:
        return set()


WELL_WHITELIST = _load_whitelist()


def canon_well(name: str) -> str:
    return re.sub(r'[\s_]+', '-', str(name or '').strip()).upper()


def canon_field(name: str) -> str:
    s = re.sub(r'\s+', ' ', str(name or '').strip())
    m = re.match(r'^(.*?)\s+(Block|Field|Basin)$', s, flags=re.I)
    if m:
        base, suf = m.group(1), m.group(2)
    else:
        base, suf = s, ''
    base = ' '.join(w.capitalize() if w.isupper() or w.islower() else w for w in base.split())
    return (base + (' ' + suf.capitalize() if suf else '')).strip()


def canon_formation(name: str) -> str:
    s = str(name or '').strip()
    up = s.upper()
    if up in FORMATION_LEXICON:
        return up
    # 别名反查
    for canon, aliases in FORMATION_LEXICON.items():
        if up == canon.upper() or any(up == a.upper() for a in aliases):
            return canon
    return s


def _dynamic_field_lexicon() -> dict:
    lex = {k: list(v) for k, v in FIELD_LEXICON.items()}
    for root in (os.path.join(BASE, 'output'),
                 r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace\output',
                 r'D:\360\Indonesia', r'D:\360\Niger', r'D:\360\Bangladesh'):
        for p in glob.glob(os.path.join(root, '*', '*info.json'))[:200]:
            try:
                cfg = json.load(open(p, encoding='utf-8'))
                if isinstance(cfg, dict):
                    fn = (cfg.get('井信息') or {}).get('field_name')
                    if fn:
                        c = canon_field(fn)
                        lex.setdefault(c, [])
                        if fn not in lex[c]:
                            lex[c].append(fn)
            except Exception:
                continue
    return lex


def valid_well_name(name: str) -> bool:
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


def valid_field(name: str) -> bool:
    n = str(name or '').strip()
    if not (3 <= len(n) <= 40):
        return False
    if n.strip().lower() in FIELD_NOISE:
        return False
    if not re.search(r'[A-Za-z]', n):
        return False
    # 字段必须带 Block/Field/Basin 后缀或为已知词典条目
    if re.search(r'\b(Block|Field|Basin)$', n, flags=re.I):
        return True
    return canon_field(n) in FIELD_LEXICON


def valid_formation(name: str) -> bool:
    n = str(name or '').strip()
    if not (2 <= len(n) <= 30):
        return False
    if n.lower() in FORMATION_NOISE:
        return False
    if not re.search(r'[A-Za-z]', n):
        return False
    return canon_formation(n) in FORMATION_LEXICON or n.upper() in FORMATION_LEXICON


def _match_lexicon(text: str, lexicon: dict) -> dict:
    """按别名词界匹配词典，返回 {canonical: set(aliases)}（最长别名优先）。"""
    found = {}
    flat = []
    for canon, aliases in lexicon.items():
        for a in [canon] + list(aliases):
            flat.append((a, canon))
    flat.sort(key=lambda x: -len(x[0]))
    for alias, canon in flat:
        pat = re.compile(r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])', re.I)
        if pat.search(text):
            found.setdefault(canon, set()).add(alias)
    return found


def extract_entities(text: str, fm: dict | None = None) -> dict:
    """返回 {kind: {canonical: {'name':..., 'aliases': set, 'conf': float}}}。"""
    fm = fm or {}
    out = {'Well': {}, 'Field': {}, 'Formation': {}}

    # ---- Well ----
    for m in WELL_RE.finditer(text[:20000]):
        w = m.group(1).strip()
        if valid_well_name(w):
            c = canon_well(w)
            out['Well'].setdefault(c, {'name': w, 'aliases': set(), 'conf': 0.6})
            out['Well'][c]['aliases'].add(w)
    wn = str(fm.get('well_name') or '').strip()
    if wn and valid_well_name(wn):
        c = canon_well(wn)
        out['Well'].setdefault(c, {'name': wn, 'aliases': set(), 'conf': 0.9})
        out['Well'][c]['aliases'].add(wn)

    # ---- Field ----
    lex = _dynamic_field_lexicon()
    for canon, aliases in _match_lexicon(text, lex).items():
        if valid_field(canon):
            name = canon
            out['Field'].setdefault(canon, {'name': name, 'aliases': set(), 'conf': 0.7})
            out['Field'][canon]['aliases'] |= aliases
    for m in FIELD_RE.finditer(text):
        cand = canon_field(m.group(1) + ' ' + m.group(2))
        if valid_field(cand):
            out['Field'].setdefault(cand, {'name': cand, 'aliases': set(), 'conf': 0.55})
            out['Field'][cand]['aliases'].add(m.group(0))
    fn = str(fm.get('field_name') or fm.get('field') or '').strip()
    if fn and valid_field(fn):
        c = canon_field(fn)
        out['Field'].setdefault(c, {'name': c, 'aliases': set(), 'conf': 0.9})
        out['Field'][c]['aliases'].add(fn)

    # ---- Formation ----
    for canon, aliases in _match_lexicon(text, FORMATION_LEXICON).items():
        if not valid_formation(canon):
            continue
        out['Formation'].setdefault(canon, {'name': canon, 'aliases': set(), 'conf': 0.7})
        out['Formation'][canon]['aliases'] |= aliases
    tf = str(fm.get('target_formation') or '').strip()
    if tf and valid_formation(tf):
        c = canon_formation(tf)
        out['Formation'].setdefault(c, {'name': c, 'aliases': set(), 'conf': 0.85})
        out['Formation'][c]['aliases'].add(tf)
    return out
