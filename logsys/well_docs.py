# -*- coding: utf-8 -*-
"""井文档独立模块：地质设计（GTO/DWOP/钻探程序/中文MD）+ masterlog 录井图。

用户要求（2026-11-01）：把"读地质设计"和"读 masterlog 录井图"单独做成模块，
放进 logInt，在解释或可视化时使用其数据，供以后调用或改进。

公共 API：
    read_design(well_dir)            -> dict: 井名/井型/设计井深/区域/目的层/解释井段/
                                             套管程序/地层顶/流体界面(GWC/OWC)/邻井试油/要点/来源
    read_masterlog(well_dir, ...)    -> dict: 岩性层 + 气测异常事件/井段（复用 logsys.masterlog）
    build_context(well_dir, info=None, out_dir=None) -> dict: 合并 info+design+masterlog，
                                              默认缓存到 <输出目录或井目录>/<井>_well_context.json
    load_context(out_dir, well)      -> dict: 读缓存（供报告/可视化调用）

设计原则：
- 只读原始资料，不改结论；所有字段带来源（文件/页/置信度）；
- 解析失败不阻断主流程（返回空字段 + 记录 note）；
- 缓存按源文件 mtime/size 失效。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

DESIGN_MD_KEYS = ('钻探程序', '地质设计', 'drillingprogram', 'drilling program', 'dwop')
DESIGN_PDF_KEYS = ('drilling program', 'dwop', '地质设计', 'gto',
                   'geological technical order', 'well prognosis', '地质设计')
MASTERLOG_KEYS = ('masterlog', 'master log', 'master_log', 'mud log', 'mudlog',
                  'mud_log', '录井', '地质录井')


def _find_files(well_dir, keys, suffixes, max_n=8):
    out = []
    wd = Path(str(well_dir))
    if not wd.is_dir():
        return out
    for p in sorted(wd.rglob('*')):
        if p.suffix.lower() not in suffixes or not p.is_file():
            continue
        low = p.name.lower()
        if any(k in low for k in keys):
            out.append(p)
            if len(out) >= max_n:
                break
    return out


def _norm_text(t):
    return (t.replace('″', '"').replace('“', '"').replace('”', '"')
             .replace('＇', "'").replace(' ', ' '))


def _read_text(path, max_pages=30, max_chars=260000):
    """读 MD/TXT/PDF/DOCX 文本（PDF 逐页截断；返回 (text, pages_note)）。"""
    p = str(path)
    low = p.lower()
    try:
        if low.endswith(('.md', '.txt', '.csv')):
            return Path(p).read_text(encoding='utf-8', errors='replace')[:max_chars], ''
        if low.endswith('.pdf'):
            import fitz
            doc = fitz.open(p)
            n = min(max_pages, doc.page_count)
            txt = '\n'.join(doc[i].get_text() for i in range(n))
            doc.close()
            return txt[:max_chars], 'pages 1-%d' % n
        if low.endswith('.docx'):
            import docx
            d = docx.Document(p)
            return '\n'.join(x.text for x in d.paragraphs)[:max_chars], ''
    except Exception:
        return '', ''
    return '', ''


def _num(s):
    try:
        return float(s)
    except Exception:
        return None


def _find_depths(text):
    return [float(x) for x in re.findall(r'\b(\d{3,5}(?:\.\d+)?)\s*(?:m|米|ft|英尺)\b', text)]


def _extract_location(text):
    """井位：经纬度/UTM/区块/气田/国家（多语言标注）。"""
    out = {}
    m = re.search(r'(?:Latitude|LAT\.?|纬度)\s*[:：]?\s*([0-9]{1,3}\s*[°度]\s*[0-9]{1,2}\s*[\'′]\s*[0-9.]{1,10}\s*[\"″]?\s*[NS]?)', text, re.I)
    if m:
        out['latitude'] = m.group(1).strip()
    m = re.search(r'(?:Longitude|LONG\.?|经度)\s*[:：]?\s*([0-9]{1,3}\s*[°度]\s*[0-9]{1,2}\s*[\'′]\s*[0-9.]{1,10}\s*[\"″]?\s*[EW]?)', text, re.I)
    if m:
        out['longitude'] = m.group(1).strip()
    m = re.search(r'UTM[^\n]{0,60}?NORTH[:：]?\s*([\d,.]{3,20})[^\n]{0,40}?EAST[:：]?\s*([\d,.]{3,20})', text, re.I)
    if m:
        out['utm_north'] = m.group(1); out['utm_east'] = m.group(2)
    m = re.search(r'(?:Block|区块|Licence|License)[^\n:：]{0,20}[:：]?\s*([^\n,，]{2,40})', text, re.I)
    if m:
        out['block'] = m.group(1).strip()
    return out


def _extract_purpose(text):
    """设计目的/目标（Objectives and Targets / 设计目的 / Purpose）：
    优先取正文 3.1 Objectives 后的项目符号条目（To ...），跳过目录页。"""
    # 先找正文中的 Objectives 小节（跳过目录页：其前 200 字不应是标题+页码列表）
    for m in re.finditer(r'(?:\d+\.\d+\s*)?Objectives?\b', text, re.I):
        _pre = text[max(0, m.start() - 120):m.start()]
        if re.search(r'(?:Page|\n\d+\s+\n)', _pre) or re.search(r'\n\d+\s*$', _pre):
            continue
        block = text[m.end():m.end() + 1500]
        items = re.findall(r'(?:^|\n|\s)(?:[▪•●\-\u2022]\s*)?'
                           r'((?:To|to|Explore|Evaluate|Appraise|Ascertain|Enhance|Determine|'
                           r'Re-evaluate|Assess|Test|设计|评价|查明|探索)[^\n]{10,200})', block)
        items = [re.sub(r'\s+', ' ', x).strip(' .;；') for x in items]
        if items:
            return '；'.join(items[:8])[:800]
        break
    best = None
    pats = [
        r'(?:Objectives?\s*(?:and|&)\s*Targets?|Design\s*Purpose|Purpose\s*of\s*(?:the\s*)?Well|'
        r'设计目的|钻探目的)',
        r'(?:Objectives?|目标)\b',
    ]
    for pat in pats:
        for m in re.finditer(pat, text, re.I):
            start = m.end()
            body = text[start:start + 1200]
            body = re.sub(r'\s+', ' ', body).strip()
            body = re.sub(r'^[:：\s-]+', '', body)
            # 去掉目录页（大量 "标题 页码"）
            body = re.sub(r'^(?:[A-Z][A-Za-z&/().\- ]{3,70}\s+\d{1,3}\s+){1,6}', '', body)
            body = re.sub(r'^(?:\d{1,3}\s+){1,6}', '', body)
            body = re.split(r'(?:Page\b|\n\d+\.\s|Geology\s+of\s+the)', body)[0].strip()
            if len(body) < 40:
                continue
            _letters = len(re.findall(r'[A-Za-z\u4e00-\u9fa5]', body))
            _score = _letters / max(len(body), 1)
            for kw in ('well', 'objective', 'evaluate', 'explor', 'gas', 'target',
                       '设计', '目的', '评价', '勘探'):
                if kw.lower() in body.lower():
                    _score += 0.2
            if best is None or _score > best[0]:
                best = (_score, body[:500])
    return best[1] if best else None


def _extract_regional_geology(text):
    """区域地质：地层/岩性/邻井油气显示/试油（多语言关键词行）。"""
    kws = ('Formation', 'Lithology', 'Sandstone', 'Shale', 'Limestone', 'Dolomite',
           'reservoir', 'offset well', 'adjacent well', 'neighbour', 'neighbor',
           'DST', 'test', 'gas show', 'oil show', 'GWC', 'OWC', '地层', '岩性',
           '邻井', '试油', '油气显示', '砂岩', '泥岩', '灰岩',
           'formation', 'géologie', 'puits voisin', 'test de production',
           'formação', 'poço vizinho', 'teste de produção')
    out = []
    for line in text.splitlines():
        s0 = line.strip()
        if not (6 <= len(s0) <= 240):
            continue
        if any(k.lower() in s0.lower() for k in kws):
            # 过滤目录页行（标题+页码）与章节标题
            if re.search(r'\s\d{1,3}$', s0) and len(s0) < 90:
                continue
            _heading = re.match(r'^[A-Za-z0-9/&().\- ]{4,90}$', s0) and not re.search(r'[.;:,，。：]', s0)
            if _heading or re.search(r'(?:Program|Completion|Analysis|Logging|Prognosis|Design)$', s0):
                continue
            out.append(s0)
        if len(out) >= 20:
            break
    return out


def _detect_language(text):
    ch = len(re.findall(r'[\u4e00-\u9fa5]', text))
    fr = len(re.findall(r'\b(?:puits|objectif|géologie|forage|sondage|réservoir)\b', text, re.I))
    pt = len(re.findall(r'\b(?:poço|objetivo|geologia|formação|perfuração)\b', text, re.I))
    if ch > 50:
        return 'zh'
    if fr > pt and fr > 3:
        return 'fr'
    if pt > fr and pt > 3:
        return 'pt'
    return 'en'


def _extract_interval(text):
    """从地质设计文本提取目标/解释井段（8.5in井眼、尾管、完井段、解释井段）。"""
    pats = [
        r'(?:解释井段|解释层段|评价井段|目标井段)\s*[:：]?\s*(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
        r'8\s*[½.5]?\s*["″]?\s*(?:井眼|hole section|section|open\s*hole)[^\n]{0,120}?'
        r'(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)\s*m',
        r'(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)\s*m[^\n]{0,80}?'
        r'8\s*[½.5]?\s*["″]?\s*(?:井眼|hole|section)',
        r'7\s*["″]?\s*(?:liner|尾管|套管)[^\n]{0,100}?(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
        r'(?:Open\s*Hole|Completion\s*Interval|Perforation)[^\n]{0,80}?'
        r'(\d{3,5}(?:\.\d+)?)\s*[-–~to]\s*(\d{3,5}(?:\.\d+)?)',
    ]
    pats += [
        r'8\s*[½.]?\s*5?\s*["″]?\s*7?\s*["″]?\s*(?:Liner|liner|尾管)\s{0,60}?'
        r'(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
        r'(?:Liner|liner|尾管)\s{0,60}?(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
    ]
    for pat in pats:
        m = re.search(pat, text, flags=re.I)
        if m:
            a, b = _num(m.group(1)), _num(m.group(2))
            if a is not None and b is not None and 0 < a < b < 9000:
                return {'top': a, 'bottom': b, 'text': m.group(0)[:160]}
    return None


def _extract_contacts(text):
    out = []
    for m in re.finditer(r'(GWC|OWC|GOC|ODT|WUT|气水界面|油水界面|气油界面|油水接触|气水接触)'
                         r'[^\d\n]{0,30}(\d{3,5}(?:\.\d+)?)\s*(m|米|ft|英尺|TVDSS|MDSS|TVD)?',
                         text, flags=re.I):
        out.append({'type': m.group(1).upper(), 'depth': _num(m.group(2)),
                    'unit': (m.group(3) or 'm'), 'text': m.group(0)[:80]})
    # 去重
    seen = set(); uniq = []
    for c in out:
        k = (c['type'], c['depth'])
        if k in seen:
            continue
        seen.add(k); uniq.append(c)
    return uniq[:8]


def _extract_tops(text):
    """地层顶（英文 Formation 行 / 表格 Top X : depth / 中文 组顶）。"""
    out = []
    pats = [
        r'([A-Z][A-Za-z]{2,20}(?:\s+[A-Z][A-Za-z]{2,20}){0,3}\s+(?:Formation|Fm\.?|Group))\s*'
        r'[:：]?\s*(\d{3,5}(?:\.\d+)?)\s*(?:m|TVDSS|MD)',
        r'(?:Top|TOP)\s+([A-Z][A-Za-z0-9 \-]{2,30})\s*[:：]\s*(\d{3,5}(?:\.\d+)?)\s*(?:m|TVDSS|MD)',
        r'([\u4e00-\u9fa5]{2,10}(?:组|段|层))\s*[:：]?\s*(?:顶|顶界)?\s*(\d{3,5}(?:\.\d+)?)\s*m',
    ]
    pats += [
        r'8\s*[½.]?\s*5?\s*["″]?\s*7?\s*["″]?\s*(?:Liner|liner|尾管)\s{0,60}?'
        r'(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
        r'(?:Liner|liner|尾管)\s{0,60}?(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
    ]
    for pat in pats:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            d = _num(m.group(2))
            # 过滤纯数字/把井段当"地层"的伪行
            if not re.search(r'[A-Za-z\u4e00-\u9fa5]', name) or name.lower() in ('top', 'formation'):
                continue
            if m.group(0).strip().startswith(('8', '7', '6', '5')) and 'Liner' in m.group(0):
                continue
            if d and 0 < d < 9000:
                out.append({'formation': name, 'depth': d, 'text': m.group(0)[:80]})
    seen = set(); uniq = []
    for x in out:
        k = (x['formation'].lower(), x['depth'])
        if k in seen:
            continue
        seen.add(k); uniq.append(x)
    return uniq[:30]


def _extract_casing(text):
    """井身结构/套管程序（英寸尺寸 + 深度）。"""
    out = []
    for m in re.finditer(r'(\d{1,2}(?:[⅜⅝¼½¾]|\.\d+|\s*[½¼¾])?)\s*["″]?\s*'
                         r'(?:casing|liner|套管|尾管)[^\n]{0,60}?(\d{3,5}(?:\.\d+)?)\s*(?:m|ft)?',
                         text, flags=re.I):
        out.append({'size_in': m.group(1), 'depth': _num(m.group(2)),
                    'text': m.group(0)[:100]})
    # 8½" / 7" Liner 顶底
    for m in re.finditer(r'(\d{1,2}(?:[½¼¾]|\.\d+)?)\s*["″]?\s*'
                         r'(?:\d{1,2}\s*["″]\s*)?(?:Liner|liner|尾管)'
                         r'\s{0,40}?(\d{3,5}(?:\.\d+)?)\s*[-–~至]\s*(\d{3,5}(?:\.\d+)?)',
                         text):
        out.append({'size_in': m.group(1), 'depth': _num(m.group(2)),
                    'bottom': _num(m.group(3)), 'text': m.group(0)[:100]})
    # 中文井身结构表: 尺寸 x 深度 行
    for m in re.finditer(r'(\d{1,2}(?:[⅜⅝¼½¾]|\.\d+))\s*["″]\s*[×x]\s*(\d{3,5}(?:\.\d+)?)\s*m',
                         text, flags=re.I):
        out.append({'size_in': m.group(1), 'depth': _num(m.group(2)),
                    'text': m.group(0)[:80]})
    seen = set(); uniq = []
    for x in out:
        k = (x['size_in'], x['depth'])
        if k in seen:
            continue
        seen.add(k); uniq.append(x)
    return uniq[:20]


def _extract_formation_names(text):
    """从地质设计"预测地层/Prognosed Stratigraphy"表提取地层序列（可有名无深度）。"""
    known = ['DupiTila', 'Dupitila', 'Tipam', 'BokaBil', 'Bokabil', 'Bhuban',
             'Jenam', 'Surma', 'Kopili', 'Barail', 'Titas', 'Girujan', 'Chinji']
    found = []
    low = text.lower()
    for name in known:
        for m in re.finditer(r'\b' + re.escape(name) + r'[A-Za-z]*\b', text, re.I):
            # 取上下文 40 字内的原始写法
            ctx = text[max(0, m.start() - 10):m.start() + 60].replace('\n', ' ')
            found.append({'name': m.group(0), 'context': ctx[:80]})
            break
    # 去重保序
    seen = set(); out = []
    for f in found:
        k = f['name'].lower()
        if k in seen:
            continue
        seen.add(k); out.append(f)
    return out[:20]


def _extract_offsets(text):
    """邻井试油/测试结论（DST / 试油 / 产能）片段。"""
    out = []
    for line in text.splitlines():
        if re.search(r'(DST|试油|测试|产能|m3/d|m³/d|MMscf|气产量|油产量)', line, re.I):
            s = line.strip()
            if 6 <= len(s) <= 240:
                out.append(s)
        if len(out) >= 30:
            break
    return out


def _extract_notes(text):
    keys = ('气田', '油藏', '凝析', '干气', 'GWC', 'OWC', '气水', '油水', '煤层', '目的层',
            'gas field', 'oil field', 'reservoir', 'target')
    out = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) < 4 or len(s) > 200:
            continue
        if any(k.lower() in s.lower() for k in keys):
            out.append(s)
        if len(out) >= 25:
            break
    return out


def read_masterlog_header(well_dir, out_dir=None, well_name=None) -> dict:
    """读 masterlog 图头通用字段（多国格式基本一致）：
    公司/作业者、服务商、开钻/完钻日期、完钻井深、井型、坐标、泥浆、
    井身结构（钻头/套管+鞋深）、岩性图例、油气显示图例。"""
    cands = _masterlog_candidates(well_dir)
    if not cands:
        return {'ok': False, 'error': '未找到 masterlog PDF'}
    pdf = cands[0]
    txt, _ = _read_text(pdf, max_pages=2, max_chars=200000)
    if not txt:
        return {'ok': False, 'error': 'masterlog 无可读文本'}
    head = {'ok': True, 'source_pdf': str(pdf), 'fields': {}, 'mud': [],
            'sizes': [], 'lithology_legend': [], 'show_legend': [], 'language': _detect_language(txt)}
    f = head['fields']
    def grab(pat, key):
        m = re.search(pat, txt, re.I)
        if m and key not in f:
            f[key] = m.group(1).strip()
    grab(r'(?:Company\s*Name|Operator|作业者|公司)\s*[:：]\s*([^\n]{2,60})', 'company')
    grab(r'(?:WELL\s*NAME|Well\s*Name|井名)\s*[:：]?\s*([^\n]{2,60})', 'well')
    grab(r'(?:Country|国家)\s*[:：]\s*([^\n]{2,40})', 'country')
    grab(r'(?:WELL\s*TYPE|Well\s*Type|井型)\s*[:：]\s*([^\n]{2,40})', 'well_type')
    grab(r'(?:Spud(?:-in)?\s*Date|SPUD\s*DATE|开钻日期)\s*[:：]?\s*([^\n]{6,30})', 'spud_date')
    grab(r'(?:Drilling\s*End\s*Date|END\s*OF\s*WELL|完钻日期)\s*[:：]?\s*([^\n]{6,30})', 'end_date')
    grab(r'(?:Drilling\s*Contractor|RIG\s*OPERATOR|钻井承包商|钻机)\s*[:：]?\s*([^\n]{2,60})', 'contractor')
    grab(r'(?:RIG\s*NAME|Rig\s*Name)\s*[:：]\s*([^\n]{2,40})', 'rig')
    grab(r'(?:FINAL\s*DEPTH|Final\s*Depth|完钻井深)\s*[:：]?\s*([0-9.,]+\s*(?:m|ft))', 'final_depth')
    grab(r'(?:MD\s*Depth|Depth)\s*[:：]\s*([0-9.,]+\s*m)', 'md_depth')
    grab(r'(?:TVD\s*Depth)\s*[:：]\s*([0-9.,]+\s*m)', 'tvd_depth')
    grab(r'(?:FIELD|Field|气田|油田)\s*[:：]\s*([^\n]{2,50})', 'field')
    grab(r'(?:SEDIMENTARY\s*BASIN|Basin|盆地)\s*[:：]\s*([^\n]{2,50})', 'basin')
    grab(r'(?:RKB[- ]GL|RTE|KB)\s*[:：]\s*([0-9.,]+\s*m)', 'elevation')
    grab(r'(?:Drilling\s*Contractor)\s*[:：]?\s*([^\n]{2,60})', 'drilling_contractor')
    # 服务商
    svc = []
    for k in ('LWD', 'WIRELINE LOG', 'MUD LOGGING', 'MWD', 'Cementing', '测井', '录井'):
        for m in re.finditer(k + r'\s*[:：]\s*([^\n]{2,40})', txt, re.I):
            svc.append('%s: %s' % (k, m.group(1).strip()))
    head['services'] = svc[:10]
    # 坐标
    loc = _extract_location(txt)
    if loc:
        head['location'] = loc
    # 泥浆井段/类型
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)\s*m\s*:\s*([A-Za-z0-9가-힣 \-]{2,40})', txt):
        head['mud'].append({'top': float(m.group(1)), 'bottom': float(m.group(2)),
                            'type': m.group(3).strip()})
    # 井身结构（尺寸 to 深度 / SECTION / CASING SHOE / LINER）
    for m in re.finditer(r'(\d{1,2}(?:\s+\d+/\d+)?|\d+\.\d+)\s*["”″]\s*(?:to|至)\s*([0-9.]+)\s*m', txt):
        head['sizes'].append({'size_in': m.group(1).strip(), 'depth': float(m.group(2))})
    for m in re.finditer(r'(SECTION|CASING\s*SHOE|LINER)\s*[:：]?\s*'
                         r'(\d{1,2}(?:\s+\d+/\d+)?|\d+\.\d+)\s*["”″]\s*[:：]?\s*([0-9.]+)\s*m',
                         txt, re.I):
        head['sizes'].append({'type': m.group(1).upper(), 'size_in': m.group(2).strip(),
                              'depth': float(m.group(3))})
    # 岩性图例
    for w in ('Sandstone', 'Shale', 'Siltstone', 'Claystone', 'Limestone', 'Dolomite',
              'Anhydrite', 'Halite', 'Coal', 'Basalt', 'Alluvium', '砂岩', '泥岩', '灰岩',
              '白云岩', '膏岩', '盐岩', '煤'):
        if re.search(re.escape(w), txt, re.I):
            head['lithology_legend'].append(w)
    for w in ('Gas Show', 'Oil Show', 'Fluorescence', '油气显示', '荧光', '气测异常'):
        if re.search(re.escape(w), txt, re.I):
            head['show_legend'].append(w)
    if well_name and not f.get('well'):
        f['well'] = str(well_name)
    # 置信度
    _keys = ('company', 'well', 'spud_date', 'end_date', 'final_depth', 'mud', 'sizes')
    head['confidence'] = round(sum(1 for k in _keys if head.get('fields', {}).get(k)) / 6.0, 3)
    try:
        if out_dir:
            json.dump(head, open(Path(out_dir) / 'masterlog_header.json', 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
    except Exception:
        pass
    return head


def read_client_format(well_dir, repo_dir=None) -> dict:
    """读甲方 quicklook 格式与图例（quicklook_config.json / templates/qlpt.json 等）。"""
    cands = []
    try:
        for p in Path(str(well_dir)).rglob('*.json'):
            low = p.name.lower()
            if any(k in low for k in ('quicklook', 'qlpt', 'format', 'layout')):
                cands.append(p)
    except Exception:
        pass
    if repo_dir is None:
        repo_dir = Path(__file__).resolve().parents[1]
    for p in (Path(repo_dir) / 'quicklook_config.json', Path(repo_dir) / 'templates' / 'qlpt.json'):
        if p.exists():
            cands.append(p)
    out = {'ok': False, 'source': None, 'format_name': None, 'legend_items': [],
           'legend_title': None, 'header_fixed': {}, 'header_fields': [],
           'borehole_record': [], 'casing_record': [], 'title_template': None}
    for p in cands:
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        items = d.get('legend_items') or (d.get('legend') or {}).get('items') or []
        if not items and not d.get('header_fields') and not d.get('title_template'):
            continue
        out.update({'ok': True, 'source': str(p),
                    'format_name': d.get('format_name') or (d.get('meta') or {}).get('format'),
                    'legend_items': items, 'legend_title': d.get('legend_title') or (d.get('legend') or {}).get('title'),
                    'header_fixed': d.get('header_fixed') or (d.get('header') or {}).get('fixed') or {},
                    'header_fields': d.get('header_fields') or (d.get('header') or {}).get('fields_v') or [],
                    'borehole_record': d.get('borehole_record') or (d.get('header') or {}).get('borehole_record') or [],
                    'casing_record': d.get('casing_record') or (d.get('header') or {}).get('casing_record') or [],
                    'title_template': d.get('title_template') or (d.get('title') or {}).get('template')})
        out['legend_labels'] = [str(x.get('label') or x.get('name') or '')
                                for x in out['legend_items'] if isinstance(x, dict)][:20]
        break
    return out


def read_design(well_dir) -> dict:
    """读取地质设计（MD/PDF/DOCX）→ 结构化字段 + 来源。"""
    mds = _find_files(well_dir, DESIGN_MD_KEYS, ('.md', '.txt'))
    pdfs = _find_files(well_dir, DESIGN_PDF_KEYS, ('.pdf',))
    docs = _find_files(well_dir, DESIGN_PDF_KEYS, ('.docx',))
    res = {'sources': [], 'well': None, 'field': None, 'well_type': None,
           'designed_td_m': None, 'structure': None, 'target_formation': None,
           'interval': None, 'contacts': [], 'formation_tops': [], 'casing': [],
           'offset_tests': [], 'notes': [], 'country': None,
           'confidence': 0.0, 'notes_parse': []}
    files = [(p, 'md') for p in mds[:3]] + [(p, 'pdf') for p in pdfs[:3]] + \
            [(p, 'docx') for p in docs[:2]]
    _texts = []
    for p, kind in files:
        txt, note = _read_text(p)
        if not txt:
            continue
        _texts.append(txt)
        res['sources'].append({'file': p.name, 'path': str(p), 'type': kind,
                               'note': note,
                               'size': p.stat().st_size if p.exists() else None})
    if not _texts:
        res['notes_parse'].append('未找到地质设计文件')
        return res
    text = _norm_text('\n'.join(_texts))
    # 井名/井型/设计井深/构造/区域
    m = re.search(r'\b(?:well|井)\s*[:：]?\s*([A-Z][A-Za-z0-9\-]{2,20}(?:[\- ]\d+)?)', text)
    if m:
        res['well'] = m.group(1).strip()
    m = re.search(r'(?:Type\s*of\s*well|井型|井别)\s*[:：]?\s*'
                  r'(Vertical|Directional|Deviated|Horizontal|Exploration|Appraisal|Development)',
                  text, re.I)
    if m:
        res['well_type'] = m.group(1).strip()
    elif re.search(r'\bExploration\s+Well\b', text, re.I):
        res['well_type'] = 'Exploration Well'
    elif re.search(r'\bAppraisal\s+Well\b', text, re.I):
        res['well_type'] = 'Appraisal Well'
    m = re.search(r'(?:Target\s*Depth|Total\s*Depth|设计井深|完钻深度|Proposed\s*TD)'
                  r'[^\d\n]{0,25}(\d{3,5}(?:\.\d+)?)\s*(m|MD|ft)?', text, re.I)
    if m:
        res['designed_td_m'] = _num(m.group(1))
    m = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+(?:Gas|Oil)\s+Field(?!s))', text)
    if m:
        res['field'] = m.group(1).strip()
    m = re.search(r'(构造[位形置][^\n:：]{0,20}[:：]\s*[^\n|（*。]{2,40})', text)
    if m:
        res['structure'] = m.group(1).strip()
    m = re.search(r'(?:Target|Objective)\s*Formation[s]?[^\n]{0,10}[:：]?\s*([A-Z][A-Za-z0-9 \-]{2,40})',
                  text, re.I)
    if m:
        res['target_formation'] = m.group(1).strip()
    if res['well_type'] is None:
        m = re.search(r'\b(Exploration|Appraisal|Development)\s+Well\b', text, re.I)
        if m:
            res['well_type'] = m.group(0)
    res['interval'] = _extract_interval(text)
    res['contacts'] = _extract_contacts(text)
    res['formation_tops'] = _extract_tops(text)
    res['formation_names'] = _extract_formation_names(text)
    res['location'] = _extract_location(text)
    res['purpose'] = _extract_purpose(text)
    res['regional_geology'] = _extract_regional_geology(text)
    res['language'] = _detect_language(text)
    res['casing'] = _extract_casing(text)
    res['offset_tests'] = _extract_offsets(text)
    res['notes'] = _extract_notes(text)
    # 区域/国家（路径或文本）
    for c in ('Bangladesh', 'Niger', 'Chad', 'Brasil', 'Brazil', 'Indonesia'):
        if c.lower() in text.lower() or c.lower() in str(well_dir).lower():
            res['country'] = c
            break
    # 置信度：关键字段命中比例
    _keys = ('well', 'field', 'designed_td_m', 'interval', 'formation_tops', 'contacts')
    res['confidence'] = round(sum(1 for k in _keys if res.get(k)) / len(_keys), 3)
    return res


def _masterlog_candidates(well_dir):
    out = _find_files(well_dir, MASTERLOG_KEYS, ('.pdf',), max_n=12)
    # 排除地质设计 PDF（GTO 等）
    out = [p for p in out if not any(k in p.name.lower() for k in
                                     ('gto', 'geological technical', 'drilling program', 'dwop'))]
    return out


def read_masterlog(well_dir, out_dir=None, depth_range=None, cache=True,
                   well_name=None) -> dict:
    """读取 masterlog（录井图 PDF）→ 岩性层 + 气测异常井段；带缓存。"""
    try:
        from .masterlog import extract_masterlog
    except Exception as e:
        return {'ok': False, 'error': 'masterlog 模块不可用: %s' % e}
    cands = _masterlog_candidates(well_dir)
    if not cands:
        return {'ok': False, 'error': '未找到 masterlog PDF'}
    pdf = cands[0]
    od = Path(out_dir) if out_dir else Path(well_dir)
    try:
        od.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # 井名前缀：优先 info.json 的井名，否则 PDF 名
    well = well_name
    try:
        for f in Path(well_dir).rglob('*info.json'):
            d0 = json.load(open(f, encoding='utf-8'))
            well = d0.get('井信息', {}).get('井名') or d0.get('well') or well
            if well:
                break
    except Exception:
        pass
    if not well:
        well = os.path.splitext(pdf.name)[0].split('_')[0].split(' ')[0]
    # 深度范围：入参 > 文件名（0-4240m）> 设计井深
    rng = depth_range
    if rng is None:
        m = re.search(r'(\d{3,5})\s*[-–~]\s*(\d{3,5})\s*m', pdf.name)
        if m:
            rng = (float(m.group(1)), float(m.group(2)))
    cache_json = od / f'{well}_masterlog_extract.json'
    if cache and cache_json.exists() and not _stale(cache_json, pdf):
        try:
            r = json.load(open(cache_json, encoding='utf-8'))
            r['cached'] = True
            return r
        except Exception:
            pass
    r = extract_masterlog(str(pdf),
                          lith_out=str(od / f'{well}_masterlog_lith.csv'),
                          gas_out=str(od / f'{well}_masterlog_gas.csv'),
                          depth_range=rng, depth_max_hint=(rng[1] if rng else None))
    r['ok'] = True
    r['cached'] = False
    r['source_pdf'] = str(pdf)
    try:
        # extract_masterlog 已写 JSON 到 PDF 目录；统一复制到输出目录
        import shutil
        if r.get('json') and Path(r['json']).exists():
            shutil.copyfile(r['json'], cache_json)
            r['json_out'] = str(cache_json)
    except Exception:
        pass
    return r


def _stale(cache_json, pdf):
    try:
        return cache_json.stat().st_mtime < Path(pdf).stat().st_mtime
    except Exception:
        return False


def _find_info(well_dir):
    info = {}
    try:
        for f in sorted(Path(well_dir).rglob('*info.json')):
            try:
                d = json.load(open(f, encoding='utf-8'))
            except Exception:
                continue
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(info.get(k), dict):
                    info[k].update(v)
                else:
                    info[k] = v
    except Exception:
        pass
    return info


def build_context(well_dir, info=None, out_dir=None, use_cache=True,
                  depth_range=None, well_name=None) -> dict:
    """合并 info + 地质设计 + masterlog，写 <井>_well_context.json 缓存。"""
    wd = Path(str(well_dir))
    inf = info or _find_info(wd)
    well = well_name
    try:
        well = well or inf.get('井信息', {}).get('井名') or inf.get('well')
    except Exception:
        well = None
    if not well:
        # 从路径取
        well = wd.name.replace(' ', '_')
    od = Path(out_dir) if out_dir else wd
    cache = od / f'{well}_well_context.json'
    ctx = {'well': well, 'well_dir': str(wd), 'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
           'info': inf, 'design': {}, 'masterlog': {}, 'sources': [], 'cache': str(cache)}
    if use_cache and cache.exists():
        try:
            old = json.load(open(cache, encoding='utf-8'))
            # 只要设计/masterlog 源文件未变即可复用
            srcs = [s.get('path') for s in old.get('sources', []) if s.get('path')]
            if srcs and all(Path(s).exists() for s in srcs):
                old['cached'] = True
                return old
        except Exception:
            pass
    try:
        ctx['design'] = read_design(wd)
    except Exception as e:
        ctx['design'] = {'error': str(e)}
    # masterlog 深度范围：设计井深/井段
    dr = depth_range
    if dr is None:
        des = ctx['design'] or {}
        if des.get('interval'):
            dr = (des['interval']['top'], des['interval']['bottom'])
        elif des.get('designed_td_m'):
            dr = (0.0, float(des['designed_td_m']) + 50.0)
    try:
        ctx['masterlog'] = read_masterlog(wd, out_dir=od, depth_range=dr, well_name=well)
    except Exception as e:
        ctx['masterlog'] = {'ok': False, 'error': str(e)}
    try:
        ctx['masterlog_header'] = read_masterlog_header(wd, out_dir=od, well_name=well)
    except Exception as e:
        ctx['masterlog_header'] = {'ok': False, 'error': str(e)}
    try:
        ctx['client_format'] = read_client_format(wd)
    except Exception as e:
        ctx['client_format'] = {'ok': False, 'error': str(e)}
    for s in (ctx['design'].get('sources') or []):
        ctx['sources'].append(s)
    if ctx['masterlog'].get('source_pdf'):
        ctx['sources'].append({'file': Path(ctx['masterlog']['source_pdf']).name,
                               'path': ctx['masterlog']['source_pdf'], 'type': 'masterlog'})
    if (ctx.get('client_format') or {}).get('source'):
        ctx['sources'].append({'file': Path(ctx['client_format']['source']).name,
                               'path': ctx['client_format']['source'], 'type': 'quicklook_format'})
    ctx['cached'] = False
    try:
        json.dump(ctx, open(cache, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception:
        pass
    return ctx


def load_context(out_dir, well):
    p = Path(str(out_dir)) / f'{well}_well_context.json'
    if p.exists():
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            return {}
    return {}


def apply_design_interval(design: dict, info: dict):
    """解释井段优先级：info.json 显式 > 地质设计目标井段。返回 (interval, source)。"""
    itv = (info or {}).get('解释井段')
    if isinstance(itv, dict) and (itv.get('自动') or itv.get('顶深') is not None):
        return itv, 'info.json'
    if isinstance(itv, (list, tuple)) and len(itv) == 2:
        return {'top': float(itv[0]), 'bottom': float(itv[1])}, 'info.json'
    if design and design.get('interval'):
        d = design['interval']
        return {'top': float(d['top']), 'bottom': float(d['bottom']),
                'unit': 'm', 'note': '地质设计目标井段: ' + (d.get('text') or '')}, 'design'
    return None, None


def apply_contacts(design: dict, md_col, unit='m'):
    """返回流体界面约束列表（仅数值型，供解释后处理）。"""
    out = []
    if not design:
        return out
    for c in design.get('contacts') or []:
        d = c.get('depth')
        if d is None:
            continue
        out.append({'type': c.get('type'), 'depth': float(d),
                    'unit': c.get('unit') or unit})
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='井文档（地质设计+masterlog）读取')
    ap.add_argument('--well-dir', required=True)
    ap.add_argument('--out-dir', default=None)
    ap.add_argument('--no-cache', action='store_true')
    args = ap.parse_args(argv)
    ctx = build_context(args.well_dir, out_dir=args.out_dir, use_cache=not args.no_cache)
    print(json.dumps({k: ctx.get(k) for k in ('well', 'sources', 'design', 'masterlog')},
                     ensure_ascii=False, indent=2, default=str)[:6000])
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
