# -*- coding: utf-8 -*-
"""PyQt5 兼容层：为从 tkinter 迁移的界面提供最小 API 适配。

R83 迁移时，项目工作台（project_browser.py）大量业务逻辑直接操作
``ttk.Treeview`` 的字符串 iid、``StringVar``、``Text`` 等tk 概念。
为降低改写风险，本模块提供同名/同语义的薄封装，使这些业务逻辑几乎不动：

  - ``Var``          对应 tk.StringVar / BooleanVar（get/set/trace_add）
  - ``TreeViewCompat`` 对应 ttk.Treeview 的 iid 风格 API（QTreeWidget 实现）
  - ``TextCompat``   对应 tk.Text 的 get/insert/delete/see/configure
  - ``TkEvent``      供 bind 回调使用的简化事件对象
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCursor
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QTextEdit, QAbstractItemView,
)


# ---------------------------------------------------------------------------
# 变量
# ---------------------------------------------------------------------------
class Var:
    """轻量 StringVar/BooleanVar 替身：get/set/trace_add。

    可选 ``bind_label(qlabel)``：set 时同步刷新标签文本，
    使业务逻辑里的 ``self.xxx_var.set(...)`` 原样可用。
    """

    def __init__(self, value=''):
        self._value = value
        self._callbacks = []
        self._label = None

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        if self._label is not None:
            try:
                self._label.setText(str(value))
            except Exception:
                pass
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                pass

    def trace_add(self, mode, cb):
        self._callbacks.append(cb)

    def bind_label(self, qlabel):
        self._label = qlabel
        qlabel.setText(str(self._value))


# ---------------------------------------------------------------------------
# 事件
# ---------------------------------------------------------------------------
class TkEvent:
    """bind 回调用的简化事件对象（提供 x/y/x_root/y_root）。"""

    def __init__(self, x=0, y=0, x_root=0, y_root=0):
        self.x = x
        self.y = y
        self.x_root = x_root
        self.y_root = y_root


# ---------------------------------------------------------------------------
# Treeview → QTreeWidget（iid 字符串 API）
# ---------------------------------------------------------------------------
class TreeViewCompat(QTreeWidget):
    """以 ttk.Treeview 的 iid 语义包装 QTreeWidget。

    支持 project_browser.py 实际用到的 API：
      heading / column / configure / bind
      insert(parent_iid, index, text=, values=, tags=, open=) -> iid
      get_children(iid) / delete(*iids) / parent(iid)
      item(iid, 'values'|'text') / item(iid, open=...) / item(iid, image=None)
      selection() / selection_set(iid) / focus(iid) / see(iid)
      identify_row(y)
    """

    _IID_ROLE = Qt.UserRole + 100
    _TAG_ROLE = Qt.UserRole + 101

    def __init__(self, parent=None, columns=(), tag_colors=None,
                 selectmode='browse'):
        super().__init__(parent)
        self._tag_colors = dict(tag_colors or {})
        self._items: dict[str, QTreeWidgetItem] = {}
        self._seq = 0
        self._bindings: dict[str, object] = {}
        self._column_names = list(columns or ())
        self.setColumnCount(1 + len(self._column_names))
        self.setHeaderLabels([''] + self._column_names)
        self.setAlternatingRowColors(False)
        if selectmode == 'extended':
            self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        else:
            self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu)
        self.itemSelectionChanged.connect(self._emit_select)
        self.itemDoubleClicked.connect(self._emit_double)

    # -- 列头/样式（保留被调用即可，细节由样式表处理） ---------------------
    def heading(self, col, text=None, anchor=None):
        idx = self._col_index(col)
        if text is not None:
            self.setHeaderLabel(idx, str(text))

    def column(self, col, width=None, minwidth=None, stretch=None):
        idx = self._col_index(col)
        if width is not None:
            self.setColumnWidth(idx, int(width))

    def configure(self, **kwargs):
        # yscrollcommand/xscrollcommand/cursor 等：QTreeWidget 自带滚动条
        return None

    def _col_index(self, col) -> int:
        if col in ('#0', 0):
            return 0
        if isinstance(col, int):
            return col
        if isinstance(col, str):
            if col.isdigit():
                return int(col)
            if col in self._column_names:
                return self._column_names.index(col) + 1
        return 0

    # -- 事件绑定 ----------------------------------------------------------
    def bind(self, seq, cb):
        self._bindings[seq] = cb

    def _emit_context_menu(self, pos):
        cb = self._bindings.get('<Button-3>')
        if cb:
            gp = self.mapToGlobal(pos)
            cb(TkEvent(x=pos.x(), y=pos.y(), x_root=gp.x(), y_root=gp.y()))

    def _emit_select(self):
        cb = self._bindings.get('<<TreeviewSelect>>')
        if cb:
            cb(TkEvent())

    def _emit_double(self, item, column):
        cb = self._bindings.get('<Double-1>')
        if cb:
            cb(TkEvent())

    # -- 节点操作 ----------------------------------------------------------
    def _new_iid(self) -> str:
        self._seq += 1
        return 'I%06d' % self._seq

    def insert(self, parent_iid, index, text='', values=(), tags=(), open=False, **kw):
        iid = self._new_iid()
        cells = [str(text)] + [str(v) for v in (values or ())]
        while len(cells) < self.columnCount():
            cells.append('')
        item = QTreeWidgetItem(cells[:self.columnCount()])
        item.setData(0, self._IID_ROLE, iid)
        item.setData(0, self._TAG_ROLE, tuple(tags or ()))
        self._apply_tags(item, tags or ())
        self._items[iid] = item
        parent_item = self._items.get(parent_iid) if parent_iid else None
        if parent_item is not None:
            parent_item.addChild(item)
        else:
            self.addTopLevelItem(item)
        item.setExpanded(bool(open))
        return iid

    def _apply_tags(self, item, tags):
        for tag in tags:
            color = self._tag_colors.get(tag)
            if color:
                qc = QColor(color)
                for c in range(self.columnCount()):
                    item.setForeground(c, qc)
                break

    def delete(self, *iids):
        for iid in iids:
            item = self._items.pop(iid, None)
            if item is None:
                continue
            parent = item.parent()
            if parent is not None:
                parent.removeChild(item)
            else:
                idx = self.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.takeTopLevelItem(idx)

    def get_children(self, iid=''):
        item = self._items.get(iid) if iid else None
        if item is None:
            return [self._iid_of(self.topLevelItem(i))
                    for i in range(self.topLevelItemCount())]
        return [self._iid_of(item.child(i)) for i in range(item.childCount())]

    def _iid_of(self, item):
        return str(item.data(0, self._IID_ROLE)) if item is not None else ''

    def parent(self, iid):
        item = self._items.get(iid)
        if item is None or item.parent() is None:
            return ''
        return self._iid_of(item.parent())

    def item(self, iid, option=None, **kw):
        item = self._items.get(iid)
        if item is None:
            return None if option else ''
        if option == 'text':
            return item.text(0)
        if option == 'values':
            return tuple(item.text(c) for c in range(1, self.columnCount()))
        if 'open' in kw:
            item.setExpanded(bool(kw['open']))
        if 'image' in kw:
            pass
        return None

    def selection(self):
        return tuple(self._iid_of(i) for i in self.selectedItems())

    def selection_set(self, iid):
        item = self._items.get(iid)
        if item is None:
            return
        self.clearSelection()
        item.setSelected(True)
        self.setCurrentItem(item)

    def focus(self, iid):
        item = self._items.get(iid)
        if item is not None:
            self.setCurrentItem(item)

    def see(self, iid):
        item = self._items.get(iid)
        if item is not None:
            self.scrollToItem(item)

    def identify_row(self, y):
        item = self.itemAt(0, int(y))
        return self._iid_of(item)

    def grab_release(self):
        return None


# ---------------------------------------------------------------------------
# Text → QTextEdit（只读文本区）
# ---------------------------------------------------------------------------
class TextCompat(QTextEdit):
    """对应 tk.Text 的 get/insert/delete/see/configure 最小子集。"""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setReadOnly(True)

    def get(self, _start='1.0', _end='end'):
        return self.toPlainText()

    def insert(self, pos, text):
        cur = self.textCursor()
        if str(pos).startswith('1.0') or pos == 1.0:
            cur.movePosition(QTextCursor.Start)
            cur.insertText(str(text))
        else:
            cur.movePosition(QTextCursor.End)
            cur.insertText(str(text))
        self.setTextCursor(cur)

    def delete(self, _start, _end):
        self.clear()

    def see(self, _pos):
        cur = self.textCursor()
        cur.movePosition(QTextCursor.End)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def configure(self, **kwargs):
        if 'state' in kwargs:
            self.setReadOnly(kwargs['state'] != 'normal')
