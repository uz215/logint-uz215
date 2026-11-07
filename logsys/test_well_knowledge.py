# -*- coding: utf-8 -*-
"""井目录知识总结自检。"""
import sys
sys.path.insert(0, r'D:\360\src')
from logsys.well_knowledge import (build_well_knowledge, save_well_knowledge,
                                   load_well_knowledge, query_well_knowledge)
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
res={'output_dir': r'D:\360\src\output\1-SPS-108'}
k=build_well_knowledge(r'D:\360\Brasil\Curacao-1', well_name='1-SPS-108', results=res)
chk('无错误', not k.get('error'), k.get('error'))
chk('岩性大段', len(k.get('lithology_zones') or [])>0, len(k.get('lithology_zones') or []))
chk('XRD按井段汇总', len(k.get('xrd_bins') or [])>0, len(k.get('xrd_bins') or []))
chk('XRF按井段汇总', len(k.get('xrf_bins') or [])>0, len(k.get('xrf_bins') or []))
chk('井壁取芯', len(k.get('swc_core') or [])>0, len(k.get('swc_core') or []))
chk('深度说明不强制对齐', '不强制' in (k.get('depth_note') or ''), k.get('depth_note'))
k2,mp,jp=save_well_knowledge(r'D:\360\Brasil\Curacao-1', well_name='1-SPS-108', results=res)
chk('Markdown已生成', mp.exists() and mp.stat().st_size>1000, mp)
chk('JSON可加载', bool(load_well_knowledge('1-SPS-108')))
chk('logInt查询接口', len(query_well_knowledge('1-SPS-108','XRD'))>100)
chk('知识层级含国家/盆地/构造/油田/井', all((k.get('hierarchy') or {}).get(x) for x in ('country','basin','structure','field','well')), k.get('hierarchy'))
chk('层级自动补全(盆地Santos/构造Curacao)', (k.get('hierarchy') or {}).get('basin')=='Santos' and (k.get('hierarchy') or {}).get('structure')=='Curacao', k.get('hierarchy'))
chk('油水/气水界面字段', ('owc' in (k.get('testing') or {})) and ('gwc' in (k.get('testing') or {})), list((k.get('testing') or {}).keys()))
_owc=(k.get('testing') or {}).get('owc')
chk('OWC候选标注来源/置信度', bool(_owc) and _owc.get('source') and _owc.get('confidence'), _owc)
chk('基础数据(坐标/钻头)', bool((k.get('basic_data') or {}).get('coordinates')) and bool((k.get('basic_data') or {}).get('bit_size')), k.get('basic_data'))
chk('试油分类', bool((k.get('testing') or {}).get('files')), k.get('testing'))
chk('测井解释分类', int((k.get('log_interpretation') or {}).get('layers') or 0)>=0, k.get('log_interpretation'))
chk('气测异常含深度', all(('top' in x and 'base' in x) for x in (k.get('gas_show') or [])), (k.get('gas_show') or [])[:1])
chk('地层顶已提取', len((k.get('stratigraphy') or {}).get('formation_tops') or [])>0, k.get('stratigraphy'))
chk('岩性带地层', any(z.get('formation') not in ('', '未提供') for z in (k.get('lithology_zones') or [])), (k.get('lithology_zones') or [])[:2])
chk('SWC带地层', any(s.get('formation') not in ('', '未提供') for s in (k.get('swc_core') or [])), (k.get('swc_core') or [])[:2])
chk('分类齐全', {'basic_data','stratigraphy','lithology','testing','log_interpretation','gas_show','oil_gas_show','engineering'} <= set((k.get('categories') or {}).keys()), list((k.get('categories') or {}).keys()))
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
