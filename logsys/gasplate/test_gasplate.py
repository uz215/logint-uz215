# -*- coding: utf-8 -*-
"""气测图版引擎自检（无需 pytest，直接运行：python -m logsys.gasplate.test_gasplate）。

覆盖：
1) Pixler 图版分带（图版锚点样品：红/黄/褐/兰）
2) 真实样品（Curacao-1，烃比值图版.xls Sheet7 6309.00 m）
3) 轻重烃比值 / 乙烷甲烷比值（与图版 Excel 计算值 2.98 / 18.46 对齐）
4) 缺重烃 → UNDEFINED（不误判为油）
5) 按层聚合（GAS/OIL 两段）
6) 图版 × 测井融合（含"无气测不得强制降油"）
"""
from __future__ import annotations

import sys

import pandas as pd

from . import engine, methods

PASS, FAIL = [], []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print(f'  PASS  {name}')
    else:
        FAIL.append((name, detail))
        print(f'  FAIL  {name}  {detail}')


def sample(c1, c2, c3, ic4=0.0, nc4=0.0, ic5=0.0, nc5=0.0):
    return pd.DataFrame([{'C1': c1, 'C2': c2, 'C3': c3, 'IC4': ic4, 'NC4': nc4,
                          'IC5': ic5, 'NC5': nc5}])


def main():
    cfg = engine.load_config()
    print('config version:', cfg['meta']['version'])

    # 1) Pixler 锚点样品（气测解释图版.xls 行 6-9：红/黄/褐/兰）
    anchors = {
        'red':   sample(85.69, 9.03, 4.28, 0.28, 0.72),
        'yellow': sample(74.65, 14.14, 7.66, 0.73, 2.54),
        'brown': sample(72.18, 13.97, 9.11, 0.90, 3.44),
        'blue':  sample(76.21, 11.66, 8.34, 0.99, 1.81),
    }
    got = {k: engine.evaluate_points(v, cfg)['PLATE_FLUID'].iloc[0] for k, v in anchors.items()}
    print('  锚点判别:', got)
    check('Pixler 红样判 GAS', got['red'] == 'GAS', got['red'])
    check('Pixler 黄/褐/蓝判 OIL', got['yellow'] == got['brown'] == got['blue'] == 'OIL', got)

    # 2) 真实样品 Curacao-1 6309 m（Sheet7）
    c = sample(6421, 351, 92, 13, 17, 9, 4)
    r = engine.evaluate_points(c, cfg)
    print('  Curacao ratios: %.2f / %.2f / %.2f' % (
        r['PLATE_C1_C2'].iloc[0], r['PLATE_C1_C3'].iloc[0], r['PLATE_C1_C4'].iloc[0]))
    check('Curacao 判 GAS（2/3 比值落气区）', r['PLATE_FLUID'].iloc[0] == 'GAS',
          r['PLATE_FLUID'].iloc[0])
    check('Curacao 置信度 < 0.95（非三项全中）', 0 < r['PLATE_CONF'].iloc[0] < 0.95,
          str(r['PLATE_CONF'].iloc[0]))

    # 3) 比值法（与图版 Excel 计算值对齐：2.98 与 18.46）
    heavy = methods.ratio_c1_heavy(anchors['yellow'], cfg).iloc[0]
    c2c3 = methods.ratio_c2c3(anchors['yellow'], cfg).iloc[0]
    print('  ratio_c1_heavy=%s  ratio_c2c3=%s' % (heavy, c2c3))
    check('轻重烃比 = 与油有关的天然气', heavy == '与油有关的天然气', str(heavy))
    check('乙烷甲烷比 = 伴生气→油', c2c3 == '伴生气→油', str(c2c3))

    # 4) 缺重烃 → UNDEFINED（不得误判为油）
    only_c1 = pd.DataFrame([{'C1': 1000.0, 'C2': None, 'C3': None}])
    r2 = engine.evaluate_points(only_c1, cfg)
    check('缺 C2/C3 → UNDEFINED', r2['PLATE_FLUID'].iloc[0] == 'UNDEFINED',
          r2['PLATE_FLUID'].iloc[0])

    # 5) 按层聚合
    rows = []
    for i in range(20):
        md = 1000.0 + i * 0.5
        if md < 1005:
            # 比例 20 / 50 / 166.7 → Pixler 三项全落气区
            rows.append({'MD': md, 'C1': 1000, 'C2': 50, 'C3': 20, 'IC4': 3, 'NC4': 3})
        else:
            # 比例 5 / 10 / 16.7 → Pixler 三项全落油区
            rows.append({'MD': md, 'C1': 1000, 'C2': 200, 'C3': 100, 'IC4': 30, 'NC4': 30})
    gas_df = pd.DataFrame(rows)
    lay = engine.evaluate_layers(gas_df, [(1000.0, 1005.0), (1005.0, 1010.0)], cfg)
    print('  分层结果:', lay[['TOP', 'BASE', 'PLATE_FLUID', 'PLATE_CONF', 'POINTS']].to_dict('records'))
    check('层1 判 GAS', lay.iloc[0]['PLATE_FLUID'] == 'GAS', lay.iloc[0]['PLATE_FLUID'])
    check('层2 判 OIL', lay.iloc[1]['PLATE_FLUID'] == 'OIL', lay.iloc[1]['PLATE_FLUID'])
    check('每层点数=10', int(lay.iloc[0]['POINTS']) == 10)

    # 6) 与测井融合
    f1 = engine.fuse_with_log('OIL', 'GAS', cfg)
    f2 = engine.fuse_with_log('GAS', 'OIL', cfg)
    f3 = engine.fuse_with_log('UNDEFINED', 'GAS', cfg)
    f4 = engine.fuse_with_log('DRY', 'GAS', cfg)
    check('图版 OIL 不再降级（保留 GAS + 冲突标记）',
          f1['final'] == 'GAS' and f1['flag'] == 'PLATE_OIL_CONFLICT', str(f1))
    check('图版 GAS 可提升 OIL→GAS', f2['final'] == 'GAS' and f2['action'] == 'promote_gas', str(f2))
    check('图版无依据：保留 GAS 且标 NO_GAS_DATA（不强制降油）',
          f3['final'] == 'GAS' and f3['flag'] == 'NO_GAS_DATA', str(f3))
    check('图版 DRY：保留结论并标 NO_GAS_SHOW', f4['final'] == 'GAS' and f4['flag'] == 'NO_GAS_SHOW', str(f4))

    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        for n, d in FAIL:
            print('  -', n, d)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
