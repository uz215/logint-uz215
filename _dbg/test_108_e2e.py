# -*- coding: utf-8 -*-
"""SPS-108 端到端岩性修复验证：直接用 DLIS 跑完整 load_data 后处理 + 识别器。"""
import logging
logging.disable(logging.CRITICAL)
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import logInt
from logint.dlis_tool import DlisTool
from logInt import (LithologyRecognizer, standardize_curve_names,
                    sanitize_null_markers, reconcile_vsh_with_gr,
                    detect_well_profile_type)

DLIS = "F:/360/data/uploads/1-SPS-108_all.dlis"

# 1. DLIS 读取（修复后）
raw, info = DlisTool().load_dlis(DLIS)
print("DLIS 提取行数:", len(raw), "列数:", len(raw.columns))

# 2. 复现 load_data 后处理
df = raw.copy()
df.columns = [str(c).upper() for c in df.columns]
ctx = os.path.basename(DLIS)
df = standardize_curve_names(df, context=ctx)
print("标准化后列(部分):", [c for c in df.columns if c in
      ('DT', 'DEN', 'CNL', 'GR', 'PE', 'RT', 'CAL', 'VOL_CALCITE', 'VOL_DOLOM')])
df = sanitize_null_markers(df)
df = reconcile_vsh_with_gr(df)
# load_data 会把深度列统一改名 MD（recognize 取 self.raw['MD']）
if 'MD' not in df.columns and 'DEPTH' in df.columns:
    df = df.rename(columns={'DEPTH': 'MD'})

# 3. 剖面判定
try:
    _prof = detect_well_profile_type(df, "1-SPS-108")
    profile = _prof[0] if isinstance(_prof, tuple) else _prof
except Exception as e:
    profile = "mixed"
    print("profile detect err:", e)
print("剖面类型:", profile)

# 4. PE 可靠性（用户明确 PE 不可信；数据 max 坏道）
pe_reliable = False
print("PE 中位=%.2f  非空=%d" % (df['PE'].median() if 'PE' in df.columns else float('nan'),
      df['PE'].notna().sum() if 'PE' in df.columns else 0))

# 5. 识别器
rec = LithologyRecognizer(df, depth_unit="m", pe_reliable=pe_reliable,
                         profile_type=profile, neutron_reliable=True)
rec.recognize()
lith = np.asarray(rec.lith).ravel()
ser = pd.Series(lith)
print("\n=== SPS-108 岩性分布 (DLIS 端到端, PE不可信, profile=%s) ===" % profile)
for k, v in ser.value_counts(dropna=False).items():
    print("  %-18s %7d (%.1f%%)" % (str(k), v, 100.0 * v / len(ser)))

# 6. 抽查若干深度
print("\n抽查 (深度, 岩性, DEN, DT, CNL, GR, RT, VOL_CALCITE):")
md = df['DEPTH'] if 'DEPTH' in df.columns else pd.Series(range(len(df)))
cols = [c for c in ('DEN', 'DT', 'CNL', 'GR', 'RT', 'VOL_CALCITE') if c in df.columns]
for idx in (int(len(df) * f) for f in (0.1, 0.3, 0.5, 0.7, 0.9)):
    row = df.iloc[idx]
    vals = " ".join("%s=%.2f" % (c, row[c]) for c in cols if pd.notna(row[c]))
    print("  MD=%.1f  %-12s %s" % (md.iloc[idx], str(lith[idx]), vals))
