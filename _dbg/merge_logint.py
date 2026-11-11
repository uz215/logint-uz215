#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io

G = r"G:/360/src/logInt.py"
F = r"F:/360/src/logInt.py"

with io.open(G, encoding="utf-8") as fh:
    glines = fh.readlines()
with io.open(F, encoding="utf-8") as fh:
    ftext = fh.read()

# 提取 G: 的两个函数 (well_package_inventory + select_startup_task): 行 17938..18087 (1-indexed)
ui = glines[17937:18087]
assert ui[0].lstrip().startswith("def well_package_inventory"), "首行应为 well_package_inventory, 实际: %r" % ui[0]
ui_block = "".join(ui)

# 在 F: 的 def select_run_mode(): 之前插入
anchor = "\ndef select_run_mode():"
idx = ftext.find(anchor)
assert idx != -1, "未找到 select_run_mode 锚点"
header = ("\n"
          "# =============================================================================\n"
          "# 【2026-11-02 合并自 G:】统一启动界面相关函数（结构化管理：每个模块规定任务\n"
          "# + 文档化）。以下两个函数来自 G:/360/src/logInt.py 的周末结构化改动，\n"
          "# 与本地 R57 功能（build_interpretation_layer_table / run_workflow 等）并存。\n"
          "# well_package_inventory 依赖 logsys.well_docs（已并入本仓库 logsys/）。\n"
          "# =============================================================================\n")
new_ftext = ftext[:idx] + header + ui_block + ftext[idx:]

# 替换 __main__ 默认分支：select_run_mode() -> select_startup_task() 分发
old_block = ("            _mode, _tgt, _cfg, _gas = _sel\n"
             "            if _mode in ('quicklook', 'config'):\n"
             "                quicklook_well(_tgt, config_file=_cfg, gas_file=_gas)\n"
             "            else:\n"
             "                run_well_log_workflow(file_path=_tgt, plot_mode=_mode, gas_file=_gas)")
assert old_block in new_ftext, "未找到 __main__ 默认分支待替换块"
new_block = ("            # 【2026-11-01 R72】统一启动界面：任务选择 + 井目录（资料统一存放）\n"
             "            _sel2 = select_startup_task()\n"
             "            if _sel2 is None:\n"
             "                print(\"已取消，未执行。\")\n"
             "                sys.exit(0)\n"
             "            if _sel2.get('task') == 'quicklook':\n"
             "                quicklook_well(_sel2.get('well_dir'), config_file=_sel2.get('config'),\n"
             "                               gas_file=_sel2.get('gas'))\n"
             "            else:\n"
             "                run_well_log_workflow(file_path=_sel2.get('las'), plot_mode='all',\n"
             "                                      gas_file=_sel2.get('gas'))")
new_ftext = new_ftext.replace(old_block, new_block, 1)

with io.open(F, "w", encoding="utf-8", newline="") as fh:
    fh.write(new_ftext)

print("MERGE_OK  F:行数=%d  插入ui块行数=%d" % (new_ftext.count("\n")+1, len(ui)))
