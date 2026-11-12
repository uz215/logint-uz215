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


def read_masterlog_header(well_dir, out_dir=None, well_name=None, pdf_path=None) -> dict:
    """读 masterlog 图头通用字段（多国格式基本一致）：
    公司/作业者、服务商、开钻/完钻日期、完钻井深、井型、坐标、泥浆、
    井身结构（钻头/套管+鞋深）、岩性图例、油气显示图例。"""
    cands = [Path(str(pdf_path))] if pdf_path else _masterlog_candidates(well_dir)
    if not cands:
        return {'ok': False, 'skipped': True, 'error': '未找到 masterlog PDF'}
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


def find_design_files(well_dir):
    """查找地质设计文件：中文MD/地质设计 + 英文 Drilling Program/DWOP/GTO PDF。"""
    mds = _find_files(well_dir, DESIGN_MD_KEYS, ('.md', '.txt'))
    pdfs = _find_files(well_dir, DESIGN_PDF_KEYS, ('.pdf',))
    docxs = _find_files(well_dir, DESIGN_PDF_KEYS, ('.docx',))
    return mds, pdfs, docxs


def read_md_knowledge(md_files, limit_chars=6000):
    """从井目录 .md 知识文件提取结构化知识（地质认识/分层/岩性/试油/气测）。"""
    parts = []
    for md in list(md_files)[:12]:
        try:
            text = Path(str(md)).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            try:
                text = Path(str(md)).read_text(encoding='gbk', errors='ignore')
            except Exception:
                continue
        text = text.strip()
        if not text:
            continue
        body = text
        if text.startswith('---'):
            _end = text.find('\n---', 4)
            if _end > 0:
                body = text[_end + 4:].strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        title = lines[0] if lines else Path(str(md)).stem
        excerpt = '\n'.join(lines[1:])[:limit_chars]
        parts.append(f"### 来源: {Path(str(md)).name}\n**{title}**\n{excerpt[:limit_chars]}")
    return '\n\n'.join(parts)


def extract_pdf_knowledge(pdf_files, max_pages=3, limit_chars=4000):
    """提取井目录 PDF（mud log/DWOP/钻井程序等）关键文本。"""
    parts = []
    for pdf in list(pdf_files)[:6]:
        try:
            import fitz
            doc = fitz.open(str(pdf))
            txt_parts = [doc[i].get_text() for i in range(min(max_pages, doc.page_count))]
            doc.close()
            txt = '\n'.join(txt_parts).strip()
            if txt:
                parts.append(f"### 来源: {Path(str(pdf)).name}\n{txt[:limit_chars]}")
        except Exception:
            continue
    return '\n\n'.join(parts)


def find_masterlog_file(well_dir):
    """井目录查找 masterlog/录井图 PDF；找不到返回 None（调用方跳过）。"""
    cands = _masterlog_candidates(well_dir)
    return cands[0] if cands else None


def read_masterlog_file(pdf_path, out_dir=None, depth_range=None, well_name=None) -> dict:
    """按 PDF 路径读取 masterlog（供 truth_lith 等调用；解析实现仍在 masterlog.py）。"""
    from .masterlog import extract_masterlog
    od = Path(out_dir) if out_dir else Path(str(pdf_path)).parent
    try:
        od.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    wn = well_name or Path(str(pdf_path)).stem.split('_')[0].split(' ')[0]
    r = extract_masterlog(str(pdf_path),
                          lith_out=str(od / f'{wn}_masterlog_lith.csv'),
                          gas_out=str(od / f'{wn}_masterlog_gas.csv'),
                          depth_range=depth_range,
                          depth_max_hint=(depth_range[1] if depth_range else None))
    r['ok'] = True
    return r


_CASING_CACHE = {}


def casing_shoes_from_masterlog(pdf_path, md_max=None) -> tuple:
    """从 masterlog 井身结构读取套管/尾管鞋深（唯一实现）。返回 (鞋深, 尺寸, [(深, 尺寸)...])。"""
    import re as _re
    p = str(pdf_path)
    try:
        st = os.stat(p)
        ck = (p, int(st.st_size), round(float(st.st_mtime), 3), None if md_max is None else round(float(md_max), 1))
    except Exception:
        ck = (p, 0, 0, md_max)
    if ck in _CASING_CACHE:
        return _CASING_CACHE[ck]
    size_pat = _re.compile(r'^(?:(\d{1,2})[-\s](\d)/(\d)|(\d{1,2}(?:\.\d+)?))["”]?:?$')
    frac_pat = _re.compile(r'^(\d)/(\d)["”]?:?$')
    num_pat = _re.compile(r'^(\d{2,5}(?:\.\d+)?)(?:\s*(?:m|ft))?$', _re.I)
    out = []
    try:
        import fitz
        doc = fitz.open(p)
        pages = []
        for pi in range(min(3, doc.page_count)):
            page = doc[pi]
            pages.append([(w[1], w[0], w[4]) for w in page.get_text('words')])
        doc.close()
        for toks in pages:
            if not toks:
                continue
            toks = sorted(toks)
            rows = []
            for y, x, t in toks:
                if rows and abs(y - rows[-1][0][0]) <= 9:
                    rows[-1].append((y, x, t))
                else:
                    rows.append([(y, x, t)])
            for row in rows:
                row.sort(key=lambda z: z[1])
                labels = [t for _y, _x, t in row]
                rowtext = ' '.join(labels).upper()
                if not _re.search(r'\b(CASING|LINER|CSG)\b', rowtext):
                    continue
                i = 0
                while i < len(labels):
                    m = size_pat.match(labels[i].strip())
                    if m:
                        if m.group(1):
                            size_txt = '%s-%s/%s' % (m.group(1), m.group(2), m.group(3))
                        else:
                            size_txt = m.group(4)
                            if i + 1 < len(labels):
                                fm = frac_pat.match(labels[i + 1].strip())
                                if fm:
                                    size_txt = '%s-%s/%s' % (size_txt, fm.group(1), fm.group(2))
                                    i += 1
                        for j in range(i + 1, len(labels)):
                            nm = num_pat.match(labels[j].strip())
                            if nm:
                                out.append((float(nm.group(1)), size_txt))
                                break
                    i += 1
    except Exception:
        pass

    def _size_inch(txt):
        m = _re.match(r'^(\d+)-(\d+)/(\d+)$', str(txt).strip())
        if m:
            return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
        try:
            return float(txt)
        except Exception:
            return float('nan')
    clean = []
    for d0, s0 in out:
        sv = _size_inch(s0)
        if 4.0 <= sv <= 36.0 and d0 > 0 and (md_max is None or d0 <= float(md_max) + 1):
            clean.append((d0, s0))
    if len(clean) < 2:
        clean = []
    clean.sort()
    res = (clean[-1][0], clean[-1][1], clean) if clean else (None, None, [])
    _CASING_CACHE[ck] = res
    return res


def _normalize_format(d: dict, source: str) -> dict:
    items = d.get('legend_items') or (d.get('legend') or {}).get('items') or []
    return {'ok': True, 'source': source,
            'format_name': d.get('format_name') or (d.get('meta') or {}).get('format'),
            'legend_items': items,
            'legend_title': d.get('legend_title') or (d.get('legend') or {}).get('title'),
            'header_fixed': d.get('header_fixed') or (d.get('header') or {}).get('fixed') or {},
            'header_fields': d.get('header_fields') or (d.get('header') or {}).get('fields_v') or [],
            'borehole_record': d.get('borehole_record') or (d.get('header') or {}).get('borehole_record') or [],
            'casing_record': d.get('casing_record') or (d.get('header') or {}).get('casing_record') or [],
            'title_template': d.get('title_template') or (d.get('title') or {}).get('template'),
            'legend_labels': [str(x.get('label') or x.get('name') or '')
                              for x in items if isinstance(x, dict)][:20]}


def _scan_to_quicklook_config(res: dict) -> dict:
    """qlscan 扫描结果 → quicklook_config（图例/比例尺/免责声明）。"""
    import re as _re
    cfg = {'format_name': 'quick look (OCR 扫描样本)', 'legend_items': []}
    colors = {'oil': '#ffd400', 'gas': '#ff0000', 'water': '#00a2e8',
              'shale': '#7f7f7f', 'sand': '#ffedb0', 'sandstone': '#ffedb0',
              'limestone': '#00b050', 'coal': '#000000', 'tight': '#a5a5a5',
              'condensate': '#ff7f27', 'pay': '#ffff00', 'dolomite': '#00b0f0'}
    for pg in res.get('scanned', []):
        if pg.get('disclaimer'):
            cfg['disclaimer'] = pg['disclaimer']
        if pg.get('legend_title'):
            cfg['legend_title'] = pg['legend_title']
        for it in pg.get('legend_items', []):
            lbl = (it.get('label') or '').strip()
            if not lbl:
                continue
            color = '#bdbdbd'
            for k, c in colors.items():
                if k in lbl.lower():
                    color = c
                    break
            cfg['legend_items'].append({'label': lbl, 'color': color})
        for b in pg.get('big_text', []):
            m = _re.search(r'1\s*:\s*(\d{2,4})', b.get('text', ''))
            if m:
                cfg['scale'] = '1:%s' % m.group(1)
    return cfg


def read_client_format(well_dir=None, config_file=None) -> dict:
    """甲方 quicklook 出图格式/图例读取（唯一入口）。

    规则（用户定案 2026-11-01）：
    - 显式选择 config_file：JSON 直接读；PDF/图片用 qlscan 扫描；
    - 未选择：在井目录查找 quicklook_config.json / *_qlpt.json；
    - 都没有：返回 {'ok': False, 'skipped': True}（调用方跳过，不弹窗、不报错）。
    """
    import json as _json
    if config_file:
        p = Path(str(config_file))
        if not p.exists():
            return {'ok': False, 'skipped': True, 'error': '格式文件不存在: %s' % p}
        if p.suffix.lower() == '.json':
            try:
                return _normalize_format(_json.load(open(p, encoding='utf-8')), str(p))
            except Exception as e:
                return {'ok': False, 'skipped': True, 'error': str(e)}
        if p.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'):
            try:
                import qlscan
                res = qlscan.scan_pdf(str(p), pages=(1, 2, 3))
                cfg = _scan_to_quicklook_config(res)
                out = p.with_name(p.stem + '_qlpt.json')
                out.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
                return _normalize_format(cfg, str(out))
            except Exception as e:
                return {'ok': False, 'skipped': True, 'error': '样本格式扫描失败: %s' % e}
        return {'ok': False, 'skipped': True, 'error': '不支持的格式文件类型'}
    # 未选择：井目录查找
    if well_dir:
        wd = Path(str(well_dir))
        cands = []
        for p in sorted(wd.rglob('*.json')):
            low = p.name.lower()
            if 'quicklook' in low or low.endswith('_qlpt.json') or 'format' in low or 'layout' in low:
                cands.append(p)
        # 井目录根下 quicklook_config.json 优先
        root_cfg = wd / 'quicklook_config.json'
        if root_cfg.exists():
            cands.insert(0, root_cfg)
        for p in cands:
            try:
                d = _json.load(open(p, encoding='utf-8'))
                if isinstance(d, dict) and (d.get('legend_items') or d.get('header_fields')
                                            or d.get('title_template') or d.get('legend')):
                    return _normalize_format(d, str(p))
            except Exception:
                continue
    return {'ok': False, 'skipped': True, 'reason': '未选择且井目录未找到 quicklook 格式文件'}


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
                   well_name=None, pdf_path=None) -> dict:
    """读取 masterlog（录井图 PDF）→ 岩性层 + 气测异常井段；带缓存。"""
    try:
        from .masterlog import extract_masterlog
    except Exception as e:
        return {'ok': False, 'error': 'masterlog 模块不可用: %s' % e}
    cands = [Path(str(pdf_path))] if pdf_path else _masterlog_candidates(well_dir)
    if not cands:
        return {'ok': False, 'skipped': True, 'error': '未找到 masterlog PDF'}
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


def _info_paths(well_dir, well_name=None):
    """定位井 info.json（源井目录优先，其次输出目录由调用方处理）。"""
    wd = Path(str(well_dir))
    cands = []
    try:
        for p in sorted(wd.rglob('*info.json')):
            cands.append(p)
    except Exception:
        pass
    if well_name:
        for name in ('%sinfo.json' % well_name, '%sinfo.json' % well_name.lower(),
                     '%sinfo.json' % well_name.upper()):
            for base in (wd,):
                q = base / name
                if q.exists() and q not in cands:
                    cands.append(q)
    return cands


def _deep_merge(dst, src):
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _merge_auto(dst, src):
    """首次只补缺失字段（保护人工已有字段）；已 _自动同步 则整体刷新。"""
    if dst.get('_自动同步'):
        _deep_merge(dst, src)
    else:
        for k, v in src.items():
            if k not in dst or dst.get(k) in (None, '', [], {}):
                dst[k] = v
    return dst


def sync_info_json(well_dir, ctx, out_dir=None, well_name=None) -> dict:
    """把 well_docs 读取结果同步进 <井名>info.json（可读可改的单一配置）。

    规则：
    - 只补/更新「地质设计」「录井图」「甲方格式」三个分区，保留用户已有手工字段；
    - 手工修改优先：若 info 中已有同名字段，不覆盖（_自动同步 标记只在首次写入）；
    - 记录 _同步时间/_来源/_自动同步，便于下次判断是否刷新；
    - 返回 {path, updated}。
    """
    wd = Path(str(well_dir))
    wn = well_name or ctx.get('well') or wd.name.replace(' ', '_')
    paths = _info_paths(wd, wn)
    info_path = paths[0] if paths else (wd / ('%sinfo.json' % wn))
    try:
        info = json.load(open(info_path, encoding='utf-8')) if info_path.exists() else {}
    except Exception:
        info = {}
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    des = ctx.get('design') or {}
    mlh = ctx.get('masterlog_header') or {}
    ml = ctx.get('masterlog') or {}
    cf = ctx.get('client_format') or {}
    # 地质设计
    des_sec = info.setdefault('地质设计', {})
    if True:
        _merge_auto(des_sec, {
            '井名': des.get('well') or wn,
            '气田/油田': des.get('field'),
            '国家': des.get('country'),
            '井型': des.get('well_type'),
            '设计井深': des.get('designed_td_m'),
            '构造位置': des.get('structure'),
            '目的层': des.get('target_formation'),
            '预测地层序列': [x.get('name') for x in (des.get('formation_names') or [])],
            '地层顶': des.get('formation_tops') or [],
            '流体界面': des.get('contacts') or [],
            '套管程序': des.get('casing') or [],
            '目标井段': des.get('interval'),
            '设计目的': des.get('purpose'),
            '区域地质': des.get('regional_geology') or [],
            '井位': des.get('location') or {},
            '来源文件': [x.get('file') for x in (des.get('sources') or [])],
            '解析置信度': des.get('confidence'),
            '_同步时间': now,
            '_来源': 'well_docs:read_design',
            '_自动同步': True,
        })
    # 录井图
    ml_sec = info.setdefault('录井图', {})
    if True:
        _merge_auto(ml_sec, {
            '来源文件': os.path.basename(ml.get('source_pdf') or '') or None,
            '岩性层数': ml.get('lith_layers'),
            '岩性分布': ml.get('lith_dist') or {},
            '深度范围': ml.get('depth_range'),
            '气测异常事件': ml.get('gas_events'),
            '气测异常井段': ml.get('gas_zones'),
            '气测异常总厚_m': ml.get('gas_zone_total_m'),
            '气测异常等级': ml.get('gas_zone_grades') or {},
            '图头': {
                '作业公司': (mlh.get('fields') or {}).get('company'),
                '服务商': mlh.get('services') or [],
                '开钻日期': (mlh.get('fields') or {}).get('spud_date'),
                '完钻日期': (mlh.get('fields') or {}).get('end_date'),
                '完钻井深': (mlh.get('fields') or {}).get('final_depth'),
                '井型': (mlh.get('fields') or {}).get('well_type'),
                '泥浆': mlh.get('mud') or [],
                '井身结构': mlh.get('sizes') or [],
                '岩性图例': mlh.get('lithology_legend') or [],
                '油气显示图例': mlh.get('show_legend') or [],
            },
            '_同步时间': now,
            '_来源': 'well_docs:read_masterlog',
            '_自动同步': True,
        })
    # 解释参数（可人工修改）：气油比例/干层含烃
    par_sec = info.setdefault('解释参数', {})
    for _k, _v in (('气油比例', None), ('干层含烃', True)):
        if _k not in par_sec:
            par_sec[_k] = _v
    par_sec.setdefault('_说明', '气油比例=GAS_OIL中气占烃比例(0-1)，默认各半0.5；如试油测试油气比例不同可修改（0.4=气40%/油60%仅示例）')
    # 甲方格式
    cf_sec = info.setdefault('甲方格式', {})
    if True:
        _merge_auto(cf_sec, {
            '来源文件': os.path.basename(cf.get('source') or '') or None,
            '格式名': cf.get('format_name'),
            '图例标题': cf.get('legend_title'),
            '图例': cf.get('legend_labels') or [],
            '表头固定': cf.get('header_fixed') or {},
            '井身结构': cf.get('borehole_record') or [],
            '套管': cf.get('casing_record') or [],
            '_同步时间': now,
            '_来源': 'well_docs:read_client_format',
            '_自动同步': True,
        })
    try:
        json.dump(info, open(info_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception as e:
        return {'path': str(info_path), 'updated': False, 'error': str(e)}
    return {'path': str(info_path), 'updated': True}


def load_info_overrides(well_dir, well_name=None) -> dict:
    """读 info.json 的三类手工配置（地质设计/录井图/甲方格式）。"""
    paths = _info_paths(well_dir, well_name)
    out = {}
    for p in paths[:2]:
        try:
            d = json.load(open(p, encoding='utf-8'))
            for k in ('地质设计', '录井图', '甲方格式'):
                if isinstance(d.get(k), dict):
                    out.setdefault(k, {})
                    _deep_merge(out[k], d[k])
        except Exception:
            continue
    return out


def _apply_info_overrides(ctx, ov):
    """把 info.json 中文配置映射回 parsed 字段（人工修改优先）。"""
    des = (ov or {}).get('地质设计') or {}
    d = ctx.setdefault('design', {})
    _map = {'井名': 'well', '气田/油田': 'field', '国家': 'country', '井型': 'well_type',
            '设计井深': 'designed_td_m', '构造位置': 'structure', '目的层': 'target_formation',
            '设计目的': 'purpose', '区域地质': 'regional_geology', '井位': 'location'}
    for k, f in _map.items():
        if des.get(k) not in (None, '', [], {}):
            d[f] = des[k]
    if des.get('目标井段'):
        itv = des['目标井段']
        try:
            if isinstance(itv, dict) and itv.get('top') is not None:
                d['interval'] = {'top': float(itv['top']), 'bottom': float(itv['bottom']),
                                 'text': str(itv.get('说明') or itv.get('text') or 'info.json 配置')}
        except Exception:
            pass
    for k, f in (('套管程序', 'casing'), ('流体界面', 'contacts'),
                 ('地层顶', 'formation_tops')):
        if des.get(k):
            d[f] = des[k]
    if des.get('预测地层序列'):
        _seq = des['预测地层序列']
        d['formation_names'] = [x if isinstance(x, dict) else {'name': str(x)} for x in _seq]
    # 录井图
    ml = (ov or {}).get('录井图') or {}
    h = ctx.setdefault('masterlog_header', {})
    hf = h.setdefault('fields', {})
    ht = ml.get('图头') or {}
    _m2 = {'作业公司': 'company', '开钻日期': 'spud_date', '完钻日期': 'end_date',
           '完钻井深': 'final_depth', '井型': 'well_type'}
    for k, f in _m2.items():
        if ht.get(k) not in (None, '', [], {}):
            hf[f] = ht[k]
    if ht.get('服务商'):
        h['services'] = ht['服务商']
    for k, f in (('泥浆', 'mud'), ('井身结构', 'sizes'),
                 ('岩性图例', 'lithology_legend'), ('油气显示图例', 'show_legend')):
        if ht.get(k):
            h[f] = ht[k]
    h['ok'] = True
    m = ctx.setdefault('masterlog', {})
    for k, f in (('岩性层数', 'lith_layers'), ('岩性分布', 'lith_dist'),
                 ('气测异常事件', 'gas_events'), ('气测异常井段', 'gas_zones'),
                 ('气测异常总厚_m', 'gas_zone_total_m'), ('气测异常等级', 'gas_zone_grades')):
        if ml.get(k) not in (None, '', [], {}):
            m[f] = ml[k]
    return ctx


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
            _infos = _info_paths(wd, well)
            _newest = max([cache.stat().st_mtime] +
                          [q.stat().st_mtime for q in _infos if q.exists()] or [0])
            # 源文件与 info.json 均未变才复用
            if srcs and all(Path(s).exists() for s in srcs) and \
                    cache.stat().st_mtime >= _newest - 1e-6:
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
    # info.json 手工配置优先（可读可改）：地质设计/录井图/甲方格式
    try:
        _ov = load_info_overrides(wd, well)
        if _ov.get('地质设计'):
            _deep_merge(ctx['design'], _ov['地质设计'])
        if _ov.get('甲方格式') and (ctx.get('client_format') or {}).get('ok', True):
            _cf0 = ctx.get('client_format') or {}
            _cf0.update({'format_name': _ov['甲方格式'].get('格式名') or _cf0.get('format_name'),
                         'legend_labels': _ov['甲方格式'].get('图例') or _cf0.get('legend_labels') or [],
                         'legend_title': _ov['甲方格式'].get('图例标题') or _cf0.get('legend_title'),
                         'source': _ov['甲方格式'].get('来源文件') or _cf0.get('source'),
                         'from_info': True})
            ctx['client_format'] = _cf0
        if _ov.get('录井图'):
            ctx['masterlog_info'] = _ov['录井图']
    except Exception as e:
        ctx['info_override_error'] = str(e)
    try:
        ctx['masterlog_header'] = read_masterlog_header(wd, out_dir=od, well_name=well)
    except Exception as e:
        ctx['masterlog_header'] = {'ok': False, 'error': str(e)}
    try:
        ctx['client_format'] = read_client_format(wd)
    except Exception as e:
        ctx['client_format'] = {'ok': False, 'error': str(e)}
    try:
        if _ov:
            _apply_info_overrides(ctx, _ov)
    except Exception as e:
        ctx['info_apply_error'] = str(e)
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


def grade_gas_zones(zones, gas=None):
    """气测异常井段分级（唯一实现位于 masterlog.py；此处为模块统一出口）。"""
    from .masterlog import grade_gas_zones as _g
    return _g(zones, gas)
