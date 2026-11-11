# -*- coding: utf-8 -*-
"""SPS-108 岩性识别修复验证（无头）。
用真实 processed.csv 曲线 + LWD DTCO 并回 DT，验证修复 A/B 后碳酸盐能否正确识别。
"""
import logging
logging.disable(logging.CRITICAL)
import os
import sys
import numpy as np
import pandas as pd
import lasio

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import logInt
from logInt import LithologyRecognizer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..")
PROC = os.path.join(SRC, "output", "1-SPS-108", "1-SPS-108_processed.csv")
LWD = os.path.join(SRC, "data", "1-SPS-108_DDP_LWD-rt_8_GR-RES-SON-NMR_campo.las")

# ---- 1. 载入 processed.csv，重命名为标准名 ----
df = pd.read_csv(PROC)
ren = {"RHOB": "DEN", "NPOR": "CNL", "GR_EDTC": "GR", "PE": "PE",
       "CAL": "CAL", "RT": "RT"}
sub = df[["MD"]].copy()
for src_c, std in ren.items():
    if src_c in df.columns:
        sub[std] = pd.to_numeric(df[src_c], errors="coerce")

# ---- 2. 从 LWD 并回 DT（模拟 DLIS sonic 被提取）----
try:
    las = lasio.read(LWD)
    lwd = las.df().reset_index()
    lwd.columns = [c.upper() for c in lwd.columns]
    if "DTCO" in lwd.columns and "DEPT" in lwd.columns:
        lwd2 = lwd[["DEPT", "DTCO"]].copy()
        lwd2["DTCO"] = pd.to_numeric(lwd2["DTCO"], errors="coerce")
        lwd2 = lwd2.dropna(subset=["DEPT", "DTCO"])
        lwd2 = lwd2[lwd2["DTCO"] > -900]
        sub = pd.merge_asof(
            sub.sort_values("MD"),
            lwd2.rename(columns={"DEPT": "MD", "DTCO": "DT"}).sort_values("MD"),
            on="MD", direction="nearest")
        sub = sub.sort_values("MD").reset_index(drop=True)
        print("DT 合并：非空点数 = %d / %d" % (sub["DT"].notna().sum(), len(sub)))
    else:
        print("LWD 无 DTCO/DEPT")
except Exception as e:
    import traceback
    traceback.print_exc()

print("构造数据列:", list(sub.columns))
print("DEN 中位=%.3f  CNL 中位=%.3f  GR 中位=%.1f  RT 中位=%.1f  PE 中位=%.2f"
      % (sub["DEN"].median(), sub["CNL"].median(), sub["GR"].median(),
         sub["RT"].median(), sub["PE"].median()))


def run(profile, with_dt):
    d = sub.copy()
    if not with_dt and "DT" in d.columns:
        d = d.drop(columns=["DT"])
    rec = LithologyRecognizer(d, depth_unit="m", pe_reliable=False,
                              profile_type=profile, neutron_reliable=True)
    rec.recognize()
    # 取结果
    lith = getattr(rec, "lith", None)
    if lith is None:
        for c in rec.raw.columns:
            if "LITH" in c.upper():
                lith = rec.raw[c]
                break
    if lith is None:
        print("  [%s|DT=%s] 未找到岩性结果列; rec attrs=%s"
              % (profile, with_dt, [a for a in dir(rec) if 'lith' in a.lower()]))
        return
    ser = pd.Series(np.asarray(lith).ravel())
    vc = ser.value_counts(dropna=False)
    print("\n=== profile=%s  with_dt=%s  PE不可信 ===" % (profile, with_dt))
    for k, v in vc.items():
        print("  %-18s %6d (%.1f%%)" % (str(k), v, 100.0 * v / len(ser)))


for pt in ("mixed", "carbonate", "sand_shale"):
    run(pt, with_dt=True)
    run(pt, with_dt=False)
