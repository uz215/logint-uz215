# =============================================================================
# 测井综合图可视化模块 - 完整修复版
# 修复问题：
# 1. 道名位置不对
# 2. 图头区左右边框超出问题
# 3. 图头区底框作为第一条刻度线
# 4. 添加PE曲线刻度
# =============================================================================

import os
import sys
import logging
import math
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.artist
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from pathlib import Path
import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log_visualizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== 岩性符号图片系统 ==========
SYMBOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'symbol')
_lithology_symbol_cache = {}

# 岩性符号图片标准化尺寸（正方形，像素）
SYMBOL_STANDARD_SIZE = 512
# 岩性符号平铺参数
TILE_DEPTH_M = 1.0        # 每个符号单元代表的深度（米），即每1.0米重复一次图案
                           # 1:200比例下=0.5cm/单元，300DPI打印≈59px，512→256px tile=4.3x oversample→清晰
SYMBOL_TILE_PX = 256      # 单个符号单元在下采样后的像素高度（用于构建平铺图像）
SYMBOL_X_EXTENT = 0.8     # 符号在岩性道内的水平填充比例（0-1之间，0.8=占道宽80%）
MIN_LAYER_THICKNESS_M = 0.25  # 最小层厚，小于此厚度的薄层不绘制岩性/沉积相/解释结论

# 岩性值 → 符号图片文件名 映射
LITHOLOGY_TO_SYMBOL = {
    'sandstone': 'Sandstone.png',
    'shale': 'Shale.png',
    'limestone': 'Limestone.png',
    'dolomite': 'Dolomite.png',
    'anhydrite': 'Anhydrite.png',
    'gypsum': 'Gypsum.png',
    # 岩盐/盐岩统一用 Halite.png（淡紫底黑 L 形），不用 Salt.png 的纯黑版
    'halite': 'Halite.png',
    'salt': 'Halite.png',
    # 火成岩用 Igneous rock.png（白底红棕人字）；火山岩另用 DBOS_Volcanic.png
    'igneous': 'Igneous rock.png',
    'igneous rock': 'Igneous rock.png',
    'volcanic': 'DBOS_Volcanic.png',
    'carbonate': 'Limestone.png',
    'mixed': 'Sandstone.png',
    'coal': 'Coal.png',
    'pyrite': 'Pyrite.png',
    'conglomerate': 'Conglomerate.png',
    # 碳质泥岩：DBOS 无专用图例，沿用泥岩符号，底色用深灰绿以区别于普通泥岩
    'carbonaceous_shale': 'Shale.png', '炭质泥岩': 'Shale.png',
    '碳质泥岩': 'Shale.png', '碳质页岩': 'Shale.png',
    'mudstone': 'Shale.png',
    # 套管段（2026-10-07 新增）：不是岩石，是工程井段。
    # DBOS 无套管符号，用 Unknown.png（斜线）表示，与真实岩性明确区分。
    'casing': 'Unknown.png', '套管': 'Unknown.png', '套管内': 'Unknown.png',
    # 中文名称
    '砂岩': 'Sandstone.png',
    '泥岩': 'Shale.png',
    '灰岩': 'Limestone.png',
    '白云岩': 'Dolomite.png',
    '硬石膏': 'Anhydrite.png',
    '石膏': 'Gypsum.png',
    '盐岩': 'Halite.png',
    '岩盐': 'Halite.png',
    '盐': 'Halite.png',
    '火成岩': 'Igneous rock.png',
    '火山岩': 'DBOS_Volcanic.png',
    '碳酸盐岩': 'Limestone.png',
    '煤': 'Coal.png',
    '煤层': 'Coal.png',
    '黄铁矿': 'Pyrite.png',
    '砾岩': 'Conglomerate.png',
    'unknown': 'Unknown.png',
}
# ======================================

# ========== 统一岩性符号绘制（岩性道 / profile道 / 图例 共用） ==========
# 2026-10-06 修正要点：
#   1) 图案在**物理空间**按固定英寸间距绘制，不随道宽/道高拉伸变形；
#   2) 砂岩 = 均匀错排圆点；泥岩 = 均匀水平短横线；灰岩/白云岩 = 砖砌线；煤 = 横线黑底；
#   3) 岩性道、profile道、图例方框全部走同一套函数，符号样式与密度完全一致。
LITH_PATTERN_PITCH_PX = 5.0       # 图案基本间距（像素，保证两道人字一致且不变形）
LITH_PATTERN_PITCH_PX_DASH = 9.0   # 泥岩/灰岩行距（像素）
LITH_DOT_MS = 1.0                  # 砂岩点直径（磅）
LITH_LINE_LW = 0.55                # 泥岩短线线宽（磅）
LITH_BRICK_LW = 0.45               # 灰岩砖线线宽（磅）
LITH_MAX_COLS = 400                # 单层最大点列数（防御上限）
LITH_MAX_ROWS = 800                # 单层最大点行数（防御上限）

# 岩性背景色（统一维护一份，避免各道各写一份导致不一致）
LITH_BG_COLORS = {
    'sandstone': '#FFFF00', 'shale': '#228B22', 'mudstone': '#228B22',
    '页岩': '#228B22', '泥岩': '#228B22', '泥页岩': '#228B22',
    'limestone': '#87CEEB', 'dolomite': '#B0E0E6', 'carbonate': '#87CEEB',
    '灰岩': '#87CEEB', '白云岩': '#B0E0E6', '碳酸盐岩': '#87CEEB',
    'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
    '硬石膏': '#FFC0CB', '石膏': '#FFC0CB',
    # 火成岩=淡蓝底（Igneous rock.png 原图是白底黑人字、仅 20% 不透明，
    # 纯白底上几乎看不见；给淡蓝底才能识别，且仍保持"冷色侵入岩"的观感）
    'igneous': '#E8F4F8', 'igneous rock': '#E8F4F8', '火成岩': '#E8F4F8',
    # 岩盐=淡紫底（Halite.png 原图即淡紫底黑 L 形，保持原图观感）
    'halite': '#C5C0F5', 'salt': '#C5C0F5',
    '岩盐': '#C5C0F5', '盐岩': '#C5C0F5', '盐': '#C5C0F5',
    'volcanic': '#90EE90', '火山岩': '#90EE90',
    'coal': '#000000', '煤': '#000000', '煤层': '#000000',   # 煤层按纯黑处理
    'pyrite': '#FFD700', '黄铁矿': '#FFD700',
    'conglomerate': '#FFFF99', '砾岩': '#FFFF99',   # 砾岩改黄底
    # 碳质泥岩：深灰绿（介于泥岩绿与煤黑之间，体现"含碳"）
    'carbonaceous_shale': '#3D5A3D', '炭质泥岩': '#3D5A3D',
    '碳质泥岩': '#3D5A3D', '碳质页岩': '#3D5A3D',
    # 套管段（2026-10-07 新增）：套管内测井反映泥浆/钢材，不是岩石，
    # 岩性识别会标为 casing。工程图例用**灰底红斜线**表示套管，
    # 与真实岩性明确区分，避免被误读成灰岩/泥岩。
    'casing': '#B0B0B0', '套管': '#B0B0B0', '套管内': '#B0B0B0',
    'mixed': '#D3D3D3', 'unknown': '#D3D3D3',
}

# profile 道矿物顺序：**泥岩固定在最左**（孔隙度因此只会在储层岩性里"开"出来，
# 不会在泥岩等非储层里出现），孔隙度在最右（留白区）。
PROFILE_MINERAL_ORDER = [
    (['VClay', 'VSH', 'VClayShale'], 'shale',     '泥岩', 'shale',     'dash'),
    (['VQuartz', 'VSAND'],            'sandstone', '砂岩', 'sandstone', 'dots'),
    (['VCalcite'],                    'limestone', '灰岩', 'limestone', 'brick'),
    (['VDolomite'],                   'dolomite',  '白云岩', 'dolomite', 'brick'),
    (['VHalite'],                     'halite',    '岩盐', 'halite',    'image'),
    (['VIgneous', 'VIgn'],            'igneous',   '火成岩', 'igneous', 'image'),
]

_SAND_NAMES = ('sandstone', '砂岩')
_SHALE_NAMES = ('shale', 'mudstone', '泥岩', '页岩', '泥页岩')
_LIME_NAMES = ('limestone', 'dolomite', 'carbonate', '灰岩', '白云岩', '碳酸盐岩')
_COAL_NAMES = ('coal', '煤', '煤层')

# 岩性英文/中文名 → 中文显示名（图例文字统一走这张表）
_LITH_CN_MAP = {
    'sandstone': '砂岩', 'sand': '砂岩', '砂岩': '砂岩',
    'shale': '泥岩', 'mudstone': '泥岩', '页岩': '页岩',
    '泥岩': '泥岩', '泥页岩': '泥页岩', 'claystone': '泥岩',
    'limestone': '灰岩', '灰岩': '灰岩',
    'dolomite': '白云岩', '白云岩': '白云岩',
    'carbonate': '灰岩', '碳酸盐岩': '碳酸盐岩', 'marl': '泥灰岩',
    'halite': '岩盐', 'salt': '岩盐', '岩盐': '岩盐', '盐岩': '盐岩', '盐': '盐',
    'igneous': '火成岩', 'igneous rock': '火成岩', '火成岩': '火成岩',
    'volcanic': '火山岩', '火山岩': '火山岩',
    'coal': '煤', '煤': '煤', '煤层': '煤',
    'conglomerate': '砾岩', '砾岩': '砾岩',
    'carbonaceous_shale': '碳质泥岩', '炭质泥岩': '碳质泥岩',
    'carbonaceous mudstone': '碳质泥岩', '碳质页岩': '碳质泥岩',
    'anhydrite': '硬石膏', '硬石膏': '硬石膏',
    'gypsum': '石膏', '石膏': '石膏',
    'pyrite': '黄铁矿', '黄铁矿': '黄铁矿',
    # 套管段（2026-10-07）：不是岩石，单独标注
    'casing': '套管', '套管': '套管', '套管内': '套管',
    'siltstone': '粉砂岩', '粉砂岩': '粉砂岩',
    'silt': '粉砂岩', 'mud': '泥岩',
}


def _lith_bg_color(lith_name):
    """按岩性取背景色，未知岩性用浅灰"""
    return LITH_BG_COLORS.get(str(lith_name).lower(), '#D3D3D3')


def _axes_data_per_px(ax):
    """返回 (x数据/像素, y数据/像素)；坐标轴未完成布局时返回 None。

    图案间距以像素定义，因此同一物理间距在岩性道与 profile道完全一致，
    且不随道宽/道高拉伸变形。
    """
    try:
        fig = ax.get_figure()
        pos = ax.get_position()
        dpi = float(fig.dpi) or 100.0
        w_px = pos.width * fig.get_figwidth() * dpi
        h_px = pos.height * fig.get_figheight() * dpi
        if w_px <= 1 or h_px <= 1:
            return None
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        if x1 == x0 or y1 == y0:
            return None
        return (x1 - x0) / w_px, (y1 - y0) / h_px
    except Exception:
        return None


def _lith_pattern_kind(lith_name):
    """岩性 → 图案类型。

    砂岩/泥岩用矢量点阵与短横线（用户已确认效果满意，密度可控、点恒为圆）；
    其余岩性一律回到 symbol 目录下的 DBOS 原图例（灰岩/白云岩为标准砖砌、
    岩盐为 L 形、火山岩为人字纹、盐岩与煤为纯黑），并按物理正方形平铺保证不变形。
    """
    name = str(lith_name).lower()
    if name in _SAND_NAMES:
        return 'dots'
    if name in _SHALE_NAMES:
        return 'dash'
    return 'image'


# 物理正方形平铺：单元边长（英寸）。1:200 下 0.20 in ≈ 5 mm，与 DBOS 图例习惯一致。
LITH_TILE_SIZE_IN = 0.20


def _tile_symbol_physical(ax, lith_name, z0, z1, x0, x1, zorder=10):
    """把 symbol 目录下的原图例按**物理正方形**平铺到任意道宽/任意深度区间。

    之前的问题：imshow(extent=[..., TILE_DEPTH_M], aspect='auto') 会把正方形图例
    拉成非正方形，砖砌图案被压成"一两根竖线"。这里先按像素把单元算成正方形
    （宽=高= LITH_TILE_SIZE_IN 英寸），再在水平与垂直方向双向平铺，边界处按比例裁剪。
    """
    img, _ = _load_lithology_symbol(str(lith_name).lower())
    if img is None:
        return False
    scale = _axes_data_per_px(ax)
    if scale is None:
        return False
    fig = ax.get_figure()
    dpi = float(getattr(fig, 'dpi', 100.0) or 100.0)
    x_per_in = abs(scale[0]) * dpi
    y_per_in = abs(scale[1]) * dpi
    if x_per_in <= 0 or y_per_in <= 0:
        return False
    tw = LITH_TILE_SIZE_IN * x_per_in      # 一个单元在 x 方向的数据跨度
    th = LITH_TILE_SIZE_IN * y_per_in      # 一个单元在 y 方向的数据跨度
    if tw <= 0 or th <= 0:
        return False

    try:
        from PIL import Image
        base = Image.fromarray((img * 255).astype(np.uint8)
                               if img.max() <= 1.0 else img.astype(np.uint8))
    except Exception:
        base = None

    n_rows = int(np.ceil((z1 - z0) / th)) + 2
    n_cols = int(np.ceil((x1 - x0) / tw)) + 2
    n_rows = max(1, min(n_rows, 4000))
    n_cols = max(1, min(n_cols, 400))
    tsz = 256
    # 网格对齐到全局基准（而不是段起点），保证同一段多次绘制/相邻段之间图案连续
    z_off = np.floor(z0 / th) * th
    x_off = np.floor(x0 / tw) * tw
    tile_full = None
    for r in range(-1, n_rows):
        za, zb = z_off + r * th, z_off + (r + 1) * th
        if zb <= z0:
            continue
        if za >= z1:
            break
        for c in range(-1, n_cols):
            xa, xb = x_off + c * tw, x_off + (c + 1) * tw
            if xb <= x0:
                continue
            if xa >= x1:
                break
            if base is None:
                ax.imshow(img, extent=[max(xa, x0), min(xb, x1), min(zb, z1), max(za, z0)],
                          aspect='auto', interpolation='nearest', clip_on=True,
                          zorder=zorder)
                continue
            if tile_full is None:
                tile_full = np.array(base.resize((tsz, tsz), Image.NEAREST)) / 255.0
            # 只取落在本段内的部分（按比例裁剪，图案不变形）
            cx0 = max(0.0, (x0 - xa) / tw)
            cx1 = min(1.0, (x1 - xa) / tw)
            cy0 = max(0.0, (z0 - za) / th)
            cy1 = min(1.0, (z1 - za) / th)
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            px0, px1 = int(tsz * cx0), max(int(tsz * cx1), int(tsz * cx0) + 1)
            py0, py1 = int(tsz * cy0), max(int(tsz * cy1), int(tsz * cy0) + 1)
            tile = tile_full[py0:py1, px0:px1, :]
            if tile.size:
                ax.imshow(tile, extent=[max(xa, x0), min(xb, x1), min(zb, z1), max(za, z0)],
                          aspect='auto', interpolation='nearest', clip_on=True,
                          zorder=zorder)
    return True


def _lith_pattern_points(ax, lith_name, z0, z1, x0, x1):
    """生成统一岩性符号的坐标点（按**像素**等间距，天然有界、不会拉伸变形）。

    返回 (kind, xs, ys)
    """
    kind = _lith_pattern_kind(lith_name)
    if kind == 'image':
        return kind, [], []
    scale = _axes_data_per_px(ax)
    x0d = max(x1 - x0, 1e-9)
    z0d = max(z1 - z0, 1e-9)
    if scale is None:
        # 退化情形：直接在数据空间取有限行列（最多 60×120），保证不会点位爆炸
        dx = x0d / 60.0
        dy = z0d / 120.0
    else:
        xpi, ypi = abs(scale[0]), abs(scale[1])   # 深度轴常反向(y1<y0)，取绝对值
        pitch = LITH_PATTERN_PITCH_PX if kind == 'dots' else LITH_PATTERN_PITCH_PX_DASH
        dx = max(pitch * xpi, x0d / LITH_MAX_COLS)
        dy = max(pitch * ypi, z0d / LITH_MAX_ROWS)
    n_rows = min(int(z0d / dy) + 1, LITH_MAX_ROWS)
    n_cols = min(int(x0d / dx) + 1, LITH_MAX_COLS)
    xs, ys = [], []
    if kind == 'dots':
        for r in range(n_rows):
            z = z0 + (r + 0.5) * dy
            if z > z1:
                break
            stagger = 0.5 if (r % 2) else 0.0
            for c in range(n_cols + 1):
                xv = x0 + (c + 0.5 + stagger) * dx
                if xv > x1:
                    break
                xs.append(xv)
                ys.append(z)
    elif kind == 'dash':
        for r in range(n_rows):
            z = z0 + (r + 0.5) * dy
            if z > z1:
                break
            for c in range(n_cols):
                xv = x0 + (c + 0.5) * dx
                xs.extend([xv - dx * 0.32, xv + dx * 0.32, np.nan])
                ys.extend([z, z, np.nan])
    elif kind == 'brick':
        for r in range(n_rows):
            z = z0 + (r + 0.5) * dy
            if z > z1:
                break
            xs.extend([x0 + 0.02 * (x1 - x0), x1 - 0.02 * (x1 - x0), np.nan])
            ys.extend([z, z, np.nan])
            xv = x0 + (0.34 if (r % 2) else 0.66) * (x1 - x0)
            xs.extend([xv, xv, np.nan])
            ys.extend([z, min(z + dy, z1), np.nan])
    else:  # coal
        for r in range(n_rows):
            z = z0 + (r + 0.5) * dy
            if z > z1:
                break
            xs.extend([x0 + 0.15 * (x1 - x0), x1 - 0.15 * (x1 - x0), np.nan])
            ys.extend([z, z, np.nan])
    return kind, xs, ys


def _plot_lith_points(ax, kind, xs, ys, zorder=10):
    if not len(xs):
        return
    if kind == 'dots':
        ax.plot(xs, ys, 'o', color='black', ms=LITH_DOT_MS, mew=0,
                linestyle='none', zorder=zorder)
    else:
        lw = LITH_BRICK_LW if kind == 'brick' else LITH_LINE_LW
        ax.plot(xs, ys, '-', color='black', lw=lw, zorder=zorder)


def _draw_track_legend_row(fig, bx, by, bw, bh, label, lith_key, color,
                          font_size=9, zorder=6000):
    """绘制一个道头图例条目（岩性道与 profile 道共用，保证两处完全一致）。

    布局（用户要求）：
      · 条目**横向铺满整个道宽**，竖向不留空隙、依次叠置；
      · 左侧一个**视觉正方形**符号块，垂直居中；
      · 文字在**整个条目内上下左右居中**；
      · 白色不透明底衬（zorder 5900）确保不被道内曲线穿透。
    """
    from matplotlib.lines import Line2D as _L2D
    # 白色底衬：zorder 高于所有曲线 artist，但低于符号与文字
    fig.add_artist(plt.Rectangle((bx, by), bw, bh, transform=fig.transFigure,
                                 facecolor='white', edgecolor='none',
                                 zorder=zorder - 100))
    fig.add_artist(plt.Rectangle((bx, by), bw, bh, transform=fig.transFigure,
                                 facecolor=color, edgecolor='k', lw=0.6,
                                 zorder=zorder))
    yc = by + bh / 2.0
    fw, fh = fig.get_figwidth(), fig.get_figheight()
    dpi = float(fig.dpi) or 100.0
    # 视觉正方形必须**在像素空间**是方的：综合图是极端长图（可到 24in × 150in），
    # figure 坐标是各向同性的，所以正确做法是
    #   ① 先用条目宽高（换算成像素）取一个正方形边长；
    #   ② 再把边长分别换算回 figure 坐标的 x 与 y。
    # 不能直接用 sq_w/sq_h = fw/fh 去同时约束两个方向——那会在长图上
    # 把符号压成几个像素宽的竖条。
    bw_px = bw * fw * dpi
    bh_px = bh * fh * dpi
    side = max(3.0, min(bh_px * 0.72, bw_px * 0.34))
    sq_w = side / (fw * dpi)
    sq_h = side / (fh * dpi)
    sq_x = bx + bw * 0.045
    sq_y = yc - sq_h / 2.0
    if lith_key:
        draw_lithology_pattern_fig(fig, lith_key, sq_x, sq_y, sq_w, sq_h,
                                   bg_color=None, zorder=zorder + 2)
    # 文字在整个条目内上下左右居中
    fig.text(bx + bw / 2.0, yc, label, fontsize=font_size, ha='center',
             va='center', fontfamily='Microsoft YaHei',
             transform=fig.transFigure, zorder=zorder + 3)


def _lith_cn_name(lith_name):
    """岩性英文名 → 中文名（图例文字用）"""
    return _LITH_CN_MAP.get(str(lith_name).lower(), str(lith_name).title())


def _lith_needs_frame(lith_name):
    """白底类岩性（岩盐/火成岩）图案极淡，需要画淡边框才看得见层界"""
    return str(lith_name).lower() in ('halite', 'salt', 'igneous', 'igneous rock',
                                      '岩盐', '盐岩', '盐', '火成岩')


def draw_lithology_pattern(ax, lith_name, z0, z1, x0=0.0, x1=None,
                           fill_bg=True, bg_color=None, zorder=10):
    """**统一**岩性符号绘制入口：岩性道、profile道、图例方框都调用本函数。

    参数
    ----
    ax : matplotlib Axes
    lith_name : 岩性名（英文小写或中文）
    z0, z1 : 深度区间（z0 小、z1 大）
    x0, x1 : 道内水平范围（数据坐标）
    fill_bg : 是否绘制背景色
    bg_color : 自定义背景色（profile道按矿物配色时传入）
    """
    if x1 is None:
        x1 = SYMBOL_X_EXTENT
    if (x1 - x0) <= 0 or (z1 - z0) <= 0:
        return
    name = str(lith_name).lower()
    if fill_bg:
        ax.fill_betweenx([z0, z1], x0, x1,
                         color=bg_color or _lith_bg_color(name),
                         alpha=0.95, zorder=zorder - 1)
    if _lith_needs_frame(name):
        # 白底淡纹（岩盐/火成岩）：补一条淡灰边框，避免图案几乎看不见
        ax.plot([x0, x0, x1, x1], [z0, z0, z1, z1], color='#9AA0A6',
                lw=0.5, zorder=zorder + 0.5)
    kind, xs, ys = _lith_pattern_points(ax, name, z0, z1, x0, x1)
    if kind == 'image':
        # 灰岩/白云岩/岩盐/火山岩/煤等：回到 symbol 目录原图例，按物理正方形平铺
        if not _tile_symbol_physical(ax, name, z0, z1, x0, x1, zorder=zorder):
            img, _ = _load_lithology_symbol(name)
            if img is None:
                return
            try:
                from PIL import Image
                img_pil = Image.fromarray((img * 255).astype(np.uint8)
                                          if img.max() <= 1.0 else img.astype(np.uint8))
                img_pil = img_pil.resize((SYMBOL_TILE_PX, SYMBOL_TILE_PX), Image.NEAREST)
                tile = np.array(img_pil) / 255.0
            except Exception:
                tile = img
            cur = z0
            while z1 - cur > 1e-6:
                remain = z1 - cur
                if remain >= TILE_DEPTH_M:
                    ax.imshow(tile, extent=[x0, x1, cur + TILE_DEPTH_M, cur],
                              aspect='auto', interpolation='nearest',
                              clip_on=True, zorder=zorder)
                    cur += TILE_DEPTH_M
                else:
                    frac = remain / TILE_DEPTH_M
                    crop = max(1, int(SYMBOL_TILE_PX * frac + 0.5))
                    ax.imshow(tile[:crop, :, :], extent=[x0, x1, z1, cur],
                              aspect='auto', interpolation='nearest',
                              clip_on=True, zorder=zorder)
                    break
        return
    _plot_lith_points(ax, kind, xs, ys, zorder=zorder)



def draw_lithology_pattern_fig(fig, lith_name, x0, y0, w, h,
                               bg_color=None, zorder=6002):
    """在图形坐标系(fig.transFigure)内绘制统一岩性符号——图例方框专用。

    与 draw_lithology_pattern 使用同一套符号定义（砂岩圆点/泥岩横线/灰岩砖/煤横线），
    点径与线宽仍以磅计，因此在图例小方框里同样是圆点、同样是均匀间距。
    """
    name = str(lith_name).lower()
    kind = _lith_pattern_kind(name)
    from matplotlib.lines import Line2D
    if bg_color is not None:
        fig.add_artist(plt.Rectangle((x0, y0), w, h, transform=fig.transFigure,
                                     facecolor=bg_color, edgecolor='black',
                                     lw=0.5, zorder=zorder - 1))
    if kind == 'dots':
        nx = max(1, int(round(w / 0.020)))
        ny = max(1, int(round(h / 0.020)))
        for r in range(ny):
            for c in range(nx):
                fig.add_artist(Line2D([x0 + (c + 0.5) * w / nx],
                                      [y0 + (r + 0.5) * h / ny],
                                      marker='o', color='black',
                                      markersize=LITH_DOT_MS,
                                      linestyle='none',
                                      transform=fig.transFigure, zorder=zorder))
    elif kind == 'dash':
        ny = max(1, int(round(h / 0.028)))
        for r in range(ny):
            yy = y0 + (r + 0.5) * h / ny
            fig.add_artist(Line2D([x0 + 0.12 * w, x0 + 0.88 * w], [yy, yy],
                                  color='black', lw=LITH_LINE_LW,
                                  transform=fig.transFigure, zorder=zorder))
    elif kind == 'brick':
        ny = max(1, int(round(h / 0.030)))
        for r in range(ny):
            yy = y0 + (r + 0.5) * h / ny
            fig.add_artist(Line2D([x0 + 0.02 * w, x0 + 0.98 * w], [yy, yy],
                                  color='black', lw=LITH_BRICK_LW,
                                  transform=fig.transFigure, zorder=zorder))
            xv = x0 + (0.34 if (r % 2) else 0.66) * w
            fig.add_artist(Line2D([xv, xv], [yy - h / (2 * ny), yy],
                                  color='black', lw=LITH_BRICK_LW,
                                  transform=fig.transFigure, zorder=zorder))
    elif kind == 'coal':
        ny = max(1, int(round(h / 0.028)))
        for r in range(ny):
            yy = y0 + (r + 0.5) * h / ny
            fig.add_artist(Line2D([x0 + 0.15 * w, x0 + 0.85 * w], [yy, yy],
                                  color='#5A5A5A', lw=LITH_LINE_LW,
                                  transform=fig.transFigure, zorder=zorder))
    else:
        # 其余岩性（灰岩/白云岩/岩盐/火成岩/砾岩…）：DBOS 原图例。
        # 不能用 fig.add_axes()（axes 永远画在 figure artist 之上，会盖住图例
        # 文字与边框，图例上方会冒出彩色竖条），也不能用 fig.figimage()
        # （图片在 figure artist 之后绘制，会把图案盖住）。
        # 这里把原图降采样成"马赛克"，用 figure 级 Rectangle 逐块绘制 ——
        # 与其它 figure artist 同一层级，zorder 正常生效。
        img, _ = _load_lithology_symbol(name)
        if img is not None:
            _draw_symbol_mosaic(fig, img, x0, y0, w, h, zorder)


def _draw_symbol_mosaic(fig, img, x0, y0, w, h, zorder=6002, max_side=26):
    """把岩性符号图降采样成马赛克，用 figure 级 Rectangle 绘制到给定矩形。

    目的：绕开 fig.add_axes()/fig.figimage() 的层级问题，让图例符号与图例
    边框、文字处在同一 zorder 体系里（Rectangle 可正常参与 zorder 排序）。
    图案本身已由 _recolor_symbol_background 统一过底色，这里只做形状还原。
    """
    try:
        buf = np.asarray(img)
        if buf.ndim == 2:
            buf = np.dstack([buf] * 3)
        buf = buf[:, :, :3]
        if buf.max() <= 1.0:
            buf = buf * 255.0
        H0, W0 = buf.shape[0], buf.shape[1]
        n = max(2, min(int(max_side), min(W0, H0)))
        # 保持宽高比：按目标框的比例决定每格像素数
        ar = (w * fig.get_figwidth()) / max(1e-9, (h * fig.get_figheight()))
        nx = max(2, min(n, int(round(n * max(ar, 1.0)))))
        ny = max(2, min(n, int(round(n / max(ar, 1.0)))))
        # 面积平均降采样（比最近邻取样更平滑，砖块/点阵仍可辨）
        ys = np.linspace(0, H0, ny + 1).astype(int)
        xs = np.linspace(0, W0, nx + 1).astype(int)
        cell_w = w / nx
        cell_h = h / ny
        for r in range(ny):
            y1, y2 = ys[r], max(ys[r] + 1, ys[r + 1])
            for c in range(nx):
                x1, x2 = xs[c], max(xs[c] + 1, xs[c + 1])
                patch = buf[y1:y2, x1:x2].reshape(-1, 3).mean(axis=0)
                col = tuple(int(round(v)) / 255.0 for v in patch)
                fig.add_artist(plt.Rectangle(
                    (x0 + c * cell_w, y0 + r * cell_h), cell_w, cell_h,
                    transform=fig.transFigure, facecolor=col,
                    edgecolor='none', linewidth=0, zorder=zorder))
    except Exception as _e:
        logger.warning(f'图例符号绘制失败: {_e}')


def _fig_imshow(fig, img, x0, y0, w, h, zorder=6002):
    """在 figure 坐标系里画一张岩性符号图，返回可参与 zorder 排序的 artist。

    matplotlib 里能放在 figure 坐标系又参与 zorder 排序的只有 figure 级
    artist（Rectangle / Line2D / Text / figimage）。而 fig.add_axes() 建出的
    axes 永远画在 figure artist 之上 —— 道头图例的符号方块用 add_axes 会盖住
    图例文字与边框（图例上方冒出一条彩色竖条），因此改用 Figure.figimage()。

    figimage 走的是 figure 的图片缓存（fig._get_draw_artists 单独处理），
    zorder 仍会被参考；这里把符号按目标像素预缩放，保证不变形。
    """
    from PIL import Image
    buf = np.asarray(img)
    if buf.ndim == 2:
        buf = np.dstack([buf] * 3)
    if buf.shape[2] == 4:
        buf = buf[:, :, :3]
    if buf.max() <= 1.0:
        buf = (buf * 255).astype(np.uint8)
    else:
        buf = buf.astype(np.uint8)
    fw, fh = fig.get_figwidth(), fig.get_figheight()
    dpi = fig.dpi
    px_w = max(1, int(round(w * fw * dpi)))
    px_h = max(1, int(round(h * fh * dpi)))
    pil = Image.fromarray(buf).resize((px_w, px_h), Image.NEAREST)
    arr = np.array(pil.convert('RGBA'), dtype=np.uint8, copy=True)
    # figimage 的 (xo, yo) 是像素坐标，原点取决于 origin；这里用像素坐标显式给出
    left = int(round(x0 * fw * dpi))
    bottom = int(round((fh - y0 - h) * fh * dpi))
    artist = fig.figimage(arr, xo=left, yo=bottom, origin='upper', zorder=zorder)
    return artist


# 兼容旧接口：统一走 draw_lithology_pattern
def _draw_lithology_tiles(ax, lith_name, seg_start_md, seg_end_md):
    """岩性道：统一符号（水平范围 0~SYMBOL_X_EXTENT）"""
    draw_lithology_pattern(ax, lith_name, seg_start_md, seg_end_md,
                           0.0, SYMBOL_X_EXTENT)


def _draw_lithology_tiles_profile(ax, lith_name, seg_start_md, seg_end_md):
    """profile道：与岩性道同一符号，仅水平范围占满整道"""
    draw_lithology_pattern(ax, lith_name, seg_start_md, seg_end_md, 0.0, 1.0)


def _draw_lithology_in_xrange(ax, lith_name, seg_start_md, seg_end_md, x_left, x_right):
    """在指定水平范围内绘制统一岩性符号"""
    draw_lithology_pattern(ax, lith_name, seg_start_md, seg_end_md, x_left, x_right)




# 岩性符号图案使用DBOS（中国石油行业标准）符号集，图案密度一致
# 每张符号图片在_resize_symbol_to_square中统一缩放到512×512


def _resize_symbol_to_square(img_array, target_size=SYMBOL_STANDARD_SIZE):
    """
    将符号图片统一标准化为正方形，所有图片大小和分辨率一致。
    
    所有符号图片已原生统一为 128×128，图案元素视觉密度完全一致。
    直接等比缩放到 target_size 填满画布，无需密度归一化。
    """
    try:
        from PIL import Image
        # numpy数组 → PIL Image
        if img_array.max() <= 1.0:
            img_pil = Image.fromarray((img_array * 255).astype(np.uint8))
        else:
            img_pil = Image.fromarray(img_array.astype(np.uint8))
        
        # 处理RGBA图片：转换为RGB+白色背景
        if img_pil.mode == 'RGBA':
            background = Image.new('RGBA', img_pil.size, (255, 255, 255, 255))
            img_pil = Image.alpha_composite(background, img_pil).convert('RGB')
        elif img_pil.mode != 'RGB':
            img_pil = img_pil.convert('RGB')
        
        # 等比缩放到 target_size，填满画布
        original_w, original_h = img_pil.size
        scale = target_size / max(original_w, original_h)
        new_w = max(1, int(original_w * scale))
        new_h = max(1, int(original_h * scale))
        img_pil = img_pil.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
        offset_x = (target_size - new_w) // 2
        offset_y = (target_size - new_h) // 2
        canvas.paste(img_pil, (offset_x, offset_y))
        
        # 所有图片填充率均为1.0（图案密度一致）
        fill_ratio = 1.0
        
        # 转回numpy数组（0-1范围，兼容matplotlib）
        return np.array(canvas) / 255.0, fill_ratio
    except Exception as e:
        logger.warning(f"标准化图片尺寸失败: {e}")
        return img_array, 1.0


def _border_connected_white(cand_mask, max_iter=512):
    """从图像四边界对 cand_mask 做连通泛洪，返回与边界连通的区域。

    用于把"符号图的底色"与"图案线"分开：只有与边界连通的底色才替换，
    图案线（哪怕颜色很浅）会保留。
    """
    try:
        h, w = cand_mask.shape
        reach = np.zeros_like(cand_mask, dtype=bool)
        # 多源 BFS：把四边界上的候选像素作为起点，逐轮向内扩散
        frontier = np.zeros_like(cand_mask, dtype=bool)
        frontier[0, :] = cand_mask[0, :]
        frontier[-1, :] = cand_mask[-1, :]
        frontier[:, 0] |= cand_mask[:, 0]
        frontier[:, -1] |= cand_mask[:, -1]
        reach |= frontier
        for _ in range(int(max_iter)):
            if not frontier.any():
                break
            nxt = np.zeros_like(reach)
            nxt[1:, :] |= frontier[:-1, :]
            nxt[:-1, :] |= frontier[1:, :]
            nxt[:, 1:] |= frontier[:, :-1]
            nxt[:, :-1] |= frontier[:, 1:]
            nxt &= cand_mask & ~reach
            if not nxt.any():
                break
            reach |= nxt
            frontier = nxt
        return reach if reach.any() else None
    except Exception:
        return None


def _recolor_symbol_background(img, bg_hex, tolerance=42, lith_name_hint=''):
    """把符号图的底色统一替换成 LITH_BG_COLORS 指定色，使同一岩性在
    岩性道 / profile道 / 图例里颜色完全一致。

    DBOS 原图例的底色是烤进图片里的（岩盐淡紫 #9A9CFA、砾岩亮绿 #00FF00…），
    而 RGBA 图在 _resize_symbol_to_square 里被合成到白底（透明→白），
    于是底色众数往往是白色。因此这里分两步处理：
      ① 若众数接近目标色 → 已一致，跳过；
      ② 否则把"接近原图主底色"和"接近白色/透明合成色"的像素一并替换为目标色，
         图案线（黑、红棕、青等）保持不变。
    """
    if img is None or img.ndim != 3 or img.shape[2] < 3:
        return img
    try:
        a = img[:, :, :3]
        rgb255 = np.array([int(bg_hex[1:3], 16), int(bg_hex[3:5], 16),
                           int(bg_hex[5:7], 16)], dtype=float) / 255.0
        if (np.abs(rgb255 - np.array([1.0, 1.0, 1.0])) < 0.02).all():
            return img                      # 目标就是白底，无需处理
        flat = a.reshape(-1, 3)
        # 量化到 5 bit 统计众数（抗 JPEG 噪声）；注意必须转 int32，
        # 否则 uint8 上做 // 与 *1024 会溢出（曾导致重着色静默失效）
        q = (flat * 255).astype(np.int32)
        keys = (q[:, 0] // 8) * 1024 + (q[:, 1] // 8) * 32 + (q[:, 2] // 8)
        vals, counts = np.unique(keys, return_counts=True)
        top = int(vals[int(np.argmax(counts))])
        dom = np.array([(top // 1024) * 8 + 4, ((top // 32) % 32) * 8 + 4,
                        (top % 32) * 8 + 4], dtype=float) / 255.0
        if (np.abs(dom - rgb255).max() < 0.06):
            return img                      # 底色已经一致
        white = np.array([1.0, 1.0, 1.0])
        d_dom = np.sqrt(((a - dom) ** 2).sum(axis=2))
        tol = float(tolerance) / 255.0
        if np.abs(dom - white).max() < 0.06:
            # 众数是白色（RGBA 透明区被合成成的白）：必须只替换**与边界连通的
            # 白色底色区**，不能按颜色全局替换，否则半透明图里的浅色图案线
            # 会被一起漂白（Igneous rock.png 的黑纹只占 20%）。
            bg_mask = _border_connected_white(d_dom < tol)
            if bg_mask is None or bg_mask.mean() < 0.05:
                return img
            out = img.copy()
            out[:, :, :3][bg_mask] = rgb255
            return out
        mask = d_dom < tol
        if mask.mean() < 0.05:
            return img
        out = img.copy()
        out[:, :, :3][mask] = rgb255
        return out
    except Exception as e:
        logger.warning(f"符号底色重着色失败({lith_name_hint}): {e}")
        return img


def _load_lithology_symbol(lith_name):
    """加载岩性符号图片（带缓存），返回 (numpy数组, fill_ratio) 或 (None, 1.0)"""
    if lith_name in _lithology_symbol_cache:
        return _lithology_symbol_cache[lith_name]

    symbol_file = LITHOLOGY_TO_SYMBOL.get(lith_name)
    if symbol_file:
        img_path = os.path.join(SYMBOL_DIR, symbol_file)
        if os.path.exists(img_path):
            try:
                img = plt.imread(img_path)
                # 标准化为统一正方形尺寸 + 图案密度归一化
                img, fill_ratio = _resize_symbol_to_square(img, SYMBOL_STANDARD_SIZE)
                # 底色统一到 LITH_BG_COLORS（仅图例型岩性需要）
                if _lith_pattern_kind(lith_name) == 'image':
                    img = _recolor_symbol_background(
                        img, _lith_bg_color(lith_name), lith_name_hint=lith_name)
                _lithology_symbol_cache[lith_name] = (img, fill_ratio)
                return img, fill_ratio
            except Exception as e:
                logger.warning(f"加载岩性符号图片失败 {img_path}: {e}")

    _lithology_symbol_cache[lith_name] = (None, 1.0)
    return None, 1.0


def _merge_thin_layers(segments, min_thickness=MIN_LAYER_THICKNESS_M):
    """
    将薄层（厚度 < min_thickness）合并到相邻大层，保持大层连续性。
    
    参数:
        segments: [(start_md, end_md, value), ...] 按深度排序的段列表
                  start_md < end_md（start是较浅=较小值，图上方）
        min_thickness: 最小层厚阈值（米）
    
    返回:
        合并后的段列表，薄层已吸收到相邻大层
    """
    if len(segments) <= 1:
        return segments
    
    # NonReservoir段作为分隔屏障，不参与合并
    BARRIER_VALUES = {'NonReservoir', 'Non-Reservoir'}

    merged = []
    i = 0
    while i < len(segments):
        start, end, val = segments[i]
        thickness = end - start

        # NonReservoir段始终保留，不参与合并
        if val in BARRIER_VALUES:
            merged.append((start, end, val))
            i += 1
            continue

        if thickness >= min_thickness:
            merged.append((start, end, val))
            i += 1
        else:
            # 薄层：比较左右邻居，合并到更厚的一方；等厚优先合并到上方
            # 不能合并到NonReservoir段（分隔屏障）
            prev_available = merged and merged[-1][2] not in BARRIER_VALUES
            prev_thick = merged[-1][1] - merged[-1][0] if prev_available else 0
            next_available = False
            next_thick = 0
            if i + 1 < len(segments):
                next_start, next_end, next_val = segments[i + 1]
                if next_val not in BARRIER_VALUES:
                    next_available = True
                    next_thick = next_end - next_start

            if prev_thick >= next_thick and prev_available:
                # 合并到上一个段（扩展上一个段的 end）
                prev_start, prev_end, prev_val = merged.pop()
                merged.append((prev_start, end, prev_val))
                i += 1
            elif next_available:
                # 合并到下一个段（扩展当前段到下一个段的 start，使用下一个段的值）
                i += 1  # 跳到下一个段
                next_start, next_end, next_val = segments[i]
                merged.append((start, next_end, next_val))
                i += 1
            else:
                # 两侧都是NonReservoir或无邻居，保留薄层
                merged.append((start, end, val))
                i += 1
    
    # 合并后可能产生新的相邻同值段，二次合并
    final = []
    for seg in merged:
        if final and final[-1][2] == seg[2]:
            final[-1] = (final[-1][0], seg[1], seg[2])
        else:
            final.append(seg)
    
    return final


plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'WenQuanYi Micro Hei']
plt.rcParams['font.family'] = ['sans-serif']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 12

HEADER_HEIGHT_CM = 7  # 基础值，将在代码中根据曲线数量动态调整
TITLE_LAS_GAP_CM = 1
LAS_HEADER_GAP_CM = 0.5
TITLE_HEIGHT_CM = 2

# 固定的刻度位置常量（从图头区底部向上的厘米数）
# 将在代码中根据每道实际曲线数量动态计算，确保所有道对齐
TICK_POSITIONS_CM = {
    'bottom': 0.8,      # 底部刻度位置（距底部0.8cm）
    'lower_middle': 2.3, # 下中部刻度位置（距底部2.3cm），与bottom间距1.5cm
    'upper_middle': 3.8, # 上中部刻度位置（距底部3.8cm），与lower_middle间距1.5cm
    'top': 5.2          # 顶部刻度位置（距底部5.2cm），与upper_middle间距1.4cm，距上框1.8cm
}


def _draw_legend_image(fig, x, y, symbol_size, img_array):
    """在图例中绘制纹理图片方块"""
    fig_w_inches = fig.get_figwidth()
    img_w_inches = img_array.shape[1] / 72.0
    target_w_inches = symbol_size * fig_w_inches
    zoom = target_w_inches / img_w_inches
    imagebox = OffsetImage(img_array, zoom=zoom, interpolation='bilinear')
    ab = AnnotationBbox(imagebox, (x + symbol_size / 2, y),
                       frameon=False, pad=0,
                       xycoords=fig.transFigure,
                       box_alignment=(0.5, 0.5))
    fig.add_artist(ab)


# LAS 原始曲线名 → 绘图标准名（LAS 用 CNCF/DTC 表示中子/声波、ZDEN 表示密度，
# 而绘图代码按 DT/DEN/CNL 找列，不做归一就会整条曲线缺失）
#
# 【重要修正 2026-10-07】CNCF 是**补偿中子**（孔隙度 PU），不是声波！
# 原映射写成 'CNCF': 'DT'，后果有两条：
#   1) 中子道（CNL）取不到列 → 绘图侧回退到被解释层段回填的 CNL → **平头**；
#   2) 声波道（DT）拿到的是中子值（20-30 PU），画出的"声波"其实是中子。
# 正确归属：声波 = DTC/DTCO/AC；中子 = CNCF/CNC/NPHI。
CURVE_ALIASES = {
    'DTC': 'DT', 'DTCO': 'DT', 'AC': 'DT',
    'CNCF': 'CNL', 'CNC': 'CNL', 'NPHI': 'CNL',
    'ZDEN': 'DEN', 'RHOB': 'DEN',
    'RD': 'RT',
    'CALY': 'CAL', 'CALX': 'CAL',
    'GR_XMAC': 'GRX',
}


def _normalize_curve_aliases(data):
    """把 LAS 原始曲线名归一到绘图标准名（已存在标准名时不覆盖）。"""
    try:
        out = data
        added = []
        for src, dst in CURVE_ALIASES.items():
            if src not in out.columns or dst in out.columns:
                continue
            v = pd.to_numeric(out[src], errors='coerce')
            if v.notna().sum() == 0:
                continue
            if out is data:
                out = data.copy()
            out[dst] = v
            added.append('%s→%s' % (src, dst))
        if added:
            logger.info('曲线名归一: ' + ', '.join(added))
        return out
    except Exception as e:
        logger.warning(f'曲线名归一失败: {e}')
        return data


def _flat_run_ratio(values, min_run=8):
    """统计"连续相同值"的最长run长度占比，用于判断曲线是否被层段回填成常量。

    返回 (最长平头点数, 平头段数)。原始 0.25ft 采样曲线不会有长平头；
    而按解释层段回填的列会出现几十上百点的平头。
    """
    try:
        v = np.asarray(values, dtype=float)
    except Exception:
        return 0, 0
    finite = ~np.isnan(v)
    if finite.sum() < min_run * 2:
        return 0, 0
    longest, runs, cur = 0, 0, 1
    for i in range(1, len(v)):
        if finite[i] and finite[i - 1] and abs(v[i] - v[i - 1]) < 1e-9:
            cur += 1
        else:
            if cur >= min_run:
                runs += 1
                longest = max(longest, cur)
            cur = 1
    if cur >= min_run:
        runs += 1
        longest = max(longest, cur)
    return longest, runs


def _prefer_raw_curve_columns(data, curve_names, min_run=8):
    """为每个曲线名挑选"原始采样"版本，避免综合图上出现"一段曲线一个值"的平头。

    背景：解释程序（SLAM 等）会把解释层段均值回填到 GR/CNL/DEN 等列
    （实测 BET-1：GR 主列有 23 段平头、最长 98 点，而 GR_LAS 列 0 段），
    于是综合图上出现平头。原始 LAS 采样（0.25 ft）是连续点云、没有平头。

    做法：比较 XXX 与 XXX_LAS 的平头程度，原始列明显更好就用它覆盖主列名；
    两者接近时保持原列（避免误判真实台阶式曲线，如 CAL 的 8.7 in 台阶）。
    原地修改并返回同一 DataFrame。
    """
    replaced = []
    for name in curve_names:
        raw = name + '_LAS'
        if name not in data.columns or raw not in data.columns:
            continue
        # 注意：pandas 的 .values 常返回**只读**视图，直接 data[name] = v_raw
        # 会被静默跳过（不报错、也不生效）。必须用 .to_numpy(copy=True) 或
        # 走 loc 赋值，否则会出现"日志说替换了、实际没换"的假象。
        v_main = pd.to_numeric(data[name], errors='coerce').to_numpy(copy=True)
        v_raw = pd.to_numeric(data[raw], errors='coerce').to_numpy(copy=True)
        # 有效性检查：原始列必须有有效数据；主列若全为 NaN 也没有比较意义
        # （注意判断方向：这里要的是"主列有有效值"，写成 not ...any() 会把
        #   "没有 NaN" 误判成 True 而错误跳过整列）
        if np.isnan(v_raw).all() or np.isnan(v_main).all():
            continue
        lm = _flat_run_ratio(v_main, min_run)[0]
        lr = _flat_run_ratio(v_raw, min_run)[0]
        if lr < lm:
            # 用新的 Series 整体替换该列（不能用只读的 .values 赋值，
            # 也不能用 loc[:, name] —— 二者在只读视图下都会静默失效）
            data[name] = pd.Series(v_raw, index=data.index, dtype='float64')
            replaced.append('%s(%d->%d)' % (name, lm, lr))
    if replaced:
        logger.info('采用原始LAS曲线列: %s', ', '.join(replaced))
    return data

def _clean_sentinel_values(data, curve_names=None):
    """把测井哨兵值（-999.25 等"未测量"占位值）转为 NaN。

    背景
    ----
    LAS 用 -999.25 / -999.99 等哨兵值表示"该深度未测量"。若不处理，
    matplotlib 会把这些点连成一条**水平线**，看上去就是"平头"。
    实测 TrakesKE-1 的浅段 29.8-584.8 m（5551 点）NPHI/DT/RHOB/PEF
    全部为 -999.25 —— 这段"平头"是**源数据的未测段**，不是层段回填。

    处理为 NaN 后，绘图曲线会在此自然断开，既符合物理，
    也不会把无效段误画成一条水平直线。
    """
    try:
        sentinels = [-999.25, -999.9, -999.99, -9999, -9999.0, -9999.9,
                      -9999.99, -99999, -99999.0, -999, -999.0,
                      -888.88, -888, -888.0, -777.77, -777, -777.0]
        if curve_names is None:
            curve_names = [c for c in data.columns
                           if pd.api.types.is_numeric_dtype(data[c])]
        cleaned = []
        for c in curve_names:
            if c not in data.columns:
                continue
            try:
                v = pd.to_numeric(data[c], errors='coerce')
            except Exception:
                continue
            if v.notna().sum() == 0:
                continue
            mask = pd.Series(False, index=data.index)
            for sv in sentinels:
                mask = mask | (np.isclose(v, sv, atol=1e-4))
            n = int(mask.sum())
            if n == 0:
                continue
            if v is data[c]:
                v = v.copy()
            v[mask] = np.nan
            data[c] = v
            cleaned.append('%s(%d)' % (c, n))
        if cleaned:
            logger.info('哨兵值(-999.25等)已置为NaN: %s', ', '.join(cleaned))
        return data
    except Exception as e:
        logger.warning(f'哨兵值清洗失败: {e}')
        return data


def _recover_flat_curves(data, min_run=40, depth_col='MD'):
    """兜底修复"层段回填造成的平头"—— 仅在存在**同量纲**替代列时生效。

    背景
    ----
    `_prefer_raw_curve_columns` 依赖解释程序同时保存 `XXX` 与 `XXX_LAS`。
    部分井没有 `XXX_LAS` 列，若曲线已被按层段回填就会出现长平头。

    重要修正（2026-10-07）
    ----------------------
    首版实现把 NPHI（中子，量程 0-100 v/v 或 0-60 PU）替换成
    `PHI_CNL_SHALE`（小数孔隙度 0-1 v/v），**量纲完全不同**，会把中子道
    画成 0.15-0.40 的平缓线而彻底失真；且实测发现 TrakesKE-1 等井的
    "5551 点平头"其实是 LAS 原生的 -999.25 未测段，由 `_clean_sentinel_values`
    处理即可，不需要也不应该替换曲线。

    因此这里的替代列只允许**同一物理量、同一量纲**，
    且要求替代列本身不是哨兵值主导。
    """
    try:
        # 替代列候选：必须是同一物理量、同一量纲
        equiv = {
            'NPHI': ['NPHI_LAS', 'CNCF', 'CNC', 'CNL_LAS', 'CNL'],
            'CNL':  ['CNL_LAS', 'CNCF', 'CNC', 'NPHI_LAS'],
            'DT':   ['DT_LAS', 'DTCO', 'DTC', 'AC'],
            'RHOB': ['RHOB_LAS', 'ZDEN', 'DEN_LAS'],
            'DEN':  ['DEN_LAS', 'ZDEN'],
            'GR':   ['GR_LAS', 'GRX', 'SGR', 'CGR'],
            'MSFL': ['MSFL_LAS', 'MSFL_corrected'],
            'PEF':  ['PE_LAS'],
        }
        fixed = []
        for name, cands in equiv.items():
            if name not in data.columns:
                continue
            v = pd.to_numeric(data[name], errors='coerce')
            # 先排除哨兵值主导的列：那是"未测段"，不是回填，不该替换
            if v.notna().sum() < 50:
                continue
            longest, _runs = _flat_run_ratio(v.values, min_run)
            n_valid = int(v.notna().sum())
            if longest < min_run or longest < n_valid * 0.25:
                continue
            for cand in cands:
                if cand == name or cand not in data.columns:
                    continue
                vr = pd.to_numeric(data[cand], errors='coerce')
                if vr.notna().sum() < n_valid * 0.5:
                    continue
                lr = _flat_run_ratio(vr.values, min_run)[0]
                if lr >= longest:
                    continue
                data[name] = vr
                fixed.append('%s(%d->%d,取自%s)' % (name, longest, lr, cand))
                break
        if fixed:
            logger.info('平头曲线已用同量纲原始列还原: %s', ', '.join(fixed))
        return data
    except Exception as e:
        logger.warning(f'平头兜底修复失败: {e}')
        return data


def _mask_constant_segments(data, depth_col='MD', min_run=60, min_frac=0.85,
                            max_loss=0.05):
    """把"多曲线同时恒定"的常值段置 NaN（未测段/停测段的伪平头）。

    背景
    ----
    实测残留的长平头分三类，全部是**源数据的未测/停测段**：
      · 井口浅段：XIMENIA-5 的 NPHI/DT/RHOB/PEF/MSFL/SP 在 27-335 m
        同时恒定 3078 点（整段未测量）；
      · 井中孤立段：Delo 4 的 NPHI/RHOB/PEF 在 1723-1732 m 同时恒定；
      · 井底尾部：Delo 4 2757-2775 m、XIMENIA-5 2836-2849 m。

    为什么必须用"多曲线同时恒定"判定
    --------------------------------
    单条曲线的常值段在真实地层中也存在（致密夹层、极慢速层），
    直接置 NaN 会误删有效解释。**多条独立测井曲线在同一深度段
    同时完全不变**在物理上几乎不可能——那只能是仪器停测或无测值。

    安全阀 `max_loss`（关键）
    ------------------------
    某些井（如 3-SPS-111D）的原始曲线本身就被解释程序按层段回填过，
    大量深度段本就"多曲线同时恒定"。若不设上限，会把**整口井的
    真实解释数据全部抹掉**（实测曾损失 68% 的有效点）。
    因此若置 NaN 的点超过全井 `max_loss`，说明这是回填而非未测段，
    **放弃处理**，把数据原样返回。
    """
    try:
        if depth_col not in data.columns:
            return data
        n = len(data)
        if n < min_run * 3:
            return data
        # 只考虑独立的**原始测井曲线**（派生列如 SW/VSH 天然分层，
        # 参与统计会误判）
        raw_names = ('GR', 'GRX', 'SGR', 'CGR', 'DEN', 'ZDEN', 'RHOB',
                     'RHOB_corrected', 'NPHI', 'CNL', 'CNCF', 'CNC',
                     'DT', 'DTC', 'DTCO', 'AC', 'PEF', 'PE',
                     'SP', 'CAL', 'CALS', 'CALX', 'CALY',
                     'RT', 'RD', 'LLD', 'ILD', 'RMSL', 'MSFL', 'RS')
        curves = [c for c in data.columns
                  if c in raw_names and c != depth_col]
        if len(curves) < 4:
            return data

        # 逐曲线标记常值段（游程编码，向量化）
        flat_mask = np.zeros((len(curves), n), dtype=bool)
        for k, c in enumerate(curves):
            v = pd.to_numeric(data[c], errors='coerce').astype('float64').values
            if np.isnan(v).all():
                continue
            same = np.zeros(n, dtype=bool)
            if n > 1:
                both_nan = np.isnan(v[1:]) & np.isnan(v[:-1])
                finite = (~np.isnan(v[1:])) & (~np.isnan(v[:-1]))
                close = np.isclose(v[1:], v[:-1], rtol=0, atol=1e-9)
                same[1:] = both_nan | (finite & close)
            run = np.zeros(n, dtype=int)
            run[0] = 1
            for i in range(1, n):
                run[i] = run[i - 1] + 1 if same[i] else 1
            flat_mask[k] = run >= min_run

        # 每点被多少条曲线判为常值
        cover = flat_mask.sum(axis=0)
        need = max(4, int(len(curves) * min_frac))
        bad = cover >= need
        if not bad.any():
            return data
        # 安全阀：损失过大说明这是"层段回填"而非"未测段"，放弃处理
        loss = bad.sum() / n
        if loss > max_loss:
            logger.info('常值段覆盖 %.1f%% > 上限 %.0f%%，判定为层段回填而非未测段，'
                        '跳过置NaN（保留原始数据）', loss * 100, max_loss * 100)
            return data
        out = data.copy()
        touched = []
        for k, c in enumerate(curves):
            if not flat_mask[k].any():
                continue
            nv = pd.to_numeric(out[c], errors='coerce').astype('float64').copy()
            nv[bad] = np.nan
            out[c] = nv
            touched.append(c)
        logger.info('多曲线常值段(未测/停测)已置NaN: %d点(%.1f%%), 涉及%d条曲线 %s',
                    int(bad.sum()), loss * 100, len(touched), ','.join(touched[:10]))
        return out
    except Exception as e:
        logger.warning(f'常值段处理失败: {e}')
        return data


def _trim_tail_constant(data, depth_col='MD', min_run=40, max_frac=0.02):
    """把井底尾部各曲线的常值段置为 NaN（重复回次 / 仪器停测造成的伪平头）。

    背景
    ----
    实测 Delo 4 井底各曲线的停测位置**互不相同**：
      SP 常值 262 点（2748.9m 起）、GR 210 点、NPHI 178 点、
      CALS/RHOB/PEF 115 点、LLD 54 点、DT 19 点。
    这些是重复回次或仪器停测的真实数据状态，不是层段回填，
    但画在图上就是一条水平线，观感上是"平头"。

    做法
    ----
    对每条曲线**独立**判断：若从井底末端回溯的连续常值长度超过
    `min_run`（且该段不超全井 `max_frac`），就把这些点置 NaN，
    曲线在井底自然断开。

    为什么置 NaN 而不是裁掉整段
    --------------------------
    各曲线停测起点不同（262/210/178/115/54/19 点），
    若按"最早的起点"裁整段，会把其他曲线仍有效的数据也删掉；
    若按"最晚的起点"裁，则裁不掉什么。逐曲线置 NaN 才是对的。
    """
    try:
        if depth_col not in data.columns:
            return data
        n = len(data)
        if n < min_run * 3:
            return data
        out = data
        touched = []
        for c in data.columns:
            if c == depth_col or not pd.api.types.is_numeric_dtype(data[c]):
                continue
            v = pd.to_numeric(data[c], errors='coerce').astype('float64')
            arr = v.values
            if np.isnan(arr).all():
                continue
            same = np.zeros(n, dtype=bool)
            if n > 1:
                both_nan = np.isnan(arr[1:]) & np.isnan(arr[:-1])
                finite = (~np.isnan(arr[1:])) & (~np.isnan(arr[:-1]))
                close = np.isclose(arr[1:], arr[:-1], rtol=0, atol=1e-9)
                same[1:] = both_nan | (finite & close)
            idx_nz = np.flatnonzero(~same[:n - 1])
            run_len = (n - 1 - idx_nz[-1]) if len(idx_nz) else (n - 1)
            if run_len < min_run:
                continue
            # 常值段过长（超过全井 max_frac）说明不是井底停测，而是
            # 真实的层段回填/致密夹层，不在这里动（交给 _recover_flat_curves）
            if run_len > n * max_frac:
                continue
            if out is data:
                out = data.copy()
            nv = v.copy()
            nv.iloc[n - run_len:] = np.nan
            out[c] = nv.astype('float64')
            touched.append('%s(%d)' % (c, run_len))
        if touched:
            logger.info('井底常值段已置NaN: %s', ', '.join(touched))
        return out
    except Exception as e:
        logger.warning(f'井底常值段处理失败: {e}')
        return data


def _sample_step(data, depth_col='MD'):
    """返回深度采样间隔（数据单位：ft 或 m），取众数。

    用于按采样分辨率反推所需图高：若"每像素代表的深度 > 采样间隔"，
    matplotlib 只能每像素取一个代表值，曲线会被画成平头。
    """
    try:
        d = pd.to_numeric(data[depth_col], errors='coerce').dropna().values
        if len(d) < 3:
            return None
        diffs = np.abs(np.diff(d))
        # 注意：不能只用 `diffs < p99` 过滤 —— 当采样完全等间隔（如恒为 0.25 ft）时
        # p99 就等于 0.25，会把所有点都排掉。改为用「上界 = 中位数的 3 倍」
        # 剔除个别跳段（重采样/重复点），其余全部保留。
        med = float(np.median(diffs[diffs > 0])) if (diffs > 0).any() else 0.0
        if med <= 0:
            return None
        good = diffs[(diffs > 0) & (diffs <= med * 3.0)]
        if len(good) == 0:
            return med
        return float(np.median(good))
    except Exception:
        return None


def visualize_composite_log(data, results, gas_data=None, depth_unit=None):
    """可视化综合测井图，可选气测数据道

    Args:
        data: 主测井数据 DataFrame，必须包含MD列
        results: 结果字典，包含 well_name, output_dir, las_info 等
        gas_data: 可选的气测数据 DataFrame，包含MD和气体组分列（如TG, C1, C2等）
        depth_unit: 深度单位 'ft'/'m'；None 时按 results['depth_unit'] →
            全局 set_depth_unit() → 按深度值域自动判定
    """
    if data is None:
        logger.error("数据未加载")
        return None

    try:
        if 'MD' not in data.columns:
            logger.error("数据中缺少Depth列 'MD'")
            return None

        # ========== 深度单位：显式传入 > results > las_info > 全局 > 值域判定 ==========
        # 不修这里会导致英尺井的道头标成 "Depth (m)"、刻度间隔也按米取整。
        if depth_unit is None and isinstance(results, dict):
            depth_unit = results.get('depth_unit')
        if depth_unit is None:
            depth_unit = getattr(results, 'depth_unit', None)
        if depth_unit is None and isinstance(results, dict):
            # LAS ~C 区深度曲线的单位（如 DEPT.FEET / DEPT.M），最权威
            _li = results.get('las_info') or {}
            if isinstance(_li, dict):
                depth_unit = (_li.get('depth_unit')
                              or _li.get('well', {}).get('depth_unit')
                              if isinstance(_li.get('well'), dict) else None)
        if depth_unit is not None:
            u = str(depth_unit).strip().lower()
            if u in ('ft', 'feet', 'feet'):
                depth_unit = 'ft'
            elif u in ('m', 'meter', 'meters', 'metre', 'metres'):
                depth_unit = 'm'
            else:
                depth_unit = None
        if depth_unit:
            set_depth_unit(depth_unit)

        data = data.sort_values('MD').reset_index(drop=True)
        if len(data) == 0:
            logger.error("数据为空")
            return None
        
        depth = data['MD']

        # 气测单位自动归一：TGAS 为 unit 时 ×200 = ppm（印尼惯例，量级守卫防重复换算）
        if gas_data is not None and 'TGAS' in gas_data.columns:
            _tg = pd.to_numeric(gas_data['TGAS'], errors='coerce')
            if _tg.notna().any() and 0 < _tg.median() < 1000:
                gas_data = gas_data.copy()
                gas_data['TGAS'] = _tg * 200.0
                logger.info('气测 TGAS 按 unit×200 换算为 ppm')
        
        # 定义有效曲线列表（原始测井曲线，不包括计算出来的曲线如Sw、VSH等）
        # 10条曲线：CAL, SP, GR, 3条电阻率, 4条孔隙度
        # 添加阵列感应曲线：AT10-AT90（阵列感应）、M2R1-M2RX（多阵列感应）
        raw_curves = ['CAL', 'CALX', 'CALY', 'SP', 'GR', 'GR_XMAC', 'RT', 'RD',
                      'LLD', 'ILD', 'R90', 'MSFL', 'LLS',
                      'AT10', 'AT20', 'AT30', 'AT60', 'AT90',
                      'M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX',
                      'DEN', 'ZDEN', 'RHOB', 'NPHI', 'CNL', 'CNCF',
                      'DT', 'DTC', 'DTCO', 'AC', 'PE']

        # ========== 关键：优先使用原始 LAS 曲线列 ==========
        # 【第0步】哨兵值清洗：LAS 用 -999.25 表示"该深度未测量"。
        #   不处理的话 matplotlib 会把这些点连成水平线，视觉上就是"平头"。
        #   实测 TrakesKE-1 浅段 29.8-584.8m（5551 点）NPHI/DT/RHOB/PEF
        #   全为 -999.25 —— 那是未测段，不是回填。置 NaN 后曲线自然断开。
        # ========== 【第0.2步】岩性列归一 ==========
        # 解释程序有两条岩性链路：
        #   LITHOLOGY      —— 老链路（SegmentClassifier 逐点最小二乘/交汇图），
        #                     只区分砂/泥/碳酸盐，**不认识煤、碳质泥岩、岩盐**；
        #   LITHOLOGY_MC   —— 新多判据一致性链路（must/core/deny），
        #                     才能识别煤、碳质泥岩等特殊岩性。
        # 绘图道读的是 LITHOLOGY，于是煤层/碳质泥岩在综合图上
        # 全部显示成泥岩（实测 BET-1：煤 87 点 → shale 53/sandstone 34，
        # 碳质泥岩 474 点 → shale 471）。这里把多判据结果作为唯一口径，
        # 覆盖到 LITHOLOGY，保证图/表/报告三者一致。
        if 'LITHOLOGY_MC' in data.columns:
            _mc = data['LITHOLOGY_MC'].astype(str).str.strip().str.lower()
            _ol = (data['LITHOLOGY'].astype(str).str.strip().str.lower()
                   if 'LITHOLOGY' in data.columns else pd.Series('', index=data.index))
            # 仅在多判据给出**具体岩性**时覆盖；套管段沿用已有的 casing 标记
            _override = _mc.isin(set(LITH_BG_COLORS.keys()) - {'mixed', 'unknown'})
            if 'LITHOLOGY' not in data.columns:
                data['LITHOLOGY'] = _mc
            else:
                data.loc[_override, 'LITHOLOGY'] = _mc[_override]
            _changed = int((_override &
                            (_ol != _mc)).sum())
            if _changed:
                logger.info('岩性道已统一为多判据结果(LITHOLOGY_MC): '
                            '%d 点覆盖原判定', _changed)

        data = _clean_sentinel_values(data)
        # 【第0.5步】多曲线同时恒定的段 = 未测段/停测段（伪平头）。
        #   必须是"多条独立曲线同时不变"才判定 —— 单条曲线恒值在真实
        #   地层中也存在（致密夹层），不能一刀切。
        #   实测可处理三类残留：井口浅段（XIMENIA-5 27-335m 全部未测）、
        #   井中孤立段（Delo 4 1723-1732m）、井底尾部（Delo 4 2757-2775m）。
        data = _mask_constant_segments(data)
        # 解释程序（如 SLAM）输出的结果里，GR/CNL/DEN 等列会被**按解释层段
        # 回填层段均值**，导致综合图上出现"一段曲线是一个值"的平头
        #（原始 LAS 采样是 0.25ft，点云连续，不会有平头）。
        # 而同表里的 *_LAS 列保存的是未经回填的原始曲线。
        # 因此这里为每个曲线名挑选"最接近原始采样"的那一列。
        data = _prefer_raw_curve_columns(data, raw_curves)
        # 别名归一：LAS 原始名（CNCF/ZDEN/RD…）统一到绘图用标准名，
        # 否则声波等曲线会因为名字对不上而整条缺失。
        data = _normalize_curve_aliases(data)
        # 中子道优选：解释程序常把 NPHI/CNL 按解释层段回填成层段均值，
        # 绘图侧若直接读回填列就会出现"一段曲线一个值"的平头。
        # LAS 里的原始中子列名是 CNCF（补偿中子），上面的别名归一已把它
        # 汇入 CNL；这里再对 NPHI/CNC/CNL 三个名字统一挑一次原始版本。
        data = _prefer_raw_curve_columns(data, ['NPHI', 'CNC', 'CNL'])
        # CNL 已经取到原始中子后，同步给 NPHI，使第3道优先读的 NPHI
        # 拿到的是原始采样而不是层段回填值（否则中子道平头依旧）
        if 'CNL' in data.columns and 'NPHI' not in data.columns:
            data['NPHI'] = data['CNL']
        # 兜底：若某些井的输出里根本没有 XXX_LAS 原始列，曲线已被解释流程
        # 按层段回填成均值（实测 NPHI 最长平头 5551 点），此时用同物理量的
        # 计算列（PHI_CNL_SHALE / RHOB_corrected 等）还原曲线形态。
        data = _recover_flat_curves(data)
        
        # 找到有有效曲线的深度范围
        # 顶部：从第一条有有效曲线的深度开始
        # 底部：到最后一条有有效曲线的深度截止
        # 如果某段深度所有10条曲线的值都无效（NaN或超出合理范围），则不绘制这段区域
        
        # 获取数据中实际可用的曲线
        available_curves = [curve for curve in raw_curves if curve in data.columns]
        
        # 使用数据的实际深度范围，不进行有效曲线过滤
        # 确保完整绘制所有数据，不因为有效曲线判断而裁剪
        actual_first_depth = data['MD'].iloc[0]
        actual_last_depth = data['MD'].iloc[-1]
        
        # 深度刻度显示范围：向下取整到整十米（顶部），向上取整到整十米（底部）
        depth_min = ((int(actual_first_depth) // 10) * 10)
        depth_max = ((int(actual_last_depth) + 9) // 10) * 10
            
        depth_range = depth_max - depth_min
        
        if depth_range <= 0:
            logger.error("Depth范围无效")
            return None
        
        # logger.info(f"深度范围: {depth_min:.1f}m - {depth_max:.1f}m")
        # logger.info(f"实际数据深度范围: {data['MD'].min():.1f}m - {data['MD'].max():.1f}m")
        # logger.info(f"总数据点数: {len(data)}")
        # logger.info(f"可用曲线: {available_curves}")
        
        # 检查数据第一行和最后一行（调试用）
        # logger.info(f"第一行数据: MD={data['MD'].iloc[0]:.1f}")
        # for curve in available_curves[:5]:
        #     if curve in data.columns:
        #         logger.info(f"  {curve}={data[curve].iloc[0]}")
        # logger.info(f"最后一行数据: MD={data['MD'].iloc[-1]:.1f}")
        # for curve in available_curves[:5]:
        #     if curve in data.columns:
        #         logger.info(f"  {curve}={data[curve].iloc[-1]}")
        
        # 检查曲线数据和深度数据的长度（调试用）
        # for curve in available_curves:
        #     if curve in data.columns:
        #         curve_len = len(data[curve])
        #         depth_len = len(depth)
        #         if curve_len != depth_len:
        #             logger.warning(f"曲线 {curve} 长度({curve_len})与深度长度({depth_len})不一致")
        #         # 检查曲线数据的有效范围
        #         valid_data = data[curve].dropna()
        #         if len(valid_data) > 0:
        #             logger.info(f"  {curve}: min={valid_data.min():.2f}, max={valid_data.max():.2f}, valid_count={len(valid_data)}")
        
        valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'MSFL', 'LLS',
                  'AT10', 'AT20', 'AT30', 'AT60', 'AT90',
                  'M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX',
                  'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC', 'PE', 'PEF', 'CAL', 'CALS', 'CALI']
        available_curves = [curve for curve in valid_curves if curve in data.columns]
        has_enough_curves = len(available_curves) >= 2
        
        # ========== 预识别电阻率曲线和BS曲线（用于动态计算图头区高度和对齐刻度线） ==========
        traditional_res = {
            'MSFL': ['MSFL', 'RMSL'],
            'LLS': ['LLS', 'RS'],
            'LLD': ['LLD', 'RD', 'RT', 'ILD', 'R90']
        }
        
        array_res_at = {
            'MSFL': ['AT10'],
            'LLS': ['AT30'],
            'LLD': ['AT90', 'AT60']
        }
        
        array_res_m2r = {
            'MSFL': ['M2R1'],
            'LLS': ['M2R3'],
            'LLD': ['M2RX', 'M2R6']
        }
        
        def find_res_column_pre(res_type):
            for col in traditional_res[res_type]:
                if col in data.columns:
                    return col
            for col in array_res_at[res_type]:
                if col in data.columns:
                    return col
            for col in array_res_m2r[res_type]:
                if col in data.columns:
                    return col
            return None
        
        msfl_col = find_res_column_pre('MSFL')
        lls_col = find_res_column_pre('LLS')
        lld_col = find_res_column_pre('LLD')
        
        resistivity_cols_pre = []
        has_traditional_pre = False
        
        if msfl_col:
            resistivity_cols_pre.append(msfl_col)
            has_traditional_pre = True
        if lls_col and lls_col != msfl_col:
            resistivity_cols_pre.append(lls_col)
            has_traditional_pre = True
        if lld_col and lld_col not in resistivity_cols_pre:
            resistivity_cols_pre.append(lld_col)
            has_traditional_pre = True
        
        # 如果没有找到传统曲线，查找所有可用的阵列感应曲线（绘制全部）
        if not resistivity_cols_pre:
            array_curves = []
            for col in ['AT10', 'AT20', 'AT30', 'AT60', 'AT90']:
                if col in data.columns:
                    array_curves.append(col)
            if not array_curves:
                for col in ['M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX']:
                    if col in data.columns:
                        array_curves.append(col)
            resistivity_cols_pre = array_curves
        
        n_res_curves = len(resistivity_cols_pre)
        
        # 检查是否有BS曲线
        has_bs = _find_column(data, ['BS', 'BIT', 'BITSIZE', 'BIT_SIZE', 'BSIZE', 'DRILL_BIT']) is not None
        
        # ========== 计算最大曲线数量和对齐刻度位置 ==========
        # 第1道（岩性道）：BS(有则算)+CAL+SP+GR = 4(有BS)或3(无BS)
        # 第2道（电阻率道）：n_res_curves（传统3条或阵列感应5条）
        # 第3道（孔隙度道）：PE+NPHI+RHOB+DT = 4
        n_track1_curves = 4 if has_bs else 3
        n_track3_curves = 4
        max_curves = max(n_track1_curves, n_res_curves, n_track3_curves)
        
        # 确保至少3个刻度位置，最多8个
        max_curves = max(3, min(max_curves, 8))
        
        # 动态计算图头区高度：每条曲线2.0cm + 底部0.5cm余量
        HEADER_HEIGHT_CM_ADJUSTED = max_curves * 2.0 + 0.5
        # 计算对齐刻度位置（从底部0.8cm到顶部0.8cm均匀分布）
        ALIGNED_POSITIONS_CM = []
        for i in range(max_curves):
            pos = 0.8 + i * (HEADER_HEIGHT_CM_ADJUSTED - 1.6) / max(max_curves - 1, 1)
            ALIGNED_POSITIONS_CM.append(pos)
        
        cm_to_inch = 1 / 2.54
        header_height_inch = HEADER_HEIGHT_CM_ADJUSTED * cm_to_inch
        title_las_gap_inch = TITLE_LAS_GAP_CM * cm_to_inch
        las_header_gap_inch = LAS_HEADER_GAP_CM * cm_to_inch
        title_height_inch = TITLE_HEIGHT_CM * cm_to_inch
        
        # 计算曲线区高度
        # 印刷比例（1:200）只是下限，不能作为唯一依据 —— 当深度跨度大时，
        # 1:200 算出的图高会让**每像素代表的深度 > 采样间隔**，matplotlib
        # 只能按像素取代表值绘制，曲线视觉上被拉成"一段一个值"的平头
        # （实测 BET-1：2725 ft 跨度 → 1:200 得 7898 px，每像素 0.345 ft，
        #   而 LAS 采样是 0.25 ft，1.4 个采样点挤进 1 像素 → 平头）。
        # 因此这里取"印刷比例高度"与"采样分辨率高度"的较大者：
        #   采样分辨率要求每像素 ≤ 采样间隔的一半（Nyquist）。
        _du = DEPTH_UNIT if DEPTH_UNIT != 'auto' else _detect_depth_unit(depth_min, depth_max)
        # 1:240 比例尺：depth_in_per_px = 每英寸代表的深度单位数
        #   ft → 24 ft/in；m → 10 m/in（240 cm 内的 100 m）
        _depth_per_inch = 24.0 if _du == 'ft' else 10.0
        curve_height_cm = depth_range * (30.48 if _du == 'ft' else 100) / 240
        curve_height_inch = curve_height_cm * cm_to_inch

        # 采样间隔（数据行距）
        try:
            _step = _sample_step(data, depth)
        except Exception:
            _step = None
        if _step and _step > 0:
            # 目标：每像素代表的深度 ≤ 采样间隔/2（否则 matplotlib 每像素只取
            # 一个代表值，曲线视觉上被拉成"一段一个值"的平头）
            #   每像素深度 = _step/2  →  1 英寸代表的深度 = _step/2 * 每像素英寸数
            #   1 英寸代表的深度 = _depth_per_inch，所以像素英寸数 = (_step/2)/_depth_per_inch
            _px_in = (_step / 2.0) / _depth_per_inch
            _need_in = depth_range * _px_in
            if _need_in > curve_height_inch:
                logger.info('曲线区高度按采样分辨率提升: %.1f in → %.1f in'
                            '（采样间隔 %.2f %s，1:240 下每像素 %.3f %s 会丢采样点）',
                            curve_height_inch, _need_in, _step,
                            'ft' if _du == 'ft' else 'm',
                            _step / 2.0, 'ft' if _du == 'ft' else 'm')
                curve_height_inch = _need_in
        
        # 计算LAS信息区高度（4列，5行数据 + 3部分图例*2行，每行约1.3cm）
        las_height_cm = 11 * 1.3  # 5行数据 + 6行图例，增加高度使图例方块更清晰
        las_height_inch = las_height_cm * cm_to_inch
        
        # 总高度 = 图名高度 + 图名-LAS间隔 + LAS高度 + 图头区高度 + 曲线区高度
        # 去掉LAS-图头区间隔，让LAS信息区直接紧贴图头区，避免黑色带状区域
        total_height_inch = curve_height_inch + header_height_inch + las_height_inch + title_las_gap_inch + title_height_inch
        # 最小高度 14 英寸是给**全井**图用的下限（保证图头/LAS区可读）。
        # 若传入的是局部井段（如只看煤层 60ft），14 英寸下限会让图多出一半
        # 空白、曲线被压到下半部分。这里按实际内容需求缩放下限：
        # 局部段用 6 英寸即可，既保证图头可读又不浪费画布。
        min_height_inch = 14 if depth_range > 300 else 6
        total_height_inch = max(total_height_inch, min_height_inch)
        
        # 计算各部分占总高度的比例
        curve_height_ratio = curve_height_inch / total_height_inch
        header_height_ratio = header_height_inch / total_height_inch
        las_height_ratio = las_height_inch / total_height_inch
        title_las_gap_ratio = title_las_gap_inch / total_height_inch
        las_header_gap_ratio = las_header_gap_inch / total_height_inch
        title_height_ratio = title_height_inch / total_height_inch
        
        # 从底部往上计算位置（确保曲线区高度正确）
        # 曲线区上边界 = 曲线区高度占总高度的比例
        header_bottom_y = curve_height_ratio
        # 图头区上边界 = 曲线区上边界 + 图头区高度
        header_top_y = header_bottom_y + header_height_ratio
        # LAS信息区下边界 = 图头区上边界（直接紧贴，无间隔）
        las_bottom_y = header_top_y
        # LAS信息区上边界 = LAS下边界 + LAS高度
        las_top_y = las_bottom_y + las_height_ratio
        # 图名底部位置 = LAS上边界 + 图名-LAS间隔
        title_bottom_y = las_top_y + title_las_gap_ratio
        
        # 如果图名超出figure范围，调整总高度
        if title_bottom_y > 0.99:
            extra_height_inch = (title_bottom_y - 0.99) * total_height_inch
            total_height_inch += extra_height_inch
            # logger.info(f"图名超出范围，增加总高度: {extra_height_inch:.1f} inch")
            # 重新计算比例
            curve_height_ratio = curve_height_inch / total_height_inch
            header_height_ratio = header_height_inch / total_height_inch
            las_height_ratio = las_height_inch / total_height_inch
            title_las_gap_ratio = title_las_gap_inch / total_height_inch
            # 重新计算位置
            header_bottom_y = curve_height_ratio
            header_top_y = header_bottom_y + header_height_ratio
            las_bottom_y = header_top_y
            las_top_y = las_bottom_y + las_height_ratio
            title_bottom_y = las_top_y + title_las_gap_ratio
        
        # 添加关键调试信息（调试用）
        # logger.info(f"深度范围差值: {depth_range:.1f}m")
        # logger.info(f"曲线区高度(cm): {curve_height_cm:.1f}")
        # logger.info(f"曲线区高度(inch): {curve_height_inch:.1f}")
        # logger.info(f"总高度(inch): {total_height_inch:.1f}")
        # logger.info(f"curve_height_ratio: {curve_height_ratio:.4f}")
        # logger.info(f"header_height_ratio: {header_height_ratio:.4f}")
        # logger.info(f"header_bottom_y: {header_bottom_y:.4f}")
        # logger.info(f"header_top_y: {header_top_y:.4f}")
        # logger.info(f"图头区高度: {header_top_y - header_bottom_y:.4f}")
        
        fig = plt.figure(figsize=(24, total_height_inch))
        has_gas = gas_data is not None and len(gas_data) > 0
        
        # 预检测气测曲线数量（用于动态计算气测道宽度）
        gas_track_width = 0.6
        if has_gas:
            gas_curve_cols_pre = _find_gas_columns(gas_data)
            tg_keywords = ('TG', 'TOTGAS', 'TOTALGAS', 'TOTAL_GAS', 'GAS_TOTAL', 'GAS', 'TOTAL', 'TOTG')
            tg_found_pre = any(col.upper().strip() in tg_keywords for col in gas_curve_cols_pre) if gas_curve_cols_pre else False
            component_cols_pre = [col for col in gas_curve_cols_pre if not col.upper().strip() in tg_keywords] if gas_curve_cols_pre else []
            gas_curve_count = (1 if tg_found_pre else 0) + len(component_cols_pre)
            # 动态宽度：每条曲线0.15单位，最小0.4，最大2.0
            gas_track_width = max(0.4, min(2.0, gas_curve_count * 0.15))
            # 更新max_curves以包含气测曲线数量，确保所有气测曲线都有刻度槽位
            max_curves = max(max_curves, min(gas_curve_count, 10))
            # 更新图头区高度：气测道每条曲线1.5cm + 余量
            gas_header_extra = max(0, gas_curve_count - 4) * 1.5  # 超过4条曲线时增加图头区
            HEADER_HEIGHT_CM_ADJUSTED = max(HEADER_HEIGHT_CM_ADJUSTED, max_curves * 2.0 + 0.5 + gas_header_extra)
            # 重新计算对齐刻度位置
            ALIGNED_POSITIONS_CM = []
            for i in range(max_curves):
                pos = 0.8 + i * (HEADER_HEIGHT_CM_ADJUSTED - 1.6) / max(max_curves - 1, 1)
                ALIGNED_POSITIONS_CM.append(pos)
            cm_to_inch = 1 / 2.54
            header_height_inch = HEADER_HEIGHT_CM_ADJUSTED * cm_to_inch
            # 重新计算总高度
            curve_height_inch = curve_height_cm * cm_to_inch
            las_height_inch = las_height_cm * cm_to_inch
            total_height_inch = curve_height_inch + header_height_inch + las_height_inch + title_las_gap_inch + title_height_inch
            total_height_inch = max(total_height_inch, 14)
            curve_height_ratio = curve_height_inch / total_height_inch
            header_height_ratio = header_height_inch / total_height_inch
            las_height_ratio = las_height_inch / total_height_inch
            header_bottom_y = curve_height_ratio
            header_top_y = header_bottom_y + header_height_ratio
            las_bottom_y = header_top_y
            las_top_y = las_bottom_y + las_height_ratio
            title_bottom_y = las_top_y + title_las_gap_ratio
        
        if has_gas:
            # 气测道在第6道（第二孔隙度道POR2）之后
            track_widths = [1, 1, 1, 0.5, 1, 1, gas_track_width, 1, 1, 1, 1]
            gs = GridSpec(1, 11, width_ratios=track_widths, wspace=0)
            axes = [fig.add_subplot(gs[i]) for i in range(11)]
            IDX_LITHO, IDX_RES, IDX_POR, IDX_DEPTH, IDX_SW, IDX_POR2, IDX_GAS, IDX_LITHO_FILL, IDX_FACIES, IDX_PROFILE, IDX_INTERP = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        else:
            track_widths = [1, 1, 1, 0.5, 1, 1, 1, 1, 1, 1]
            gs = GridSpec(1, 10, width_ratios=track_widths, wspace=0)
            axes = [fig.add_subplot(gs[i]) for i in range(10)]
            IDX_LITHO, IDX_RES, IDX_POR = 0, 1, 2
            IDX_DEPTH = 3
            IDX_SW, IDX_POR2, IDX_LITHO_FILL, IDX_FACIES, IDX_PROFILE, IDX_INTERP = 4, 5, 6, 7, 8, 9
        
        for i in range(len(axes)):
            if i != IDX_LITHO:
                axes[i].sharey(axes[IDX_LITHO])
        
        # 设置所有axes背景透明，避免遮挡figure背景
        for ax in axes:
            ax.patch.set_alpha(0)
        
        # 必须先绘制一次才能获取正确的axes位置
        fig.canvas.draw()
        
        # 检查axes位置（调试用）
        # for i, ax in enumerate(axes):
        #     pos = ax.get_position()
        #     logger.info(f"Axes[{i}]位置: x0={pos.x0:.4f}, y0={pos.y0:.4f}, x1={pos.x1:.4f}, y1={pos.y1:.4f}")
        
        # 设置axes位置，确保覆盖整个曲线区
        for ax in axes:
            pos = ax.get_position()
            new_pos = [pos.x0, 0, pos.x1 - pos.x0, header_bottom_y]
            ax.set_position(new_pos)
        
        # 再次检查axes位置（调试用）
        # for i, ax in enumerate(axes):
        #     pos = ax.get_position()
        #     logger.info(f"Axes[{i}]新位置: x0={pos.x0:.4f}, y0={pos.y0:.4f}, x1={pos.x1:.4f}, y1={pos.y1:.4f}")
        
        def get_tick_position_in_header(cm_from_bottom):
            """计算刻度线在图头区内的位置（figure坐标）"""
            cm_from_bottom = max(0.3, min(HEADER_HEIGHT_CM_ADJUSTED - 0.8, cm_from_bottom))
            return header_bottom_y + (cm_from_bottom / HEADER_HEIGHT_CM_ADJUSTED) * header_height_ratio
        
        def draw_tick_line(ax, cm_from_bottom, color='black', linewidth=1):
            """在图头区内绘制刻度横线（使用figure坐标）"""
            from matplotlib.lines import Line2D
            
            y_pos = get_tick_position_in_header(cm_from_bottom)
            # 获取当前axes在figure中的位置
            pos = ax.get_position()
            ax_left = pos.x0
            ax_right = pos.x1
            
            # 使用fig.add_line直接在figure级别绘制，避免axes裁剪影响
            # zorder设置为6000，确保在边框(zorder=5000)之上
            line = Line2D([ax_left, ax_right], [y_pos, y_pos], color=color, 
                          linewidth=linewidth, zorder=6000, transform=fig.transFigure)
            fig.add_artist(line)
            return y_pos
        
        def draw_tick_labels(ax, cm_from_bottom, label, min_val, max_val, color='black', fontsize_label=11, fontsize_value=9, is_log=False, draw_tick_marks=True):
            """在图头区内绘制刻度标签和首尾数据，确保都在图头区内（使用figure坐标）
            
            Args:
                is_log: 是否为对数刻度。True时会在min_val和max_val之间绘制10的幂次刻度线和标签
                draw_tick_marks: 是否绘制对数刻度小竖线标记（气测道设为False避免视觉杂乱）
            """
            y_pos = get_tick_position_in_header(cm_from_bottom)
            
            # 获取当前axes在figure中的位置
            pos = ax.get_position()
            ax_left = pos.x0
            ax_right = pos.x1
            ax_center = (ax_left + ax_right) / 2
            
            # 计算图头区高度（figure坐标）
            header_height_fig = header_top_y - header_bottom_y
            
            # 标签和数值在刻度线下方（向上偏移），确保在图头区内
            # 使用更小的偏移量(0.05cm)使标签更贴近刻度线
            offset_ratio = 0.05 / HEADER_HEIGHT_CM_ADJUSTED  # 0.05cm相对于图头区高度的比例
            label_offset = header_height_fig * offset_ratio
            
            # 确保标签不会超出图头区上边界和下边界
            max_y_for_label = header_top_y - header_height_fig * 0.05  # 顶部留5%余量
            min_y_for_label = header_bottom_y + header_height_fig * 0.05  # 底部留5%余量
            actual_y_pos = max(min(y_pos + label_offset, max_y_for_label), min_y_for_label)
            
            # 确保首尾数值在图头区内，向内偏移更多
            margin_ratio = 0.08  # 8%的边距
            left_pos = ax_left + (ax_right - ax_left) * margin_ratio
            right_pos = ax_right - (ax_right - ax_left) * margin_ratio
            
            if is_log and min_val > 0 and max_val > min_val:
                # 对数刻度：只显示首尾数值（与线性刻度一致）
                log_min = math.log10(min_val)
                log_max = math.log10(max_val)
                tick_powers = list(range(int(math.ceil(log_min)), int(log_max) + 1))
                
                # 只绘制首尾数值（不绘制中间幂次）
                for power in [tick_powers[0], tick_powers[-1]]:
                    val = 10 ** power
                    norm_x = (power - log_min) / (log_max - log_min)
                    x_pos = ax_left + norm_x * (ax_right - ax_left - 2 * margin_ratio * (ax_right - ax_left)) + margin_ratio * (ax_right - ax_left)
                    
                    # 刻度竖线（仅在draw_tick_marks=True时绘制）
                    if draw_tick_marks:
                        tick_top = y_pos + header_height_fig * 0.03
                        tick_bottom = y_pos - header_height_fig * 0.03
                        fig.add_artist(Line2D([x_pos, x_pos], [tick_bottom, tick_top],
                                             color=color, linewidth=0.8, transform=fig.transFigure, zorder=1001))
                    
                    # 刻度数值标签
                    if val >= 1_000_000:
                        tick_label = '1M'
                    elif val >= 1_000:
                        tick_label = f'{val//1000}K'
                    else:
                        tick_label = str(val)
                    ax.text(x_pos, actual_y_pos, tick_label, color=color, fontsize=6,
                           ha='center', va='bottom', transform=fig.transFigure, zorder=1001)
            else:
                # 线性刻度：只显示首尾数值
                ax.text(left_pos, actual_y_pos, str(min_val), color=color, fontsize=fontsize_value, 
                       ha='left', va='bottom', transform=fig.transFigure, zorder=1001)
                ax.text(right_pos, actual_y_pos, str(max_val), color=color, fontsize=fontsize_value, 
                       ha='right', va='bottom', transform=fig.transFigure, zorder=1001)
            
            ax.text(ax_center, actual_y_pos, label, color=color, fontsize=fontsize_label, 
                   ha='center', va='bottom', transform=fig.transFigure, zorder=1001)
        
        # 获取所有道的位置范围，用于绘制整体外框
        all_axes_pos = [ax.get_position() for ax in axes]
        overall_x_left = min(pos.x0 for pos in all_axes_pos)
        overall_x_right = max(pos.x1 for pos in all_axes_pos)
        
        # 统一绘制整体外框（只绘制一次，避免重复）
        from matplotlib.lines import Line2D
        linewidth = 0.8
        # 上边框（图头区顶部）
        fig.add_artist(Line2D([overall_x_left, overall_x_right], [header_top_y, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        # 左边框
        fig.add_artist(Line2D([overall_x_left, overall_x_left], [0, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        # 右边框
        fig.add_artist(Line2D([overall_x_right, overall_x_right], [0, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        # 下边框
        fig.add_artist(Line2D([overall_x_left, overall_x_right], [0, 0],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        # 图头区和曲线区分隔线
        fig.add_artist(Line2D([overall_x_left, overall_x_right], [header_bottom_y, header_bottom_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        
        # 绘制道之间的分隔线（竖线）
        # 获取每个道的右边界位置（从axes位置计算）
        ax_right_positions = [pos.x1 for pos in all_axes_pos]
        # 按x坐标排序，确保从左到右绘制
        ax_right_positions.sort()
        
        # 绘制道间分隔线（从底部到图头区顶部）
        for x_pos in ax_right_positions[:-1]:  # 不绘制最右边的线（已经是外框）
            fig.add_artist(Line2D([x_pos, x_pos], [0, header_top_y],
                                  color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
        
        # ========== 第1道: 岩性道 ==========
        ax1 = axes[IDX_LITHO]
        _setup_track_with_header(ax1, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
        
        # 第1道曲线分配槽位（从底部向上编号）：
        # 有BS时：BS→slot0, CAL→slot1, SP→slot2, GR→slot3
        # 无BS时：CAL→slot0, SP→slot1, GR→slot2
        track1_slot = 0
        
        # BS单独画刻度线（slot0）
        bs_col = _find_column(data, ['BS', 'BIT', 'BITSIZE', 'BIT_SIZE', 'BSIZE', 'DRILL_BIT'])
        if bs_col:
            _plot_curve(ax1, data[bs_col], depth, 'black', (5.5, 16.5), depth_max, depth_min, curve_height_ratio, header_bottom_y,
                       linestyle='--')
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'black')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'BS (in)', 6, 16, 'black', fontsize_value=7)
            track1_slot += 1
        
        # CAL（下一个槽位）
        cal_col = _find_column(data, ['CALS', 'CALI', 'CAL'])
        if cal_col:
            _plot_curve(ax1, data[cal_col], depth, 'red', (5.5, 16.5), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'red')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'CAL (in)', 6, 16, 'red')
            track1_slot += 1
            
            # 淡粉色填充CAL和BS之间的区域
            if bs_col:
                fill_ax = ax1.twiny()
                fill_ax.set_position(ax1.get_position())
                fill_ax.set_ylim(depth_max, depth_min)
                fill_ax.set_xlim(0, 1)
                for spine in fill_ax.spines.values():
                    spine.set_visible(False)
                fill_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                    labelbottom=False, labeltop=False, length=0)
                fill_ax.set_xticks([])
                cal_norm = (data[cal_col] - 5.5) / (16.5 - 5.5)
                bs_norm = (data[bs_col] - 5.5) / (16.5 - 5.5)
                valid_mask = cal_norm.notna() & bs_norm.notna()
                valid_depth = depth[valid_mask]
                valid_cal = cal_norm[valid_mask]
                valid_bs = bs_norm[valid_mask]
                if len(valid_depth) > 10:
                    fill_ax.fill_betweenx(valid_depth, valid_cal, valid_bs,
                                          color='lightpink', alpha=0.5, zorder=1)
        
        # SP（下一个槽位）
        if 'SP' in data.columns:
            _plot_curve(ax1, data['SP'], depth, 'blue', (-110, 110), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'blue')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'SP (mV)', -100, 100, 'blue')
            track1_slot += 1
        
        # GR（下一个槽位）
        if 'GR' in data.columns:
            _plot_curve(ax1, data['GR'], depth, 'green', (-10, 210), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'green')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'GR (API)', 0, 200, 'green')
            track1_slot += 1
        
        # ========== 第2道: 电阻率道 ==========
        ax2 = axes[IDX_RES]
        _setup_resistivity_track(ax2, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
        
        # 使用预识别的电阻率曲线结果
        resistivity_cols = resistivity_cols_pre
        res_colors = ['green', 'red', 'black', 'blue', 'orange']
        
        # 电阻率道曲线的颜色可逆映射，按顺序分配
        if len(resistivity_cols) > 0:
            for i, col in enumerate(resistivity_cols):
                color = res_colors[i % len(res_colors)]
                _plot_log_curve(ax2, data[col], depth, color, (0.15, 3000), depth_max, depth_min, curve_height_ratio, header_bottom_y)
                draw_tick_line(ax2, ALIGNED_POSITIONS_CM[i], color)
                draw_tick_labels(ax2, ALIGNED_POSITIONS_CM[i], f'{col} (ohm·m)', 0.2, 2000, color, fontsize_value=7)
        
        logger.info(f"电阻率道绘制曲线: {resistivity_cols}")
        
        # ========== 第3道: 孔隙度道 ==========
        ax3 = axes[IDX_POR]
        _setup_track_with_header(ax3, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
        
        # 第3道曲线分配槽位（与第1道对齐）：
        # PE→slot0, NPHI→slot1, RHOB→slot2, DT→slot3
        track3_slot = 0
        
        # PE曲线（slot0，与BS对齐）
        pe_col = _find_column(data, ['PEF', 'PE'])
        if pe_col:
            _plot_curve(ax3, data[pe_col], depth, 'orange', (-1, 11), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax3, ALIGNED_POSITIONS_CM[track3_slot], 'orange')
            draw_tick_labels(ax3, ALIGNED_POSITIONS_CM[track3_slot], f'{pe_col} (b/e)', 0, 10, 'orange')
            track3_slot += 1
        
        # 孔隙度曲线（slot1，与CAL对齐，倒序绘制）
        # 第3道优先绘制中子曲线(NPHI)，直观反映含氢指数
        phi_plot = None
        phi_label = None
        if 'NPHI' in data.columns:
            nphi = data['NPHI'].copy()
            if nphi.max() > 1:
                x_range = (65, -5)
                phi_label = 'NPHI (%)'
                tick_vals = [60, 0]
            else:
                x_range = (1.1, -0.1)
                phi_label = 'NPHI (v/v)'
                tick_vals = [1, 0]
            phi_plot = nphi
        elif 'PHI' in data.columns:
            phi_plot = data['PHI'].copy()
            phi_label = 'PHI (v/v)'
            x_range = (1.1, -0.1)
            tick_vals = [1, 0]
        elif 'PHIE' in data.columns:
            phi_plot = data['PHIE'].copy()
            phi_label = 'PHIE (v/v)'
            x_range = (1.1, -0.1)
            tick_vals = [1, 0]
        if phi_plot is not None:
            # 只对标签中的无效段置NaN（matplotlib自动断开），不强制置0避免方波效应
            if '_POROSITY_VALID' in data.columns:
                phi_plot = phi_plot.copy()
                phi_plot.loc[~data['_POROSITY_VALID']] = np.nan
            _plot_curve(ax3, phi_plot, depth, 'green', x_range, depth_max, depth_min, curve_height_ratio, header_bottom_y)
            # 刻度始终绘制
            draw_tick_line(ax3, ALIGNED_POSITIONS_CM[track3_slot], 'green')
            draw_tick_labels(ax3, ALIGNED_POSITIONS_CM[track3_slot], phi_label, tick_vals[0], tick_vals[1], 'green')
            track3_slot += 1
        
        # RHOB（slot2，与SP对齐）
        # 优先使用RHOB，如果没有则使用DEN
        den_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        if den_col:
            # 顶部/底部无效段mask为NaN，matplotlib自动断开
            den_plot = data[den_col].copy()
            if '_POROSITY_VALID' in data.columns:
                den_plot.loc[~data['_POROSITY_VALID']] = np.nan
            _plot_curve(ax3, den_plot, depth, 'blue', (1.7, 2.9), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            # 刻度始终绘制
            draw_tick_line(ax3, ALIGNED_POSITIONS_CM[track3_slot], 'blue')
            draw_tick_labels(ax3, ALIGNED_POSITIONS_CM[track3_slot], f'{den_col} (g/cc)', 1.8, 2.8, 'blue')
            track3_slot += 1
        
        # DT/DTCO（slot3，与GR对齐，倒序绘制）
        dt_col = None
        if 'DT' in data.columns:
            dt_col = 'DT'
        elif 'DTCO' in data.columns:
            dt_col = 'DTCO'
        if dt_col:
            # 顶部/底部无效段mask为NaN，matplotlib自动断开
            dt_plot = data[dt_col].copy()
            if '_POROSITY_VALID' in data.columns:
                dt_plot.loc[~data['_POROSITY_VALID']] = np.nan
            dt_max = data[dt_col].max()
            if dt_max > 200:
                x_range = (620, 80)
                label = f'{dt_col} (us/m)'
                tick_vals = [600, 100]
            else:
                x_range = (150, 30)
                label = f'{dt_col} (us/ft)'
                tick_vals = [140, 40]
            _plot_curve(ax3, dt_plot, depth, 'red', x_range, depth_max, depth_min, curve_height_ratio, header_bottom_y)
            # 刻度始终绘制
            draw_tick_line(ax3, ALIGNED_POSITIONS_CM[track3_slot], 'red')
            draw_tick_labels(ax3, ALIGNED_POSITIONS_CM[track3_slot], label, tick_vals[0], tick_vals[1], 'red')
            track3_slot += 1
        
        # ========== 深度道 ==========
        ax4 = axes[IDX_DEPTH]
        _setup_depth_track(ax4, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y)
        
        # ========== 含水饱和度道 ==========
        ax5 = axes[IDX_SW]
        _setup_track_with_header(ax5, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
        
        # 检查是否有足够的有效曲线
        has_valid_curves = False
        if 'VALID_CURVES_COUNT' in data.columns:
            has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3
        
        sw_col = _find_column(data, ['Sw', 'SW'])
        if sw_col and has_valid_curves:
            # 0值保留为0（不设NaN），0即左边框，曲线自然闭合到左边框
            sw_plot = data[sw_col].copy()
            _plot_curve(ax5, sw_plot, depth, 'blue', (0, 1.0), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax5, TICK_POSITIONS_CM['upper_middle'], 'blue')
            draw_tick_labels(ax5, TICK_POSITIONS_CM['upper_middle'], 'Sw (v/v)', 0, 1, 'blue')

        # ========== 孔隙度道（有效孔隙度PHI） ==========
        ax6 = axes[IDX_POR2]
        _setup_track_with_header(ax6, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)

        # 第6道绘制PHI（与profile道使用相同的孔隙度数据，确保两者一致）
        por_col = _find_column(data, ['PHI', 'PHIE', 'POR'])
        if por_col:
            por_plot = data[por_col].copy()
            por_label = f'{por_col} (v/v)'
        else:
            por_plot = None
            por_label = None
        if por_plot is not None:
            # 只对无效段置NaN（matplotlib自动断开），0值保留为0画到左边框
            if '_POROSITY_VALID' in data.columns:
                por_plot = por_plot.copy()
                por_plot.loc[~data['_POROSITY_VALID']] = np.nan
            _plot_curve(ax6, por_plot, depth, 'green', (0, 0.5), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax6, TICK_POSITIONS_CM['upper_middle'], 'green')
            draw_tick_labels(ax6, TICK_POSITIONS_CM['upper_middle'], por_label, 0, 0.5, 'green')
        
        # ========== 岩性剖面道 ==========
        ax7 = axes[IDX_LITHO_FILL]
        _setup_lithology_track(ax7, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 沉积相道 ==========
        ax8 = axes[IDX_FACIES]
        _setup_facies_track(ax8, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 矿物剖面道 ==========
        ax_profile = axes[IDX_PROFILE]
        _setup_profile_track(ax_profile, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 测井解释道 ==========
        ax9 = axes[IDX_INTERP]
        _setup_interpretation_track(ax9, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 气测道 ==========
        if has_gas:
            ax_gas = axes[IDX_GAS]
            _setup_gas_track(ax_gas, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
            
            # 识别气测组分列
            gas_depth_col = _find_column(gas_data, ['MD', 'DEPTH', 'DEP', 'DEPT'])
            gas_curve_cols = _find_gas_columns(gas_data)
            
            if gas_curve_cols:
                # 对齐深度
                gas_depth = gas_data[gas_depth_col] if gas_depth_col else gas_data.iloc[:, 0]
                
                # 判断气测数据是否包含C5+组分（C6/C7/C8/MCH/BZ/TL）
                # 包含C5+时绘制C4/C5，否则绘制IC4/NC4/IC5/NC5
                c5plus_keywords = ['C6', 'C7', 'C8', 'MCH', 'BZ', 'TL']
                has_c5plus = any(
                    any(kw in col.upper().strip() for kw in c5plus_keywords)
                    for col in gas_curve_cols
                )
                
                # 分离TG（全烃）和烃类组分
                tg_col = None
                component_cols = []
                for col in gas_curve_cols:
                    col_upper = col.upper().strip()
                    if col_upper in tg_keywords:
                        tg_col = col
                    else:
                        # 判断是否为C4/C5/IC4/NC4/IC5/NC5相关的列
                        is_c4_total = col_upper in ['C4', 'C4PCT', 'C4%', 'C4_PCT', 'BUTANE']
                        is_c5_total = col_upper in ['C5', 'C5PCT', 'C5%', 'C5_PCT', 'PENTANE']
                        is_ic4_nc4 = any(kw in col_upper for kw in ['IC4', 'NC4'])
                        is_ic5_nc5 = any(kw in col_upper for kw in ['IC5', 'NC5'])
                        is_c1_c3 = any(kw in col_upper for kw in ['C1', 'C2', 'C3'])
                        is_c5plus = any(kw in col_upper for kw in ['C6', 'C7', 'C8', 'MCH', 'BZ', 'TL'])
                        
                        if has_c5plus:
                            # 有C5+：保留C4/C5/C6/C7/C8/MCH/BZ/TL/C1/C2/C3，排除IC4/NC4/IC5/NC5
                            if is_ic4_nc4 or is_ic5_nc5:
                                continue
                            if is_c4_total or is_c5_total or is_c1_c3 or is_c5plus:
                                component_cols.append(col)
                        else:
                            # 只有C5及以下：保留IC4/NC4/IC5/NC5/C1/C2/C3，排除C4/C5
                            if is_c4_total or is_c5_total:
                                continue
                            if is_ic4_nc4 or is_ic5_nc5 or is_c1_c3:
                                component_cols.append(col)
                
                # 颜色方案：TG用红色粗线，C1-C8用不同颜色区分
                gas_color_map = {
                    'C1': '#1A7A1A',    # 深绿
                    'C2': '#1A5B9C',    # 深蓝
                    'C3': '#E67E22',    # 橙
                    'IC4': '#9B59B6',   # 紫
                    'NC4': '#9B59B6',   # 紫（同IC4）
                    'IC5': '#8B4513',   # 褐
                    'NC5': '#8B4513',   # 褐（同IC5）
                    'C6': '#34495E',    # 深灰蓝
                    'C7': '#7F8C8D',    # 灰
                    'C8': '#BDC3C7',    # 浅灰
                    'MCH': '#E74C3C',   # 红（甲基环己烷）
                    'BZ': '#F39C12',    # 金（苯）
                    'TL': '#2ECC71',    # 绿（甲苯）
                }
                
                # 1. 绘制TG全烃（粗红线，占用第一个刻度槽）
                gas_slot = 0
                if tg_col:
                    # 将0值设为NaN，semilogx会自动在NaN处断开曲线，避免过滤后连接非相邻点产生异常直线
                    tg_plot = pd.Series(pd.to_numeric(gas_data[tg_col], errors='coerce').values, index=gas_data.index).copy()
                    tg_plot[tg_plot <= 0] = np.nan
                    if tg_plot.notna().any():
                        _plot_log_curve(ax_gas, tg_plot.values, gas_depth.values, 'red',
                                       (10, 1_000_000), depth_max, depth_min,
                                       curve_height_ratio, header_bottom_y, linewidth=2.0)
                        draw_tick_line(ax_gas, ALIGNED_POSITIONS_CM[gas_slot], 'red')
                        draw_tick_labels(ax_gas, ALIGNED_POSITIONS_CM[gas_slot],
                                        f'{tg_col} (ppm)', 10, 1_000_000, 'red',
                                        fontsize_value=7, is_log=True, draw_tick_marks=False)
                        gas_slot += 1
                
                # 2. 绘制C1-C8组分
                for col in component_cols:
                    if gas_slot >= len(ALIGNED_POSITIONS_CM):
                        break
                    # 确定颜色
                    col_upper = col.upper().strip()
                    color = 'blue'
                    for key, c in gas_color_map.items():
                        if key in col_upper:
                            color = c
                            break
                    
                    # 将0值设为NaN，semilogx会自动在NaN处断开曲线，避免过滤后连接非相邻点产生异常直线
                    gas_plot = pd.Series(pd.to_numeric(gas_data[col], errors='coerce').values, index=gas_data.index).copy()
                    gas_plot[gas_plot <= 0] = np.nan
                    
                    if gas_plot.notna().any():
                        _plot_log_curve(ax_gas, gas_plot.values, gas_depth.values, color,
                                       (10, 1_000_000), depth_max, depth_min,
                                       curve_height_ratio, header_bottom_y, linewidth=1.0)
                        draw_tick_line(ax_gas, ALIGNED_POSITIONS_CM[gas_slot], color)
                        draw_tick_labels(ax_gas, ALIGNED_POSITIONS_CM[gas_slot],
                                        f'{col} (ppm)', 10, 1_000_000, color,
                                        fontsize_value=7, is_log=True, draw_tick_marks=False)
                        gas_slot += 1
                
                logger.info(f"气测道绘制曲线: TG={'有' if tg_col else '无'}, 组分{len(component_cols)}条")
            else:
                logger.warning("气测数据中未识别到有效气体组分列")
        
        # 隐藏非深度道的y轴
        for i, ax in enumerate(axes):
            if i == IDX_DEPTH:
                continue
            ax.set_yticks([])
            ax.set_yticklabels([])
            ax.yaxis.set_visible(False)
        
        # 添加图名和道名
        well_name = results.get('well_name', 'Unknown Well')
        
        fig.text(0.5, title_bottom_y, f"{well_name} Composite Log Plot", fontsize=16, fontweight='bold', 
                 ha='center', va='bottom', fontfamily='Microsoft YaHei')
        
        # 在图名和道名之间添加井信息表格（4列布局，与图头区曲线区同宽）
        las_info = results.get('las_info', {})
        if las_info:
            well_info = las_info.get('well', {})
            param_info = las_info.get('parameter', {})
            
            # 收集图例数据（**只列本井实际出现的岩性**，按厚度降序）
            lith_types = []
            if has_enough_curves and 'LITHOLOGY' in data.columns:
                _t = data['LITHOLOGY'].dropna().astype(str).str.strip().str.lower()
                _t = _t[~_t.isin(['', 'nan', 'none', 'mixed'])]
                if len(_t):
                    _thick = _t.value_counts()
                    lith_types = [str(k) for k in _thick.index]
            if not lith_types:
                lith_types = ['sandstone', 'shale', 'limestone', 'dolomite']
            facies_items = ['Channel', 'Floodplain', 'Delta Front', 'Prodelta']
            interp_items = ['Oil', 'Gas', 'Water']
            engi_name = well_info.get('engi', '') or well_info.get('engineer', '') or ''

            # 图例颜色统一走 LITH_BG_COLORS（与道头区/岩性道/profile道完全一致）
            fallback_colors = {lt: _lith_bg_color(lt) for lt in lith_types}
            lith_types_cn = [_lith_cn_name(lt) for lt in lith_types]
            # 中文标签 → 统一底色（LAS 图例方块用）
            fallback_colors_cn = {cn: _lith_bg_color(lt) for lt, cn
                                  in zip(lith_types, lith_types_cn)}
            # 中文标签 → 岩性英文名（供 draw_lithology_pattern_fig 取符号）
            cn2lith = {cn: lt for lt, cn in zip(lith_types, lith_types_cn)}
            facies_color_map = {'Channel': 'firebrick', 'Floodplain': 'sandybrown', 
                                'Delta Front': 'wheat', 'Prodelta': 'darkolivegreen'}
            interp_color_map = {'Oil': 'green', 'Gas': 'red', 'Water': 'blue', 'Dry': 'saddlebrown'}
            
            # 预加载岩性符号（供 LAS 图例方块取用，走同一套缓存与底色重着色）
            for lith_name in lith_types:
                _load_lithology_symbol(lith_name)

            # 基础数据
            def _fmt_val(v):
                """将数值格式化为2位小数，非数值原样返回"""
                if v is None or str(v).strip() == '':
                    return ''
                try:
                    fv = float(v)
                    return f'{fv:.2f}'
                except (ValueError, TypeError):
                    return str(v)
            
            table_data = [
                ['Company', well_info.get('company', '')],
                ['Country', well_info.get('country', '')],
                ['Contractor', well_info.get('service_company_name', '')],
                ['Field', well_info.get('field_name', '')],
                ['Well Name', well_info.get('well_name', '')],
                ['State/Prov', well_info.get('state_or_province', '')],
                ['Log Date', well_info.get('date', '')],
                ['Datum', well_info.get('permanent_datum', '')],
                ['TD Driller', _fmt_val(well_info.get('total_depth_driller', ''))],
                ['TD Logger', _fmt_val(well_info.get('total_depth_logger', ''))],
                ['Start Depth', _fmt_val(well_info.get('start_depth', ''))],
                ['Stop Depth', _fmt_val(well_info.get('stop_depth', ''))],
                ['Bit Size', f"{_fmt_val(param_info.get('bit_size', ''))}@{_fmt_val(param_info.get('bit_size_depth_from', ''))}"],
                ['Casing Size', f"{_fmt_val(param_info.get('current_casing_size', ''))}@{_fmt_val(param_info.get('casing_depth_from', ''))}"],
                ['Mud Type', param_info.get('drilling_fluid_type', '')],
                ['Mud Density', _fmt_val(param_info.get('drilling_fluid_density', ''))],
                ['Mud Viscosity', _fmt_val(param_info.get('drilling_fluid_viscosity', ''))],
                ['Mud Loss', _fmt_val(param_info.get('drilling_fluid_loss', ''))],
            ]
            
            num_cols = 4
            num_rows = (len(table_data) + num_cols - 1) // num_cols
            
            # 获取道区域的实际宽度（从axes位置计算）
            all_axes_pos = [ax.get_position() for ax in axes]
            tracks_x_left = min(pos.x0 for pos in all_axes_pos)
            tracks_x_right = max(pos.x1 for pos in all_axes_pos)
            tracks_width = tracks_x_right - tracks_x_left
            
            # 表格宽度与道区域完全一致
            table_x_left = tracks_x_left
            table_x_right = tracks_x_right
            table_width = table_x_right - table_x_left
            cell_width = table_width / num_cols
            
            # LAS信息区高度由前面计算的las_height_ratio确定
            table_height_ratio = las_height_ratio
            table_y_start = las_top_y
            table_y_end = las_bottom_y
            
            # 行间距减小，字体与图头区一致（8号）
            cell_height = table_height_ratio / num_rows
            
            # 绘制表格边框（与图头区曲线区格式一致）
            from matplotlib.lines import Line2D
            # 外框
            # 上边框
            fig.add_artist(Line2D([table_x_left, table_x_right], [table_y_start, table_y_start], 
                                  color='black', linewidth=0.5, transform=fig.transFigure))
            # 下边框不绘制，因为图头区的上边框会覆盖它，避免重复导致黑色横带
            # fig.add_artist(Line2D([table_x_left, table_x_right], [table_y_end, table_y_end], 
            #                       color='black', linewidth=0.5, transform=fig.transFigure))
            # 左边框
            fig.add_artist(Line2D([table_x_left, table_x_left], [table_y_start, table_y_end], 
                                  color='black', linewidth=0.5, transform=fig.transFigure))
            # 右边框
            fig.add_artist(Line2D([table_x_right, table_x_right], [table_y_start, table_y_end], 
                                  color='black', linewidth=0.5, transform=fig.transFigure))
            # 列分隔线
            for col_idx in range(1, num_cols):
                x_pos = table_x_left + col_idx * cell_width
                fig.add_artist(Line2D([x_pos, x_pos], [table_y_start, table_y_end], 
                                      color='black', linewidth=0.5, transform=fig.transFigure))
            # 总行数（数据行 + 图例行6行）
            total_rows = num_rows + 6  # 5数据行 + 6图例行(3部分×2行)
            cell_height = table_height_ratio / total_rows
            
            # 行分隔线（只绘制数据行之间）
            for row_idx in range(1, num_rows):
                y_pos = table_y_start - row_idx * cell_height
                fig.add_artist(Line2D([table_x_left, table_x_right], [y_pos, y_pos], 
                                      color='black', linewidth=0.5, transform=fig.transFigure))
            
            # 绘制数据行
            for i, (label, value) in enumerate(table_data):
                col_idx = i % num_cols
                row_idx = i // num_cols
                x_start = table_x_left + col_idx * cell_width
                y_pos = table_y_start - (row_idx + 0.5) * cell_height
                fig.text(x_start + 0.003, y_pos, label, fontsize=8, ha='left', va='center', 
                        fontfamily='Microsoft YaHei', color='black')
                fig.text(x_start + cell_width * 0.4, y_pos, str(value), fontsize=8, ha='left', va='center', 
                        fontfamily='Microsoft YaHei', color='black')
            
            # ========== 图例绘制（在数据行下方，使用3部分×2行，所有方块为统一大小正方形） ==========
            # 数据行底部
            data_bottom_y = table_y_start - num_rows * cell_height
            # 图例区域总高度
            legend_total_height = data_bottom_y - table_y_end
            
            # 图例区域划分：3部分（岩性、沉积相、解释），每部分2行
            # 岩性部分用中文标签 + 统一配色（与道头区/岩性道/profile道一致）
            legend_sections = [
                ('Litho:', lith_types_cn, None, fallback_colors_cn, 'texture'),
                ('Facies:', facies_items, None, facies_color_map, 'color'),
                ('Interp:', interp_items, None, interp_color_map, 'color'),
            ]
            n_sections = len(legend_sections)
            section_height = legend_total_height / n_sections  # 每部分高度
            row_height = section_height / 2  # 每行高度
            
            # 计算图宽高比，使方块在视觉上为正方形
            # 因 figure 宽>高，figure坐标中的正方形会变横条，需校正
            fig_hw_ratio = fig.get_figheight() / fig.get_figwidth()  # <1
            # 高度受行高约束，宽度按比例缩小以保持视觉正方形
            sq_h = row_height * 0.85  # figure坐标中的高度
            sq_w = sq_h * fig_hw_ratio  # figure坐标中的宽度（校正后视觉正方形）
            # 同时确保不超出列宽
            max_sq_w = cell_width * 0.22
            if sq_w > max_sq_w:
                sq_w = max_sq_w
                sq_h = sq_w / fig_hw_ratio  # 重新计算高度保持正方形
            
            for sec_idx, (sec_name, items, img_map, color_map, draw_type) in enumerate(legend_sections):
                for row_in_sec in range(2):
                    # 行中心y坐标
                    y_center = data_bottom_y - (sec_idx * 2 + row_in_sec + 0.5) * row_height
                    
                    # 该行应显示的图例项（第1行前6个，第2行剩余）
                    if row_in_sec == 0:
                        items_in_row = items[:6]
                    else:
                        items_in_row = items[6:]
                    
                    if items_in_row:
                        # 部分名称只在第1行第1列显示
                        if row_in_sec == 0:
                            fig.text(table_x_left + 0.003, y_center, sec_name, fontsize=6,
                                    ha='left', va='center', fontfamily='Microsoft YaHei', color='black')
                        
                        # 每行最多6个图例项，按2列排列在3个单元格中
                        # 每个单元格分为左/右2个子列，共6个位置
                        for j, name in enumerate(items_in_row):
                            col_idx = j // 2  # 列索引 0,1,2 → 对应单元格1,2,3
                            sub_col = j % 2   # 0=左, 1=右
                            # 实际列索引（从1开始，因为列0是部分名称）
                            actual_col = 1 + col_idx
                            x_start = table_x_left + actual_col * cell_width
                            # 子列偏移：左列在0.05宽度处，右列在0.52宽度处
                            sub_offset = 0.05 if sub_col == 0 else 0.52
                            x_pos = x_start + cell_width * sub_offset
                            
                            # 符号方块缩小到半格宽度
                            sub_sq_w = sq_w * 0.45
                            sub_sq_h = sub_sq_w / fig_hw_ratio
                            
                            # 绘制符号方块（岩性用中文标签，需映射回英文名取符号）
                            if draw_type == 'texture' and name:
                                _lt = cn2lith.get(name, name)
                                draw_lithology_pattern_fig(
                                    fig, _lt, x_pos, y_center - sub_sq_h / 2,
                                    sub_sq_w, sub_sq_h,
                                    bg_color=color_map.get(name, None), zorder=6002)
                            else:
                                color = color_map.get(name, '#D3D3D3')
                                sq = plt.Rectangle((x_pos, y_center - sub_sq_h/2),
                                                   sub_sq_w, sub_sq_h,
                                                   transform=fig.transFigure, facecolor=color,
                                                   linewidth=0.5, edgecolor='black')
                                fig.add_artist(sq)
                            
                            # 名称标签（紧跟在方块右侧）
                            fig.text(x_pos + sub_sq_w + 0.002, y_center, name,
                                    fontsize=5, ha='left', va='center',
                                    fontfamily='Microsoft YaHei', color='black')
                    elif sec_idx == 2 and row_in_sec == 1:
                        # Interp部分第2行至少显示工程师信息
                        fig.text(table_x_left + 0.003, y_center, f'Eng: {engi_name}', fontsize=6,
                                ha='left', va='center', fontfamily='Microsoft YaHei', color='black')
            
            # ========== 绘制分隔横线 ==========
            # 1. 数据行与图例之间的分隔线（图例顶部）
            fig.add_artist(Line2D([table_x_left, table_x_right], [data_bottom_y, data_bottom_y],
                                  color='black', linewidth=0.5, transform=fig.transFigure))
            # 2. Interp图例项与Eng信息之间的分隔线
            # Interp部分第2行（Eng信息）与第1行之间的边界 = data_bottom_y - 5 * row_height
            interp_sep_y = data_bottom_y - 5 * row_height
            fig.add_artist(Line2D([table_x_left, table_x_right], [interp_sep_y, interp_sep_y],
                                  color='black', linewidth=0.5, transform=fig.transFigure))
        
        # 同步所有 twiny 副轴：_plot_curve/_plot_log_curve 用 ax.twiny() 建副轴，
        # 而副轴是在 axes 被 set_position 之前创建的，位置/ylim 仍是旧值，
        # 会让曲线越出曲线区、画进道头区（表现为黄绿竖条穿透道头图例）。
        # 在最终绘制前统一对齐一次。
        try:
            for ax in axes:
                for tw in getattr(ax, '_twins', []):
                    tw.set_position(ax.get_position())
                    tw.set_ylim(ax.get_ylim())
                    tw.set_xlim(ax.get_xlim())
        except Exception as _e:
            logger.debug(f'twin 轴对齐跳过: {_e}')

        # 必须先绘制一次才能确保布局正确
        fig.canvas.draw()
        
        # 保存文件
        if 'output_dir' in results:
            well_output_dir = Path(results['output_dir'])
        else:
            well_output_dir = Path('output') / well_name
        
        well_output_dir.mkdir(exist_ok=True, parents=True)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = well_output_dir / f'{well_name}_composite_log_{timestamp}.png'
        
        plt.savefig(output_path, dpi=150)
        plt.close(fig)
        
        logger.info(f"综合测井图已保存: {output_path.absolute()}")
        results['visualization_results'] = {'well_log_composite': str(output_path.absolute())}
        
        return str(output_path.absolute())
        
    except Exception as e:
        logger.error(f"生成综合测井图失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _draw_border(fig, ax_left, ax_right, header_top_y, header_bottom_y, draw_top=True, draw_left=True, draw_right=True, draw_bottom=True, draw_separator=True):
    """在figure级别绘制边框（支持选择性绘制，避免重复）"""
    from matplotlib.lines import Line2D
    
    # 使用Line2D绘制真正的线条，避免Rectangle导致的宽度问题
    linewidth = 0.8
    
    # 上边框
    if draw_top:
        fig.add_artist(Line2D([ax_left, ax_right], [header_top_y, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
    # 左边框
    if draw_left:
        fig.add_artist(Line2D([ax_left, ax_left], [0, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
    # 右边框
    if draw_right:
        fig.add_artist(Line2D([ax_right, ax_right], [0, header_top_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
    # 下边框
    if draw_bottom:
        fig.add_artist(Line2D([ax_left, ax_right], [0, 0],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))
    
    # 图头区和曲线区之间的分隔线
    if draw_separator:
        fig.add_artist(Line2D([ax_left, ax_right], [header_bottom_y, header_bottom_y],
                              color='black', linewidth=linewidth, transform=fig.transFigure, zorder=5000))


def _setup_track_with_header(ax, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y):
    """设置道的基本属性（完整外框，无图头区和曲线区分隔线）"""
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    # 关闭axes的顶部和底部边框
    ax.spines['top'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 边框已在主函数中统一绘制，这里不再单独绘制
    
    # 使用figure坐标绘制十等分竖线（只在曲线区）
    # 曲线区范围：x从ax_left到ax_right，y从0到header_bottom_y
    for i in range(1, 10):
        x = ax_left + (ax_right - ax_left) * (i / 10.0)
        if i == 5:
            ax.plot([x, x], [0, header_bottom_y], transform=fig.transFigure, 
                    color='black', linewidth=1.0, zorder=500)
        else:
            ax.plot([x, x], [0, header_bottom_y], transform=fig.transFigure, 
                    color='black', linewidth=0.6, zorder=500)
    
    # 绘制深度刻度线（只在曲线区）
    major_step = 10
    # 从depth_min开始生成整十米刻度（depth_min已经是整十米）
    major_ticks = np.arange(depth_min, depth_max + major_step, major_step)
    major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
    
    minor_step = 1
    # 从depth_min开始生成整米刻度
    minor_ticks = np.arange(depth_min, depth_max + minor_step, minor_step)
    minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
    
    for depth_val in major_ticks:
        # 计算深度值对应的figure y坐标
        # depth_max在底部(fig_y=0), depth_min在顶部(fig_y=header_bottom_y)
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        # 确保在曲线区内（0 <= fig_y <= header_bottom_y）
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                    color='black', linewidth=1, zorder=500)
    
    for depth_val in minor_ticks:
        if depth_val not in major_ticks:
            norm_y = (depth_max - depth_val) / (depth_max - depth_min)
            fig_y = norm_y * header_bottom_y
            # 确保在曲线区内
            if 0 <= fig_y <= header_bottom_y:
                ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                        color='black', linewidth=0.6, zorder=500)


def _setup_resistivity_track(ax, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y):
    """设置电阻率道（对数刻度，完整外框）"""
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 边框已在主函数中统一绘制，这里不再单独绘制
    
    # 使用figure坐标绘制对数刻度竖线（只在曲线区）
    log_min = np.log10(0.2)
    log_max = np.log10(2000)
    
    log_ticks = []
    for i in range(2, 11):
        log_ticks.append(np.log10(i / 10.0))
    for i in range(1, 3):
        log_ticks.append(np.log10(i))
    for decade in [10, 100]:
        for i in range(2, 11):
            log_ticks.append(np.log10(i * decade / 10))
    for decade in [200, 300, 400, 500, 600, 700, 800, 900, 1000]:
        log_ticks.append(np.log10(decade))
    
    for log_val in log_ticks:
        if log_val >= log_min and log_val <= log_max:
            x_pos = ax_left + (ax_right - ax_left) * (log_val - log_min) / (log_max - log_min)
            ax.plot([x_pos, x_pos], [0, header_bottom_y], transform=fig.transFigure, 
                    color='black', linewidth=0.6, zorder=500)
    
    major_log_ticks = [np.log10(1), np.log10(10), np.log10(100), np.log10(1000)]
    for log_val in major_log_ticks:
        if log_val >= log_min and log_val <= log_max:
            x_pos = ax_left + (ax_right - ax_left) * (log_val - log_min) / (log_max - log_min)
            ax.plot([x_pos, x_pos], [0, header_bottom_y], transform=fig.transFigure, 
                    color='black', linewidth=1.0, zorder=500)
    
    # 绘制深度刻度线（只在曲线区）
    major_step = 10
    # 从depth_min开始生成整十米刻度（depth_min已经是整十米）
    major_ticks = np.arange(depth_min, depth_max + major_step, major_step)
    major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
    
    minor_step = 1
    # 从depth_min开始生成整米刻度
    minor_ticks = np.arange(depth_min, depth_max + minor_step, minor_step)
    minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
    
    for depth_val in major_ticks:
        # 计算深度值对应的figure y坐标
        # depth_max在底部(fig_y=0), depth_min在顶部(fig_y=header_bottom_y)
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        # 确保在曲线区内（0 <= fig_y <= header_bottom_y）
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                    color='black', linewidth=1, zorder=500)
    
    for depth_val in minor_ticks:
        if depth_val not in major_ticks:
            norm_y = (depth_max - depth_val) / (depth_max - depth_min)
            fig_y = norm_y * header_bottom_y
            # 确保在曲线区内
            if 0 <= fig_y <= header_bottom_y:
                ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                        color='black', linewidth=0.6, zorder=500)


def _setup_gas_track(ax, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y):
    """设置气测道（对数刻度10-1000000，完整外框和网格线）
    
    在曲线区绘制对数刻度竖线，范围10-1000000，风格与电阻率道一致。
    """
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 使用figure坐标绘制对数刻度竖线（只在曲线区）
    # 范围：10 - 1000000
    log_min = np.log10(10)
    log_max = np.log10(1000000)
    
    # 生成所有刻度线：每个数量级内 2,3,4,5,6,7,8,9 倍
    log_ticks = []
    for decade_power in range(1, 7):  # 10^1=10 到 10^6=1000000
        base = 10 ** decade_power
        log_ticks.append(np.log10(base))  # 主刻度（10的整数幂）
        # 中间刻度：2-9倍
        for i in range(2, 10):
            val = i * base
            if val >= 10 and val <= 1000000:
                log_ticks.append(np.log10(val))
    
    # 去重并按值排序
    log_ticks = sorted(set(log_ticks))
    
    # 绘制所有刻度竖线
    for log_val in log_ticks:
        if log_val >= log_min and log_val <= log_max:
            x_pos = ax_left + (ax_right - ax_left) * (log_val - log_min) / (log_max - log_min)
            # 判断是否为主刻度（10的整数幂）
            is_major = abs(log_val - round(log_val)) < 1e-10
            lw = 1.0 if is_major else 0.6
            ax.plot([x_pos, x_pos], [0, header_bottom_y], transform=fig.transFigure, 
                    color='black', linewidth=lw, zorder=500)
    
    # 绘制深度刻度线（只在曲线区）
    major_step = 10
    major_ticks = np.arange(depth_min, depth_max + major_step, major_step)
    major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
    
    minor_step = 1
    minor_ticks = np.arange(depth_min, depth_max + minor_step, minor_step)
    minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
    
    for depth_val in major_ticks:
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                    color='black', linewidth=1, zorder=500)
    
    for depth_val in minor_ticks:
        if depth_val not in major_ticks:
            norm_y = (depth_max - depth_val) / (depth_max - depth_min)
            fig_y = norm_y * header_bottom_y
            if 0 <= fig_y <= header_bottom_y:
                ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure, 
                        color='black', linewidth=0.6, zorder=500)


def _close_zero_segments(series, threshold=0.001):
    """
    将0值段内部设为NaN（避免绘制与左框线重叠的0直线），但在0段的
    边界保留0值，使曲线在进入/离开0段时各画一条到0的连线，实现"闭合"。

    输入: [0.3, 0.2, 0.0, 0.0, 0.0, 0.25, 0.3]  (中间为0段)
    输出: [0.3, 0.2, 0.0, NaN,  NaN,  0.0, 0.25, 0.3]
          (边界保留0→画闭合线，内部NaN→不画0直线)

    边界规则：
    - 0段起点：前一个点非0 → 保留0（画 non-zero→0 的连线）
    - 0段终点：后一个点非0 → 保留0（画 0→non-zero 的连线）
    - 0段内部：设NaN（不画线）
    - 0值在序列首尾且无相邻非0值 → 设NaN（无需闭合）
    """
    import numpy as np
    result = series.copy()
    vals = series.values
    n = len(vals)
    # NaN 不视为 0
    is_zero = np.array([(np.isfinite(v) and v <= threshold) for v in vals])

    i = 0
    while i < n:
        if is_zero[i]:
            # 找到0段的结束
            j = i
            while j + 1 < n and is_zero[j + 1]:
                j += 1
            # 0段 [i, j]
            # 仅当相邻点为有效非0值（非NaN、非0）时才保留边界0，避免NaN旁的无意义0线
            keep_start = (i > 0) and np.isfinite(vals[i - 1]) and (not is_zero[i - 1])
            keep_end   = (j < n - 1) and np.isfinite(vals[j + 1]) and (not is_zero[j + 1])
            for k in range(i, j + 1):
                if (k == i and keep_start) or (k == j and keep_end):
                    result.iloc[k] = 0.0
                else:
                    result.iloc[k] = np.nan
            i = j + 1
        else:
            i += 1
    return result


def _plot_curve(ax, curve_data, depth, color, x_range, depth_max, depth_min, curve_height_ratio, header_bottom_y, linestyle='-'):
    """绘制线性刻度曲线，只绘制有效数据区域"""
    import pandas as pd
    
    twin_ax = ax.twiny()
    
    # 同步twin_ax位置与ax一致
    ax_pos = ax.get_position()
    twin_ax.set_position(ax_pos)
    
    # 直接使用原始数据，不做任何过滤
    # 让matplotlib处理NaN值（自动断开曲线）
    line, = twin_ax.plot(curve_data, depth, color=color, linewidth=1.5, linestyle=linestyle)
    
    twin_ax.set_ylim(depth_max, depth_min)
    twin_ax.set_xlim(x_range)
    
    for spine in twin_ax.spines.values():
        spine.set_visible(False)
    twin_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                        labelbottom=False, labeltop=False, length=0)
    twin_ax.set_xticks([])


def _plot_log_curve(ax, curve_data, depth, color, x_range, depth_max, depth_min, curve_height_ratio, header_bottom_y, linewidth=1.5):
    """绘制对数刻度曲线，只绘制有效数据（>0）区域"""
    import pandas as pd
    
    twin_ax = ax.twiny()
    
    # 同步twin_ax位置与ax一致
    ax_pos = ax.get_position()
    twin_ax.set_position(ax_pos)
    
    # 将无效数据（<=0 或 NaN）设为 NaN，这样 matplotlib 会自动断开曲线
    valid_data = pd.Series(curve_data).copy()
    valid_data = valid_data.mask((valid_data <= 0) | valid_data.isna())
    
    line, = twin_ax.semilogx(valid_data, depth, color=color, linewidth=linewidth)
    
    # 暂时移除clip_rect，检查是否是裁剪导致曲线不完整
    # clip_rect = plt.Rectangle((0, 0), 1, header_bottom_y, transform=ax.figure.transFigure, 
    #                           clip_on=False, fill=False, edgecolor='none')
    # ax.add_patch(clip_rect)
    # line.set_clip_path(clip_rect)
    
    twin_ax.set_ylim(depth_max, depth_min)
    twin_ax.set_xlim(x_range)
    
    for spine in twin_ax.spines.values():
        spine.set_visible(False)
    twin_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                        labelbottom=False, labeltop=False, length=0)
    twin_ax.set_xticks([])


# ---------------------------------------------------------------------------
# 深度道单位：'auto' 自动识别，'m' 米（主刻度10/次刻度1），'ft' 英尺（主刻度100/次刻度10）
# 可调用 set_depth_unit('m'/'ft') 显式覆盖；logInt 会通过 results['depth_unit'] 传入。
# ---------------------------------------------------------------------------
DEPTH_UNIT = 'auto'


def set_depth_unit(unit):
    """显式设置深度道单位：'m' 或 'ft'；传 'auto' 恢复自动识别。"""
    global DEPTH_UNIT
    DEPTH_UNIT = str(unit).strip().lower()


def _detect_depth_unit(depth_min, depth_max):
    """单位回退判定。

    优先路径：单位来自 LAS ~C 区深度曲线的 unit 字段（如 DEPT.FEET），
    由 logInt 加载后通过 set_depth_unit('ft'/'m') 或 results['depth_unit'] 传入。

    回退判定（之前固定返回 'm'，导致英尺井的道头标成 "Depth (m)"）：
    按深度数值量级判断 —— 深度超过 1000 且不是恰好等于千米整数倍时，
    基本不可能是米（千米级整数如 3000/4000 m 也可能），因此
      · 深度 > 1500 且不为 100 的整数倍 → 判为英尺；
      · 深度 > 1500 且为 500 的整数倍     → 可能是千米（保留 m 并记录）；
      · 其余按米处理。
    """
    try:
        dmin = float(depth_min)
        dmax = float(depth_max)
    except Exception:
        return 'm'
    dtop = max(abs(dmin), abs(dmax))
    if dtop <= 1500:
        return 'm'
    # 明显是英尺：不是整百/整五百的整数倍（英尺井深度很少落在整千米上）
    for step in (1000, 500):
        if abs(dtop / step - round(dtop / step)) < 1e-6:
            return 'm'
    return 'ft'


def _setup_depth_track(ax, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y):
    """设置深度道（米：主刻度10/次刻度1；英尺：主刻度100/次刻度10）"""
    unit = DEPTH_UNIT
    if unit == 'auto':
        unit = _detect_depth_unit(depth_min, depth_max)
    if unit == 'ft':
        major_step, minor_step = 20, 10
        unit_label = 'Depth (ft)'
    else:
        major_step, minor_step = 10, 1
        unit_label = 'Depth (m)'
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)

    # 完全隐藏y轴相关内容
    ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False, labelright=False)
    ax.set_yticks([])
    ax.yaxis.set_visible(False)

    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    ax_center = (ax_left + ax_right) / 2

    # 使用figimage在figure最顶层绘制边框（确保可见）
    _draw_border(fig, ax_left, ax_right, header_top_y, header_bottom_y)

    # 图头区只显示"深度"标签和比例尺（使用figure坐标）
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.6,
            unit_label, ha='center', va='center', fontsize=12, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)
    # 比例尺在深度标签下方
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.35,
            '1:240', ha='center', va='center', fontsize=10, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)

    # 主刻度：深度数字标签（整百英尺 / 整十米）
    base = (int(depth_min) // major_step) * major_step
    major_ticks = np.arange(base, depth_max + major_step, major_step)
    major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
    label_x_center = ax_center

    for depth_val in major_ticks:
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        if fig_y < header_bottom_y - 0.01:
            ax.text(label_x_center, fig_y, f'{depth_val:.0f}', ha='center', va='center',
                    fontsize=11, fontfamily='Microsoft YaHei', transform=fig.transFigure, zorder=501)

    # 次刻度：短横线（英尺每10、米每1），不标数字
    sub_base = (int(depth_min) // minor_step) * minor_step
    minor_ticks = np.arange(sub_base, depth_max + minor_step, minor_step)
    minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
    for depth_val in minor_ticks:
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        if fig_y >= header_bottom_y - 0.005:
            continue
        ax.plot([ax_left, ax_left + (ax_right - ax_left) * 0.18], [fig_y, fig_y],
                color='black', lw=0.5, transform=fig.transFigure, zorder=500)


def _draw_track_name(fig, ax_left, ax_right, header_top_y, header_bottom_y, track_name, display_name):
    """在图头区绘制道名（用于无有效曲线时的占位显示）"""
    header_mid_y = (header_top_y + header_bottom_y) / 2
    header_mid_x = (ax_left + ax_right) / 2
    fig.text(header_mid_x, header_mid_y, display_name, ha='center', va='center',
             fontsize=7, fontfamily='Microsoft YaHei', transform=fig.transFigure,
             color='gray', style='italic')


def _setup_lithology_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """设置岩性剖面道（有效曲线不足3条的井段留空白）"""
    ax.set_xlim(0, 0.5)  # 缩小填充范围至0-0.5
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 边框已在主函数中统一绘制，这里不再单独绘制
    
    # 检查是否有足够的有效曲线
    has_valid_curves = False
    if 'VALID_CURVES_COUNT' in data.columns:
        has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3
    
    # 如果没有足够的有效曲线，只绘制道名，不绘制岩性
    if not has_valid_curves:
        _draw_track_name(fig, ax_left, ax_right, header_top_y, header_bottom_y, 'LITHOLOGY', 'LITHOLOGY')
        return
    
    # 岩性类型列表（从数据中动态提取，只显示井中实际出现的岩性）
    lith_types_raw = []
    if has_enough_curves and 'LITHOLOGY' in data.columns:
        unique_liths = set(data['LITHOLOGY'].dropna().unique())
        # 统一转首字母大写用于显示
        lith_types_raw = sorted([str(l).strip().title() for l in unique_liths if str(l).strip()])
    # 如果数据中没有岩性信息，使用默认列表（仅常见岩性，避免过多图例压缩logo）
    if not lith_types_raw:
        lith_types_raw = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
    lith_types = lith_types_raw
    # 过滤非岩性类型：Mixed 是混合剖面类型，不是具体岩性，不纳入岩性图例
    lith_types = [lt for lt in lith_types if lt.lower() not in ('mixed',)]
    if not lith_types:
        lith_types = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
    
    # ========== 曲线区：使用符号图片填充岩性 ==========
    if has_enough_curves and 'LITHOLOGY' in data.columns:
        # 岩性值到符号的映射（统一转小写）
        lithology_symbol_map = {k.lower(): k for k in lith_types}
        
        # 分组：连续相同岩性的深度段
        # 第一步：逐段分组收集所有岩性段
        i = 0
        n = len(data)
        raw_segments = []  # [(start_md, end_md, lith_key), ...]
        while i < n - 1:
            valid_count = data.iloc[i].get('VALID_CURVES_COUNT', 0)
            if valid_count < 3:
                i += 1
                continue
            
            lithology = data.iloc[i]['LITHOLOGY']
            lith_key = str(lithology).lower()
            
            # 跳过空字符串的岩性（有效曲线不足3条时不解释）
            # 跳过'mixed'（混合剖面类型，不是具体岩性，图例中已排除）
            if not lith_key or lith_key == 'nan' or lith_key == 'none' or lith_key == 'mixed':
                i += 1
                continue
                
            seg_start_md = data.iloc[i]['MD']
            
            j = i + 1
            while j < n:
                vc = data.iloc[j].get('VALID_CURVES_COUNT', 0)
                if vc < 3:
                    break
                if str(data.iloc[j]['LITHOLOGY']).lower() != lith_key:
                    break
                j += 1
            
            seg_end_md = data.iloc[min(j, n - 1)]['MD']
            raw_segments.append((seg_start_md, seg_end_md, lith_key))
            i = j
        
        # 第二步：合并薄层到相邻大层
        merged_segments = _merge_thin_layers(raw_segments)

        # 第三步：绘制合并后的段
        for seg_start_md, seg_end_md, lith_key in merged_segments:
            _draw_lithology_tiles(ax, lith_key, seg_start_md, seg_end_md)

    # ========== 道头图例：只列本道实际出现的岩性 ==========
    # 布局与 profile 道一致：横向铺满整道宽、竖向无空隙叠置、文字上下左右居中。
    from matplotlib.lines import Line2D as _L2D
    # 统计本段实际出现的岩性（按厚度降序，保证图例稳定）
    seg_thick = {}
    for seg_start_md, seg_end_md, lith_key in merged_segments:
        seg_thick[lith_key] = seg_thick.get(lith_key, 0.0) + (seg_end_md - seg_start_md)
    present = [k for k, _ in sorted(seg_thick.items(), key=lambda x: -x[1])]
    if not present:
        return
    hh = header_top_y - header_bottom_y
    n = len(present)
    ih = hh / n
    tw = ax_right - ax_left
    bx, bw, bh = ax_left, tw, ih
    for i, lith_key in enumerate(present):
        y_top = header_top_y - i * ih
        by = y_top - bh
        _draw_track_legend_row(fig, bx, by, bw, bh, _lith_cn_name(lith_key),
                               lith_key, _lith_bg_color(lith_key))
        if i > 0:
            from matplotlib.lines import Line2D as _L2
            fig.add_artist(_L2([bx, bx + bw], [y_top, y_top], color='k',
                               lw=0.5, transform=fig.transFigure, zorder=6004))


def _setup_facies_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """设置沉积相道（完整外框，有效曲线不足3条的井段留空白）"""
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 边框已在主函数中统一绘制，这里不再单独绘制
    
    # 检查是否有足够的有效曲线
    has_valid_curves = False
    if 'VALID_CURVES_COUNT' in data.columns:
        has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3
    
    # 如果没有足够的有效曲线，只绘制道名，不绘制沉积相
    if not has_valid_curves:
        _draw_track_name(fig, ax_left, ax_right, header_top_y, header_bottom_y, 'FACIES', 'FACIES')
        return
    
    facies_colors = {
        'Channel': 'firebrick',
        'Floodplain': 'sandybrown',
        'Delta Front': 'wheat',
        'Prodelta': 'darkolivegreen'
    }
    
    if has_enough_curves and 'FACIES' in data.columns:
        facies_color_map = {
            'underwater_distributary_channel': 'darkred',
            'mouth_bar': 'orange',
            'distal_bar': 'gold',
            'sheet_sand': 'lightyellow',
            'interdistributary_bay': 'lightblue',
            'distributary_channel': 'red',
            'natural_levee': 'coral',
            'crevasse_splay': 'tomato',
            'flood_plain': 'limegreen',
            'swamp': 'forestgreen',
            'prodelta_mud': 'olive',
            'deep_lake_mud': 'slategray',
            'shallow_lake_mud': 'lightgray',
            'channel': 'firebrick',
            'flood_plain': 'sandybrown',
            'sandy_deposit': 'wheat',
            'transition': 'khaki',
            'muddy_deposit': 'darkolivegreen',
            # 沼泽相组（煤与碳质泥岩同属沼泽环境，有机质富集程度不同）
            'swamp_peatro': 'black',                # 沼泽泥炭相（煤层，有机质极富集）
            'swamp_carbonaceous': '#5C6B5C',        # 沼泽碳质泥岩相（有机质中富集）
            'carbonaceous_mud': '#5C6B5C',          # 兼容旧名
            'unknown': 'white'
        }
        
        # 暂时移除clip_rect，检查是否是裁剪导致曲线不完整
        # clip_rect = plt.Rectangle((0, 0), 1, curve_height_ratio, transform=ax.transAxes,
        #                           clip_on=False, fill=False, edgecolor='none')
        # ax.add_patch(clip_rect)
        
        # 第一步：逐段分组收集所有沉积相段
        n = len(data)
        i = 0
        raw_segments = []
        while i < n - 1:
            valid_count = data.iloc[i].get('VALID_CURVES_COUNT', 0)
            if valid_count < 3:
                i += 1
                continue
            
            facies = data.iloc[i]['FACIES']
            
            # 跳过空字符串的沉积相（有效曲线不足3条时不解释）
            if not facies or str(facies) == 'nan' or str(facies) == 'none':
                i += 1
                continue
                
            seg_start_md = data.iloc[i]['MD']
            
            j = i + 1
            while j < n:
                vc = data.iloc[j].get('VALID_CURVES_COUNT', 0)
                if vc < 3:
                    break
                if data.iloc[j]['FACIES'] != facies:
                    break
                j += 1
            
            seg_end_md = data.iloc[min(j, n - 1)]['MD']
            raw_segments.append((seg_start_md, seg_end_md, facies))
            i = j
        
        # 第二步：合并薄层到相邻大层
        merged_segments = _merge_thin_layers(raw_segments)
        
        # 第三步：绘制合并后的段
        for seg_start_md, seg_end_md, facies in merged_segments:
            color = facies_color_map.get(facies, '#D3D3D3')
            ax.fill_betweenx([seg_start_md, seg_end_md], 0, 0.5, color=color, alpha=0.8)


# 矿物组分 → symbol图片 映射
# Quartz使用Sandstone.png与岩性道保持一致
MINERAL_TO_SYMBOL = {
    'Quartz':    'Sandstone.png',
    'Calcite':   'Limestone.png',
    'Dolomite':  'Dolomite.png',
    'Anhydrite': 'Anhydrite.png',
    'Halite':    'Salt.png',
    'Clay':      'Shale.png',
    'Porosity':  'Gas.png',
}
# symbol图片缓存
_mineral_symbol_cache = {}

def _load_mineral_symbol(name):
    """加载矿物symbol图片（带缓存）"""
    if name in _mineral_symbol_cache:
        return _mineral_symbol_cache[name]
    
    symbol_file = MINERAL_TO_SYMBOL.get(name)
    if symbol_file:
        img_path = os.path.join(SYMBOL_DIR, symbol_file)
        if os.path.exists(img_path):
            try:
                img = plt.imread(img_path)
                # 转换为RGB（处理RGBA）
                if img.ndim == 3 and img.shape[2] == 4:
                    # RGBA → RGB（白色背景）
                    from PIL import Image as PILImage
                    pil_img = PILImage.fromarray((img * 255).astype(np.uint8))
                    if pil_img.mode == 'RGBA':
                        background = PILImage.new('RGBA', pil_img.size, (255, 255, 255, 255))
                        pil_img = PILImage.alpha_composite(background, pil_img).convert('RGB')
                    img = np.array(pil_img) / 255.0
                _mineral_symbol_cache[name] = img
                return img
            except Exception as e:
                logger.warning(f"加载矿物symbol图片失败 {img_path}: {e}")
    
    _mineral_symbol_cache[name] = None
    return None



def _setup_profile_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """矿物比例堆叠 profile 道。

    布局约定（用户确认）：
      · 泥岩固定在最左侧 → 孔隙度（右侧留白）因此只会在储层岩性里"开"出来，
        不会在泥岩、煤、盐岩等非储层岩性里出现；
      · 储层段矿物按 (1-φ) 归一铺满左侧，剩余右侧留白即孔隙度；
      · 非储层段（φ≈0）由主矿物填满整道，不含孔隙度；
      · 配色与符号统一走 LITH_BG_COLORS / LITHOLOGY_TO_SYMBOL，与岩性道完全一致。
    """

    PROFILE_MINERALS = PROFILE_MINERAL_ORDER
    # 配色统一取自岩性底色表，避免 profile 道与岩性道颜色不一致
    _COLORS = {name: _lith_bg_color(name) for _, _, _, name, _ in PROFILE_MINERALS}
    _KIND_BY_LITH = {name: kind for _, _, _, name, kind in PROFILE_MINERALS}

    def _sym_dots(a, x0, x1, y0, y1, rows=3, cols=3):
        for r in range(rows):
            for c in range(cols):
                a.plot([x0 + (c + 0.5) / cols * (x1 - x0)],
                       [y0 + (r + 0.5) / rows * (y1 - y0)],
                       'o', color='k', ms=1.0, mew=0, zorder=20)

    def _sym_dash(a, x0, x1, y0, y1):
        for fy in (0.32, 0.68):
            y = y0 + fy * (y1 - y0)
            a.plot([x0 + 0.12 * (x1 - x0), x1 - 0.12 * (x1 - x0)], [y, y],
                   '-', color='k', lw=0.6, zorder=20)

    def _sym_brick(a, x0, x1, y0, y1):
        y = y0 + 0.5 * (y1 - y0)
        a.plot([x0, x1], [y, y], '-', color='k', lw=0.5, zorder=20)
        for fx in (0.35, 0.7):
            x = x0 + fx * (x1 - x0)
            a.plot([x, x], [y0, y1], '-', color='k', lw=0.4, zorder=20)

    _SYM = {'dots': _sym_dots, 'dash': _sym_dash, 'brick': _sym_brick,
            'blank': lambda *a_, **k_: None}

    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    # 白色底衬：右侧未填充区即孔隙度，必须是白色（不能透出 figure 灰底）
    ax.set_facecolor('white')
    ax.patch.set_alpha(1.0)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    ax.tick_params(axis='y', which='both', left=False, right=False,
                   labelleft=False, labelright=False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig = ax.figure
    pos = ax.get_position()
    logger.info(f"PROFILE道位置: x0={pos.x0:.4f} x1={pos.x1:.4f} y0={pos.y0:.4f} y1={pos.y1:.4f}")
    _draw_border(fig, pos.x0, pos.x1, header_top_y, header_bottom_y)

    # ---------- 收集数据 ----------
    col_of = [next((c for c in cand if c in data.columns), None)
              for cand, _, _, _, _ in PROFILE_MINERALS]
    if not any(col_of):
        logger.warning("PROFILE道缺少矿物列（VQuartz/VClay等），跳过绘制")
        return
    t = data[(data.MD >= depth_min) & (data.MD <= depth_max)]
    if 'VALID_CURVES_COUNT' in t.columns:
        t = t[t.VALID_CURVES_COUNT >= 3]
    if len(t) < 2:
        return
    md = t['MD'].values.astype(float)
    phi = (pd.to_numeric(t['PHI'], errors='coerce').values
           if 'PHI' in t.columns else np.zeros(len(t)))
    phi = np.clip(np.nan_to_num(phi, nan=0.0), 0.0, 1.0)
    liths = (t['LITHOLOGY'].astype(str).str.lower().str.strip().values
             if 'LITHOLOGY' in t.columns else np.array([''] * len(t)))
    k = len(PROFILE_MINERALS)
    mv = np.zeros((len(t), k))
    for j, cc in enumerate(col_of):
        if cc:
            mv[:, j] = np.clip(np.nan_to_num(
                pd.to_numeric(t[cc], errors='coerce').values), 0, 1)

    # ---------- 累积边界 ----------
    # 储层：矿物按 PROFILE_MINERAL_ORDER 顺序（泥岩在最左）铺满左侧 (1-φ)，
    #       右侧剩余宽度即孔隙度（留白）。
    # 非储层（φ≈0）：由该岩性对应的矿物/主矿物填满整道，**不含孔隙度**，
    #       这样孔隙度就不会"开"在泥岩、煤、盐岩等非储层岩性里。
    bounds = np.zeros((len(t), k + 2))
    lith2j = {item[1]: j for j, item in enumerate(PROFILE_MINERALS)}
    # 不在矿物列表里的岩性（煤/岩盐/火成岩/砾岩…）→ 整道平铺该岩性自己的符号
    other = np.array([liths[i] if liths[i] not in lith2j else ''
                      for i in range(len(t))])
    for i in range(len(t)):
        p = phi[i]
        if p <= 1e-6:
            j = lith2j.get(liths[i])
            if j is None:
                j = int(np.argmax(mv[i])) if mv[i].sum() > 0 else 0
            bounds[i, 1:j + 1] = 0.0
            bounds[i, j + 1] = 1.0
            bounds[i, k + 1] = 1.0
        else:
            s = mv[i].sum()
            target = 1.0 - p
            acc = 0.0
            for j in range(k):
                if s > 1e-9:
                    acc += mv[i, j] / s * target
                bounds[i, j + 1] = min(acc, target)
            bounds[i, k + 1] = target
    for j in range(1, k + 2):
        bounds[:, j] = np.maximum(bounds[:, j], bounds[:, j - 1])

    # ---------- 非矿物岩性（煤/岩盐/火成岩/砾岩…）整道平铺自己的符号 ----------
    scale = _axes_data_per_px(ax)
    for lname in dict.fromkeys(x for x in other if x):
        msk = other == lname
        if not msk.any():
            continue
        ax.fill_betweenx(md[msk], 0.0, 1.0, color=_lith_bg_color(lname),
                         alpha=1.0, lw=0, zorder=8)
        if _lith_needs_frame(lname):
            zb = md[msk]
            ax.plot([0, 0, 1, 1], [zb.min(), zb.max(), zb.max(), zb.min()],
                    color='#9AA0A6', lw=0.5, zorder=11)
        if _lith_pattern_kind(lname) == 'image':
            if scale is not None:
                dy = max(LITH_PATTERN_PITCH_PX_DASH * abs(scale[1]), 1e-6)
            else:
                dy = max((md.max() - md.min()) / 200.0, 1e-6)
            for dd in np.arange(md.min() + dy / 2.0, md.max(), dy):
                if not (md.min() <= dd <= md.max()):
                    continue
                if not msk[np.argmin(np.abs(md - dd))]:
                    continue
                _tile_symbol_physical(ax, lname, dd - dy / 2.0, dd + dy / 2.0,
                                      0.0, 1.0, zorder=10)

    # ---------- 逐矿物带 + 统一符号（与岩性道同一函数、同一物理间距、同一颜色） ----------
    for j, (cand, lname, cname, color_key, kind) in enumerate(PROFILE_MINERALS):
        xl = bounds[:, j]
        xr = bounds[:, j + 1]
        if (xr - xl).max() <= 1e-4:
            continue
        # 非矿物岩性段已被整道平铺覆盖，跳过避免叠加
        keep = np.ones(len(t), dtype=bool)
        keep[other != ''] = False
        if not keep.any():
            continue
        xl_m = np.where(keep, xl, 0.0)
        xr_m = np.where(keep, xr, 0.0)
        ax.fill_betweenx(md, xl_m, xr_m, color=_lith_bg_color(lname), alpha=1.0,
                         lw=0, zorder=8)
        if _lith_needs_frame(lname):
            # 白底淡纹：沿该矿物带左右边界 + 顶底画淡框，否则图案几乎看不见
            ax.plot([xl_m[0], xl_m[0], xr_m[0], xr_m[0], xl_m[0]],
                    [md[0], md[-1], md[-1], md[0], md[0]],
                    color='#9AA0A6', lw=0.6, zorder=11)
        # 像素等间距取行 → 逐行调用统一符号函数，profile道与岩性道图案一致
        if scale is not None:
            pitch = (LITH_PATTERN_PITCH_PX if kind == 'dots'
                     else LITH_PATTERN_PITCH_PX_DASH)
            dy = max(pitch * abs(scale[1]), 1e-6)
        else:
            dy = max((md.max() - md.min()) / 200.0, 1e-6)
        pts_x, pts_y, pts_kind = [], [], None
        for dd in np.arange(md.min() + dy / 2.0, md.max(), dy):
            ii = int(np.argmin(np.abs(md - dd)))
            if not keep[ii]:
                continue
            xll = float(np.interp(dd, md, xl))
            xrr = float(np.interp(dd, md, xr))
            if xrr - xll < 0.012:
                continue
            k2, px, py = _lith_pattern_points(ax, lname,
                                              dd - dy / 2.0, dd + dy / 2.0, xll, xrr)
            if k2 == 'image':
                # 灰岩/白云岩等图例型岩性：按物理正方形平铺原图（网格全局对齐，逐行叠加连续）
                _tile_symbol_physical(ax, lname, dd - dy / 2.0, dd + dy / 2.0,
                                      xll, xrr, zorder=10)
                continue
            if not len(px):
                continue
            pts_kind = k2
            pts_x.extend(px)
            pts_y.extend(py)
        if pts_x:
            _plot_lith_points(ax, pts_kind, pts_x, pts_y, zorder=10)

    ax.plot([0, 0, 1, 1, 0],
            [md.min(), md.max(), md.max(), md.min(), md.min()],
            color='k', lw=0.5, zorder=12)

    # ---------- 道头图例 ----------
    # 布局要求（用户确认）：
    #   · **只列本道实际出现**的矿物/岩性（vis 依据实际带宽 >= 5% 判定）；
    #   · 每个条目**横向铺满整个道宽**，条目之间竖向不留空隙、依次叠置；
    #   · 条目内：符号方块在左，文字在整个条目内上下左右居中。
    hh = header_top_y - header_bottom_y
    vis = [j for j in range(k)
           if (bounds[:, j + 1] - bounds[:, j]).max() >= 0.05]
    # 本道实际出现的非矿物岩性（煤/岩盐/火成岩/砾岩…）也进图例
    seen_other = [lname for lname in dict.fromkeys(x for x in other if x)]
    items = [(PROFILE_MINERALS[j][2], _lith_bg_color(PROFILE_MINERALS[j][1]),
              PROFILE_MINERALS[j][1], PROFILE_MINERALS[j][4]) for j in vis]
    for lname in seen_other:
        if lname not in [it[2] for it in items]:
            items.append((_lith_cn_name(lname), _lith_bg_color(lname), lname,
                          _lith_pattern_kind(lname)))
    items.append(('孔隙度', 'white', None, 'blank'))
    n = len(items)
    if n == 0:
        return
    from matplotlib.lines import Line2D as _L2D
    ih = hh / n                       # 竖向等分，条目紧贴，无空隙
    tw = pos.x1 - pos.x0
    bx = pos.x0                        # 横向铺满整道宽
    bw = tw
    bh = ih                           # 竖向不留空隙（满格）
    for i, (label, color, lname, kind) in enumerate(items):
        y_top = header_top_y - i * ih
        by = y_top - bh
        _draw_track_legend_row(fig, bx, by, bw, bh, label, lname, color)
        # 条目间分隔线（叠置边界）
        if i > 0:
            from matplotlib.lines import Line2D as _L2
            fig.add_artist(_L2([bx, bx + bw], [y_top, y_top], color='k',
                               lw=0.5, transform=fig.transFigure, zorder=6004))

def _setup_interpretation_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """设置测井解释道（完整外框，有效曲线不足3条的井段留空白）"""
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    # 获取当前axes在figure中的位置
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    
    # 边框已在主函数中统一绘制，这里不再单独绘制
    
    # 检查是否有足够的有效曲线
    has_valid_curves = False
    if 'VALID_CURVES_COUNT' in data.columns:
        has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3
    
    # 如果没有足够的有效曲线，只绘制道名，不绘制解释结论
    if not has_valid_curves:
        _draw_track_name(fig, ax_left, ax_right, header_top_y, header_bottom_y, 'INTERPRETATION', 'INTERPRETATION')
        return
    
    interpretation_colors = {
        'Oil': 'green',
        'Gas': 'red',
        'Water': 'blue',
        'Dry': 'saddlebrown'
    }

    if has_enough_curves and 'INTERPRETATION' in data.columns:
        interp_color_map = {
            'OIL': 'green',
            'GAS': 'red',
            'WATER': 'blue',
            'DRY': 'saddlebrown',
            'OIL_POSSIBLE': 'lightgreen',
            'GAS_POSSIBLE': 'lightcoral',
            'Undefined': 'gray',
            'Oil': 'green',
            'Gas': 'red',
            'Water': 'blue',
            'Dry': 'saddlebrown',
            '可疑层': 'palegreen'
        }
        
        clip_rect = plt.Rectangle((0, 0), 1, curve_height_ratio, transform=ax.transAxes,
                                  clip_on=False, fill=False, edgecolor='none')
        ax.add_patch(clip_rect)
        
        # 第一步：逐段分组收集所有解释段（排除 Undefined/Non-Reservoir）
        n = len(data)
        i = 0
        raw_segments = []
        while i < n - 1:
            valid_count = data.iloc[i].get('VALID_CURVES_COUNT', 0)
            if valid_count < 3:
                i += 1
                continue
            
            interpretation = data.iloc[i]['INTERPRETATION']
            
            # 跳过空字符串的解释结论（有效曲线不足3条时不解释）
            if not interpretation or str(interpretation) == 'nan' or str(interpretation) == 'none':
                i += 1
                continue
                
            seg_start_md = data.iloc[i]['MD']
            
            j = i + 1
            while j < n:
                vc = data.iloc[j].get('VALID_CURVES_COUNT', 0)
                if vc < 3:
                    break
                if data.iloc[j]['INTERPRETATION'] != interpretation:
                    break
                j += 1
            
            seg_end_md = data.iloc[min(j, n - 1)]['MD']
            # NonReservoir作为分隔段保留（不绘制色块），但阻止合并跨越
            if interpretation not in ('Undefined', '', 'nan', 'none'):
                raw_segments.append((seg_start_md, seg_end_md, interpretation))
            i = j

        # 第二步：合并薄层到相邻大层（NonReservoir段不会被合并跨越）
        merged_segments = _merge_thin_layers(raw_segments)

        # 第三步：绘制合并后的段，油气水层从顶到底统一编号
        # NonReservoir段留白不绘制（作为分隔屏障阻止合并，但不绘制任何色块/线）
        layer_num = 0
        hc_count = 0
        for seg_start_md, seg_end_md, interpretation in merged_segments:
            # 干层DRY不绘制
            if interpretation == 'DRY':
                continue
            # NonReservoir段留白，不绘制任何元素
            if interpretation in ('NonReservoir', 'Non-Reservoir'):
                continue
            color = interp_color_map.get(interpretation, 'white')
            hc_count += 1
            # 彩色块
            patch = ax.fill_betweenx([seg_start_md, seg_end_md], 0, 0.5, color=color, alpha=0.8, zorder=2)
            patch.set_clip_path(clip_rect)

            # 统一编号：从井顶部到底部，每个油气水层依次编号
            layer_num += 1
            mid_md = (seg_start_md + seg_end_md) / 2.0
            txt = ax.text(0.75, mid_md, str(layer_num),
                          ha='center', va='center', fontsize=7, fontweight='bold',
                          color='black', clip_on=True, zorder=5)
            txt.set_clip_path(clip_rect)

        logger.info(f'解释道绘制完成: 油气水层{hc_count}个')


def _find_column(data, possible_names):
    """查找可能的列名"""
    for name in possible_names:
        if name in data.columns:
            return name
    return None


def _find_gas_columns(gas_data):
    """识别气测数据中的气体组分列，按常见优先级排序（先精确匹配，再模糊匹配）
    
    Args:
        gas_data: 气测数据 DataFrame
        
    Returns:
        list: 识别到的气体组分列名列表（按优先级排序）
    """
    # 常见气测组分列名（按显示优先级排序）
    gas_candidates = [
        ['TG', 'TOTGAS', 'TOTALGAS', 'TOTAL_GAS', 'GAS_TOTAL', 'GAS', 'TOTAL', 'TOTG'],  # 全烃
        ['C1', 'C1PCT', 'METHANE', 'CH4', 'C1_PCT', 'C1%', 'METHAN', 'ME'],              # 甲烷
        ['C2', 'C2PCT', 'ETHANE', 'C2H6', 'C2_PCT', 'C2%', 'ETHAN', 'ET'],               # 乙烷
        ['C3', 'C3PCT', 'PROPANE', 'C3H8', 'C3_PCT', 'C3%', 'PROPAN', 'PR'],             # 丙烷
        ['C4', 'C4PCT', 'BUTANE', 'C4%', 'C4_PCT'],                                       # 总丁烷(C4)
        ['IC4', 'IC4PCT', 'I-C4', 'iC4', 'IC4_PCT'],                                      # 异丁烷
        ['NC4', 'NC4PCT', 'N-C4', 'nC4', 'NC4_PCT'],                                      # 正丁烷
        ['C5', 'C5PCT', 'PENTANE', 'C5%', 'C5_PCT'],                                      # 总戊烷(C5)
        ['IC5', 'IC5PCT', 'I-C5', 'iC5', 'IC5_PCT'],                                      # 异戊烷
        ['NC5', 'NC5PCT', 'N-C5', 'nC5', 'NC5_PCT'],                                      # 正戊烷
        ['C6', 'C6%', 'HEXANE', 'C6PCT'],                                                  # 己烷(C6)
        ['C7', 'C7%', 'HEPTANE', 'C7PCT'],                                                 # 庚烷(C7)
        ['C8', 'C8%', 'OCTANE', 'C8PCT'],                                                  # 辛烷(C8)
        ['MCH', 'METHYLCYCLOHEXANE', 'C7H14', '甲基环己烷'],                              # 甲基环己烷
        ['BZ', 'BENZENE', 'C6H6', '苯'],                                                    # 苯
        ['TL', 'TOLUENE', 'C7H8', '甲苯'],                                                  # 甲苯
        ['H2', 'HYDROGEN', 'HYDRO'],                                                        # 氢气
        ['CO2', 'CARBON_DIOXIDE', 'CARBONDIOXIDE'],                                        # 二氧化碳
        ['H2S', 'HYDROGEN_SULFIDE'],                                                        # 硫化氢
    ]
    
    logger.debug(f"气测数据列名: {list(gas_data.columns)}")
    
    found_cols = []
    for candidates in gas_candidates:
        # 1. 精确匹配
        col = _find_column(gas_data, candidates)
        # 2. 模糊匹配（列名中包含关键词）
        if col is None:
            col = next(
                (c for c in gas_data.columns
                 if any(keyword in c.upper().strip() for keyword in candidates)),
                None
            )
            if col:
                logger.debug(f"气测组分模糊匹配: {candidates[0]} ← {col}")
        if col and col not in found_cols:
            found_cols.append(col)
    
    logger.debug(f"气测组分识别结果: {found_cols}")
    return found_cols


if __name__ == "__main__":
    # 构造更有真实地质意义的模拟数据
    test_depth = np.arange(1000, 1200, 0.1)
    n_test = len(test_depth)
    
    # 构造沉积旋回：砂泥岩互层 + 部分碳酸盐岩夹层
    # 深度段划分：
    #   1000-1020: 泥岩段 (高粘土含量)
    #   1020-1050: 砂岩段 (高石英含量，孔隙度较高)
    #   1050-1070: 泥岩段
    #   1070-1100: 碳酸盐岩段 (高方解石/白云石含量)
    #   1100-1140: 砂泥岩互层
    #   1140-1160: 硬石膏段
    #   1160-1200: 砂岩段
    
    def get_lithology(depth):
        if depth < 1020:
            return 'shale'
        elif depth < 1050:
            return 'sandstone'
        elif depth < 1070:
            return 'shale'
        elif depth < 1100:
            return 'carbonate'
        elif depth < 1140:
            return 'mixed'
        elif depth < 1160:
            return 'carbonate'  # 硬石膏
        else:
            return 'sandstone'
    
    def get_facies(depth):
        if depth < 1020:
            return 'prodelta_mud'
        elif depth < 1050:
            return 'channel'
        elif depth < 1070:
            return 'flood_plain'
        elif depth < 1100:
            return 'carbonate_platform'
        elif depth < 1140:
            return 'mixed_fluvial'
        elif depth < 1160:
            return 'evaporite'
        else:
            return 'distributary_channel'
    
    def get_interp(depth):
        if depth < 1020:
            return 'WATER'
        elif depth < 1050:
            return 'OIL'
        elif depth < 1070:
            return 'WATER'
        elif depth < 1100:
            return 'DRY'
        elif depth < 1140:
            return 'OIL'
        elif depth < 1160:
            return 'DRY'
        else:
            return 'GAS'
    
    # 根据深度计算矿物含量（带有渐变过渡）
    def compute_mineral_composition(depth):
        """计算矿物含量，总量为1"""
        if depth < 1020:
            # 泥岩段
            qtz = 0.25 + 0.05 * np.sin((depth - 1000) * 0.3)
            clay = 0.60 + 0.05 * np.sin((depth - 1000) * 0.3 + 1)
            cal = 0.03 * np.sin((depth - 1000) * 0.2)
            dol = 0.02 * np.sin((depth - 1000) * 0.25)
            anh = 0.01
            phi = 0.10
        elif depth < 1050:
            # 砂岩段 - 高石英，高孔隙
            t = (depth - 1020) / 30  # 归一化
            qtz = 0.65 + 0.08 * np.sin(t * 4 * np.pi)
            clay = 0.12 + 0.03 * np.sin(t * 4 * np.pi + 2)
            cal = 0.04 * np.sin(t * 3 * np.pi)
            dol = 0.03 * np.sin(t * 3 * np.pi + 1)
            anh = 0.01
            phi = 0.18 + 0.04 * np.sin(t * 2 * np.pi)
        elif depth < 1070:
            # 泥岩段
            t = (depth - 1050) / 20
            qtz = 0.28 + 0.04 * np.sin(t * 5 * np.pi)
            clay = 0.58 + 0.04 * np.sin(t * 5 * np.pi + 2)
            cal = 0.04 * np.sin(t * 4 * np.pi)
            dol = 0.03
            anh = 0.02
            phi = 0.08
        elif depth < 1100:
            # 碳酸盐岩段 - 高方解石/白云石
            t = (depth - 1070) / 30
            qtz = 0.08 + 0.03 * np.sin(t * 3 * np.pi)
            clay = 0.08 + 0.02 * np.sin(t * 3 * np.pi + 1)
            cal = 0.55 + 0.08 * np.sin(t * 2 * np.pi)
            dol = 0.18 + 0.05 * np.sin(t * 2 * np.pi + 2)
            anh = 0.02 * np.sin(t * 5 * np.pi)
            phi = 0.09
        elif depth < 1140:
            # 砂泥岩互层
            t = (depth - 1100) / 40
            # 使用正弦波模拟砂泥岩交替
            sand_ratio = 0.5 + 0.4 * np.sin(t * 4 * np.pi)
            qtz = 0.30 + 0.35 * sand_ratio
            clay = 0.30 + 0.35 * (1 - sand_ratio)
            cal = 0.05
            dol = 0.05
            anh = 0.02
            phi = 0.15 + 0.05 * sand_ratio
        elif depth < 1160:
            # 硬石膏段
            t = (depth - 1140) / 20
            qtz = 0.05
            clay = 0.10
            cal = 0.05
            dol = 0.05
            anh = 0.65 + 0.10 * np.sin(t * 3 * np.pi)
            phi = 0.10
        else:
            # 砂岩段 - 气层
            t = (depth - 1160) / 40
            qtz = 0.70 + 0.05 * np.sin(t * 2 * np.pi)
            clay = 0.10 + 0.02 * np.sin(t * 2 * np.pi + 1)
            cal = 0.03
            dol = 0.03
            anh = 0.01
            phi = 0.16 + 0.03 * np.sin(t * 3 * np.pi)
        
        total = qtz + clay + cal + dol + anh + phi
        return {
            'qtz': qtz / total,
            'clay': clay / total,
            'cal': cal / total,
            'dol': dol / total,
            'anh': anh / total,
            'phi': phi / total
        }
    
    # 生成数据
    vqtz_list, vclay_list, vcal_list, vdol_list, vanh_list, phi_list = [], [], [], [], [], []
    lithology_list, facies_list, interp_list = [], [], []
    
    for d in test_depth:
        comp = compute_mineral_composition(d)
        vqtz_list.append(comp['qtz'])
        vclay_list.append(comp['clay'])
        vcal_list.append(comp['cal'])
        vdol_list.append(comp['dol'])
        vanh_list.append(comp['anh'])
        phi_list.append(comp['phi'])
        lithology_list.append(get_lithology(d))
        facies_list.append(get_facies(d))
        interp_list.append(get_interp(d))
    
    vqtz = np.array(vqtz_list)
    vclay = np.array(vclay_list)
    vcal = np.array(vcal_list)
    vdol = np.array(vdol_list)
    vanh = np.array(vanh_list)
    phi = np.array(phi_list)
    
    # 生成测井曲线（基于岩性的真实响应）
    # GR: 泥岩高，砂岩中等，碳酸盐岩低
    gr_base = np.zeros(n_test)
    for i, d in enumerate(test_depth):
        if d < 1020:
            gr_base[i] = 140 + 20 * np.sin(d * 0.2)
        elif d < 1050:
            gr_base[i] = 60 + 15 * np.sin(d * 0.15)
        elif d < 1070:
            gr_base[i] = 150 + 15 * np.sin(d * 0.2)
        elif d < 1100:
            gr_base[i] = 30 + 10 * np.sin(d * 0.1)
        elif d < 1140:
            gr_base[i] = 50 + 80 * (0.5 + 0.5 * np.sin(d * 0.1))
        elif d < 1160:
            gr_base[i] = 20 + 10 * np.sin(d * 0.3)
        else:
            gr_base[i] = 55 + 10 * np.sin(d * 0.1)
    
    # DEN: 砂岩~2.65，泥岩~2.55，碳酸盐~2.70，硬石膏~2.95
    den_base = 2.65 - 0.15 * vclay + 0.08 * vcal + 0.22 * vanh - 0.15 * phi + np.random.normal(0, 0.01, n_test)
    
    # CNL: 泥岩高，孔隙度高
    nphi_base = 0.35 * vclay + 0.05 * vqtz + 0.02 * vcal + 0.20 * phi + np.random.normal(0, 0.02, n_test)
    
    # AC: 砂岩~55，泥岩~80，碳酸盐~45，孔隙度增加
    dt_base = 55 * vqtz + 80 * vclay + 45 * (vcal + vdol) + 120 * phi + np.random.normal(0, 1.5, n_test)
    
    # PE: 砂岩~1.8，泥岩~3.5，碳酸盐~5，硬石膏~5
    pe_base = 1.8 * vqtz + 3.5 * vclay + 5.0 * (vcal + vdol) + 5.0 * vanh + np.random.normal(0, 0.1, n_test)
    
    # RT: 水层低阻，油层高阻，气层中阻
    rt_base = np.zeros(n_test)
    for i, d in enumerate(test_depth):
        if d < 1020:  # 水层泥岩
            rt_base[i] = 10 + np.random.normal(0, 2)
        elif d < 1050:  # 油层砂岩
            rt_base[i] = 80 + np.random.normal(0, 15)
        elif d < 1070:  # 水层泥岩
            rt_base[i] = 8 + np.random.normal(0, 2)
        elif d < 1100:  # 干层碳酸盐
            rt_base[i] = 200 + np.random.normal(0, 50)
        elif d < 1140:  # 油水层
            rt_base[i] = 30 + 80 * (0.5 + 0.5 * np.sin(d * 0.1)) + np.random.normal(0, 5)
        elif d < 1160:  # 干层硬石膏
            rt_base[i] = 500 + np.random.normal(0, 100)
        else:  # 气层砂岩
            rt_base[i] = 150 + np.random.normal(0, 30)
    
    # 构造完整的测井数据
    test_data = pd.DataFrame({
        'MD': test_depth,
        'GR': gr_base,
        'SP': -50 + 30 * np.sin(test_depth * 0.1) + np.random.normal(0, 3, n_test),
        'CAL': 8 + 0.3 * np.sin(test_depth * 0.05) + np.random.normal(0, 0.1, n_test),
        'LLD': rt_base,
        'LLS': rt_base * 0.85 + np.random.normal(0, 2, n_test),
        'MSFL': rt_base * 0.6 + np.random.normal(0, 1, n_test),
        'RHOB': den_base,
        'NPHI': nphi_base,
        'DT': dt_base,
        'PE': pe_base,
        'Sw': np.where(rt_base > 50, 0.3 + np.random.normal(0, 0.05), 
                      0.85 + np.random.normal(0, 0.05)),
        'LITHOLOGY': lithology_list,
        'FACIES': facies_list,
        'INTERPRETATION': interp_list,
        'VALID_CURVES_COUNT': 5,
        'VQuartz': vqtz,
        'VClay': vclay,
        'VCalcite': vcal,
        'VDolomite': vdol,
        'VAnhydrite': vanh,
        'PHI': phi,
    })
    
    # 在顶部0-5米段设置无效曲线（测试跳过逻辑）
    test_data.loc[test_data['MD'] < 1005, 'VALID_CURVES_COUNT'] = 0
    
    # 在底部最后3米设置无效曲线
    test_data.loc[test_data['MD'] > 1197, 'VALID_CURVES_COUNT'] = 0
    
    # 创建气测数据
    gas_depth = np.arange(1000, 1200, 0.1)
    gas_data = pd.DataFrame({
        'MD': gas_depth,
        'GAS': np.random.uniform(100, 50000, len(gas_depth)),
        'C1': np.random.uniform(50, 30000, len(gas_depth)),
        'C2': np.random.uniform(10, 5000, len(gas_depth)),
        'C3': np.random.uniform(5, 2000, len(gas_depth)),
        'IC4': np.random.uniform(1, 500, len(gas_depth)),
        'NC4': np.random.uniform(1, 500, len(gas_depth)),
        'IC5': np.random.uniform(0.5, 100, len(gas_depth)),
        'NC5': np.random.uniform(0.5, 100, len(gas_depth)),
        'CO2': np.random.uniform(0.1, 50, len(gas_depth))
    })
    
    test_results = {
        'well_name': 'TestWell_Header',
        'output_dir': 'output'
    }
    
    print("正在生成测试综合测井图（无气测数据）...")
    result = visualize_composite_log(test_data, test_results)
    if result:
        print(f"测试图已生成: {result}")
    
    print("\n正在生成测试综合测井图（含气测数据）...")
    result2 = visualize_composite_log(test_data, test_results, gas_data=gas_data)
    if result2:
        print(f"气测测试图已生成: {result2}")
    else:
        print("生成失败")


# ============================================================================
# 流体交会图扩展（由 visualization_fluid 模块提供，可选依赖）
#   patch_depth_unit('ft')            —— 深度道适配英尺井
#   visualize_fluid_crossplots(...)   —— 油绿/气红/水蓝 交会图，按层号标注
# ============================================================================
try:
    from visualization_fluid import (patch_depth_unit, visualize_fluid_crossplots,
                                     setup_chinese_font, classify_fluid,
                                     FLUID_LABEL_CN, FLUID_COLOR)
    HAS_FLUID_VIZ = True
except ImportError as _e:
    HAS_FLUID_VIZ = False
    _FLUID_VIZ_IMPORT_ERR = _e


def visualize_fluid(data, results, output_dir=None, gas_data=None,
                    depth_unit='auto', min_thickness=3.0):
    """log_visualizer 的流体交会图入口。

    visualization_fluid 模块不可用时返回 None 并记录警告，
    不影响综合测井图的正常绘制。
    """
    if not HAS_FLUID_VIZ:
        logger.warning('流体交会图不可用（visualization_fluid 未安装）: %s',
                       getattr(_FLUID_VIZ_IMPORT_ERR, '__str__', lambda: '?')())
        return None
    setup_chinese_font()
    if depth_unit and str(depth_unit).lower() in ('m', 'ft'):
        patch_depth_unit(str(depth_unit).lower())
    out = output_dir or results.get('output_dir', 'output')
    return visualize_fluid_crossplots(
        data, results, output_dir=out, depth_unit=depth_unit or 'ft',
        gas_data=gas_data, min_thickness=min_thickness)

