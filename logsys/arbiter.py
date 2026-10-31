# -*- coding: utf-8 -*-
"""解释结论单一裁决（一处确定，不能多头）。

候选：
  - rules 层表：<井>_interpretation_layers_rules.csv（规则法）
  - ML 层表：  <井>_interpretation_layers_ML.csv（井内标定模型，如存在）
唯一成果：
  - canonical：<井>_interpretation_layers.csv（由裁决层复制）
  - 决策：    <井>_interpretation_decision.json（来源/策略/候选/置信度/时间）

策略（一处配置：<井>info.json 的「解释来源」）：
  - 'rules'：强制规则法
  - 'ML'   ：强制井内 ML
  - 'auto'（缺省）：有 ML 模型且其验证精度 ≥ min_cv（默认 0.80）→ ML，否则 rules
"""
from __future__ import annotations

import json
import os
import shutil
import time

import pandas as pd

DEFAULT_MIN_CV = 0.80


def _read_json(p: str) -> dict:
    try:
        return json.load(open(p, encoding='utf-8')) if p and os.path.exists(p) else {}
    except Exception:
        return {}


def _rows(p: str) -> int:
    try:
        return int(len(pd.read_csv(p)))
    except Exception:
        return 0


def model_cv(ml_layers_path: str | None) -> float | None:
    """从 ML 层表路径推断模型 JSON（data/calibration/models/<井>.json）读 cv5。"""
    if not ml_layers_path:
        return None
    try:
        base = os.path.basename(ml_layers_path)
        well = base.replace('_interpretation_layers_ML.csv', '')
        mp = os.path.join(r'D:\360\src', 'data', 'calibration', 'models', well + '.json')
        if os.path.exists(mp):
            d = _read_json(mp)
            for k in ('cv5_acc', 'cv5_layer', 'layer_acc', 'cv5'):
                if d.get(k) is not None:
                    return float(d[k])
    except Exception:
        pass
    return None


def choose(well: str, out_dir: str, info: dict | None = None,
           ml_available: bool = False, ml_layers: str | None = None,
           min_cv: float = DEFAULT_MIN_CV) -> dict:
    info = info or {}
    policy = str(info.get('解释来源') or 'auto').strip()
    cv = model_cv(ml_layers) if ml_available else None
    if policy.lower() in ('rules', '规则'):
        src, reason = 'rules', '配置强制规则法'
    elif policy.lower() in ('ml', '机器学习'):
        src, reason = ('ML' if ml_available else 'rules'), (
            '配置强制ML' if ml_available else '配置强制ML但无模型→回退规则')
    else:
        if ml_available and (cv is None or cv >= min_cv):
            src, reason = 'ML', 'auto: 有模型(%s) → ML' % (
                'cv=%.3f' % cv if cv is not None else 'cv未知按可用')
        else:
            src, reason = 'rules', 'auto: 无模型或验证精度不足(%s) → rules' % (
                'cv=%.3f' % cv if cv is not None else '无模型')
    return {'well': well, 'policy': policy, 'chosen': src, 'reason': reason,
            'model_cv': cv, 'ml_available': bool(ml_available)}


def finalize(out_dir: str, well: str, rule_csv: str | None, ml_csv: str | None,
             decision: dict) -> dict:
    """复制裁决结果到 canonical，写决策 JSON，返回结果字典。"""
    os.makedirs(out_dir, exist_ok=True)
    canonical = os.path.join(out_dir, str(well) + '_interpretation_layers.csv')
    chosen_csv = ml_csv if decision.get('chosen') == 'ML' else rule_csv
    copied = False
    if chosen_csv and os.path.exists(chosen_csv):
        shutil.copyfile(chosen_csv, canonical)
        copied = True
    dec = dict(decision)
    dec.update({
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'rule_layers': rule_csv, 'ml_layers': ml_csv,
        'rule_rows': _rows(rule_csv) if rule_csv else 0,
        'ml_rows': _rows(ml_csv) if ml_csv else 0,
        'canonical': canonical if copied else None,
        'canonical_rows': _rows(canonical) if copied else 0,
    })
    dp = os.path.join(out_dir, str(well) + '_interpretation_decision.json')
    json.dump(dec, open(dp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    dec['decision_path'] = dp
    return dec
