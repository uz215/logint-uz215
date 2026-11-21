"""深度视窗内的包络降采样。

【R80 交互绘图】
测井曲线的尖峰（薄层、扩径、煤层响应）是关键地质信息，
**均值抽稀会抹平**，必须取 min/max 包络。

目标：把 4 万行数据压到 ~2×画布像素高度的点数，且保留尖峰。
"""
from __future__ import annotations

import numpy as np


def envelope_decimate(values, n_bins: int):
    """返回 (抽稀后的值数组, 对应的原始索引数组)。

    每个 bin 取 min 和 max 两点，并按原始先后顺序排列，
    保证连线形状忠实于原曲线的包络。
    全 NaN 的 bin 跳过（不产生伪值）。
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    if n_bins <= 0 or n <= n_bins * 2:
        idx = np.arange(n)
        return v, idx

    edges = np.linspace(0, n, n_bins + 1).astype(int)
    out_v: list[float] = []
    out_i: list[int] = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        seg = v[a:b]
        if seg.size == 0:
            continue
        finite = seg[~np.isnan(seg)]
        if finite.size == 0:
            continue                      # 全 NaN 的 bin 跳过，不产生伪值
        with np.errstate(invalid='ignore'):
            seg2 = np.where(np.isnan(seg), np.nan, seg)
            imin = int(np.nanargmin(seg2))
            imax = int(np.nanargmax(seg2))
        for k in sorted({imin, imax}):
            out_v.append(seg[k])
            out_i.append(a + k)
    if not out_v:
        idx = np.arange(n)
        return v, idx
    return np.asarray(out_v), np.asarray(out_i)


def depth_window_slice(depth, top, bottom):
    """返回深度落在 [top, bottom] 内的布尔掩码（深度轴假定单调）。"""
    d = np.asarray(depth, dtype=float)
    lo, hi = (top, bottom) if top <= bottom else (bottom, top)
    return (d >= lo) & (d <= hi)


def decimate_for_pixels(values, depth, top, bottom, pixel_height: int,
                        min_bins: int = 40, max_bins: int = 2000):
    """按画布像素高度决定抽稀档位，并只取深度窗口内的点。

    返回 (值数组, 深度数组, 原始索引数组)。
    """
    v = np.asarray(values, dtype=float)
    d = np.asarray(depth, dtype=float)
    if v.size == 0 or d.size == 0:
        return v, d, np.arange(v.size)
    mask = depth_window_slice(d, top, bottom)
    if not mask.any():
        return v[:0], d[:0], np.arange(0)
    idx_all = np.nonzero(mask)[0]
    vw = v[idx_all]
    dw = d[idx_all]
    n_bins = int(max(min_bins, min(max_bins, pixel_height * 0.75)))
    dv, di = envelope_decimate(vw, n_bins)
    return dv, dw[di], idx_all[di]
