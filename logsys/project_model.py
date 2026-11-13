# -*- coding: utf-8 -*-
"""项目-井数据模型：Project → Well → Dataset → Variable 四层树。

借鉴 Techlog 2019.2 Project Browser 的对象模型（见官方帮助：
  Project browser / Common actions、Filter the project browser、
  Techlog project databases、What is a well, dataset and variable），
  映射到本系统的测井解释领域对象：

  | Techlog          | 本系统                                  |
  |------------------|------------------------------------------|
  | Project          | 项目根目录（多井容器，如 output/）         |
  | Well             | 井目录（output/<井名>/）                 |
  | Dataset          | 数据集（产物文件族：曲线/层表/成果LAS…）  |
  | Variable         | 变量（数据集内的曲线列）                  |

设计原则（沿用 logsys 约定）：
- 纯逻辑，不依赖 tkinter，可独立单测；
- 只读扫描，不写项目目录；
- 变量三色规则与 Techlog 一致：
    黑 = 同时具备 family 与 unit；灰 = 缺其一；红 = 两者皆缺。
- 所有阈值来自本模块顶部常量表，调用方不硬编码。
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

# --------------------------------------------------------------------------
# 曲线族定义：Techlog 的 "family" 在本系统对应标准曲线族/解释族。
# family 决定显示方式（对数/线性/岩性填充）与插值策略。
# --------------------------------------------------------------------------

#: 岩石物理标准曲线族：family -> (显示名, 单位, 线性/对数)
ROCK_PHYSICS_FAMILIES: dict[str, tuple[str, str, str]] = {
    'MD':   ('测量深度', 'm', 'linear'),
    'GR':   ('自然伽马', 'API', 'linear'),
    'DEN':  ('密度', 'g/cm3', 'linear'),
    'CNL':  ('中子', 'v/v', 'linear'),
    'DT':   ('声波时差', 'us/ft', 'linear'),
    'RT':   ('电阻率', 'ohm.m', 'log'),
    'CAL':  ('井径', 'in', 'linear'),
    'PE':   ('光电效应', 'b/e', 'linear'),
    'SP':   ('自然电位', 'mV', 'linear'),
    'LLD':  ('深电阻率', 'ohm.m', 'log'),
    'LLS':  ('浅电阻率', 'ohm.m', 'log'),
    'MSFL': ('微电阻率', 'ohm.m', 'log'),
    'PERM': ('渗透率', 'mD', 'log'),
    'TVD':  ('真垂深', 'm', 'linear'),
    'AZIM': ('方位角', 'deg', 'linear'),
    'DEVI': ('井斜', 'deg', 'linear'),
}

#: 派生/解释族：由计算与解释产生，非原始测量曲线
DERIVED_FAMILIES: dict[str, tuple[str, str, str]] = {
    'POR':     ('孔隙度', 'v/v', 'linear'),
    'SW':      ('含水饱和度', 'v/v', 'linear'),
    'So':      ('含油饱和度', 'v/v', 'linear'),
    'Sg':      ('含气饱和度', 'v/v', 'linear'),
    'PHI':     ('有效孔隙度', 'v/v', 'linear'),
    'VSH':     ('泥质含量', 'v/v', 'linear'),
    'VClay':   ('粘土含量', 'v/v', 'linear'),
    'VQuartz': ('石英含量', 'v/v', 'linear'),
    'VCalcite': ('方解石含量', 'v/v', 'linear'),
    'VDolomite': ('白云石含量', 'v/v', 'linear'),
    'RTI':     ('侵入带电阻率', 'ohm.m', 'log'),
    'NDI':     ('侵入带电导率', 'mS/m', 'linear'),
    'GSI':     ('岩性指数', '', 'linear'),
    'CGI':     ('几何因子', '', 'linear'),
}

#: 解释族：定性/结论类变量，对应 Techlog 的 "qualitative log" / "flag curve"
INTERPRETATION_FAMILIES: dict[str, tuple[str, str, str]] = {
    'LITHOLOGY':      ('岩性', '', 'qualitative'),
    'LITH_MC_CONF':   ('岩性置信度', '', 'qualitative'),
    'INTERPRETATION': ('解释结论', '', 'qualitative'),
    'FACIES':         ('沉积相', '', 'qualitative'),
    'LAYER_ID':       ('层号', '', 'flag'),
    'LAYER_LABEL':    ('层名', '', 'flag'),
    'IS_CASING':      ('套管井段', '', 'flag'),
    'VALID_CURVES_COUNT': ('有效曲线数', '', 'flag'),
}

#: 井段/工具族
TOOL_FAMILIES: dict[str, tuple[str, str, str]] = {
    'BS':      ('钻头尺寸', 'in', 'linear'),
    'CALS':    ('井径（计算）', 'in', 'linear'),
    'DRHO':    ('密度校正', 'g/cm3', 'linear'),
    'TENS':    ('张力', 'lbf', 'linear'),
    'SPED':    ('井底温度', 'degC', 'linear'),
    'MTEM':    ('测量温度', 'degC', 'linear'),
}

#: 内部质量标记列（不作为用户变量展示）
INTERNAL_COLUMNS = {
    '_POROSITY_VALID', 'SPRING_QC', 'VSH_PREV', 'VSH_GR_CAL',
    'INTERPRETATION_SCORE', 'DISTANCE', 'HIT_RATE', 'DIRECTION_SCORE',
    'BETTER_COUNT', 'PHI_DISP', 'SW_DISP', 'RHOB_corrected', 'MSFL_corrected',
}

#: 全部族表（查找优先级：岩石物理 > 派生 > 解释 > 工具）
ALL_FAMILIES: dict[str, tuple[str, str, str]] = {
    **ROCK_PHYSICS_FAMILIES, **DERIVED_FAMILIES,
    **INTERPRETATION_FAMILIES, **TOOL_FAMILIES,
}

#: 常见单位别名（用于从 LAS 头或 processed.csv 推断单位）
UNIT_HINTS: dict[str, str] = {
    'GR': 'API', 'DEN': 'g/cm3', 'CNL': 'v/v', 'DT': 'us/ft',
    'RT': 'ohm.m', 'CAL': 'in', 'PE': 'b/e', 'SP': 'mV',
    'POR': 'v/v', 'SW': 'v/v', 'VSH': 'v/v',
}

#: 数据集类型 → Techlog 数据集图标语义
DATASET_TYPES = {
    'curve':    ('连续深度增量曲线集', 'curve'),
    'interval': ('顶底深度边界层集', 'interval'),
    'point':    ('点数据集', 'point'),
    'log':      ('解释成果 LAS', 'log'),
    'table':    ('层段表', 'table'),
    'source':   ('原始测井 LAS', 'source'),
    'meta':     ('井元信息', 'meta'),
    'image':    ('图件', 'image'),
    'report':   ('报告', 'report'),
}

#: 井状态（Techlog 用图标区分；本系统用状态词 + 颜色）
#:
#: 【2026-11-11 修正】原 no_source 的判据是"有源无产物"却标成"缺原始资料"，
#: 语义与标签相反。改为两个**正交维度**：
#:   status      —— 产物的解释完成度（complete/partial/pending/empty）
#:   has_source  —— 是否已关联原始资料（决定能否在项目里做 QuickLook）
#: 混成一个维度会导致正常井被误标为红色错误，故拆开。
WELL_STATUS = {
    'complete':  ('已解释', 'ok'),
    'partial':   ('部分完成', 'warn'),
    'pending':   ('待解释', 'warn'),
    'empty':     ('仅建目录', 'muted'),
}

#: 源资料关联状态 → (标签, 颜色)
SOURCE_STATUS = {
    'linked':    ('已关联', 'ok'),
    'unlinked':  ('缺源', 'error'),
}


def _norm(name: str) -> str:
    """列名归一：去空白、转大写。"""
    return str(name or '').strip().upper()


def classify_variable(col: str) -> dict[str, Any]:
    """判定单个变量（曲线列）的族、单位与 Techlog 三色状态。

    Techlog 规则（官方帮助 Project browser / Common actions）：
      黑色 = 既有 family 又有 unit
      灰色 = 缺 family 或缺 unit 之一
      红色 = 两者皆缺
    """
    key = _norm(col)
    if key in INTERNAL_COLUMNS:
        return {'name': col, 'key': key, 'family': None, 'family_name': None,
                'unit': None, 'scale': None, 'kind': 'internal', 'color': 'muted',
                'complete': False}

    fam = ALL_FAMILIES.get(key)
    if fam:
        display, unit, scale = fam
        color = 'ok' if unit else 'warn'
        return {'name': col, 'key': key, 'family': display, 'family_name': display,
                'unit': unit, 'scale': scale, 'kind': 'curve',
                'color': color, 'complete': bool(unit)}

    # 未登记的列：按命名规则推断单位，仍无族 → 红色
    unit = UNIT_HINTS.get(key)
    if unit:
        return {'name': col, 'key': key, 'family': None, 'family_name': None,
                'unit': unit, 'scale': 'linear', 'kind': 'unknown',
                'color': 'warn', 'complete': False}
    return {'name': col, 'key': key, 'family': None, 'family_name': None,
            'unit': None, 'scale': None, 'kind': 'unknown',
            'color': 'error', 'complete': False}


@dataclass
class Variable:
    """变量（曲线列）。"""
    name: str
    family: str | None = None
    unit: str | None = None
    scale: str | None = None
    kind: str = 'curve'
    color: str = 'error'
    description: str = ''
    source: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Dataset:
    """数据集：一组同类产物（Techlog 的 dataset 概念）。"""
    name: str
    path: str = ''
    dtype: str = 'curve'
    icon: str = 'curve'
    variables: list[Variable] = field(default_factory=list)
    size: int = 0
    mtime: float = 0.0
    n_rows: int = 0
    n_cols: int = 0
    depth_min: float | None = None
    depth_max: float | None = None
    note: str = ''

    @property
    def complete(self) -> bool:
        """Techlog 语义：变量全部齐备（族+单位）才算完整。"""
        vs = [v for v in self.variables if v.kind != 'internal']
        return bool(vs) and all(v.complete for v in vs)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['complete'] = self.complete
        return d


@dataclass
class Well:
    """井：Techlog 的 well 概念。"""
    name: str
    path: str = ''
    datasets: list[Dataset] = field(default_factory=list)
    source_datasets: list[Dataset] = field(default_factory=list)
    info: dict = field(default_factory=dict)
    status: str = 'empty'
    status_label: str = ''
    status_color: str = 'muted'
    source_dir: str = ''
    source_label: str = '缺源'
    source_color: str = 'error'
    depth_min: float | None = None
    depth_max: float | None = None
    layer_count: int = 0
    fluid_dist: dict = field(default_factory=dict)
    last_run: str = ''

    @property
    def complete(self) -> bool:
        return self.status == 'complete'

    @property
    def has_source(self) -> bool:
        """是否已关联到原始资料目录（可在项目里跑 QuickLook / 综合解释）。"""
        return bool(self.source_dir) and os.path.isdir(self.source_dir)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['complete'] = self.complete
        d['has_source'] = self.has_source
        return d


@dataclass
class Project:
    """项目：一组井的容器。"""
    name: str
    path: str = ''
    wells: list[Well] = field(default_factory=list)
    groups: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {'name': self.name, 'path': self.path, 'wells': [w.to_dict() for w in self.wells],
                'groups': self.groups}


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------

#: 井目录识别：目录下出现任一产物即视为井
_WELL_MARKERS = ('*_processed.csv', '*_interpreted.LAS', '*info.json',
                  '*_interpretation_layers.csv', '*_run_manifest.json')

#: 数据集识别规则：glob → (数据集名, 类型)
_DATASET_RULES = [
    ('*_processed.csv',        '解释曲线集',   'curve'),
    ('*_interpreted.LAS',      '解释成果',     'log'),
    ('*_interpretation_layers.csv', '层段表',   'table'),
    ('*_interpretation_layers_ML.csv', '机器学习层表', 'table'),
    ('*_processed_SYT5945_report_*.md', '标准化报告', 'report'),
    ('*_report.html',          '综合报告',     'report'),
    ('*_quicklook_*.pdf',      '快速解释图',   'image'),
    ('*_composite_log_*.pdf',  '综合解释图',   'image'),
    ('*_crossplot_*.pdf',      '交汇图',       'image'),
    ('*info.json',             '井信息',       'meta'),
    ('*_run_manifest.json',    '运行清单',     'meta'),
]

#: 源目录（原始资料）识别规则：glob → (数据集名, 类型)
#:
#: 【2026-11-11】源数据集让"项目里的井"不只有产物、还能看到输入资料，
#: 与 Techlog 的 Well → Dataset 语义对齐（井下挂原始与成果两类数据集）。
_SOURCE_RULES = [
    ('*.las',                  '原始测井 LAS', 'source'),
    ('*_qlpt.json',            '甲方出图格式', 'meta'),
    ('quicklook_config.json',  '甲方出图格式', 'meta'),
    ('*masterlog*.pdf',        '录井图',       'report'),
    ('*Masterlog*.pdf',        '录井图',       'report'),
    ('*.xlsx',                 '试油/测试表',  'report'),
    ('*.xls',                  '试油/测试表',  'report'),
]


def _first(paths: list[str]) -> str:
    return paths[0] if paths else ''


def _latest(paths: list[str]) -> str:
    """取最新一个（按 mtime）。"""
    if not paths:
        return ''
    return max(paths, key=lambda p: os.path.getmtime(p))


def _scan_source_datasets(source_dir: str) -> list[Dataset]:
    """扫描原始资料目录，产出源数据集列表。"""
    out: list[Dataset] = []
    if not source_dir or not os.path.isdir(source_dir):
        return out
    for pattern, ds_name, dtype in _SOURCE_RULES:
        try:
            hits = sorted(glob.glob(os.path.join(source_dir, pattern)))
        except Exception:
            continue
        if not hits:
            continue
        p = _latest(hits)
        try:
            st = os.stat(p)
        except Exception:
            continue
        ds = Dataset(name=ds_name, path=p, dtype=dtype,
                     icon=DATASET_TYPES.get(dtype, ('数据', 'curve'))[1],
                     size=st.st_size, mtime=st.st_mtime)
        if dtype == 'source':
            ds.variables = _scan_variables_from_las(p)
            ds.n_cols = len(ds.variables)
            lo, hi = _depth_range_from_las(p)
            ds.depth_min, ds.depth_max = lo, hi
        out.append(ds)
    return out


def _pick_header_value(cands: list[str]) -> str:
    """从候选值里挑出更像"真值"的那个（而不是冒号右侧的描述文字）。

    LAS 2.0 的写法是 ``WELL.   BET-1   :WELL NAME`` —— 右侧是描述，
    直接取右侧会得到 'WELL NAME' 这种废值。
    """
    cands = [str(c).strip() for c in cands if str(c).strip()]
    if not cands:
        return ''
    for c in cands:
        if any(ch.isdigit() for ch in c):
            return c
    for c in cands:
        if ' ' not in c and c.upper() != c:
            return c
    for c in cands:
        if ' ' not in c:
            return c
    return cands[0]


def _las_w_section(path: str, max_lines: int = 4000) -> dict:
    """解析 LAS 的 ~W 段，返回 ``{MNEM: [候选值, ...]}``。

    兼容两种主流写法：
      - **LAS 1.2**：``WELL : BET-1``              值在冒号**右**侧；
      - **LAS 2.0**：``WELL.   BET-1   :WELL NAME`` 值在冒号**左**侧，
        右侧是描述文字（国内井的 LAS 几乎都是这种）。

    每个字段可能给出多个候选（左值 / 右值），由调用方按需挑选。
    """
    out: dict = {}
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            in_w = False
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                if s.startswith('~'):
                    up = s.upper()
                    if up.startswith('~W'):
                        in_w = True
                        continue
                    if up.startswith('~A'):
                        break
                    if in_w:
                        break
                    continue
                if not in_w:
                    continue
                left, _sep, right = s.partition(':')
                lt = left.split()
                if not lt:
                    continue
                key = lt[0]
                if '.' in key:
                    key = key.split('.')[0]
                key = key.strip().upper()
                if not key:
                    continue
                cands = []
                for tok in lt[1:]:
                    if tok in ('.', ''):
                        continue
                    cands.append(tok)
                if right.strip():
                    cands.append(right.strip().split()[0])
                if cands:
                    out.setdefault(key, []).extend(cands)
    except Exception:
        pass
    return out


def las_well_name(path: str) -> str:
    """从 LAS 的 ~W 段读取井名。读不到返回 ''。

    这是**产物落盘目录名**的决定依据 —— logInt 内部用
    ``Path('output') / well_name`` 定位产物目录，而 ``well_name`` 取自
    LAS 的 ~W 段（取不到时退化为文件名）。因此项目内的井名必须与它一致，
    否则"作业在项目里做 → 产物回到项目树"的闭环会断在命名上。

    实测：源目录 ``RP-13`` 里的 LAS 记录井名为 ``RASHIDPUR_13`` ——
    两者不同，正是需要归集兜底的场景。
    """
    sec = _las_w_section(path)
    for key in ('WELL', 'WELLNAME', 'WELL_NAME', 'WELLID', 'WELL_ID'):
        cands = sec.get(key)
        if cands:
            v = _pick_header_value(cands)
            if v:
                return v
    return ''


def _depth_range_from_las(path: str) -> tuple[float | None, float | None]:
    """从 LAS 估算深度范围（读 ~W 段的起始/终止深度）。

    兼容 LAS 1.2（值在冒号右）与 LAS 2.0（值在冒号左），
    以及 ``START``/``STOP``、``STRT``/``STOP``、``STRT.MS``/``STOP.MS``。
    """
    sec = _las_w_section(path)
    lo = hi = None
    for key in ('START', 'STRT'):
        for v in sec.get(key, []):
            try:
                lo = float(v)
                break
            except Exception:
                continue
        if lo is not None:
            break
    for key in ('STOP', 'EOT'):
        for v in sec.get(key, []):
            try:
                hi = float(v)
                break
            except Exception:
                continue
        if hi is not None:
            break
    if lo is not None and hi is not None:
        return lo, hi
    return None, None


def _read_csv_header(path: str, max_rows: int = 200) -> tuple[list[str], int]:
    """读 CSV 表头 + 行数（流式，不整表载入）。"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            rd = csv.reader(f)
            header = next(rd, [])
            n = 0
            for _ in rd:
                n += 1
                if n >= max_rows:
                    break
        return header, n
    except Exception:
        return [], 0


def _scan_variables_from_csv(path: str) -> list[Variable]:
    """从 processed.csv 表头生成变量列表，并标出解释/质量列。"""
    header, nrows = _read_csv_header(path)
    out: list[Variable] = []
    for col in header:
        if not col:
            continue
        info = classify_variable(col)
        out.append(Variable(name=info['name'], family=info['family'],
                            unit=info['unit'], scale=info['scale'],
                            kind=info['kind'], color=info['color'],
                            source=os.path.basename(path)))
    return out


def _scan_variables_from_las(path: str) -> list[Variable]:
    """从成果 LAS 读取曲线与单位（不引入 lasio 依赖，失败则跳过）。"""
    out: list[Variable] = []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            in_curves = False
            for _ in range(4000):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                if not s:
                    continue
                up = s.upper()
                if up.startswith('~C'):
                    in_curves = True
                    continue
                if up.startswith('~'):
                    in_curves = False
                    continue
                if not in_curves:
                    continue
                if s.startswith('#') or s.startswith('~'):
                    continue
                parts = [p.strip() for p in s.split('.')]  # name.unit
                if len(parts) < 2:
                    continue
                nm, unit = parts[0], parts[1]
                if not nm or nm.startswith('~'):
                    continue
                info = classify_variable(nm)
                if not info['unit'] and unit and unit not in ('?', ''):
                    info['unit'] = unit
                    info['color'] = 'ok' if info['family'] else 'warn'
                    info['complete'] = bool(info['family'])
                out.append(Variable(name=nm, family=info['family'], unit=info['unit'],
                                    scale=info['scale'], kind=info['kind'],
                                    color=info['color'], source=os.path.basename(path)))
    except Exception:
        pass
    return out


def _read_info(path: str) -> dict:
    """读井信息 json（扁平化为便于展示的键值对）。"""
    try:
        raw = json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}
    flat: dict[str, str] = {}
    for section, val in raw.items():
        if section.startswith('_') or not isinstance(val, dict):
            continue
        for k, v in val.items():
            if k.startswith('_'):
                continue
            if v in (None, '', [], {}):
                continue
            flat['%s/%s' % (section, k)] = v
    flat['_meta_well'] = raw.get('_meta', {}).get('well', '')
    return flat


def _read_manifest(path: str) -> dict:
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}


def _read_layers(path: str) -> tuple[int, dict]:
    """读层表：返回 (层数, 流体分布)。"""
    try:
        n = 0
        dist: dict[str, int] = {}
        with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            rd = csv.DictReader(f)
            for row in rd:
                n += 1
                key = (row.get('INTERPRETATION') or row.get('FLUID_FINAL')
                       or row.get('PLATE_FLUID') or '').strip().upper()
                if key:
                    dist[key] = dist.get(key, 0) + 1
        return n, dist
    except Exception:
        return 0, {}


def _depth_range_from_csv(path: str) -> tuple[float | None, float | None]:
    """从 processed.csv 估算深度范围（只读首列）。"""
    lo = hi = None
    try:
        with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            rd = csv.reader(f)
            header = next(rd, [])
            try:
                di = [i for i, h in enumerate(header) if _norm(h) == 'MD']
                if not di:
                    return None, None
                di = di[0]
            except Exception:
                return None, None
            for row in rd:
                if len(row) <= di:
                    continue
                try:
                    v = float(row[di])
                except Exception:
                    continue
                if lo is None or v < lo:
                    lo = v
                if hi is None or v > hi:
                    hi = v
    except Exception:
        return None, None
    return lo, hi


def scan_well(well_dir: str, source_dir: str = '') -> Well:
    """扫描单口井，产出 Well 对象（数据集 + 变量 + 状态）。

    只读；任何单步失败都降级为空集而不抛错（与 logsys 约定一致）。
    """
    name = os.path.basename(os.path.normpath(well_dir))
    w = Well(name=name, path=well_dir, source_dir=source_dir)

    for pattern, ds_name, dtype in _DATASET_RULES:
        hits = sorted(glob.glob(os.path.join(well_dir, pattern)))
        if not hits:
            continue
        p = _latest(hits)
        try:
            st = os.stat(p)
        except Exception:
            continue
        ds = Dataset(name=ds_name, path=p, dtype=dtype,
                     icon=DATASET_TYPES.get(dtype, ('数据', 'curve'))[1],
                     size=st.st_size, mtime=st.st_mtime)
        if dtype == 'curve':
            ds.variables = _scan_variables_from_csv(p)
            ds.n_cols = len(ds.variables)
            lo, hi = _depth_range_from_csv(p)
            ds.depth_min, ds.depth_max = lo, hi
            w.depth_min = lo if lo is not None else w.depth_min
            w.depth_max = hi if hi is not None else w.depth_max
        elif dtype == 'log':
            ds.variables = _scan_variables_from_las(p)
            ds.n_cols = len(ds.variables)
        elif dtype == 'table':
            n, dist = _read_layers(p)
            ds.n_rows = n
            # 规则层表与 ML 层表并存时：层数取两者之和，流体分布合并
            if '层' in ds_name:
                w.layer_count += n
                for k, v in dist.items():
                    w.fluid_dist[k] = w.fluid_dist.get(k, 0) + v
            ds.variables = [Variable(name=k, family='解释结论', unit='', scale='qualitative',
                                     kind='qualitative', color='warn')
                            for k in sorted(dist)]
        elif dtype == 'meta':
            if '井信息' in ds_name:
                w.info = _read_info(p)
            elif '运行清单' in ds_name:
                mf = _read_manifest(p)
                w.last_run = mf.get('created_at', '')
                # manifest 仅作兜底：层数以层表 CSV 实测为准
                if not w.layer_count:
                    lay = mf.get('layers') or {}
                    if lay.get('rules'):
                        w.layer_count = lay['rules'].get('n', 0)
                        w.fluid_dist = lay['rules'].get('dist', {})
        w.datasets.append(ds)

    # 源数据集（原始 LAS / 甲方格式 / 录井图 …）
    w.source_datasets = _scan_source_datasets(source_dir)
    if w.source_datasets:
        for ds in w.source_datasets:
            if ds.dtype == 'source' and ds.depth_min is not None:
                w.depth_min = ds.depth_min if w.depth_min is None else min(w.depth_min, ds.depth_min)
                w.depth_max = ds.depth_max if w.depth_max is None else max(w.depth_max, ds.depth_max)

    # 状态判定
    # 【2026-11-11 修正】拆成两个正交维度：
    #   status     —— 产物的解释完成度
    #   has_source —— 是否已关联原始资料（决定能否在项目里做 QuickLook）
    # 原实现把两者混成一个状态（判据与标签相反：有源无产物被标成"缺原始资料"）。
    has_curve = any(d.dtype == 'curve' for d in w.datasets)
    has_log = any(d.dtype == 'log' for d in w.datasets)
    has_layer = any(d.dtype == 'table' for d in w.datasets)
    has_product = bool(w.datasets)
    has_src = bool(source_dir) and os.path.isdir(source_dir)
    if has_curve and (has_log or has_layer):
        key = 'complete'
    elif has_curve or has_log:
        key = 'partial'
    elif has_src:
        # 源资料已就位、尚未出产物 → 项目里该跑作业的井
        key = 'pending'
    else:
        key = 'empty'
    label, color = WELL_STATUS[key]
    w.status, w.status_label, w.status_color = key, label, color
    w.source_label, w.source_color = SOURCE_STATUS[
        'linked' if has_src else 'unlinked']
    return w


def scan_project(root: str, source_root: str = '',
                 source_map: dict | None = None,
                 registered: dict | None = None) -> Project:
    """扫描项目根目录，产出 Project（井集合）。

    root        —— 产物根（每子目录 = 一口井）
    source_root —— 原始资料根（可选，用于标记"待解释"井）
    source_map  —— 显式的 {井名: 源目录} 映射（来自 project_config），优先级最高
    registered  —— **已登记的项目成员** {井名: 源目录}。

    【2026-11-11】项目成员不再等于"产物目录里有什么"：
    一口刚添加到项目、**尚未出产物**的井在产物目录里并不存在，
    若只扫目录，它就永远进不了项目树（先有鸡还是先有蛋的问题）。
    因此成员集合 = 产物目录下的子目录 ∪ 已登记的井。
    """
    root = os.path.abspath(root)
    p = Project(name=os.path.basename(root) or root, path=root)
    if not os.path.isdir(root):
        return p
    # 成员集合：产物目录子目录 ∪ 已登记井（后者可能还没有产物目录）
    names = []
    try:
        for entry in sorted(os.listdir(root)):
            d = os.path.join(root, entry)
            if not os.path.isdir(d):
                continue
            if entry.startswith('.') or entry.startswith('_'):
                continue
            names.append(entry)
    except Exception:
        names = []
    for entry in (registered or {}):
        name = str(entry)
        if name not in names:
            names.append(name)
    for entry in sorted(names):
        d = os.path.join(root, entry)
        src = ''
        if source_map:
            src = str(source_map.get(entry) or '')
        if not src and (registered or {}).get(entry):
            src = str((registered or {}).get(entry) or '')
        if not src and source_root:
            cand = os.path.join(source_root, entry)
            if os.path.isdir(cand):
                src = cand
        p.wells.append(scan_well(d, src))
    return p


# --------------------------------------------------------------------------
# 过滤 / 分组 / 条件选择（Techlog Project browser 能力移植）
# --------------------------------------------------------------------------

def filter_wells(project: Project, text: str = '', dataset_type: str = '',
                 variable: str = '', status: str = '') -> list[Well]:
    """按 Techlog Filter tab 语义过滤井。

    text         —— 井名/数据集名/变量名 关键字（不区分大小写）
    dataset_type —— 数据集类型筛选（curve/log/table/source/meta/image/report）
    variable     —— 变量关键字
    status       —— 井状态（complete/partial/pending/empty/no_source）
    """
    kw = (text or '').strip().lower()
    kvar = (variable or '').strip().lower()
    out: list[Well] = []
    for w in project.wells:
        if status and w.status != status:
            continue
        # 源数据集也参与关键字/类型/变量匹配（项目里的井，输入与产物都算）
        all_ds = list(w.datasets) + list(w.source_datasets)
        if kw:
            hit = kw in w.name.lower()
            if not hit:
                for d in all_ds:
                    if kw in d.name.lower():
                        hit = True
                        break
            if not hit and kvar:
                for d in all_ds:
                    if any(kvar in v.name.lower() for v in d.variables):
                        hit = True
                        break
            if not hit:
                continue
        if dataset_type:
            if not any(d.dtype == dataset_type for d in all_ds):
                continue
        if kvar:
            if not any(any(kvar in v.name.lower() for v in d.variables)
                       for d in all_ds):
                continue
        out.append(w)
    return out


def group_wells(wells: list[Well], key: str = 'status') -> dict[str, list[Well]]:
    """分组（Techlog Grouping function 的简化版）。

    key —— 'status'（按状态）| 'country'（按国别）| 'field'（按油田/区块）
    """
    groups: dict[str, list[Well]] = {}
    for w in wells:
        if key == 'country':
            g = str(w.info.get('井信息/country') or '未标注国别')
        elif key == 'field':
            g = str(w.info.get('井信息/field_name') or '未标注区块')
        else:
            g = w.status_label or w.status
        groups.setdefault(g, []).append(w)
    return groups


def conditional_select(project: Project, family: str = '', unit: str = '',
                       kind: str = '') -> dict:
    """条件选择（Techlog Conditional selection）：按族/单位/类型挑变量。

    返回 {'<井名>': {'<数据集名>': [变量名, ...]}}
    """
    res: dict[str, dict[str, list[str]]] = {}
    for w in project.wells:
        for d in w.datasets:
            picked = []
            for v in d.variables:
                if kind and v.kind != kind:
                    continue
                if family and (v.family or '') != family:
                    continue
                if unit and (v.unit or '') != unit:
                    continue
                picked.append(v.name)
            if picked:
                res.setdefault(w.name, {})[d.name] = picked
    return res


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------

def summarize(project: Project) -> dict:
    """项目汇总统计（用于状态栏与属性面板）。"""
    total = len(project.wells)
    by_status: dict[str, int] = {}
    for w in project.wells:
        by_status[w.status_label] = by_status.get(w.status_label, 0) + 1
    ds_total = sum(len(w.datasets) for w in project.wells)
    src_total = sum(len(w.source_datasets) for w in project.wells)
    var_total = sum(len(ds.variables) for w in project.wells for ds in w.datasets)
    var_total += sum(len(ds.variables) for w in project.wells for ds in w.source_datasets)
    layers = sum(w.layer_count for w in project.wells)
    ready = sum(1 for w in project.wells if w.has_source)
    return {
        'project': project.name,
        'path': project.path,
        'wells': total,
        'by_status': by_status,
        'datasets': ds_total,
        'source_datasets': src_total,
        'variables': var_total,
        'layers': layers,
        'ready': ready,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli():
    import argparse
    ap = argparse.ArgumentParser(description='项目-井模型扫描')
    ap.add_argument('--root', required=True, help='项目根目录')
    ap.add_argument('--source-root', default='', help='原始资料根目录（可选）')
    ap.add_argument('--json', action='store_true', help='输出完整 JSON')
    args = ap.parse_args()
    p = scan_project(args.root, args.source_root)
    s = summarize(p)
    if args.json:
        print(json.dumps(p.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print('项目: %s  (%s)' % (s['project'], s['path']))
    print('井数 %d  数据集 %d  变量 %d  层数 %d' %
          (s['wells'], s['datasets'], s['variables'], s['layers']))
    print('状态分布:', json.dumps(s['by_status'], ensure_ascii=False))
    print()
    for w in p.wells:
        print('  [%-6s] %-28s 数据集 %2d  层 %4d  %s' %
              (w.status_label, w.name, len(w.datasets), w.layer_count, w.last_run))
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(_cli())
