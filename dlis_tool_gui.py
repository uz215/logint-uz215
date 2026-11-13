"""
dlis_tool_gui.py
DLIS工具GUI：单文件+批量，带json配置持久化；支持dlis/las/csv/xlsx
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from logint.dlis_tool import DlisTool


class DlisToolWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("DLIS工具 | logint-win-f360")
        self.geometry("780x650")
        self.tool = DlisTool()
        self.in_file = ""
        self.build_ui()
        self.fill_config()

    def build_ui(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=5, pady=2)
        ttk.Button(top_bar, text="刷新配置", command=self.fill_config).pack(side="left")
        ttk.Button(top_bar, text="保存当前配置", command=self.save_gui_config).pack(side="left", padx=5)

        tab_control = ttk.Notebook(self)
        tab_single = ttk.Frame(tab_control)
        tab_batch = ttk.Frame(tab_control)
        tab_control.add(tab_single, text="单文件处理")
        tab_control.add(tab_batch, text="批量文件夹处理")
        tab_control.pack(fill="both", expand=True, padx=5, pady=5)

        # ========== 单文件 ==========
        top_frame = ttk.Frame(tab_single)
        top_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(top_frame, text="打开DLIS", command=self.open_dlis).pack(side="left")
        self.file_label = ttk.Label(top_frame, text="未选择文件")
        self.file_label.pack(side="left", padx=8)

        info_frame = ttk.LabelFrame(tab_single, text="井信息")
        info_frame.pack(fill="x", padx=5, pady=2)
        self.info_text = tk.Text(info_frame, height=3)
        self.info_text.pack(fill="x", padx=3)

        curve_frame = ttk.LabelFrame(tab_single, text="曲线列表")
        curve_frame.pack(fill="both", expand=True, padx=5, pady=2)
        self.curve_list = tk.Listbox(curve_frame)
        self.curve_list.pack(fill="both", expand=True)

        mod_frame = ttk.LabelFrame(tab_single, text="曲线偏移修改")
        mod_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(mod_frame, text="偏移值：").grid(row=0, column=0)
        self.offset_entry = ttk.Entry(mod_frame, width=10)
        self.offset_entry.grid(row=0, column=1, padx=3)
        ttk.Button(mod_frame, text="应用偏移", command=self.apply_offset).grid(row=0, column=2, padx=5)

        export_frame = ttk.Frame(tab_single)
        export_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(export_frame, text="另存DLIS", command=self.save_dlis).pack(side="left", padx=3)
        ttk.Button(export_frame, text="导出LAS", command=self.export_las).pack(side="left", padx=3)
        ttk.Button(export_frame, text="导出CSV", command=self.export_csv).pack(side="left", padx=3)
        ttk.Button(export_frame, text="导出XLSX", command=self.export_xlsx).pack(side="left", padx=3)

        # ========== 批量 ==========
        batch_in_f = ttk.Frame(tab_batch)
        batch_in_f.pack(fill="x", padx=5, pady=4)
        ttk.Label(batch_in_f, text="输入文件夹：").grid(row=0, column=0)
        self.batch_in_var = tk.StringVar()
        ttk.Entry(batch_in_f, textvariable=self.batch_in_var, width=48).grid(row=0, column=1, padx=4)
        ttk.Button(batch_in_f, text="选择", command=self.select_batch_in).grid(row=0, column=2)

        batch_out_f = ttk.Frame(tab_batch)
        batch_out_f.pack(fill="x", padx=5, pady=4)
        ttk.Label(batch_out_f, text="输出文件夹：").grid(row=0, column=0)
        self.batch_out_var = tk.StringVar()
        ttk.Entry(batch_out_f, textvariable=self.batch_out_var, width=48).grid(row=0, column=1, padx=4)
        ttk.Button(batch_out_f, text="选择", command=self.select_batch_out).grid(row=0, column=2)

        batch_opt_f = ttk.Frame(tab_batch)
        batch_opt_f.pack(fill="x", padx=5, pady=4)
        ttk.Label(batch_opt_f, text="输出格式：").grid(row=0, column=0)
        self.batch_fmt_combo = ttk.Combobox(batch_opt_f, values=["dlis", "las", "csv", "xlsx"], state="readonly", width=8)
        self.batch_fmt_combo.grid(row=0, column=1, padx=4)

        ttk.Label(batch_opt_f, text="曲线名(可选)：").grid(row=0, column=2, padx=(10,0))
        self.batch_curve_var = tk.StringVar()
        ttk.Entry(batch_opt_f, textvariable=self.batch_curve_var, width=8).grid(row=0, column=3)

        ttk.Label(batch_opt_f, text="偏移值(可选)：").grid(row=0, column=4, padx=(5,0))
        self.batch_offset_var = tk.StringVar()
        ttk.Entry(batch_opt_f, textvariable=self.batch_offset_var, width=8).grid(row=0, column=5)

        batch_run_f = ttk.Frame(tab_batch)
        batch_run_f.pack(fill="x", padx=5, pady=10)
        ttk.Button(batch_run_f, text="开始批量转换", command=self.run_batch).pack()

        batch_log_f = ttk.LabelFrame(tab_batch, text="批量日志")
        batch_log_f.pack(fill="both", expand=True, padx=5, pady=2)
        self.batch_log = tk.Text(batch_log_f)
        self.batch_log.pack(fill="both", expand=True)

    def fill_config(self):
        cfg = self.tool.config
        self.batch_fmt_combo.set(cfg.get("default_format", "las"))
        self.batch_curve_var.set(cfg.get("batch_curve", ""))
        off = cfg.get("batch_offset")
        self.batch_offset_var.set(str(off) if off is not None else "")
        self.batch_in_var.set(cfg.get("last_in_dir", ""))
        self.batch_out_var.set(cfg.get("last_out_dir", ""))

    def save_gui_config(self):
        cfg = self.tool.config
        cfg["default_format"] = self.batch_fmt_combo.get()
        cfg["batch_curve"] = self.batch_curve_var.get().strip()
        off_str = self.batch_offset_var.get().strip()
        cfg["batch_offset"] = float(off_str) if off_str else None
        cfg["last_in_dir"] = self.batch_in_var.get().strip()
        cfg["last_out_dir"] = self.batch_out_var.get().strip()
        self.tool.save_config()
        messagebox.showinfo("配置", "已保存到 dlis_config.json")

    def open_dlis(self):
        fp = filedialog.askopenfilename(
            title="选择DLIS",
            filetypes=[("DLIS文件", "*.dlis"), ("所有文件", "*.*")]
        )
        if not fp:
            return
        try:
            self.in_file = fp
            self.file_label.config(text=fp)
            df, info = self.tool.load_dlis(fp)
            self.info_text.delete(1.0, tk.END)
            self.info_text.insert(tk.END, "\n".join(f"{k}:{v}" for k, v in info.items()))
            self.curve_list.delete(0, tk.END)
            for c in df.columns:
                self.curve_list.insert(tk.END, c)
            messagebox.showinfo("成功", "DLIS读取完成")
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    def apply_offset(self):
        sel = self.curve_list.curselection()
        if not sel:
            messagebox.showwarning("提示", "选中一条曲线")
            return
        curve_name = self.curve_list.get(sel[0])
        try:
            val = float(self.offset_entry.get())
            self.tool.modify_curve(curve_name, lambda arr: arr + val)
            messagebox.showinfo("完成", f"{curve_name} 偏移 {val}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def save_dlis(self):
        fp = filedialog.asksaveasfilename(defaultextension=".dlis", filetypes=[("DLIS", "*.dlis")])
        if fp:
            self.tool.save_dlis(fp)
            messagebox.showinfo("完成", "DLIS已保存")

    def export_las(self):
        fp = filedialog.asksaveasfilename(defaultextension=".las", filetypes=[("LAS", "*.las")])
        if fp:
            self.tool.export_las(fp)
            messagebox.showinfo("完成", "LAS导出完成，可直接给logint计算REG")

    def export_csv(self):
        fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if fp:
            self.tool.export_csv(fp)
            messagebox.showinfo("完成", "CSV导出完成")

    def export_xlsx(self):
        fp = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel XLSX", "*.xlsx")])
        if fp:
            self.tool.export_xlsx(fp)
            messagebox.showinfo("完成", "XLSX导出完成")

    def select_batch_in(self):
        d = filedialog.askdirectory(title="选择DLIS输入文件夹")
        if d:
            self.batch_in_var.set(d)

    def select_batch_out(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.batch_out_var.set(d)

    def run_batch(self):
        in_dir = self.batch_in_var.get().strip()
        out_dir = self.batch_out_var.get().strip()
        fmt = self.batch_fmt_combo.get()
        curve = self.batch_curve_var.get().strip()
        offset_str = self.batch_offset_var.get().strip()

        if not in_dir or not out_dir:
            messagebox.showwarning("提示", "请选择输入、输出文件夹")
            return
        self.batch_log.delete(1.0, tk.END)
        try:
            off_val = float(offset_str) if offset_str else None
            curve_name = curve if curve else None
            succ, fail = self.tool.batch_convert(in_dir, out_dir, fmt, curve_name, off_val)
            self.batch_log.insert(tk.END, f"✅ 成功：{len(succ)} 个\n")
            for s in succ:
                self.batch_log.insert(tk.END, f"  {s}\n")
            if fail:
                self.batch_log.insert(tk.END, f"\n❌ 失败：{len(fail)} 个\n")
                for f, err in fail:
                    self.batch_log.insert(tk.END, f"  {f} : {err}\n")
            messagebox.showinfo("批量结束", f"成功{len(succ)}，失败{len(fail)}")
        except Exception as e:
            self.batch_log.insert(tk.END, f"💥 全局异常：{str(e)}\n")
            messagebox.showerror("批量出错", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    win = DlisToolWindow(root)
    win.mainloop()
