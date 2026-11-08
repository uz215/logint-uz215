# -*- coding: utf-8 -*-
"""录井图知识提取：基础数据/岩性/气测异常/油气显示/工程情况。"""
from __future__ import annotations
import re


def _num(s):
    try:
        return float(str(s).replace(',', '.'))
    except Exception:
        return None


def _depth_near(text, max_chars=120):
    m = re.search(r'(-?\d{3,5}(?:\.\d+)?)\s*(m|ft|米|英尺)?', text[:max_chars])
    if not m:
        return None, None
    v = _num(m.group(1)); u = (m.group(2) or 'm').lower()
    if u in ('ft', '英尺') and v is not None: v *= 0.3048
    return (round(v, 1) if v is not None else None), ('m' if u not in ('ft', '英尺') else 'm')


def parse_mudlog_text(text, well_name=''):
    """从录井图文本提取五类知识（正则/关键词，保守不臆造）。"""
    out = {'well_name': well_name, 'basic_data': {}, 'lithology': [],
           'gas_show': [], 'oil_gas_show': [], 'engineering': []}
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    joined = '\n'.join(lines)
    # 基础数据
    def grab(pat, key):
        m = re.search(pat, joined, re.I)
        if m:
            out['basic_data'][key] = m.group(1).strip()[:80]
    grab(r'(?:WELL\s*NAME|井名|井\s*名)\s*[:：]\s*([^\n]{2,60})', 'well_name')
    grab(r'(?:LOCATION|井位|井\s*位)\s*[:：]\s*([^\n]{2,120})', 'location')
    grab(r'(?:WELL\s*TYPE|井型|井别)\s*[:：]\s*([^\n]{2,60})', 'well_category')
    grab(r'(?:BIT\s*SIZE|钻头尺寸|钻头程序)\s*[:：]?\s*([^\n]{1,80})', 'bit_program')
    grab(r'(?:CASING|套管程序|套管)\s*[:：]?\s*([^\n]{1,120})', 'casing_program')
    grab(r'(?:MUD\s*TYPE|泥浆类型|钻井液类型)\s*[:：]?\s*([^\n]{2,80})', 'mud_type')
    grab(r'(?:MUD\s*(?:DENSITY|WEIGHT)|泥浆密度|钻井液密度)\s*[:：]?\s*([0-9.]+)', 'mud_density')
    grab(r'(?:MUD\s*VISCOSITY|泥浆粘度|钻井液粘度)\s*[:：]?\s*([0-9.]+)', 'mud_viscosity')
    grab(r'(?:FLUID\s*LOSS|失水)\s*[:：]?\s*([0-9.]+)', 'fluid_loss')
    # 井别中英文标准化
    wc = (out['basic_data'].get('well_category') or '').lower()
    for kw, typ in (('explor', '探井'), ('appraisal', '评价井'), ('develop', '开发井'),
                    ('探井', '探井'), ('评价', '评价井'), ('开发', '开发井')):
        if kw in wc:
            out['basic_data']['well_category'] = typ
            break
    # 岩性（带深度）
    lith_kw = (('limestone', 'limestone'), ('dolomite', 'dolomite'), ('sandstone', 'sandstone'),
               ('shale', 'shale'), ('灰岩', 'limestone'), ('白云岩', 'dolomite'),
               ('砂岩', 'sandstone'), ('泥岩', 'shale'), ('膏岩', 'anhydrite'),
               ('anhydrite', 'anhydrite'), ('мергель', 'limestone'), ('известняк', 'limestone'),
               ('доломит', 'dolomite'), ('песчаник', 'sandstone'), ('алевролит', 'shale'),
               ('глина', 'shale'), ('сланец', 'shale'), ('ангидрит', 'anhydrite'),
               ('соль', 'halite'), ('базальт', 'basalt'))
    for ln in lines:
        low = ln.lower()
        for kw, lith in lith_kw:
            if kw in low:
                dep, unit = _depth_near(ln)
                if dep is not None:
                    out['lithology'].append({'depth': dep, 'unit': unit, 'lith': lith,
                                             'source': 'mudlog', 'text': ln[:120]})
                break
    for ln in lines:
        low = ln.lower()
        # 气测异常
        if any(k in low for k in ('gas show', 'gas break', '气测异常', '全烃异常', '气测显示',
                                  'газопроявление', 'газирование', 'газ (усредненный)')):
            dep, unit = _depth_near(ln)
            out['gas_show'].append({'depth': dep, 'unit': unit, 'type': 'GAS_SHOW',
                                    'text': ln[:160], 'source': 'mudlog'})
        # 油气显示 / 油砂 / 级别 / 气泡
        if any(k in low for k in ('oil show', 'gas show', 'oil sand', 'oil stain',
                                  'fluorescence', 'bleeding', 'bubble', '油显示', '气显示',
                                  '油砂', '油斑', '油浸', '油迹', '富含油', '荧光', '气泡',
                                  'нефтепроявление', 'флуоресценция', 'пленка', 'запах нефти',
                                  'признаки нефти', 'признаки газа')):
            dep, unit = _depth_near(ln)
            grade = ''
            for g in ('富含油', '油浸', '油斑', '油迹', '荧光', 'oil sand', 'oil stain',
                      'fluorescence', 'bleeding', '气泡', 'bubble'):
                if g in low:
                    grade = g; break
            out['oil_gas_show'].append({'depth': dep, 'unit': unit, 'grade': grade,
                                        'text': ln[:160], 'source': 'mudlog'})
        # 工程情况
        if any(k in low for k in ('mud loss', 'lost circulation', '漏失', '井漏',
                                  'kick', '溢流', 'stuck', '卡钻', 'collapse', '井塌',
                                  'tight hole', '遇阻', '遇卡',
                                  'поглощение раствора', 'прихват', 'выброс', 'обвал')):
            dep, unit = _depth_near(ln)
            out['engineering'].append({'depth': dep, 'unit': unit,
                                       'text': ln[:160], 'source': 'mudlog'})
    # 去重
    for k in ('lithology', 'gas_show', 'oil_gas_show', 'engineering'):
        seen = set(); vals = []
        for x in out[k]:
            key = (x.get('depth'), x.get('lith') or x.get('grade') or x.get('text'))
            if key not in seen:
                seen.add(key); vals.append(x)
        out[k] = vals
    return out


def extract_mudlog_knowledge(pdf_path, max_pages=8):
    """读取录井图 PDF 文本 → parse_mudlog_text。"""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        txt = ''
        for i in range(min(max_pages, doc.page_count)):
            txt += (doc[i].get_text() or '') + '\n'
        doc.close()
        return parse_mudlog_text(txt)
    except Exception as e:
        return {'error': str(e), 'basic_data': {}, 'lithology': [], 'gas_show': [],
                'oil_gas_show': [], 'engineering': []}


def extract_core_doc_knowledge(path):
    """读取俄文/英文 .doc 岩心描述（UTF-16 文本）→ 基础/层位/岩性/含气/荧光。"""
    import re
    from pathlib import Path
    raw = Path(path).read_bytes()
    txt = raw.decode('utf-16le', errors='ignore')
    # 清理不可打印 + Word 二进制乱码：只保留俄文/英文/数字/常用标点
    import re as _re0
    txt = ''.join(ch if (ch.isprintable() or ch in '\n\t') else ' ' for ch in txt)
    txt = _re0.sub(r'[^А-Яа-яЁёA-Za-z0-9 .,;:()%№/\-\n\r\t]', ' ', txt)
    txt = _re0.sub(r'[ \t]{2,}', ' ', txt)
    lines = [l.strip() for l in txt.splitlines() if len(l.strip()) >= 3]
    out = {'file': Path(path).name, 'basic_data': {}, 'cores': [], 'lithology': [],
           'gas_show': [], 'oil_gas_show': []}
    joined = '\n'.join(lines)
    def _clean(v):
        v = str(v or '').strip()
        for sep in ('Дата', 'Скважина', '№ керна', 'Буровая', 'Пробурено',
                    'Горизонт', 'Длина керна', 'Вынос', 'Средняя', 'ПАРАМЕТРЫ',
                    'Нагрузка', 'Давление', 'MFI', 'RPM', 'Газ', 'ТУБУС',
                    'ГЛУБИНА', 'ОПИСАНИЕ'):
            v = re.split(sep, v)[0].strip()
        return v[:100]
    def grab(pat, key):
        m = re.search(pat, joined, re.I)
        if m:
            out['basic_data'][key] = _clean(m.group(1))
    grab(r'(?:ОПИСАНИЕ\s*КЕРН|CORE\s*DESCRIPTION)\s*№?\s*(\d+)', 'core_no')
    grab(r'(?:Месторождение|Field)\s*[:\s]*([^\n]{2,80})', 'field')
    grab(r'(?:Дата|Date)\s*[:\s]*([0-9./-]{6,20})', 'date')
    grab(r'(?:Скважина|Well)\s*[:\s]*([^\n]{2,40})', 'well')
    grab(r'(?:Буровая установка|Rig)\s*[:\s]*([^\n]{2,40})', 'rig')
    grab(r'(?:Горизонт|Formation)\s*[:\s]*([^\n]{2,80})', 'formation')
    grab(r'(?:Пробурено|Drilled)\s*[:\s]*([0-9.,\- ]{5,40})', 'drilled_interval')
    grab(r'(?:Газ\s*\(усредненный\)|Gas)\s*[:\s]*([0-9.,]+\s*%?)', 'gas_avg')
    for _k in list(out['basic_data'].keys()):
        out['basic_data'][_k] = _clean(out['basic_data'][_k])
    _iv = out['basic_data'].get('drilled_interval') or ''
    import re as _re2
    _mm = _re2.search(r'(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)', _iv)
    _top = _base = None
    if _mm:
        try:
            _top = float(_mm.group(1).replace(',', '.')); _base = float(_mm.group(2).replace(',', '.'))
        except Exception:
            pass
    # 岩性
    lith_map = (('мергель', 'limestone'), ('известняк', 'limestone'), ('доломит', 'dolomite'),
                ('песчаник', 'sandstone'), ('алевролит', 'shale'), ('глина', 'shale'),
                ('ангидрит', 'anhydrite'), ('соль', 'halite'), ('базальт', 'basalt'))
    for ln in lines:
        low = ln.lower()
        for kw, lith in lith_map:
            if kw in low:
                out['lithology'].append({'lith': lith, 'text': _clean(ln)[:160],
                                         'formation': out['basic_data'].get('formation', '未提供'),
                                         'source': Path(path).name})
                break
    # 含气/荧光/油气显示行
    _seen = set()
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in ('газ', 'флуоресценц', 'нефт', 'запах', 'пленк')):
            _neg = ('нет ' in low or 'отсутств' in low) and ('флуоресценц' in low or 'нефт' in low)
            typ = 'GAS_SHOW' if ('газ' in low and not _neg) else ('NO_SHOW' if _neg else 'OIL_SHOW')
            rec = {'text': ln[:200], 'formation': out['basic_data'].get('formation', '未提供'),
                   'source': Path(path).name, 'type': typ,
                   'top': _top, 'base': _base}
            _key = (typ, _clean(ln)[:80], _top, _base)
            if _key in _seen:
                continue
            _seen.add(_key)
            if typ == 'GAS_SHOW':
                out['gas_show'].append(rec)
            elif typ == 'OIL_SHOW':
                out['oil_gas_show'].append(rec)
            else:
                out.setdefault('no_show', []).append(rec)
    if not out.get('description'):
        _ml = _re0.search(r'(?:Мергель|Известняк|Доломит|Песчаник|Алевролит|Глина|Ангидрит|Соль)[^\n\r]{0,500}', txt)
        if _ml:
            out['description'] = _re0.sub(r'\s+', ' ', _ml.group(0)).strip()
    return out
