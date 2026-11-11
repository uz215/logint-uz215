# -*- coding: utf-8 -*-
"""录井图五类知识提取自检。"""
import sys
sys.path.insert(0, r'D:\360\src')
from logsys.mudlog_knowledge import parse_mudlog_text
text = """
WELL NAME: TEST-1
LOCATION: Block A, 1000m
WELL TYPE: Exploration Well
BIT SIZE: 12.25 in
CASING: 9 5/8 in to 2000m
MUD TYPE: WATER BASED
MUD DENSITY: 1.25
MUD VISCOSITY: 45
FLUID LOSS: 3.2
Lithology: Limestone 6300-6310m
Gas show: 6312-6315m
Oil sand: 6316m, oil stain, grade 油浸, bubble 气泡
Mud loss: 6400m, lost circulation
"""
k=parse_mudlog_text(text,'TEST-1')
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
chk('井名', k['basic_data'].get('well_name')=='TEST-1', k['basic_data'])
chk('井别=探井', k['basic_data'].get('well_category')=='探井', k['basic_data'])
chk('钻头/套管/泥浆', bool(k['basic_data'].get('bit_program') and k['basic_data'].get('casing_program') and k['basic_data'].get('mud_type') and k['basic_data'].get('mud_density')), k['basic_data'])
chk('岩性', len(k['lithology'])>0, k['lithology'])
chk('气测异常', len(k['gas_show'])>0, k['gas_show'])
chk('油气显示/级别/气泡', len(k['oil_gas_show'])>0 and any(x.get('grade') for x in k['oil_gas_show']), k['oil_gas_show'])
chk('工程情况(井漏)', len(k['engineering'])>0, k['engineering'])
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
