# -*- coding: utf-8 -*-
"""岩心/XRD/XRF 标定自检。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
from logsys.core_calib import (read_well_calibration, attach_core_calibration,
                               apply_core_lithology, estimate_xrd_depth_shifts)
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
    chk('含钻井取芯孔隙度(DRILL_CORE_PHIE)', 'DRILL_CORE_PHIE' in cal or 'CORE_PHIE' in cal)
if 'DRILL_CORE_PHIE' in cal:
    _m=cal['DRILL_CORE_PHIE'].notna() & cal['DEPTH_BASIS'].eq('MUD')
    chk('钻井取芯深度基准=MUD', bool(_m.any()), int(_m.sum()))
    chk('区分取芯(LOG)/XRD-XRF(MUD)深度基准', set(cal.get('DEPTH_BASIS', [])) >= {'LOG','MUD'}, cal.get('DEPTH_BASIS').value_counts().to_dict() if 'DEPTH_BASIS' in cal else None)
    _xrd=cal[cal['DEPTH_BASIS'].eq('MUD')].dropna(subset=['MD'])
    _d0=pd.DataFrame({'MD':[6300,6310,6320],'CALCITE_QE':[0.3,0.5,0.2]})
    _sh,_det=estimate_xrd_depth_shifts(_d0,_xrd)
    chk('XRD局部配准在±10m内', len(_sh)==len(_xrd) and float(_sh.abs().max())<=10.0,
        (_sh.min(),_sh.max(),_det.get('mode')))
df=pd.DataFrame({'MD':[6312.1,6314.5,6320.0],'LITHOLOGY':['sandstone']*3})
df=attach_core_calibration(df,r'D:\360\Brasil\Curacao-1')
chk('按深度挂接岩心岩性', 'CORE_LITH' in df and df['CORE_LITH'].notna().any(), df.get('CORE_LITH'))
df2,n=apply_core_lithology(df.copy())
chk('岩心岩性覆盖', n>=1 and str(df2['LITHOLOGY'].iloc[0]) in ('limestone','dolomite'), (n,df2['LITHOLOGY'].tolist()))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
