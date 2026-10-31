# -*- coding: utf-8 -*-
"""RT 回退规则回归测试（用户 2026-10-31）：

1) 无 RT 时用深电阻率/最深阵列：LLD 优先（本井 XIMENIA-5 以 LLD 作 RT）；
2) 无 RT 但有 RD → RT 用 RD；
3) 只有浅电阻率（LLS/MSFL/RS）→ **不**派生 RT（避免 Sw 失真）；
4) 已有 RT → 不改动。
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'D:\360\src')
import logInt  # noqa: E402
from logInt import ensure_rt_from_deep  # noqa: E402


def check(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(detail)) if detail else ''))
    return bool(cond)


def main():
    ok = total = 0
    n = 20
    md = np.arange(1000, 1000 + n, 1.0)

    # 1) LLD only → RT = LLD
    d = pd.DataFrame({'MD': md, 'GR': np.full(n, 60.0),
                      'LLD': np.linspace(10, 30, n), 'LLS': np.linspace(8, 12, n),
                      'MSFL': np.linspace(5, 7, n)})
    out = ensure_rt_from_deep(d, context='test-LLD')
    total += 1
    ok += check('无 RT 时 LLD 派生 RT', 'RT' in out.columns and np.allclose(out['RT'], out['LLD']), list(out.columns))
    total += 1
    ok += check('LD 不被 LLS 顶替', not np.allclose(out['RT'], out['LLS']))

    # 2) RD（深）→ RT = RD
    d2 = pd.DataFrame({'MD': md, 'GR': np.full(n, 60.0), 'RD': np.linspace(20, 40, n),
                       'RS': np.linspace(10, 15, n)})
    out2 = ensure_rt_from_deep(d2, context='test-RD')
    total += 1
    ok += check('无 LLD 时 RD 派生 RT', 'RT' in out2.columns and np.allclose(out2['RT'], out2['RD']))

    # 3) 只有浅电阻率 → 不派生 RT
    d3 = pd.DataFrame({'MD': md, 'GR': np.full(n, 60.0),
                       'LLS': np.linspace(5, 8, n), 'MSFL': np.linspace(3, 5, n)})
    out3 = ensure_rt_from_deep(d3, context='test-shallow')
    total += 1
    ok += check('仅浅电阻率不派生 RT', 'RT' not in out3.columns, list(out3.columns))

    # 4) 已有 RT → 不改
    d4 = pd.DataFrame({'MD': md, 'GR': np.full(n, 60.0), 'RT': np.full(n, 99.0),
                       'LLD': np.linspace(10, 30, n)})
    out4 = ensure_rt_from_deep(d4, context='test-existing')
    total += 1
    ok += check('已有 RT 不改动', np.allclose(out4['RT'], 99.0))

    # 5) 阵列最深：AT90 优先于 AT60（无 RD/LLD 时）
    d5 = pd.DataFrame({'MD': md, 'GR': np.full(n, 60.0),
                       'AT90': np.linspace(30, 50, n), 'AT60': np.linspace(20, 30, n)})
    out5 = ensure_rt_from_deep(d5, context='test-array')
    total += 1
    ok += check('最深阵列 AT90 优先', 'RT' in out5.columns and np.allclose(out5['RT'], out5['AT90']))

    print('\n结果: %d 通过, %d 失败' % (ok, total - ok))
    return 0 if ok == total else 1


if __name__ == '__main__':
    sys.exit(main())
