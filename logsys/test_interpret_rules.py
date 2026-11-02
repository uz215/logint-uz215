# -*- coding: utf-8 -*-
"""解释规则回归测试（用户 2026-10-31 定案）：

1) 水层 = 高 Sw（Sw≥0.65），**不要求 RT 低**（高阻水层同样判水）；
2) 干层 = 低孔储层（POR≥截止值且 <水层孔渗下限），非水（Sw<0.65），**RT 不是判据**；
3) 截止值以下（POR<0.06）不解释（None）；
4) 油气层仍按 Sw/RT 判（Sw<0.5 & RT 门槛）。
"""
import sys

sys.path.insert(0, r'D:\360\src')
from logInt import match_interpretation_rules  # noqa: E402


def check(name, got, exp):
    ok = (got == exp)
    print(('  PASS  ' if ok else '  FAIL  ') + name + ' | got=%r exp=%r' % (got, exp))
    return ok


def main():
    cases = [
        ('高Sw高阻水层(Sw0.8,POR0.15,RT100)', 0.8, 0.15, 100, 'WATER'),
        ('低孔非水干层(Sw0.6,POR0.08,RT80)', 0.6, 0.08, 80, 'DRY'),
        ('低孔高Sw水层(Sw0.8,POR0.08,RT50)', 0.8, 0.08, 50, 'WATER'),
        ('截止值以下不解释(Sw0.4,POR0.04,RT80)', 0.4, 0.04, 80, None),
        ('高孔油层(Sw0.3,POR0.15,RT40)', 0.3, 0.15, 40, 'OIL'),
        ('高孔过渡带无规则(Sw0.6,POR0.15,RT40)', 0.6, 0.15, 40, None),
        ('高孔气层(Sw0.3,POR0.15,RT100)', 0.3, 0.15, 100, 'GAS'),
    ]
    ok = 0
    for name, sw, phi, rt, exp in cases:
        r = match_interpretation_rules(sw, phi, rt)
        ok += check(name, (r[0] if r else None), exp)
    print('\n结果: %d 通过, %d 失败' % (ok, len(cases) - ok))
    return 0 if ok == len(cases) else 1


if __name__ == '__main__':
    sys.exit(main())
