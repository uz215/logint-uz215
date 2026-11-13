# -*- coding: utf-8 -*-
"""补丁：在统一启动界面 select_startup_task() 增加可校正的数据选择
（测井数据 LAS / 气测 / 井目录），防止自动发现找不到或找错。

同时让 quicklook_well 接受 las_file 参数，使界面选定的 LAS 在 quicklook
模式下也生效；__main__ 调用补传 las_file。

改写保持 CRLF 行尾（与仓库约定一致）。改写后整文件归一化为 CRLF。
"""
import io

P = r'F:/360/src/logInt.py'
with open(P, 'rb') as f:
    raw = f.read()
text = raw.decode('utf-8')
# 统一为 \n 便于跨行字符串匹配；末尾再归一化回 CRLF
text = text.replace('\r\n', '\n')

# ---------------------------------------------------------------------------
# 1) 重写 select_startup_task() 主体（start = def ... 到 end = def run_well_...）
# ---------------------------------------------------------------------------
NEW_FUNC = '''def select_startup_task():
    """统一启动界面：先选任务，再选井目录；自动识别并允许手动校正测井数据/气测/井目录。

    返回 {'task','well_dir','inventory','las','config','gas'} 或 None（取消）。
    - las: 选定的测井 LAS 文件路径（界面可校正，防止找错/找不到）
    - gas: 选定的气测文件路径或 None（不使用气测）
    - well_dir: 选定井目录（用于提取基础数据：地质设计/录井图/格式/info）
    说明：只做功能选择与资料清单，不改变解释/知识/图谱/气测程序的既有能力。
    """
    import tkinter as tk
    from tkinter import ttk, filedialog
    from pathlib import Path as _P
    res = {}
    inv_cache = {}
    win = tk.Tk()
    win.title('logInt 智能测井解释 — 任务与数据选择（统一入口）')
    win.geometry('760x620')
    win.resizable(False, False)
    tk.Label(win, text='智能测井解释系统', font=('Microsoft YaHei', 15, 'bold')).pack(anchor='w', padx=18, pady=(14, 2))
    tk.Label(win, text='一个井目录放齐资料：LAS / 地质设计 / 录井图 / 气测 / 甲方格式 / info.json；程序按资料自动适配流程',
             font=('Microsoft YaHei', 9), fg='#555555').pack(anchor='w', padx=18)

    # 任务
    tk.Label(win, text='1. 选择任务', font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', padx=18, pady=(14, 4))
    _tasks = ['quicklook 快速解释图（现场工程师→交甲方代表）',
              '综合解释（岩性/流体/层表/综合图/报告，室内工程师）']
    _task_var = tk.StringVar(value=_tasks[0])
    ttk.Combobox(win, textvariable=_task_var, state='readonly', values=_tasks, width=84).pack(anchor='w', padx=18)

    # 井目录（用于提取基础数据）
    tk.Label(win, text='2. 选择井目录（用于提取基础数据：地质设计/录井图/格式/info）', font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', padx=18, pady=(14, 4))
    _dir_var = tk.StringVar(value='未选择')
    tk.Label(win, textvariable=_dir_var, fg='#1a5c9e', font=('Microsoft YaHei', 9), width=98, anchor='w').pack(anchor='w', padx=18)
    tk.Button(win, text='选择井目录...', command=lambda: _pick_dir(), width=18).pack(anchor='w', padx=18, pady=(4, 0))

    # 数据选择（目录选定后填充）
    _data_frame = tk.LabelFrame(win, text='3. 数据选择（可校正，防止找不到/找错）', font=('Microsoft YaHei', 11, 'bold'))
    _data_frame.pack(anchor='w', fill='x', padx=18, pady=(10, 4))
    tk.Label(_data_frame, text='测井数据 (LAS)：', width=16, anchor='w').grid(row=0, column=0, padx=4, pady=4, sticky='w')
    _las_var = tk.StringVar(value='（请先选择井目录）')
    _las_cb = ttk.Combobox(_data_frame, textvariable=_las_var, state='readonly', width=64)
    _las_cb.grid(row=0, column=1, padx=4, pady=4)
    tk.Button(_data_frame, text='浏览...', width=8, command=lambda: _browse_las()).grid(row=0, column=2, padx=4, pady=4)
    tk.Label(_data_frame, text='气测数据：', width=16, anchor='w').grid(row=1, column=0, padx=4, pady=4, sticky='w')
    _gas_var = tk.StringVar(value='（请先选择井目录）')
    _gas_cb = ttk.Combobox(_data_frame, textvariable=_gas_var, state='readonly', width=64)
    _gas_cb.grid(row=1, column=1, padx=4, pady=4)
    tk.Button(_data_frame, text='浏览...', width=8, command=lambda: _browse_gas()).grid(row=1, column=2, padx=4, pady=4)

    # 井目录资料清单（基础数据）
    tk.Label(win, text='井目录资料清单（地质设计/录井图/甲方格式/info.json）', font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w', padx=18, pady=(8, 2))
    _inv_txt = tk.Text(win, height=8, width=98, font=('Consolas', 9), state='disabled', relief='solid', bd=1)
    _inv_txt.pack(anchor='w', padx=18, pady=(2, 2))
    _note = tk.Label(win, text='未选/未找到的资料将在运行时自动跳过（不弹窗、不中断）。', font=('Microsoft YaHei', 8), fg='#777777')
    _note.pack(anchor='w', padx=18)

    def _refresh_data(wd):
        wd = _P(str(wd))
        las_files = sorted(wd.rglob('*.las'))
        main_las = _find_main_las(wd)
        inv_cache['las_main'] = str(main_las) if main_las else None
        if las_files:
            vals = [str(p) for p in las_files]
            _las_cb['values'] = vals
            _las_cb.set(str(main_las) if main_las else vals[0])
        else:
            _las_cb['values'] = []
            _las_cb.set('（井目录未找到 LAS）')
        gas_files = sorted(p for p in wd.rglob('*') if p.is_file() and _is_gas_file(p))[:8]
        inv_cache['gas_all'] = [str(p) for p in gas_files]
        gvals = ['(不使用气测)'] + [str(p) for p in gas_files]
        _gas_cb['values'] = gvals
        _gas_cb.set(gvals[1] if len(gvals) > 1 else gvals[0])

    def _pick_dir():
        d = filedialog.askdirectory(title='选择井目录（该目录下放 LAS/地质设计/录井图/气测/格式/info.json）')
        if not d:
            return
        _dir_var.set(d)
        inv = well_package_inventory(d)
        res['inventory'] = inv
        _show_inv(inv)
        _refresh_data(d)

    def _browse_las():
        if not res.get('inventory'):
            _note.configure(text='请先选择井目录。', fg='#b00')
            return
        f = filedialog.askopenfilename(title='选择测井 LAS 文件', filetypes=[('LAS 文件', '*.las'), ('全部', '*.*')])
        if not f:
            return
        cur = list(_las_cb['values'])
        if f not in cur:
            cur = [f] + cur
        _las_cb['values'] = cur
        _las_cb.set(f)

    def _browse_gas():
        if not res.get('inventory'):
            _note.configure(text='请先选择井目录。', fg='#b00')
            return
        f = filedialog.askopenfilename(title='选择气测数据文件', filetypes=[('气测/录井', '*.txt;*.csv;*.xls;*.xlsx;*.las'), ('全部', '*.*')])
        if not f:
            return
        cur = list(_gas_cb['values'])
        if f not in cur:
            cur = [f] + [c for c in cur if c != '(不使用气测)']
        _gas_cb['values'] = cur
        _gas_cb.set(f)

    def _show_inv(inv):
        lines = []
        def _fmt(label, ok, val):
            if ok:
                lines.append('  \\u2713 %-10s %s' % (label, val))
            else:
                lines.append('  - %-10s 未找到（运行时跳过）' % label)
        _fmt('地质设计', bool(inv.get('design')), '；'.join(Path(x).name for x in inv.get('design', [])[:3]))
        _fmt('录井图', bool(inv.get('masterlog')), Path(str(inv.get('masterlog'))).name if inv.get('masterlog') else '')
        _fmt('甲方格式', bool(inv.get('format')), Path(str(inv.get('format'))).name if inv.get('format') else '')
        _fmt('info.json', bool(inv.get('info')), Path(str(inv.get('info'))).name if inv.get('info') else '')
        try:
            _d = json.load(open(inv['info'], encoding='utf-8')) if inv.get('info') else {}
            _p = []
            if _d.get('解释来源'):
                _p.append('解释来源=%s' % _d.get('解释来源'))
            if _d.get('解释井段'):
                _p.append('解释井段=%s' % _d.get('解释井段'))
            if _d.get('解释截止值'):
                _p.append('解释截止值=已配置')
            _reg, _ = _guess_region(inv.get('well_dir'), None)
            if _reg:
                _p.append('区域=%s' % _reg)
            if _p:
                lines.append('')
                lines.append('  将采用参数：' + '；'.join(_p))
        except Exception:
            pass
        lines.append('')
        lines.append('  运行时会自动评估数据充分性、读取知识库/区域规则，并生成本次决策记录。')
        _inv_txt.configure(state='normal')
        _inv_txt.delete('1.0', 'end')
        _inv_txt.insert('1.0', '\\n'.join(lines))
        _inv_txt.configure(state='disabled')

    def _ok():
        if not res.get('inventory'):
            _note.configure(text='请先选择井目录。', fg='#b00')
            return
        task = 'quicklook' if _task_var.get().startswith('quicklook') else 'comprehensive'
        las_sel = _las_var.get()
        if not las_sel or las_sel.startswith('（'):
            las_sel = inv_cache.get('las_main')
        gas_sel = _gas_var.get()
        if not gas_sel or gas_sel == '(不使用气测)':
            gas_sel = None
        if not las_sel:
            _note.configure(text='需要 LAS：井目录未找到，请把 LAS 放进井目录或点“浏览...”指定。', fg='#b00')
            return
        inv = res['inventory']
        res.update({'task': task, 'well_dir': inv.get('well_dir'),
                    'las': las_sel, 'config': inv.get('format'),
                    'gas': gas_sel})
        win.destroy()

    _btns = tk.Frame(win)
    _btns.pack(anchor='e', padx=18, pady=(6, 10))
    tk.Button(_btns, text='取消', command=win.destroy, width=10).pack(side='left', padx=6)
    tk.Button(_btns, text='确定并运行', command=_ok, width=14).pack(side='left')
    win.mainloop()
    return res if res.get('task') else None
'''

start = text.index('def select_startup_task():')
end = text.index('def run_well_log_workflow(')
assert end > start, '函数边界异常'
assert text.count('def select_startup_task():') == 1
assert text.count('def run_well_log_workflow(') == 1
text = text[:start] + NEW_FUNC + '\n\n' + text[end:]

# ---------------------------------------------------------------------------
# 2) quicklook_well 增加 las_file 参数（签名 + LAS 发现块）
# ---------------------------------------------------------------------------
OLD_SIG = 'def quicklook_well(well_dir=None, config_file=None, gas_file=None):'
NEW_SIG = 'def quicklook_well(well_dir=None, config_file=None, gas_file=None, las_file=None):'
assert OLD_SIG in text, 'quicklook 签名未找到'
text = text.replace(OLD_SIG, NEW_SIG, 1)

OLD_LAS = "    las_main = _find_main_las(well_dir)\n    if las_main is None:"
NEW_LAS = ("    # 【2026-11-02 启动界面数据选择】界面显式选定 LAS 时优先使用，否则回退主 LAS 自动发现\n"
           "    las_main = Path(las_file) if las_file else _find_main_las(well_dir)\n"
           "    if las_main is None or not Path(las_main).is_file():")
assert OLD_LAS in text, 'LAS 发现块未找到'
text = text.replace(OLD_LAS, NEW_LAS, 1)

# ---------------------------------------------------------------------------
# 3) __main__ 调用补传 las_file
# ---------------------------------------------------------------------------
OLD_CALL = "gas_file=_sel2.get('gas'))"
NEW_CALL = "gas_file=_sel2.get('gas'), las_file=_sel2.get('las'))"
assert OLD_CALL in text, '__main__ 调用未找到'
text = text.replace(OLD_CALL, NEW_CALL, 1)

# ---------------------------------------------------------------------------
# 归一化为 CRLF（仓库约定），保持其它行不变
# ---------------------------------------------------------------------------
text = text.replace('\r\n', '\n').replace('\n', '\r\n')
with open(P, 'wb') as f:
    f.write(text.encode('utf-8'))

# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
checks = {
    '_las_cb': text.count('_las_cb'),
    '_gas_cb': text.count('_gas_cb'),
    'las_file in quicklook sig': NEW_SIG in text,
    'las_file in __main__ call': NEW_CALL in text,
    'def select_startup_task count': text.count('def select_startup_task():'),
    'def run_well_log_workflow count': text.count('def run_well_log_workflow('),
}
print('OK: 已重写 logInt.py')
for k, v in checks.items():
    print('  %-32s = %s' % (k, v))
