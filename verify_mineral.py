"""验证非储层矿物含量重新分配效果"""
import pandas as pd
import numpy as np

df = pd.read_csv(r'f:\360\src\output\XIMENIA-5\XIMENIA-5_processed.csv')

# 检查NonReservoir点
nr_mask = df['INTERPRETATION'] == 'NonReservoir'
nr_data = df[nr_mask]

# 矿物列
mineral_cols = ['VQuartz', 'VCalcite', 'VDolomite', 'VAnhydrite', 'VHalite', 'VClay']
available = [c for c in mineral_cols if c in df.columns]

print("=" * 60)
print("非储层点矿物含量重新分配验证")
print("=" * 60)
print(f"NonReservoir点数: {nr_mask.sum()}")
print(f"PHI=0: {(nr_data['PHI'] == 0).sum()} / {nr_mask.sum()}")

if available:
    print(f"\n矿物列: {available}")
    nr_minerals = nr_data[available]
    mineral_sum = nr_minerals.sum(axis=1)
    
    print(f"\n矿物总和统计:")
    print(f"  均值: {mineral_sum.mean():.4f}")
    print(f"  最小: {mineral_sum.min():.4f}")
    print(f"  最大: {mineral_sum.max():.4f}")
    print(f"  sum(minerals)=1.0点数: {(mineral_sum.between(0.99, 1.01)).sum()} / {nr_mask.sum()}")
    
    print(f"\n矿物含量均值 (NonReservoir):")
    for col in available:
        print(f"  {col}: {nr_minerals[col].mean():.4f}")
    
    # 检查VSAND和VSH
    if 'VSAND' in df.columns:
        print(f"\nVSAND均值: {nr_data['VSAND'].mean():.4f}")
    if 'VSH' in df.columns:
        print(f"VSH均值: {nr_data['VSH'].mean():.4f}")

# 检查储层点
res_mask = df['INTERPRETATION'].isin(['GAS', 'OIL', 'WATER', 'DRY', 'TIGHT'])
res_data = df[res_mask]
if available and len(res_data) > 0:
    res_minerals = res_data[available]
    res_sum = res_minerals.sum(axis=1)
    res_phi = res_data['PHI']
    total_sum = res_sum + res_phi
    
    print(f"\n{'='*60}")
    print(f"储层点验证 ({res_mask.sum()} points)")
    print(f"{'='*60}")
    print(f"sum(minerals)+PHI统计:")
    print(f"  均值: {total_sum.mean():.4f}")
    print(f"  最小: {total_sum.min():.4f}")
    print(f"  最大: {total_sum.max():.4f}")
    print(f"  ≈1.0点数: {total_sum.between(0.99, 1.01).sum()} / {res_mask.sum()}")

print("\n验证完成!")
