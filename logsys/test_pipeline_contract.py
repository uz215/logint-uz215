# -*- coding: utf-8 -*-
"""主流程一致性契约测试（单一裁决/一处确定）。

检查一口井输出目录：
  1) 候选层表存在：<井>_interpretation_layers_rules.csv / *_ML.csv（可有其一）；
  2) **唯一** canonical：<井>_interpretation_layers.csv，且决策 JSON 记录 chosen/canonical；
  3) canonical 层数与决策一致；canonical 是 chosen 候选的副本（大小一致）；
  4) processed CSV 只有一套 INTERPRETATION（无重复解释列），层表字段完整；
  5) QC/清洗报告、运行清单存在；清单含 interp_decision/kb_usage；
  6) canonical 含知识证据列（EV_*）。
用法：python -m logsys.test_pipeline_contract --well TrakesKE-1 [--dir ...]
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import pandas as pd

BASE = r'D:\360\src'
WS = r'C:\Users\Administrator\Documents\deepseek-harness\default-workspace'
REQ_COLS = ['LAYER_ID', 'TOP_MD', 'BASE_MD', 'THICKNESS', 'LITHOLOGY', 'INTERPRETATION']


def _sha(path, n=65536):
    try:
        return hashlib.sha256(open(path, 'rb').read(n)).hexdigest()
    except Exception:
        return None


def check(well: str, d: str) -> list:
    rows = []

    def add(name, ok, detail=''):
        rows.append((name, bool(ok), detail))

    canon = os.path.join(d, well + '_interpretation_layers.csv')
    rules = os.path.join(d, well + '_interpretation_layers_rules.csv')
    ml = os.path.join(d, well + '_interpretation_layers_ML.csv')
    decp = os.path.join(d, well + '_interpretation_decision.json')
    add('canonical 层表存在', os.path.exists(canon), canon)
    add('决策 JSON 存在', os.path.exists(decp), decp)
    dec = {}
    if os.path.exists(decp):
        try:
            dec = json.load(open(decp, encoding='utf-8'))
        except Exception:
            pass
    add('裁决值合法', dec.get('chosen') in ('rules', 'ML'), dec.get('chosen'))
    add('候选层表存在(至少一)', os.path.exists(rules) or os.path.exists(ml),
        '%s | %s' % (os.path.exists(rules), os.path.exists(ml)))
    if os.path.exists(canon) and dec.get('canonical'):
        add('canonical_rows 与文件一致',
            int(dec.get('canonical_rows') or 0) == len(pd.read_csv(canon)))
        # 有"裁决后处理"（解释井段裁剪/气田先验等）时 canonical 允许与候选不同，
        # 但仍必须与决策记录的行数一致（单一成果，过程可追溯）。
        _post = bool(dec.get('interval')) or bool(dec.get('gas_field_prior')) or bool(dec.get('postprocess'))
        if _post:
            add('canonical 经后处理(井段/气田先验)且行数一致',
                len(pd.read_csv(canon)) == int(dec.get('canonical_rows') or 0),
                {'postprocess': True, 'rows': len(pd.read_csv(canon)),
                 'dec': dec.get('canonical_rows')})
        else:
            chosen = ml if dec.get('chosen') == 'ML' else rules
            add('canonical=chosen 候选副本', bool(chosen) and os.path.exists(chosen)
                and _sha(chosen) == _sha(canon))
    if os.path.exists(canon):
        lay = pd.read_csv(canon)
        add('层表必需列完整', all(c in lay.columns for c in REQ_COLS),
            [c for c in REQ_COLS if c not in lay.columns])
        add('canonical 含知识证据列(EV_*)',
            any(c.startswith('EV_') for c in lay.columns),
            [c for c in lay.columns if c.startswith('EV_')])
    pr = os.path.join(d, well + '_processed.csv')
    if os.path.exists(pr):
        cols = list(pd.read_csv(pr, nrows=1).columns)
        # 结论列只能有 INTERPRETATION；SCORE/WHY 等辅助列允许（非结论）
        concl = [c for c in cols if c.upper() == 'INTERPRETATION']
        aux = [c for c in cols if c.upper().startswith('INTERPRETATION')
               and c.upper() != 'INTERPRETATION']
        add('解释结论列唯一', len(concl) == 1, {'concl': concl, 'aux': aux})
        add('processed CSV 存在 MD/解释列', 'MD' in cols and len(concl) == 1)
    add('QC 报告存在', bool(glob.glob(os.path.join(d, '*_qc_report.json'))))
    add('清洗报告存在', bool(glob.glob(os.path.join(d, '*_data_clean_report.json'))))
    man = os.path.join(d, well + '_run_manifest.json')
    add('运行清单存在', os.path.exists(man))
    if os.path.exists(man):
        try:
            m = json.load(open(man, encoding='utf-8'))
            add('清单含 interp_decision', 'interp_decision' in m)
            add('清单含 kb_usage', 'kb_usage' in m)
        except Exception:
            add('清单可读', False)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--well', default='TrakesKE-1')
    ap.add_argument('--dir', default=None)
    args = ap.parse_args(argv)
    candidates = [args.dir] if args.dir else [
        os.path.join(WS, 'output', args.well), os.path.join(BASE, 'output', args.well)]
    d = next((x for x in candidates if x and os.path.isdir(x)), None)
    if not d:
        print('输出目录不存在:', candidates)
        return 2
    rows = check(args.well, d)
    ok = sum(1 for _, k, _ in rows if k)
    for name, k, detail in rows:
        print(('  PASS  ' if k else '  FAIL  ') + name + ((' | ' + str(detail)) if detail else ''))
    print('\n结果: %d 通过, %d 失败（%s）' % (ok, len(rows) - ok, d))
    return 0 if ok == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main())
