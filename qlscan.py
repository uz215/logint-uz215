#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""qlscan.py — quick look 样本格式扫描器（OCR 一次扫描 → 格式配置 JSON）

解决"快速解释只给样本格式、要求按格式出图"的对接问题：
对甲方样本 PDF/图片做一次 OCR 扫描，自动提取版式结构（页1 右转信息表
字段对、井名/图名/比例尺、页2 免责声明全文、页3 LEGEND 图例文字），
输出可直接作为 qlpt.json 格式配置的 JSON，避免多轮人工打磨。

用法:
  python qlscan.py <样本PDF> --pages 1,2,3 --out templates/qlpt_scan.json
  python qlscan.py <样本PDF>            # 仅打印扫描摘要
依赖: pymupdf(fitz), rapidocr_onnxruntime（均已安装）
"""
import argparse
import json
import re
import sys
from pathlib import Path

import fitz

_HAS_RAPID = False
_OCR = None


def _get_ocr():
    global _OCR, _HAS_RAPID
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
            _HAS_RAPID = True
        except Exception as e:  # noqa: BLE001
            print(f'[qlscan] rapidocr 不可用: {e}（回退无 OCR）')
            _OCR = False
    return _OCR or None


def page_to_png(pdf_path, pno, dpi=150, out_dir=None, crop=(0.0, 1.0)):
    """提取 PDF 指定页为 PNG，返回图片路径与尺寸。

    crop=(top_ratio, bottom_ratio)：只渲染页面上部区域（免责声明/LEGEND
    等表头都在页面顶部，裁上部可放大文字、显著提高 OCR 识别率）。
    """
    doc = fitz.open(pdf_path)
    if pno < 0 or pno >= doc.page_count:
        doc.close()
        return None, (0, 0)
    pg = doc[pno]
    rect = pg.rect
    top_r, bot_r = crop
    clip = fitz.Rect(0, rect.height * top_r, rect.width, rect.height * bot_r)
    pix = pg.get_pixmap(dpi=dpi, clip=clip)
    if out_dir is None:
        out_dir = Path(pdf_path).parent
    out = Path(out_dir) / f'_qlscan_p{pno + 1}.png'
    pix.save(str(out))
    doc.close()
    return str(out), (pix.width, pix.height)


def ocr_page(img_path):
    """整页 OCR，返回带坐标文本项列表"""
    ocr = _get_ocr()
    if ocr is None:
        return []
    res, _ = ocr(str(img_path))
    items = []
    for b, txt, score in (res or []):
        pts = [[int(v) for v in p] for p in b]
        x0, y0 = pts[0]
        x1, y1 = pts[2]
        items.append({
            'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
            'text': (txt or '').strip(), 'score': float(score),
        })
    return items


def rows_from_items(items, y_gap=14):
    """按 y0 聚类成行（行内按 x0 排序），返回 [{y, x0, x1, text}]"""
    rows = []
    for it in sorted(items, key=lambda i: (i['y0'], i['x0'])):
        hit = None
        for r in rows:
            if abs(r['y'] - it['y0']) <= y_gap:
                hit = r
                break
        if hit is None:
            hit = {'y': it['y0'], 'items': []}
            rows.append(hit)
        hit['items'].append(it)
    out = []
    for r in rows:
        r['items'].sort(key=lambda i: i['x0'])
        xs = [i['x0'] for i in r['items']]
        xe = [i['x1'] for i in r['items']]
        out.append({
            'y': r['y'], 'x0': min(xs), 'x1': max(xe),
            'text': ' '.join(i['text'] for i in r['items']),
            'cells': [(i['x0'], i['text']) for i in r['items']],
        })
    out.sort(key=lambda r: r['y'])
    return out


def merge_multiline(items, y_gap=30):
    """把同段连续行合并为整段文本（用于免责声明/图例标题）"""
    rows = rows_from_items(items, y_gap=y_gap)
    segs = []
    cur = []
    for r in rows:
        if cur and r['y'] - cur[-1]['y'] > y_gap * 2:
            segs.append(' '.join(x['text'] for x in cur))
            cur = []
        cur.append(r)
    if cur:
        segs.append(' '.join(x['text'] for x in cur))
    return segs


# ---------- 版式提取 ----------

_HEADER_FIELD_KEYS = (
    'rig name', 'well name', 'field', 'company', 'contractor', 'location',
    'country', 'spudded', 'reached', 'td', 'date', 'logged', 'processed',
    'coord', 'long', 'lat', 'x :', 'y :', 'elevation', 'elev', 'kb', 'gl',
    'density', 'mud', 'interval', 'equip', 'corrected', 'depth', 'scale',
    'datum', 'unit', 'permit', 'lease', 'operator',
)


def scan_header_page(items, W, H):
    """页1（右转信息表放正后）字段提取：字段名行/值行配对 + 井名/图名/比例尺。
    样本页1 是完整右转表（信息字段+BH/CS+免责+LEGEND 同页），rows 全部保留，
    供免责/图例/套管记录二次分类提取。"""
    rows = rows_from_items(items)
    fields = []      # [{label, value, y}]
    big_text = []    # 大字号文本（井名/图名/比例尺候选）
    all_rows = []    # 全行文本（供免责/图例/BH-CS 提取）
    for r in rows:
        cells = r['cells']
        text = r['text']
        all_rows.append({
            'y': r['y'], 'x0': r['x0'], 'x1': r['x1'],
            'text': text, 'cells': cells,
        })
        span = r['x1'] - r['x0']
        # 图名：Well Logging ... Result Plot
        if re.search(r'well\s*logging', text, re.I) and 'plot' in text.lower():
            big_text.append({'kind': 'title', 'text': text, 'y': r['y']})
            continue
        # 井名：含 (…-…) 或大写字母+数字+横杠的长文本
        if len(text) > 8 and re.search(r'[A-Z0-9]{2,}[\s-]+[A-Z0-9]', text) \
                and not any(k in text.lower() for k in _HEADER_FIELD_KEYS):
            big_text.append({'kind': 'well_name', 'text': text, 'y': r['y']})
            continue
        # 比例尺：含 1:xxx 或 SCALE
        if re.search(r'1\s*:\s*\d{2,4}', text):
            big_text.append({'kind': 'scale', 'text': text, 'y': r['y']})
            continue
        # 字段名:值 配对（同列相邻行）
        for x0, cell in cells:
            low = cell.lower().rstrip('.: ')
            if len(low) < 2 or len(low) > 40:
                continue
            if any(low.startswith(k) or k in low for k in _HEADER_FIELD_KEYS):
                # 同行右邻或下一行同 x 区域为值
                val = ''
                same_row = [c for c in cells if c[0] > x0]
                if same_row:
                    val = same_row[0][1]
                fields.append({'label': cell, 'value': val, 'x0': x0, 'y': r['y']})
                break
    return {'fields': fields, 'big_text': big_text, 'rows': all_rows}


def scan_disclaimer(items, W, H):
    """免责声明：从命中关键词的行起向后收集连续行（表底部区域），
    遇到下一表标题（BOREHOLE/CASING/LEGEND）截断。"""
    rows = rows_from_items(items, y_gap=14)
    disc_lines = []
    started = False
    for r in rows:
        t = r['text']
        if re.search(r'interpret|opinion|customer|guarantee|inferences', t, re.I) \
                and not re.search(r'result\s*plot', t, re.I):
            started = True
        if started:
            if re.search(r'^borehole|casing\s*record|^legend', t, re.I):
                break
            disc_lines.append(t)
    return {'disclaimer': ' '.join(disc_lines) if disc_lines else None}


def scan_legend(items, W, H):
    """LEGEND：标题 + 图例文字项（图标无法 OCR，保留文字供 symbol 匹配；
    无 symbol 时留空但文字必须保留）。整行与单元格双通道匹配，去重。"""
    rows = rows_from_items(items)
    title = None
    legend = []
    _KEY = ('oil', 'gas', 'water', 'shale', 'sand', 'coal', 'tight',
            'condensate', 'pay', 'reservoir', 'limestone', 'dolomite',
            'porosity', 'perme')
    for r in rows:
        text = r['text']
        if 'legend' in text.lower():
            title = text
            continue
        if any(k in text.lower() for k in _KEY):
            if not any(x.get('label') == text for x in legend):
                legend.append({'label': text, 'y': r['y']})
            continue
        for _x0, cell in r['cells']:
            low = cell.lower()
            if any(k in low for k in _KEY):
                if not any(x.get('label') == cell for x in legend):
                    legend.append({'label': cell, 'y': r['y']})
    return {'legend_title': title, 'legend_items': legend}


# ---------- 主流程 ----------

def scan_pdf(pdf_path, pages=(1, 2, 3), dpi=150, tmp_dir=None):
    doc = fitz.open(pdf_path)
    npages = doc.page_count
    doc.close()
    result = {'source': str(pdf_path), 'pages': npages, 'scanned': []}
    for pno in pages:
        if pno < 1 or pno > npages:
            continue
        # 页2/页3 只裁页面上部（免责声明/LEGEND 表头在顶部），OCR 更清晰
        _crop = (0.0, 1.0)
        if pno == 2:
            _crop = (0.0, 0.45)
        if pno == 3:
            _crop = (0.0, 0.35)
        img, (W, H) = page_to_png(pdf_path, pno - 1, dpi=dpi, out_dir=tmp_dir,
                                  crop=_crop)
        if not img:
            continue
        items = ocr_page(img)
        page = {'page': pno, 'size': [W, H], 'n_items': len(items),
                'crop': list(_crop)}
        # 页1 即完整右转表（信息字段+BH/CS+免责+LEGEND 同页），页2/3 按需
        if pno == 1:
            hdr = scan_header_page(items, W, H)
            page.update(hdr)
            page.update(scan_disclaimer(items, W, H))
            page.update(scan_legend(items, W, H))
        if pno in (2, 3):
            page.update(scan_disclaimer(items, W, H))
        if pno == 3:
            page.update(scan_legend(items, W, H))
        result['scanned'].append(page)
    return result


def main():
    ap = argparse.ArgumentParser(description='quick look 样本格式 OCR 扫描器')
    ap.add_argument('pdf', help='样本 PDF 或图片路径')
    ap.add_argument('--pages', default='1,2,3', help='要扫描的页码，逗号分隔，默认 1,2,3')
    ap.add_argument('--out', default='', help='输出 JSON 路径（默认只打印摘要）')
    ap.add_argument('--dpi', type=int, default=150)
    args = ap.parse_args()

    if not _get_ocr():
        print('[qlscan] OCR 不可用，扫描失败')
        return 2

    pages = [int(p) for p in args.pages.split(',') if p.strip().isdigit()]
    result = scan_pdf(args.pdf, pages=pages, dpi=args.dpi,
                      tmp_dir=str(Path(args.pdf).parent))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[qlscan] 已输出格式配置 -> {args.out}')

    # 摘要
    for pg in result['scanned']:
        print(f"== 页 {pg['page']} ({pg['size'][0]}x{pg['size'][1]}, {pg['n_items']} 项)")
        if 'big_text' in pg:
            for b in pg['big_text']:
                print(f"   [{b['kind']}] {b['text'][:80]}")
        if 'fields' in pg:
            for f in pg['fields'][:24]:
                print(f"   field: {f['label'][:40]} = {f['value'][:40]}")
        if pg.get('disclaimer'):
            print(f"   disclaimer({len(pg['disclaimer'])}): {pg['disclaimer'][:100]}...")
        if pg.get('legend_title'):
            print(f"   legend_title: {pg['legend_title']}")
        if pg.get('legend_items'):
            for it in pg['legend_items'][:14]:
                print(f"   legend: {it['label'][:60]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
