"""交互式测井图（Log View）模块。

【R80 交互绘图】
Techlog logview 风格的交互式绘图能力，作为**项目工作台的井级动作**提供，
不新增独立程序入口（手册 §0.3「所有能力作为既有程序的功能」）。

能力：
  - 曲线目录拖入绘图区即自动出曲线（纯 tkinter 三段式拖放实现）；
  - 绘图区图头实时可改（写回 `<井名>info.json`，快速图/综合图同步生效）；
  - 曲线/道实时增减、道序调整；
  - 版式与静态出图**同源**（共用 logvis.logview.track_spec 的布局解析）。

模块划分：
    track_spec.py  道/曲线配置与布局解析（静态出图与交互画布共用）
    decimate.py    包络降采样（保尖峰）
    datasource.py  井数据装配（曲线表/层段表/井信息）
    catalog.py     曲线目录（复用 project_model 的 Techlog 三色语义）
    header.py      图头字段读写
    canvas.py      交互画布
    window.py      主窗口（三栏 + 拖放）
"""
from __future__ import annotations

__all__ = [
    'track_spec', 'decimate', 'datasource', 'catalog', 'header', 'canvas', 'window',
]


def open_logview(master, well_name: str, out_dir: str = '', source_dir: str = '',
                 las_file: str = '', kind: str = 'qlpt'):
    """打开交互绘图窗口（便捷入口，延迟导入以免拖起 matplotlib）。"""
    from logsys.logview.window import open_logview as _open
    return _open(master, well_name, out_dir=out_dir, source_dir=source_dir,
                 las_file=las_file, kind=kind)
