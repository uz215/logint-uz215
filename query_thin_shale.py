# -*- coding: utf-8 -*-
"""重新验证 processed.csv 中 1102.4-1103.3m 的数据"""
import pandas as pd
import numpy as np

csv_path = r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv'
df = pd.read_csv(csv_path)
print(f'总行数: {len(df)}, 深度范围: {df["MD"].min()} - {df["MD"].max()}')

cols = ['MD', 'VQuartz', 'VClay', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite',
        'PHI', 'VALID_CURVES_COUNT', 'LITHOLOGY', '_POROSITY_VALID']
cols = [c for c in cols if c in df.columns]

sub = df[(df['MD'] >= 1101.5) & (df['MD'] <= 1104.0)][cols]
pd.set_option('display.max_rows', 100)
pd.set_option('display.width', 200)
print(sub.to_string())
