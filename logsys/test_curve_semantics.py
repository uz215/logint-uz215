# -*- coding: utf-8 -*-
"""LAS 注释语义识别自检：Gamma Ray/Caliper/Bit size → GR/CAL/BS。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
import logInt
from logInt import parse_las_semantics_raw, standardize_curve_names
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
LQC=r'D:\360\Brasil\Curacao-1\LQC.las'
sem=parse_las_semantics_raw(LQC)
chk('TLFamily GR_EDTC=Gamma Ray', sem['families'].get('GR_EDTC','').lower().startswith('gamma ray'), str(sem['families'].get('GR_EDTC')))
chk('TLFamily CALC1=Caliper', sem['families'].get('CALC1','').lower()=='caliper', str(sem['families'].get('CALC1')))
chk('BS 参数含 8.5', any(abs(v-8.5)<1e-6 for _,v in sem['bit_sizes']), str(sem['bit_sizes']))
chk('BS6=8.5(最后/最小)', abs(min(v for _,v in sem['bit_sizes'])-8.5)<1e-6)
# 合成数据
n=20
df=pd.DataFrame({
 'CALC1':[8.6]*n, 'CALC3':[np.nan]*n, 'CALC5':[np.nan]*n,
 'GR_EDTC':[45.0]*n, 'GRN':[np.nan]*n,
})
df.loc[5:10,'CALC1']=np.nan; df.loc[5:10,'CALC3']=8.7; df.loc[5:10,'GR_EDTC']=np.nan; df.loc[5:10,'GRN']=46
desc={'CALC1':{'desc':'','family':'Caliper'},'CALC3':{'desc':'','family':'Caliper'},'CALC5':{'desc':'','family':'Caliper'},
      'GR_EDTC':{'desc':'GR_EDTC_1 Depth Shifted','family':'Gamma Ray'},'GRN':{'desc':'','family':'Gamma Ray Normalized'}}
out=standardize_curve_names(df, context='test', descriptions=desc, bit_sizes=sem['bit_sizes'])
chk('GR 已识别', 'GR' in out.columns, str(list(out.columns)))
chk('CAL 已合并', 'CAL' in out.columns and out['CAL'].notna().sum()>=n, str(list(out.columns)))
chk('BS 已合成=8.5', 'BS' in out.columns and abs(float(out['BS'].iloc[0])-8.5)<1e-6, str(out.get('BS', pd.Series()).head(1).to_dict()))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
