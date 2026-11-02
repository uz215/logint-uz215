# -*- coding: utf-8 -*-
"""层段构建器自检（无需 pytest）。"""
import sys

import numpy as np
import pandas as pd

from .layers import build_layers

PASS, FAIL = [], []


def check(n, c, d=''):
    (PASS if c else FAIL).append(n)
    print(('  PASS  ' if c else '  FAIL  ') + n + ('' if c else '  ' + str(d)))


def main():
    md = np.arange(1000.0, 1020.0, 0.5)  # 40 点
    d = pd.DataFrame({'MD': md})
    d['INTERPRETATION'] = 'OIL'
    d.loc[d['MD'] < 1005, 'INTERPRETATION'] = 'NonReservoir'
    d.loc[(d['MD'] >= 1005) & (d['MD'] < 1010), 'INTERPRETATION'] = 'OIL'
    d.loc[(d['MD'] >= 1010) & (d['MD'] < 1015), 'INTERPRETATION'] = 'WATER'
    d.loc[d['MD'] >= 1015, 'INTERPRETATION'] = 'GAS'
    d['LITHOLOGY'] = np.where(d['INTERPRETATION'] == 'NonReservoir', 'shale', 'sandstone')
    d['PHI'] = 0.2
    d['Sw'] = np.where(d['INTERPRETATION'].isin(['OIL', 'GAS']), 0.3, 0.9)
    d['RT'] = 20.0

    lay = build_layers(d, min_thick=0.4, thin_absorb=0.6, gap_break=0.5)
    print(lay[['LAYER_ID', 'TOP_MD', 'BASE_MD', 'THICKNESS', 'INTERPRETATION',
               'LITHOLOGY', 'POINTS', 'SW_MEAN', 'REVIEW_FLAG']].to_string())
    check('层数=3（OIL/WATER/GAS）', len(lay) == 3, len(lay))
    check('层序正确', list(lay['INTERPRETATION']) == ['OIL', 'WATER', 'GAS'], list(lay['INTERPRETATION']))
    check('厚度=5m', all(abs(lay['THICKNESS'] - 5.0) < 1e-6), lay['THICKNESS'].tolist())
    check('OIL 层 SW_MEAN=0.3', abs(lay.iloc[0]['SW_MEAN'] - 0.3) < 1e-6, lay.iloc[0]['SW_MEAN'])
    check('WATER 层 SW_MEAN=0.9', abs(lay.iloc[1]['SW_MEAN'] - 0.9) < 1e-6, lay.iloc[1]['SW_MEAN'])
    check('岩性=砂岩', all(lay['LITHOLOGY'] == 'sandstone'), lay['LITHOLOGY'].tolist())

    # 薄层：0.5m（2点）夹在 OIL 中、流体族不同 → 不合并，标 THIN
    md2 = np.arange(2000.0, 2010.0, 0.5)
    d2 = pd.DataFrame({'MD': md2, 'INTERPRETATION': 'OIL'})
    d2.loc[(d2['MD'] >= 2004) & (d2['MD'] < 2004.5), 'INTERPRETATION'] = 'WATER'
    lay2 = build_layers(d2, thin_absorb=0.6)
    print(lay2[['LAYER_ID', 'TOP_MD', 'BASE_MD', 'THICKNESS', 'INTERPRETATION', 'REVIEW_FLAG']].to_string())
    check('跨族薄水层不被油层吞并', len(lay2) == 3, len(lay2))
    check('薄层标 THIN', 'THIN' in str(lay2.iloc[1]['REVIEW_FLAG']), lay2.iloc[1]['REVIEW_FLAG'])

    # 同族薄层：0.5m OIL 夹在 OIL 中 → 合并
    d3 = d2.copy()
    d3['INTERPRETATION'] = 'OIL'
    d3.loc[(d3['MD'] >= 2004) & (d3['MD'] < 2004.5), 'INTERPRETATION'] = 'GAS'
    lay3 = build_layers(d3, thin_absorb=0.6)
    check('同族(油/气同族?)不同族不合并——油与气分族', len(lay3) == 3, len(lay3))

    # 空数据
    check('空输入返回空表', len(build_layers(pd.DataFrame())) == 0)
    check('缺 INTERPRETATION 返回空表', len(build_layers(pd.DataFrame({'MD': [1.0]}))) == 0)

    print('\n结果: %d 通过, %d 失败' % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
