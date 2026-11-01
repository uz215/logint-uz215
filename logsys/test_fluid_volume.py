import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
from logsys.fluids import compute_sg_so
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
n=6
df=pd.DataFrame({'MD':np.arange(n),'INTERPRETATION':['GAS_OIL','GAS_OIL','GAS','OIL','DRY','WATER'],
                 'SW_COMP':[0.4]*n})
gas=pd.DataFrame({'MD':np.arange(n),'C1':[900]*n,'C2':[100]*n,'C3':[0]*n,'C4':[0]*n,'C5':[0]*n})
d1,st1=compute_sg_so(df, gas_data=gas)
chk('默认油气各半(有气测也不自动改)', abs(d1.loc[0,'SG']-0.3)<1e-6 and abs(d1.loc[0,'SO']-0.3)<1e-6, str(d1.loc[0].to_dict()))
d2,st2=compute_sg_so(df, gas_oil_ratio=0.4)
chk('显式比例0.4=气40%/油60%', abs(d2.loc[1,'SG']-0.24)<1e-6 and abs(d2.loc[1,'SO']-0.36)<1e-6, str(d2.loc[1].to_dict()))
chk('守恒', float(st2['max_conservation_residual'])<1e-6, str(st2))
chk('干层含烃', (d2.loc[4,'SG']+d2.loc[4,'SO'])>0, str(d2.loc[4].to_dict()))
chk('水层无烃', abs(d2.loc[5,'SG'])+abs(d2.loc[5,'SO'])<1e-9)
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
