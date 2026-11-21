"""绘图区图头（header）的字段化读写。

【R80 交互绘图】
井信息文件 `<井名>info.json` 按**中文分组**组织，是图头文字的天然来源：

    井信息/  日期/  坐标/  海拔/  钻机/  人员/  井深/
    地质设计/  泥浆信息/  测量记录/  图表标题/  免责声明/

本模块负责：
  - 把分组井信息展平成"可编辑字段清单"（label + 取值路径）；
  - 写回时**保持原有分组结构**，只覆盖被编辑的那个键；
  - 提供扁平视图供画布顶部图头条实时显示。

与静态出图同源：`logvis._load_well_info_json` 每次出图都重读本文件，
所以这里改完，交互画布与后续的快速图/综合图**同时生效**。
"""
from __future__ import annotations

import json
import os

#: 字段键 → 中文标签（未登记的字段回退显示键名本身）
FIELD_LABELS = {
    # 井信息
    'company': '业主公司', 'well_name': '井名', 'field_name': '区块',
    'area': '区域', 'country': '国家', 'classification': '井别',
    'service_company_name': '服务公司', 'state_or_province': '州/省',
    'permanent_datum': '永久基准面',
    # 日期
    'spud_date': '开钻日期', 'td_date': '完钻日期', 'log_date': '测井日期',
    'process_date': '处理日期',
    # 坐标
    'latitude': '纬度', 'longitude': '经度',
    'x_coordinate': 'X 坐标', 'y_coordinate': 'Y 坐标',
    # 海拔
    'elevation_gl': '地面海拔', 'elevation_kb': '补心海拔', 'elevation_df': '海拔偏移',
    # 钻机
    'rig_name': '钻机名', 'logging_unit': '测井单位', 'equipment_no': '设备号',
    # 人员
    'processed_by': '解释工程师', 'corrected_by': '校正工程师',
    'field_recorded_by': '记录人', 'field_witnessed_by': '见证人',
    # 井深
    'start_depth': '起始深度', 'stop_depth': '终止深度',
    'total_depth_driller': '钻井总深', 'total_depth_logger': '测井总深',
    # 地质设计
    'target_formation': '目的层', 'well_type': '井型',
    'designed_td': '设计井深', 'structure': '构造位置',
    # 泥浆
    'drilling_fluid_type': '泥浆类型', 'drilling_fluid_density': '泥浆密度',
    'drilling_fluid_viscosity': '泥浆粘度', 'drilling_fluid_ph': '泥浆 PH',
    'drilling_fluid_loss': '失水',
    'rm_meas_temp': '测量温度电阻率', 'rmf_meas_temp': '滤液电阻率',
    'rmc_meas_temp': '泥饼电阻率', 'rm_bht': '井底温度电阻率',
    # 测量记录
    'bit_size': '钻头尺寸', 'time_since_circulation': '循环时间',
    'max_record_temp': '最高记录温度',
    'casing_record': '套管记录', 'borehole_record': '井眼记录',
    # 图表标题
    'ql_title': '快速图标题', 'cmpt_title': '综合图标题',
    'xplot_title': '交会图标题', 'footer_text': '页脚文字',
    # 免责声明
    'disclaimer': '免责声明',
}

#: 这些分组在图头编辑面板中优先展示（其余分组仍可编辑，只是排在后面）
PRIORITY_SECTIONS = ('井信息', '日期', '井深', '图表标题', '坐标', '海拔',
                      '钻机', '人员', '地质设计', '泥浆信息', '测量记录', '免责声明')


class HeaderField:
    """一个可编辑的图头字段。"""

    __slots__ = ('section', 'key', 'label', 'value', 'group')

    def __init__(self, section: str, key: str, label: str, value: str, group: str = ''):
        self.section = section
        self.key = key
        self.label = label
        self.value = value
        self.group = group

    @property
    def path(self) -> str:
        return f'{self.section}/{self.key}'

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f'<HeaderField {self.path}={self.value!r}>'


def flatten_info(info: dict) -> dict:
    """分组井信息 → 扁平 dict（跳过 _ 开头的说明键与空值）。

    与 `logvis._flatten_well_info_cfg` 语义一致，保证交互画布取到的值
    与静态出图取到的值相同。
    """
    out: dict = {}
    if not isinstance(info, dict):
        return out
    for sec, vals in info.items():
        if sec.startswith('_') or not isinstance(vals, dict):
            continue
        for k, v in vals.items():
            if k.startswith('_'):
                continue
            if v is None or v == '':
                continue
            out[k] = v
    return out


def load_header_fields(info: dict) -> list[HeaderField]:
    """井信息 → 可编辑字段清单（按优先级分组排序）。"""
    fields: list[HeaderField] = []
    if not isinstance(info, dict):
        return fields
    for sec, vals in info.items():
        if sec.startswith('_') or not isinstance(vals, dict):
            continue
        for k, v in vals.items():
            if k.startswith('_'):
                continue
            fields.append(HeaderField(
                section=sec, key=k,
                label=FIELD_LABELS.get(k, k),
                value='' if v is None else str(v),
                group=sec))
    order = {s: i for i, s in enumerate(PRIORITY_SECTIONS)}
    fields.sort(key=lambda f: (order.get(f.section, 99), f.section, f.key))
    return fields


def field_value(info: dict, section: str, key: str) -> str:
    """取分组井信息里的某个字段值（扁平视图，找不到返回空串）。"""
    flat = flatten_info(info)
    v = flat.get(key, '')
    return '' if v is None else str(v)


def save_header_field(info_path: str, section: str, key: str, value: str) -> bool:
    """写回单个图头字段（保持分组结构，其余字段不动）。"""
    if not info_path or not section or not key:
        return False
    data: dict = {}
    if os.path.exists(info_path):
        try:
            with open(info_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    grp = data.get(section)
    if not isinstance(grp, dict):
        grp = {}
    grp[key] = value
    data[section] = grp
    try:
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def save_header_fields(info_path: str, values: dict) -> bool:
    """批量写回（values: {(section, key): value}）。"""
    if not info_path:
        return False
    ok = True
    for (section, key), val in (values or {}).items():
        ok = save_header_field(info_path, section, key, val) and ok
    return ok


def header_summary(info: dict, depth_unit: str = 'm', scale_text: str = '') -> list[str]:
    """画布顶部图头条的文本行（井名 / 图题 / 深度范围 / 比例尺）。"""
    flat = flatten_info(info)
    lines: list[str] = []
    well = str(flat.get('well_name', '') or '').strip()
    if well:
        lines.append(well)
    for k in ('ql_title', 'cmpt_title'):
        t = str(flat.get(k, '') or '').strip()
        if t:
            lines.append(t)
            break
    sp, ep = flat.get('start_depth'), flat.get('stop_depth')
    if sp is not None and ep is not None:
        try:
            lines.append(f'深度 {float(sp):.1f}–{float(ep):.1f} {depth_unit}')
        except (TypeError, ValueError):
            pass
    if scale_text:
        lines.append(scale_text)
    return lines
