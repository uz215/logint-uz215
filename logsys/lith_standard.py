# -*- coding: utf-8 -*-
"""岩性判定标准规则库（LITH-2026-11-02-v2.2）。

本模块是"程序即标准依据"的唯一规则入口：标准条款编号、证据优先级、
GR 政策、酸解 CO2 语义、深度基准、剖面仲裁、缓存校验集中在此；
实现细节在 logInt.py / core_calib.py / logvis.py，测试在 logsys/test_lith_standard.py。
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd

STANDARD_ID = 'LITH-2026-11-02-v2.8'
STANDARD_DATE = '2026-11-02'

# 证据优先级：取芯/岩心（最高）> 元素测井 > 曲线特征 > 点级统计
EVIDENCE_PRIORITY = ('core', 'element', 'curve', 'point_count')

# GR 政策：绝对值不作否决；只用井内分位判断高低
GR_POLICY = {
    'absolute_veto': False,
    'use': 'within_well_percentile',
    'note': 'GR 绝对值不得否决任何岩性；泥质碳酸盐岩 GR 80–110 属正常。',
}

# 酸解 CO2 语义（用户 2026-11-02 定案）：CALC1=灰岩，CALC3/5=白云岩
CALC_SEMANTICS = {
    'CALC1': {'window': '0-1min', 'indicator': 'limestone',
              'derived': 'CALC_LIME_CO2'},
    'CALC3': {'window': '3-5min', 'indicator': 'dolomite',
              'derived': 'CALC_DOL_CO2'},
    'CALC5': {'window': '3-5min', 'indicator': 'dolomite',
              'derived': 'CALC_DOL_CO2'},
    'note': 'CALC1/3/5 不是井径；CALC3/5 取均值作白云岩指示。',
}

# 深度基准（用户 2026-11-02 定案）
DEPTH_BASIS = {
    'SWC': 'logging_depth',
    'drilling_core': 'mud_logging_depth',
    'XRD': 'mud_logging_depth',
    'XRF': 'mud_logging_depth',
    'xrd_xrf_max_shift_m': 10.0,
    'xrd_xrf_normal_shift_m': (3.0, 5.0),
    'xrd_xrf_shift_mode': 'per_sample_local_anchored',
    'xrd_xrf_window_m': 100.0,
    'xrd_xrf_anchor_m': 150.0,
    'note': '井壁取芯SWC按测井深度直挂；钻井取芯、XRD/XRF为录井深度，不是全井固定偏移：换钻具/'
            '起下钻都可能变，通常 3–5m、上限 10m；逐样本滑动窗+局部锚点配准后再挂。',
}

# 剖面仲裁：元素 > 曲线特征 > 点级计数（点级只能参考，不能反推覆盖）
PROFILE_ARBITRATION = {
    'order': ('element_profile', 'crossplot_pti_density', 'point_count'),
    'point_count_can_override': False,
    'cache': {'well_name_required': True, 'allowed_labels': ('sand_shale', 'carbonate', 'mixed'),
              'unknown_well_cache': False},
}

# 碳酸盐岩规则：泥质碳酸盐岩不因 GR 高被否决
CARBONATE_RULES = {
    'gr_absolute_veto': False,
    'element_carbonate_min': 0.45,
    'element_clay_max': 0.45,
    'notes': '元素方解石+白云石≥0.45 且泥质<0.45 可直接定碳酸盐；'
             'GR 只作井内分位参考；密度/声波/中子/电阻率为第二证据。',
}

# 井目录知识总结（2026-11-02/05 用户定案）：录井/XRD/XRF 不要求与测井深度精确对齐
WELL_KNOWLEDGE_POLICY = {
    'depth_alignment_required': False,
    'summary_bin_m': 50.0,
    'kb_category': 'well_material',
    'sections': ('lithology_zones', 'xrd_bins', 'xrf_bins', 'swc_core', 'drill_core'),
    'taxonomy': ('country', 'basin', 'sag', 'structure', 'field', 'well'),
    'categories': ('basic_data', 'stratigraphy', 'lithology', 'testing',
                   'log_interpretation', 'gas_show', 'oil_gas_show', 'engineering'),
    'db_ingest': True,
    'formation_required': True,
    'formation_fields': ('lithology', 'xrd_bins', 'swc_core', 'drill_core',
                         'gas_show', 'oil_gas_show', 'engineering'),
    'hierarchy_autofill': True,
    'contacts': {'owc_gwc_fields': ('owc', 'gwc'),
                 'candidate_allowed': True,
                 'candidate_must_label_source_confidence': True},
    'note': '按国家/盆地/凹陷/构造/油田/井分层；井下面按基础数据/地层/岩性/试油/测井解释/气测分类。',
}

# 本井验证案例（1-SPS-108，2026-11-02）
VALIDATION_CASE = {
    'well': '1-SPS-108',
    'problem': '纯砂泥岩剖面（3335砂岩/2022泥岩/0碳酸盐）',
    'fix': '元素*_QE→VOL_*、元素VSH/KTH、去GR绝对否决、岩心标定',
    'result': '140层（limestone76/dolomite60/sandstone3/anhydrite1）；'
              '288取芯点100%一致',
}


def annotate_calc_curves(data):
    """按标准给酸解 CO2 曲线加语义派生列（保留原始 CALC1/3/5）。"""
    if data is None or len(data) == 0:
        return data
    if 'CALC1' in data.columns and 'CALC_LIME_CO2' not in data.columns:
        data['CALC_LIME_CO2'] = pd.to_numeric(data['CALC1'], errors='coerce')
    _dol_src = [c for c in ('CALC3', 'CALC5') if c in data.columns]
    if _dol_src and 'CALC_DOL_CO2' not in data.columns:
        _parts = [pd.to_numeric(data[c], errors='coerce') for c in _dol_src]
        data['CALC_DOL_CO2'] = pd.concat(_parts, axis=1).mean(axis=1)
    if 'CALC_LIME_CO2' in data.columns and 'CALC_DOL_CO2' in data.columns:
        _sum = data['CALC_LIME_CO2'] + data['CALC_DOL_CO2']
        data['CALC_DOL_RATIO'] = (data['CALC_DOL_CO2'] / _sum).where(_sum > 0)
        data['CALC_LIME_RATIO'] = (data['CALC_LIME_CO2'] / _sum).where(_sum > 0)
        logging.getLogger('logInt').info(
            '酸解CO2语义(%s): CALC1→灰岩指示(CALC_LIME_CO2)；'
            'CALC3/5→白云岩指示(CALC_DOL_CO2)', STANDARD_ID)
    return data
