# -*- coding: utf-8 -*-
"""文档入库：markdown/docx → doc/chunk/FTS + 轻量实体/事实抽取。

- 中文 FTS：用 jieba 预分词后写入 doc_fts.body（同时保留原文 chunk.text）；
- frontmatter 字段（category/region/country/well_name/depth_range/title）解析入列；
- 实体抽取（MVP）：井名正则、国家/区块词典；事实：well LOCATED_IN country/region；
- 幂等：按 path 去重（重跑不会重复入库，除非 --force）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from .db import connect
try:
    from .entities import (extract_entities, canon_well, canon_field, canon_formation)
except Exception:
    extract_entities = None

try:
    import jieba
    jieba.setLogLevel(60)
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

WELL_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:[-\s][A-Za-z0-9]+){0,3}[-\s](?:\d{1,3}[A-Za-z]?))\b')
COUNTRIES = ['Chad', '乍得', 'Brazil', '巴西', 'Uzbekistan', '乌兹别克', 'Indonesia', '印尼',
             'Bangladesh', '孟加拉', 'Niger', '尼日尔', 'Kazakhstan', '哈萨克', 'Sudan', '苏丹',
             'Venezuela', '委内瑞拉', 'Peru', '秘鲁', 'Canada', '加拿大', 'Australia', '澳洲']

# 路径/标题国别推导：规范中文名 <- 中文名/别名/英文名（最长匹配，避免 印度⊂印度尼西亚、南苏丹⊂苏丹 误判）
# 覆盖图谱 90 国。英文用整词边界，中文用子串。
_COUNTRY_EN = {'中国': 'China', '乌克兰': 'Ukraine', '乌兹别克斯坦': 'Uzbekistan', '乍得': 'Chad',
    '也门': 'Yemen', '伊拉克': 'Iraq', '伊朗': 'Iran', '俄罗斯': 'Russia', '保加利亚': 'Bulgaria',
    '克罗地亚': 'Croatia', '刚果（布）': 'Congo-Brazzaville', '刚果（金）': 'DR Congo', '利比亚': 'Libya',
    '利比里亚': 'Liberia', '加拿大': 'Canada', '加纳': 'Ghana', '南苏丹': 'South Sudan', '卡塔尔': 'Qatar',
    '印度尼西亚': 'Indonesia', '危地马拉': 'Guatemala', '厄瓜多尔': 'Ecuador', '叙利亚': 'Syria',
    '古巴': 'Cuba', '哈萨克斯坦': 'Kazakhstan', '哥伦比亚': 'Colombia', '喀麦隆': 'Cameroon',
    '土库曼斯坦': 'Turkmenistan', '圭亚那': 'Guyana', '坦桑尼亚': 'Tanzania', '埃及': 'Egypt',
    '塞内加尔': 'Senegal', '塞尔维亚': 'Serbia', '墨西哥': 'Mexico', '孟加拉国': 'Bangladesh',
    '安哥拉': 'Angola', '尼日利亚': 'Nigeria', '尼日尔': 'Niger', '巴基斯坦': 'Pakistan',
    '巴布亚新几内亚': 'Papua New Guinea', '巴拿马': 'Panama', '巴西': 'Brazil', '布基纳法索': 'Burkina Faso',
    '意大利': 'Italy', '挪威': 'Norway', '摩洛哥': 'Morocco', '斯里兰卡': 'Sri Lanka',
    '新西兰': 'New Zealand', '智利': 'Chile', '柬埔寨': 'Cambodia', '格鲁吉亚': 'Georgia',
    '毛里塔尼亚': 'Mauritania', '沙特阿拉伯': 'Saudi Arabia', '澳大利亚': 'Australia',
    '特立尼达和多巴哥': 'Trinidad and Tobago', '玻利维亚': 'Bolivia', '科威特': 'Kuwait',
    '科特迪瓦': 'Cote dIvoire', '秘鲁': 'Peru', '突尼斯': 'Tunisia', '索马里': 'Somalia',
    '约旦': 'Jordan', '缅甸': 'Myanmar', '罗马尼亚': 'Romania', '美国': 'United States',
    '肯尼亚': 'Kenya', '苏丹': 'Sudan', '苏里南': 'Suriname', '英国': 'United Kingdom',
    '西班牙': 'Spain', '越南': 'Vietnam', '阿塞拜疆': 'Azerbaijan', '阿尔及利亚': 'Algeria',
    '阿尔巴尼亚': 'Albania', '阿曼': 'Oman', '阿根廷': 'Argentina', '阿联酋': 'UAE',
    '马来西亚': 'Malaysia', '马达加斯加': 'Madagascar', '东帝汶': 'Timor-Leste', '乌拉圭': 'Uruguay',
    '加蓬': 'Gabon', '印度': 'India', '埃塞俄比亚': 'Ethiopia', '塞浦路斯': 'Cyprus', '文莱': 'Brunei',
    '泰国': 'Thailand', '纳米比亚': 'Namibia', '菲律宾': 'Philippines', '土耳其': 'Turkey',
    '乌干达': 'Uganda'}
# 额外常见别名
_COUNTRY_EXTRA = {'孟加拉': '孟加拉国', '哈萨克': '哈萨克斯坦', '印尼': '印度尼西亚', '阿联': '阿联酋',
    '阿拉伯联合酋长国': '阿联酋', '刚果共和国': '刚果（布）', '刚果民主共和国': '刚果（金）',
    'UAE': '阿联酋', 'USA': '美国', 'UK': '英国'}

_COUNTRY_PATH_MAP = {}  # alias(lower) -> canonical zh
for _cn, _en in _COUNTRY_EN.items():
    _COUNTRY_PATH_MAP[_cn.lower()] = _cn
    _COUNTRY_PATH_MAP[_en.lower()] = _cn
for _a, _cn in _COUNTRY_EXTRA.items():
    _COUNTRY_PATH_MAP[_a.lower()] = _cn
_CN_ALIASES = [a for a in _COUNTRY_PATH_MAP if re.search(r'[\u4e00-\u9fff]', a)]
_EN_ALIASES = [(a, c) for a, c in _COUNTRY_PATH_MAP.items() if not re.search(r'[\u4e00-\u9fff]', a)]


def detect_country(path: str, title: str = '') -> str:
    """从文件路径/标题推导国别（规范中文名）。无命中返回空串。"""
    blob = '%s %s' % (path or '', title or '')
    low = blob.lower()
    hits = []
    for a in _CN_ALIASES:
        if a in blob:
            hits.append((len(a), _COUNTRY_PATH_MAP[a]))
    for a, c in _EN_ALIASES:
        if re.search(r'(?<![a-z])' + re.escape(a) + r'(?![a-z])', low):
            hits.append((len(a), c))
    if not hits:
        return ''
    hits.sort(reverse=True)
    return hits[0][1]


# ── 知识技术分类（本知识库是以测井专业为主的油气知识库；按知识本身领域 + 技术细类，不按国别；国别单独存 country 列）──
DOMAIN_LOGGING = '测井方法'   # 测井专业技术/方法：随钻 / 生产 / 光纤 / 裸眼 / 电缆 / 解释方法（× 厂商小类）
DOMAIN_GEO = '地质'           # 以油气地质为主：油气地质 / 非常规地质 / 基础地质（构造·沉积·岩性）（× 技术细分小类）
DOMAIN_GENERAL = '通用知识'    # 油气通用知识（不属于测井专业）：标准规范 / 项目管理 / 软件工具 / 其他

# 地质领域技术细类（以油气地质为主：优先级 非常规 > 油气地质 > 储层地质 > 构造 > 沉积与地层 > 岩性与矿物 > 其他）
_GEO_TECH = {
    '非常规地质': ['煤层气', '页岩气', '页岩油', '致密', '非常规', '天然气水合物', 'cbm', 'shale',
                'tight', 'coalbed', 'unconventional', '煤层', '页岩'],
    '油气地质': ['烃源', '生油', '源岩', '油气藏', '圈闭', '盖层', '运移', '聚集', '含油气', '油藏',
               '气藏', '油气系统', '勘探', 'hydrocarbon', 'source rock', 'trap', 'petroleum', 'maturity'],
    '储层地质': ['水淹层', '成岩', '储集体', '油藏描述', 'water flooded', 'reservoir',
               'diagenesis', '储层地质'],
    '构造地质': ['构造', '断裂', '断层', '褶皱', '裂缝', '地应力', '孔隙压力', 'pore pressure',
               'tectonic', 'fault', 'fracture', 'structural', '地质力学'],
    '沉积与地层': ['沉积', '相', '三角洲', '滩坝', '层序', '地层', '不整合', '年代地层', '旋回', '砂体',
                'sediment', 'stratig', 'facies', 'sequence', '编图'],
    '岩性与矿物': ['岩性', '岩石', '矿物', '碳酸盐', '白云岩', '灰岩', '砂岩', '泥岩', '火山岩', '变质岩',
                '煤岩', '数学地质', 'clay', 'mineral', 'litholog', 'rock', 'carbonate', 'petrog', '岩相'],
}
# 测井方法领域「大类」（按测井技术类型，优先级：随钻 > 生产 > 光纤 > 裸眼 > 电缆 > 解释）。
# 大类是仪器/方法知识的一级细分；小类（厂商）见 _LOG_MINOR。
_LOG_MAJOR = {
    '随钻测井': ['随钻', 'lwd', 'mwd', '地质导向', '旋转导向', '随钻测量', '随钻测井', '录井', '气测',
              'mud logging', 'geosteering', 'logging while', 'directional', '井眼轨迹', '轨迹'],
    '生产测井': ['生产测井', '产出剖面', '注入剖面', '吸水剖面', '产液剖面', '套管井', 'production logging',
              '地层测试', 'mdt', 'rci', 'rpm', 'wft', 'flowmeter', '流量计', '持水', '含水率', '井筒',
              'through tubing', '过油管', '剩余油', '可动', 'aft', 'mfat', '找水'],
    '光纤': ['光纤', '分布式', 'dts', 'das', 'fiber optic', 'optical fiber', '布里渊', '拉曼', '光时域',
          '光纤测井', '分布式测温', '分布式声波'],
    '裸眼测井': ['裸眼', 'openhole', 'open hole', 'open-hole'],
    '电缆测井': ['电缆', 'wireline', '常规测井', '完井测井', '测井系列', '测井曲线', '测井资料', '组合测井',
              '双侧向', '微球', '感应', '三组合', '声波测井', '密度测井', '中子测井', '自然伽马', '井径',
              '电阻率', '成像测井', '阵列', '连续管', '过钻杆', '过钻具', '穿缆', 'eilog', 'ait', 'hrla',
              'hgns', 'tld', 'mcfl', 'cmr', 'fmi', 'acquisition', 'depth control', '仪器', '传感器',
              '探头', '电极', '探测器', '测井仪', '下井仪', '下井', '采集面板', '硬件', '震击器', '配件',
              '模块', '组件', '推靠', '极板', '线圈', '天线', '发射', '接收', '刻度', '标定', 'calibration',
              'hardware', 'tool', 'sonde', 'probe', 'fits', '过钻具成像', '介电', '补偿密度', '补偿中子',
              '井壁', '取心', 'coring', '固井', '射孔', '水泥', 'perforation', 'cement'],
    '解释方法': ['解释', '评价', '处理', '饱和度', '流体', '含油', '含水', '油水层', '识别', '划分', '建模',
              '反演', '岩石物理', '交会', '图版', '模板', '标准层', '隔层', '岩心', '压汞', '数字岩心',
              'interpretation', 'petrophysics', 'evaluation', 'saturation', 'facies', 'well log',
              'log analysis', 'analysis', 'porosity', 'permeability', '核磁', '核磁共振'],
}
# 测井方法领域「小类」（按厂商/来源；缺测归 其他）。优先级：国外服务商 > 国内。
_LOG_MINOR = {
    'SLB': ['slb', 'schlumberger', '斯伦贝谢'],
    '贝克休斯': ['贝克休斯', 'baker hughes', 'bakerhughes', 'bhge'],
    '哈里伯顿': ['哈里伯顿', 'halliburton'],
    'CNLC': ['cnlc', '中国石油测井', '中油测井', '中石油测井', '长城测井', 'cpl', 'cnpc logging',
           '国产仪器', '国产测井'],
    '中海油': ['中海油', 'cnooc', '海油'],
}
# 通用知识（油气通用知识，不属于测井专业）：
#   - 标准规范：关于测井及油气相关方面的规范/标准/规程
#   - 项目管理：测井地质研究的课题设计、实施、方案等（非预算/合同/软件类）
#   - 软件工具：测井专业软件（Techlog/Geolog/LEAD 等），非通用办公软件
_GEN_TECH = {
    '标准规范': ['规范', '标准', '规程', '图式', '编制', '编图', 'spec', 'standard'],
    '项目管理': ['课题', '立项', '开题', '结题', '验收', '技术路线', '实施方案', '项目设计', '课题设计',
              '申报书', '可行性', '论证', '研究计划', '中期', 'project', 'proposal'],
    '软件工具': ['techlog', 'geolog', 'paradigm', 'petrel', 'landmark', 'discovery', 'jason',
              'logview', 'geooffice', '测井软件', '专业软件', '解释软件', '测井平台', 'lead测井', 'lead软件'],
}

# 地质领域「大类」：由技术细分(小类)向上归并的粗分组。
#   基础地质 = 构造 / 沉积与地层 / 岩性与矿物
#   油气地质 = 油气地质 / 储层地质
#   非常规地质 = 非常规地质（其余单独成大类）
_GEO_MAJOR_MAP = {
    '构造地质': '基础地质', '沉积与地层': '基础地质', '岩性与矿物': '基础地质',
    '油气地质': '油气地质', '储层地质': '油气地质',
    '非常规地质': '非常规地质',
    '其他': '其他',
}
# 通用知识领域「小类」：按 大类 各自独立的范围（避免跨大类误挂小类）。
# 关键词均为内容信号，不含 ppt/word 等格式后缀（防误命中）。全不命中归 其他。
_GEN_MINOR = {
    '标准规范': {
        '国标': ['gb', 'gb/t', '国家标准', '国标'],
        '行标': ['sy/t', '石油行业标准', '行业标准', '行标', '能源标准', '能源行业'],
        '企标': ['企标', '企业标准', 'q/sh', 'q/s'],
        '图式编制': ['图式', '图例', '编制图', '图件'],
    },
    '项目管理': {
        '课题设计': ['课题', '立项', '开题', '申报书', '可行性', '论证', '设计书'],
        '实施方案': ['实施', '方案', '技术路线', '研究计划', '运行', '部署'],
        '研究报告': ['结题', '验收', '中期', '总结', '报告', '年度', '进展'],
    },
    '软件工具': {
        'Techlog': ['techlog'],
        'Geolog': ['geolog'],  # 实际由 _SOFTWARE_RE 词边界匹配，避免 geology 误中
        'LEAD': ['lead测井', 'lead平台', 'lead软件'],
        'Paradigm': ['paradigm', 'eps'],
        '其他专业软件': ['petrel', 'landmark', 'discovery', 'jason', 'logview', 'geooffice',
                      '测井软件', '专业软件', '解释软件'],
    },
}

# 通用知识 - 额外高精触发（优先于技术域，体现"油气通用知识"而非测井方法/地质本身）
#   标准规范：关于测井及油气相关的规范/规程/标准规范（不含"标准"单独，避免 标准层/标准图版 误判）
_STANDARD = ['规范', '规程', '标准规范']
#   项目管理：测井地质研究的课题设计/实施/方案等（非预算/合同/软件类）
_PROJ_RESEARCH = ['课题', '立项', '开题', '结题', '验收', '技术路线', '实施方案', '项目设计', '课题设计',
                 '申报书', '可行性研究', '论证', '研究计划', '中期检查', 'project proposal', 'proposal']
#   软件工具：测井专业软件（Techlog/Geolog/LEAD/Paradigm 等）。
#   英文软件名用词边界正则，避免 geology/geological 误中 geolog；lead 避免 lead-in 误中。
_SOFTWARE_CN = ['测井软件', '专业软件', '解释软件', '测井平台', 'lead测井', 'lead软件']
_SOFTWARE_RE = re.compile(r'(?i)\b(?:techlog|geolog|paradigm|petrel|landmark|discovery|jason|logview|geooffice|lead)\b')

# 领域判定触发词（命中即归属该领域；地质优先于测井，保证地质为一等类）
# 通用行政/杂项（无技术要素时才判通用，否则会被技术词抢占）
_GEN_ONLY = ['预算', '财务', '审计', '经费', '研讨', '通知', '合同', '招标', '申报', '核算', '制度',
           '年报', 'annual report', '检查', '要求', '意见', '细则', '科技处', '会议', '总结', '计划',
           '规划', '论文', '写作', '如何写', '怎样写']
# 地质专属信号（基本只在地质地语境出现）
_GEO_ONLY = ['沉积', '三角洲', '滩坝', '层序', '不整合', '年代地层', '旋回', '砂体', '构造', '断裂', '断层',
           '褶皱', '裂缝', '地应力', '孔隙压力', '岩性', '岩石', '矿物', '碳酸盐', '白云岩', '灰岩', '砂岩',
           '泥岩', '页岩', '火山岩', '变质岩', '煤岩', '数学地质', '烃源', '生油', '源岩', '油气藏', '圈闭',
           '盖层', '运移', '含油气', '油藏', '气藏', '油气系统', '煤层气', '页岩气', '页岩油', '致密',
           '非常规', '天然气水合物', '成岩', '水淹层', '储集体', '油藏描述', '地质编图', '地层表', '年代',
           'water flooded', 'shale', 'shale gas', 'geology', 'carbonate', '地质']
# 测井专属信号
_LOG_ONLY = ['仪器', '传感器', '探头', '电极', '探测器', '核磁共振', '核磁', '测井仪', '下井仪', '刻度',
           '标定', 'calibration', 'hardware', 'tool', 'sonde', 'probe', '机械', '电子线路', '采集面板',
           '硬件', '震击器', '配件', '模块', '组件', '推靠', '极板', '线圈', '天线', '发射', '接收',
           '电缆', 'wireline', '常规测井', '裸眼', '完井测井', '生产测井', '测井系列', '测井曲线',
           '测井资料', '组合测井', '双侧向', '微球', '感应', '三组合', '声波测井', '密度测井', '中子测井',
           '自然伽马', '井径', '电阻率', '成像测井', '阵列', 'eilog', 'ait', 'hrla', 'hgns', 'tld', 'mcfl',
           'cmr', 'fmi', 'acquisition', 'depth control', '录井', '气测', '随钻', 'lwd', 'mwd', '地质导向',
           '旋转导向', 'mud logging', 'directional', 'geosteering', '测井', 'logging', 'well log',
           '试油', '试井', 'well test', '解释']


def _blob_has(low: str, lst) -> bool:
    return any(k.lower() in low for k in lst)


def _pick(tech_map: dict, low: str):
    """技类细类按字典定义顺序（已排优先级）取最先命中。"""
    for t in tech_map:
        if _blob_has(low, tech_map[t]):
            return t
    return None


def classify_logging_method(path: str, title: str = '') -> (str, str):
    """测井方法领域的内部分类：返回 (大类 major, 小类 minor)。

    大类（按测井技术类型）：随钻测井 / 生产测井 / 光纤 / 裸眼测井 / 电缆测井 / 解释方法
      —— 命中即取最先（优先级见 _LOG_MAJOR 字典顺序）；全不命中默认 电缆测井（最通用的测井方式）。
    小类（按厂商/来源）：SLB / 贝克休斯 / 哈里伯顿 / CNLC(国内) / 中海油 —— 缺测归 其他。
    """
    low = '%s %s' % (path or '', title or '')
    low = low.lower()
    major = _pick(_LOG_MAJOR, low) or '电缆测井'
    minor = _pick(_LOG_MINOR, low) or '其他'
    return major, minor


def classify_geo_method(path: str, title: str = '') -> (str, str):
    """地质领域的内部分类：返回 (大类 major, 小类 minor)。

    小类 = 技术细分（构造/沉积与地层/岩性与矿物/油气地质/储层地质/非常规地质/其他，沿用 _GEO_TECH）。
    大类 = 由小类向上归并的粗分组（基础地质/油气地质/非常规地质/其他，见 _GEO_MAJOR_MAP）。
    """
    low = '%s %s' % (path or '', title or '')
    low = low.lower()
    minor = _pick(_GEO_TECH, low) or '其他'
    major = _GEO_MAJOR_MAP.get(minor, '其他')
    return major, minor


def classify_general_method(path: str, title: str = '') -> (str, str):
    """通用知识领域（油气通用知识，不属于测井专业）的内部分类：返回 (大类 major, 小类 minor)。

    大类 = 标准规范 / 项目管理 / 软件工具 / 其他（沿用 _GEN_TECH）。
    小类 = 在大类之下的进一步细分：
        标准规范 -> 国标/行标/企标/图式编制
        项目管理 -> 课题设计/实施方案/研究报告（基于测井地质研究项目）
        软件工具 -> Techlog/Geolog/LEAD/Paradigm/其他专业软件
      全不命中归 其他。
    """
    low = '%s %s' % (path or '', title or '')
    low = low.lower()
    major = _pick(_GEN_TECH, low) or '其他'
    minor_map = _GEN_MINOR.get(major, {})
    minor = _pick(minor_map, low) or '其他'
    return major, minor


def classify_knowledge(path: str, title: str = '', category: str = '') -> (str, str, str):
    """返回 (domain, tech_major, tech_minor)，按知识本身技术分类，不按国别。

    本知识库是以测井专业为主的油气知识库：领域 = 测井方法 / 地质 / 通用知识。
    - 测井方法：测井专业技术/方法（× 厂商小类）
    - 地质：以油气地质为主（× 技术细分小类）
    - 通用知识：油气通用知识（不属于测井专业），含 标准规范 / 项目管理 / 软件工具 / 其他

    领域判定优先级（高精「通用内容型」先于「技术域」，确保项目/软件/标准不误归技术方法）：
      1) 标准规范（规范/规程/标准规范）               -> 通用-标准规范
      2) 项目管理（测井地质研究的课题设计/实施/方案） -> 通用-项目管理
      3) 测井专业软件（Techlog/Geolog/LEAD…）         -> 通用-软件工具
      4) 地质专属信号 -> 地质（优先于测井，保证地质为一等类）
      5) 测井专属信号 -> 测井方法
      6) 通用行政/杂项（无技术要素）-> 通用
      7) 兜底 -> 通用-其他
    - category 参数保留兼容（历史调用），本函数不再依据它决定是否分类；国别由 country 列单独承载。
    """
    low = '%s %s' % (path or '', title or '')
    low = low.lower()
    # 1) 标准规范（关于测井及油气相关的规范/规程）
    if _blob_has(low, _STANDARD):
        return DOMAIN_GENERAL, *classify_general_method(path, title)
    # 2) 项目管理（测井地质研究的课题设计/实施/方案）
    if _blob_has(low, _PROJ_RESEARCH):
        return DOMAIN_GENERAL, *classify_general_method(path, title)
    # 3) 测井专业软件（Techlog/Geolog/LEAD…；词边界匹配避免 geology 误中）
    if _blob_has(low, _SOFTWARE_CN) or _SOFTWARE_RE.search(low):
        return DOMAIN_GENERAL, *classify_general_method(path, title)
    # 4) 地质专属信号 -> 地质（优先于测井）
    if _blob_has(low, _GEO_ONLY):
        return DOMAIN_GEO, *classify_geo_method(path, title)
    # 5) 测井专属信号 -> 测井方法
    if _blob_has(low, _LOG_ONLY):
        return DOMAIN_LOGGING, *classify_logging_method(path, title)
    # 6) 通用行政/杂项（无技术要素）
    if _blob_has(low, _GEN_ONLY):
        return DOMAIN_GENERAL, *classify_general_method(path, title)
    # 7) 兜底：通用-其他
    return DOMAIN_GENERAL, '其他', '其他'


def tokenize(text: str) -> str:
    """中文预分词（供 FTS5 unicode61 使用）。"""
    if not text:
        return ''
    if _HAS_JIEBA:
        return ' '.join(t for t in jieba.lcut(text) if t.strip())
    return re.sub(r'([\u4e00-\u9fff])', r' \1 ', text)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8', 'replace')).hexdigest()


def _split_frontmatter(text: str):
    if text.startswith('---'):
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n?', text, re.S)
        if m:
            fm = {}
            for line in m.group(1).splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip()
            return fm, text[m.end():]
    return {}, text


def _chunks(text: str):
    n = len(text)
    if n <= CHUNK_SIZE:
        return [text]
    out, i = [], 0
    while i < n:
        out.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return out


WELL_NOISE_PREFIX = ('layer', 'step', 'swab', 'section', 'table', 'figure', 'fig', 'eq',
                      'well', 'no.', 'test', 'sample', 'zone', 'unit', 'block', 'page',
                      'phase', 'stage', 'case', 'run', 'point', 'interval', 'depth',
                      'ltaf', 'taf', 'utaf', 'gumai', 'sokor', 'baturaja', 'talang',
                      'e1-', 'e2-', 'e3-', 'e5-', 'rop', 'tg', 'gr', 'rt', 'sw', 'por',
                      'perm', 'p10', 'p50', 'p90', 'wob', 'rpm', 'trpm', 'yp', 'pv')


WELL_WHITELIST = set()
try:
    import json as _json
    _wl = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'well_whitelist.json')
    if os.path.exists(_wl):
        WELL_WHITELIST = {re.sub(r'[\s_]+', '-', str(x)).upper()
                          for x in _json.load(open(_wl, encoding='utf-8'))}
except Exception:
    WELL_WHITELIST = set()

STRICT_WELL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9]*?(?:-[A-Za-z0-9]+)*-\d{1,3}[A-Za-z]?$')
STRICT_WELL_RE2 = re.compile(r'^[A-Za-z0-9]+-[A-Za-z0-9]+-\d{1,3}[A-Za-z]?$')


def valid_well_name(name: str) -> bool:
    """井名校验：白名单优先，或严格"字母-NN"格式；拒绝 Layer 3/GR 156/SW 100 等噪声。"""
    n = str(name or '').strip()
    if not (3 <= len(n) <= 25):
        return False
    low = n.lower()
    if any(low.startswith(p) for p in WELL_NOISE_PREFIX):
        return False
    if not re.search(r'\d', n):
        return False
    if canon_well(n) in WELL_WHITELIST:
        return True
    return bool(STRICT_WELL_RE.match(n) or STRICT_WELL_RE2.match(n))


def canon_well(name: str) -> str:
    return re.sub(r'[\s_]+', '-', str(name or '').strip()).upper()


def _find_entities(text: str, fm: dict):
    wells = set()
    for m in WELL_RE.finditer(text[:20000]):
        w = m.group(1).strip()
        if valid_well_name(w):
            wells.add(w)
    if fm.get('well_name') and valid_well_name(str(fm['well_name'])):
        wells.add(str(fm['well_name']).strip())
    countries = {c for c in COUNTRIES if c in text[:5000]}
    if fm.get('country'):
        countries.add(str(fm['country']).strip())
    return wells, countries


def ingest_markdown(conn, path: str, force: bool = False) -> str:
    """入库一个 md 文件；返回 doc_id（已存在且未 force 时返回原 id）。"""
    mtime = os.path.getmtime(path)
    raw = open(path, encoding='utf-8', errors='replace').read()
    sha1 = _sha1(raw)
    row = conn.execute('SELECT id, sha1, mtime FROM doc WHERE path=?', (path,)).fetchone()
    if row and not force and row[1] == sha1:
        return row[0]
    doc_id = 'DOC:' + hashlib.sha1(path.encode('utf-8', 'replace')).hexdigest()[:16]
    fm, body = _split_frontmatter(raw)
    title = fm.get('title') or os.path.splitext(os.path.basename(path))[0]
    region = fm.get('region') or fm.get('detected_region') or ''
    country = fm.get('country') or detect_country(path, title)
    well = fm.get('well_name') or ''
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    domain, tech_major, tech_minor = classify_knowledge(path, title, ext)

    conn.execute('DELETE FROM chunk WHERE doc_id=?', (doc_id,))
    conn.execute('DELETE FROM doc_fts WHERE doc_id=?', (doc_id,))
    conn.execute('INSERT OR REPLACE INTO doc(id, path, title, category, region, country, well, '
                 'tech_type, tech_minor, sha1, mtime, chars, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (doc_id, path, title, domain, region, country, well, tech_major, tech_minor, sha1, mtime,
                  len(body), json.dumps(fm, ensure_ascii=False)[:4000]))
    for i, ch in enumerate(_chunks(body)):
        cid = '%s#%03d' % (doc_id, i)
        conn.execute('INSERT OR REPLACE INTO chunk(id, doc_id, idx, text, chars) VALUES(?,?,?,?,?)',
                     (cid, doc_id, i, ch, len(ch)))
        conn.execute('INSERT INTO doc_fts(doc_id, title, body, region, well) VALUES(?,?,?,?,?)',
                     (doc_id, tokenize(title), tokenize(ch), region, well))

    # 轻量实体/事实（Well/Field/Formation 归一化；先清本文档旧抽取结果）
    conn.execute('DELETE FROM entity WHERE source_doc=?', (doc_id,))
    conn.execute('DELETE FROM fact WHERE source_doc=?', (doc_id,))
    if extract_entities is not None:
        countries = {c for c in COUNTRIES if c in body[:5000]}
        if fm.get('country'):
            countries.add(str(fm['country']).strip())
        ents = extract_entities(body, fm)
        primary_field = next(iter(ents['Field']), '')
        _fm_well = canon_well(str(fm.get('well_name') or ''))
        for kind, items in ents.items():
            for canon, info in list(items.items())[:30]:
                pref = {'Well': 'WELL', 'Field': 'FIELD', 'Formation': 'FRM'}[kind]
                eid = '%s:%s' % (pref, canon)
                conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, '
                             'props_json, source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                             (eid, kind, info['name'], canon, region,
                              json.dumps({'aliases': sorted(info['aliases'])}, ensure_ascii=False),
                              doc_id, float(info['conf'])))
                if kind == 'Well':
                    if country:
                        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                     'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                     ('FACT:%s:LOCATED_IN:%s' % (eid, _sha1(country)[:8]),
                                      eid, 'LOCATED_IN', 'COUNTRY:%s' % country, '{}',
                                      doc_id, 'frontmatter', 0.8, 'rule:frontmatter'))
                    _single_well = (len(ents['Well']) == 1) or bool(str(fm.get('well_name') or '').strip())
                    _assign_field = bool(primary_field) and _single_well and \
                        (len(ents['Well']) == 1 or canon == _fm_well)
                    if _assign_field:
                        conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                     'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                     ('FACT:%s:IN_FIELD:%s' % (eid, _sha1(primary_field)[:8]),
                                      eid, 'IN_FIELD', 'FIELD:%s' % primary_field, '{}',
                                      doc_id, 'entity', 0.7, 'rule:entity'))
                if kind == 'Field' and country:
                    conn.execute('INSERT OR REPLACE INTO fact(id, subj, rel, obj, props_json, '
                                 'source_doc, source_loc, conf, extractor) VALUES(?,?,?,?,?,?,?,?,?)',
                                 ('FACT:%s:LOCATED_IN:%s' % (eid, _sha1(country)[:8]),
                                  eid, 'LOCATED_IN', 'COUNTRY:%s' % country, '{}',
                                  doc_id, 'entity', 0.7, 'rule:entity'))
        # 国家实体保留
        for c in list(countries)[:5]:
            cid = 'COUNTRY:%s' % c
            conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json, '
                         'source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                         (cid, 'Country', c, cid, c, '{}', doc_id, 0.7))
    else:
        # 兜底：旧逻辑
        wells, countries = _find_entities(body, fm)
        for w in list(wells)[:20]:
            cn = canon_well(w)
            eid = 'WELL:%s' % cn
            conn.execute('INSERT OR REPLACE INTO entity(id, kind, name, canonical, region, props_json, '
                         'source_doc, conf) VALUES(?,?,?,?,?,?,?,?)',
                         (eid, 'Well', w, cn, region, '{}', doc_id, 0.6))
    conn.commit()
    return doc_id


def ingest_file(conn, path: str, force=False) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.md':
        return ingest_markdown(conn, path, force=force)
    if ext == '.docx':
        return _ingest_docx(conn, path, force=force)
    raise ValueError('unsupported: ' + path)


def _ingest_docx(conn, path: str, force=False) -> str:
    """docx → 文本 → 复用 md 入库逻辑（临时不落盘：直接调用内部函数）。"""
    from docx import Document
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    # 表格文本
    for t in doc.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                paras.append(' | '.join(cells))
    body = '\n'.join(paras)
    doc_id = 'DOC:' + hashlib.sha1(path.encode('utf-8', 'replace')).hexdigest()[:16]
    title = os.path.splitext(os.path.basename(path))[0]
    country = detect_country(path, title)
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    domain, tech_major, tech_minor = classify_knowledge(path, title, ext)
    cat = domain
    row = conn.execute('SELECT id, sha1 FROM doc WHERE path=?', (path,)).fetchone()
    sha1 = _sha1(body)
    if row and not force and row[1] == sha1:
        return row[0]
    conn.execute('DELETE FROM chunk WHERE doc_id=?', (doc_id,))
    conn.execute('DELETE FROM doc_fts WHERE doc_id=?', (doc_id,))
    conn.execute('INSERT OR REPLACE INTO doc(id, path, title, category, region, country, well, '
                 'tech_type, tech_minor, sha1, mtime, chars, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (doc_id, path, title, cat, '', country, '', tech_major, tech_minor, sha1, os.path.getmtime(path),
                  len(body), '{}'))
    for i, ch in enumerate(_chunks(body)):
        cid = '%s#%03d' % (doc_id, i)
        conn.execute('INSERT OR REPLACE INTO chunk(id, doc_id, idx, text, chars) VALUES(?,?,?,?,?)',
                     (cid, doc_id, i, ch, len(ch)))
        conn.execute('INSERT INTO doc_fts(doc_id, title, body, region, well) VALUES(?,?,?,?,?)',
                     (doc_id, tokenize(os.path.basename(path)), tokenize(ch), '', ''))
    conn.commit()
    return doc_id


def ingest_directory(conn, root: str, limit: int | None = None, force=False,
                     exts=('.md', '.docx')) -> dict:
    """递归入库目录（默认 md/docx），返回统计。"""
    ok, fail = 0, []
    n = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ('__pycache__', '.git', 'node_modules')]
        for f in sorted(fn):
            if f.startswith('~$') or f.startswith('.'):
                continue
            if not f.lower().endswith(exts):
                continue
            p = os.path.join(dp, f)
            try:
                ingest_file(conn, p, force=force)
                ok += 1
            except Exception as e:
                fail.append((p, '%s: %s' % (type(e).__name__, e)))
            n += 1
            if limit and n >= limit:
                return {'ok': ok, 'fail': len(fail), 'errors': fail[:10], 'stopped_at_limit': limit}
    return {'ok': ok, 'fail': len(fail), 'errors': fail[:10]}
