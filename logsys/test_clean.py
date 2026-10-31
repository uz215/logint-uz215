# -*- coding: utf-8 -*-
"""数据清洗回归测试（单位归一/非法值/深度处理）。"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'D:\360\src')
from logsys.clean import clean_well  # noqa: E402


def check(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(detail)) if detail else ''))
    return bool(cond)


def main():
    ok = total = 0
    md = np.arange(1000.0, 1020.0)
    n = len(md)

    # 1) CAL mm→in、NPHI 分数→百分、RHOB kg/m3→g/cc、DT us/m→us/ft
    d = pd.DataFrame({'MD': md, 'CAL': np.full(n, 215.9), 'NPHI': np.full(n, 0.25),
                      'RHOB': np.full(n, 2450.0), 'DT': np.full(n, 328.0)})
    c, rep = clean_well(d, context='units')
    total += 1
    ok += check('CAL mm→in', abs(float(c['CAL'].median()) - 8.5) < 0.2, c['CAL'].median())
    total += 1
    ok += check('NPHI fraction→percent', abs(float(c['NPHI'].median()) - 25.0) < 0.5)
    total += 1
    ok += check('RHOB kg/m3→g/cc', abs(float(c['RHOB'].median()) - 2.45) < 0.01)
    total += 1
    ok += check('DT us/m→us/ft', abs(float(c['DT'].median()) - 100.0) < 0.5, c['DT'].median())

    # 2) 非法值 NaN 化（负 GR、超范围密度、负电阻率）
    d2 = pd.DataFrame({'MD': md, 'GR': np.r_[-50.0, np.full(n - 1, 80.0)],
                       'RHOB': np.r_[5.0, np.full(n - 1, 2.4)],
                       'RT': np.r_[-10.0, np.full(n - 1, 10.0)]})
    c2, rep2 = clean_well(d2, context='values')
    total += 1
    ok += check('非法值清理', np.isnan(c2.loc[0, 'GR']) and np.isnan(c2.loc[0, 'RHOB'])
                and np.isnan(c2.loc[0, 'RT']), rep2.get('value_total'))

    # 3) 深度重复/乱序/非正
    d3 = pd.DataFrame({'MD': [1001.0, 1000.0, 1000.0, -5.0, 1002.0],
                       'GR': [1, 2, 3, 4, 5]})
    c3, rep3 = clean_well(d3, context='depth')
    total += 1
    ok += check('深度排序去重去非正', list(c3['MD']) == [1000.0, 1001.0, 1002.0]
                and float(c3.loc[c3['MD'] == 1000.0, 'GR'].iloc[0]) == 3.0,
                (list(c3['MD']), rep3))
    print('\n结果: %d 通过, %d 失败' % (ok, total - ok))
    return 0 if ok == total else 1


if __name__ == '__main__':
    sys.exit(main())
