"""交互绘图的井数据装配。

【R80 交互绘图】
把一口井的"可画的东西"装配成一个对象：
  - 曲线表（解释曲线集 processed.csv；缺失时回退原始 LAS）
  - 层段表（interpretation_layers.csv）
  - 井信息（<井名>info.json，图头字段的来源）

装配路径与 `logsys/rerender.py` 的最小闭环一致：
    processed.csv + info.json → 出图
这样交互画布与静态出图读的是同一份数据，不会出现"两套数据分叉"。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEPTH_COLUMN = 'MD'
INFO_SUFFIX = 'info.json'


@dataclass
class WellData:
    """一口井的绘图数据。"""
    well_name: str = ''
    df: object = None                # pandas.DataFrame
    depth: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    layers: object = None            # pandas.DataFrame（层段表）
    info: dict = field(default_factory=dict)
    depth_unit: str = 'm'
    out_dir: str = ''                # 产物目录
    source_dir: str = ''             # 原始资料目录
    origin: str = ''                 # 'processed' | 'las' | ''
    note: str = ''

    @property
    def has_data(self) -> bool:
        return self.df is not None and len(self.df) > 0

    @property
    def columns(self) -> list[str]:
        if self.df is None:
            return []
        return [str(c) for c in self.df.columns]

    @property
    def depth_range(self) -> tuple[float, float]:
        if self.depth.size == 0:
            return (0.0, 1.0)
        return (float(self.depth[0]), float(self.depth[-1]))

    def series(self, column: str):
        """取一列的数值数组（缺列返回空数组）。"""
        if self.df is None or column not in self.df.columns:
            return np.array([], dtype=float)
        return self.df[column].to_numpy(dtype=float)


# --------------------------------------------------------------------------
# 定位
# --------------------------------------------------------------------------

def find_output_dir(root: str, well_name: str) -> str:
    """在项目根下定位某井的产物目录。"""
    if not root:
        return ''
    cands = [
        os.path.join(root, 'output', well_name),
        os.path.join(root, well_name),
    ]
    for c in cands:
        if os.path.isdir(c):
            return c
    out_root = os.path.join(root, 'output')
    if os.path.isdir(out_root):
        for name in sorted(os.listdir(out_root)):
            if name.lower() == well_name.lower():
                return os.path.join(out_root, name)
    return ''


def _first_existing(dirpath: str, patterns: list[str]) -> str:
    if not dirpath or not os.path.isdir(dirpath):
        return ''
    for pat in patterns:
        hits = sorted(Path(dirpath).glob(pat))
        if hits:
            return str(hits[0])
    return ''


def find_processed_csv(out_dir: str, well_name: str) -> str:
    return _first_existing(out_dir, [f'{well_name}_processed.csv', '*_processed.csv'])


def find_layers_csv(out_dir: str, well_name: str) -> str:
    return _first_existing(out_dir, [
        f'{well_name}_interpretation_layers.csv',
        '*_interpretation_layers.csv',
        '*_interpretation_layers_ML.csv',
    ])


def find_info_json(out_dir: str, well_name: str) -> str:
    return _first_existing(out_dir, [f'{well_name}{INFO_SUFFIX}', f'*{INFO_SUFFIX}'])


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------

def _read_csv(path: str):
    if not path:
        return None
    try:
        import pandas as pd
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None


def _read_json(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _depth_unit_of(info: dict, df) -> str:
    """深度单位：井信息优先；缺失按米（与 logvis._detect_depth_unit 一致，不再按数值猜）。"""
    for key in ('depth_unit', 'unit'):
        v = (info or {}).get(key)
        if v:
            s = str(v).strip().lower()
            if s in ('m', 'ft', 'meters', 'feet'):
                return 'ft' if s.startswith('f') else 'm'
    return 'm'


def load_well_data(well_name: str, out_dir: str = '', source_dir: str = '',
                   las_file: str = '') -> WellData:
    """装配一口井的绘图数据。

    优先用解释曲线集（processed.csv）；没有则回退读原始 LAS。
    """
    import pandas as pd

    wd = WellData(well_name=well_name, out_dir=out_dir or '', source_dir=source_dir or '')

    p_csv = find_processed_csv(out_dir, well_name) if out_dir else ''
    p_layers = find_layers_csv(out_dir, well_name) if out_dir else ''
    p_info = find_info_json(out_dir, well_name) if out_dir else ''

    wd.info = _read_json(p_info)
    wd.layers = _read_csv(p_layers)

    df = _read_csv(p_csv) if p_csv else None
    if df is not None and df.empty:
        df = None

    if df is None and las_file and os.path.exists(las_file):
        try:
            import lasio
            las = lasio.read(las_file)
            df = las.df().reset_index()
            wd.note = '曲线来自原始 LAS（无解释曲线集）'
        except Exception as e:
            wd.note = f'LAS 读取失败：{e}'

    if df is None:
        wd.note = wd.note or '未找到解释曲线集或 LAS'
        return wd

    # 深度列：优先 MD，其次常见深度列名
    depth_col = None
    for cand in (DEPTH_COLUMN, 'DEPT', 'DEPTH', 'MD_'):
        if cand in df.columns:
            depth_col = cand
            break
    if depth_col is None:
        wd.note = '曲线表缺少深度列'
        return wd

    df = df.sort_values(depth_col).reset_index(drop=True)
    wd.df = df
    wd.depth = df[depth_col].to_numpy(dtype=float)
    wd.depth_unit = _depth_unit_of(wd.info, df)
    wd.origin = 'processed' if p_csv else 'las'
    return wd


def save_info_json(path: str, info: dict) -> bool:
    """写回井信息 JSON（保留原有键，仅覆盖传入项）。"""
    if not path:
        return False
    data = _read_json(path)
    data.update(info or {})
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def update_info_field(info_path: str, key: str, value: str) -> bool:
    """单个字段写回井信息 JSON（图头实时编辑的落盘出口）。"""
    if not info_path or not key:
        return False
    return save_info_json(info_path, {key: value})
