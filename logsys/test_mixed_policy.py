# -*- coding: utf-8 -*-
"""油气同层策略回归测试（用户 2026-10-31 定案）：

1) 单点混合（无法分上下）→ **保留 GAS_OIL + SINGLE_POINT**（不强行改 GAS/OIL）；
2) ≥2 点连续混合段 → 按气测证据拆为 GAS(上) + OIL(下)，无梯度按中点并标 INFERRED；
3) 油水同层（OIL_WATER）不在本模块拆分（保留混合类）。
"""
import sys

import pandas as pd

sys.path.insert(0, r'D:\360\src')
from logsys.mixed_split import split_gas_oil  # noqa: E402


def check(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(detail)) if detail else ''))
    return bool(cond)


def main():
    ok = 0
    total = 0

    # 1) 单点混合：保留 GAS_OIL + SINGLE_POINT
    d = pd.DataFrame({'MD': [1000.0], 'INTERPRETATION': ['GAS_OIL'],
                      'PLATE_FLUID': ['GAS'], 'TG': [9000]})
    r = split_gas_oil(d)
    total += 1
    ok += check('单点混合保留 GAS_OIL', d['INTERPRETATION'].iloc[0] == 'GAS_OIL', d['INTERPRETATION'].tolist())
    total += 1
    ok += check('单点混合标记 SINGLE_POINT', d['GAS_OIL_SPLIT'].iloc[0] == 'SINGLE_POINT', d['GAS_OIL_SPLIT'].tolist())

    # 2) 连续段：气上油下
    d2 = pd.DataFrame({'MD': [2000, 2000.5, 2001, 2001.5],
                       'INTERPRETATION': ['GAS_OIL'] * 4,
                       'PLATE_FLUID': ['GAS', 'GAS', 'OIL', 'OIL'],
                       'TG': [9000, 12000, 4000, 3500]})
    r2 = split_gas_oil(d2)
    total += 1
    ok += check('连续段拆成 2 段', r2['splits'] == 1, r2)
    labels = d2['INTERPRETATION'].tolist()
    total += 1
    ok += check('气在上', labels[:2] == ['GAS', 'GAS'], labels)
    total += 1
    ok += check('油在下', labels[2:] == ['OIL', 'OIL'], labels)
    total += 1
    ok += check('顺序标记 GAS_ABOVE_OIL', (d2['FLUID_MIX_ORDER'] == 'GAS_ABOVE_OIL').all())

    # 3) 无梯度：中点拆分 + INFERRED
    d3 = pd.DataFrame({'MD': [3000, 3000.5, 3001, 3001.5],
                       'INTERPRETATION': ['GAS_OIL'] * 4})
    r3 = split_gas_oil(d3)
    total += 1
    ok += check('无梯度按中点拆且标 INFERRED',
                r3['inferred'] == 1 and d3['GAS_OIL_SPLIT'].iloc[0] == 'INFERRED', r3)

    # 4) 油水同层不在此拆分
    d4 = pd.DataFrame({'MD': [4000, 4000.5], 'INTERPRETATION': ['OIL_WATER'] * 2})
    r4 = split_gas_oil(d4)
    total += 1
    ok += check('OIL_WATER 保持混合类', (d4['INTERPRETATION'] == 'OIL_WATER').all())

    print('\n结果: %d 通过, %d 失败' % (ok, total - ok))
    return 0 if ok == total else 1


if __name__ == '__main__':
    sys.exit(main())
