"""道（track）与曲线（curve）的配置数据结构 + 布局解析。

【R80 交互绘图（Log View）】
本模块是**道布局的唯一解析入口**，同时供两类消费方使用：
  1. 静态出图（logvis.py 的快速图 / 综合图）；
  2. 交互画布（logsys/logview 的多道交互测井图）。
两者共用同一套解析逻辑，杜绝"交互画布与甲方交付图版式分叉"。

原则（沿用手册 §0.3「单一裁决/单一来源」）：
- **模板是布局的唯一源头**：`templates/<kind>.json` 的 `track.layout`；
- 代码里的 FALLBACK_LAYOUT 只是**模板缺失时的兜底**，数值逐一对齐
  `logvis.py` 的两处硬编码（quicklook / composite），保证老模板出图像素级不变；
- 解析结果带 `from_template` 标志，出图时打日志说明布局来源，
  避免再出现"改了模板没反应还不知道为什么"。

字段命名对齐 templates/*.json 现有风格（英文小写下划线）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# --------------------------------------------------------------------------
# 道 ID → 显示条件。None 表示无条件显示；字符串键表示依赖该运行时标志。
# --------------------------------------------------------------------------
TRACK_CONDITIONS = {
    'RES_TRAD':  'has_res_trad',
    'RES_ARRAY': 'has_res_array',
    'GAS':       'has_gas',
}

#: 硬编码兜底布局：与 logvis.py 中 quicklook / composite 两处构造逐一对齐。
#: 仅当模板缺失 track.layout 时使用，保证老模板出图结果完全不变。
#: 注意：quicklook 含 CALIB（标定道，2026-11-02 加入），不可遗漏。
FALLBACK_LAYOUT: dict[str, list] = {
    'qlpt': [
        ('LITHO', 1.2),
        ('RES_TRAD', 1.4),
        ('RES_ARRAY', 1.4),
        ('POR', 1.0),
        ('DEPTH', 0.30),
        ('SW', 0.6),
        ('POR2', 0.6),
        ('CALIB', 0.9),
        ('GAS', 'gas'),
        ('PROFILE', 1.0),
        ('INTERP', 0.42),
    ],
    'cmpt': [
        ('LITHO', 1.0),
        ('RES_TRAD', 1.4),
        ('RES_ARRAY', 1.4),
        ('POR', 1.25),
        ('DEPTH', 0.5),
        ('SWPOR', 1.0),
        ('GAS', 'gas'),
        ('LITHO_FILL', 1.0),
        ('FACIES', 1.0),
        ('PROFILE', 1.0),
        ('INTERP', 1.0),
    ],
}

#: 道 ID → 中文道名（道头显示）
TRACK_NAMES = {
    'LITHO':      '岩性道',
    'RES_TRAD':   '电阻率道(传统)',
    'RES_ARRAY':  '电阻率道(阵列)',
    'POR':        '孔隙度道',
    'DEPTH':      '深度道',
    'SW':         '含水饱和度道',
    'SWPOR':      '含水饱和度道',
    'POR2':       '孔隙度道(2)',
    'CALIB':      '标定道',
    'GAS':        '气测道',
    'PROFILE':    '剖面道',
    'LITHO_FILL': '岩性填充道',
    'FACIES':     '沉积相道',
    'INTERP':     '解释结论道',
}

#: 道 ID → 绘制类型与默认候选曲线。
#: 只描述"道怎么画"，不描述"有哪些道、多宽"——后者由 resolve_track_layout 解析。
TRACK_KINDS = {
    'LITHO':      ('lithology',      []),
    'RES_TRAD':   ('curve',          ['RT', 'LLD', 'MSFL']),
    'RES_ARRAY':  ('curve',          ['AT10', 'AT20', 'AT30', 'AT60', 'AT90']),
    'POR':        ('curve',          ['DEN', 'NPHI', 'AC']),
    'DEPTH':      ('depth',          []),
    'SW':         ('curve',          ['Sw']),
    'SWPOR':      ('curve',          ['Sw']),
    'POR2':       ('curve',          ['porosity']),
    'CALIB':      ('curve',          []),
    'GAS':        ('gas',            ['TG']),
    'PROFILE':    ('profile',        []),
    'LITHO_FILL': ('lithology',      []),
    'FACIES':     ('facies',         []),
    'INTERP':     ('interpretation', []),
}

#: 道 ID → 期望的曲线族（按族挑曲线是 Techlog 的做法：族优先于固定列名）。
#: 固定列名候选为空时，用这里的族回退。
TRACK_FAMILY_HINTS = {
    'RES_TRAD':   ('深电阻率', '浅电阻率', '电阻率', '侵入带电阻率'),
    'RES_ARRAY':  ('阵列电阻率',),
    'POR':        ('孔隙度', '有效孔隙度'),
    'POR2':       ('孔隙度', '有效孔隙度'),
    'SW':         ('含水饱和度',),
    'SWPOR':      ('含水饱和度', '孔隙度'),
    'GAS':        ('总烃', '气测'),
    'CALIB':      ('岩心', '取心'),
}

#: 道 ID → 列名子串候选（族也匹配不到时用；子串为不区分大小写包含匹配）
TRACK_NAME_PATTERNS = {
    'RES_ARRAY':  ('AT10', 'AT20', 'AT30', 'AT60', 'AT90', 'AF10', 'M2R'),
    'GAS':        ('TG', 'GAS'),
    'CALIB':      ('CORE', 'XRD', 'XRF', 'CALC'),
}


def _pick_by_family(track_id: str, columns, column_family: dict | None,
                    limit: int = 3) -> list[str]:
    """按族挑默认曲线（族名取自 project_model.classify_variable）。"""
    if not column_family:
        return []
    hints = TRACK_FAMILY_HINTS.get(track_id) or ()
    if not hints:
        return []
    by_family: dict[str, list[str]] = {}
    for col, fam in column_family.items():
        if fam:
            by_family.setdefault(fam, []).append(col)
    out: list[str] = []
    for fam in hints:
        for col in sorted(by_family.get(fam, [])):
            if col not in out:
                out.append(col)
            if len(out) >= limit:
                return out
    return out


def _pick_by_pattern(track_id: str, columns, limit: int = 3) -> list[str]:
    """按列名子串挑默认曲线（族匹配不到时的最后回退）。"""
    pats = TRACK_NAME_PATTERNS.get(track_id) or ()
    if not pats:
        return []
    out: list[str] = []
    for col in columns:
        up = str(col).upper()
        if any(p.upper() in up for p in pats):
            if col not in out:
                out.append(col)
            if len(out) >= limit:
                break
    return out


@dataclass
class CurveSpec:
    """道内一条曲线的绘制规格。"""
    column: str                      # DataFrame 列名，如 'GR' / 'RT' / 'Sw'
    label: str = ''                  # 道头显示名（空则用 column）
    color: str = '#1f77b4'
    linestyle: str = '-'
    linewidth: float = 0.9
    scale: str = 'lin'               # 'lin' | 'log'
    xmin: float | None = None        # None = 自动（百分位）
    xmax: float | None = None
    fill_to: float | None = None     # 填充到该 x 值（如 Vsh 填到 0）
    fill_color: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'CurveSpec':
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class TrackSpec:
    """一道（track）的配置。"""
    id: str                          # 'LITHO' / 'RES_TRAD' / 'POR' / 'DEPTH' ...
    name: str = ''                   # 中文道名，道头显示
    kind: str = 'curve'              # curve|lithology|depth|interpretation|profile|gas|facies
    width: float = 1.0
    curves: list[CurveSpec] = field(default_factory=list)
    show_grid: bool = True
    header_lines: int = 3            # 道头占几行文字高度
    #: 启停：True/False 显式开关，'auto' 按运行时标志判定（沿用模板 reg_tracks 既有约定）
    enabled: bool | str = 'auto'

    def to_dict(self) -> dict:
        d = asdict(self)
        d['curves'] = [c.to_dict() for c in self.curves]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'TrackSpec':
        cs = [CurveSpec.from_dict(c) for c in (d or {}).get('curves', [])]
        known = {f for f in cls.__dataclass_fields__}
        kw = {k: v for k, v in (d or {}).items() if k in known and k != 'curves'}
        return cls(curves=cs, **kw)


def resolve_track_layout(tpl, kind: str, flags: dict, gas_track_width: float = 1.0):
    """解析出道布局：[(道ID, 宽度float), ...]。

    参数
    ----
    tpl   : logvis.load_plot_template(kind) 的返回（可为 None）
    kind  : 'qlpt'（快速解释）| 'cmpt'（综合图）
    flags : {'has_res_trad': bool, 'has_res_array': bool, 'has_gas': bool}
            运行时可用道判定，对应代码里的 trad_res_cols / array_res_cols / has_gas
    gas_track_width : 气测道实算宽度，用于替换模板里的 "gas" 占位

    优先级
    ------
    模板 track.layout（有效项）→ FALLBACK_LAYOUT[kind]（应急兜底）

    约定
    ----
    width 可为数字，或字符串 "gas"（表示用 gas_track_width 实算值）；
    enabled 可为 true/false，或 "auto"（按 flags 判定，缺省即 auto）。
    """
    cfg = ((tpl or {}).get('track') or {}).get('layout')
    raw = cfg if isinstance(cfg, list) and cfg else FALLBACK_LAYOUT.get(kind, [])
    from_template = isinstance(cfg, list) and bool(cfg)

    out: list[tuple[str, float]] = []
    for it in raw:
        if isinstance(it, dict):
            tid = it.get('id')
            width = it.get('width', 1.0)
            enabled = it.get('enabled', 'auto')
        else:                       # 兜底布局是 (id, width) 元组
            if not it:
                continue
            tid, width, enabled = it[0], it[1], 'auto'
        if not tid:
            continue
        # enabled: false → 显式关闭；true → 强制开启；auto → 按运行时标志判定
        if enabled is False:
            continue
        if enabled == 'auto':
            cond = TRACK_CONDITIONS.get(tid)
            if cond and not (flags or {}).get(cond):
                continue
        if width == 'gas':
            if not (flags or {}).get('has_gas'):
                continue
            width = gas_track_width
        try:
            out.append((str(tid), float(width)))
        except (TypeError, ValueError):
            continue

    if not out:                     # 模板写了但全被禁用 → 回落兜底
        return resolve_track_layout(None, kind, flags, gas_track_width)[0], False
    return out, from_template


def _default_scale(column: str, column_family: dict | None) -> str:
    """默认曲线刻度：电阻率族用对数，其余线性。

    电阻率动态范围可达 0.2~5000 ohm.m，线性轴会把整条曲线压成一条平线。
    """
    fam = (column_family or {}).get(column) or ''
    if '电阻率' in fam or '电导率' in fam:
        return 'log'
    return 'lin'


def build_tracks(tpl, kind: str, flags: dict, gas_track_width: float = 1.0,
                 available_columns=None, curve_overrides=None,
                 column_family=None) -> list[TrackSpec]:
    """从模板解析布局 → 组装成 TrackSpec 列表。

    与 logvis 静态出图调用同一个 resolve_track_layout，
    因此交互画布与甲方交付图的道顺序、道宽、启停状态永远一致。

    curve_overrides : {track_id: [CurveSpec, ...]} —— 交互态用户手工增减的曲线，
                      优先于模板/默认曲线。
    column_family   : {列名: 族显示名} —— 用于按族挑默认曲线（缺省则只认固定列名）。
    """
    layout, _from_tpl = resolve_track_layout(tpl, kind, flags, gas_track_width)
    track_cfg = ((tpl or {}).get('track') or {})
    defs = track_cfg.get('track_defs') or {}
    names = {}
    for t in (track_cfg.get('layout') or []):
        if isinstance(t, dict) and t.get('id'):
            names[t['id']] = t.get('name')
    cols = set(available_columns or [])
    overrides = curve_overrides or {}

    out: list[TrackSpec] = []
    for tid, width in layout:
        d = defs.get(tid, {}) or {}
        tk, default_curves = TRACK_KINDS.get(tid, ('curve', []))
        if tid in overrides:
            curves = list(overrides[tid])
        else:
            curves = [CurveSpec(**c) for c in (d.get('curves') or [])]
            if not curves:
                # 模板未定义曲线 → ①固定列名候选 ②按族 ③按列名子串
                picked = [c for c in default_curves if not cols or c in cols]
                if not picked:
                    picked = _pick_by_family(tid, available_columns or [],
                                             column_family)
                if not picked:
                    picked = _pick_by_pattern(tid, available_columns or [])
                curves = [CurveSpec(column=c, scale=_default_scale(c, column_family))
                          for c in picked]
        out.append(TrackSpec(
            id=tid,
            name=names.get(tid) or d.get('name') or TRACK_NAMES.get(tid, tid),
            kind=d.get('kind', tk),
            width=width,
            curves=curves,
            show_grid=d.get('show_grid', True),
        ))
    return out


def default_quicklook_tracks(available_columns=None) -> list[TrackSpec]:
    """模板完全不可用时的最后兜底（快速图版式）。"""
    return build_tracks(
        None, 'qlpt',
        {'has_res_trad': True, 'has_res_array': False, 'has_gas': False},
        available_columns=available_columns)


def default_composite_tracks(available_columns=None) -> list[TrackSpec]:
    """模板完全不可用时的最后兜底（综合图版式）。"""
    return build_tracks(
        None, 'cmpt',
        {'has_res_trad': True, 'has_res_array': False, 'has_gas': False},
        available_columns=available_columns)


def tracks_to_dicts(tracks) -> list[dict]:
    """TrackSpec 列表 → 可 JSON 化的 dict 列表（供模板/工程文件持久化）。"""
    return [t.to_dict() for t in tracks]


def tracks_from_dicts(items) -> list[TrackSpec]:
    """dict 列表 → TrackSpec 列表。"""
    return [TrackSpec.from_dict(it) for it in (items or [])]
