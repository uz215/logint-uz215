# -*- coding: utf-8 -*-
"""证据栈进层表：为每个解释层附加"相似案例 + 标准条款 + 证据置信度"。

设计：
- 知识库不可用/无案例 → 返回 0，不写列，不影响主流程（零静默失败）；
- 层表原有列与结论不改，仅追加 EV_CASES / EV_CLAUSES / EV_CONF / EV_SUMMARY；
- 深度单位：层表 TOP_MD/BASE_MD 与案例库 top_m/base_m 可能不同（ft vs m），
  这里仅用于"相似案例"展示（按流体检索），单位换算保证展示一致。

用法：
    python -m logsys.evidence_stack --db data/kb/kb.db --well BET-1 --layers output/BET-1/BET-1_interpretation_layers.csv --unit ft
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

BASE = r'D:\360\src'
DEFAULT_DB = os.path.join(BASE, 'data', 'kb', 'kb.db')
FT_TO_M = 0.3048


def _norm_fluid(x: str) -> str:
    s = str(x or '').upper()
    if s in ('NONRESERVOIR', 'DRY'):
        return 'TIGHT'
    if s in ('GAS_OIL', 'GAS&OIL'):
        return 'MIXED'
    return s


def enrich_layers(conn, well: str, layers: pd.DataFrame, unit: str = 'm',
                  max_cases: int = 2, max_clauses: int = 3) -> pd.DataFrame:
    from .knowledge.evidence import evidence_for  # noqa: F401
    out = layers.copy()
    ev_cases, ev_clauses, ev_conf, ev_sum = [], [], [], []
    for _, r in out.iterrows():
        top = pd.to_numeric(r.get('TOP_MD'), errors='coerce')
        base = pd.to_numeric(r.get('BASE_MD'), errors='coerce')
        if unit.lower() == 'ft':
            top_m, base_m = (top * FT_TO_M) if pd.notna(top) else None, (base * FT_TO_M) if pd.notna(base) else None
        else:
            top_m, base_m = top, base
        try:
            ev = evidence_for(conn, well, float(top_m), float(base_m),
                              _norm_fluid(r.get('INTERPRETATION')))
        except Exception:
            ev = {'cases': [], 'clauses': []}
        cases = ev.get('cases') or []
        clauses = ev.get('clauses') or []
        c_txt = '; '.join('%s %.1f-%.1f %s(%.2f)' % (c['well'], c['top_m'], c['base_m'],
                                                     c['fluid'], c['conf']) for c in cases[:max_cases])
        k_txt = '; '.join(c['std_no'] for c in clauses[:max_clauses])
        conf = (sum(float(c['conf']) for c in cases) / len(cases)) if cases else 0.0
        ev_cases.append(c_txt)
        ev_clauses.append(k_txt)
        ev_conf.append(round(conf, 3))
        ev_sum.append('案例 %d / 条款 %d' % (len(cases), len(clauses)))
    out['EV_CASES'] = ev_cases
    out['EV_CLAUSES'] = ev_clauses
    out['EV_CONF'] = ev_conf
    out['EV_SUMMARY'] = ev_sum
    return out


def enrich_layers_file(db_path: str, well: str, layers_csv: str, unit: str = 'm') -> dict:
    if not os.path.exists(db_path) or not os.path.exists(layers_csv):
        return {'ok': False, 'reason': 'kb.db 或层表不存在', 'rows': 0}
    try:
        from .knowledge.db import connect
        from .knowledge.evidence import evidence_for  # noqa: F401
    except Exception:
        from logsys.knowledge.db import connect  # 兼容直接运行脚本
    try:
        conn = connect(db_path)
    except Exception as e:
        return {'ok': False, 'reason': 'kb 连接失败: %s' % e, 'rows': 0}
    try:
        layers = pd.read_csv(layers_csv)
        if len(layers) == 0:
            return {'ok': True, 'rows': 0}
        enr = enrich_layers(conn, well, layers, unit=unit)
        enr.to_csv(layers_csv, index=False, encoding='utf-8-sig')
        n_cases = int((enr['EV_CASES'].astype(str).str.len() > 0).sum())
        return {'ok': True, 'rows': int(len(enr)), 'rows_with_cases': n_cases,
                'avg_conf': round(float(enr['EV_CONF'].mean()), 3)}
    except Exception as e:
        return {'ok': False, 'reason': '%s: %s' % (type(e).__name__, e), 'rows': 0}


def main(argv=None):
    ap = argparse.ArgumentParser(description='层表证据栈')
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--well', required=True)
    ap.add_argument('--layers', required=True)
    ap.add_argument('--unit', default='m')
    args = ap.parse_args(argv)
    r = enrich_layers_file(args.db, args.well, args.layers, args.unit)
    print(r)
    return 0 if r.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
