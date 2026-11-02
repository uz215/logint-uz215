# -*- coding: utf-8 -*-
"""岩心/XRD/XRF 标定自检。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
from logsys.core_calib import read_well_calibration, attach_core_calibration, apply_core_lithology
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
cal=read_well_calibration(r'D:\360\Brasil\Curacao-1')
chk('标定表非空', cal is not None and len(cal)>200, len(cal) if cal is not None else None)
if cal is not None and len(cal):
    chk('含 SWC 岩性', 'CORE_LITH' in cal and cal['CORE_LITH'].notna().any())
    chk('含 XRD 方解石/白云石', 'XRD_CAL' in cal and 'XRD_DOL' in cal)
    chk('含 XRF 元素', 'XRF_FE' in cal or 'XRF_AL' in cal)
    chk('含岩心孔隙度', 'CORE_PHIE' in cal)
df=pd.DataFrame({'MD':[6312.1,6314.5,6320.0],'LITHOLOGY':['sandstone']*3})
df=attach_core_calibration(df,r'D:\360\Brasil\Curacao-1')
chk('按深度挂接岩心岩性', 'CORE_LITH' in df and df['CORE_LITH'].notna().any(), df.get('CORE_LITH'))
df2,n=apply_core_lithology(df.copy())
chk('岩心岩性覆盖', n>=1 and str(df2['LITHOLOGY'].iloc[0]) in ('limestone','dolomite'), (n,df2['LITHOLOGY'].tolist()))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
