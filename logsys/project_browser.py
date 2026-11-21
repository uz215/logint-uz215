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

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QCursor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QVBoxLayout, QHBoxLayout,
    QMenu, QAction, QDialog, QDialogButtonBox, QListWidget, QAbstractItemView,
    QTextEdit, QShortcut, QTabWidget, QSizePolicy,
)

from logsys import qtgui as _qg
from logsys import qtcompat as _qc
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
        self._root_iid = ''
        self._filter_timer = None
        self._job_queue: queue.Queue = queue.Queue()
        self._job_running = False
        self._job_runner: pjob.JobRunner | None = None
        self._batch_queue: list = []
        self._batch_job: str = ''

        # Qt 要求先有 QApplication 才能创建任何 QWidget
        _qg.get_app()
        self.win = QMainWindow(parent)
        self.win.setWindowTitle('智能测井解释系统 —— 项目工作台')
        self.win.resize(1280, 780)
        self.win.setMinimumSize(1024, 620)
        self.win.setStyleSheet('QWidget { background: %s; color: %s; }' % (C_BG, C_TEXT))

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
            QTimer.singleShot(200, self._poll_job_queue)
        except Exception:
            pass

    # ---------------- 界面骨架 ----------------

    # ---------------- 界面骨架 ----------------

    def _init_style(self):
        # Qt 下用样式表统一配色（tkinter 的 ttk.Style 概念不再需要）
        self.win.setStyleSheet("""
            QTreeWidget { background: %s; border: 1px solid %s; }
            QTreeWidget::item { height: 22px; }
            QTreeWidget::item:selected { background: #d6e4f5; color: %s; }
            QHeaderView::section { background: #e9ecf1; color: %s;
                                  border: none; padding: 3px; }
            QTabWidget::pane { border: 1px solid %s; background: %s; }
            QPushButton { padding: 3px 8px; }
            QLabel { background: transparent; }
        """ % (C_PANEL, C_LINE, C_TEXT, C_TEXT, C_LINE, C_PANEL))

    def _mk_button(self, parent, text, slot):
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _mk_label(self, text, bold=False, small=False, muted=False, parent=None):
        lab = QLabel(text)
        if bold:
            lab.setStyleSheet('font-weight: bold;')
        if small or muted:
            lab.setStyleSheet('color: %s; font-size: 8pt;' % C_MUTED)
        return lab

    def _build_header(self):
        central = QWidget()
        self.win.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # 顶栏
        hdr = QFrame()
        hdr.setStyleSheet('background: %s;' % C_PANEL)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 6, 10, 6)
        title = QLabel('智能测井解释系统')
        title.setStyleSheet('color: %s; font-size: 13pt; font-weight: bold;' % C_ACCENT)
        hl.addWidget(title)
        hl.addWidget(self._mk_label('项目工作台', bold=True))
        self.path_var = _qc.Var()
        self.lbl_path = self._mk_label('', small=True, muted=True)
        self.path_var.bind_label(self.lbl_path)
        hl.addWidget(self.lbl_path, 1)
        hl.addWidget(self._mk_button(hdr, '打开项目根…', self._pick_root))
        hl.addWidget(self._mk_button(hdr, '刷新', self.refresh))
        root.addWidget(hdr)

        # 项目作业工具条
        bar = QFrame()
        bar.setStyleSheet('background: %s;' % C_PANEL)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 4, 10, 4)
        bl.addWidget(self._mk_label('项目作业', bold=True))
        bl.addWidget(self._mk_button(bar, '添加井到项目…', self._menu_add_well))
        bl.addWidget(self._mk_button(bar, '批量添加井…', self._menu_add_wells_batch))
        bl.addWidget(self._vline())
        bl.addWidget(self._mk_button(bar, '批量快速解释图（待解释井）',
                                     lambda: self._run_batch('quicklook')))
        bl.addWidget(self._mk_button(bar, '批量综合解释（待解释井）',
                                     lambda: self._run_batch('comprehensive')))
        bl.addWidget(self._vline())
        bl.addWidget(self._mk_label('候选源根', small=True, muted=True))
        self.roots_var = _qc.Var()
        self.lbl_roots = self._mk_label('', small=True, muted=True)
        self.roots_var.bind_label(self.lbl_roots)
        bl.addWidget(self.lbl_roots)
        bl.addWidget(self._mk_button(bar, '添加源根…', self._menu_add_root))
        bl.addWidget(self._mk_button(bar, '管理源根…', self._menu_manage_roots))
        bl.addStretch(1)
        root.addWidget(bar)

        # 过滤条（实时生效 + 防抖）
        flt = QWidget()
        fl = QHBoxLayout(flt)
        fl.setContentsMargins(10, 4, 10, 2)
        fl.addWidget(self._mk_label('过滤', bold=True))
        self.search_var = _qc.Var()
        self.le_search = QLineEdit()
        self.le_search.setFixedWidth(220)
        self.le_search.textChanged.connect(lambda t: self.search_var.set(t))
        self.search_var.trace_add('write', lambda *a: self._schedule_filter())
        fl.addWidget(self.le_search)

        fl.addWidget(self._mk_label('状态', small=True, muted=True))
        self.status_var = _qc.Var('全部')
        self.cmb_status = QComboBox()
        self.cmb_status.setFixedWidth(110)
        self.cmb_status.addItems(['全部'] + [v[0] for v in pm.WELL_STATUS.values()])
        self.cmb_status.currentTextChanged.connect(lambda t: (self.status_var.set(t), self.refresh()))
        fl.addWidget(self.cmb_status)

        fl.addWidget(self._mk_label('分组', small=True, muted=True))
        self.group_var = _qc.Var('不分组')
        self.cmb_group = QComboBox()
        self.cmb_group.setFixedWidth(110)
        self.cmb_group.addItems(['不分组', '按状态', '按国别', '按区块'])
        self.cmb_group.currentTextChanged.connect(lambda t: (self.group_var.set(t), self.refresh()))
        fl.addWidget(self.cmb_group)

        self.show_vars = _qc.Var(False)
        self.chk_expand = QCheckBox('展开全部变量')
        self.chk_expand.stateChanged.connect(
            lambda s: (self.show_vars.set(s == Qt.Checked), self.refresh()))
        fl.addWidget(self.chk_expand)

        fl.addStretch(1)
        self._member_var = _qc.Var('成员 0（已登记 0）')
        self.lbl_member = self._mk_label('', small=True, muted=True)
        self._member_var.bind_label(self.lbl_member)
        fl.addWidget(self.lbl_member)
        self.stat_var = _qc.Var()
        self.lbl_stat = self._mk_label('', small=True, muted=True)
        self.stat_var.bind_label(self.lbl_stat)
        fl.addWidget(self.lbl_stat)
        root.addWidget(flt)

        # 主体区（树 + 属性）由 _build_body 追加到 root
        self._root_layout = root

    def _vline(self):
        ln = QFrame()
        ln.setFrameShape(QFrame.VLine)
        ln.setFrameShadow(QFrame.Sunken)
        return ln

    def _build_body(self):
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(10, 4, 10, 4)

        # ---- 左：项目浏览器 ----
        left = QFrame()
        left.setFrameShape(QFrame.StyledPanel)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        cap = self._mk_label('项目浏览器', bold=True)
        ll.addWidget(cap)
        tag_colors = dict(COLOR_MAP)
        tag_colors.update(STATUS_TAG)
        self.tree = _qc.TreeViewCompat(left, columns=('type', 'detail'),
                                       tag_colors=tag_colors)
        self.tree.setAlternatingRowColors(False)
        ll.addWidget(self.tree, 1)
        bl.addWidget(left, 3)

        # 右键菜单（作业入口挂在井节点上）
        self.menu = QMenu(self.win)
        for label, slot in (
                ('快速解释图（Quick Look）', self._menu_quicklook),
                ('综合解释', self._menu_comprehensive),
                ('交互绘图（logvis）…', self._menu_logview),
                (None, None),
                ('指定主 LAS…', self._menu_set_las),
                ('指定气测文件…', self._menu_set_gas),
                ('选择甲方出图格式…', self._menu_set_format),
                ('清除资料指定', self._menu_clear_inputs),
                (None, None),
                ('打开该井解释', self._menu_open_well),
                ('打开产物目录', self._menu_open_dir),
                ('打开源资料目录', self._menu_open_source),
                ('复制路径', self._menu_copy_path),
                (None, None),
                ('关联原始资料目录…', self._menu_bind_source),
                ('重命名井…', self._menu_rename_well),
                ('从项目移除', self._menu_remove_well),
                ('按此条件选择变量…', self._menu_conditional)):
            if label is None:
                self.menu.addSeparator()
            else:
                act = QAction(label, self.win)
                act.triggered.connect(slot)
                self.menu.addAction(act)
        self.menu_project = QMenu(self.win)
        for label, slot in (
                ('添加井到项目…', self._menu_add_well),
                ('批量添加井…', self._menu_add_wells_batch),
                (None, None),
                ('批量快速解释图（待解释井）', lambda: self._run_batch('quicklook')),
                ('批量综合解释（待解释井）', lambda: self._run_batch('comprehensive')),
                (None, None),
                ('打开项目根…', self._pick_root),
                ('管理源根…', self._menu_manage_roots),
                ('刷新', self.refresh)):
            if label is None:
                self.menu_project.addSeparator()
            else:
                act = QAction(label, self.win)
                act.triggered.connect(slot)
                self.menu_project.addAction(act)

        # ---- 右：属性 ----
        right = QFrame()
        right.setFrameShape(QFrame.StyledPanel)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 4, 6, 4)
        self.prop_title = self._mk_label('（未选择对象）', bold=True)
        self.prop_title.setStyleSheet('color: %s; font-weight: bold;' % C_ACCENT)
        rl.addWidget(self.prop_title)
        self.prop_type = self._mk_label('', small=True, muted=True)
        rl.addWidget(self.prop_type)
        self.nb = QTabWidget()
        rl.addWidget(self.nb, 1)
        self._tabs: dict = {}
        for key in ('概览', '井信息', '数据集', '变量', '资料', '原始'):
            txt = _qc.TextCompat(right)
            txt.setStyleSheet('font-family: Consolas; font-size: 9pt;')
            self.nb.addTab(txt, key)
            self._tabs[key] = txt
        bl.addWidget(right, 2)
        self._root_layout.addWidget(body, 1)

    def _build_output(self):
        out = QFrame()
        out.setFrameShape(QFrame.StyledPanel)
        ol = QVBoxLayout(out)
        ol.setContentsMargins(4, 4, 4, 4)
        cap = self._mk_label('输出', bold=True)
        ol.addWidget(cap)
        self.out_txt = _qc.TextCompat(out)
        self.out_txt.setMaximumHeight(90)
        self.out_txt.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        ol.addWidget(self.out_txt)
        self._root_layout.addWidget(out)

    def _bind_keys(self):
        QShortcut(QKeySequence('F5'), self.win, activated=self.refresh)
        QShortcut(QKeySequence('Escape'), self.win, activated=self._close)
        QShortcut(QKeySequence('Ctrl+F'), self.win, activated=self.focus_search)

    def focus_search(self):
        try:
            self.le_search.setFocus()
            self.le_search.selectAll()
        except Exception:
            pass

    def _schedule_filter(self):
        """过滤防抖：连续输入只在停顿后触发一次重扫。"""
        if self._filter_timer is not None:
            try:
                self._filter_timer.stop()
            except Exception:
                pass
        self._filter_timer = QTimer.singleShot(250, self._do_filter)

    def _do_filter(self):
        self._filter_timer = None
        self.refresh()

    def refresh(self):
        """重建树（过滤/分组实时生效）。"""
        # 项目成员 = 已登记的井 ∪ 产物目录子目录。
        # source_map 传 None 时自动取全部成员，确保"刚添加进项目、尚无产物"
        # 的井也能拿到源目录（否则它永远进不了项目树）。
        _smap = pcfg.source_map(self.root_dir)
        if self.source_root:
            for n in pcfg.project_member_names(self.root_dir):
                if n not in _smap:
                    _c = os.path.join(self.source_root, n)
                    if os.path.isdir(_c):
                        _smap[n] = _c
        _reg = {k: str(v.get('source_dir') or '')
                for k, v in pcfg.registered_wells(self.root_dir).items()}
        self.project = pm.scan_project(self.root_dir, self.source_root,
                                       source_map=_smap, registered=_reg)
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
        self._root_iid = root_iid

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
        self._member_var.set('成员 %d（已登记 %d）' % (s['wells'], len(_reg)))
        # 候选源根显示
        try:
            # 源根路径若在传递途中被损坏（如 ":\<数字>" 片段被吞），
            # 该源根下的井会永远探测不到 —— 刷新时顺手修复并提示。
            fixed = pcfg.repair_source_roots(self.root_dir)
            for old in fixed:
                self._log('已修复损坏的候选源根：%s → %s' % (old, pcfg.normalize_source_root(old)))
            _roots = pcfg.source_roots(self.root_dir)
            self.roots_var.set('（%d 个）%s' % (len(_roots), '；'.join(_roots[:2])))
            _bad = pcfg.invalid_source_roots(self.root_dir)
            if _bad:
                self._log('无效候选源根（目录不存在，井将探测不到）：%s' % '；'.join(_bad))
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
        self._set_tab('资料', '（项目视图 —— 选择一口井可查看其作业资料）')

    def _show_well(self, w: pm.Well):
        self.prop_title.configure(text=w.name)
        self.prop_type.configure(text='井 · %s' % w.status_label)
        s = pm.summarize(self.project)
        _registered = w.name in pcfg.registered_wells(self.root_dir)
        lines = [
            '井名        : %s' % w.name,
            '产物状态    : %s' % w.status_label,
            '源资料状态  : %s' % w.source_label,
            '项目登记    : %s' % ('已登记（项目成员）' if _registered
                                else '未登记（来自产物目录扫描）'),
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

        # 资料（原启动界面"手动校正资料"的下沉视图）：
        # 显示作业**实际会用的**文件，以及它是手工指定还是自动探测来的
        ins = self._well_inputs(w)
        ilines = [
            '原始资料目录: %s' % (w.source_dir or
                                   '（未关联 —— 右键「关联原始资料目录…」）'),
            '',
            '作业实际使用的文件（手工指定优先于自动探测）:',
        ]
        for key in ('las', 'gas', 'config'):
            label = pcfg.WELL_OPTION_LABELS.get(key, key)
            val, src = ins.get(key, ('', ''))
            ilines.append('  %s' % label)
            ilines.append('    文件 : %s' % (val or '（无）'))
            ilines.append('    来源 : %s' % (src or '—'))
            ilines.append('')
        ilines.append('右键井 → 指定主 LAS / 指定气测文件 / 选择甲方出图格式')
        self._set_tab('资料', '\n'.join(ilines))

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
        self._set_tab('资料', '（数据集视图）')
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

    def _menu_logview(self):
        """【R80/R81 交互绘图】打开该井的交互式测井图（logvis）。

        与 QuickLook / 综合解释并列的井级动作，但**不跑子进程**——
        直接读该井的既有产物（解释曲线集 + 井信息）在工作台内开交互画布。
        【R81】绘图模块统一为根目录 logvis.py，交互绘图已并入其中。
        """
        w = self._selected_well()
        if not w:
            self._log('请先选中一口井')
            return
        try:
            from logvis import open_logview, find_output_dir
        except Exception as e:
            self._log(f'交互绘图模块不可用：{e}')
            return
        opts = pcfg.well_options(self.root_dir, w.name)
        source_dir = w.source_dir or pcfg.resolve_source_dir(self.root_dir, w.name)
        out_dir = find_output_dir(self.root_dir, w.name)
        if not out_dir and not (opts.get('las') or source_dir):
            self._log('该井既无解释产物也无原始 LAS，无法交互绘图')
            return
        try:
            open_logview(self.win, w.name, out_dir=out_dir, source_dir=source_dir,
                         las_file=opts.get('las', ''))
            self._log(f'已打开交互绘图：{w.name}')
        except Exception as e:
            self._log(f'交互绘图打开失败：{e}')

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
        # 井级资料指定（手工指定优先于自动探测）
        opts = pcfg.well_options(self.root_dir, w.name)
        runner = pjob.JobRunner(on_log=self._on_job_log, on_done=self._on_job_done)
        self._job_runner = runner
        self._job_running = True
        ok = runner.start(job_type, w.source_dir, self.root_dir,
                          las_file=opts.get('las', ''),
                          gas_file=opts.get('gas', ''),
                          config_file=opts.get('config', ''),
                          well_name=w.name)
        if not ok:
            self._job_running = False
            return
        self._log('── %s：%s ──' % (label, w.name))

    # ---------------- 井级资料指定（原启动界面能力下沉） ----------------

    def _pick_input_file(self, title: str, well_name: str,
                         patterns: list[tuple[str, str]]) -> str:
        """弹出文件选择框，返回选中的路径（取消返回 ''）。"""
        initial = self.root_dir
        try:
            w = self._selected_well()
            if w and w.source_dir and os.path.isdir(w.source_dir):
                initial = w.source_dir
        except Exception:
            pass
        ftypes = [('所有文件', '*.*')] + patterns
        return _qg.open_file(title=title, initialdir=initial,
                             filetypes=ftypes, parent=self.win)

    def _set_input(self, key: str, value: str, label: str):
        """写入井级资料指定并刷新。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        if pcfg.set_well_option(self.root_dir, w.name, key, value):
            self._log('已指定 %s：%s' % (label, value or '（清除）'))
            self.refresh()
        else:
            self._log('指定失败：无法写入项目配置 %s' % pcfg.config_path(self.root_dir))

    def _menu_set_las(self):
        """手工指定主 LAS（防止自动探测选错文件）。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        f = self._pick_input_file(
            '选择 %s 的主测井 LAS' % w.name, w.name,
            [('LAS 文件', '*.las'), ('LAS/LAS2', '*.las2')])
        if f:
            self._set_input('las', f, '主 LAS')

    def _menu_set_gas(self):
        """手工指定气测文件。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        f = self._pick_input_file(
            '选择 %s 的气测数据文件' % w.name, w.name,
            [('Excel', '*.xls *.xlsx'), ('CSV', '*.csv'), ('文本', '*.txt')])
        if f:
            self._set_input('gas', f, '气测文件')

    def _menu_set_format(self):
        """手工指定甲方出图格式。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        f = self._pick_input_file(
            '选择 %s 的甲方出图格式（quicklook / 综合图）' % w.name, w.name,
            [('JSON', '*.json'), ('全部文件', '*.*')])
        if f:
            self._set_input('config', f, '甲方出图格式')

    def _menu_clear_inputs(self):
        """清除井级资料指定（回到自动探测）。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        if pcfg.clear_well_options(self.root_dir, w.name):
            self._log('已清除 %s 的资料指定（回到自动探测）' % w.name)
            self.refresh()
        else:
            self._log('清除失败：无法写入项目配置 %s' % pcfg.config_path(self.root_dir))

    def _well_inputs(self, w):
        """返回该井作业实际会用的文件（手工指定 > 自动探测）。

        格式：``{'las': (值, 来源), 'gas': (值, 来源), 'config': (值, 来源)}``
        """
        opts = pcfg.well_options(self.root_dir, w.name)
        out = {}

        las = opts.get('las', '')
        src = '手工指定' if las else ''
        if not las and w.source_dir:
            las = pjob.find_main_las(w.source_dir)
            src = '自动探测' if las else ''
        out['las'] = (las, src)

        gas = opts.get('gas', '')
        out['gas'] = (gas, '手工指定' if gas else '未指定')

        cfg = opts.get('config', '')
        src = '手工指定' if cfg else ''
        if not cfg and w.source_dir:
            cfg = pjob.find_client_format(w.source_dir)
            src = '自动探测' if cfg else ''
        out['config'] = (cfg, src)
        return out

    def _menu_bind_source(self):
        """把井的原始资料目录显式绑定并持久化到项目配置。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        d = _qg.select_dir(
            title='选择 %s 的原始资料目录（含 LAS / 地质资料 / 甲方格式）' % w.name,
            initialdir=w.source_dir or self.root_dir, parent=self.win)
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
        opts = pcfg.well_options(self.root_dir, w.name)
        runner = pjob.JobRunner(on_log=self._on_job_log, on_done=self._on_job_done)
        self._job_runner = runner
        self._job_running = True
        if not runner.start(job_type, w.source_dir, self.root_dir,
                            las_file=opts.get('las', ''),
                            gas_file=opts.get('gas', ''),
                            config_file=opts.get('config', ''),
                            well_name=w.name):
            self._job_running = False
            self._start_next_batch()

    def _menu_add_root(self):
        d = _qg.select_dir(title='添加候选原始资料根目录', parent=self.win)
        if not d:
            return
        if pcfg.add_source_root(self.root_dir, d):
            self._log('已添加候选源根：%s' % d)
            self.refresh()
        else:
            self._log('添加候选源根失败')

    def _menu_manage_roots(self):
        """管理候选源根（增删 + 显示已绑定关系）。"""
        dlg = QDialog(self.win)
        dlg.setWindowTitle('项目配置 — 候选源根与井绑定')
        dlg.resize(680, 480)
        vl = QVBoxLayout(dlg)
        vl.addWidget(self._mk_label('候选原始资料根目录（用于按井名自动探测源目录）', bold=True))
        lst = QListWidget()
        vl.addWidget(lst, 1)
        cfg = pcfg.load_config(self.root_dir)
        for r in cfg.get('source_roots', []):
            lst.addItem(str(r))

        vl.addWidget(self._mk_label('已绑定的井（井名 → 源目录）', bold=True))
        lst2 = QListWidget()
        vl.addWidget(lst2, 1)
        for k, v in sorted((cfg.get('wells') or {}).items()):
            lst2.addItem('%-24s → %s' % (k, v.get('source_dir', '')))

        bl = QHBoxLayout()
        b_add = self._mk_button(dlg, '添加…', lambda: self._root_add(lst))
        b_rm = self._mk_button(dlg, '移除选中', lambda: self._root_remove(lst))
        b_apply = self._mk_button(dlg, '应用并刷新', lambda: (dlg.accept(), self.refresh()))
        bl.addWidget(b_add)
        bl.addWidget(b_rm)
        bl.addStretch(1)
        bl.addWidget(b_apply)
        vl.addLayout(bl)
        dlg.exec_()

    def _root_add(self, lst):
        d = _qg.select_dir(title='添加候选原始资料根目录', parent=self.win)
        if d:
            pcfg.add_source_root(self.root_dir, d)
            lst.addItem(d)

    def _root_remove(self, lst):
        cur = lst.currentItem()
        if cur is None:
            return
        pcfg.remove_source_root(self.root_dir, cur.text())
        lst.takeItem(lst.row(cur))

    def _ask_yes_no(self, title: str, message: str) -> bool:
        return _qg.yes_no(title, message, self.win)

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
        QApplication.clipboard().setText(p)
        self._log('已复制路径：%s' % p)

    def _menu_conditional(self):
        """条件选择（Techlog Conditional selection）。"""
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        dlg = QDialog(self.win)
        dlg.setWindowTitle('条件选择变量 — %s' % w.name)
        dlg.resize(620, 460)
        vl = QVBoxLayout(dlg)
        vl.addWidget(self._mk_label('按族 / 单位 / 类型筛选变量（留空 = 不过滤）', bold=True))

        fams = sorted({v.family for d in w.datasets for v in d.variables if v.family})
        units = sorted({v.unit for d in w.datasets for v in d.variables if v.unit})
        kinds = sorted({v.kind for d in w.datasets for v in d.variables})
        combos = {}
        for label, vals in (('族', fams), ('单位', units), ('类型', kinds)):
            row = QHBoxLayout()
            row.addWidget(self._mk_label(label))
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItems([''] + list(vals))
            cb.setFixedWidth(300)
            row.addWidget(cb)
            row.addStretch(1)
            vl.addLayout(row)
            combos[label] = cb

        res = _qc.TextCompat(dlg)
        vl.addWidget(res, 1)

        def _run():
            sel = pm.conditional_select(pm.Project(self.project.name, self.project.path, [w]),
                                        family=combos['族'].currentText().strip(),
                                        unit=combos['单位'].currentText().strip(),
                                        kind=combos['类型'].currentText().strip())
            res.clear()
            if not sel:
                res.insert('1.0', '（无匹配变量）')
                return
            lines = []
            for well, dss in sel.items():
                for dn, vs in dss.items():
                    lines.append('%s / %s\n' % (well, dn))
                    for v in vs:
                        lines.append('    %s\n' % v)
                    lines.append('\n')
            res.insert('1.0', ''.join(lines))

        bl = QHBoxLayout()
        bl.addWidget(self._mk_button(dlg, '执行选择', _run))
        bl.addStretch(1)
        bl.addWidget(self._mk_button(dlg, '关闭', dlg.accept))
        vl.addLayout(bl)
        dlg.exec_()

    # ---------------- 项目成员管理（把井添加到项目） ----------------

    def _default_src_dir(self) -> str:
        """默认打开的目录：已登记的第一个源目录，或候选源根的第一个。"""
        try:
            reg = pcfg.registered_wells(self.root_dir)
            for v in reg.values():
                d = str(v.get('source_dir') or '')
                if d and os.path.isdir(d):
                    return d
            roots = pcfg.source_roots(self.root_dir)
            for r in roots:
                if os.path.isdir(r):
                    return r
        except Exception:
            pass
        return os.path.abspath(self.root_dir)

    def _ask_add_wells(self, path: str, title: str = '添加井到项目'):
        """弹出"添加到项目"对话框。

        返回 ``[(井名, 源目录), ...]``；用户取消或无可添加项返回 ``None``。

        井名即**产物落盘目录名**（logInt 用 ``output/<LAS井名>/``），也是
        项目内标识。因此这里优先用 **LAS 里记录的井名**（读不到才用目录名），
        登记名与产物目录名天然一致，闭环不需要靠事后归集来救。
        """
        cands = pcfg.discover_wells_in_dir(path)
        if not cands:
            _qg.warn('添加井到项目',
                     '在所选目录里没有发现 LAS 文件：\n%s\n\n'
                     '请选择一口井的资料目录，或一个包含多口井的资料根目录。' % path,
                     self.win)
            return None

        used = set()
        for c in cands:
            las_wn = pm.las_well_name(c.get('las_path', '')) or ''
            name = las_wn or c['name']
            if name in used:
                name = c['name']
            used.add(name)
            c['well_name'] = name
            c['las_well_name'] = las_wn

        result: dict = {}
        dlg = QDialog(self.win)
        dlg.setWindowTitle(title)
        dlg.resize(600, 500)
        vl = QVBoxLayout(dlg)
        vl.addWidget(self._mk_label('原始资料目录', small=True, muted=True))
        p_lab = self._mk_label(path)
        p_lab.setWordWrap(True)
        vl.addWidget(p_lab)

        name_edit = None
        lb = None
        if len(cands) == 1:
            c = cands[0]
            vl.addWidget(self._mk_label('井名（= 项目内标识，也是产物落盘目录名）',
                                        small=True, muted=True))
            name_edit = QLineEdit(c['well_name'])
            vl.addWidget(name_edit)
            hint = '发现 %d 个文件（主 LAS：%s）' % (c['files'], c.get('las', ''))
            if c['las_well_name'] and c['las_well_name'] != c['name']:
                hint += '\nLAS 记录井名：%s  →  产物将落在 output/%s/' % (
                    c['las_well_name'], c['well_name'])
            h = self._mk_label(hint, small=True, muted=True)
            h.setWordWrap(True)
            vl.addWidget(h)
        else:
            vl.addWidget(self._mk_label('发现 %d 口井，勾选要加入项目的井' % len(cands),
                                        small=True, muted=True))
            lb = QListWidget()
            lb.setSelectionMode(QAbstractItemView.ExtendedSelection)
            for c in cands:
                tail = '' if c['well_name'] == c['name'] \
                    else '   (LAS 井名 %s)' % c['las_well_name']
                lb.addItem('%-22s %3d 个文件%s' % (c['well_name'], c['files'], tail))
            for i in range(lb.count()):
                lb.item(i).setSelected(True)
            vl.addWidget(lb, 1)
            vl.addWidget(self._mk_label('井名取自 LAS 记录（与产物目录同名）；'
                                        '如需改名，添加后再单独调整',
                                        small=True, muted=True))

        def _ok():
            if lb is not None:
                rows = [lb.row(it) for it in lb.selectedItems()]
                picks = [(cands[i]['well_name'], cands[i]['dir']) for i in rows]
            else:
                n = name_edit.text().strip() if name_edit else ''
                picks = [(n, cands[0]['dir'])] if n else []
            if not picks:
                _qg.warn('添加井到项目', '请至少选择一口井。', dlg)
                return
            result['picks'] = picks
            dlg.accept()

        bl = QHBoxLayout()
        bl.addStretch(1)
        bl.addWidget(self._mk_button(dlg, '取消', dlg.reject))
        bl.addWidget(self._mk_button(dlg, '添加到项目', _ok))
        vl.addLayout(bl)
        dlg.exec_()
        return result.get('picks')

    def _menu_add_well(self):
        """把井添加到项目：选资料目录 → 确认井名 → 登记。"""
        path = _qg.select_dir(
            title='选择井的原始资料目录（含 LAS / 地质设计 / 甲方格式）',
            initialdir=self._default_src_dir(), parent=self.win)
        if not path:
            return
        picks = self._ask_add_wells(path, title='添加井到项目')
        if not picks:
            return
        added, failed = [], []
        for name, src in picks:
            if pcfg.add_well_to_project(self.root_dir, name, src):
                added.append(name)
            else:
                failed.append(name)
        if added:
            self._log('已添加 %d 口井到项目：%s' % (len(added), '；'.join(added)))
        if failed:
            self._log('添加失败（源目录不存在）：%s' % '；'.join(failed))
        self.refresh()
        if added:
            self._select_well(added[0])

    def _menu_add_wells_batch(self):
        """批量添加：选一个资料根，把里面多口井一次性加进项目。"""
        path = _qg.select_dir(
            title='选择包含多口井的资料根目录',
            initialdir=self._default_src_dir(), parent=self.win)
        if not path:
            return
        picks = self._ask_add_wells(path, title='批量添加井到项目')
        if not picks:
            return
        added, failed = [], []
        for name, src in picks:
            if pcfg.add_well_to_project(self.root_dir, name, src):
                added.append(name)
            else:
                failed.append(name)
        if added:
            self._log('已批量添加 %d 口井到项目：%s' % (len(added), '；'.join(added)))
        if failed:
            self._log('添加失败（源目录不存在）：%s' % '；'.join(failed))
        self.refresh()
        if added:
            self._select_well(added[0])

    def _ask_text(self, title: str, prompt: str, default: str = '') -> str | None:
        """单行输入对话框。取消返回 None。"""
        return _qg.text_input(title, prompt, default, self.win)

    def _menu_rename_well(self):
        """重命名项目内的井。

        井名 = 项目内标识 = 产物落盘目录名，因此改名时**产物目录一并改名**，
        保证"作业在项目里做 → 产物回到项目树"的闭环不被改名打断。
        """
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        new = self._ask_text('重命名井', '新的井名：\n（= 项目内标识，也是产物目录名；'
                                         '建议与 LAS 记录井名一致）', w.name)
        if not new or new == w.name:
            return
        reg = pcfg.registered_wells(self.root_dir)
        if new in reg:
            _qg.warn('重命名井', '项目里已存在井「%s」。' % new, self.win)
            return
        old_dir = os.path.join(self.root_dir, w.name)
        new_dir = os.path.join(self.root_dir, new)
        if os.path.exists(new_dir):
            _qg.warn('重命名井',
                                   '目标产物目录已存在：\n%s\n\n请先清理或改名。' % new_dir,
                                   self.win)
            return
        # 1) 迁移产物目录
        moved = False
        if os.path.isdir(old_dir):
            try:
                os.replace(old_dir, new_dir)
                moved = True
            except Exception as e:
                self._log('产物目录改名失败：%s' % e)
        # 2) 迁移项目登记（保留源目录与资料指定）
        entry = dict(reg.get(w.name) or {})
        src = str(entry.get('source_dir') or w.source_dir or '')
        if w.name in reg:
            pcfg.remove_well_from_project(self.root_dir, w.name)
        if src:
            extra = {k: v for k, v in entry.items() if k in pcfg.WELL_OPTIONS}
            pcfg.add_well_to_project(self.root_dir, new, src, extra=extra)
        self._log('井已重命名：%s → %s%s' % (w.name, new, '（产物目录已改名）' if moved else ''))
        self.refresh()
        self._select_well(new)

    def _ask_yes_no_cancel(self, title: str, message: str) -> str:
        """三态确认框。返回 'yes' / 'no' / 'cancel'。"""
        return _qg.yes_no_cancel(title, message, self.win)

    def _menu_remove_well(self):
        """把井从项目移除。

        语义要分清：**移除登记** ≠ **删除产物**。
        - 无产物的井（纯登记成员）→ 移除后真正从项目树消失；
        - 有产物的井 → 产物目录还在，它就仍会被扫到。此时询问是否一并
          删除产物目录（不可恢复），默认保留并明确告知用户。
        """
        w = self._selected_well()
        if not w:
            self._log('请先选择一口井')
            return
        reg = pcfg.registered_wells(self.root_dir)
        if w.name not in reg:
            self._log('井 %s 不在项目登记名单里（来自产物目录扫描）—— '
                      '如需移出项目，请连同其产物目录一起删除' % w.name)
            return
        # 产物目录存在且非空即视为"有产物"（不依赖是否识别出规则内的数据集 ——
        # 目录里可能有尚未归类的文件，删不删必须问用户）
        has_products = False
        try:
            has_products = os.path.isdir(w.path) and bool(os.listdir(w.path))
        except OSError:
            has_products = False
        if has_products:
            ans = self._ask_yes_no_cancel(
                '从项目移除',
                '井「%s」在项目里已有产物：\n%s\n\n'
                '【是】删除产物目录并把井移出项目（不可恢复）\n'
                '【否】保留一切，什么都不做\n\n'
                '（只解除登记而保留产物会让这口井变成"有产物、缺原始资料"的孤儿，'
                '因此不做这种半吊子操作）' % (w.name, w.path))
            if ans == 'cancel':
                return
            if ans == 'no':
                self._log('已取消：井 %s 保持不变（产物与原始资料绑定都保留）' % w.name)
                return
            import shutil
            try:
                shutil.rmtree(w.path)
            except Exception as e:
                self._log('删除产物目录失败：%s' % e)
                return
            pcfg.remove_well_from_project(self.root_dir, w.name)
            self._log('已把井 %s 移出项目（产物目录已删除）' % w.name)
            self.refresh()
            return
        if not self._ask_yes_no('从项目移除',
                                '把井「%s」移出项目？\n\n'
                                '该井尚无产物，只解除项目登记。' % w.name):
            return
        if pcfg.remove_well_from_project(self.root_dir, w.name):
            self._log('已把井 %s 移出项目' % w.name)
            self.refresh()
        else:
            self._log('移除失败：井 %s' % w.name)

    def _select_well(self, name: str):
        """按井名选中树中对应节点（并刷新属性面板）。"""
        for iid, w in self._wells_by_iid.items():
            if w.name == name:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                self._on_select()
                QApplication.processEvents()
                return True
        return False

    def _popup_menu(self, evt):
        sel = self.tree.identify_row(evt.y)
        if sel:
            self.tree.selection_set(sel)
        # 项目根节点 → 项目成员管理菜单；井 / 数据集 → 井级操作菜单
        menu = self.menu_project if sel and sel == getattr(self, '_root_iid', '') \
            else self.menu
        menu.exec_(QCursor.pos())

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
        d = _qg.select_dir(title='选择项目根目录（每子目录 = 一口井）',
                           initialdir=self.root_dir, parent=self.win)
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
            self.win.close()
        except Exception:
            pass

    def show(self):
        self.win.show()

    def run(self):
        self.win.show()
        return _qg.exec_app()


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
    """启动项目工作台（主界面）。

    root 为空时：优先使用默认项目根（仓库 ``output/``），不存在才弹窗选择。
    【2026-11-11 界面整合】启动后**直接**进入本界面工作，不再经过前置对话框。
    """
    if not root:
        _d = default_root()
        if os.path.isdir(_d):
            root = _d
        else:
            root = _qg.select_dir(title='选择项目根目录（每子目录 = 一口井）',
                                  initialdir=os.path.dirname(_d) or '.')
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
