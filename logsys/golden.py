# -*- coding: utf-8 -*-
"""黄金图回归：quicklook 出图 → 指纹（页数/尺寸/文本哈希/栅格缩略图）→ 与基线比对。

用法：
    python -m logsys.golden --update     # 生成/更新基线
    python -m logsys.golden --check      # 回归检查（失败退出码 1）

基线文件：<项目>/tests/golden/qlpt_golden.json
测试数据：<项目>/tests/golden/SMOKE-2_processed.csv + SMOKE-2info.json（合成井，稳定）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

BASE = r'D:\360\src'
GOLD_DIR = os.path.join(BASE, 'tests', 'golden')
GOLD_JSON = os.path.join(GOLD_DIR, 'qlpt_golden.json')
GOLD_JSON_CMPT = os.path.join(GOLD_DIR, 'cmpt_golden.json')
PROC = os.path.join(GOLD_DIR, 'SMOKE-2_processed.csv')
INFO = os.path.join(GOLD_DIR, 'SMOKE-2info.json')


def render(out_dir: str, kind: str = 'qlpt') -> str:
    import pandas as pd
    import logvis

    if not os.path.exists(PROC):
        raise FileNotFoundError('缺少测试数据: ' + PROC)
    data = pd.read_csv(PROC, low_memory=False)
    os.makedirs(out_dir, exist_ok=True)
    results = {
        'well_name': 'SMOKE-2', 'output_dir': out_dir, 'well_dir': GOLD_DIR,
        'well_info_json': INFO, 'depth_unit': 'm',
        'las_info': {'well': {'well_name': 'SMOKE-2', 'company': 'TESTCO',
                              'country': 'Testland', 'field_name': 'TESTFIELD',
                              'depth_unit': 'm'}},
    }
    if kind == 'cmpt':
        pdf = logvis.visualize_composite_log(data, results, gas_data=None, quicklook_config=None)
    else:
        pdf = logvis.visualize_quicklook_log(data, results, gas_data=None, quicklook_config=None)
    return pdf


def fingerprint(pdf_path: str) -> dict:
    import fitz
    import numpy as np
    doc = fitz.open(pdf_path)
    page = doc[0]
    text = page.get_text()
    pix = page.get_pixmap(matrix=fitz.Matrix(0.05, 0.05), colorspace=fitz.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(float)
    return {
        'pages': doc.page_count,
        'width': round(page.rect.width, 2),
        'height': round(page.rect.height, 2),
        'text_md5': hashlib.md5(text.encode('utf-8')).hexdigest(),
        'text_chars': len(text),
        'thumb_shape': [int(pix.width), int(pix.height)],
        'thumb_mean': round(float(arr.mean()), 3),
        'thumb': [round(float(v), 1) for v in arr.flatten().tolist()][:2048],
    }


def compare(cur: dict, gold: dict, tol_mean: float = 4.0) -> list:
    diffs = []
    for k in ('pages', 'width', 'height', 'text_chars'):
        if cur.get(k) != gold.get(k):
            diffs.append('%s: %r != %r' % (k, cur.get(k), gold.get(k)))
    if cur.get('text_md5') != gold.get('text_md5'):
        diffs.append('text_md5 变化（文案/字段可能被改动）')
    dm = abs(float(cur.get('thumb_mean', 0)) - float(gold.get('thumb_mean', 0)))
    if dm > tol_mean:
        diffs.append('thumb_mean 偏差 %.2f > %.2f' % (dm, tol_mean))
    # 像素级差异（缩略图同尺寸时）
    a, b = cur.get('thumb') or [], gold.get('thumb') or []
    if len(a) == len(b) and a:
        import numpy as _np
        pix = float(_np.mean(_np.abs(_np.array(a) - _np.array(b))))
        if pix > tol_mean:
            diffs.append('缩略图像素差 %.2f > %.2f' % (pix, tol_mean))
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser(description='quicklook 黄金图回归')
    ap.add_argument('--update', action='store_true', help='更新基线')
    ap.add_argument('--check', action='store_true', help='检查回归')
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'golden_out'))
    ap.add_argument('--kind', default='qlpt', choices=['qlpt', 'cmpt'])
    ap.add_argument('--tol', type=float, default=4.0, help='栅格均值容差')
    args = ap.parse_args(argv)
    if not (args.update or args.check):
        print('需 --update 或 --check')
        return 2
    pdf = render(args.out, kind=args.kind)
    cur = fingerprint(pdf)
    print('渲染: %s (%d 页, %.1f x %.1f pt, 文本 %d 字)' % (
        os.path.basename(pdf), cur['pages'], cur['width'], cur['height'], cur['text_chars']))
    _gold_path = GOLD_JSON if args.kind == 'qlpt' else GOLD_JSON_CMPT
    if args.update:
        os.makedirs(GOLD_DIR, exist_ok=True)
        json.dump(cur, open(_gold_path, 'w', encoding='utf-8'), ensure_ascii=False)
        print('基线已更新:', _gold_path)
        return 0
    if not os.path.exists(_gold_path):
        print('基线不存在，请先 --update')
        return 2
    gold = json.load(open(_gold_path, encoding='utf-8'))
    diffs = compare(cur, gold, args.tol)
    if diffs:
        print('黄金图回归: FAIL')
        for d in diffs:
            print('  -', d)
        return 1
    print('黄金图回归: PASS（页数/尺寸/文本/栅格均一致）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
