# -*- coding: utf-8 -*-
"""变量字典库（Variable Catalog）—— Techlog 式「族 → 分支变量 → 图例」元数据库。

【R87】用户定案：

* **所有解释产物都是「有语义的曲线变量」**，与原始测井曲线同口径；
* 按 Techlog 模式组织为 **族（group）→ 分支变量（variable）** 两级：
  深度族、电阻率族、岩性族、解释结论族、矿物含量族、气测族、核磁族、
  电成像族……族决定**绘图方式**（线性 / 对数 / 定性代码道 / 谱 / 成像）；
* **专门设一个数据库**：族名、单位、刻度、图例代码都可以在主界面
  「变量库」里增删改，改动持久化；
* **不同族对应不同绘图方式**：岩性族、解释结论族调用各自的**图例**
  （离散代码 → 中文标签 + 颜色），其余族按数值刻度绘制。

持久化
------
``logsys/variable_catalog.json``（结构化 JSON，随源码入库、可 diff、随
git 四同步、换机直接恢复）。选 JSON 而非二进制 SQLite：可读可审查、
不引入 DLL/驱动（本项目已有 fitz/onnxruntime 与 Qt 的 DLL 冲突史）、
用户改动能直接进版本控制。本模块提供等价的 CRUD 接口，逻辑上就是
四张"表"：``groups`` / ``variables`` / ``legends`` / ``prefix_rules``。

兼容口径
--------
``family``（历史字段）保留为**分支变量的显示名**（如 GR → "自然伽马"），
新的族名放在 ``group`` / ``group_id``。这样既满足"按族组织"，
又不破坏既有属性面板、条件选择与回归测试。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

# --------------------------------------------------------------------------
# 持久化位置
# --------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(_HERE, 'variable_catalog.json')
SCHEMA_VERSION = 'R87.1'

_LOCK = threading.RLock()
_CACHE: dict | None = None
_CACHE_MTIME: float = -1.0

#: 绘图方式取值（族默认 / 变量可覆盖）
DRAW_MODES = ('linear', 'log', 'qualitative', 'flag', 'spectrum', 'image', 'matrix')
#: 刻度取值（历史字段 scale）
SCALES = ('linear', 'log', 'qualitative', 'flag', 'lin')


def _norm(name: Any) -> str:
    return str(name or '').strip()


def _key(name: Any) -> str:
    return _norm(name).upper()


# --------------------------------------------------------------------------
# 默认库（种子）：族
#   id / 族名 / 绘图方式 / 默认单位 / 图例 / 族色 / 顺序 / 说明
# --------------------------------------------------------------------------

_DEFAULT_GROUPS: list[tuple] = [
    ('DEPTH', '深度族', 'linear', 'm', '', '#37474f', 1, 'MD / TVD / TVDSS 等深度基准'),
    ('RAD', '放射性族', 'linear', 'API', '', '#4c9a4c', 2, '自然伽马、光电效应等放射性曲线'),
    ('RES', '电阻率族', 'log', 'ohm.m', '', '#b03030', 3, '深/中/浅电阻率，默认对数刻度'),
    ('POR', '孔隙度/物性族', 'linear', 'v/v', '', '#2f6f9f', 4, '中子、密度、声波、孔隙度及其校正'),
    ('SAT', '饱和度族', 'linear', 'v/v', '', '#1a9850', 5, '含水/含油/含气饱和度'),
    ('MIN', '矿物/组分族', 'linear', 'v/v', '', '#795548', 6, '逐点矿物含量 VOL_*、泥质/粘土含量'),
    ('LITH', '岩性族', 'qualitative', '', 'LITHOLOGY', '#8e44ad', 7,
     '岩性定名与岩心录井，离散代码道 → 岩性图例'),
    ('INTERP', '解释结论族', 'qualitative', '', 'INTERPRETATION', '#d35400', 8,
     '流体/储层解释结论，离散代码道 → 解释结论图例'),
    ('GAS', '气测族', 'linear', 'ppm', '', '#e67e22', 9, 'C1–C5、图版法 ITP、相对异常曲线'),
    ('NMR', '核磁族', 'spectrum', '', '', '#16a085', 10, 'T2 谱、孔隙度组分、渗透率'),
    ('FMI', '电成像族', 'image', '', '', '#7f8c8d', 11, '微电阻率成像孔隙/溶孔/裂缝'),
    ('CAL', '井径/井斜族', 'linear', 'in', '', '#606060', 12, '井径、钻头尺寸、井斜与方位'),
    ('TOOL', '工具/质量族', 'linear', '', '', '#9e9e9e', 13, '自然电位、张力、温度、质量标记'),
    ('LAYER', '层段/标志族', 'flag', '', 'FLAG', '#607d8b', 14, '层号、层名、套管井段等标志道'),
    ('UNCLASSIFIED', '未分类', 'linear', '', '', '#b0bec5', 99, '尚未登记的曲线'),
]


def _g(t) -> dict:
    gid, name, mode, unit, legend, color, order, note = t
    return {'id': gid, 'name': name, 'draw_mode': mode, 'unit_default': unit,
            'legend_id': legend, 'color': color, 'order': order, 'note': note}


# --------------------------------------------------------------------------
# 默认库（种子）：分支变量
#   key / 显示名(分支) / 族 / 单位 / 刻度 / 图例 / 别名 / 说明
#   —— 显示名与 R85 之前的 family 完全一致，保证回归测试与条件选择不变。
# --------------------------------------------------------------------------

_V: list[tuple] = [
    # 深度族
    ('MD', '测量深度', 'DEPTH', 'm', 'linear', '', [], '主深度基准'),
    ('TVD', '真垂深', 'DEPTH', 'm', 'linear', '', [], ''),
    ('DEPTH', '深度', 'DEPTH', 'm', 'linear', '', ['DEPT'], ''),
    # 放射性族
    ('GR', '自然伽马', 'RAD', 'API', 'linear', '', ['GR_API', 'GAMMA'], ''),
    ('PE', '光电效应', 'RAD', 'b/e', 'linear', '', ['PEF'], ''),
    # 电阻率族
    ('RT', '电阻率', 'RES', 'ohm.m', 'log', '', [], ''),
    ('LLD', '深电阻率', 'RES', 'ohm.m', 'log', '', ['RD', 'RDEP'], ''),
    ('LLS', '浅电阻率', 'RES', 'ohm.m', 'log', '', ['RS', 'RSHAL'], ''),
    ('MSFL', '微电阻率', 'RES', 'ohm.m', 'log', '', ['RXO'], ''),
    ('RTI', '侵入带电阻率', 'RES', 'ohm.m', 'log', '', [], ''),
    ('NDI', '侵入带电导率', 'RES', 'mS/m', 'linear', '', [], ''),
    # 孔隙度/物性族
    ('DEN', '密度', 'POR', 'g/cm3', 'linear', '', ['RHOB', 'RHOZ'], ''),
    ('CNL', '中子', 'POR', 'v/v', 'linear', '', ['NPHI', 'CNL'], ''),
    ('DT', '声波时差', 'POR', 'us/ft', 'linear', '', ['DTC', 'DTCO'], ''),
    ('POR', '孔隙度', 'POR', 'v/v', 'linear', '', ['PHIT'], ''),
    ('PHI', '有效孔隙度', 'POR', 'v/v', 'linear', '', ['PHIE'], ''),
    ('NPOR', '中子孔隙度(解释)', 'POR', 'v/v', 'linear', '', [], '解释产物'),
    ('DRHO', '密度校正', 'POR', 'g/cm3', 'linear', '', [], ''),
    ('PERM', '渗透率', 'POR', 'mD', 'log', '', ['K'], ''),
    # 饱和度族
    ('SW', '含水饱和度', 'SAT', 'v/v', 'linear', '', ['SWB'], ''),
    ('So', '含油饱和度', 'SAT', 'v/v', 'linear', '', ['SXO'], ''),
    ('Sg', '含气饱和度', 'SAT', 'v/v', 'linear', '', [], ''),
    # 矿物/组分族 —— 解释产物（逐点数值曲线）
    ('VSH', '泥质含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VClay', '粘土含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VQuartz', '石英含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VCalcite', '方解石含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VDolomite', '白云石含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('GSI', '岩性指数', 'MIN', '', 'linear', '', [], ''),
    ('CGI', '几何因子', 'MIN', '', 'linear', '', [], ''),
    ('VOL_CALCITE', '方解石含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_DOLOM', '白云石含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_ANHY', '硬石膏含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_HALITE', '盐岩含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_ILLITE', '伊利石含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_QUARTZ', '石英含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    ('VOL_CLAY', '粘土含量', 'MIN', 'v/v', 'linear', '', [], '解释产物'),
    # 岩性族 —— 解释产物（离散代码道 → 岩性图例）
    ('LITHOLOGY', '岩性', 'LITH', '', 'qualitative', 'LITHOLOGY', ['LITH'], '解释产物'),
    ('LITHOLOGY_MC', '岩性定名(蒙特卡洛)', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('CORE_LITH', '岩心录井岩性', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('CORE_ZONE_LITH', '岩心分层岩性', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('LITHO_QE', '岩性(QE)', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('LITHO_QE1', '岩性(QE1)', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('FACIES', '沉积相', 'LITH', '', 'qualitative', 'LITHOLOGY', [], '解释产物'),
    ('LITH_MC_CONF', '岩性置信度', 'LITH', '', 'linear', '', [], '数值覆盖族默认'),
    # 解释结论族 —— 解释产物（离散代码道 → 解释结论图例）
    ('INTERPRETATION', '解释结论', 'INTERP', '', 'qualitative', 'INTERPRETATION',
     ['FLUID_FINAL', 'FLUID_IDENTIFICATION', 'PLATE_FLUID'], '解释产物'),
    ('FLUID_FINAL', '最终流体结论', 'INTERP', '', 'qualitative', 'INTERPRETATION', [], '解释产物'),
    ('PLATE_FLUID', '图版流体结论', 'INTERP', '', 'qualitative', 'INTERPRETATION', [], '解释产物'),
    # 气测族
    ('C1', '甲烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('C2', '乙烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('C3', '丙烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('IC4', '异丁烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('NC4', '正丁烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('IC5', '异戊烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('NC5', '正戊烷', 'GAS', 'ppm', 'linear', '', [], ''),
    ('ITP', '气测图版结论', 'GAS', '', 'qualitative', 'INTERPRETATION',
     ['GAS_ITP'], '解释产物：图版法定性结论（DRY/GAS/OIL…），调解释结论图例'),
    ('GAS_ANOM', '气测相对异常', 'GAS', '', 'linear', '', [], '解释产物'),
    ('GAS_ANOM_RATIO', '气测相对异常比', 'GAS', '', 'linear', '', [], '解释产物'),
    ('TGAS', '全烃', 'GAS', 'ppm', 'linear', '', ['TOTAL_GAS'], ''),
    # 核磁族
    ('TCMR', '核磁总孔隙度', 'NMR', 'v/v', 'linear', '', ['NMR_POR'], '解释产物'),
    ('FFI', '自由流体孔隙度', 'NMR', 'v/v', 'linear', '', ['NMR_FFI'], '解释产物'),
    ('BVI', '束缚流体孔隙度', 'NMR', 'v/v', 'linear', '', ['NMR_BVI'], '解释产物'),
    ('NMR_CBW', '粘土束缚水孔隙度', 'NMR', 'v/v', 'linear', '', ['CBW'], '解释产物'),
    ('T2LM', 'T2 几何均值', 'NMR', 'ms', 'log', '', ['T2_GM'], '解释产物'),
    ('NMR_T1', 'T1 弛豫时间', 'NMR', 'ms', 'log', '', [], '解释产物'),
    ('NMR_D', '扩散系数', 'NMR', 'um2/ms', 'log', '', [], '解释产物'),
    ('NMR_PERM', '核磁渗透率', 'NMR', 'mD', 'log', '', [], '解释产物'),
    ('NMR_PERM_SDR', '核磁渗透率(SDR)', 'NMR', 'mD', 'log', '', [], '解释产物'),
    ('NMR_PERM_COATES', '核磁渗透率(Coates)', 'NMR', 'mD', 'log', '', [], '解释产物'),
    ('NMR_IV03_1', '区间孔隙度 0.3-1ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV1_10', '区间孔隙度 1-10ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV10_33', '区间孔隙度 10-33ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV33_100', '区间孔隙度 33-100ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV100_300', '区间孔隙度 100-300ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV300_1000', '区间孔隙度 300-1000ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    ('NMR_IV1000_3000', '区间孔隙度 1000-3000ms', 'NMR', 'v/v', 'linear', '', [], '解释产物'),
    # 电成像族
    ('FMI_POROSITY', '成像孔隙度', 'FMI', 'v/v', 'linear', '', [], '解释产物'),
    ('FMI_VUG', '溶孔密度', 'FMI', '', 'linear', '', [], '解释产物'),
    ('FMI_FRAC', '裂缝密度', 'FMI', '', 'linear', '', [], '解释产物'),
    # 井径/井斜族
    ('CAL', '井径', 'CAL', 'in', 'linear', '', ['CALI'], ''),
    ('CALS', '井径（计算）', 'CAL', 'in', 'linear', '', [], ''),
    ('BS', '钻头尺寸', 'CAL', 'in', 'linear', '', [], ''),
    ('AZIM', '方位角', 'CAL', 'deg', 'linear', '', [], ''),
    ('DEVI', '井斜', 'CAL', 'deg', 'linear', '', [], ''),
    # 工具/质量族
    ('SP', '自然电位', 'TOOL', 'mV', 'linear', '', [], ''),
    ('TENS', '张力', 'TOOL', 'lbf', 'linear', '', [], ''),
    ('SPED', '井底温度', 'TOOL', 'degC', 'linear', '', [], ''),
    ('MTEM', '测量温度', 'TOOL', 'degC', 'linear', '', [], ''),
    # 层段/标志族
    ('LAYER_ID', '层号', 'LAYER', '', 'flag', 'FLAG', [], '解释产物'),
    ('LAYER_LABEL', '层名', 'LAYER', '', 'flag', 'FLAG', [], '解释产物'),
    ('IS_CASING', '套管井段', 'LAYER', '', 'flag', 'FLAG', [], ''),
    ('VALID_CURVES_COUNT', '有效曲线数', 'LAYER', '', 'flag', 'FLAG', [], ''),
]


def _v(t) -> dict:
    key, name, gid, unit, scale, legend, aliases, note = t
    return {'key': _key(key), 'name': name, 'group_id': gid, 'unit': unit,
            'scale': scale, 'legend_id': legend, 'aliases': aliases, 'note': note}


# --------------------------------------------------------------------------
# 默认库（种子）：图例
#   codes: [代码, 中文标签, 颜色]；代码可有多个别名（用 | 分隔）
# --------------------------------------------------------------------------

_DEFAULT_LEGENDS: list[dict] = [
    {'id': 'LITHOLOGY', 'name': '岩性图例', 'note': '岩性族定性道使用',
     'codes': [
         ['SANDSTONE|砂岩|SS|SAND', '砂岩', '#f4d03f'],
         ['SILTSTONE|粉砂岩|粉砂', '粉砂岩', '#d2b4de'],
         ['SHALE|泥岩|SH|MUDSTONE', '泥岩', '#7f8c8d'],
         ['CARBONACEOUS_SHALE|碳质泥岩|炭质泥岩', '碳质泥岩', '#4d5656'],
         ['CLAY|粘土|黏土', '粘土', '#a04000'],
         ['LIMESTONE|灰岩|石灰岩|LS|LIME', '灰岩', '#85c1e9'],
         ['DOLOMITE|白云岩|DOL', '白云岩', '#af7ac5'],
         ['MARL|泥灰岩', '泥灰岩', '#a3e4d7'],
         ['ANHYDRITE|硬石膏|ANHY', '硬石膏', '#f5b7b1'],
         ['HALITE|盐岩|岩盐|SALT', '盐岩', '#fdfefe'],
         ['GYPSUM|石膏', '石膏', '#fadbd8'],
         ['CONGLOMERATE|砾岩', '砾岩', '#e59866'],
         ['COAL|煤|煤层', '煤层', '#212f3d'],
         ['IGNEOUS|火成岩|岩浆岩', '火成岩', '#c0392b'],
         ['OTHER|其它|其他|UNKNOWN', '其它', '#eceff1'],
     ]},
    {'id': 'INTERPRETATION', 'name': '解释结论图例', 'note': '解释结论族定性道使用',
     'codes': [
         ['OIL|油层|OIL_LAYER', '油层', '#1a9850'],
         ['GAS|气层|GAS_LAYER', '气层', '#d73027'],
         ['WATER|水层|WATER_LAYER', '水层', '#00a8f8'],
         ['OIL_POSSIBLE|弱油|油水过渡|含油可能', '弱油/油水过渡', '#a6d96a'],
         ['GAS_POSSIBLE|含气可能|弱气', '含气可能', '#fc8d59'],
         ['OIL_WATER|油水同层|油水层', '油水同层', '#66c2a5'],
         ['GAS_WATER|气水同层|气水层', '气水同层', '#fdae61'],
         ['DRY|干层|致密层|致密|TIGHT', '干层/致密层', '#bdbdbd'],
         ['OTHER|非储层|其它|其他|UNKNOWN', '非储层', '#eceff1'],
     ]},
    {'id': 'FLAG', 'name': '标志图例', 'note': '层段/标志族使用',
     'codes': [
         ['CASING|套管|套管井段', '套管井段', '#607d8b'],
         ['LAYER|层|层界', '层界', '#8d6e63'],
         ['GOOD|有效|合格', '有效', '#2e7d32'],
         ['BAD|无效|不合格', '无效', '#c62828'],
     ]},
]

#: 前缀规则（未精确登记的曲线按前缀归族，与 R85 语义一致）
_DEFAULT_PREFIX_RULES: list[dict] = [
    {'prefix': 'VOL_', 'name': '矿物含量', 'group_id': 'MIN', 'unit': 'v/v',
     'scale': 'linear', 'legend_id': ''},
    {'prefix': 'LITHOLOGY', 'name': '岩性解释', 'group_id': 'LITH', 'unit': '',
     'scale': 'qualitative', 'legend_id': 'LITHOLOGY'},
    {'prefix': 'LITH_', 'name': '岩性解释', 'group_id': 'LITH', 'unit': '',
     'scale': 'qualitative', 'legend_id': 'LITHOLOGY'},
    {'prefix': 'CORE_LITH', 'name': '岩心岩性', 'group_id': 'LITH', 'unit': '',
     'scale': 'qualitative', 'legend_id': 'LITHOLOGY'},
    {'prefix': 'INTERPRET', 'name': '解释结论', 'group_id': 'INTERP', 'unit': '',
     'scale': 'qualitative', 'legend_id': 'INTERPRETATION'},
    {'prefix': 'FLUID_', 'name': '解释结论', 'group_id': 'INTERP', 'unit': '',
     'scale': 'qualitative', 'legend_id': 'INTERPRETATION'},
    {'prefix': 'FMI_', 'name': '电成像解释', 'group_id': 'FMI', 'unit': '',
     'scale': 'linear', 'legend_id': ''},
    {'prefix': 'T2_', 'name': '核磁 T2 谱', 'group_id': 'NMR', 'unit': 'ms',
     'scale': 'linear', 'legend_id': ''},
    {'prefix': 'GAS_', 'name': '气测解释', 'group_id': 'GAS', 'unit': '',
     'scale': 'linear', 'legend_id': ''},
]

_DEFAULT_INTERNAL = [
    '_POROSITY_VALID', 'SPRING_QC', 'VSH_PREV', 'VSH_GR_CAL',
    'INTERPRETATION_SCORE', 'DISTANCE', 'HIT_RATE', 'DIRECTION_SCORE',
    'BETTER_COUNT', 'PHI_DISP', 'SW_DISP', 'RHOB_corrected', 'MSFL_corrected',
]

_DEFAULT_UNIT_HINTS = {
    'GR': 'API', 'DEN': 'g/cm3', 'CNL': 'v/v', 'DT': 'us/ft',
    'RT': 'ohm.m', 'CAL': 'in', 'PE': 'b/e', 'SP': 'mV',
    'POR': 'v/v', 'SW': 'v/v', 'VSH': 'v/v',
}


def default_catalog() -> dict:
    """构造一份全新的默认变量库（不改磁盘）。"""
    return {
        'version': SCHEMA_VERSION,
        'groups': [_g(t) for t in _DEFAULT_GROUPS],
        'variables': [_v(t) for t in _V],
        'legends': [dict(x, codes=[list(c) for c in x['codes']]) for x in _DEFAULT_LEGENDS],
        'prefix_rules': [dict(x) for x in _DEFAULT_PREFIX_RULES],
        'internal_columns': list(_DEFAULT_INTERNAL),
        'unit_hints': dict(_DEFAULT_UNIT_HINTS),
    }


# --------------------------------------------------------------------------
# 读写 / 缓存
# --------------------------------------------------------------------------

def _atomic_write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.vc_', suffix='.json',
                               dir=os.path.dirname(path) or '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def get_catalog(refresh: bool = False) -> dict:
    """取当前变量库（带缓存；文件被外部改动会自动重载）。"""
    global _CACHE, _CACHE_MTIME
    with _LOCK:
        try:
            mt = os.path.getmtime(CATALOG_PATH)
        except OSError:
            mt = -1.0
        if _CACHE is not None and not refresh and mt == _CACHE_MTIME:
            return _CACHE
        data = None
        if os.path.isfile(CATALOG_PATH):
            try:
                with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = None
        if not isinstance(data, dict) or not data.get('groups'):
            data = default_catalog()
            try:
                _atomic_write(CATALOG_PATH, data)
            except OSError:
                pass
            mt = os.path.getmtime(CATALOG_PATH) if os.path.isfile(CATALOG_PATH) else -1.0
        # 补齐缺键（升级旧库）
        seed = default_catalog()
        for k, v in seed.items():
            data.setdefault(k, v)
        _CACHE, _CACHE_MTIME = data, mt
        return data


def save(catalog: dict | None = None) -> bool:
    """把库写回磁盘；None 表示保存当前缓存。"""
    global _CACHE, _CACHE_MTIME
    with _LOCK:
        data = catalog if catalog is not None else get_catalog()
        if not isinstance(data, dict):
            return False
        data['version'] = SCHEMA_VERSION
        try:
            _atomic_write(CATALOG_PATH, data)
        except OSError:
            return False
        _CACHE = data
        try:
            _CACHE_MTIME = os.path.getmtime(CATALOG_PATH)
        except OSError:
            _CACHE_MTIME = -1.0
        return True


def reset_defaults() -> dict:
    """恢复出厂默认（覆盖磁盘）。"""
    data = default_catalog()
    save(data)
    return data


def as_dict() -> dict:
    """返回库内容的浅拷贝（供 GUI 表格/导出用）。"""
    return json.loads(json.dumps(get_catalog(), ensure_ascii=False))


def import_dict(data: dict) -> bool:
    """整库导入（用于换机恢复 / 批量编辑）。"""
    if not isinstance(data, dict) or not isinstance(data.get('groups'), list):
        return False
    seed = default_catalog()
    for k, v in seed.items():
        data.setdefault(k, v)
    return save(data)


# --------------------------------------------------------------------------
# 表级查询 / CRUD
# --------------------------------------------------------------------------

def groups() -> list[dict]:
    return sorted(get_catalog().get('groups', []), key=lambda g: (g.get('order', 99), g.get('id', '')))


def variables() -> list[dict]:
    return list(get_catalog().get('variables', []))


def legends() -> list[dict]:
    return list(get_catalog().get('legends', []))


def prefix_rules() -> list[dict]:
    return list(get_catalog().get('prefix_rules', []))


def group(group_id: str) -> dict | None:
    gid = _key(group_id)
    for g in groups():
        if _key(g.get('id')) == gid or _norm(g.get('name')) == _norm(group_id):
            return g
    return None


def legend(legend_id: str) -> dict | None:
    lid = _key(legend_id)
    for lg in legends():
        if _key(lg.get('id')) == lid:
            return lg
    return None


def upsert_group(row: dict) -> bool:
    """新增或更新一个族（按 id 匹配）。"""
    gid = _key(row.get('id'))
    if not gid or not _norm(row.get('name')):
        return False
    cat = get_catalog()
    item = {'id': gid, 'name': _norm(row.get('name')),
            'draw_mode': _norm(row.get('draw_mode')) or 'linear',
            'unit_default': _norm(row.get('unit_default')),
            'legend_id': _key(row.get('legend_id')),
            'color': _norm(row.get('color')) or '#607d8b',
            'order': int(row.get('order') or 99), 'note': _norm(row.get('note'))}
    if item['draw_mode'] not in DRAW_MODES:
        item['draw_mode'] = 'linear'
    arr = cat['groups']
    for i, g in enumerate(arr):
        if _key(g.get('id')) == gid:
            arr[i] = item
            break
    else:
        arr.append(item)
    return save(cat)


def delete_group(group_id: str, reassign: str = 'UNCLASSIFIED') -> bool:
    """删除族；其下变量改挂到 reassign 指定的族。"""
    gid = _key(group_id)
    cat = get_catalog()
    before = len(cat['groups'])
    cat['groups'] = [g for g in cat['groups'] if _key(g.get('id')) != gid]
    if len(cat['groups']) == before:
        return False
    target = _key(reassign)
    for v in cat['variables']:
        if _key(v.get('group_id')) == gid:
            v['group_id'] = target
    return save(cat)


def upsert_variable(row: dict) -> bool:
    """新增或更新一个分支变量（按 key 匹配）。"""
    key = _key(row.get('key'))
    if not key:
        return False
    cat = get_catalog()
    aliases = row.get('aliases') or []
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.replace('，', ',').split(',') if a.strip()]
    item = {'key': key, 'name': _norm(row.get('name')) or key,
            'group_id': _key(row.get('group_id')) or 'UNCLASSIFIED',
            'unit': _norm(row.get('unit')),
            'scale': _norm(row.get('scale')) or 'linear',
            'legend_id': _key(row.get('legend_id')),
            'aliases': list(aliases), 'note': _norm(row.get('note'))}
    if item['scale'] not in SCALES:
        item['scale'] = 'linear'
    arr = cat['variables']
    for i, v in enumerate(arr):
        if _key(v.get('key')) == key:
            arr[i] = item
            break
    else:
        arr.append(item)
    return save(cat)


def delete_variable(key: str) -> bool:
    k = _key(key)
    cat = get_catalog()
    before = len(cat['variables'])
    cat['variables'] = [v for v in cat['variables'] if _key(v.get('key')) != k]
    return len(cat['variables']) != before and save(cat)


def upsert_prefix_rule(row: dict) -> bool:
    pfx = _key(row.get('prefix'))
    if not pfx:
        return False
    cat = get_catalog()
    item = {'prefix': pfx, 'name': _norm(row.get('name')) or pfx,
            'group_id': _key(row.get('group_id')) or 'UNCLASSIFIED',
            'unit': _norm(row.get('unit')), 'scale': _norm(row.get('scale')) or 'linear',
            'legend_id': _key(row.get('legend_id'))}
    if item['scale'] not in SCALES:
        item['scale'] = 'linear'
    arr = cat['prefix_rules']
    for i, r in enumerate(arr):
        if _key(r.get('prefix')) == pfx:
            arr[i] = item
            break
    else:
        arr.append(item)
    # 长前缀优先，避免 'LITH_' 抢在 'LITHOLOGY' 前
    arr.sort(key=lambda r: -len(_key(r.get('prefix'))))
    return save(cat)


def delete_prefix_rule(prefix: str) -> bool:
    p = _key(prefix)
    cat = get_catalog()
    before = len(cat['prefix_rules'])
    cat['prefix_rules'] = [r for r in cat['prefix_rules'] if _key(r.get('prefix')) != p]
    return len(cat['prefix_rules']) != before and save(cat)


def upsert_legend(row: dict) -> bool:
    lid = _key(row.get('id'))
    if not lid:
        return False
    cat = get_catalog()
    codes = row.get('codes') or []
    norm_codes = []
    for c in codes:
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            norm_codes.append([_norm(c[0]), _norm(c[1]),
                               _norm(c[2]) if len(c) > 2 else '#b0bec5'])
        elif isinstance(c, dict):
            norm_codes.append([_norm(c.get('code')), _norm(c.get('label')),
                               _norm(c.get('color')) or '#b0bec5'])
    item = {'id': lid, 'name': _norm(row.get('name')) or lid,
            'note': _norm(row.get('note')), 'codes': norm_codes}
    arr = cat['legends']
    for i, lg in enumerate(arr):
        if _key(lg.get('id')) == lid:
            arr[i] = item
            break
    else:
        arr.append(item)
    return save(cat)


def legend_codes(legend_id: str) -> dict[str, tuple[str, str]]:
    """展开图例：``{代码(大写/中文): (中文标签, 颜色)}``。

    一个条目可用 ``A|B|C`` 声明多个别名，全部映射到同一标签与颜色。
    """
    lg = legend(legend_id)
    out: dict[str, tuple[str, str]] = {}
    if not lg:
        return out
    for row in lg.get('codes') or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        label = _norm(row[1]) or _norm(row[0])
        color = _norm(row[2]) if len(row) > 2 else '#b0bec5'
        for alias in _norm(row[0]).split('|'):
            a = alias.strip()
            if a:
                out[a.upper()] = (label, color)
                out[a] = (label, color)
    return out


def legend_for(col: str) -> str:
    """返回该曲线应调用的图例 id（无则 ''）。"""
    info = classify(col)
    return info.get('legend_id') or ''


# --------------------------------------------------------------------------
# 分类（project_model.classify_variable 的唯一事实来源）
# --------------------------------------------------------------------------

def _scale_of(draw_mode: str) -> str:
    return {'qualitative': 'qualitative', 'flag': 'qualitative',
            'log': 'log'}.get(draw_mode, 'linear')


def _mode_of(scale: str) -> str:
    return {'qualitative': 'qualitative', 'flag': 'flag',
            'log': 'log'}.get(scale, 'linear')


def _unknown(key: str, name: str, unit: str = '') -> dict:
    return {'name': name, 'key': key,
            'family': None, 'family_name': None,
            'group': '未分类', 'group_id': 'UNCLASSIFIED',
            'draw_mode': 'linear', 'legend_id': '',
            'unit': unit or None, 'scale': 'linear' if unit else None,
            'kind': 'unknown', 'color': 'warn' if unit else 'error',
            'complete': False, 'description': ''}


def classify(col: Any) -> dict:
    """判定一条曲线的族、分支、单位、刻度与绘图方式。

    返回字段（``family`` 为历史兼容字段，``group`` 才是本次的"族名"）：:

        name/key/family/family_name  —— 变量名与分支显示名（旧语义）
        group/group_id               —— 族名 / 族 id（新语义）
        unit/scale/kind/color/complete
        draw_mode/legend_id          —— 绘图方式与应调用的图例
    """
    name = _norm(col)
    key = _key(col)
    cat = get_catalog()

    if key in {_key(x) for x in cat.get('internal_columns', [])}:
        return {'name': name, 'key': key, 'family': None, 'family_name': None,
                'group': '内部列', 'group_id': 'INTERNAL',
                'draw_mode': 'linear', 'legend_id': '',
                'unit': None, 'scale': None, 'kind': 'internal',
                'color': 'muted', 'complete': False, 'description': '内部质量标记列'}

    gmap = {_key(g.get('id')): g for g in cat.get('groups', [])}
    hit: dict | None = None
    for v in cat.get('variables', []):
        if _key(v.get('key')) == key:
            hit = dict(v)
            break
        if key in {_key(a) for a in (v.get('aliases') or [])}:
            hit = dict(v)
            break
    if hit is None:
        rules = sorted(cat.get('prefix_rules', []),
                       key=lambda r: -len(_key(r.get('prefix'))))
        for r in rules:
            pfx = _key(r.get('prefix'))
            if pfx and key.startswith(pfx):
                hit = {'key': key, 'name': _norm(r.get('name')) or pfx,
                       'group_id': _key(r.get('group_id')),
                       'unit': _norm(r.get('unit')), 'scale': _norm(r.get('scale')),
                       'legend_id': _key(r.get('legend_id')),
                       'aliases': [], 'note': '前缀规则'}
                break
    if hit is not None:
        g = gmap.get(_key(hit.get('group_id'))) or gmap.get('UNCLASSIFIED') or {}
        unit = _norm(hit.get('unit')) or _norm(g.get('unit_default'))
        scale = _norm(hit.get('scale')) or _scale_of(_norm(g.get('draw_mode')))
        draw_mode = _mode_of(scale)          # 变量级刻度优先于族默认
        legend_id = _key(hit.get('legend_id')) or _key(g.get('legend_id'))
        display = _norm(hit.get('name')) or key
        kind = 'qualitative' if scale in ('qualitative', 'flag') else 'curve'
        color = 'ok' if (display and unit) else ('warn' if display else 'error')
        return {'name': name, 'key': key,
                'family': display, 'family_name': display,
                'group': _norm(g.get('name')) or '未分类',
                'group_id': _key(g.get('id')) or 'UNCLASSIFIED',
                'group_color': _norm(g.get('color')) or '#607d8b',
                'draw_mode': draw_mode, 'legend_id': legend_id,
                'unit': unit or None, 'scale': scale, 'kind': kind,
                'color': color, 'complete': bool(unit and display),
                'description': _norm(hit.get('note'))}

    unit = (cat.get('unit_hints') or {}).get(key)
    if unit:
        r = _unknown(key, name, unit)
        r['draw_mode'] = 'linear'
        return r
    return _unknown(key, name)


def group_of(col: Any) -> str:
    """曲线所属族名（绘图分组用）。"""
    return classify(col).get('group') or '未分类'


def draw_mode_of(col: Any) -> str:
    return classify(col).get('draw_mode') or 'linear'


def all_group_names() -> list[str]:
    return [g.get('name', '') for g in groups()]


# --------------------------------------------------------------------------
# CLI 自检
# --------------------------------------------------------------------------

if __name__ == '__main__':
    c = get_catalog()
    print('变量库:', CATALOG_PATH)
    print('族 %d ｜ 变量 %d ｜ 图例 %d ｜ 前缀规则 %d' % (
        len(c['groups']), len(c['variables']), len(c['legends']), len(c['prefix_rules'])))
    for col in ('MD', 'GR', 'RT', 'LITHOLOGY', 'INTERPRETATION',
                'VOL_CALCITE', 'VOL_SOMETHING', 'ZZZ_UNKNOWN'):
        i = classify(col)
        print('  %-18s 族=%-10s 分支=%-16s 单位=%-8s 刻度=%-12s 图例=%s'
              % (col, i['group'], i['family'] or '-', i['unit'] or '-',
                 i['scale'] or '-', i['legend_id'] or '-'))
