# -*- coding: utf-8 -*-
"""元素第一岩性/剖面自检：*_QE→VOL_*、元素剖面、砂岩高钙→碳酸盐。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
import logInt
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
n=100
df=pd.DataFrame({
    'MD': np.arange(6000,6000+n),
    'GR': np.full(n, 87.0),
    'CALCITE_QE': np.full(n, 0.62),
    'DOLOMITE_QE': np.full(n, 0.02),
    'SHALE_QE': np.full(n, 0.10),
    'QUARTZ_QE': np.full(n, 0.20),
    'LITHOLOGY': ['sandstone']*n,
})
out=logInt.standardize_curve_names(df, context='element-test')
chk('CALCITE_QE→VOL_CALCITE', 'VOL_CALCITE' in out.columns and abs(out['VOL_CALCITE'].iloc[0]-0.62)<1e-9)
chk('DOLOMITE_QE→VOL_DOLOM', 'VOL_DOLOM' in out.columns)
chk('SHALE_QE→VOL_ILLITE', 'VOL_ILLITE' in out.columns)
chk('QUARTZ_QE→VOL_QUARTZ', 'VOL_QUARTZ' in out.columns)
chk('元素剖面=carbonate', logInt.element_profile_type(out)=='carbonate', logInt.element_profile_type(out))
arb,_=logInt.arbitrate_lithology_by_elements(out.copy())
chk('砂岩高钙→碳酸盐(不只泥岩)', set(arb['LITHOLOGY']) <= {'limestone','dolomite'}, arb['LITHOLOGY'].value_counts().to_dict())
# 泥质高、碳酸盐低 → 不应强改
df2=out.copy(); df2['CALCITE_QE']=0.05; df2['SHALE_QE']=0.70; df2['LITHOLOGY']='sandstone'
out2=logInt.standardize_curve_names(df2, context='element-low')
chk('低钙高泥质不强行碳酸盐', logInt.element_profile_type(out2) in ('sand_shale','', 'mixed'), logInt.element_profile_type(out2))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
