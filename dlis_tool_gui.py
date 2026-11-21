"""
dlis_tool_gui.py
DLIS工具GUI：单文件+批量，带json配置持久化；支持dlis/las/csv/xlsx

【R83】GUI 由 tkinter 迁移到 PyQt5。业务逻辑（logint.dlis_tool.DlisTool）不变。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit,
    QComboBox, QListWidget, QTextEdit, QTabWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout,
)
from logsys import qtgui as _qg
from logint.dlis_tool import DlisTool


class DlisToolWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('DLIS工具 | logint-win-f360')
        self.resize(780, 650)
        self.tool = DlisTool()
        self.in_file = ''
        self.build_ui()
        self.fill_config()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        b1 = QPushButton('刷新配置')
        b1.clicked.connect(self.fill_config)
        b2 = QPushButton('保存当前配置')
        b2.clicked.connect(self.save_gui_config)
        top_bar.addWidget(b1)
        top_bar.addWidget(b2)
        top_bar.addStretch(1)
        root.addLayout(top_bar)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # ========== 单文件 ==========
        single = QWidget()
        sl = QVBoxLayout(single)
        top_frame = QHBoxLayout()
        btn_open = QPushButton('打开DLIS')
        btn_open.clicked.connect(self.open_dlis)
        self.file_label = QLabel('未选择文件')
        top_frame.addWidget(btn_open)
        top_frame.addWidget(self.file_label, 1)
        sl.addLayout(top_frame)

        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        il = QVBoxLayout(info_frame)
        il.addWidget(QLabel('井信息'))
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(80)
        il.addWidget(self.info_text)
        sl.addWidget(info_frame)

        curve_frame = QFrame()
        curve_frame.setFrameShape(QFrame.StyledPanel)
        cl = QVBoxLayout(curve_frame)
        cl.addWidget(QLabel('曲线列表'))
        self.curve_list = QListWidget()
        cl.addWidget(self.curve_list)
        sl.addWidget(curve_frame, 1)

        mod_frame = QFrame()
        mod_frame.setFrameShape(QFrame.StyledPanel)
        ml = QHBoxLayout(mod_frame)
        ml.addWidget(QLabel('曲线偏移修改'))
        ml.addWidget(QLabel('偏移值：'))
        self.offset_entry = QLineEdit()
        self.offset_entry.setFixedWidth(90)
        ml.addWidget(self.offset_entry)
        btn_off = QPushButton('应用偏移')
        btn_off.clicked.connect(self.apply_offset)
        ml.addWidget(btn_off)
        ml.addStretch(1)
        sl.addWidget(mod_frame)

        export_frame = QHBoxLayout()
        for text, slot in (('另存DLIS', self.save_dlis), ('导出LAS', self.export_las),
                           ('导出CSV', self.export_csv), ('导出XLSX', self.export_xlsx)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            export_frame.addWidget(b)
        export_frame.addStretch(1)
        sl.addLayout(export_frame)
        tabs.addTab(single, '单文件处理')

        # ========== 批量 ==========
        batch = QWidget()
        bl = QVBoxLayout(batch)
        g1 = QGridLayout()
        g1.addWidget(QLabel('输入文件夹：'), 0, 0)
        self.batch_in_var = QLineEdit()
        g1.addWidget(self.batch_in_var, 0, 1)
        bi = QPushButton('选择')
        bi.clicked.connect(self.select_batch_in)
        g1.addWidget(bi, 0, 2)
        g1.addWidget(QLabel('输出文件夹：'), 1, 0)
        self.batch_out_var = QLineEdit()
        g1.addWidget(self.batch_out_var, 1, 1)
        bo = QPushButton('选择')
        bo.clicked.connect(self.select_batch_out)
        g1.addWidget(bo, 1, 2)
        bl.addLayout(g1)

        g2 = QGridLayout()
        g2.addWidget(QLabel('输出格式：'), 0, 0)
        self.batch_fmt_combo = QComboBox()
        self.batch_fmt_combo.addItems(['dlis', 'las', 'csv', 'xlsx'])
        g2.addWidget(self.batch_fmt_combo, 0, 1)
        g2.addWidget(QLabel('曲线名(可选)：'), 0, 2)
        self.batch_curve_var = QLineEdit()
        g2.addWidget(self.batch_curve_var, 0, 3)
        g2.addWidget(QLabel('偏移值(可选)：'), 0, 4)
        self.batch_offset_var = QLineEdit()
        g2.addWidget(self.batch_offset_var, 0, 5)
        bl.addLayout(g2)

        btn_run = QPushButton('开始批量转换')
        btn_run.clicked.connect(self.run_batch)
        bl.addWidget(btn_run)

        bl.addWidget(QLabel('批量日志'))
        self.batch_log = QTextEdit()
        self.batch_log.setReadOnly(True)
        bl.addWidget(self.batch_log, 1)
        tabs.addTab(batch, '批量文件夹处理')

    # -- 配置 --------------------------------------------------------------
    def fill_config(self):
        cfg = self.tool.config
        idx = self.batch_fmt_combo.findText(cfg.get('default_format', 'las'))
        if idx >= 0:
            self.batch_fmt_combo.setCurrentIndex(idx)
        self.batch_curve_var.setText(cfg.get('batch_curve', ''))
        off = cfg.get('batch_offset')
        self.batch_offset_var.setText(str(off) if off is not None else '')
        self.batch_in_var.setText(cfg.get('last_in_dir', ''))
        self.batch_out_var.setText(cfg.get('last_out_dir', ''))

    def save_gui_config(self):
        cfg = self.tool.config
        cfg['default_format'] = self.batch_fmt_combo.currentText()
        cfg['batch_curve'] = self.batch_curve_var.text().strip()
        off_str = self.batch_offset_var.text().strip()
        cfg['batch_offset'] = float(off_str) if off_str else None
        cfg['last_in_dir'] = self.batch_in_var.text().strip()
        cfg['last_out_dir'] = self.batch_out_var.text().strip()
        self.tool.save_config()
        _qg.info('配置', '已保存到 dlis_config.json', self)

    # -- 单文件 ------------------------------------------------------------
    def open_dlis(self):
        fp = _qg.open_file(title='选择DLIS',
                           filetypes=[('DLIS文件', '*.dlis'), ('所有文件', '*.*')],
                           parent=self)
        if not fp:
            return
        try:
            self.in_file = fp
            self.file_label.setText(fp)
            df, info = self.tool.load_dlis(fp)
            self.info_text.setPlainText('\n'.join('%s:%s' % (k, v) for k, v in info.items()))
            self.curve_list.clear()
            for c in df.columns:
                self.curve_list.addItem(str(c))
            _qg.info('成功', 'DLIS读取完成', self)
        except Exception as e:
            _qg.error('读取失败', str(e), self)

    def apply_offset(self):
        cur = self.curve_list.currentItem()
        if cur is None:
            _qg.warn('提示', '选中一条曲线', self)
            return
        curve_name = cur.text()
        try:
            val = float(self.offset_entry.text())
            self.tool.modify_curve(curve_name, lambda arr: arr + val)
            _qg.info('完成', '%s 偏移 %s' % (curve_name, val), self)
        except Exception as e:
            _qg.error('错误', str(e), self)

    def save_dlis(self):
        fp = _qg.save_file(defaultextension='.dlis', filetypes=[('DLIS', '*.dlis')], parent=self)
        if fp:
            self.tool.save_dlis(fp)
            _qg.info('完成', 'DLIS已保存', self)

    def export_las(self):
        fp = _qg.save_file(defaultextension='.las', filetypes=[('LAS', '*.las')], parent=self)
        if fp:
            self.tool.export_las(fp)
            _qg.info('完成', 'LAS导出完成，可直接给logint计算REG', self)

    def export_csv(self):
        fp = _qg.save_file(defaultextension='.csv', filetypes=[('CSV', '*.csv')], parent=self)
        if fp:
            self.tool.export_csv(fp)
            _qg.info('完成', 'CSV导出完成', self)

    def export_xlsx(self):
        fp = _qg.save_file(defaultextension='.xlsx', filetypes=[('Excel XLSX', '*.xlsx')], parent=self)
        if fp:
            self.tool.export_xlsx(fp)
            _qg.info('完成', 'XLSX导出完成', self)

    # -- 批量 --------------------------------------------------------------
    def select_batch_in(self):
        d = _qg.select_dir(title='选择DLIS输入文件夹', parent=self)
        if d:
            self.batch_in_var.setText(d)

    def select_batch_out(self):
        d = _qg.select_dir(title='选择输出文件夹', parent=self)
        if d:
            self.batch_out_var.setText(d)

    def run_batch(self):
        in_dir = self.batch_in_var.text().strip()
        out_dir = self.batch_out_var.text().strip()
        fmt = self.batch_fmt_combo.currentText()
        curve = self.batch_curve_var.text().strip()
        offset_str = self.batch_offset_var.text().strip()
        if not in_dir or not out_dir:
            _qg.warn('提示', '请选择输入、输出文件夹', self)
            return
        self.batch_log.clear()
        try:
            off_val = float(offset_str) if offset_str else None
            curve_name = curve if curve else None
            succ, fail = self.tool.batch_convert(in_dir, out_dir, fmt, curve_name, off_val)
            self.batch_log.append('✅ 成功：%d 个\n' % len(succ))
            for s in succ:
                self.batch_log.append('  %s\n' % s)
            if fail:
                self.batch_log.append('\n❌ 失败：%d 个\n' % len(fail))
                for f, err in fail:
                    self.batch_log.append('  %s : %s\n' % (f, err))
            _qg.info('批量结束', '成功%d，失败%d' % (len(succ), len(fail)), self)
        except Exception as e:
            self.batch_log.append('💥 全局异常：%s\n' % str(e))
            _qg.error('批量出错', str(e), self)


if __name__ == '__main__':
    app = QApplication.instance() or QApplication([])
    win = DlisToolWindow()
    win.show()
    app.exec_()
