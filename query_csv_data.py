# -*- coding: utf-8 -*-
"""查询 processed.csv 中关键深度段的 LITHOLOGY/PHI/VClay 等数据"""
import pandas as pd
import numpy as np

df = pd.read_csv(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv')
print("列名:", list(df.columns))
print("MD范围:", df['MD'].min(), "-", df['MD'].max(), "行数:", len(df))

def show_range(d0, d1):
    sub = df[(df['MD'] >= d0) & (df['MD'] <= d1)]
    if len(sub) == 0:
        print(f"\n=== {d0}-{d1}m: 无数据 ===")
        return
    print(f"\n=== {d0}-{d1}m: {len(sub)} 点 ===")
    cols = [c for c in ['MD', 'LITHOLOGY', 'PHI', 'VQuartz', 'VClay', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite', 'VALID_CURVES_COUNT', '_POROSITY_VALID'] if c in df.columns]
    print(sub[cols].to_string(index=False))

show_range(1100, 1110)
show_range(1195, 1225)
show_range(1295, 1305)
show_range(1360, 1378)
show_range(2700, 2725)

# 统计 LITHOLOGY 分布
print("\n=== LITHOLOGY 全井段分布 ===")
print(df['LITHOLOGY'].value_counts())

# 统计非储层（PHI<=1e-10）且 LITHOLOGY=shale 的段
nonres = df[df['PHI'] <= 1e-10]
print(f"\n=== 非储层点总数: {len(nonres)} ===")
print(nonres['LITHOLOGY'].value_counts())

# 检查 2700-2720m 是否泥岩（大图 y=10500 附近 ≈2714m）
sub = df[(df['MD'] >= 2700) & (df['MD'] <= 2720)]
if len(sub) > 0:
    print("\n=== 2700-2720m 采样（每5点） ===")
    print(sub[::5].to_string(index=False))
