"""
dlis converter.py
DLIS 转换工具（兼容入口）。

【R83】tkinter 版本与本仓库 dlis_tool_gui.py 完全重复；GUI 统一迁移到
PyQt5 后，这里直接复用 dlis_tool_gui.DlisToolWindow，保持两种启动方式
都能用，且只有一份界面代码需要维护。
"""
from dlis_tool_gui import DlisToolWindow  # noqa: F401  (兼容导出)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = DlisToolWindow()
    win.show()
    app.exec_()
