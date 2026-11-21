"""多道交互测井图画布。

【R80 交互绘图】
交互约定（对齐行业通用测井图交互习惯，非任何单一厂商专有交互）：
    滚轮        = 以光标所在深度为锚点缩放
    左键拖拽    = 平移深度窗口
    右键拖拽    = 框选深度区间放大
    中键单击    = 复位到全井
    鼠标移动    = 跨道深度游标 + 实时读值
    双击        = 复位到全井

所有道共享深度轴（sharey），保证任意缩放级别下严格深度对齐。
曲线用**包络降采样**绘制（见 decimate.py），薄层尖峰不失真。
"""
from __future__ import annotations

import numpy as np

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from logsys.logview.decimate import decimate_for_pixels, depth_window_slice
from logsys.logview.track_spec import CurveSpec, TrackSpec

#: 版面比例
FIG_HEADER_FRAC = 0.085     # 图头条（井名/图题/深度范围/比例尺）
TRACK_HEADER_FRAC = 0.055   # 道头带（道名 + 曲线名/量程）
LEFT_MARGIN = 0.012
RIGHT_MARGIN = 0.988
BOTTOM_MARGIN = 0.012

MIN_SPAN = 2.0               # 最小可视深度跨度，防止无限放大
CURSOR_COLOR = '#e74c3c'

#: 岩性/解释道的定性列候选
LITH_COLUMNS = ('LITHOLOGY', 'LITHOLOGY_MC', 'CORE_LITH', 'lithology_identification')
INTERP_COLUMNS = ('INTERPRETATION', 'fluid_identification', 'LITH_MC_CONF')


def _fluid_colors() -> dict:
    """流体色表（与 logvis 同一套）。"""
    try:
        from logvis import FLUID_COLOR
        return dict(FLUID_COLOR)
    except Exception:
        return {'OIL': '#1a9850', 'GAS': '#d73027', 'WATER': '#00a8f8', 'DRY': '#bdbdbd'}


def _fluid_labels() -> dict:
    try:
        from logvis import FLUID_LABEL_CN
        return dict(FLUID_LABEL_CN)
    except Exception:
        return {}


class TrackCanvas(FigureCanvasTkAgg):
    """多道交互测井图画布。"""

    def __init__(self, master=None, **kwargs):
        # matplotlib 3.11 起 FigureCanvasTk 不再是 tk.Canvas 子类，
        # 真控件在 self._tkcanvas（组合式）；老版本是 self 本身。
        width = kwargs.pop('width', None)
        height = kwargs.pop('height', None)
        self.figure = Figure(facecolor='white')
        super().__init__(self.figure, master=master, **kwargs)
        self.widget = getattr(self, '_tkcanvas', None) or getattr(self, 'tkcanvas', None) or self
        # 打标记：拖放时用 winfo_containing 找到落点控件后反查本画布
        try:
            self.widget._logview_canvas = self
        except Exception:
            pass
        if width:
            self.widget.configure(width=int(width))
        if height:
            self.widget.configure(height=int(height))
        self.well_data = None
        self.tracks: list[TrackSpec] = []
        self.axes: list = []
        self.top = 0.0
        self.bottom = 1.0
        self.full_top = 0.0
        self.full_bottom = 1.0
        self.header_lines: list[str] = []
        self.scale_text = ''
        self._drag = None
        self._cursor_lines = []
        self._layout_sig = None
        self._cursor_depth = None

        # 回调（由窗口注入）
        self.on_cursor = None       # (depth, values:dict)
        self.on_range = None        # (top, bottom)
        self.on_track_click = None  # (track_id, x_data) —— 供拖放落点判定

        try:
            self.widget.setMouseTracking(True)
        except Exception:
            pass
        self.mpl_connect('scroll_event', self._on_scroll)
        self.mpl_connect('button_press_event', self._on_press)
        self.mpl_connect('motion_notify_event', self._on_motion)
        self.mpl_connect('button_release_event', self._on_release)
        self.mpl_connect('figure_leave_event', lambda e: self._clear_cursor())

    # ------------------------------------------------------------------
    # 数据装载
    # ------------------------------------------------------------------
    def set_well_data(self, well_data):
        """装载井数据并按当前道配置绘制。"""
        self.well_data = well_data
        if well_data is not None and getattr(well_data, 'depth', None) is not None \
                and len(well_data.depth) > 0:
            self.full_top = float(well_data.depth[0])
            self.full_bottom = float(well_data.depth[-1])
            self.top, self.bottom = self.full_top, self.full_bottom
        else:
            self.full_top, self.full_bottom = 0.0, 1.0
            self.top, self.bottom = 0.0, 1.0
        self.render()

    def set_tracks(self, tracks: list[TrackSpec]):
        """设置道配置（道集合/宽度变化 → 重建坐标系）。"""
        self.tracks = list(tracks or [])
        self.render()

    def set_header(self, lines: list[str], scale_text: str = ''):
        """设置图头条文本（井名/图题/深度范围/比例尺）。"""
        self.header_lines = [str(x) for x in (lines or []) if str(x).strip()]
        self.scale_text = scale_text or ''
        self.render()

    # ------------------------------------------------------------------
    # 道与曲线的增删
    # ------------------------------------------------------------------
    def track_index(self, track_id: str) -> int:
        for i, t in enumerate(self.tracks):
            if t.id == track_id:
                return i
        return -1

    def add_curve(self, track_id: str, column: str, color: str = '',
                  scale: str = 'lin') -> bool:
        """往某道加一条曲线（拖入绘图区即走这里）。"""
        idx = self.track_index(track_id)
        if idx < 0 or not column:
            return False
        if any(c.column == column for c in self.tracks[idx].curves):
            return False
        self.tracks[idx].curves.append(CurveSpec(
            column=column, label=column, color=color or '#1f77b4', scale=scale))
        self.render()
        return True

    def remove_curve(self, track_id: str, column: str) -> bool:
        idx = self.track_index(track_id)
        if idx < 0:
            return False
        curves = self.tracks[idx].curves
        for i, c in enumerate(curves):
            if c.column == column:
                curves.pop(i)
                self.render()
                return True
        return False

    def add_track(self, track_id: str, name: str = '', width: float = 1.0,
                  kind: str = 'curve') -> bool:
        """加一道（追加到末尾）。"""
        if self.track_index(track_id) >= 0:
            return False
        self.tracks.append(TrackSpec(id=track_id, name=name or track_id,
                                     kind=kind, width=width))
        self.render()
        return True

    def remove_track(self, track_id: str) -> bool:
        idx = self.track_index(track_id)
        if idx < 0 or len(self.tracks) <= 1:
            return False
        self.tracks.pop(idx)
        self.render()
        return True

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def _layout_signature(self):
        return tuple((t.id, round(float(t.width), 4)) for t in self.tracks)

    def _build_axes(self):
        """按道宽比例横向排布，全部 sharey 到第一道。"""
        self.figure.clear()
        self.axes = []
        if not self.tracks:
            return
        widths = [max(float(t.width), 0.05) for t in self.tracks]
        total = sum(widths)
        data_top = 1.0 - FIG_HEADER_FRAC - TRACK_HEADER_FRAC
        x = LEFT_MARGIN
        span = RIGHT_MARGIN - LEFT_MARGIN
        first = None
        for t, w in zip(self.tracks, widths):
            frac = (w / total) * span
            ax = self.figure.add_axes([x, BOTTOM_MARGIN, frac, data_top - BOTTOM_MARGIN])
            if first is None:
                first = ax
            else:
                try:
                    ax.sharey(first)
                except Exception:
                    pass
            ax.set_xticks([])
            ax.tick_params(left=False, labelleft=False)
            for sp in ax.spines.values():
                sp.set_visible(False)
            self.axes.append(ax)
            x += frac
        self._layout_sig = self._layout_signature()

    def render(self):
        """按当前道配置与深度窗口重绘。"""
        if self._layout_signature() != self._layout_sig:
            self._build_axes()
        for ax in self.axes:
            ax.clear()
            ax.set_xticks([])
            ax.tick_params(left=False, labelleft=False)
            for sp in ax.spines.values():
                sp.set_visible(False)
        if self.well_data is not None and getattr(self.well_data, 'has_data', False) \
                and self.axes:
            px_h = max(int(self.figure.get_size_inches()[1] *
                           self.figure.dpi * (1 - FIG_HEADER_FRAC - TRACK_HEADER_FRAC)), 120)
            for ax, t in zip(self.axes, self.tracks):
                self._draw_track(ax, t, px_h)
        elif self.axes:
            self._draw_no_data()
        self._draw_track_headers()
        self._draw_figure_header()
        self._apply_ylim()
        self.draw_idle()
        if self.on_range:
            try:
                self.on_range(self.top, self.bottom)
            except Exception:
                pass

    def _apply_ylim(self):
        for ax in self.axes:
            try:
                ax.set_ylim(self.bottom, self.top)   # 深度向下递增 → 反向
            except Exception:
                pass

    def _draw_figure_header(self):
        """图头条：井名 / 图题 / 深度范围 / 比例尺（实时可改）。"""
        if not self.header_lines:
            return
        y = 1.0 - FIG_HEADER_FRAC / 2
        x = LEFT_MARGIN + 0.004
        n = len(self.header_lines)
        for i, line in enumerate(self.header_lines[:4]):
            weight = 'bold' if i == 0 else 'normal'
            size = 11 if i == 0 else 9
            self.figure.text(x, y - (i - 0.5) * (FIG_HEADER_FRAC / max(n, 2)),
                             line, ha='left', va='center',
                             fontsize=size, weight=weight, color='black')

    def _draw_track_headers(self):
        """道头：道名 + 曲线名（量程）。"""
        for ax, t in zip(self.axes, self.tracks):
            pos = ax.get_position()
            cx = pos.x0 + pos.width / 2
            y_name = pos.y1 + TRACK_HEADER_FRAC * 0.62
            y_sub = pos.y1 + TRACK_HEADER_FRAC * 0.20
            self.figure.text(cx, y_name, t.name, ha='center', va='center',
                             fontsize=8.5, weight='bold', color='black')
            sub = []
            for c in t.curves:
                label = c.label or c.column
                sub.append(label)
            if sub:
                self.figure.text(cx, y_sub, ' / '.join(sub[:3]), ha='center',
                                 va='center', fontsize=6.5, color='#444444')
            # 道间竖分隔线
            self.figure.add_artist(matplotlib.lines.Line2D(
                [pos.x0, pos.x0], [BOTTOM_MARGIN, pos.y1 + TRACK_HEADER_FRAC],
                color='black', linewidth=0.6, transform=self.figure.transFigure,
                zorder=5))

    def _draw_no_data(self):
        """无曲线数据时的占位提示（避免一片空白让人以为程序坏了）。"""
        note = (getattr(self.well_data, 'note', '') or '') if self.well_data else ''
        msg = '（该井暂无解释曲线集或 LAS，无法绘图）'
        if note:
            msg += f'\n{note}'
        self.figure.text(0.5, 0.5, msg, ha='center', va='center', fontsize=11,
                         color='#888888')

    def _draw_track(self, ax, t: TrackSpec, px_h: int):
        kind = t.kind
        if kind == 'depth':
            self._draw_depth_track(ax)
        elif kind == 'lithology':
            self._draw_lithology_track(ax)
        elif kind == 'profile':
            self._draw_profile_track(ax)
        elif kind == 'facies':
            self._draw_lithology_track(ax)
        elif kind == 'interpretation':
            self._draw_interp_track(ax)
        elif kind == 'gas':
            self._draw_curve_track(ax, t, px_h)
        else:
            self._draw_curve_track(ax, t, px_h)

    def _draw_curve_track(self, ax, t: TrackSpec, px_h: int):
        df = self.well_data.df
        depth = self.well_data.depth
        # 注意：这里要的是**列名**，不是 CurveSpec 对象
        cols = [c.column for c in t.curves if c.column in df.columns]
        if not cols:
            ax.text(0.5, 0.5, '（无曲线）', transform=ax.transAxes, ha='center',
                    va='center', fontsize=7, color='#999999')
            ax.set_xlim(0, 1)
            return
        for c in t.curves:
            if c.column not in df.columns:
                continue
            raw = df[c.column].to_numpy(dtype=float)
            vals, dvals, _ = decimate_for_pixels(raw, depth, self.top, self.bottom, px_h)
            if vals.size == 0:
                continue
            if c.scale == 'log':
                vals = np.where(vals <= 0, np.nan, vals)
            if c.fill_to is not None:
                ax.fill_betweenx(dvals, c.fill_to, vals,
                                 color=c.fill_color or c.color, alpha=0.25, linewidth=0)
            ax.plot(vals, dvals, color=c.color, ls=c.linestyle, lw=c.linewidth)
        self._set_xlim_by_curves(ax, t, cols)
        if t.show_grid:
            ax.grid(axis='x', ls=':', lw=0.4, color='#cccccc', alpha=0.7)
        ax.set_xticks([])

    def _set_xlim_by_curves(self, ax, t: TrackSpec, cols: list[str]):
        lo = [c.xmin for c in t.curves if c.xmin is not None]
        hi = [c.xmax for c in t.curves if c.xmax is not None]
        if lo and hi:
            ax.set_xlim(min(lo), max(hi))
            return
        df = self.well_data.df
        mask = depth_window_slice(self.well_data.depth, self.top, self.bottom)
        vals = []
        for c in cols:
            try:
                v = df.loc[mask, c].to_numpy(dtype=float)
                v = v[np.isfinite(v)]
            except Exception:
                v = np.array([], dtype=float)
            if v.size:
                vals.append(v)
        if vals:
            allv = np.concatenate(vals)
            a, b = np.nanpercentile(allv, [2, 98])
            pad = (b - a) * 0.08 or max(abs(b) * 0.05, 1e-6)
            lo, hi = a - pad, b + pad
            if any(c.scale == 'log' for c in t.curves):
                try:
                    ax.set_xscale('log')
                    if lo <= 0:
                        pos = allv[allv > 0]
                        lo = float(pos.min()) if pos.size else 1e-3
                    if hi <= lo:
                        hi = lo * 10
                except Exception:
                    pass
            ax.set_xlim(lo, hi)
        else:
            ax.set_xlim(0, 1)

    def _draw_depth_track(self, ax):
        """深度道：刻度随窗口跨度自适应。"""
        unit = getattr(self.well_data, 'depth_unit', 'm') or 'm'
        span = abs(self.bottom - self.top)
        step = 1.0
        for target in (1000, 500, 200, 100, 50, 20, 10, 5, 2, 1):
            if span / target >= 4:
                step = float(target)
                break
        lo, hi = min(self.top, self.bottom), max(self.top, self.bottom)
        ticks = np.arange(np.ceil(lo / step) * step, hi + step, step)
        ax.set_xlim(0, 1)
        ax.set_xticks([])
        for tv in ticks:
            ax.axhline(tv, color='#999999', lw=0.5)
            ax.text(0.5, tv, f'{tv:g}', ha='center', va='center', fontsize=6.5,
                    color='#222222',
                    bbox=dict(fc='white', ec='none', pad=0.8), zorder=6)
        ax.text(0.5, 0.985, f'深度({unit})', transform=ax.transAxes, ha='center',
                va='top', fontsize=6.5, color='#333333')

    def _lith_column(self):
        df = self.well_data.df
        for c in LITH_COLUMNS:
            if c in df.columns:
                return c
        return None

    def _draw_lithology_track(self, ax):
        """岩性道：复用 logvis 的统一岩性符号绘制（与静态出图一致）。"""
        df = self.well_data.df
        depth = self.well_data.depth
        col = self._lith_column()
        ax.set_xlim(0, 1)
        ax.set_xticks([])
        if col is None:
            ax.text(0.5, 0.5, '（无岩性列）', transform=ax.transAxes, ha='center',
                    va='center', fontsize=7, color='#999999')
            return
        mask = depth_window_slice(depth, self.top, self.bottom)
        lith = df.loc[mask, col].astype(str).to_numpy()
        dd = depth[mask]
        try:
            from logvis import draw_lithology_pattern
        except Exception:
            draw_lithology_pattern = None
        runs = []
        cur_name, cur_z0, cur_z1 = None, None, None
        for i, name in enumerate(lith):
            if name != cur_name:
                if cur_name is not None:
                    runs.append((cur_z0, cur_z1, cur_name))
                cur_name, cur_z0, cur_z1 = name, dd[i], dd[i]
            else:
                cur_z1 = dd[i]
        if cur_name is not None:
            runs.append((cur_z0, cur_z1, cur_name))
        for z0, z1, name in runs:
            if z1 <= z0:
                continue
            if draw_lithology_pattern is not None:
                try:
                    draw_lithology_pattern(ax, name, z0, z1, x0=0.0, x1=1.0)
                    continue
                except Exception:
                    pass
            ax.axhspan(z0, z1, color='#dddddd', lw=0)
            ax.text(0.5, (z0 + z1) / 2, name, ha='center', va='center', fontsize=6)

    def _draw_profile_track(self, ax):
        """剖面道：岩性符号 + 矿物配色底（与静态出图同源的岩性绘制）。"""
        self._draw_lithology_track(ax)

    def _draw_interp_track(self, ax):
        """解释结论道：按流体类别着色（色值取 logvis 的 FLUID_COLOR）。"""
        df = self.well_data.df
        depth = self.well_data.depth
        ax.set_xlim(0, 1)
        ax.set_xticks([])
        colors = _fluid_colors()
        labels = _fluid_labels()
        col = None
        for c in INTERP_COLUMNS:
            if c in df.columns:
                col = c
                break
        if col is None:
            ax.text(0.5, 0.5, '（无解释结论列）', transform=ax.transAxes, ha='center',
                    va='center', fontsize=7, color='#999999')
            return
        mask = depth_window_slice(depth, self.top, self.bottom)
        vals = df.loc[mask, col].astype(str).to_numpy()
        dd = depth[mask]
        cur_name, cur_z0, cur_z1 = None, None, None
        segs = []
        for i, v in enumerate(vals):
            if v != cur_name:
                if cur_name is not None:
                    segs.append((cur_z0, cur_z1, cur_name))
                cur_name, cur_z0, cur_z1 = v, dd[i], dd[i]
            else:
                cur_z1 = dd[i]
        if cur_name is not None:
            segs.append((cur_z0, cur_z1, cur_name))
        for z0, z1, name in segs:
            if z1 <= z0:
                continue
            key = str(name).upper()
            ax.axhspan(z0, z1, color=colors.get(key, '#bdbdbd'), lw=0)
            cn = labels.get(key)
            if cn and (z1 - z0) > 0:
                ax.text(0.5, (z0 + z1) / 2, cn, ha='center', va='center',
                        fontsize=6, color='black')

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_scroll(self, event):
        if event.ydata is None or not self.axes:
            return
        anchor = float(event.ydata)
        factor = 0.8 if event.button == 'up' else 1.25
        span = (self.bottom - self.top) * factor
        full = self.full_bottom - self.full_top
        span = max(MIN_SPAN, min(span, full))
        ratio = (anchor - self.top) / max(self.bottom - self.top, 1e-9)
        self.top = anchor - ratio * span
        self.bottom = self.top + span
        self._clamp()
        self.render()

    def _on_press(self, event):
        if event.ydata is None:
            return
        if event.button == 1:
            self._drag = ('pan', float(event.ydata), self.top, self.bottom)
        elif event.button == 3:
            self._drag = ('zoom', float(event.ydata), None, None)
        elif event.button == 2:
            self.reset_view()

    def _on_motion(self, event):
        if event.ydata is None:
            return
        y = float(event.ydata)
        if self._drag and self._drag[0] == 'pan':
            _, y0, t0, b0 = self._drag
            dy = y0 - y
            self.top, self.bottom = t0 + dy, b0 + dy
            self._clamp()
            self.render()
            return
        self._update_cursor(y)

    def _on_release(self, event):
        if self._drag and self._drag[0] == 'zoom' and event.ydata is not None:
            y0 = self._drag[1]
            y1 = float(event.ydata)
            if abs(y1 - y0) > MIN_SPAN / 4:
                self.top, self.bottom = min(y0, y1), max(y0, y1)
                self._clamp()
                self.render()
        self._drag = None

    def _clamp(self):
        span = self.bottom - self.top
        if self.top < self.full_top:
            self.top, self.bottom = self.full_top, self.full_top + span
        if self.bottom > self.full_bottom:
            self.bottom = self.full_bottom
            self.top = self.bottom - span

    def reset_view(self):
        """复位到全井。"""
        self.top, self.bottom = self.full_top, self.full_bottom
        self.render()

    def set_depth_range(self, top: float, bottom: float):
        """设置深度窗口（外部控件用）。"""
        if bottom < top:
            top, bottom = bottom, top
        self.top, self.bottom = float(top), float(bottom)
        self._clamp()
        self.render()

    def _clear_cursor(self):
        for ln in self._cursor_lines:
            try:
                ln.remove()
            except Exception:
                pass
        self._cursor_lines = []
        self._cursor_depth = None
        self.draw_idle()

    def _update_cursor(self, y: float):
        for ln in self._cursor_lines:
            try:
                ln.remove()
            except Exception:
                pass
        self._cursor_lines = []
        for ax in self.axes:
            try:
                self._cursor_lines.append(
                    ax.axhline(y, color=CURSOR_COLOR, lw=0.9, ls='--', zorder=20))
            except Exception:
                pass
        self._cursor_depth = y
        self.draw_idle()
        if self.on_cursor:
            try:
                self.on_cursor(y, self._read_values(y))
            except Exception:
                pass

    def _read_values(self, y: float) -> dict:
        """游标处最近邻行的全部曲线值。"""
        if self.well_data is None or not getattr(self.well_data, 'has_data', False):
            return {}
        d = self.well_data.depth
        i = int(np.nanargmin(np.abs(d - y)))
        row = self.well_data.df.iloc[i]
        out = {'深度': float(d[i])}
        for k, v in row.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv != fv:       # NaN
                continue
            out[str(k)] = fv
        return out

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def track_at_pixel(self, px: float, py: float) -> str:
        """控件像素坐标 → 落在哪一道（拖放落点判定）。

        px,py 为画布控件内坐标（原点左上）。落空返回空串。
        matplotlib 3.11 起 canvas 不再有公开 bbox，这里用控件像素尺寸换算。
        """
        if not self.axes:
            return ''
        try:
            w = float(self.widget.winfo_width())
            h = float(self.widget.winfo_height())
        except Exception:
            return ''
        if w <= 1 or h <= 1:
            return ''
        fx = px / w
        fy = 1.0 - py / h          # 控件 y 向下、图形 y 向上
        for ax, t in zip(self.axes, self.tracks):
            pos = ax.get_position()
            if pos.x0 <= fx <= pos.x1 and pos.y0 <= fy <= pos.y1:
                return t.id
        return ''

    def export(self, path: str, dpi: int = 150) -> bool:
        """导出当前画布为 PNG / PDF（按扩展名）。"""
        if not path:
            return False
        try:
            self.figure.savefig(path, dpi=dpi, facecolor='white')
            return True
        except Exception:
            return False
