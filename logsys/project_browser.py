# -*- coding: utf-8 -*-
"""项目工作台 GUI（唯一入口）：Project → Well → Dataset → Variable 四层树。

借鉴 Techlog 的窗口分区范式，R86 起整理为：

  顶部功能区             —— 数据功能（加载/清洗/质检/导入/导出）、
                             解释处理（快速/综合/气测/核磁/电成像/交互绘图）、项目级批量
  左侧 Project browser   —— 四层树 + 过滤 + 分组 + 搜索
  右侧 Properties/功能   —— 属性页（选中对象）+ 功能页（各功能独立面板与输入行）
  底部 Output window     —— 作业日志、数据操作结果与错误

所有处理作业的输入都在「功能」页内完成（下拉来自数据加载扫描，或直接粘贴路径），
不再弹文件对话框；气测/核磁/电成像走独立子进程 CLI，见 logsys/process_cli.py。

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
    QMenu, QAction, QListWidget, QListWidgetItem, QAbstractItemView,
    QTextEdit, QShortcut, QTabWidget, QSizePolicy, QToolButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
)

from logsys import qtgui as _qg
from logsys import qtcompat as _qc
from logsys import project_config as pcfg
from logsys import project_job as pjob
from logsys import project_model as pm
from logsys import data_ops as dop
from logsys import variable_catalog as vc

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
        self._open_logview_windows: list = []   # R85: 保持交互绘图窗口引用，防 Qt GC

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
        # 【R89】多项目支持：菜单栏 + 窗口标题带项目名 + 记录最近项目
        self._build_menubar()
        self._update_title()
        self._recent_record(self.root_dir)

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

    def _mk_tile(self, text, tip, slot):
        """功能区按钮（Techlog ribbon 风格：短标签 + 悬浮说明）。"""
        b = QPushButton(text)
        b.setFixedSize(88, 32)
        b.setToolTip(tip)
        b.setStyleSheet(
            'QPushButton { background: #eef3f9; border: 1px solid %s; '
            'border-radius: 3px; color: %s; font-size: 9pt; }'
            'QPushButton:hover { background: #dce9f7; }' % (C_LINE, C_ACCENT))
        b.clicked.connect(slot)
        if text == '交互绘图':
            # 兼容 R85 冒烟/脚本对按钮的引用
            self.btn_logview = b
        return b

    def _ribbon_group(self, title, tiles):
        """一个功能分组：标题 + 一行按钮。"""
        frame = QFrame()
        frame.setStyleSheet('background: transparent;')
        vl = QVBoxLayout(frame)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(1)
        cap = self._mk_label(title, bold=True, small=True)
        cap.setStyleSheet('color: %s; font-size: 8pt; font-weight: bold;' % C_MUTED)
        vl.addWidget(cap)
        hl = QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(3)
        for text, tip, slot in tiles:
            hl.addWidget(self._mk_tile(text, tip, slot))
        vl.addLayout(hl)
        return frame

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
        hl.addWidget(self._mk_button(hdr, '项目根设置…', self._pick_root))
        hl.addWidget(self._mk_button(hdr, '刷新', self.refresh))
        root.addWidget(hdr)

        # 【R86】Techlog 风格功能区：数据功能 / 解释处理 / 项目级批量
        # 每一类功能只有一个入口，点按钮在右侧「功能」页展开对应面板。
        rib = QFrame()
        rib.setStyleSheet('background: %s; border-bottom: 1px solid %s;' % (C_PANEL, C_LINE))
        ril = QHBoxLayout(rib)
        ril.setContentsMargins(8, 2, 8, 4)
        ril.setSpacing(8)
        ril.addWidget(self._ribbon_group('数据功能', [
            ('数据加载', '扫描该井全部可用数据（只读）', self._show_func_load),
            ('数据清洗', '单位归一 + 缺测/非法值 + 深度整理', self._show_func_clean),
            ('数据质检', '深度/曲线/值域检查并出报告', self._show_func_qc),
            ('数据导入', '复制外部数据到井资料目录', self._show_func_import),
            ('数据导出', '曲线集导出 CSV / XLSX / LAS', self._show_func_export),
            # 【R87】变量字典库：族/分支/单位/绘图方式/图例的唯一编辑入口
            ('变量库', '族 → 分支变量 → 图例：族名、单位、绘图方式增删改',
             self._show_func_catalog),
        ]))
        ril.addWidget(self._vline())
        ril.addWidget(self._ribbon_group('解释处理', [
            ('快速解释', 'QuickLook 一键出图', lambda: self._show_func_job('quicklook')),
            ('综合解释', '完整测井解释流程', lambda: self._show_func_job('comprehensive')),
            ('气测解释', '图版法 ITP + 相对异常曲线', lambda: self._show_func_job('gas')),
            ('核磁处理', 'T2 谱 / 孔隙度 / 渗透率', lambda: self._show_func_job('nmr')),
            ('电成像处理', '孔隙 / 溶孔 / 裂缝识别', lambda: self._show_func_job('fmi')),
            ('交互绘图', '独立 logvis：拖曲线、改图头', self._show_func_logview),
        ]))
        ril.addWidget(self._vline())
        ril.addWidget(self._ribbon_group('项目级', [
            ('添加井', '登记一口井到项目', self._show_func_batch_add),
            ('批量添加', '从资料根批量登记井', self._show_func_batch_add),
            ('批量快速', '对待解释井批量 QuickLook', lambda: self._run_batch('quicklook')),
            ('批量综合', '对待解释井批量综合解释', lambda: self._run_batch('comprehensive')),
        ]))
        ril.addStretch(1)
        root.addWidget(rib)

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

        fl.addWidget(self._vline())
        fl.addWidget(self._mk_label('候选源根', small=True, muted=True))
        self.roots_var = _qc.Var()
        self.lbl_roots = self._mk_label('', small=True, muted=True)
        self.roots_var.bind_label(self.lbl_roots)
        self.lbl_roots.setMaximumWidth(260)
        fl.addWidget(self.lbl_roots)
        fl.addWidget(self._mk_button(fl, '源根管理', self._show_func_roots))

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
                ('气测解释', self._menu_gas),
                ('核磁处理', self._menu_nmr),
                ('电成像处理', self._menu_fmi),
                ('交互绘图（logvis）…', self._menu_logview),
                (None, None),
                ('数据加载 / 输入指定', self._show_func_load),
                ('数据导入（界面内输入路径）', self._show_func_import),
                ('清除资料指定', self._menu_clear_inputs),
                (None, None),
                ('打开该井解释', self._menu_open_well),
                ('打开产物目录', self._menu_open_dir),
                ('打开源资料目录', self._menu_open_source),
                ('复制路径', self._menu_copy_path),
                (None, None),
                ('关联原始资料目录（界面内输入）', self._show_func_import),
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
                ('添加井到项目…', self._show_func_batch_add),
                ('批量添加井…', self._show_func_batch_add),
                (None, None),
                ('批量快速解释图（待解释井）', lambda: self._run_batch('quicklook')),
                ('批量综合解释（待解释井）', lambda: self._run_batch('comprehensive')),
                (None, None),
                ('气测解释（选中井）', self._menu_gas),
                ('核磁处理（选中井）', self._menu_nmr),
                ('电成像处理（选中井）', self._menu_fmi),
                (None, None),
                ('项目根设置…', self._pick_root),
                ('管理源根…', self._show_func_roots),
                ('刷新', self.refresh)):
            if label is None:
                self.menu_project.addSeparator()
            else:
                act = QAction(label, self.win)
                act.triggered.connect(slot)
                self.menu_project.addAction(act)

        # ---- 右：属性 / 功能（Techlog Properties window + Process panel） ----
        right = QFrame()
        right.setFrameShape(QFrame.StyledPanel)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 3, 4, 3)
        self.right_nb = QTabWidget()
        rl.addWidget(self.right_nb, 1)

        # 属性页（原 Properties window，保持原有六个分页）
        prop_page = QWidget()
        pl = QVBoxLayout(prop_page)
        pl.setContentsMargins(4, 2, 4, 2)
        self.prop_title = self._mk_label('（未选择对象）', bold=True)
        self.prop_title.setStyleSheet('color: %s; font-weight: bold;' % C_ACCENT)
        pl.addWidget(self.prop_title)
        self.prop_type = self._mk_label('', small=True, muted=True)
        pl.addWidget(self.prop_type)
        self.nb = QTabWidget()
        pl.addWidget(self.nb, 1)
        self._tabs: dict = {}
        for key in ('概览', '井信息', '数据集', '变量', '资料', '原始'):
            txt = _qc.TextCompat(prop_page)
            txt.setStyleSheet('font-family: Consolas; font-size: 9pt;')
            self.nb.addTab(txt, key)
            self._tabs[key] = txt
        self.right_nb.addTab(prop_page, '属性')

        # 功能页（每个功能区按钮各自一套说明 + 动作）
        func_page = QWidget()
        fl2 = QVBoxLayout(func_page)
        fl2.setContentsMargins(4, 4, 4, 4)
        self.func_title = self._mk_label('（未选择功能）', bold=True)
        self.func_title.setStyleSheet('color: %s; font-weight: bold; font-size: 11pt;' % C_ACCENT)
        fl2.addWidget(self.func_title)
        self.func_text = _qc.TextCompat(func_page)
        self.func_text.setReadOnly(True)
        self.func_text.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        # 【R87】功能页两页：普通功能说明 / 变量字典库编辑器（表格增删改）
        self.func_stack = QStackedWidget()
        self.func_stack.addWidget(self.func_text)                 # index 0
        self.catalog_page = self._build_catalog_page()            # index 1
        self.func_stack.addWidget(self.catalog_page)
        self.conditional_page = self._build_conditional_page()    # index 2
        self.func_stack.addWidget(self.conditional_page)
        # 【R88】候选源根管理 / 批量添加井：也收进功能页，主界面零弹窗
        self.roots_page = self._build_roots_page()                # index 3
        self.func_stack.addWidget(self.roots_page)
        self.batch_page = self._build_batch_add_page()            # index 4
        self.func_stack.addWidget(self.batch_page)
        # 【R89】项目管理（新建 / 打开 / 保存 / 最近项目）
        self.project_page = self._build_project_page()            # index 5
        self.func_stack.addWidget(self.project_page)
        fl2.addWidget(self.func_stack, 1)
        # 输入行：与「数据加载」共用扫描结果，下拉可选/可直接粘贴路径，无文件对话框
        self.func_input_row = QHBoxLayout()
        self.func_input_row.setContentsMargins(0, 2, 0, 2)
        self.func_input_lab = self._mk_label('输入数据', small=True, muted=True)
        self.func_input_type = QComboBox()
        for k in pcfg.WELL_OPTIONS:
            self.func_input_type.addItem(pcfg.WELL_OPTION_LABELS.get(k, k), k)
        self.func_input_type.addItem('原始资料目录', 'source_dir')
        self.func_input_type.setFixedWidth(120)
        self.func_input_type.currentIndexChanged.connect(
            lambda: self._fill_func_input(getattr(self, '_func_input_kind', '')))
        self.func_input_combo = QComboBox()
        self.func_input_combo.setEditable(True)
        self.func_input_combo.setMinimumWidth(360)
        self.func_input_apply = QPushButton('应用输入')
        self.func_input_apply.clicked.connect(self._apply_func_input)
        self.func_input_row.addWidget(self.func_input_lab)
        self.func_input_row.addWidget(self.func_input_type)
        self.func_input_row.addWidget(self.func_input_combo, 1)
        self.func_input_row.addWidget(self.func_input_apply)
        fl2.addLayout(self.func_input_row)
        self.func_actions = QHBoxLayout()
        self.func_actions.setContentsMargins(0, 2, 0, 0)
        fl2.addLayout(self.func_actions)
        self.right_nb.addTab(func_page, '功能')

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
        # 【R85】双击井节点 = 直接打开交互绘图（选中态由 QTreeWidget 自身处理）
        self.tree.bind('<Double-1>', self._on_tree_double)

    def _on_tree_double(self, _evt=None):
        """双击处理：命中井节点则打开该井交互绘图，双击数据集则展开/属性。"""
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        w = self._wells_by_iid.get(iid)
        if w is not None:
            self._menu_logview()

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
        # 重建前记住选中井：界面内应用输入/作业完成后刷新不应丢掉当前井，
        # 否则紧接着的「对选中井执行」会变成"请先选择一口井"。
        prev_sel = self.tree.selection()
        prev_well = ''
        if prev_sel and prev_sel[0] in self._wells_by_iid:
            prev_well = self._wells_by_iid[prev_sel[0]].name
        elif prev_sel and prev_sel[0] in self._ds_by_iid:
            for w in self.project.wells:
                if any(ds is self._ds_by_iid[prev_sel[0]] for ds in w.datasets + w.source_datasets):
                    prev_well = w.name
                    break
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

        if prev_well:
            for iid, w in self._wells_by_iid.items():
                if w.name == prev_well:
                    self.tree.selection_set(iid)
                    break

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
        self._refresh_func_panel()

    def _refresh_func_panel(self):
        """刷新后同步功能面板（作业完成即可看到新产物计数）。"""
        try:
            if getattr(self, 'right_nb', None) is None or self.right_nb.currentIndex() != 1:
                return
            title = self.func_title.text()
            table = {'数据加载': self._show_func_load, '数据清洗': self._show_func_clean,
                     '数据质检': self._show_func_qc, '数据导入': self._show_func_import,
                     '数据导出': self._show_func_export,
                     '快速解释图': lambda: self._show_func_job('quicklook'),
                     '综合解释': lambda: self._show_func_job('comprehensive'),
                     '气测解释': lambda: self._show_func_job('gas'),
                     '核磁处理': lambda: self._show_func_job('nmr'),
                     '电成像处理': lambda: self._show_func_job('fmi'),
                     '变量字典库': self._show_func_catalog,
                     '条件选择变量': self._show_func_conditional,
                     '项目根设置': self._show_func_root,
                     '交互绘图': self._show_func_logview}
            for prefix, slot in table.items():
                if title.startswith(prefix):
                    slot()
                    return
        except Exception:
            pass

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
            # 【R87】Techlog 式「族 → 分支变量」两级：变量挂在输入 LAS/DLIS 数据集下
            for gname, vs in pm.group_variables(ds.variables):
                mode = (vs[0].draw_mode if vs else '') or 'linear'
                legend = (vs[0].legend_id if vs else '') or ''
                detail = '%d 变量 ｜ %s' % (len(vs), mode)
                if legend:
                    detail += ' ｜ 图例 %s' % legend
                giid = self.tree.insert(iid, 'end',
                                        text='▣ %s（%d）' % (gname, len(vs)),
                                        values=('族', detail),
                                        tags=('dataset',), open=True)
                for v in vs:
                    origin = '解释' if v.origin == 'interpretation' else '输入'
                    self.tree.insert(giid, 'end', text='  %s' % v.name,
                                     values=(v.family or '（无分支）',
                                             '%s ｜ %s ｜ %s' % (
                                                 v.unit or '（无单位）', origin,
                                                 v.draw_mode or 'linear')),
                                     tags=(v.color,))
        return iid

    # ---------------- 属性面板 ----------------

    # ---------------- 功能面板（R86：数据功能 / 解释处理各归一处） ----------------

    def _well_out_dir(self, w) -> str:
        return os.path.join(self.root_dir, w.name) if w else ''

    def _processed_csv(self, w) -> str:
        if not w:
            return ''
        p = os.path.join(self._well_out_dir(w), '%s_processed.csv' % w.name)
        return p if os.path.isfile(p) else ''

    # ---------------- 【R87】变量字典库编辑器（界面内增删改，无弹窗） ----------------

    _CAT_HEADERS = {
        'groups': (['族 id', '族名', '绘图方式', '默认单位', '图例', '族色', '顺序', '说明'],
                   '族决定绘图方式：定性族（岩性/解释结论）会调用对应图例；族名、单位可直接改。'),
        'variables': (['曲线名', '分支显示名', '所属族', '单位', '刻度', '图例',
                       '别名(逗号分隔)', '说明'],
                      '解释产物都是曲线变量；改「所属族」即改变其分组与绘图方式。'),
        'legend_codes': (['图例 id', '代码(可含 | 别名)', '中文标签', '颜色'],
                         '岩性族 / 解释结论族绘制时按「代码 → 标签 + 颜色」调用图例。'),
        'prefix_rules': (['前缀', '分支显示名', '所属族', '单位', '刻度', '图例'],
                         '未精确登记的曲线按前缀归族（长前缀优先）。'),
    }

    def _build_catalog_page(self):
        """变量库编辑器：一张可编辑表格 + 表类型下拉（四张逻辑表共用）。"""
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(2, 2, 2, 2)
        top = QHBoxLayout()
        top.addWidget(self._mk_label('变量字典库', bold=True))
        top.addWidget(self._mk_label('表：', small=True, muted=True))
        self.cat_kind = QComboBox()
        for key, label in (('groups', '族'), ('variables', '分支变量'),
                           ('legend_codes', '图例代码'), ('prefix_rules', '前缀规则')):
            self.cat_kind.addItem(label, key)
        self.cat_kind.setFixedWidth(130)
        self.cat_kind.currentIndexChanged.connect(lambda *_: self._cat_reload())
        top.addWidget(self.cat_kind)
        top.addStretch(1)
        self.cat_hint = self._mk_label('', small=True, muted=True)
        top.addWidget(self.cat_hint)
        vl.addLayout(top)
        self.cat_table = QTableWidget()
        self.cat_table.setAlternatingRowColors(True)
        self.cat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cat_table.setStyleSheet('font-size: 9pt;')
        self.cat_table.horizontalHeader().setStretchLastSection(True)
        vl.addWidget(self.cat_table, 1)
        return page

    def _cat_options(self):
        cat = vc.as_dict()
        return {
            'legend': [('（无）', '')] + [
                ('%s · %s' % (lg.get('id'), lg.get('name', '')), lg.get('id'))
                for lg in cat.get('legends', [])],
            'group': [('（未分类）', 'UNCLASSIFIED')] + [
                ('%s · %s' % (g.get('id'), g.get('name', '')), g.get('id'))
                for g in cat.get('groups', [])],
            'mode': [(m, m) for m in vc.DRAW_MODES],
            'scale': [(s, s) for s in vc.SCALES],
        }

    def _cat_combo(self, options, current):
        cb = QComboBox()
        for label, value in options:
            cb.addItem(str(label), value)
        idx = cb.findData(current)
        if idx >= 0:
            cb.setCurrentIndex(idx)
        elif current:
            cb.insertItem(0, str(current), current)
            cb.setCurrentIndex(0)
        return cb

    def _cat_combo_cols(self, kind):
        opts = self._cat_options()
        if kind == 'groups':
            return {2: opts['mode'], 4: opts['legend']}
        if kind == 'variables':
            return {2: opts['group'], 4: opts['scale'], 5: opts['legend']}
        if kind == 'legend_codes':
            return {0: [(lg['id'], lg['id']) for lg in vc.legends()]}
        return {2: opts['group'], 4: opts['scale'], 5: opts['legend']}

    def _cat_reload(self):
        kind = self.cat_kind.currentData() or 'groups'
        headers, hint = self._CAT_HEADERS[kind]
        cat = vc.as_dict()
        rows: list[list[str]] = []
        if kind == 'groups':
            for g in cat.get('groups', []):
                rows.append([g.get('id', ''), g.get('name', ''), g.get('draw_mode', ''),
                             g.get('unit_default', ''), g.get('legend_id', ''),
                             g.get('color', ''), str(g.get('order', '')), g.get('note', '')])
        elif kind == 'variables':
            for v in cat.get('variables', []):
                rows.append([v.get('key', ''), v.get('name', ''), v.get('group_id', ''),
                             v.get('unit', ''), v.get('scale', ''), v.get('legend_id', ''),
                             ','.join(v.get('aliases') or []), v.get('note', '')])
        elif kind == 'legend_codes':
            for lg in cat.get('legends', []):
                for c in lg.get('codes') or []:
                    rows.append([lg.get('id', ''), c[0] if len(c) > 0 else '',
                                 c[1] if len(c) > 1 else '',
                                 c[2] if len(c) > 2 else ''])
        else:
            for r in cat.get('prefix_rules', []):
                rows.append([r.get('prefix', ''), r.get('name', ''), r.get('group_id', ''),
                             r.get('unit', ''), r.get('scale', ''), r.get('legend_id', '')])
        cols = self._cat_combo_cols(kind)
        self.cat_table.blockSignals(True)
        self.cat_table.setColumnCount(len(headers))
        self.cat_table.setHorizontalHeaderLabels(headers)
        self.cat_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if c in cols:
                    self.cat_table.setCellWidget(r, c, self._cat_combo(cols[c], str(val)))
                else:
                    self.cat_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.cat_table.resizeColumnsToContents()
        self.cat_table.horizontalHeader().setStretchLastSection(True)
        self.cat_table.blockSignals(False)
        self.cat_hint.setText(hint)

    def _cat_cell(self, r, c) -> str:
        w = self.cat_table.cellWidget(r, c)
        if isinstance(w, QComboBox):
            return str(w.currentData() or '')
        it = self.cat_table.item(r, c)
        return it.text().strip() if it else ''

    def _cat_row(self, r) -> list[str]:
        return [self._cat_cell(r, c) for c in range(self.cat_table.columnCount())]

    def _cat_add_row(self):
        r = self.cat_table.rowCount()
        self.cat_table.insertRow(r)
        cols = self._cat_combo_cols(self.cat_kind.currentData() or 'groups')
        for c in range(self.cat_table.columnCount()):
            if c in cols:
                self.cat_table.setCellWidget(r, c, self._cat_combo(cols[c], ''))
            else:
                self.cat_table.setItem(r, c, QTableWidgetItem(''))
        self._log('已新增一行 —— 填好后点「保存到变量库」')

    def _cat_del_row(self):
        rows = sorted({i.row() for i in self.cat_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.cat_table.removeRow(r)
        self._log('已删除 %d 行（点「保存到变量库」后生效）' % len(rows))

    def _cat_save(self):
        """把当前表格整表写回变量库（含新增/删除/改名），随后刷新项目树。"""
        kind = self.cat_kind.currentData() or 'groups'
        cat = vc.as_dict()
        rows = [self._cat_row(r) for r in range(self.cat_table.rowCount())]
        if kind == 'groups':
            keys = ('id', 'name', 'draw_mode', 'unit_default', 'legend_id',
                    'color', 'order', 'note')
            cat['groups'] = [dict(zip(keys, row)) for row in rows
                             if row and row[0] and row[1]]
            for g in cat['groups']:
                try:
                    g['order'] = int(g['order'] or 99)
                except (ValueError, TypeError):
                    g['order'] = 99
        elif kind == 'variables':
            cat['variables'] = []
            for row in rows:
                if not row or not row[0]:
                    continue
                cat['variables'].append({
                    'key': row[0].upper(), 'name': row[1] or row[0],
                    'group_id': row[2] or 'UNCLASSIFIED', 'unit': row[3],
                    'scale': row[4] or 'linear', 'legend_id': row[5],
                    'aliases': [a.strip() for a in row[6].replace('，', ',').split(',')
                                if a.strip()],
                    'note': row[7] if len(row) > 7 else ''})
        elif kind == 'legend_codes':
            old = {lg['id']: lg for lg in cat.get('legends', [])}
            buckets = {}
            for row in rows:
                if len(row) < 4 or not row[0] or not row[1]:
                    continue
                d = buckets.setdefault(row[0], {
                    'id': row[0], 'name': old.get(row[0], {}).get('name', row[0]),
                    'note': old.get(row[0], {}).get('note', ''), 'codes': []})
                d['codes'].append([row[1], row[2] or row[1], row[3] or '#b0bec5'])
            cat['legends'] = list(buckets.values())
            for lid, lg in old.items():        # 空图例也保留，避免误删整个图例
                if lid not in buckets:
                    cat['legends'].append(dict(lg, codes=[]))
        else:
            keys = ('prefix', 'name', 'group_id', 'unit', 'scale', 'legend_id')
            cat['prefix_rules'] = [dict(zip(keys, row)) for row in rows
                                  if row and row[0]]
            for r in cat['prefix_rules']:
                r['prefix'] = r['prefix'].upper()
            cat['prefix_rules'].sort(key=lambda r: -len(r['prefix']))
        if vc.import_dict(cat):
            self._log('变量库已保存：%s（%d 行）→ %s' % (
                self.cat_kind.currentText(), len(rows), vc.CATALOG_PATH))
            self.refresh()
            self._cat_reload()
        else:
            self._log('变量库保存失败：数据结构无效')

    def _cat_reset(self):
        vc.reset_defaults()
        self._log('变量库已恢复出厂默认（15 族 / 77 变量 / 3 图例）')
        self.refresh()
        self._cat_reload()

    def _show_func_catalog(self):
        """【R87】变量字典库：族 → 分支变量 → 图例 的唯一编辑入口。"""
        self.func_title.setText('变量字典库')
        self.func_stack.setCurrentIndex(1)
        self._func_key = 'catalog'
        self._func_input_kind = ''
        self._fill_func_input('')
        while self.func_actions.count():
            item = self.func_actions.takeAt(0)
            wd = item.widget()
            if wd is not None:
                wd.deleteLater()
        for label, slot in (('保存到变量库', self._cat_save),
                            ('新增行', self._cat_add_row),
                            ('删除选中行', self._cat_del_row),
                            ('恢复默认', self._cat_reset),
                            ('刷新表', self._cat_reload)):
            b = self._mk_button(None, label, slot)
            b.setMaximumWidth(120)
            self.func_actions.addWidget(b)
        self.func_actions.addStretch(1)
        self._cat_reload()
        self.right_nb.setCurrentIndex(1)

    # ---------------- 【R87】条件选择：改为功能页，界面内完成，不弹窗 ----------------

    def _build_conditional_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(2, 2, 2, 2)
        vl.addWidget(self._mk_label(
            '条件选择变量（Techlog Conditional selection）｜留空 = 不过滤', bold=True))
        form = QHBoxLayout()
        specs = []
        for attr, width in (('cond_group', 140), ('cond_family', 140),
                            ('cond_unit', 110), ('cond_kind', 100)):
            cb = QComboBox()
            cb.setEditable(True)
            cb.setFixedWidth(width)
            setattr(self, attr, cb)
            specs.append(cb)
        for label, cb in zip(('族', '分支', '单位', '类型'), specs):
            form.addWidget(self._mk_label(label, small=True, muted=True))
            form.addWidget(cb)
        form.addStretch(1)
        vl.addLayout(form)
        self.cond_result = _qc.TextCompat(page)
        self.cond_result.setReadOnly(True)
        self.cond_result.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        vl.addWidget(self.cond_result, 1)
        return page

    # ---------------- 【R88】候选源根管理：功能页化，不再弹对话框 ----------------

    def _build_roots_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(2, 2, 2, 2)
        vl.addWidget(self._mk_label(
            '候选原始资料根目录（用于按井名自动探测源目录）', bold=True))
        self.roots_list = QListWidget(page)
        self.roots_list.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        vl.addWidget(self.roots_list, 2)
        vl.addWidget(self._mk_label('已绑定的井（井名 → 源目录）', bold=True))
        self.roots_bind_list = QListWidget(page)
        self.roots_bind_list.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        vl.addWidget(self.roots_bind_list, 1)
        vl.addWidget(self._mk_label(
            '添加：在下方输入行填/选目录路径 → 「添加为源根」；移除：列表选中 → 「移除选中源根」',
            small=True, muted=True))
        return page

    def _roots_reload(self):
        self.roots_list.clear()
        for r in pcfg.source_roots(self.root_dir):
            self.roots_list.addItem(r + ('' if os.path.isdir(r) else '　（不存在）'))
        self.roots_bind_list.clear()
        cfg = pcfg.load_config(self.root_dir)
        for k, v in sorted((cfg.get('wells') or {}).items()):
            self.roots_bind_list.addItem('%-24s → %s' % (k, v.get('source_dir', '')))

    def _roots_add_input(self):
        d = self.func_input_combo.currentText().strip()
        if not d or not os.path.isdir(d):
            self._log('请输入存在的目录绝对路径再添加')
            return
        if pcfg.add_source_root(self.root_dir, d):
            self._log('已添加候选源根：%s' % d)
        else:
            self._log('添加候选源根失败：项目配置不可写')
        self._show_func_roots()

    def _roots_remove(self):
        it = self.roots_list.currentItem()
        if it is None:
            self._log('请先在列表里选中一个源根')
            return
        r = it.text().replace('　（不存在）', '').strip()
        if pcfg.remove_source_root(self.root_dir, r):
            self._log('已移除候选源根：%s' % r)
        else:
            self._log('移除候选源根失败')
        self._show_func_roots()

    def _show_func_roots(self):
        self.func_title.setText('候选源根管理')
        self.func_stack.setCurrentIndex(3)
        self._func_key = 'roots'
        self._func_input_kind = 'roots'
        self._fill_func_input('roots')
        self._rebuild_func_actions([
            ('添加为源根', self._roots_add_input),
            ('移除选中源根', self._roots_remove),
            ('刷新', self._show_func_roots),
        ])
        self._roots_reload()
        self.right_nb.setCurrentIndex(1)

    # ---------------- 【R88】添加井 / 批量添加井：功能页化，不再弹对话框 ----------------

    def _build_batch_add_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(2, 2, 2, 2)
        self.batch_path_lab = self._mk_label(
            '（未扫描 —— 在下方输入行填资料根路径，点「扫描候选井」）', small=True, muted=True)
        vl.addWidget(self.batch_path_lab)
        vl.addWidget(self._mk_label(
            '候选井（勾选要加入项目的；井名 = LAS 记录井名，单井时可在下方改名）',
            small=True, muted=True))
        self.batch_list = QListWidget(page)
        self.batch_list.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        vl.addWidget(self.batch_list, 1)
        row = QHBoxLayout()
        row.addWidget(self._mk_label('井名（单井）', small=True, muted=True))
        self.batch_name_edit = QLineEdit()
        self.batch_name_edit.setVisible(False)
        row.addWidget(self.batch_name_edit, 1)
        vl.addLayout(row)
        self._batch_cands: list[dict] = []
        self._batch_cands_path = ''
        return page

    def _batch_scan(self):
        path = self.func_input_combo.currentText().strip()
        if not path or not os.path.isdir(path):
            self._log('请先在输入行填写存在的资料根目录路径')
            return
        cands = pcfg.discover_wells_in_dir(path)
        if not cands:
            self._log('在 %s 里没有发现 LAS 文件（含 LAS 的子目录 / 目录本身才算一口井）' % path)
            return
        used = set()
        for c in cands:
            las_wn = pm.las_well_name(c.get('las_path', '')) or ''
            name = las_wn or c['name']
            if name in used:
                name = c['name']
            used.add(name)
            c['well_name'] = name
            c['las_well_name'] = las_wn
        self._batch_cands = cands
        self._batch_cands_path = path
        self.batch_list.clear()
        for i, c in enumerate(cands):
            tail = '' if c['well_name'] == c['name'] \
                else '   (LAS 井名 %s)' % c['las_well_name']
            it = QListWidgetItem('%-22s %3d 个文件%s' % (c['well_name'], c['files'], tail))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, i)
            self.batch_list.addItem(it)
        self.batch_path_lab.setText('资料根：%s ｜ 发现 %d 口井' % (path, len(cands)))
        self.batch_name_edit.setText(cands[0]['well_name'] if len(cands) == 1 else '')
        self.batch_name_edit.setVisible(len(cands) == 1)
        self._log('发现 %d 口井（资料根 %s）——勾选后点「添加勾选井到项目」' % (len(cands), path))

    def _batch_apply(self):
        if not self._batch_cands:
            self._log('请先点「扫描候选井」')
            return
        picks: list[tuple[str, str]] = []
        if len(self._batch_cands) == 1:
            n = self.batch_name_edit.text().strip() or self._batch_cands[0]['well_name']
            picks.append((n, self._batch_cands[0]['dir']))
        else:
            for i in range(self.batch_list.count()):
                it = self.batch_list.item(i)
                if it.checkState() == Qt.Checked:
                    c = self._batch_cands[int(it.data(Qt.UserRole))]
                    picks.append((c['well_name'], c['dir']))
        if not picks:
            self._log('请至少勾选一口井')
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
        self._batch_cands = []
        self._batch_cands_path = ''
        self.batch_list.clear()
        self.batch_name_edit.setVisible(False)
        self.batch_path_lab.setText('（已添加 %d 口井 —— 可继续扫描下一个资料根）' % len(added))
        self.refresh()
        if added:
            self._select_well(added[0])

    def _show_func_batch_add(self):
        self.func_title.setText('添加井到项目（支持批量）')
        self.func_stack.setCurrentIndex(4)
        self._func_key = 'batch_add'
        self._func_input_kind = 'batch_add'
        self._fill_func_input('batch_add')
        self._rebuild_func_actions([
            ('扫描候选井', self._batch_scan),
            ('添加勾选井到项目', self._batch_apply),
            ('清空列表', self._batch_clear),
        ])
        self.right_nb.setCurrentIndex(1)

    def _batch_clear(self):
        self._batch_cands = []
        self._batch_cands_path = ''
        self.batch_list.clear()
        self.batch_name_edit.setVisible(False)
        self.batch_path_lab.setText('（未扫描 —— 在下方输入行填资料根路径，点「扫描候选井」）')

    # ---------------- 【R89】项目管理：新建 / 打开 / 保存 / 最近项目 ----------------
    # 支持多项目：项目根 = 一个独立目录（含 project.json），可随时新建、切换。

    _RECENT_MAX = 10

    @staticmethod
    def _recent_file() -> str:
        """最近项目清单（全局，跨项目共享）：~/.logint_projects.json。"""
        return os.path.join(os.path.expanduser('~'), '.logint_projects.json')

    def _recent_load(self) -> list[str]:
        try:
            with open(self._recent_file(), 'r', encoding='utf-8') as f:
                items = json.load(f)
            out = []
            for p in items if isinstance(items, list) else []:
                p = str(p).strip()
                if p and os.path.isdir(p) and p not in out:
                    out.append(p)
            return out
        except Exception:
            return []

    def _recent_record(self, root: str):
        """登记最近项目（去重置顶，最多 10 条），并刷新菜单与输入行候选。"""
        try:
            items = [root] + [p for p in self._recent_load() if p != root]
            with open(self._recent_file(), 'w', encoding='utf-8') as f:
                json.dump(items[:self._RECENT_MAX], f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log('最近项目清单写入失败：%s' % e)
        self._fill_recent_menu()

    def _fill_recent_menu(self):
        """把最近项目填进「文件 → 最近项目」子菜单。"""
        menu = getattr(self, '_recent_menu', None)
        if menu is None:
            return
        menu.clear()
        items = self._recent_load()
        if not items:
            act = menu.addAction('（暂无 —— 打开项目后自动记录）')
            act.setEnabled(False)
            return
        for p in items:
            act = menu.addAction('%s  (%s)' % (os.path.basename(p) or p, p))
            act.triggered.connect(lambda _c=False, d=p: self._apply_root(d))

    def _build_project_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(2, 2, 2, 2)
        self.proj_cur_lab = self._mk_label('', bold=True)
        vl.addWidget(self.proj_cur_lab)
        vl.addWidget(self._mk_label('最近项目（双击切换；也可在下方输入行粘贴路径）',
                                    small=True, muted=True))
        self.project_list = QListWidget(page)
        self.project_list.setStyleSheet('font-family: Consolas; font-size: 9pt;')
        self.project_list.itemDoubleClicked.connect(
            lambda it: self._apply_root(it.data(Qt.UserRole)))
        vl.addWidget(self.project_list, 1)
        vl.addWidget(self._mk_label(
            '新建：输入行填一个新目录路径 → 「创建新项目」（自动初始化 project.json）\n'
            '打开：输入行填已有项目根路径 → 「打开项目」；「保存项目」写回 project.json',
            small=True, muted=True))
        return page

    def _project_reload_list(self):
        self.proj_cur_lab.setText('当前项目：%s' % self.root_dir)
        self.project_list.clear()
        for p in self._recent_load():
            if os.path.abspath(p) == os.path.abspath(self.root_dir):
                continue
            it = QListWidgetItem('%s  —  %s' % (os.path.basename(p) or p, p))
            it.setData(Qt.UserRole, p)
            self.project_list.addItem(it)

    def _project_create(self, path: str):
        """新建项目：建目录 + 初始化 project.json，然后切换过去。"""
        d = str(path or '').strip().strip('"').strip("'")
        if not d:
            self._log('请先在输入行填写新项目的目录绝对路径')
            return
        d = os.path.abspath(d)
        if os.path.isfile(d):
            self._log('路径已是文件，不能作为项目根：%s' % d)
            return
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            self._log('创建项目目录失败：%s' % e)
            return
        # project.json 由 save_config 统一创建
        cfg = pcfg.load_config(d)
        pcfg.save_config(d, cfg)
        self._log('新项目已创建：%s' % d)
        self._apply_root(d)

    def _project_save(self):
        """保存项目：把当前内存配置写回 project.json（平时改动即自动保存）。"""
        cfg = pcfg.load_config(self.root_dir)
        if cfg is None:
            self._log('保存失败：当前项目配置不可读')
            return
        if pcfg.save_config(self.root_dir, cfg):
            self._log('项目已保存：%s' % pcfg.config_path(self.root_dir))
        else:
            self._log('保存失败：无法写 %s' % pcfg.config_path(self.root_dir))

    def _show_func_project(self, mode: str = 'open'):
        self._project_mode = mode
        self.func_title.setText('项目管理')
        self.func_stack.setCurrentIndex(5)
        self._func_key = 'project'
        self._func_input_kind = 'project'
        self._fill_func_input('project')
        self._rebuild_func_actions([
            ('创建新项目', lambda: self._project_create(
                self.func_input_combo.currentText())),
            ('打开项目', lambda: self._apply_root(
                self.func_input_combo.currentText())),
            ('保存项目', self._project_save),
            ('刷新列表', self._show_func_project),
        ])
        self._project_reload_list()
        self.right_nb.setCurrentIndex(1)

    def _menu_new_project(self):
        self._show_func_project('new')

    def _menu_open_project(self):
        self._show_func_project('open')

    def _menu_save_project(self):
        self._project_save()

    def _build_menubar(self):
        """【R89】菜单栏：文件 → 新建/打开/保存项目/最近项目/打开项目根/退出。"""
        mb = self.win.menuBar()
        mfile = mb.addMenu('文件(&F)')
        act_new = QAction('新建项目…', self.win)
        act_new.triggered.connect(self._menu_new_project)
        mfile.addAction(act_new)
        act_open = QAction('打开项目…', self.win)
        act_open.triggered.connect(self._menu_open_project)
        mfile.addAction(act_open)
        act_save = QAction('保存项目', self.win)
        act_save.triggered.connect(self._menu_save_project)
        mfile.addAction(act_save)
        self._recent_menu = mfile.addMenu('最近项目')
        self._fill_recent_menu()
        mfile.addSeparator()
        act_dir = QAction('打开项目根目录', self.win)
        act_dir.triggered.connect(self._menu_open_root_dir)
        mfile.addAction(act_dir)
        mfile.addSeparator()
        act_quit = QAction('退出', self.win)
        act_quit.triggered.connect(self._close)
        mfile.addAction(act_quit)

    def _menu_open_root_dir(self):
        try:
            os.startfile(self.root_dir)  # noqa: S606
            self._log('已打开项目根：%s' % self.root_dir)
        except Exception as e:
            self._log('打开项目根失败：%s' % e)

    def _update_title(self):
        self.win.setWindowTitle('智能测井解释系统 —— 项目工作台　[%s]'
                               % (os.path.basename(self.root_dir) or self.root_dir))


    def _cond_refresh_options(self, w):
        all_ds = list(w.datasets) + list(w.source_datasets)
        fams = sorted({v.family for d in all_ds for v in d.variables if v.family})
        units = sorted({v.unit for d in all_ds for v in d.variables if v.unit})
        kinds = sorted({v.kind for d in all_ds for v in d.variables})
        for cb, vals in ((self.cond_group, vc.all_group_names()),
                         (self.cond_family, fams), (self.cond_unit, units),
                         (self.cond_kind, kinds)):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem('')
            cb.addItems([str(x) for x in vals])
            if cur:
                cb.setEditText(cur)
            cb.blockSignals(False)

    def _cond_run(self):
        w = self._selected_well()
        if not w:
            self._log('请先选中一口井')
            return
        sel = pm.conditional_select(
            pm.Project(self.project.name, self.project.path, [w]),
            group=self.cond_group.currentText().strip(),
            family=self.cond_family.currentText().strip(),
            unit=self.cond_unit.currentText().strip(),
            kind=self.cond_kind.currentText().strip())
        lines = []
        for well, dss in sel.items():
            for dn, vs in dss.items():
                lines.append('%s / %s\n' % (well, dn))
                for v in vs:
                    lines.append('    %s\n' % v)
                lines.append('\n')
        self.cond_result.clear()
        self.cond_result.insert('1.0', ''.join(lines) or '（无匹配变量）')

    def _show_func_conditional(self):
        w = self._selected_well()
        self.func_title.setText('条件选择变量')
        self.func_stack.setCurrentIndex(2)
        self._func_key = 'conditional'
        self._func_input_kind = ''
        self._fill_func_input('')
        while self.func_actions.count():
            item = self.func_actions.takeAt(0)
            wd = item.widget()
            if wd is not None:
                wd.deleteLater()
        for label, slot in (('执行选择', self._cond_run),
                            ('清空结果', lambda: self.cond_result.clear())):
            b = self._mk_button(None, label, slot)
            b.setMaximumWidth(120)
            self.func_actions.addWidget(b)
        self.func_actions.addStretch(1)
        self._cond_refresh_options(w or pm.Well(''))
        self.right_nb.setCurrentIndex(1)

    def _set_func(self, title: str, text: str, actions: list[tuple[str, object]],
                  key: str = '', input_kind: str = ''):
        """切换右侧「功能」页内容并重建动作按钮/输入行。"""
        self.func_title.setText(title)
        self.func_stack.setCurrentIndex(0)
        self.func_text.configure(state='normal')
        self.func_text.delete('1.0', 'end')
        self.func_text.insert('1.0', text or '')
        self.func_text.configure(state='disabled')
        while self.func_actions.count():
            item = self.func_actions.takeAt(0)
            wd = item.widget()
            if wd is not None:
                wd.deleteLater()
        for label, slot in actions:
            b = self._mk_button(None, label, slot)
            b.setMaximumWidth(150)
            self.func_actions.addWidget(b)
        self.func_actions.addStretch(1)
        self._func_key = key
        self._func_input_kind = input_kind
        self._fill_func_input(input_kind)
        self.right_nb.setCurrentIndex(1)

    def _rebuild_func_actions(self, actions: list[tuple[str, object]]):
        """清空并重建功能页动作按钮（供各功能页复用）。"""
        while self.func_actions.count():
            item = self.func_actions.takeAt(0)
            wd = item.widget()
            if wd is not None:
                wd.deleteLater()
        for label, slot in actions:
            b = self._mk_button(None, label, slot)
            b.setMaximumWidth(150)
            self.func_actions.addWidget(b)
        self.func_actions.addStretch(1)

    def _fill_func_input(self, kind: str):
        """输入行选项来自「数据加载」的扫描结果，避免任何弹窗。

        【R88】roots / batch_add 两类不依赖选中井：候选 = 候选源根本身。
        """
        row = getattr(self, 'func_input_row', None)
        if row is None:
            return
        for i in range(row.count()):
            item = row.itemAt(i)
            wd = item.widget()
            if wd is not None:
                wd.setVisible(bool(kind))
        if not kind:
            return
        self.func_input_type.setVisible(kind == 'import')
        w = self._selected_well()
        cb = self.func_input_combo
        cb.blockSignals(True)
        cb.clear()
        choices: list[str] = []
        current = ''
        lab, apply_text = '输入路径（下拉来自数据加载扫描，也可直接粘贴）', '应用输入'
        if kind == 'roots':
            choices = list(pcfg.source_roots(self.root_dir))
            if self.root_dir not in choices:
                choices.insert(0, self.root_dir)
            lab, apply_text = '源根目录路径（下拉 = 已登记源根，也可直接粘贴）', '添加为源根'
        elif kind == 'project':
            recent = self._recent_load()
            choices = [p for p in recent
                       if os.path.abspath(p) != os.path.abspath(self.root_dir)]
            if self.root_dir not in choices:
                choices.insert(0, self.root_dir)
            lab, apply_text = '项目根目录路径（下拉 = 最近项目，也可直接粘贴）', \
                '创建新项目' if getattr(self, '_project_mode', '') == 'new' else '打开项目'
        elif kind == 'batch_add':
            choices = [r for r in pcfg.source_roots(self.root_dir) if os.path.isdir(r)]
            if self.root_dir not in choices:
                choices.insert(0, self.root_dir)
            lab, apply_text = '资料根路径（含 LAS 的子目录 = 一口井，也可直接粘贴）', '扫描候选井'
        elif w:
            out = self._well_out_dir(w)
            found = dop.discover_inputs(w.source_dir or '', out)
            opt_key = kind
            if kind == 'import':
                opt_key = self.func_input_type.currentData() or 'las'
                if opt_key == 'source_dir':
                    choices = []
                    for sr in pcfg.source_roots(self.root_dir):
                        if os.path.isdir(sr):
                            choices += [os.path.join(sr, d) for d in sorted(os.listdir(sr))
                                        if os.path.isdir(os.path.join(sr, d))]
                    current = w.source_dir or ''
                else:
                    # 导入面板的候选 = 井自有扫描 + 候选源根里的同类资料（【R88】）
                    choices = list(found.get(opt_key, []))
                    if not choices:
                        choices = self._scan_roots_for_kind(opt_key)
                    current = pcfg.well_options(self.root_dir, w.name).get(opt_key, '')
            else:
                choices = list(found.get(kind, []))
                if kind == 'las':
                    auto = pjob.find_main_las(w.source_dir or '')
                    if auto and auto not in choices:
                        choices.insert(0, auto)
                current = pcfg.well_options(self.root_dir, w.name).get(opt_key, '')
        for p in choices:
            cb.addItem(p)
        if current and current not in choices:
            cb.insertItem(0, current)
        cb.setEditText(current)
        self.func_input_lab.setText(lab)
        self.func_input_apply.setText(apply_text)
        cb.blockSignals(False)

    def _scan_roots_for_kind(self, kind: str, limit: int = 200) -> list[str]:
        """【R88】在候选源根里扫描同类资料文件（有界深度/数量，只读）。

        导入面板的候选不再局限于井自有目录 —— 未关联源目录的井也能
        直接从候选源根里挑外部文件导入。
        """
        exts = {'las': ('.las', '.las2'),
                'gas': ('.csv', '.txt', '.dat', '.xls', '.xlsx', '.las'),
                'nmr': ('.csv', '.xlsx', '.xls', '.dlis'),
                'fmi': ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.csv', '.las'),
                'config': ('.json',)}.get(kind)
        out: list[str] = []
        if not exts:
            return out
        for sr in pcfg.source_roots(self.root_dir):
            if not os.path.isdir(sr):
                continue
            for base, dirs, files in os.walk(sr):
                if base[len(sr):].count(os.sep) >= 4:
                    dirs[:] = []
                dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('_')]
                for fn in files:
                    if fn.lower().endswith(exts):
                        out.append(os.path.join(base, fn))
                        if len(out) >= limit:
                            return out
        return out

    def _apply_func_input(self):
        """输入行的统一入口：按当前功能页路由（全程无对话框）。

        【R88】导入面板的文件类型 = **导入并指定**：先把外部文件复制到
        井的原始资料目录（没有则自动建立并登记），再把井级指定指向
        复制后的文件 —— 此前只写配置不复制，外部文件根本进不了项目。
        """
        kind = getattr(self, '_func_input_kind', '')
        val = self.func_input_combo.currentText().strip()
        if not kind:
            return
        if kind == 'roots':
            self._roots_add_input()
            return
        if kind == 'batch_add':
            self._batch_scan()
            return
        if kind == 'project':
            if getattr(self, '_project_mode', '') == 'new':
                self._project_create(val)
            else:
                self._apply_root(val)
            return
        w = self._selected_well()
        if not w:
            self._log('请先选中一口井')
            return
        opt_key = kind
        if kind == 'import':
            opt_key = self.func_input_type.currentData() or 'las'
        if opt_key == 'source_dir':
            if not val or not os.path.isdir(val):
                self._log('请输入存在的原始资料目录绝对路径')
                return
            if pcfg.bind_well(self.root_dir, w.name, val):
                self._log('已关联源目录：%s → %s' % (w.name, val))
                self.refresh()
            else:
                self._log('关联源目录失败：项目配置不可写')
            self._show_func_import()
            return
        if kind == 'import':
            if not val or not os.path.isfile(val):
                self._log('请输入存在的文件绝对路径再导入')
                return
            dest = w.source_dir or os.path.join(self.root_dir, 'sources', w.name)
            if not w.source_dir:
                if not pcfg.bind_well(self.root_dir, w.name, dest):
                    self._log('导入失败：无法为井 %s 建立源目录登记' % w.name)
                    return
                self._log('已为井 %s 自动建立源目录：%s' % (w.name, dest))
            r = dop.import_files([val], dest)
            if r.get('copied'):
                copied = r['copied'][0]
                pcfg.set_well_option(self.root_dir, w.name, opt_key, copied)
                self._log('已导入并指定 %s：%s → %s'
                          % (pcfg.WELL_OPTION_LABELS.get(opt_key, opt_key),
                             os.path.basename(val), dest))
                self.refresh()
            for s in r.get('skipped') or []:
                self._log('跳过：%s' % s)
            if not r.get('ok') and r.get('error'):
                self._log('导入失败：%s' % r['error'])
            self._show_func_import()
            return
        if pcfg.set_well_option(self.root_dir, w.name, opt_key, val):
            self._log('已指定 %s：%s' % (pcfg.WELL_OPTION_LABELS.get(opt_key, opt_key),
                                       val or '（清除，回到自动探测）'))
            self.refresh()
            key = getattr(self, '_func_key', '')
            if key in pjob.JOB_TYPES:
                self._show_func_job(key)
        else:
            self._log('输入应用失败：项目配置不可写')

    def _copy_func_input(self):
        """把输入行里的外部文件复制到当前井的原始资料目录（无文件对话框）。

        【R88】井未关联源目录时自动建立 ``<项目根>/sources/<井名>`` 并登记；
        路径先校验，导入后按导入面板当前所选类型写入井级指定。
        """
        w = self._selected_well()
        val = self.func_input_combo.currentText().strip()
        if not w or not val:
            self._log('请先选中井并在输入行填写文件路径')
            return
        if not os.path.isfile(val):
            self._log('输入的路径不是存在的文件：%s' % val)
            return
        dest = w.source_dir or os.path.join(self.root_dir, 'sources', w.name)
        if not w.source_dir:
            if not pcfg.bind_well(self.root_dir, w.name, dest):
                self._log('导入失败：无法为井 %s 建立源目录登记' % w.name)
                return
            self._log('已为井 %s 自动建立源目录：%s' % (w.name, dest))
        r = dop.import_files([val], dest)
        if r.get('copied'):
            self._log('已导入 %d 个文件：%s → %s'
                      % (len(r['copied']),
                         '、'.join(os.path.basename(p) for p in r['copied']), dest))
            kind = getattr(self, '_func_input_kind', '')
            opt_key = self.func_input_type.currentData() if kind == 'import' else None
            if opt_key and opt_key in pcfg.WELL_OPTIONS:
                pcfg.set_well_option(self.root_dir, w.name, opt_key, r['copied'][0])
            self.refresh()
        for s in r.get('skipped') or []:
            self._log('跳过：%s' % s)
        if not r.get('ok') and r.get('error'):
            self._log('导入失败：%s' % r['error'])
        self._show_func_import()

    def _func_head(self, w) -> str:
        if not w:
            return '未选中井 —— 请先在左侧项目树选择一口井。\n'
        return ('井：%s\n源目录：%s\n产物目录：%s\n\n'
                % (w.name, w.source_dir or '（未关联）', self._well_out_dir(w)))

    def _func_text(self, key: str) -> str:
        w = self._selected_well()
        head = self._func_head(w)
        if not w:
            return head
        out = self._well_out_dir(w)
        if key == 'load':
            return head + dop.load_summary(w.name, w.source_dir, out)
        if key == 'clean':
            csv = self._processed_csv(w)
            lines = [head + '数据清洗：单位归一、缺测/非法值清理、深度去重排序。',
                     '输入曲线集：%s' % (csv or '（未找到 <井名>_processed.csv）')]
            for name in ('%s_cleaned.csv' % w.name, '%s_data_clean_report.json' % w.name):
                p = os.path.join(out, name)
                lines.append('%s：%s' % (name, '已存在' if os.path.isfile(p) else '尚未生成'))
            return '\n'.join(lines)
        if key == 'qc':
            csv = self._processed_csv(w)
            p = os.path.join(out, '%s_qc_report.json' % w.name)
            lines = [head + '数据质检：深度列、采样间隔、关键曲线、值域、缺测统计。',
                     '输入曲线集：%s' % (csv or '（未找到 <井名>_processed.csv）'),
                     '质检报告：%s' % (p if os.path.isfile(p) else '尚未生成')]
            if os.path.isfile(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        r = json.load(f)
                    lines.append('等级：%s ｜ 错误 %s ｜ 警告 %s ｜ 记录 %s 行'
                                 % (r.get('level'), r.get('errors'), r.get('warnings'), r.get('rows')))
                    for c in (r.get('checks') or [])[:8]:
                        lines.append('  [%s] %s：%s' % (c.get('level'), c.get('item'), c.get('detail')))
                except Exception:
                    pass
            return '\n'.join(lines)
        if key == 'import':
            opts = pcfg.well_options(self.root_dir, w.name)
            lines = [head + '数据导入：把外部数据复制到井的原始资料目录（源文件不动）。']
            for k in pcfg.WELL_OPTIONS:
                lines.append('  %-10s：%s' % (pcfg.WELL_OPTION_LABELS.get(k, k),
                                             opts.get(k) or '（未指定，自动探测）'))
            return '\n'.join(lines)
        if key == 'export':
            csv = self._processed_csv(w)
            cols = dop.columns_of(csv)
            lines = [head + '数据导出：把解释曲线集导出为 CSV / XLSX / LAS（不覆盖源文件）。',
                     '源曲线集：%s' % (csv or '（未找到）'),
                     '列数：%d ｜ 前 24 列：%s' % (len(cols), ', '.join(cols[:24]))]
            return '\n'.join(lines)
        if key in ('quicklook', 'comprehensive', 'gas', 'nmr', 'fmi'):
            opts = pcfg.well_options(self.root_dir, w.name)
            desc = {
                'quicklook': '快速解释图（QuickLook）：一键出草图与主要解释曲线。',
                'comprehensive': '综合解释：完整测井解释流程（岩性/流体/层段/图件）。',
                'gas': '气测解释：图版法 ITP + 同井相对异常 → 对齐主深度的曲线变量。',
                'nmr': '核磁处理：T2 谱、T1、扩散系数、孔隙度与渗透率。',
                'fmi': '电成像处理：微电阻率图像的孔隙、溶孔与裂缝识别。',
            }[key]
            input_key = {'gas': 'gas', 'nmr': 'nmr', 'fmi': 'fmi'}.get(key)
            lines = [head + desc,
                     '执行方式：独立子进程，产物自动归入 output/%s/' % w.name]
            if input_key:
                lines.append('指定输入：%s' % (opts.get(input_key) or '（未指定 → 自动探测源目录）'))
            else:
                lines.append('主 LAS：%s' % (opts.get('las') or '（自动探测源目录）'))
            patterns = {'gas': ('*gas_curves.csv', '*gas_result.json'),
                        'nmr': ('*_nmr_results_*.csv', '*_nmr_result.json', '*.png'),
                        'fmi': ('*_fmi_results.csv', '*_fmi_result.json', '*.png')}.get(key, ())
            import glob
            for pat in patterns:
                hits = sorted(glob.glob(os.path.join(out, pat)))
                lines.append('产物 %-22s：%d 个%s' % (
                    pat, len(hits), ('（最新：%s）' % os.path.basename(hits[-1])) if hits else ''))
            return '\n'.join(lines)
        if key == 'logview':
            return (head + '交互绘图（logvis）是**独立模块**：\n'
                    '  · 把任意一维曲线 / 二维波形 / 核磁谱 / 成像拖入作图；\n'
                    '  · 可修改道组合、比例、图头与界面；\n'
                    '  · 再次打开自动载入上次保存的布局继续修改。\n\n'
                    '不跑解释作业：有产物读产物，无产物读原始 LAS / 源数据。')
        return head

    def _show_func_load(self):
        w = self._selected_well()
        self._set_func('数据加载', self._func_text('load'), [
            ('重新扫描', self.refresh),
            ('气测解释', lambda: self._show_func_job('gas')),
            ('核磁处理', lambda: self._show_func_job('nmr')),
            ('电成像处理', lambda: self._show_func_job('fmi')),
            ('交互绘图', self._show_func_logview),
        ], key='load')

    def _show_func_clean(self):
        self._set_func('数据清洗', self._func_text('clean'), [
            ('执行清洗', self._func_clean_run),
            ('打开产物目录', self._menu_open_dir),
        ])

    def _show_func_qc(self):
        self._set_func('数据质检', self._func_text('qc'), [
            ('执行质检', self._func_qc_run),
            ('重新扫描', self.refresh),
        ])

    def _show_func_import(self):
        self._set_func('数据导入', self._func_text('import'), [
            ('复制文件到井目录', self._copy_func_input),
            ('刷新扫描', self._show_func_import),
        ], key='import', input_kind='import')

    def _show_func_export(self):
        self._set_func('数据导出', self._func_text('export'), [
            ('导出 CSV', lambda: self._func_export_run('csv')),
            ('导出 XLSX', lambda: self._func_export_run('xlsx')),
            ('导出 LAS', lambda: self._func_export_run('las')),
        ])

    def _show_func_job(self, job_type: str):
        label = pjob.JOB_TYPES.get(job_type, (job_type, ''))[0]
        actions = [('对选中井执行', lambda: self._run_job(job_type))]
        if job_type in ('quicklook', 'comprehensive'):
            actions.append(('批量执行（待解释井）', lambda: self._run_batch(job_type)))
        actions.append(('重新扫描输入', lambda: self._show_func_job(job_type)))
        input_kind = {'quicklook': 'las', 'comprehensive': 'las',
                      'gas': 'gas', 'nmr': 'nmr', 'fmi': 'fmi'}.get(job_type, '')
        self._set_func(label, self._func_text(job_type), actions,
                       key=job_type, input_kind=input_kind)

    def _show_func_logview(self):
        self._set_func('交互绘图（logvis）', self._func_text('logview'), [
            ('打开交互绘图', self._menu_logview),
        ])

    def _func_clean_run(self):
        w = self._selected_well()
        if not w or not self._processed_csv(w):
            self._log('数据清洗需要该井的解释曲线集（先跑快速解释或综合解释）')
            return
        r = dop.clean_csv(self._processed_csv(w), self._well_out_dir(w), w.name)
        if r.get('ok'):
            self._log('数据清洗完成：%s（%s → %s 行）'
                      % (r['data'], r.get('rows_in'), r.get('rows_out')))
            self.refresh()
        else:
            self._log('数据清洗失败：%s' % r.get('error'))
        self._show_func_clean()

    def _func_qc_run(self):
        w = self._selected_well()
        if not w or not self._processed_csv(w):
            self._log('数据质检需要该井的解释曲线集')
            return
        r = dop.qc_csv(self._processed_csv(w), self._well_out_dir(w), w.name)
        if r.get('ok'):
            d = r['detail']
            self._log('数据质检完成：%s（%s，错误 %s / 警告 %s）'
                      % (r['report'], d.get('level'), d.get('errors'), d.get('warnings')))
        else:
            self._log('数据质检失败：%s' % r.get('error'))
        self._show_func_qc()

    def _func_export_run(self, fmt: str):
        w = self._selected_well()
        if not w or not self._processed_csv(w):
            self._log('数据导出需要该井的解释曲线集')
            return
        r = dop.export_curves(self._processed_csv(w), self._well_out_dir(w), w.name, fmt)
        if r.get('ok'):
            self._log('已导出 %s：%s（%d 列 / %d 行）'
                      % (fmt.upper(), r['file'], len(r['columns']), r['rows']))
            self.refresh()
        else:
            self._log('导出失败：%s' % r.get('error'))
        self._show_func_export()

    # ---------------- 属性面板 ----------------

    def _on_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            self.right_nb.setCurrentIndex(0)
        except Exception:
            pass
        if iid in self._wells_by_iid:
            self._show_well(self._wells_by_iid[iid])
        elif iid in self._ds_by_iid:
            self._show_dataset(self._ds_by_iid[iid])
        else:
            self._show_object(iid)

    def _show_object(self, iid: str):
        vals = self.tree.item(iid, 'values')
        self.prop_title.setText(self.tree.item(iid, 'text'))
        self.prop_type.setText('%s　%s' % (vals[0] if vals else '', vals[1] if len(vals) > 1 else ''))
        self._set_tab('概览', '%s\n\n类型: %s\n%s' % (
            self.tree.item(iid, 'text'), vals[0] if vals else '',
            vals[1] if len(vals) > 1 else ''))
        self._set_tab('资料', '（项目视图 —— 选择一口井可查看其作业资料）')

    def _show_well(self, w: pm.Well):
        self.prop_title.setText(w.name)
        self.prop_type.setText('井 · %s' % w.status_label)
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
            lines.append('原始资料    : （未关联 —— 「数据导入」面板输入源目录）')
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
            if ds.note:
                rows.append('    说明   : %s' % ds.note)
            if ds.depth_min is not None:
                rows.append('    深度   : %.2f - %.2f m' % (ds.depth_min, ds.depth_max or 0))
            rows.append('')
        for ds in w.datasets:
            rows.append('%s  [%s]' % (ds.name, pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0]))
            rows.append('    路径   : %s' % ds.path)
            rows.append('    大小   : %s' % _human_size(ds.size))
            rows.append('    变量   : %d' % len(ds.variables))
            if ds.note:
                rows.append('    说明   : %s' % ds.note)
            if ds.depth_min is not None:
                rows.append('    深度   : %.2f - %.2f m' % (ds.depth_min, ds.depth_max or 0))
            rows.append('')
        self._set_tab('数据集', '\n'.join(rows) or '（无）')

        # 变量（【R87】按族 → 分支变量展示；解释产物归并到输入 LAS/DLIS 下）
        vrows = []
        for ds in w.source_datasets + w.datasets:
            if not ds.variables:
                continue
            tag = '［输入数据集］' if ds.dtype == 'source' else ''
            vrows.append('── %s %s ──' % (ds.name, tag))
            if ds.note:
                vrows.append('  %s' % ds.note)
            for gname, vs in pm.group_variables(ds.variables):
                mode = (vs[0].draw_mode if vs else '') or 'linear'
                legend = (vs[0].legend_id if vs else '') or ''
                head = '  ▣ %s（%d） %s' % (gname, len(vs), mode)
                if legend:
                    head += ' → 图例 %s' % legend
                vrows.append(head)
                for v in vs:
                    mark = {'ok': '●', 'warn': '●', 'error': '●', 'muted': '·'}.get(v.color, '·')
                    origin = '解释' if v.origin == 'interpretation' else '输入'
                    vrows.append('    %s %-18s %-16s %-10s %s' % (
                        mark, v.name, v.family or '（无分支）',
                        v.unit or '—', origin))
            vrows.append('')
        self._set_tab('变量', '\n'.join(vrows) or '（无变量）')

        # 资料（原启动界面"手动校正资料"的下沉视图）：
        # 显示作业**实际会用的**文件，以及它是手工指定还是自动探测来的
        ins = self._well_inputs(w)
        ilines = [
            '原始资料目录: %s' % (w.source_dir or
                                   '（未关联 —— 「数据导入」面板输入源目录）'),
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
        self.prop_title.setText(ds.name)
        self.prop_type.setText('数据集 · %s' % pm.DATASET_TYPES.get(ds.dtype, ('', ''))[0])
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
        for gname, vs in pm.group_variables(ds.variables):
            mode = (vs[0].draw_mode if vs else '') or 'linear'
            legend = (vs[0].legend_id if vs else '') or ''
            head = '▣ %s（%d） %s' % (gname, len(vs), mode)
            if legend:
                head += ' → 图例 %s' % legend
            vrows.append(head)
            for v in vs:
                mark = {'ok': '●', 'warn': '●', 'error': '●', 'muted': '·'}.get(v.color, '·')
                origin = '解释' if v.origin == 'interpretation' else '输入'
                vrows.append('  %s %-20s %-14s %-10s %-12s %s' % (
                    mark, v.name, v.family or '（无分支）', v.unit or '（无单位）',
                    v.scale or '', origin))
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

    # 【R85】旧的 _on_double_click 已删除（R83 迁移后从未绑定=死代码）；
    # 双击统一由 _on_tree_double 处理（井→交互绘图，数据集→属性）。
    # 其"打开数据集目录"能力由右键「打开产物目录」覆盖，无能力丢失。

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

    # R86：三个专用处理作业（气测 / 核磁 / 电成像）
    def _menu_gas(self):
        self._run_job('gas')

    def _menu_nmr(self):
        self._run_job('nmr')

    def _menu_fmi(self):
        self._run_job('fmi')

    def _menu_logview(self):
        """【R85】交互绘图直达入口——选中井点按钮/双击/右键，均走这里。

        交互绘图是**独立模块**（logvis），不是解释作业：不跑子进程。
        它既能把任意曲线拖入新作图，也能重开已保存的图继续改界面/图头。
        因此这里**不要求先有产物**——有产物读产物，无产物则读原始 LAS /
        源目录里的二维数据；连目录都没有才给出明确引导。
        """
        w = self._selected_well()
        if not w:
            self._log('请先选中一口井，再点交互绘图')
            return
        try:
            from logvis import open_logview, find_output_dir
        except Exception as e:
            self._log(f'交互绘图模块不可用：{e}')
            return
        opts = pcfg.well_options(self.root_dir, w.name)
        source_dir = w.source_dir or pcfg.resolve_source_dir(self.root_dir, w.name)
        out_dir = find_output_dir(self.root_dir, w.name)
        las_file = opts.get('las', '')
        if not out_dir and not las_file and not source_dir:
            self._log('该井既无产物也无原始资料：请先「数据导入」面板输入源目录')
            return
        try:
            win = open_logview(self.win, w.name, out_dir=out_dir, source_dir=source_dir,
                               las_file=las_file)
            self._open_logview_windows.append(win)
            src = '解释产物' if out_dir else ('原始 LAS' if las_file else '源资料(二维)')
            self._log(f'已打开交互绘图：{w.name}（数据源：{src}）')
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
        label = pjob.JOB_TYPES.get(job_type, (job_type, ''))[0]
        # 井级资料指定（手工指定优先于自动探测）
        opts = pcfg.well_options(self.root_dir, w.name)
        special = job_type in pjob.SPECIAL_JOBS
        if not w.has_source and not (special and opts.get(
                {'gas': 'gas', 'nmr': 'nmr', 'fmi': 'fmi'}.get(job_type, ''))):
            self._log('井 %s 未关联原始资料目录 —— 请「数据导入」面板输入源目录后再执行作业'
                      % w.name)
            return
        runner = pjob.JobRunner(on_log=self._on_job_log, on_done=self._on_job_done)
        self._job_runner = runner
        self._job_running = True
        ok = runner.start(job_type, w.source_dir, self.root_dir,
                          las_file=opts.get('las', ''),
                          gas_file=opts.get('gas', ''),
                          config_file=opts.get('config', ''),
                          well_name=w.name,
                          nmr_file=opts.get('nmr', ''),
                          fmi_file=opts.get('fmi', ''))
        if not ok:
            self._job_running = False
            return
        self._log('── %s：%s ──' % (label, w.name))

    # ---------------- 井级资料指定（统一在界面内输入行完成，无文件对话框） ----------------

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
                            well_name=w.name,
                            nmr_file=opts.get('nmr', ''),
                            fmi_file=opts.get('fmi', '')):
            self._job_running = False
            self._start_next_batch()

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
        """条件选择（Techlog Conditional selection）。

        【R87】改为右侧「功能」页内完成（按族 / 分支 / 单位 / 类型筛选），
        不再弹出对话框 —— 主界面是唯一界面。
        """
        self._show_func_conditional()

    # 项目成员管理（添加井/批量添加井）已功能页化：_show_func_batch_add（R88）

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

    def _apply_root(self, path: str):
        """【R87】界面内切换项目根（不弹目录对话框）；【R89】记录最近项目。"""
        d = str(path or '').strip().strip('"').strip("'")
        if not d or not os.path.isdir(d):
            self._log('项目根不存在：%s' % d)
            return
        self.root_dir = os.path.abspath(d)
        self.refresh()
        self._update_title()
        self._recent_record(self.root_dir)
        self._log('项目根已切换：%s' % self.root_dir)
        self._show_func_root()

    def _show_func_root(self):
        """【R89】项目根设置并入项目管理功能页（新建/打开/保存/最近项目）。"""
        self._show_func_project('open')

    def _pick_root(self):
        """【R87】「打开项目根」入口改为功能页输入，不再弹目录框。"""
        self._show_func_project('open')

    def _log(self, msg: str):
        """写输出区。与上一条相同则不重复写（避免连续刷新刷屏）。"""
        try:
            cur = self.out_txt.get().rstrip('\n')
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
