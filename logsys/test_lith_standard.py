# -*- coding: utf-8 -*-
"""LITH-2026-11-02-v2 标准规则自检。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r'D:\360\src')
from logsys import lith_standard as ls
ok=0; fail=0
def chk(n,c,d=''):
    global ok,fail
    if c: ok+=1; print('  PASS ',n)
    else: fail+=1; print('  FAIL ',n,d)
chk('标准版本', ls.STANDARD_ID=='LITH-2026-11-02-v2.11', ls.STANDARD_ID)
chk('证据优先级 core>element>curve', ls.EVIDENCE_PRIORITY[:3]==('core','element','curve'), ls.EVIDENCE_PRIORITY)
chk('GR不作绝对否决', ls.GR_POLICY.get('absolute_veto') is False, ls.GR_POLICY)
chk('CALC1=灰岩', ls.CALC_SEMANTICS['CALC1']['indicator']=='limestone')
chk('CALC3/5=白云岩', ls.CALC_SEMANTICS['CALC3']['indicator']=='dolomite' and ls.CALC_SEMANTICS['CALC5']['indicator']=='dolomite')
chk('井壁取芯=测井深度', ls.DEPTH_BASIS['SWC']=='logging_depth')
chk('钻井取芯=录井深度', ls.DEPTH_BASIS.get('drilling_core')=='mud_logging_depth')
chk('XRD/XRF=录井深度±10m', ls.DEPTH_BASIS['XRD']=='mud_logging_depth' and ls.DEPTH_BASIS['xrd_xrf_max_shift_m']==10.0)
chk('XRD/XRF逐样本局部配准+锚点', ls.DEPTH_BASIS.get('xrd_xrf_shift_mode')=='per_sample_local_anchored' and ls.DEPTH_BASIS.get('xrd_xrf_window_m',0)>0 and ls.DEPTH_BASIS.get('xrd_xrf_anchor_m',0)>0, ls.DEPTH_BASIS)
chk('点级计数不能覆盖剖面', ls.PROFILE_ARBITRATION['point_count_can_override'] is False)
chk('Unknown缓存禁用', ls.PROFILE_ARBITRATION['cache']['unknown_well_cache'] is False)
chk('录井/XRD知识不强制对齐测井深度', ls.WELL_KNOWLEDGE_POLICY.get('depth_alignment_required') is False and ls.WELL_KNOWLEDGE_POLICY.get('summary_bin_m',0)>0)
chk('井知识层级/分类齐全', ls.WELL_KNOWLEDGE_POLICY.get('taxonomy') and {'basic_data','stratigraphy','lithology','testing','log_interpretation','gas_show','oil_gas_show','engineering'} <= set(ls.WELL_KNOWLEDGE_POLICY.get('categories') or []))
chk('岩性必须带地层', ls.WELL_KNOWLEDGE_POLICY.get('formation_required') is True)
chk('层级自动补全/界面字段', ls.WELL_KNOWLEDGE_POLICY.get('hierarchy_autofill') is True and set(ls.WELL_KNOWLEDGE_POLICY.get('contacts',{}).get('owc_gwc_fields') or [])=={'owc','gwc'})
df=pd.DataFrame({'MD':[1,2,3],'CALC1':[0.4,0.8,0.0],'CALC3':[0.3,0.2,0.0],'CALC5':[0.2,0.2,0.0]})
out=ls.annotate_calc_curves(df.copy())
chk('派生CALC_LIME_CO2', abs(float(out['CALC_LIME_CO2'].iloc[0])-0.4)<1e-9)
chk('派生CALC_DOL_CO2(3/5均值)', abs(float(out['CALC_DOL_CO2'].iloc[0])-0.25)<1e-9)
chk('派生DOL_RATIO', abs(float(out['CALC_DOL_RATIO'].iloc[0])-0.25/0.65)<1e-9)
print('\n结果: %d 通过, %d 失败'%(ok,fail))
sys.exit(0 if fail==0 else 1)
