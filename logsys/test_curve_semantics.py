# -*- coding: utf-8 -*-
"""LAS/DLIS 曲线语义识别自检。"""
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
chk('TLFamily GR_EDTC=Gamma Ray', sem['families'].get('GR_EDTC','').lower().startswith('gamma ray'))
chk('TLFamily CALC1=Caliper(但实为灰岩)', sem['families'].get('CALC1','').lower()=='caliper')
chk('BS 参数含 8.5', any(abs(v-8.5)<1e-6 for _,v in sem['bit_sizes']), str(sem['bit_sizes']))
n=20
# 1) CALC1/3/5 不得当 CAL
df=pd.DataFrame({'CALC1':[0.4]*n,'CALC3':[0.3]*n,'CALC5':[0.2]*n,'GR_EDTC':[45.0]*n,'GRN':[np.nan]*n})
desc={'CALC1':{'desc':'','family':'Caliper'},'CALC3':{'desc':'','family':'Caliper'},'CALC5':{'desc':'','family':'Caliper'},
      'GR_EDTC':{'desc':'GR_EDTC_1','family':'Gamma Ray'},'GRN':{'desc':'','family':'Gamma Ray Normalized'}}
out=standardize_curve_names(df, context='las', descriptions=desc, bit_sizes=sem['bit_sizes'])
chk('CALC1/3/5 不作 CAL', 'CAL' not in out.columns, str(list(out.columns)))
chk('CALC 仍保留为灰岩含量', all(c in out.columns for c in ('CALC1','CALC3','CALC5')))
chk('GR 已识别', 'GR' in out.columns)
chk('BS 已合成=8.5', 'BS' in out.columns and abs(float(out['BS'].iloc[0])-8.5)<1e-6)
# 2) 真井径 CALA + Gamma EVR + BITSIZE（DLIS 风格）
df2=pd.DataFrame({'DEPT':np.arange(n),'CALA':[8.5]*n,'GREV':[60.0]*n,'BITSIZE':[8.5]*n})
desc2={'CALA':{'desc':'CALA/Caliper','family':''},'GREV':{'desc':'GREV/Gamma EVR','family':''},'BITSIZE':{'desc':'BITSIZE/Bit Size','family':''}}
out2=standardize_curve_names(df2, context='dlis', descriptions=desc2, bit_sizes=None)
chk('DLIS CALA→CAL', 'CAL' in out2.columns and abs(float(out2['CAL'].iloc[0])-8.5)<1e-6, str(list(out2.columns)))
chk('DLIS GREV→GR', 'GR' in out2.columns)
chk('DLIS BITSIZE→BS', 'BS' in out2.columns and abs(float(out2['BS'].iloc[0])-8.5)<1e-6)
# 3) 真实 DLIS 加载（小样本）
try:
    pdl=r'D:\360\Brasil\CuraCao-4A\3-SPS-114-wireline_20251006（第一趟取芯）\3-SPS-114A_DDP_Cabo_8f_GR-NEU-DEN_campo_rep_evr.dlis'
    ld=logInt.DataLoader(); d=ld.load_data(pdl)
    chk('DLIS 加载非空', d is not None and len(d)>0, 'rows')
    cols=set(d.columns) if d is not None else set()
    chk('DLIS 语义生成 CAL/GR/BS', {'CAL','GR','BS'}.issubset(cols), str(sorted(cols)))
    print('   DLIS columns:', sorted(cols)[:20])
except Exception as e:
    chk('DLIS 加载', False, repr(e))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
