# -*- coding: utf-8 -*-
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
from logsys.fluids import compute_sg_so
ok = 0; fail = 0
def chk(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1; print('  PASS ', name)
    else: fail += 1; print('  FAIL ', name, detail)
n = 8
df = pd.DataFrame({'MD': np.arange(n), 'INTERPRETATION': ['GAS','OIL','GAS_OIL','DRY','WATER','DRY','GAS_OIL','NonReservoir'],
                   'SW_COMP': [0.3,0.4,0.5,0.7,0.9,0.6,0.4,0.5]})
df, st = compute_sg_so(df, gas_oil_ratio=0.5)
chk('守恒 GAS', abs(df.loc[0,'SG']+df.loc[0,'SO']+df.loc[0,'SW_EFF']-1) < 1e-6)
chk('气层 Sg=1-Sw', abs(df.loc[0,'SG']-0.7)<1e-6 and abs(df.loc[0,'SO'])<1e-6, str(df.loc[0].to_dict()))
chk('油层 So=1-Sw', abs(df.loc[1,'SO']-0.6)<1e-6 and abs(df.loc[1,'SG'])<1e-6)
chk('GAS_OIL 50/50', abs(df.loc[2,'SG']-0.25)<1e-6 and abs(df.loc[2,'SO']-0.25)<1e-6, str(df.loc[2].to_dict()))
chk('干层含烃(Sg+So>0)', (df.loc[3,'SG']+df.loc[3,'SO'])>0, str(df.loc[3].to_dict()))
chk('水层无烃', abs(df.loc[4,'SG'])+abs(df.loc[4,'SO'])<1e-9)
df2, st2 = compute_sg_so(df, gas_oil_ratio=0.4)
chk('比例可配(油60%)', abs(df2.loc[2,'SG']-0.2)<1e-6 and abs(df2.loc[2,'SO']-0.3)<1e-6, str(df2.loc[2].to_dict()))
chk('守恒全部', float(st2['max_conservation_residual'])<1e-6, str(st2))
chk('统计均值', st2.get('mean_sg') is not None and st2.get('mean_so') is not None)
print('\n结果: %d 通过, %d 失败' % (ok, fail))
sys.exit(0 if fail == 0 else 1)
