"""曲线目录：把井里"能画的曲线"整理成可拖拽的清单。

【R80 交互绘图】
沿用 `logsys/project_model.py` 的 Techlog 三色语义：
  黑色 = 既有 family 又有 unit；灰色 = 缺其一；红色 = 两者皆缺。
分类逻辑直接复用 `classify_variable`，不在本模块另立一套判定。

除原始/派生曲线外，还把**快速图与综合图里的定性道**也登记进来
（岩性、解释结论、沉积相、层号），这样交互画布里就能像 Techlog 那样
把"结论道"当作可加可减的对象来摆布。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from logsys import project_model as pm

#: 曲线默认配色（按族给色，保证同族同色；无族走中性色）
_FAMILY_COLORS = {
    'GR': '#4c9a4c', 'RT': '#b03030', 'CAL': '#606060', 'DEN': '#2f6f9f',
    'CNL': '#7a5aa8', 'DT': '#c08030', 'PE': '#8a6d3b', 'SP': '#3f8f8f',
    'LLD': '#b03030', 'LLS': '#c05050', 'MSFL': '#7a2a2a',
    'POR': '#2f6f9f', 'SW': '#1a9850', 'VSH': '#8a6d3b', 'So': '#1a9850',
}
_DEFAULT_COLOR = '#1f77b4'
_QUAL_COLOR = '#7a5aa8'


@dataclass
class CurveItem:
    """目录里的一条曲线。"""
    column: str
    label: str = ''
    family: str = ''          # 族（显示名）
    unit: str = ''
    scale: str = 'linear'     # linear | log | qualitative
    kind: str = 'curve'       # curve | qualitative
    color: str = _DEFAULT_COLOR
    status: str = 'ok'        # ok | warn | error（Techlog 三色）
    source: str = '曲线集'
    vmin: float | None = None
    vmax: float | None = None
    note: str = ''

    @property
    def display(self) -> str:
        """列表显示文本：名 + 单位。"""
        return f'{self.label or self.column} ({self.unit})' if self.unit else (self.label or self.column)

    @property
    def key(self) -> str:
        return self.column


def _color_for(family: str, scale: str, status: str) -> str:
    if status == 'error':
        return '#c0392b'
    if status == 'warn':
        return '#8a8a8a'
    if scale == 'qualitative':
        return _QUAL_COLOR
    for k, c in _FAMILY_COLORS.items():
        if k and k in (family or '').upper():
            return c
    return _DEFAULT_COLOR


def build_catalog(well_data) -> list[CurveItem]:
    """扫描井数据 → 曲线目录。"""
    if well_data is None or not getattr(well_data, 'has_data', False):
        return []

    df = well_data.df
    items: list[CurveItem] = []
    for col in df.columns:
        name = str(col)
        if name.upper() == 'MD':
            continue
        info = pm.classify_variable(name)
        kind = info.get('kind', 'unknown')
        if kind == 'internal':
            continue
        family = info.get('family') or ''
        unit = info.get('unit') or ''
        scale = info.get('scale') or 'linear'
        status = info.get('color', 'error')
        if status == 'muted':
            continue
        try:
            vals = df[name].to_numpy(dtype=float)
            finite = vals[np.isfinite(vals)]
        except Exception:
            finite = np.array([], dtype=float)
        vmin = float(finite.min()) if finite.size else None
        vmax = float(finite.max()) if finite.size else None
        items.append(CurveItem(
            column=name,
            label=name,
            family=family,
            unit=unit,
            scale=scale,
            kind='qualitative' if scale == 'qualitative' else 'curve',
            color=_color_for(family, scale, status),
            status=status,
            source='曲线集',
            vmin=vmin, vmax=vmax,
        ))
    return items


def catalog_groups(items: list[CurveItem]) -> list[tuple[str, list[CurveItem]]]:
    """按族分组（有族按族，无族归「未分类」），组内按名称排序。"""
    buckets: dict[str, list[CurveItem]] = {}
    for it in items:
        key = it.family or '未分类'
        buckets.setdefault(key, []).append(it)
    out = []
    for key in sorted(buckets, key=lambda k: (k == '未分类', k)):
        group = sorted(buckets[key], key=lambda i: i.column.lower())
        out.append((key, group))
    return out


def find_curve(items: list[CurveItem], column: str) -> CurveItem | None:
    """按列名找曲线（大小写不敏感）。"""
    if not column:
        return None
    for it in items:
        if it.column == column:
            return it
    low = column.lower()
    for it in items:
        if it.column.lower() == low:
            return it
    return None


def suggest_curve_color(items: list[CurveItem], column: str) -> str:
    """给新加入的曲线选色：优先沿用目录中的族色，否则按列名稳定取色。"""
    it = find_curve(items, column)
    if it:
        return it.color
    palette = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd',
               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    h = sum(ord(c) for c in (column or ''))
    return palette[h % len(palette)]


def suggest_scale(items: list[CurveItem], column: str) -> str:
    """新加入曲线的刻度方式：电阻率族用对数，其余线性。"""
    it = find_curve(items, column)
    if it:
        return 'log' if (it.scale == 'log' or 'ohm' in (it.unit or '').lower()) else 'lin'
    return 'lin'
