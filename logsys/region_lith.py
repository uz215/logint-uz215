# -*- coding: utf-8 -*-
"""区域岩性规则：按国家/地区约束岩性类别与识别规则。

- 数据：knowledge/region_lithology.json（与条款 LITH-xx 对应）
- 功能：
  * region_of_well(well) → 区域键；
  * allowed_classes(region) → 该区域允许类别；
  * constrain(pred, region) → 把不在允许集内的预测改为 ''（unknown）或最近允许类；
  * summary() → 区域岩性规则表（用于报告/README）。

用户口径（2026-10-31）：
  BET-1 砂泥岩+煤+碳质泥岩+少量钙质泥岩/灰岩；孟加拉砂泥岩；
  111D/巴西碳酸盐岩+盐+硬石膏+玄武岩；乍得/尼日尔砂泥岩（有岩性分析/试油）。
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

BASE = r'D:\360\src'
CFG = os.path.join(BASE, 'logsys', 'knowledge', 'region_lithology.json')

# 井名 → 区域键（可扩展）
WELL_REGION = {
    'BET-1': 'Indonesia/Jabung',
    'RASHIDPUR_13': 'Bangladesh',
    'RP-13': 'Bangladesh',
    '3-SPS-111D': 'Brasil',
    '3-BRSA-1396D-SPS': 'Brasil',
    'XIMENIA-5': 'Chad',
    'XIMENIA S-1': 'Chad',
    'TrakesKE-1': 'Niger',
}


def load_cfg(path: str = CFG) -> dict:
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding='utf-8'))
        except Exception:
            pass
    return {'regions': {}}


def region_of_well(well: str | None) -> str | None:
    if not well:
        return None
    w = str(well).strip().upper()
    for k, reg in WELL_REGION.items():
        if k.upper() == w:
            return reg
    for k, reg in WELL_REGION.items():
        if k.upper() in w or w in k.upper():
            return reg
    return None


def allowed_classes(region: str | None) -> list | None:
    if not region:
        return None
    c = load_cfg()['regions'].get(region)
    if not c:
        return None
    return list(c.get('allowed_classes') or [])


def constrain(pred, region: str | None, mode: str = 'unknown') -> np.ndarray:
    """把不在区域允许集内的预测改为 ''（unknown）或保留（mode='keep'）。"""
    pred = np.asarray(pred, dtype=object)
    allow = allowed_classes(region)
    if not allow:
        return pred
    out = pred.copy()
    bad = ~np.isin(out, allow)
    if mode == 'keep':
        return out
    out[bad] = ''
    return out


def summary() -> pd.DataFrame:
    rows = []
    for reg, c in load_cfg().get('regions', {}).items():
        rows.append({'region': reg, 'wells': ', '.join(c.get('wells') or []),
                     'dominant': ', '.join(c.get('dominant_lithology') or []),
                     'allowed': ', '.join(c.get('allowed_classes') or []),
                     'notable': '；'.join(c.get('notable') or []),
                     'source': c.get('source', '')})
    return pd.DataFrame(rows)


def main(argv=None):
    print(summary().to_string(index=False))
    return 0


if __name__ == '__main__':
    import sys as _sys
    _sys.exit(main())
