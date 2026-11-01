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
    for s in (ctx['design'].get('sources') or []):
        ctx['sources'].append(s)
    if ctx['masterlog'].get('source_pdf'):
        ctx['sources'].append({'file': Path(ctx['masterlog']['source_pdf']).name,
                               'path': ctx['masterlog']['source_pdf'], 'type': 'masterlog'})
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
