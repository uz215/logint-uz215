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

from logsys import variable_catalog as vc

# --------------------------------------------------------------------------
# 【R87】曲线族 / 分支变量 / 图例 / 绘图方式的唯一事实来源 =
#        ``logsys/variable_catalog.json``（主界面「变量库」可增删改）。
#
# 本模块不再内置第二套族表：classify_variable() 直接委托变量库。
#   · ``family``     = 分支变量显示名（历史字段，保证属性面板、条件选择、
#                      默认道挑选 TRACK_FAMILY_HINTS 的既有语义不变）
#   · ``group``      = 族名（深度族 / 电阻率族 / 岩性族 / 解释结论族…）
#   · ``draw_mode``  = 绘图方式（linear / log / qualitative / spectrum / image）
#   · ``legend_id``  = 应调用的图例（岩性族、解释结论族各有专属图例）
#
# 下方 ALL_FAMILIES / INTERNAL_COLUMNS / UNIT_HINTS 仅为**加载时兼容快照**，
# 供调试与旧脚本读取；修改族名、单位、图例请走主界面「变量库」，
# 直接改这里不会生效。
# --------------------------------------------------------------------------

ALL_FAMILIES: dict[str, tuple[str, str, str]] = {
    v['key']: (v['name'], v['unit'], v['scale']) for v in vc.variables()
}
INTERNAL_COLUMNS: set[str] = {
    str(x).upper() for x in vc.get_catalog().get('internal_columns', [])
}
UNIT_HINTS: dict[str, str] = dict(vc.get_catalog().get('unit_hints', {}))

#: 数据集类型 → Techlog 数据集图标语义
DATASET_TYPES = {
    'curve':    ('连续深度增量曲线集', 'curve'),
    'interval': ('顶底深度边界层集', 'interval'),
    'point':    ('点数据集', 'point'),
    'log':      ('解释成果 LAS', 'log'),
    'table':    ('层段表', 'table'),
    'source':   ('原始测井 LAS / DLIS', 'source'),
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
    """判定单个变量的**族、分支、单位、刻度、绘图方式**与三色状态。

    【R87】唯一事实来源是 ``variable_catalog.json``（主界面「变量库」可编辑）。
    返回字段分两组：

    * 历史字段：``family`` / ``family_name`` = 分支变量显示名（如 GR →
      "自然伽马"），``unit`` / ``scale`` / ``kind`` / ``color`` / ``complete``；
      保持属性面板、条件选择、logvis 默认道挑选的既有语义不变。
    * 新增字段：``group`` / ``group_id`` = 族名与族 id（深度族、电阻率族、
      岩性族、解释结论族…），``draw_mode`` = 绘图方式，
      ``legend_id`` = 岩性/解释结论族应调用的图例。

    Techlog 三色规则：黑 = 族+单位齐备；灰 = 缺其一；红 = 两者皆缺。
    """
    info = vc.classify(col)
    # 统一用原始列名回填 name（变量库内部用的是归一化 key）
    info['name'] = str(col)
    return info


def group_variables(variables: list[Variable]) -> list[tuple[str, list[Variable]]]:
    """【R87】按族分组：Techlog「族 → 分支变量」两级视图。

    返回 ``[(族名, [变量, ...]), ...]``。族顺序取自变量库 ``order``，
    「未分类」恒排最后；组内按变量名排序。供项目树与属性面板使用。
    """
    order = {g['id']: g.get('order', 99) for g in vc.groups()}
    buckets: dict[str, list[Variable]] = {}
    gids: dict[str, str] = {}
    for v in variables:
        gname = v.group or v.family or '未分类'
        buckets.setdefault(gname, []).append(v)
        gids.setdefault(gname, v.group_id or 'UNCLASSIFIED')

    def _sort_key(name: str):
        return (name == '未分类', order.get(gids.get(name, ''), 99), name)

    return [(name, sorted(buckets[name], key=lambda x: (x.name or '').lower()))
            for name in sorted(buckets, key=_sort_key)]


@dataclass
class Variable:
    """变量（曲线列）。【R87】新增族语义与归属信息。"""
    name: str
    family: str | None = None        # 分支变量显示名（历史字段）
    unit: str | None = None
    scale: str | None = None
    kind: str = 'curve'
    color: str = 'error'
    description: str = ''
    source: str = ''
    # ---- R87：族语义 ----
    group: str = ''                  # 族名（深度族 / 电阻率族 / 岩性族…）
    group_id: str = ''
    draw_mode: str = ''              # linear / log / qualitative / spectrum / image
    legend_id: str = ''              # 岩性族、解释结论族 → 对应图例
    origin: str = 'measured'         # measured（输入曲线） / interpretation（解释产物）
    source_file: str = ''            # 【R87】变量归属的输入 LAS / DLIS 绝对路径

    @property
    def complete(self) -> bool:
        """族与单位齐备（Techlog 语义）。"""
        return bool(self.family) and bool(self.unit) and self.kind != 'internal'

    def to_dict(self) -> dict:
        d = asdict(self)
        d['complete'] = self.complete
        return d


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
    # 【R87】LAS / DLIS 由 _scan_source_datasets 用 listdir 大小写不敏感枚举，
    # 每个文件单独成一个数据集（解释产物变量归并到"输入的那个 las/dlis"下）。
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
    """扫描原始资料目录，产出源数据集列表。

    【R87】LAS / DLIS 每个文件单独成一个 dataset（大小写不敏感枚举），
    这样解释产物变量可以明确归属到「输入的那个 las 或 dlis」节点下。
    DLIS 是二进制，通道由 logvis 自行读取；这里只建容器，不解析文本。
    """
    out: list[Dataset] = []
    if not source_dir or not os.path.isdir(source_dir):
        return out
    try:
        entries = sorted(os.listdir(source_dir))
    except Exception:
        entries = []
    seen: set[str] = set()
    for fn in entries:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ('.las', '.dlis'):
            continue
        p = os.path.join(source_dir, fn)
        if not os.path.isfile(p) or os.path.normcase(p) in seen:
            continue
        seen.add(os.path.normcase(p))
        try:
            st = os.stat(p)
        except Exception:
            continue
        is_las = ext == '.las'
        ds = Dataset(name='原始测井 LAS' if is_las else '原始测井 DLIS',
                     path=p, dtype='source',
                     icon=DATASET_TYPES.get('source', ('数据', 'curve'))[1],
                     size=st.st_size, mtime=st.st_mtime)
        if is_las:
            ds.variables = _scan_variables_from_las(p, 'measured', p)
            ds.n_cols = len(ds.variables)
            lo, hi = _depth_range_from_las(p)
            ds.depth_min, ds.depth_max = lo, hi
        else:
            ds.note = 'DLIS 二进制（通道由 logvis 读取）；解释产物变量归并到本数据集下'
        out.append(ds)
    # 其余源文件类型（甲方格式 / 录井图 / 试油表）沿用规则表
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
        out.append(Dataset(name=ds_name, path=p, dtype=dtype,
                           icon=DATASET_TYPES.get(dtype, ('数据', 'curve'))[1],
                           size=st.st_size, mtime=st.st_mtime))
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


def variable_from_info(info: dict, source: str = '', origin: str = 'measured',
                       source_file: str = '') -> Variable:
    """【R87】把 classify_variable 的结果转成 Variable（含族语义与归属）。"""
    return Variable(
        name=info.get('name') or info.get('key') or '',
        family=info.get('family'), unit=info.get('unit'), scale=info.get('scale'),
        kind=info.get('kind', 'curve'), color=info.get('color', 'error'),
        description=info.get('description', ''), source=source,
        group=info.get('group') or '未分类', group_id=info.get('group_id') or '',
        draw_mode=info.get('draw_mode') or 'linear',
        legend_id=info.get('legend_id') or '',
        origin=origin, source_file=source_file)


def _scan_variables_from_csv(path: str, origin: str = 'interpretation',
                             source_file: str = '') -> list[Variable]:
    """从 processed.csv 表头生成变量列表（解释产物 = 曲线变量）。"""
    header, nrows = _read_csv_header(path)
    out: list[Variable] = []
    for col in header:
        if not col:
            continue
        info = classify_variable(col)
        out.append(variable_from_info(info, source=os.path.basename(path),
                                     origin=origin, source_file=source_file))
    return out


def _scan_variables_from_las(path: str, origin: str = 'measured',
                             source_file: str = '') -> list[Variable]:
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
                # LAS 头里带的单位优先补充（变量库未登记单位时）
                if not info['unit'] and unit and unit not in ('?', ''):
                    info['unit'] = unit
                    info['color'] = 'ok' if info['family'] else 'warn'
                    info['complete'] = bool(info['family'])
                out.append(variable_from_info(info, source=os.path.basename(path),
                                             origin=origin, source_file=source_file))
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

    # 源数据集（原始 LAS / DLIS / 甲方格式 / 录井图 …）
    w.source_datasets = _scan_source_datasets(source_dir)
    if w.source_datasets:
        for ds in w.source_datasets:
            if ds.dtype == 'source' and ds.depth_min is not None:
                w.depth_min = ds.depth_min if w.depth_min is None else min(w.depth_min, ds.depth_min)
                w.depth_max = ds.depth_max if w.depth_max is None else max(w.depth_max, ds.depth_max)

    # 【R87】变量归属：解释产物曲线变量挂到「输入的那个 LAS / DLIS」下。
    # 用户定案：「变量存在输入的那个 las 或 dlis 下面」。因此不在产物侧
    # 另立一套"解释曲线集变量"重复出现；产物文件只保留路径与说明。
    # 无源资料时兜底：变量仍留在解释曲线集里，不丢数据。
    input_ds = next((d for d in w.source_datasets
                     if d.dtype == 'source' and d.path.lower().endswith('.las')), None)
    if input_ds is None:
        input_ds = next((d for d in w.source_datasets if d.dtype == 'source'), None)
    if input_ds is not None:
        curve_ds = next((d for d in w.datasets if d.dtype == 'curve'), None)
        if curve_ds is not None and curve_ds.variables:
            existing = {_norm(v.name) for v in input_ds.variables}
            moved = 0
            for v in curve_ds.variables:
                k = _norm(v.name)
                if k in existing:      # 输入曲线里已有同名变量 → 保留输入那条
                    continue
                v.origin = 'interpretation'
                v.source_file = input_ds.path
                input_ds.variables.append(v)
                existing.add(k)
                moved += 1
            input_ds.n_cols = len(input_ds.variables)
            curve_ds.variables = []
            curve_ds.note = ('%d 个解释产物曲线变量已归并到输入数据集「%s」下'
                             % (moved, input_ds.name))

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
                       kind: str = '', group: str = '') -> dict:
    """条件选择（Techlog Conditional selection）：按族/分支/单位/类型挑变量。

    【R87】``group`` 按族名筛选（深度族/电阻率族/岩性族/解释结论族…）；
    ``family`` 仍按分支变量显示名筛选（历史语义）。

    返回 {'<井名>': {'<数据集名>': [变量名, ...]}}
    """
    res: dict[str, dict[str, list[str]]] = {}
    for w in project.wells:
        # 【R87】解释产物变量已归并到输入 LAS/DLIS 数据集下，故源数据集也参与
        for d in list(w.datasets) + list(w.source_datasets):
            picked = []
            for v in d.variables:
                if kind and v.kind != kind:
                    continue
                if group and (v.group or '') != group:
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
