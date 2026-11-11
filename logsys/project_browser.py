# -*- coding: utf-8 -*-
"""项目浏览器 GUI：Project → Well → Dataset → Variable 四层树。

借鉴 Techlog 2019.2 的 Project Browser 交互范式（官方帮助
"Project browser" / "Techlog windows" / "Properties window"），
在 logInt 的 tkinter 技术栈上落地：

  左侧 Project browser   —— 四层树 + 过滤 + 分组 + 搜索
  右侧 Properties window —— 选中对象的属性（分页签式分区）
  底部 Output window     —— 操作消息与错误（对应 Techlog Output window）

Techlog 语义对齐：
  - 数据集图标区分类型（连续曲线集/层段表/成果LAS/图件/元信息）；
  - 变量三色：黑=族+单位齐备、灰=缺其一、红=两者皆缺；
  - 过滤实时生效（Apply filter dynamically）；
  - 右键菜单含条件选择、打开产物、定位文件。

【2026-11-11 项目在前】**作业在项目里做**：
  QuickLook / 综合解释不再是顶层并列任务，而是**项目内针对某口井的作业**
  （右键井 → 快速解释图 / 综合解释）。理由：
  - 作业需要"原始井目录"（原始 LAS + 地质资料 + 甲方格式），而项目树
    扫的是产物目录 —— 只有在项目语境里，才能把"产物"和"源"挂到同一口井上；
  - 作业产物直接落回项目树（output/<井名>/），跑完刷新即可看到新数据集；
  - 批量处理天然是项目级操作（多选井 → 批量 QuickLook）。

用法：
    python -m logsys.project_browser --root D:\\360\\src\\output
    python logInt.py --project              # 启动后选择项目根
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from logsys import project_config as pcfg
from logsys import project_job as pjob
from logsys import project_model as pm

# 配色（与 logInt 现有界面一致：主色 #1a5c9e）
C_BG = '#f5f6f8'
C_PANEL = '#ffffff'
C_ACCENT = '#1a5c9e'
C_TEXT = '#222222'
C_MUTED = '#777777'
C_OK = '#1d7a3e'
C_WARN = '#b8860b'
C_ERROR = '#b00020'
C_LINE = '#d8dce3'

COLOR_MAP = {'ok': C_OK, 'warn': C_WARN, 'error': C_ERROR, 'muted': C_MUTED}

F_MAIN = ('Microsoft YaHei', 9)
F_BOLD = ('Microsoft YaHei', 9, 'bold')
F_TITLE = ('Microsoft YaHei', 13, 'bold')
F_SUB = ('Microsoft YaHei', 8)
F_MONO = ('Consolas', 9)

#: 数据集图标（用 Unicode 符号，避免外部资源依赖）
ICON_MAP = {
    'curve':    '▤',   # 连续曲线集
    'interval': '▥',   # 顶底边界层集
    'point':    '▪',   # 点数据集
    'log':      '▦',   # 成果 LAS
    'source':   '⊞',   # 原始测井 LAS（源）
    'table':    '▥',   # 层段表
    'meta':     '☰',   # 元信息
    'image':    '▣',   # 图件
    'report':   '✎',   # 报告
}

#: 井状态图标（Techlog 用图标区分井状态）
STATUS_ICON = {'complete': '✓', 'partial': '◐', 'pending': '◔', 'empty': '○'}

#: 源资料未关联时的附加标记（叠在井节点上）
NO_SOURCE_MARK = ' ⚠'

#: 状态 → 树节点标签色（浅色主题）
STATUS_TAG = {'ok': '#1d7a3e', 'warn': '#b8860b', 'error': '#b00020', 'muted': '#8a8f98'}


class ProjectBrowser:
    """项目浏览器主窗口。

    左树 = Project browser；右侧 = Properties window；底部 = Output window。
    """

    def __init__(self, root_dir: str, source_root: str = '',
                 on_open_well=None, parent=None):
        self.root_dir = os.path.abspath(root_dir)
        self.source_root = source_root or ''
        self.on_open_well = on_open_well
        self.project = pm.scan_project(self.root_dir, self.source_root)
        self._wells_by_iid: dict[str, pm.Well] = {}
        self._ds_by_iid: dict[str, pm.Dataset] = {}
        self._filter_after = None
        self._job_queue: queue.Queue = queue.Queue()
        self._job_running = False
        self._job_runner: pjob.JobRunner | None = None
        self._batch_queue: list = []
        self._batch_job: str = ''

        self.win = tk.Toplevel(parent) if parent else tk.Tk()
        self.win.title('智能测井解释系统 —— 项目浏览器')
        self.win.geometry('1280x780')
        self.win.configure(bg=C_BG)
        self.win.minsize(1024, 620)

        self._init_style()
        self._build_header()
        self._build_body()
        self._build_output()
        self.refresh()
        self._bind_keys()
        self._poll_job_queue()

    # ---------------- 作业（QuickLook / 综合解释） ----------------

    def _on_job_log(self, msg: str):
        """来自作业线程的日志 → 排队（GUI 线程统一消费，线程安全）。"""
        self._job_queue.put(('log', msg))

    def _on_job_done(self, code: int, label: str):
        self._job_queue.put(('done', (code, label)))

    def _poll_job_queue(self):
        """在 GUI 线程消费作业消息（避免跨线程操作 tk）。"""
        try:
            while True:
                kind, payload = self._job_queue.get_nowait()
                if kind == 'log':
                    self._log(payload)
                else:
                    code, label = payload
                    self._job_running = False
                    self._log('── %s 结束（退出码 %s）──' % (label, code))
                    self.refresh()
                    # 批量队列续跑（项目级作业的串行执行）
                    if getattr(self, '_batch_queue', None):
                        self._start_next_batch()
        except queue.Empty:
            pass
        try:
            self.win.after(200, self._poll_job_queue)
        except Exception:
            pass

    # ---------------- 界面骨架 ----------------

    def _init_style(self):
        st = ttk.Style()
        try:
            st.theme_use('clam')
        except Exception:
            pass
        st.configure('Treeview', font=F_MAIN, rowheight=22, background=C_PANEL,
                     fieldbackground=C_PANEL, borderwidth=0)
        st.configure('Treeview.Heading', font=F_BOLD, background='#e9ecf1',
                     foreground=C_TEXT, relief='flat')
        st.map('Treeview', background=[('selected', '#d6e4f5')],
               foreground=[('selected', C_TEXT)])
        st.configure('TNotebook', background=C_BG, borderwidth=0)
        st.configure('TNotebook.Tab', font=F_MAIN, padding=(10, 4))
        st.configure('TLabelframe', font=F_BOLD, background=C_BG)
        st.configure('TFrame', background=C_BG)

    def _build_header(self):
        hdr = tk.Frame(self.win, bg=C_PANEL)
        hdr.pack(fill='x')
        tk.Label(hdr, text='智能测井解释系统', font=F_TITLE, bg=C_PANEL,
                 fg=C_ACCENT).pack(side='left', padx=(14, 6), pady=8)
        tk.Label(hdr, text='项目浏览器', font=F_BOLD, bg=C_PANEL,
                 fg=C_TEXT).pack(side='left', pady=8)
        self.path_var = tk.StringVar()
        tk.Label(hdr, textvariable=self.path_var, font=F_SUB, bg=C_PANEL,
                 fg=C_MUTED).pack(side='left', padx=10, pady=8)

        right = tk.Frame(hdr, bg=C_PANEL)
        right.pack(side='right', padx=10)
        ttk.Button(right, text='打开井目录…', command=self._pick_root).pack(side='left', padx=3)
        ttk.Button(right, text='刷新', command=self.refresh).pack(side='left', padx=3)

        # 项目级工具条（作业在项目里做：批量执行 / 源根管理）
        bar = tk.Frame(self.win, bg=C_PANEL)
        bar.pack(fill='x', padx=10, pady=(6, 0))
        tk.Label(bar, text='项目作业', font=F_BOLD, bg=C_PANEL,
                 fg=C_TEXT).pack(side='left', padx=(0, 8))
        ttk.Button(bar, text='批量快速解释图（待解释井）',
                   command=lambda: self._run_batch('quicklook')).pack(side='left', padx=3)
        ttk.Button(bar, text='批量综合解释（待解释井）',
                   command=lambda: self._run_batch('comprehensive')).pack(side='left', padx=3)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=8)
        tk.Label(bar, text='候选源根', font=F_SUB, bg=C_PANEL,
                 fg=C_MUTED).pack(side='left')
        self.roots_var = tk.StringVar()
        tk.Label(bar, textvariable=self.roots_var, font=F_SUB, bg=C_PANEL,
                 fg=C_MUTED).pack(side='left', padx=(4, 8))
        ttk.Button(bar, text='添加源根…', command=self._menu_add_root).pack(side='left', padx=3)
        ttk.Button(bar, text='管理源根…', command=self._menu_manage_roots).pack(side='left', padx=3)

        # 过滤条（Techlog: Filter tab，实时生效）
        flt = tk.Frame(self.win, bg=C_BG)
        flt.pack(fill='x', padx=10, pady=(8, 4))
        tk.Label(flt, text='过滤', font=F_BOLD, bg=C_BG, fg=C_TEXT).pack(side='left')
        self.search_var = tk.StringVar()
        ent = tk.Entry(flt, textvariable=self.search_var, font=F_MAIN, width=26,
                       relief='solid', bd=1)
        ent.pack(side='left', padx=(6, 10))
        # 实时过滤（Techlog: Apply filter dynamically），250ms 防抖避免逐字符全量重扫
        self._filter_after = None
        self.search_var.trace_add('write', lambda *a: self._schedule_filter())

        tk.Label(flt, text='状态', font=F_SUB, bg=C_BG, fg=C_MUTED).pack(side='left')
        self.status_var = tk.StringVar(value='全部')
        cb = ttk.Combobox(flt, textvariable=self.status_var, width=11, state='readonly',
                          values=['全部'] + [v[0] for v in pm.WELL_STATUS.values()])
        cb.pack(side='left', padx=(4, 10))
        cb.bind('<<ComboboxSelected>>', lambda e: self.refresh())

        tk.Label(flt, text='分组', font=F_SUB, bg=C_BG, fg=C_MUTED).pack(side='left')
        self.group_var = tk.StringVar(value='不分组')
        cb2 = ttk.Combobox(flt, textvariable=self.group_var, width=11, state='readonly',
                           values=['不分组', '按状态', '按国别', '按区块'])
        cb2.pack(side='left', padx=(4, 10))
        cb2.bind('<<ComboboxSelected>>', lambda e: self.refresh())

        self.show_vars = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text='展开全部变量', variable=self.show_vars,
                        command=self.refresh).pack(side='left', padx=4)

        self.stat_var = tk.StringVar()
        tk.Label(flt, textvariable=self.stat_var, font=F_SUB, bg=C_BG,
                 fg=C_MUTED).pack(side='right')

    def _build_body(self):
        body = tk.Frame(self.win, bg=C_BG)
        body.pack(fill='both', expand=True, padx=10, pady=(0, 6))

        # ---- 左：Project browser ----
        left = tk.LabelFrame(body, text='项目浏览器', font=F_BOLD, bg=C_BG)
        left.pack(side='left', fill='both', expand=True)
        tree_wrap = tk.Frame(left, bg=C_PANEL)
        tree_wrap.pack(fill='both', expand=True, padx=4, pady=4)

        self.tree = ttk.Treeview(tree_wrap, columns=('type', 'detail'),
                                 show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='名称', anchor='w')
        self.tree.heading('type', text='类型', anchor='w')
        self.tree.heading('detail', text='摘要', anchor='w')
        self.tree.column('#0', width=300, minwidth=160, stretch=True)
        self.tree.column('type', width=110, minwidth=70, stretch=False)
        self.tree.column('detail', width=320, minwidth=120, stretch=True)

        vsb = ttk.Scrollbar(tree_wrap, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_wrap, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        # 右键菜单
        # 【2026-11-11 项目在前】作业入口挂在**井节点**上（而不是顶层任务）：
        #   快速解释图 / 综合解释 —— 在项目里对这口井跑作业
        self.menu = tk.Menu(self.win, tearoff=0)
        self.menu.add_command(label='快速解释图（Quick Look）', command=self._menu_quicklook)
        self.menu.add_command(label='综合解释', command=self._menu_comprehensive)
        self.menu.add_separator()
        self.menu.add_command(label='打开该井解释', command=self._menu_open_well)
        self.menu.add_command(label='打开产物目录', command=self._menu_open_dir)
        self.menu.add_command(label='打开源资料目录', command=self._menu_open_source)
        self.menu.add_command(label='复制路径', command=self._menu_copy_path)
        self.menu.add_separator()
        self.menu.add_command(label='关联原始资料目录…', command=self._menu_bind_source)
        self.menu.add_command(label='按此条件选择变量…', command=self._menu_conditional)
        self.tree.bind('<Button-3>', self._popup_menu)

        # ---- 右：Properties window ----
        right = tk.LabelFrame(body, text='属性', font=F_BOLD, bg=C_BG)
        right.pack(side='left', fill='both', expand=True, padx=(8, 0))

        self.prop_title = tk.Label(right, text='（未选择对象）', font=F_BOLD,
                                   bg=C_BG, fg=C_ACCENT, anchor='w')
        self.prop_title.pack(fill='x', padx=10, pady=(8, 2))
        self.prop_type = tk.Label(right, text='', font=F_SUB, bg=C_BG,
                                   fg=C_MUTED, anchor='w')
        self.prop_type.pack(fill='x', padx=10)

        self.nb = ttk.Notebook(right)
        self.nb.pack(fill='both', expand=True, padx=8, pady=6)
        self._tabs: dict[str, tk.Text] = {}
        for key in ('概览', '井信息', '数据集', '变量', '原始'):
            f = tk.Frame(self.nb, bg=C_PANEL)
            txt = tk.Text(f, font=F_MONO, wrap='none', bg=C_PANEL, fg=C_TEXT,
                          relief='flat', borderwidth=0, padx=8, pady=6)
            sb = ttk.Scrollbar(f, orient='vertical', command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            txt.pack(side='left', fill='both', expand=True)
            sb.pack(side='right', fill='y')
            self.nb.add(f, text=key)
            self._tabs[key] = txt

        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind('<Double-1>', self._on_double_click)

    def _build_output(self):
        out = tk.LabelFrame(self.win, text='输出', font=F_BOLD, bg=C_BG)
        out.pack(fill='x', padx=10, pady=(0, 8))
        self.out_txt = tk.Text(out, height=4, font=F_MONO, bg=C_PANEL, fg=C_TEXT,
                               relief='solid', bd=1, state='disabled')
        self.out_txt.pack(fill='x', padx=4, pady=4)

    def _bind_keys(self):
        self.win.bind('<F5>', lambda e: self.refresh())
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.win.bind('<Control-f>', lambda e: self.focus_search())
        self.win.protocol('WM_DELETE_WINDOW', self._close)

    def focus_search(self):
        for c in self.win.winfo_children():
            pass
        # 定位搜索框
        try:
            self.win.focus_set()
        except Exception:
            pass

    # ---------------- 数据装载 ----------------

    def _schedule_filter(self):
        """过滤防抖：连续输入只在停顿后触发一次重扫。"""
        if self._filter_after is not None:
            try:
                self.win.after_cancel(self._filter_after)
            except Exception:
                pass
        self._filter_after = self.win.after(250, self._do_filter)

    def _do_filter(self):
        self._filter_after = None
        self.refresh()

    def refresh(self):
        """重建树（过滤/分组实时生效）。"""
        # 井 → 原始资料目录 映射（显式绑定优先，其次按候选源根自动探测）
        _names = []
        try:
            _names = [e for e in os.listdir(self.root_dir)
                      if os.path.isdir(os.path.join(self.root_dir, e))]
        except Exception:
            _names = []
        _smap = pcfg.source_map(self.root_dir, _names)
        if self.source_root:
            for n in _names:
                if n not in _smap:
                    _c = os.path.join(self.source_root, n)
                    if os.path.isdir(_c):
                        _smap[n] = _c
        self.project = pm.scan_project(self.root_dir, self.source_root, source_map=_smap)
        self.path_var.set(self.root_dir)
        st_label = self.status_var.get()
        status = '' if st_label == '全部' else st_label
        status = next((k for k, v in pm.WELL_STATUS.items() if v[0] == status), '')

        wells = pm.filter_wells(self.project, self.search_var.get(), status=status)
        self.tree.delete(*self.tree.get_children())
        self._wells_by_iid.clear()
        self._ds_by_iid.clear()

        root_iid = self.tree.insert('', 'end', text='%s  %s' % (
            self.project.name, self.project.path), open=True,
            values=('项目', '%d 口井' % len(wells)), tags=('project',))
        self.tree.item(root_iid, image=None)

        groups = None
        if self.group_var.get() != '不分组':
            key = {'按状态': 'status', '按国别': 'country', '按区块': 'field'}[self.group_var.get()]
            groups = pm.group_wells(wells, key)

        if groups:
            for gname, gw in sorted(groups.items()):
                giid = self.tree.insert(root_iid, 'end', text='%s  (%d)' % (gname, len(gw)),
                                        open=True, values=('分组', ''), tags=('group',))
                for w in gw:
                    self._insert_well(giid, w)
        else:
            for w in wells:
                self._insert_well(root_iid, w)

        s = pm.summarize(self.project)
        self.stat_var.set('项目 %s ｜ 井 %d ｜ 数据集 %d ｜ 源 %d ｜ 变量 %d ｜ 层 %d ｜ 已关联源 %d ｜ 当前筛选 %d' % (
            s['project'], s['wells'], s['datasets'], s['source_datasets'],
            s['variables'], s['layers'], s['ready'], len(wells)))
        # 候选源根显示
        try:
            _roots = pcfg.source_roots(self.root_dir)
            self.roots_var.set('（%d 个）%s' % (len(_roots), '；'.join(_roots[:2])))
        except Exception:
            self.roots_var.set('')
        # 输出区只保留最近一条刷新摘要（连续刷新不刷屏）
        self._log('刷新：%d 口井（筛选后 %d）｜ 数据集 %d ｜ 源 %d ｜ 变量 %d ｜ 层 %d ｜ 已关联源 %d' % (
            s['wells'], len(wells), s['datasets'], s['source_datasets'],
            s['variables'], s['layers'], s['ready']))

    def _insert_well(self, parent: str, w: pm.Well):
        icon = STATUS_ICON.get(w.status, '○')
        detail = '数据集 %d' % len(w.datasets)
        if w.source_datasets:
            detail += ' ｜ 源 %d' % len(w.source_datasets)
        detail += ' ｜ 层 %d' % w.layer_count
        if w.last_run:
            detail += ' ｜ %s' % w.last_run
        # 未关联源资料的井加警示标记（可在项目里做作业的前提）
        mark = '' if w.has_source else NO_SOURCE_MARK
        # 井节点：展开全部变量时直接展开井节点，层级才可见
        iid = self.tree.insert(parent, 'end',
                               text='%s %s%s' % (icon, w.name, mark),
                               values=(w.status_label, detail),
                               tags=(w.status_color,),
                               open=bool(self.show_vars.get()))
        self._wells_by_iid[iid] = w
        for ds in w.source_datasets:
            self._insert_dataset(iid, ds, source=True)
        for ds in w.datasets:
            self._insert_dataset(iid, ds)
        return iid

    def _insert_dataset(self, parent: str, ds: pm.Dataset, source: bool = False):
        icon = ICON_MAP.get(ds.icon, '▤')
        detail = '%d 变量' % len(ds.variables) if ds.variables else ''
        if ds.n_rows:
            detail += ' ｜ %d 行' % ds.n_rows
        if ds.depth_min is not None:
            detail += ' ｜ %.1f-%.1f m' % (ds.depth_min, ds.depth_max or ds.depth_min)
        iid = self.tree.insert(parent, 'end', text='%s %s' % (icon, ds.name),
                               values=(pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0], detail),
                               tags=('source' if source else 'dataset',))
        self._ds_by_iid[iid] = ds
        if self.show_vars.get():
            self.tree.item(iid, open=True)
            for v in ds.variables:
                self.tree.insert(iid, 'end', text='  %s' % v.name,
                                 values=(v.family or '（无族）', v.unit or '（无单位）'),
                                 tags=(v.color,))
        return iid

    # ---------------- 属性面板 ----------------

    def _on_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self._wells_by_iid:
            self._show_well(self._wells_by_iid[iid])
        elif iid in self._ds_by_iid:
            self._show_dataset(self._ds_by_iid[iid])
        else:
            self._show_object(iid)

    def _show_object(self, iid: str):
        vals = self.tree.item(iid, 'values')
        self.prop_title.configure(text=self.tree.item(iid, 'text'))
        self.prop_type.configure(text='%s　%s' % (vals[0] if vals else '', vals[1] if len(vals) > 1 else ''))
        self._set_tab('概览', '%s\n\n类型: %s\n%s' % (
            self.tree.item(iid, 'text'), vals[0] if vals else '',
            vals[1] if len(vals) > 1 else ''))

    def _show_well(self, w: pm.Well):
        self.prop_title.configure(text=w.name)
        self.prop_type.configure(text='井 · %s' % w.status_label)
        s = pm.summarize(self.project)
        lines = [
            '井名        : %s' % w.name,
            '产物状态    : %s' % w.status_label,
            '源资料状态  : %s' % w.source_label,
            '产物目录    : %s' % w.path,
        ]
        if w.source_dir:
            lines.append('原始资料    : %s' % w.source_dir)
        else:
            lines.append('原始资料    : （未关联 —— 右键「关联原始资料目录…」）')
        lines += [
            '数据集数量  : %d（产物） + %d（源）' % (len(w.datasets), len(w.source_datasets)),
            '变量总数    : %d' % sum(len(d.variables) for d in w.datasets + w.source_datasets),
            '层数        : %d' % w.layer_count,
        ]
        if w.fluid_dist:
            lines.append('流体分布    : %s' % json.dumps(w.fluid_dist, ensure_ascii=False))
        if w.depth_min is not None:
            lines.append('深度范围    : %.2f - %.2f m' % (w.depth_min, w.depth_max or 0))
        if w.last_run:
            lines.append('最近运行    : %s' % w.last_run)
        self._set_tab('概览', '\n'.join(lines))

        # 井信息
        info = w.info or {}
        if info:
            txt = '\n'.join('%s = %s' % (k, v) for k, v in sorted(info.items())
                            if not k.startswith('_'))
        else:
            txt = '（未找到 <井名>info.json）'
        self._set_tab('井信息', txt)

        # 数据集（产物 + 源）
        rows = []
        for ds in w.source_datasets:
            rows.append('%s  [源 · %s]' % (ds.name, pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0]))
            rows.append('    路径   : %s' % ds.path)
            rows.append('    大小   : %s' % _human_size(ds.size))
            rows.append('    变量   : %d' % len(ds.variables))
            if ds.depth_min is not None:
                rows.append('    深度   : %.2f - %.2f m' % (ds.depth_min, ds.depth_max or 0))
            rows.append('')
        for ds in w.datasets:
            rows.append('%s  [%s]' % (ds.name, pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0]))
            rows.append('    路径   : %s' % ds.path)
            rows.append('    大小   : %s' % _human_size(ds.size))
            rows.append('    变量   : %d' % len(ds.variables))
            if ds.depth_min is not None:
                rows.append('    深度   : %.2f - %.2f m' % (ds.depth_min, ds.depth_max or 0))
            rows.append('')
        self._set_tab('数据集', '\n'.join(rows) or '（无）')

        # 变量
        vrows = []
        for ds in w.source_datasets + w.datasets:
            if not ds.variables:
                continue
            vrows.append('── %s ──' % ds.name)
            for v in ds.variables:
                mark = {'ok': '●', 'warn': '●', 'error': '●', 'muted': '·'}.get(v.color, '·')
                vrows.append('  %s %-18s %-12s %s' % (
                    mark, v.name, v.family or '（无族）', v.unit or '（无单位）'))
            vrows.append('')
        self._set_tab('变量', '\n'.join(vrows) or '（无变量）')

        self._set_tab('原始', json.dumps(w.to_dict(), ensure_ascii=False, indent=2))

    def _show_dataset(self, ds: pm.Dataset):
        self.prop_title.configure(text=ds.name)
        self.prop_type.configure(text='数据集 · %s' % pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0])
        lines = [
            '名称    : %s' % ds.name,
            '类型    : %s' % pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0],
            '路径    : %s' % ds.path,
            '大小    : %s' % _human_size(ds.size),
            '变量数  : %d' % len(ds.variables),
        ]
        if ds.n_rows:
            lines.append('行数    : %d' % ds.n_rows)
        if ds.depth_min is not None:
            lines.append('深度    : %.2f - %.2f m' % (ds.depth_min, ds.depth_max or 0))
        lines.append('完整    : %s' % ('是' if ds.complete else '否（存在缺族/缺单位的变量）'))
        self._set_tab('概览', '\n'.join(lines))
        vrows = []
        for v in ds.variables:
            mark = {'ok': '●', 'warn': '●', 'error': '●', 'muted': '·'}.get(v.color, '·')
            vrows.append('%s %-20s %-14s %-10s %s' % (
                mark, v.name, v.family or '（无族）', v.unit or '（无单位）', v.scale or ''))
        self._set_tab('变量', '\n'.join(vrows) or '（无变量）')
        self._set_tab('数据集', '本数据集属性\n\n' + '\n'.join(lines))
        self._set_tab('井信息', '（数据集视图）')
        self._set_tab('原始', json.dumps(ds.to_dict(), ensure_ascii=False, indent=2))

    def _set_tab(self, name: str, text: str):
        t = self._tabs.get(name)
        if not t:
            return
        t.configure(state='normal')
        t.delete('1.0', 'end')
        t.insert('1.0', text or '')
        t.configure(state='disabled')

    # ---------------- 交互 ----------------

    def _on_double_click(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self._wells_by_iid:
            self._open_well(self._wells_by_iid[iid])
        elif iid in self._ds_by_iid:
            ds = self._ds_by_iid[iid]
            if os.path.exists(ds.path):
                try:
                    os.startfile(os.path.dirname(ds.path))  # noqa: S606
                except Exception as e:
                    self._log('打开目录失败: %s' % e)

    def _menu_open_well(self):
        w = self._selected_well()
        if w:
            self._open_well(w)

    # ---------------- 作业（在项目里做） ----------------

    def _menu_quicklook(self):
        """项目内作业：对选中井跑 QuickLook（快速解释图）。"""
        self._run_job('quicklook')

    def _menu_comprehensive(self):
        """项目内作业：对选中井跑综合解释。"""
        self._run_job('comprehensive')

    def _run_job(self, job_type: str):
        if self._job_running:
            self._log('已有作业在运行，请等待完成或先取消')
            return
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        if not w.has_source:
            self._log('井 %s 未关联原始资料目录 —— 请右键「关联原始资料目录…」后再执行作业'
                      % w.name)
            return
        label = pjob.JOB_TYPES.get(job_type, (job_type, ''))[0]
        runner = pjob.JobRunner(on_log=self._on_job_log, on_done=self._on_job_done)
        self._job_runner = runner
        self._job_running = True
        ok = runner.start(job_type, w.source_dir, self.root_dir)
        if not ok:
            self._job_running = False
            return
        self._log('── %s：%s ──' % (label, w.name))

    def _menu_bind_source(self):
        """把井的原始资料目录显式绑定并持久化到项目配置。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        d = filedialog.askdirectory(
            title='选择 %s 的原始资料目录（含 LAS / 地质资料 / 甲方格式）' % w.name,
            initialdir=w.source_dir or self.root_dir)
        if not d:
            return
        if pcfg.bind_well(self.root_dir, w.name, d):
            self._log('已关联源目录：%s → %s' % (w.name, d))
            self.refresh()
        else:
            self._log('关联失败：无法写入项目配置 %s' % pcfg.config_path(self.root_dir))

    def _menu_open_source(self):
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        if not w.has_source:
            self._log('井 %s 未关联原始资料目录' % w.name)
            return
        try:
            os.startfile(w.source_dir)  # noqa: S606
            self._log('已打开源目录：%s' % w.source_dir)
        except Exception as e:
            self._log('打开源目录失败：%s' % e)

    def _run_batch(self, job_type: str):
        """项目级批量作业：对所有"待解释"且已关联源的井依次执行。

        批量是**项目语境**才有的能力 —— 单井流程里没有"一批井"的概念。
        """
        if self._job_running:
            self._log('已有作业在运行，请等待完成')
            return
        targets = [w for w in self.project.wells
                   if w.status == 'pending' and w.has_source]
        if not targets:
            self._log('没有可执行的井：批量作业仅针对「待解释」且已关联原始资料的井')
            return
        label = pjob.JOB_TYPES.get(job_type, (job_type, ''))[0]
        if not self._ask_yes_no('批量%s' % label,
                                '将对 %d 口井依次执行%s：\n%s\n\n单井可能耗时数分钟，是否继续？'
                                % (len(targets), label,
                                   '\n'.join('  · %s' % w.name for w in targets))):
            return
        self._batch_queue = [(job_type, w) for w in targets]
        self._batch_job = job_type
        self._log('批量%s：%d 口井' % (label, len(targets)))
        self._start_next_batch()

    def _start_next_batch(self):
        if not getattr(self, '_batch_queue', None):
            self._log('批量作业全部结束')
            self._batch_queue = []
            return
        job_type, w = self._batch_queue.pop(0)
        runner = pjob.JobRunner(on_log=self._on_job_log, on_done=self._on_job_done)
        self._job_runner = runner
        self._job_running = True
        if not runner.start(job_type, w.source_dir, self.root_dir):
            self._job_running = False
            self._start_next_batch()

    def _menu_add_root(self):
        d = filedialog.askdirectory(title='添加候选原始资料根目录')
        if not d:
            return
        if pcfg.add_source_root(self.root_dir, d):
            self._log('已添加候选源根：%s' % d)
            self.refresh()
        else:
            self._log('添加候选源根失败')

    def _menu_manage_roots(self):
        """管理候选源根（增删 + 显示已绑定关系）。"""
        win = tk.Toplevel(self.win)
        win.title('项目配置 — 候选源根与井绑定')
        win.geometry('680x480')
        win.configure(bg=C_BG)
        tk.Label(win, text='候选原始资料根目录（用于按井名自动探测源目录）',
                 font=F_BOLD, bg=C_BG).pack(anchor='w', padx=12, pady=(10, 4))
        lst = tk.Listbox(win, font=F_MONO, height=8, bg=C_PANEL, relief='solid', bd=1)
        lst.pack(fill='both', expand=True, padx=12)

        cfg = pcfg.load_config(self.root_dir)
        for r in cfg.get('source_roots', []):
            lst.insert('end', r)

        tk.Label(win, text='已绑定的井（井名 → 源目录）',
                 font=F_BOLD, bg=C_BG).pack(anchor='w', padx=12, pady=(8, 4))
        lst2 = tk.Listbox(win, font=F_MONO, height=8, bg=C_PANEL, relief='solid', bd=1)
        lst2.pack(fill='both', expand=True, padx=12)
        for k, v in sorted((cfg.get('wells') or {}).items()):
            lst2.insert('end', '%-24s → %s' % (k, v.get('source_dir', '')))

        b = tk.Frame(win, bg=C_BG)
        b.pack(fill='x', padx=12, pady=10)

        def _add():
            d = filedialog.askdirectory(title='添加候选原始资料根目录')
            if d:
                pcfg.add_source_root(self.root_dir, d)
                lst.insert('end', d)

        def _remove():
            sel = lst.curselection()
            if not sel:
                return
            pcfg.remove_source_root(self.root_dir, lst.get(sel[0]))
            lst.delete(sel[0])

        ttk.Button(b, text='添加…', command=_add).pack(side='left', padx=3)
        ttk.Button(b, text='移除选中', command=_remove).pack(side='left', padx=3)
        ttk.Button(b, text='应用并刷新', command=lambda: (win.destroy(), self.refresh())
                   ).pack(side='right', padx=3)

    def _ask_yes_no(self, title: str, message: str) -> bool:
        win = tk.Toplevel(self.win)
        win.title(title)
        win.geometry('520x260')
        win.configure(bg=C_BG)
        tk.Label(win, text=title, font=F_BOLD, bg=C_BG, fg=C_ACCENT).pack(
            anchor='w', padx=14, pady=(12, 4))
        tk.Label(win, text=message, font=F_MAIN, bg=C_BG, justify='left').pack(
            anchor='w', padx=14)
        res = {'ok': False}

        def _ok():
            res['ok'] = True
            win.destroy()

        b = tk.Frame(win, bg=C_BG)
        b.pack(fill='x', padx=14, pady=12)
        ttk.Button(b, text='取消', command=win.destroy).pack(side='right', padx=4)
        ttk.Button(b, text='开始', command=_ok).pack(side='right', padx=4)
        win.grab_set()
        self.win.wait_window(win)
        return res['ok']

    def _open_well(self, w: pm.Well):
        if self.on_open_well:
            try:
                self.on_open_well(w)
                self._log('已触发井解释流程：%s' % w.name)
            except Exception as e:
                self._log('触发解释失败: %s' % e)
        else:
            src = w.source_dir or w.path
            self._log('井目录：%s（右键可执行快速解释图 / 综合解释）' % src)

    def _menu_open_dir(self):
        w = self._selected_well()
        d = w.path if w else self.root_dir
        try:
            os.startfile(d)  # noqa: S606
            self._log('已打开目录：%s' % d)
        except Exception as e:
            self._log('打开目录失败：%s' % e)

    def _menu_copy_path(self):
        w = self._selected_well()
        p = w.path if w else self.root_dir
        self.win.clipboard_clear()
        self.win.clipboard_append(p)
        self._log('已复制路径：%s' % p)

    def _menu_conditional(self):
        """条件选择（Techlog Conditional selection）。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        win = tk.Toplevel(self.win)
        win.title('条件选择变量 — %s' % w.name)
        win.geometry('620x460')
        win.configure(bg=C_BG)
        tk.Label(win, text='按族 / 单位 / 类型筛选变量（留空 = 不过滤）',
                 font=F_BOLD, bg=C_BG).pack(anchor='w', padx=12, pady=(10, 6))

        fams = sorted({v.family for d in w.datasets for v in d.variables if v.family})
        units = sorted({v.unit for d in w.datasets for v in d.variables if v.unit})
        kinds = sorted({v.kind for d in w.datasets for v in d.variables})

        f_fam = tk.StringVar()
        f_unit = tk.StringVar()
        f_kind = tk.StringVar()
        for label, var, vals in (('族', f_fam, fams), ('单位', f_unit, units), ('类型', f_kind, kinds)):
            row = tk.Frame(win, bg=C_BG)
            row.pack(fill='x', padx=12, pady=3)
            tk.Label(row, text=label, font=F_MAIN, bg=C_BG, width=6, anchor='w').pack(side='left')
            cb = ttk.Combobox(row, textvariable=var, values=[''] + list(vals),
                              state='readonly', width=34)
            cb.pack(side='left')

        res = tk.Text(win, font=F_MONO, bg=C_PANEL, relief='solid', bd=1)
        res.pack(fill='both', expand=True, padx=12, pady=8)

        def _run():
            sel = pm.conditional_select(pm.Project(self.project.name, self.project.path, [w]),
                                        family=f_fam.get(), unit=f_unit.get(), kind=f_kind.get())
            res.delete('1.0', 'end')
            if not sel:
                res.insert('1.0', '（无匹配变量）')
                return
            for well, dss in sel.items():
                for dn, vs in dss.items():
                    res.insert('end', '%s / %s\n' % (well, dn))
                    for v in vs:
                        res.insert('end', '    %s\n' % v)
                    res.insert('end', '\n')

        b = tk.Frame(win, bg=C_BG)
        b.pack(fill='x', padx=12, pady=(0, 10))
        ttk.Button(b, text='执行选择', command=_run).pack(side='left')
        ttk.Button(b, text='关闭', command=win.destroy).pack(side='right')

    def _popup_menu(self, evt):
        sel = self.tree.identify_row(evt.y)
        if sel:
            self.tree.selection_set(sel)
        try:
            self.menu.tk_popup(evt.x_root, evt.y_root)
        finally:
            self.menu.grab_release()

    def _selected_well(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid in self._wells_by_iid:
            return self._wells_by_iid[iid]
        # 数据集 → 反查其井
        for w_iid, w in self._wells_by_iid.items():
            for ds in w.datasets:
                if ds in self._ds_by_iid.values():
                    pass
        return self._well_of(iid)

    def _well_of(self, iid: str):
        cur = iid
        while cur:
            if cur in self._wells_by_iid:
                return self._wells_by_iid[cur]
            cur = self.tree.parent(cur)
        return None

    def _pick_root(self):
        d = filedialog.askdirectory(title='选择项目根目录（每子目录 = 一口井）',
                                    initialdir=self.root_dir)
        if d:
            self.root_dir = d
            self.refresh()

    def _log(self, msg: str):
        """写输出区。与上一条相同则不重复写（避免连续刷新刷屏）。"""
        try:
            cur = self.out_txt.get('1.0', 'end').rstrip('\n')
            last = cur.rsplit('\n', 1)[-1].strip() if cur else ''
            if last == msg:
                return
            self.out_txt.configure(state='normal')
            self.out_txt.insert('end', msg + '\n')
            self.out_txt.see('end')
            self.out_txt.configure(state='disabled')
        except Exception:
            pass

    def _close(self):
        try:
            self.win.destroy()
        except Exception:
            pass

    def run(self):
        self.win.mainloop()


def _human_size(n: int) -> str:
    if not n:
        return '-'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return '%.1f %s' % (n, unit)
        n /= 1024.0
    return '%.1f TB' % n


def default_root() -> str:
    """默认项目根 = 仓库下的 output/（logInt 的产物落盘位置）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'output')


def launch(root: str = '', source_root: str = '', on_open_well=None) -> int:
    """启动项目浏览器。root 为空时弹窗选择项目根。"""
    if not root:
        r = tk.Tk()
        r.withdraw()
        root = filedialog.askdirectory(title='选择项目根目录（每子目录 = 一口井）',
                                       initialdir=default_root())
        r.destroy()
        if not root:
            return 1
    browser = ProjectBrowser(root, source_root, on_open_well)
    browser.run()
    return 0


def _cli():
    ap = argparse.ArgumentParser(description='项目浏览器')
    ap.add_argument('--root', default='', help='项目根目录')
    ap.add_argument('--source-root', default='', help='原始资料根目录（可选）')
    ap.add_argument('--source-roots', default='',
                    help='候选原始资料根目录，多个用 ; 分隔（可选）')
    args = ap.parse_args()
    if args.source_roots:
        for r in args.source_roots.split(';'):
            r = r.strip()
            if r:
                pcfg.add_source_root(args.root or default_root(), r)
    return launch(args.root, args.source_root)


if __name__ == '__main__':
    sys.exit(_cli())
