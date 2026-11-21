"""交互式测井图窗口（Log View）。

【R80 交互绘图】
三栏布局：
    左：曲线目录（按族分组）—— **拖拽源**，曲线拖进绘图区即自动出图；
    中：交互画布（多道共享深度轴）；
    右：道与曲线 / 图头编辑 / 深度读值 三个页签。

交互清单：
    - 曲线拖入绘图区 → 落到哪道就画进哪道；双击曲线 → 加到当前选中道；
    - 道与曲线页签里可删曲线、删道、调整道序；
    - 图头页签改字段 → 立即写回 `<井名>info.json` → 画布图头条实时刷新，
      并且**后续的快速图 / 综合图出图也同步生效**（同一份井信息源）；
    - 版式可一键切到「快速图版式」或「综合图版式」，与静态出图同源解析。

拖放实现说明：tkinter 无原生 DnD（Tk 未实现 drag&drop 协议），
这里用**按下-移动-抬起**三段式自行实现：
    ① 目录树 ButtonPress 记录候选曲线；
    ② B1-Motion 超过阈值进入拖拽态（光标变手型）；
    ③ ButtonRelease 时用 winfo_pointerxy + winfo_containing 判断落点，
       落在画布上则按像素坐标反查目标道并加入该道。
"""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from logsys.logview import catalog as cat
from logsys.logview import datasource as ds
from logsys.logview import header as hdr
from logsys.logview.canvas import TrackCanvas
from logsys.logview.track_spec import (CurveSpec, TrackSpec, build_tracks,
                                        default_composite_tracks,
                                        default_quicklook_tracks)

DRAG_THRESHOLD = 6          # 超过该像素位移才判定为拖拽（避免误触）
LAYOUT_FILE_SUFFIX = 'logview.json'


def _load_template(kind: str):
    """读图版模板（logvis 带 mtime 热重载）。"""
    try:
        import logvis
        return logvis.load_plot_template(kind)
    except Exception:
        return None


class LogViewWindow(tk.Toplevel):
    """交互式测井图窗口。"""

    def __init__(self, master, well_name: str, out_dir: str = '',
                 source_dir: str = '', las_file: str = '', kind: str = 'qlpt'):
        super().__init__(master)
        self.title(f'交互绘图（Log View） —— {well_name}')
        self.geometry('1580x920')
        self.minsize(1180, 700)

        self.well_name = well_name
        self.out_dir = out_dir or ''
        self.source_dir = source_dir or ''
        self.kind = kind
        self.tracks: list[TrackSpec] = []
        self.catalog: list[cat.CurveItem] = []
        self._drag_item = None
        self._drag_origin = None
        self._dragging = False
        self._selected_track = ''
        self._suspend_save = False

        self.data = ds.load_well_data(well_name, out_dir=out_dir,
                                      source_dir=source_dir, las_file=las_file)
        self.info_path = ds.find_info_json(self.out_dir, well_name) if self.out_dir else ''

        self._build_ui()
        self._refresh_catalog()          # 先建目录 → 族映射可用
        self.canvas.set_well_data(self.data)
        self._load_tracks(kind)
        self._refresh_header_panel()
        self._update_status()

    # ------------------------------------------------------------------
    # 界面骨架
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._style()
        top = ttk.Frame(self, padding=(6, 4))
        top.pack(side='top', fill='x')
        self._build_toolbar(top)

        body = ttk.PanedWindow(self, orient='horizontal')
        body.pack(side='top', fill='both', expand=True)

        left = ttk.Frame(body, width=280)
        body.add(left, weight=1)
        self._build_catalog_panel(left)

        mid = ttk.Frame(body)
        body.add(mid, weight=6)
        self.canvas = TrackCanvas(mid, width=900, height=760)
        # matplotlib 3.11 起真控件是 canvas.widget（组合式），需自行 pack
        self.canvas.widget.pack(fill='both', expand=True)
        self.canvas.on_cursor = self._on_cursor
        self.canvas.on_range = self._on_range

        right = ttk.Frame(body, width=340)
        body.add(right, weight=2)
        self._build_right_panel(right)

        self.status = tk.StringVar(value='')
        ttk.Label(self, textvariable=self.status, relief='sunken',
                  anchor='w').pack(side='bottom', fill='x')

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('Small.TLabel', font=('Microsoft YaHei', 8))

    def _build_toolbar(self, parent):
        row1 = ttk.Frame(parent)
        row1.pack(side='top', fill='x')
        ttk.Label(row1, text='版式：').pack(side='left')
        self.cmb_kind = ttk.Combobox(row1, values=('快速图版式', '综合图版式'),
                                     state='readonly', width=14)
        self.cmb_kind.set('快速图版式' if self.kind == 'qlpt' else '综合图版式')
        self.cmb_kind.pack(side='left', padx=(0, 10))
        self.cmb_kind.bind('<<ComboboxSelected>>', self._on_kind_changed)

        ttk.Button(row1, text='读取保存的布局', command=self._load_saved_layout
                   ).pack(side='left', padx=2)
        ttk.Button(row1, text='保存当前布局', command=self._save_layout
                   ).pack(side='left', padx=2)
        ttk.Separator(row1, orient='vertical').pack(side='left', fill='y', padx=8)
        ttk.Button(row1, text='复位全井', command=self._reset_view).pack(side='left', padx=2)
        ttk.Button(row1, text='导出 PNG', command=self._export_png).pack(side='left', padx=2)
        ttk.Button(row1, text='导出 PDF', command=self._export_pdf).pack(side='left', padx=2)

        row2 = ttk.Frame(parent)
        row2.pack(side='top', fill='x')
        ttk.Label(row2, text='深度范围：').pack(side='left')
        self.var_top = tk.StringVar(value='')
        self.var_bottom = tk.StringVar(value='')
        e1 = ttk.Entry(row2, textvariable=self.var_top, width=12)
        e1.pack(side='left', padx=2)
        e1.bind('<Return>', lambda e: self._apply_depth_range())
        ttk.Label(row2, text='—').pack(side='left')
        e2 = ttk.Entry(row2, textvariable=self.var_bottom, width=12)
        e2.pack(side='left', padx=2)
        e2.bind('<Return>', lambda e: self._apply_depth_range())
        ttk.Button(row2, text='应用', command=self._apply_depth_range).pack(side='left', padx=2)
        ttk.Label(row2, text='  提示：滚轮缩放 / 左键拖拽平移 / 右键框选放大 / 中键复位',
                  style='Small.TLabel').pack(side='left', padx=10)

    def _build_catalog_panel(self, parent):
        ttk.Label(parent, text='曲线目录（拖到绘图区即出曲线）',
                  font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w', pady=(4, 2))
        self.var_filter = tk.StringVar()
        ent = ttk.Entry(parent, textvariable=self.var_filter)
        ent.pack(fill='x', padx=2)
        ent.bind('<KeyRelease>', lambda e: self._refresh_catalog())

        wrap = ttk.Frame(parent)
        wrap.pack(fill='both', expand=True, padx=2, pady=2)
        self.tree = ttk.Treeview(wrap, columns=('unit',), show='tree headings',
                                 selectmode='browse')
        self.tree.heading('#0', text='名称', anchor='w')
        self.tree.column('#0', width=190, minwidth=120, stretch=True)
        self.tree.heading('unit', text='单位', anchor='w')
        self.tree.column('unit', width=70, minwidth=50, stretch=False)
        vsb = ttk.Scrollbar(wrap, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self.tree.bind('<ButtonPress-1>', self._on_tree_press)
        self.tree.bind('<B1-Motion>', self._on_tree_motion)
        self.tree.bind('<ButtonRelease-1>', self._on_tree_release)
        self.tree.bind('<Double-1>', self._on_tree_double)

        btns = ttk.Frame(parent)
        btns.pack(fill='x', padx=2, pady=(0, 4))
        ttk.Button(btns, text='加入当前道', command=self._add_selected_to_track
                   ).pack(side='left', padx=2)
        ttk.Button(btns, text='新建道并加入', command=self._add_selected_new_track
                   ).pack(side='left', padx=2)

    def _build_right_panel(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.pack(fill='both', expand=True)

        # 页签1：道与曲线
        tab_tracks = ttk.Frame(self.nb)
        self.nb.add(tab_tracks, text='道与曲线')
        self.tree_tracks = ttk.Treeview(tab_tracks, columns=('kind',),
                                         show='tree headings', selectmode='browse')
        self.tree_tracks.heading('#0', text='道 / 曲线', anchor='w')
        self.tree_tracks.column('#0', width=190, stretch=True)
        self.tree_tracks.heading('kind', text='类型', anchor='w')
        self.tree_tracks.column('kind', width=70, stretch=False)
        self.tree_tracks.pack(fill='both', expand=True)
        self.tree_tracks.bind('<Double-1>', self._on_track_double)

        row = ttk.Frame(tab_tracks)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='删曲线', command=self._remove_selected_curve
                   ).pack(side='left', padx=2)
        ttk.Button(row, text='删道', command=self._remove_selected_track
                   ).pack(side='left', padx=2)
        ttk.Button(row, text='上移', command=lambda: self._move_track(-1)
                   ).pack(side='left', padx=2)
        ttk.Button(row, text='下移', command=lambda: self._move_track(1)
                   ).pack(side='left', padx=2)

        # 页签2：图头
        tab_header = ttk.Frame(self.nb)
        self.nb.add(tab_header, text='图头')
        self.header_canvas = tk.Canvas(tab_header, highlightthickness=0, borderwidth=0)
        hsb = ttk.Scrollbar(tab_header, orient='horizontal', command=self.header_canvas.xview)
        vsb = ttk.Scrollbar(tab_header, orient='vertical', command=self.header_canvas.yview)
        self.header_frame = ttk.Frame(self.header_canvas)
        self.header_window = self.header_canvas.create_window(
            (0, 0), window=self.header_frame, anchor='nw')
        self.header_frame.bind('<Configure>',
                               lambda e: self.header_canvas.configure(scrollregion=self.header_canvas.bbox('all')))
        self.header_canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.header_canvas.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tab_header.rowconfigure(0, weight=1)
        tab_header.columnconfigure(0, weight=1)
        ttk.Label(tab_header, text='改动立即写回井信息 info.json，快速图/综合图同步生效',
                  style='Small.TLabel').grid(row=2, column=0, columnspan=2, sticky='w', pady=2)

        # 页签3：读值
        tab_read = ttk.Frame(self.nb)
        self.nb.add(tab_read, text='深度读值')
        self.var_cursor = tk.StringVar(value='深度游标：--')
        ttk.Label(tab_read, textvariable=self.var_cursor,
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w', pady=(4, 2))
        wrap = ttk.Frame(tab_read)
        wrap.pack(fill='both', expand=True)
        self.tree_read = ttk.Treeview(wrap, columns=('value',), show='tree headings')
        self.tree_read.heading('#0', text='曲线', anchor='w')
        self.tree_read.column('#0', width=150, stretch=True)
        self.tree_read.heading('value', text='数值', anchor='w')
        self.tree_read.column('value', width=110, stretch=False)
        rsb = ttk.Scrollbar(wrap, orient='vertical', command=self.tree_read.yview)
        self.tree_read.configure(yscrollcommand=rsb.set)
        self.tree_read.pack(side='left', fill='both', expand=True)
        rsb.pack(side='right', fill='y')

    # ------------------------------------------------------------------
    # 道配置
    # ------------------------------------------------------------------
    def _load_tracks(self, kind: str):
        """按模板解析道布局（与静态出图同源）。"""
        self.kind = kind
        tpl = _load_template(kind)
        df = self.data.df
        cols = list(df.columns) if df is not None else []
        flags = {
            'has_res_trad': bool(_any_col(cols, ['RT', 'LLD', 'MSFL', 'RTD', 'ILD'])),
            'has_res_array': bool(_any_col(cols, ['AT10', 'AT20', 'AT30', 'AT60', 'AT90',
                                                  'M2R1', 'AF10'])),
            'has_gas': bool(_any_col(cols, ['TG', 'C1TG', 'GAS', 'TOTAL_GAS'])),
        }
        # 列 → 族（供按族挑默认曲线，与工作台三色语义同源）
        fam_map = {it.column: it.family for it in self.catalog}
        if tpl:
            tracks = build_tracks(tpl, kind, flags, gas_track_width=1.0,
                                  available_columns=cols, column_family=fam_map)
        else:
            tracks = (default_quicklook_tracks(cols) if kind == 'qlpt'
                      else default_composite_tracks(cols))
        self.tracks = tracks
        self.canvas.set_tracks(self.tracks)
        self._refresh_track_tree()
        self._refresh_canvas_header()

    def _on_kind_changed(self, _evt=None):
        kind = 'qlpt' if self.cmb_kind.get() == '快速图版式' else 'cmpt'
        self._load_tracks(kind)
        self._update_status()

    def _refresh_track_tree(self):
        self.tree_tracks.delete(*self.tree_tracks.get_children())
        for t in self.tracks:
            iid = self.tree_tracks.insert('', 'end', text=t.name, values=(t.kind,))
            for c in t.curves:
                self.tree_tracks.insert(iid, 'end', text=c.label or c.column,
                                        values=(c.scale,))
            self.tree_tracks.item(iid, open=True)

    def _refresh_canvas_header(self):
        """图头条 = 井信息（井名/图题/深度范围）+ 当前深度窗口。"""
        unit = self.data.depth_unit or 'm'
        info = self.data.info or {}
        lines = [str(info.get('井信息', {}).get('well_name', '') or self.well_name)]
        for key in ('ql_title', 'cmpt_title'):
            v = str(info.get('图表标题', {}).get(key, '') or '').strip()
            if v:
                lines.append(v)
                break
        lines.append(f'深度 {self.canvas.top:.1f}–{self.canvas.bottom:.1f} {unit}')
        self.canvas.set_header(lines)

    # ------------------------------------------------------------------
    # 曲线目录
    # ------------------------------------------------------------------
    def _refresh_catalog(self):
        self.catalog = cat.build_catalog(self.data)
        keyword = (self.var_filter.get() or '').strip().lower()
        groups = cat.catalog_groups(self.catalog)
        self.tree.delete(*self.tree.get_children())
        for gname, items in groups:
            shown = [i for i in items
                     if not keyword or keyword in i.column.lower()
                     or keyword in (i.family or '').lower()
                     or keyword in i.display.lower()]
            if not shown:
                continue
            gid = self.tree.insert('', 'end', text=gname, open=True)
            for it in shown:
                self.tree.insert(gid, 'end', text=it.column, values=(it.unit,))

    def _current_curve_item(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        parent = self.tree.parent(iid)
        if not parent:
            return None
        name = self.tree.item(iid, 'text')
        for gname, items in cat.catalog_groups(self.catalog):
            for it in items:
                if it.column == name:
                    return it
        return None

    def _current_track_id(self) -> str:
        if self._selected_track:
            return self._selected_track
        for t in self.tracks:
            if t.kind == 'curve':
                return t.id
        return self.tracks[0].id if self.tracks else ''

    # ------------------------------------------------------------------
    # 拖放（纯 tkinter 三段式实现）
    # ------------------------------------------------------------------
    def _on_tree_press(self, evt):
        self._drag_item = self.tree.identify_row(evt.y)
        self._drag_origin = (evt.x, evt.y)
        self._dragging = False

    def _on_tree_motion(self, evt):
        if not self._drag_item:
            return
        if not self._dragging and self._drag_origin:
            dx = evt.x - self._drag_origin[0]
            dy = evt.y - self._drag_origin[1]
            if (dx * dx + dy * dy) ** 0.5 >= DRAG_THRESHOLD:
                self._dragging = True
                self.tree.configure(cursor='hand2')

    def _on_tree_release(self, _evt):
        if self._dragging:
            self._drop_on_canvas()
        self.tree.configure(cursor='')
        self._drag_item = None
        self._drag_origin = None
        self._dragging = False

    def _drop_on_canvas(self):
        """抬起时判断落点：落在画布 → 加入目标道。"""
        item = self._current_curve_item()
        if item is None:
            return
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        if widget is None:
            return
        target = self._canvas_of(widget)
        if target is None:
            return
        px = x - target.widget.winfo_rootx()
        py = y - target.widget.winfo_rooty()
        track_id = target.track_at_pixel(px, py) or self._current_track_id()
        if not track_id:
            return
        self._add_curve_to_track(item, track_id)

    def _canvas_of(self, widget):
        """从命中的控件反查画布实例。

        matplotlib 3.11 起画布真控件是 tk.Canvas（打有 _logview_canvas 标记），
        不在 TrackCanvas 的控件父子链里，故先查标记再回溯父级。
        """
        w = widget
        while w is not None:
            found = getattr(w, '_logview_canvas', None)
            if isinstance(found, TrackCanvas):
                return found
            if isinstance(w, TrackCanvas):
                return w
            try:
                w = w.master
            except Exception:
                break
        return None

    def _on_tree_double(self, _evt):
        item = self._current_curve_item()
        if item is not None:
            self._add_curve_to_track(item, self._current_track_id())

    def _add_selected_to_track(self):
        item = self._current_curve_item()
        if item is None:
            messagebox.showinfo('提示', '请先在左侧选中一条曲线', parent=self)
            return
        self._add_curve_to_track(item, self._current_track_id())

    def _add_selected_new_track(self):
        item = self._current_curve_item()
        if item is None:
            messagebox.showinfo('提示', '请先在左侧选中一条曲线', parent=self)
            return
        tid = f'CUSTOM_{len(self.tracks) + 1}'
        self.canvas.add_track(tid, name=f'自定义道 {len(self.tracks) + 1}',
                              width=1.0, kind='curve')
        self.tracks = self.canvas.tracks
        self._add_curve_to_track(item, tid)
        self._refresh_track_tree()

    def _add_curve_to_track(self, item: cat.CurveItem, track_id: str):
        color = cat.suggest_curve_color(self.catalog, item.column)
        scale = cat.suggest_scale(self.catalog, item.column)
        ok = self.canvas.add_curve(track_id, item.column, color=color, scale=scale)
        self.tracks = self.canvas.tracks
        if ok:
            self._refresh_track_tree()
            self._update_status(f'已把曲线「{item.column}」加入 {track_id}')
        else:
            self._update_status(f'曲线「{item.column}」已在 {track_id} 中')

    # ------------------------------------------------------------------
    # 道与曲线增删
    # ------------------------------------------------------------------
    def _remove_selected_curve(self):
        sel = self.tree_tracks.selection()
        if not sel:
            return
        iid = sel[0]
        parent = self.tree_tracks.parent(iid)
        if not parent:
            return
        track_id = self._track_id_by_tree_item(parent)
        name = self.tree_tracks.item(iid, 'text')
        if track_id and self.canvas.remove_curve(track_id, name):
            self.tracks = self.canvas.tracks
            self._refresh_track_tree()

    def _remove_selected_track(self):
        sel = self.tree_tracks.selection()
        if not sel:
            return
        iid = sel[0]
        if self.tree_tracks.parent(iid):
            self._remove_selected_curve()
            return
        track_id = self._track_id_by_tree_item(iid)
        if track_id and self.canvas.remove_track(track_id):
            self.tracks = self.canvas.tracks
            self._refresh_track_tree()

    def _move_track(self, delta: int):
        sel = self.tree_tracks.selection()
        if not sel:
            return
        iid = sel[0]
        if self.tree_tracks.parent(iid):
            return
        track_id = self._track_id_by_tree_item(iid)
        idx = next((i for i, t in enumerate(self.tracks) if t.id == track_id), -1)
        j = idx + delta
        if idx < 0 or j < 0 or j >= len(self.tracks):
            return
        self.tracks[idx], self.tracks[j] = self.tracks[j], self.tracks[idx]
        self.canvas.set_tracks(self.tracks)
        self._refresh_track_tree()

    def _on_track_double(self, _evt):
        """双击道名 → 选为当前目标道（后续拖入的曲线进这道）。"""
        sel = self.tree_tracks.selection()
        if not sel:
            return
        iid = sel[0]
        parent = self.tree_tracks.parent(iid)
        if parent:
            return
        self._selected_track = self._track_id_by_tree_item(iid)

    def _track_id_by_tree_item(self, iid: str) -> str:
        name = self.tree_tracks.item(iid, 'text')
        for t in self.tracks:
            if t.name == name or t.id == name:
                return t.id
        return ''

    # ------------------------------------------------------------------
    # 图头编辑
    # ------------------------------------------------------------------
    def _refresh_header_panel(self):
        for ch in self.header_frame.winfo_children():
            ch.destroy()
        fields = hdr.load_header_fields(self.data.info)
        if not fields:
            ttk.Label(self.header_frame, text='（未找到井信息文件）').pack(anchor='w')
            return
        last_section = None
        for f in fields:
            if f.section != last_section:
                last_section = f.section
                ttk.Label(self.header_frame, text=f.section,
                          font=('Microsoft YaHei', 9, 'bold'),
                          foreground='#1f4e79').pack(anchor='w', pady=(6, 1))
            row = ttk.Frame(self.header_frame)
            row.pack(fill='x', pady=1)
            ttk.Label(row, text=f.label, width=14, anchor='w').pack(side='left')
            var = tk.StringVar(value=f.value)
            ent = ttk.Entry(row, textvariable=var, width=22)
            ent.pack(side='left', fill='x', expand=True)
            ent.bind('<FocusOut>', lambda e, fld=f, v=var: self._on_header_edit(fld, v))
            ent.bind('<Return>', lambda e, fld=f, v=var: self._on_header_edit(fld, v))

    def _on_header_edit(self, field: hdr.HeaderField, var: tk.StringVar):
        if self._suspend_save:
            return
        value = var.get()
        if value == field.value:
            return
        field.value = value
        if self.info_path and hdr.save_header_field(self.info_path, field.section,
                                                     field.key, value):
            self.data.info = hdr.flatten_info(self.data.info)
            self.data.info = _reload_info(self.info_path) or self.data.info
            self._refresh_canvas_header()
            self._update_status(f'图头已更新：{field.label}')

    # ------------------------------------------------------------------
    # 读值 / 状态
    # ------------------------------------------------------------------
    def _on_cursor(self, depth: float, values: dict):
        unit = self.data.depth_unit or 'm'
        self.var_cursor.set(f'深度游标：{depth:.2f} {unit}')
        self.tree_read.delete(*self.tree_read.get_children())
        for k, v in sorted(values.items()):
            if k == '深度':
                continue
            self.tree_read.insert('', 'end', text=k,
                                  values=(f'{v:.4g}' if isinstance(v, float) else str(v),))

    def _on_range(self, top: float, bottom: float):
        if hasattr(self, 'var_top'):
            self.var_top.set(f'{top:.1f}')
            self.var_bottom.set(f'{bottom:.1f}')

    def _update_status(self, msg: str = ''):
        if msg:
            self.status.set(msg)
            return
        n_curve = sum(len(t.curves) for t in self.tracks)
        rows = len(self.data.depth) if self.data.depth is not None else 0
        self.status.set(
            f'井：{self.well_name}｜道 {len(self.tracks)} 条 / 曲线 {n_curve} 条｜'
            f'数据 {rows} 行｜曲线目录 {len(self.catalog)} 条｜'
            f'数据源 {self.data.origin or "无"}'
            + (f'｜{self.data.note}' if self.data.note else ''))

    # ------------------------------------------------------------------
    # 视图控制 / 导出 / 布局持久化
    # ------------------------------------------------------------------
    def _apply_depth_range(self):
        try:
            top = float(self.var_top.get())
            bottom = float(self.var_bottom.get())
        except (TypeError, ValueError):
            return
        self.canvas.set_depth_range(top, bottom)
        self._refresh_canvas_header()

    def _reset_view(self):
        self.canvas.reset_view()
        self._refresh_canvas_header()

    def _export_png(self):
        path = filedialog.asksaveasfilename(
            parent=self, title='导出 PNG',
            defaultextension='.png',
            initialfile=f'{self.well_name}_logview.png')
        if path and self.canvas.export(path):
            self._update_status(f'已导出：{path}')

    def _export_pdf(self):
        path = filedialog.asksaveasfilename(
            parent=self, title='导出 PDF',
            defaultextension='.pdf',
            initialfile=f'{self.well_name}_logview.pdf')
        if path and self.canvas.export(path):
            self._update_status(f'已导出：{path}')

    def _layout_path(self) -> str:
        if not self.out_dir:
            return ''
        return os.path.join(self.out_dir, f'{self.well_name}{LAYOUT_FILE_SUFFIX}')

    def _save_layout(self):
        path = self._layout_path()
        if not path:
            messagebox.showinfo('提示', '该井没有产物目录，无法保存布局', parent=self)
            return
        data = {
            'well_name': self.well_name,
            'kind': self.kind,
            'tracks': [t.to_dict() for t in self.tracks],
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._update_status(f'布局已保存：{path}')
        except Exception as e:
            messagebox.showerror('保存失败', str(e), parent=self)

    def _load_saved_layout(self):
        path = self._layout_path()
        if not path or not os.path.exists(path):
            messagebox.showinfo('提示', '没有找到保存的布局', parent=self)
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror('读取失败', str(e), parent=self)
            return
        from logsys.logview.track_spec import tracks_from_dicts
        tracks = tracks_from_dicts(data.get('tracks'))
        if tracks:
            self.tracks = tracks
            self.canvas.set_tracks(tracks)
            self._refresh_track_tree()
            self._update_status('已载入保存的布局')


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------

def _any_col(cols: list[str], names: list[str]) -> bool:
    upper = {str(c).upper() for c in cols}
    return any(n.upper() in upper for n in names)


def _reload_info(path: str):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return None


def open_logview(master, well_name: str, out_dir: str = '', source_dir: str = '',
                 las_file: str = '', kind: str = 'qlpt') -> LogViewWindow:
    """从项目工作台调起交互绘图窗口。"""
    win = LogViewWindow(master, well_name, out_dir=out_dir, source_dir=source_dir,
                        las_file=las_file, kind=kind)
    return win
