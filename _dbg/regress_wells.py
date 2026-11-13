# -*- coding: utf-8 -*-
"""回归测试：XIMENIA-5(砂泥岩) 与 3-SPS-111D(碳酸盐) 岩性识别，确认 SPS-108 修复无回归。
注意：本次 _rule_match 改动仅在曲线缺失(v=None)时改变行为；曲线齐全时应与原逻辑一致。
"""
import logging
logging.disable(logging.CRITICAL)
import os, sys
import numpy as np
import pandas as pd
import lasio

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from logInt import (LithologyRecognizer, standardize_curve_names,
                    sanitize_null_markers, reconcile_vsh_with_gr,
                    detect_well_profile_type)

WELLS = [
    ("XIMENIA-5", "F:/360/src/data/Ximenia 5-all_test.LAS", True),
    ("3-SPS-111D", "F:/360/src/data/3-sps-111d_lqc.las", True),
]

for name, path, pe_rel in WELLS:
    try:
        las = lasio.read(path)
        df = las.df().reset_index()
        df.columns = [str(c).upper() for c in df.columns]
        df = standardize_curve_names(df, os.path.basename(path))
        df = sanitize_null_markers(df)
        df = reconcile_vsh_with_gr(df)
        if 'MD' not in df.columns:
            for c in ('DEPT', 'DEPTH', 'TDEP'):
                if c in df.columns:
                    df = df.rename(columns={c: 'MD'})
                    break
        _prof = detect_well_profile_type(df, name)
        prof = _prof[0] if isinstance(_prof, tuple) else _prof
        rec = LithologyRecognizer(df, depth_unit='m', pe_reliable=pe_rel,
                                 profile_type=prof, neutron_reliable=True)
        rec.recognize()
        lith = pd.Series(np.asarray(rec.lith).ravel())
        print("\n=== %s  (profile=%s, PE可信=%s) ===" % (name, prof, pe_rel))
        for k, v in lith.value_counts(dropna=False).items():
            print("  %-18s %7d (%.1f%%)" % (str(k), v, 100.0 * v / len(lith)))
    except Exception as e:
        import traceback
        print("\n=== %s 出错 ===" % name)
        traceback.print_exc()
