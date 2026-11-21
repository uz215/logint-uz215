# -*- coding: utf-8 -*-
"""PyQt5 GUI 公共工具层。

集中管理：
  - 全进程唯一的 ``QApplication``（``get_app``）；
  - 文件/目录对话框（``open_file`` / ``open_files`` / ``save_file`` / ``select_dir``）；
  - 消息框与输入对话框（``info`` / ``warn`` / ``error`` / ``yes_no`` /
    ``yes_no_cancel`` / ``text_input``）。

迁移背景（R83）：本项目 GUI 由 tkinter 统一切换到 PyQt5。原先散落在
各模块里的 ``tk.Tk().withdraw() + filedialog`` / ``messagebox`` 调用改为本
模块的一层薄封装，避免每个文件各自创建 QApplication（一个进程只允许一个）。

所有对话框函数都接受可选 ``parent``（QWidget），保证模态归属于调用窗口。
无 parent 时也能工作（用于 CLI 场景）。
"""
from __future__ import annotations

_APP = None

# 常用字体（与 tkinter 版保持一致）
FONT_MAIN = 'Microsoft YaHei'
FONT_MONO = 'Consolas'


# ---------------------------------------------------------------------------
# QApplication 单例
# ---------------------------------------------------------------------------
def get_app():
    """返回全进程唯一的 QApplication（不存在则创建）。"""
    global _APP
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        _APP = app
    return app


def exec_app() -> int:
    """启动 Qt 事件循环（在哪创建就在哪 exec，配套 get_app）。"""
    return get_app().exec_()


# ---------------------------------------------------------------------------
# 文件类型过滤：tk [('图片','*.png *.jpg'), ...] → Qt '图片 (*.png *.jpg);;...'
# ---------------------------------------------------------------------------
def _ft2qt(filetypes) -> str:
    parts = []
    for label, pat in (filetypes or []):
        pats = str(pat).replace(',', ' ').split()
        parts.append('%s (%s)' % (label, ' '.join(pats)))
    return ';;'.join(parts) if parts else '所有文件 (*)'


# ---------------------------------------------------------------------------
# 文件 / 目录对话框
# ---------------------------------------------------------------------------
def open_file(title='', initialdir='', filetypes=None, parent=None) -> str:
    from PyQt5.QtWidgets import QFileDialog
    get_app()
    path, _ = QFileDialog.getOpenFileName(
        parent, title or '选择文件', initialdir or '', _ft2qt(filetypes))
    return path or ''


def open_files(title='', initialdir='', filetypes=None, parent=None) -> list[str]:
    from PyQt5.QtWidgets import QFileDialog
    get_app()
    paths, _ = QFileDialog.getOpenFileNames(
        parent, title or '选择文件', initialdir or '', _ft2qt(filetypes))
    return list(paths)


def save_file(title='', initialdir='', initialfile='', defaultextension='',
              filetypes=None, parent=None) -> str:
    from PyQt5.QtWidgets import QFileDialog
    get_app()
    start_dir = initialdir or ''
    if start_dir and initialfile and not start_dir.endswith(('/', '\\')):
        start_dir += '/'
    start_path = start_dir + (initialfile or '')
    path, _ = QFileDialog.getSaveFileName(
        parent, title or '保存文件', start_path, _ft2qt(filetypes))
    if path and defaultextension and not path.lower().endswith(defaultextension.lower()):
        path += defaultextension
    return path or ''


def select_dir(title='', initialdir='', parent=None) -> str:
    from PyQt5.QtWidgets import QFileDialog
    get_app()
    d = QFileDialog.getExistingDirectory(parent, title or '选择目录', initialdir or '')
    return d or ''


# ---------------------------------------------------------------------------
# 消息 / 输入对话框
# ---------------------------------------------------------------------------
def info(title: str, message: str, parent=None):
    from PyQt5.QtWidgets import QMessageBox
    get_app()
    return QMessageBox.information(parent, title, str(message))


def warn(title: str, message: str, parent=None):
    from PyQt5.QtWidgets import QMessageBox
    get_app()
    return QMessageBox.warning(parent, title, str(message))


def error(title: str, message: str, parent=None):
    from PyQt5.QtWidgets import QMessageBox
    get_app()
    return QMessageBox.critical(parent, title, str(message))


def yes_no(title: str, message: str, parent=None) -> bool:
    """确认框：确定 → True，取消 → False。"""
    from PyQt5.QtWidgets import QMessageBox
    get_app()
    res = QMessageBox.question(parent, title, str(message),
                               QMessageBox.Yes | QMessageBox.No,
                               QMessageBox.No)
    return res == QMessageBox.Yes


def yes_no_cancel(title: str, message: str, parent=None) -> str:
    """三态确认：返回 'yes' / 'no' / 'cancel'。"""
    from PyQt5.QtWidgets import QMessageBox
    get_app()
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(str(message))
    b_yes = box.addButton('是', QMessageBox.YesRole)
    b_no = box.addButton('否', QMessageBox.NoRole)
    b_cancel = box.addButton('取消', QMessageBox.RejectRole)
    box.setDefaultButton(b_cancel)
    box.exec_()
    clicked = box.clickedButton()
    if clicked is b_yes:
        return 'yes'
    if clicked is b_no:
        return 'no'
    return 'cancel'


def text_input(title: str, prompt: str, default: str = '', parent=None):
    """单行输入：确定返回字符串，取消返回 None。"""
    from PyQt5.QtWidgets import QInputDialog
    get_app()
    text, ok = QInputDialog.getText(parent, title, str(prompt), text=str(default or ''))
    return text if ok else None
