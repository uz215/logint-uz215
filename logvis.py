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
import json
import logging
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from pathlib import Path
import datetime
import shutil
import tempfile

# 【2026-10-20 RASHIDPUR_13】解除 Pillow 防炸图像素上限（默认 1.79 亿）。
# 本模块只打开**本地自生成**的 PNG（深井 quick look 长图可超 4 亿像素，
# 如 RP-13 井深 4425m 正图 465,847,200 像素），不存在不可信来源；
# 超限时 DecompressionBombError 会使 LEGEND 拼接/整图拼接/PDF 生成
# 全部失败，兜底只剩一张正图 PNG（无 PDF 交付）。
try:
    from PIL import Image as _PIL_guard
    _PIL_guard.MAX_IMAGE_PIXELS = None
except Exception:
    pass

# =============================================================================
# 【2026-10-10 quick look】出图格式注册表
# logvis 保留 4 种出图格式，供 logInt 数据选择界面选定：
#   composite  - 综合图（标准 Composite Log Plot）
#   crossplot  - 交汇图（岩性/流体/储层交会图, visualize_fluid）
#   quicklook  - 快速解释图（Quick Look, 参照 BET-1 masterlog 版式）
#   config     - 格式文件（甲方 quicklook_config.json 定义的格式）
# 未选择时按 quicklook 默认格式与默认图标出图。
# =============================================================================
PLOT_FORMATS = {
    'composite': '综合图（Composite Log）',
    'crossplot': '交汇图（Crossplot）',
    'quicklook': '快速解释图（Quick Look，默认格式+默认图标）',
    'config': '格式文件（Config File，甲方格式）',
}

# ============================================================================
# 图版模板加载器（2026-10-10 图版化）
#   templates/qlpt.json —— 快速解释图版（承接原 quicklook_config.json）
#   templates/cmpt.json —— 综合图图版
#   templates/cppt.json —— 交汇图图版
# 作图时直接调用图版：load_plot_template('qlpt'/'cmpt'/'cppt')。
# 图版中未配置的键，代码使用内置默认值（向后兼容）；
# 用户只需改 templates/<key>.json 即可调整版式，无需改代码。
# ============================================================================
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
_TEMPLATE_CACHE = {}          # key -> {'mtime': float, 'tpl': dict|None}
_TEMPLATE_CACHE_MTIME = {}    # key -> 文件修改时间（GUI 常驻时改 json 可自动重载）


def load_plot_template(key, use_cache=True):
    """加载 templates/<key>.json 图版定义。

    key: 'qlpt'（快速解释图）/ 'cmpt'（综合图）/ 'cppt'（交汇图）。
    文件不存在或 JSON 解析失败时返回 None（代码用内置默认值）。
    GUI 常驻进程内：每次调用先比对文件 mtime，图版文件改动后自动重载。
    """
    if use_cache:
        try:
            p = os.path.join(TEMPLATES_DIR, f'{key}.json')
            _mtime = os.path.getmtime(p) if os.path.exists(p) else -1
            if key in _TEMPLATE_CACHE and _TEMPLATE_CACHE_MTIME.get(key) == _mtime:
                return _TEMPLATE_CACHE[key]
        except Exception:
            pass
    tpl = None
    try:
        p = os.path.join(TEMPLATES_DIR, f'{key}.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                tpl = json.load(f)
    except Exception as _e:
        logger.warning('加载图版 %s 失败: %s', key, _e)
        tpl = None
    if use_cache:
        try:
            _TEMPLATE_CACHE_MTIME[key] = os.path.getmtime(
                os.path.join(TEMPLATES_DIR, f'{key}.json')) if os.path.exists(
                os.path.join(TEMPLATES_DIR, f'{key}.json')) else -1
        except Exception:
            _TEMPLATE_CACHE_MTIME[key] = -1
        _TEMPLATE_CACHE[key] = tpl
    return tpl


# 深度刻度配置（模板 depth_scale 覆盖；None 时用代码内置 米制100/10、英制100/20）
_TPL_DEPTH_SCALE = None
# 比例尺配置（模板 figure.curve_scale / curve_scale_den 覆盖；None 时用内置默认）
_TPL_CURVE_SCALE = None
# <井名>info.json 展平缓存（visualize_composite_log 入口刷新）。
# 【2026-10-14 用户定案】深度比例尺进 json：深度单位英尺=1:240、公制=1:200，
# json 非空值优先于图版（curve_scale_ft / curve_scale_m，人工修改后出图直接调用）
_WELLINFO_FLAT = {}


def _tpl_curve_scale_den(du):
    """比例尺分母取值链：
    <井名>info.json 深度比例尺（curve_scale_ft/curve_scale_m）>
    图版 figure.curve_scale / curve_scale_den >
    内置默认（用户2026-10-14定案：英制 240 → 1:240，公制 200 → 1:200）。"""
    # 1) 井信息 json 优先（人工可修改）
    _jv = str(_WELLINFO_FLAT.get('curve_scale_ft' if du == 'ft' else 'curve_scale_m') or '').strip()
    if _jv:
        try:
            return int(_jv.split(':')[1]) if ':' in _jv else int(float(_jv))
        except Exception:
            pass
    # 2) 图版
    _cfg = _TPL_CURVE_SCALE or {}
    if isinstance(_cfg, dict):
        _den = _cfg.get(du)
        if isinstance(_den, (int, float)):
            return int(_den)
        if isinstance(_den, str) and ':' in _den:
            try:
                return int(_den.split(':')[1])
            except Exception:
                pass
    # 3) 内置默认
    return 240 if du == 'ft' else 200


def _tpl_depth_steps(du):
    """深度刻度步长（用户2026-10-15定案：曲线区横线三档——
    公制 100/10/1（每1m一条浅色细线）、英制 100/10/2（每2ft一条浅色
    细线，"英制的深度改为100/10/2"）；每10一条深色线、每100一条加粗线；
    公制每10m标注一个深度、英制每20ft标注一个深度）。
    返回 (coarse, mid, fine, label)；图版 depth_scale 的 major/minor
    仍可覆盖前两档。"""
    coarse, mid = 100, 10
    if isinstance(_TPL_DEPTH_SCALE, dict):
        _mj = (_TPL_DEPTH_SCALE.get('major_step') or {}).get(du)
        _mn = (_TPL_DEPTH_SCALE.get('minor_step') or {}).get(du)
        if _mj:
            coarse = int(_mj)
        if _mn:
            mid = int(_mn)
    # 细线档：英制每2ft一条（100/10/2），公制每1m一条（100/10/1）
    return coarse, mid, (2 if du == 'ft' else 1), (20 if du == 'ft' else 10)


def _draw_depth_gridlines(ax, depth_min, depth_max, header_bottom_y):
    """曲线区深度横线三档（用户2026-10-15定案：公制100/10/1、英制100/10/2，
    综合图/快速解释图共用）：英制每2ft/公制每1m一条浅色细线
    （gray 0.78 / lw0.35）、每10一条深色线（黑 / lw0.8）、每100一条
    加粗线（黑 / lw1.3）。只画曲线区。"""
    fig = ax.figure
    pos = ax.get_position()
    ax_left, ax_right = pos.x0, pos.x1
    _du = DEPTH_UNIT
    if _du == 'auto':
        _du = _detect_depth_unit(depth_min, depth_max)
    coarse_step, mid_step, fine_step, _label_step = _tpl_depth_steps(_du)

    def _ticks(step):
        base = (int(depth_min) // step) * step
        t = np.arange(base, depth_max + step, step)
        return t[(t >= depth_min) & (t <= depth_max)]

    def _fy(v):
        return (depth_max - v) / (depth_max - depth_min) * header_bottom_y

    for depth_val in _ticks(fine_step):
        fig_y = _fy(depth_val)
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure,
                    color='0.78', linewidth=0.35, zorder=499)
    for depth_val in _ticks(mid_step):
        fig_y = _fy(depth_val)
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure,
                    color='black', linewidth=0.8, zorder=500)
    for depth_val in _ticks(coarse_step):
        fig_y = _fy(depth_val)
        if 0 <= fig_y <= header_bottom_y:
            ax.plot([ax_left, ax_right], [fig_y, fig_y], transform=fig.transFigure,
                    color='black', linewidth=1.3, zorder=501)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logvis.log'),
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

# 【2026-10-21 R18 用户定案：统一的井径绘制规则】CAL 与 BS(BIT) 之间双向充填色
CAL_OVERFILL_COLOR = '#F4A6A6'    # 超径 CAL > BS（扩径/井壁坍塌/溶蚀）淡红
CAL_UNDERFILL_COLOR = '#9CC3E5'   # 缩径 CAL < BS（泥饼厚/侵入）淡蓝

# 岩性值 → 符号图片文件名 映射
LITHOLOGY_TO_SYMBOL = {
    'sandstone': 'Sandstone.png',
    'shale': 'Shale.png',
    'limestone': 'Limestone.png',
    'dolomite': 'Dolomite.png',
    'anhydrite': 'Anhydrite.png',
    'gypsum': 'Gypsum.png',
    'halite': 'Halite.png',
    'salt': 'Salt.png',
    'volcanic': 'DBOS_Volcanic.png',
    'basalt': 'volcanic.png',
    'carbonate': 'Limestone.png',
    'mixed': 'Sandstone.png',
    'coal': 'Coal.png',
    'carbonaceous_shale': 'Carbonaceous shale.png',
    'carbonaceous shale': 'Carbonaceous shale.png',
    'pyrite': 'Pyrite.png',
    'conglomerate': 'Conglomerate.png',
    'mudstone': 'Shale.png',
    # 中文名称
    '砂岩': 'Sandstone.png',
    '泥岩': 'Shale.png',
    '灰岩': 'Limestone.png',
    '白云岩': 'Dolomite.png',
    '硬石膏': 'Anhydrite.png',
    '石膏': 'Gypsum.png',
    '盐岩': 'Halite.png',
    '盐': 'Salt.png',
    '火山岩': 'DBOS_Volcanic.png',
    '玄武岩': 'volcanic.png',
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
    # 【2026-10-23 R21】碳酸盐岩底色改为**参考图自身底色**（symbol/ 实测
    # 众数）：Limestone.png=#97CFF4、Dolomite.png=#00BFCF。原值 #87CEEB /
    # #B0E0E6 与参考图底色色距分别 26 / 232 ⇒ profile 道"只画底色不画符号"
    # 的窄带与"整段取最窄范围"露出的平涂区呈淡色，与符号区不一致 → 用户
    # 反馈"灰岩和白云岩都有淡色的不连续色带"。改后露底与符号区同源同色。
    'limestone': '#97CFF4', 'dolomite': '#00BFCF', 'carbonate': '#97CFF4',
    '灰岩': '#97CFF4', '白云岩': '#00BFCF', '碳酸盐岩': '#97CFF4',
    'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
    '硬石膏': '#FFC0CB', '石膏': '#FFC0CB',
    'halite': '#FF69B4', 'salt': '#FF69B4', '盐岩': '#FF69B4', '盐': '#FF69B4',
    'volcanic': '#FF0000', '火山岩': '#FF0000',
    # 【2026-10-16 用户要求】玄武岩（火山岩类）= volcanic.png 十字符号 +
    # 红色底色（原 Basalt.bmp 灰底废弃）
    'basalt': '#FF0000', '玄武岩': '#FF0000',
    # 【2026-10-20 用户定案】煤=纯黑填充、无横线（Coal.png 纯黑零墨迹→只画底色）
    'coal': '#000000', '煤': '#000000', '煤层': '#000000',
    'carbonaceous_shale': '#6B6B6B', 'carbonaceous shale': '#6B6B6B', '碳质泥岩': '#6B6B6B',
    'pyrite': '#FFD700', '黄铁矿': '#FFD700',
    'conglomerate': '#D2B48C', '砾岩': '#D2B48C',
    'mixed': '#D3D3D3', 'unknown': '#D3D3D3',
}

_SAND_NAMES = ('sandstone', '砂岩')
_SHALE_NAMES = ('shale', 'mudstone', '泥岩', '页岩', '泥页岩')
_LIME_NAMES = ('limestone', 'carbonate', '灰岩', '碳酸盐岩')
_DOLO_NAMES = ('dolomite', '白云岩')
_ANHY_NAMES = ('anhydrite', 'gypsum', '硬石膏', '石膏')
_SALT_NAMES = ('halite', 'salt', '盐岩', '盐')
_COAL_NAMES = ('coal', '煤', '煤层')
# 【2026-10-19 用户要求】火成岩/玄武岩名称集合——错开十字符号（红底）
_BASALT_NAMES = ('basalt', 'volcanic', '玄武岩', '火山岩', '火成岩')

# ---------------------------------------------------------------------------
# 【2026-10-19 机制化·单一几何定义源】SYMBOL_SPECS 注册表
# 用户定案："绘制其实是图例的重复……需要建立一套保证整体一致的机制，不能
# 每个图例都来修改。" 本机制三层，任何修改只允许发生在定义层：
#   ① 定义层（本表 + _lith_pattern_core）：8 类符号的几何比例/样式/间距
#      只在此处定义一次，_lith_pattern_core 只从本表读数、不硬编码；
#   ② 共享层（_lith_pitch_px / _lith_style）：实体道、profile道、各类图例
#      （道头 swatch / LAS 信息区微图例 / masterlog）全部调用同一组取值
#      函数——禁止任何绘制路径自行计算 pitch 或样式；
#   ③ 门禁层（_test_symbol_consistency.py）：回归测试自动验证"任意路径
#      渲染 == 图例渲染"（几何/样式/像素结构逐一相等）+ 静态检查禁止新增
#      绕过本机制的绘制代码。新增/修改符号只改本表，跑门禁确认全程序一致。
# 历史教训：2026-10-19 之前 pitch/样式在实体与图例各写一份，图例漏 mew=0
# 致砂岩点粘连、blank 落默认分支画灰线、_sym_* 死代码另有一套几何——
# 逐项"打补丁"式修复反复翻车，故收敛为本机制。
# ---------------------------------------------------------------------------
_SYMBOL_GEOM = {          # 几何比例（单位=格；屏幕等比类按 cw_px/ch_px 修正）
    'dots':        dict(stagger=0.5),                    # 奇行错半格（蜂窝交错）
    'dash':        dict(half_w=0.32),                    # 行中横线半宽
    'brick':       dict(brick_w=2.0),                    # 砖宽（格）
    'slant_brick': dict(hz=0.28, brick_w=2.0),           # 斜线半高/砖宽
    'tri':         dict(angle_k=0.577, leg_frac=0.5),    # 顶角60°/腿高=半行距
    'invL':        dict(gw=0.5, gh=0.65, top_pad=0.05),  # 短横在上/长竖在左
    'ell':         dict(vh=0.85, hw=0.6),                # 盐岩L形
    'coal':        dict(x0_frac=0.15, x1_frac=0.85),     # 行中横线（灰色）
}
_SYMBOL_STYLE = {         # 样式（磅/颜色）；dots 用 dot_ms/dot_mew，其余用 lw/color
    'dots':        dict(dot_ms=LITH_DOT_MS, dot_mew=0.0, color='black'),
    'dash':        dict(lw=LITH_LINE_LW, color='black'),
    'brick':       dict(lw=LITH_BRICK_LW, color='black'),
    'slant_brick': dict(lw=LITH_BRICK_LW, color='black'),
    'tri':         dict(lw=LITH_LINE_LW, color='black'),
    'invL':        dict(lw=LITH_LINE_LW, color='black'),
    'ell':         dict(lw=LITH_LINE_LW, color='black'),
    'coal':        dict(lw=LITH_LINE_LW, color='#5A5A5A'),
}
_SYMBOL_PITCH = {         # 像素间距（dots 密、其余疏）——全程序唯一来源
    'dots':        LITH_PATTERN_PITCH_PX,
    'dash':        LITH_PATTERN_PITCH_PX_DASH,
    'brick':       LITH_PATTERN_PITCH_PX_DASH,
    'slant_brick': LITH_PATTERN_PITCH_PX_DASH,
    'tri':         LITH_PATTERN_PITCH_PX_DASH,
    'invL':        LITH_PATTERN_PITCH_PX_DASH,
    'ell':         LITH_PATTERN_PITCH_PX_DASH,
    'coal':        LITH_PATTERN_PITCH_PX_DASH,
    # 【2026-10-20】参考图墨迹瓦片：1 参考图单元≈28px 屏幕（1:200·150dpi
    # ≈1 米/单元，与 TILE_DEPTH_M 语义同源），实体/图例共用
    'ref':         28.0,
}


def _lith_pitch_px(kind):
    """岩性符号像素间距——实体道/profile道/图例共用（禁止各处自行计算）。"""
    return _SYMBOL_PITCH.get(kind, LITH_PATTERN_PITCH_PX_DASH)


def _lith_style(kind):
    """岩性符号样式——实体道/profile道/图例共用（禁止各处自行硬编码）。"""
    return _SYMBOL_STYLE.get(kind, dict(lw=LITH_LINE_LW, color='black'))


def _lith_bg_color(lith_name):
    """按岩性取背景色，未知岩性用浅灰"""
    return LITH_BG_COLORS.get(str(lith_name).lower(), '#D3D3D3')


# ---------------------------------------------------------------------------
# 【2026-10-20 用户定案】岩性符号"一切以 symbol/ 参考图为准"：全部有可用
# 参考图的岩性统一走参考图墨迹瓦片（kind 'ref'）——符号几何直接取参考图
# 墨迹（_lith_ink_tile），按 _SYMBOL_REF_PITCH[文件] 正方格铺排，实体道/
# 剖面道/所有图例共用同一瓦片，机制保证"效果=岩性图例图片"。
# 参考图选用（已逐张核查）：
#   砂岩=Sandstone.png（黄底黑方点错排，与蜂窝口径一致）；泥岩=Shale.png
#   （绿底黑横线）；灰岩/碳酸盐岩=Limestone.png（蓝底砖砌）；煤=Coal_std.png
#   （深灰底灰横线——Coal.png 全黑废图禁用）；白云岩=Dolomite.png；
#   硬石膏/石膏=Anhydrite.png（Gypsum.png 全黑废图禁用）；盐岩=Halite.png
#   （Salt.png 全黑废图禁用）；玄武岩=basalt.png（2026-10-20 用户更新）；
#   火山岩=DBOS_Volcanic.png（红底黑V）；砾岩=Conglomerate.png；
#   未知=Unknown.png（灰底X）。
#   黄铁矿（Pyrite.png/Pyrite.1.png 均棋盘格废图）、碳质泥岩（亮墨青线待
#   用户确认）暂无可用参考图 → 维持旧 image 整图瓦片路径。
#   煤参考图（Coal*.png）均为纯黑无墨迹 → 按参考图渲染为纯黑填充
#   （2026-10-20 用户定案"煤就是黑色没有煤横线"）。
# 【2026-10-20 二次定案】瓦片=参考图整图（底色+纹理都以参考图为主，
# 不再统一底色）：_lith_ink_tile 保留参考图自身底色不透明上墙，
# LITH_BG_COLORS 仅作瓦片加载失败时的兜底。
# 格距规则见 _SYMBOL_REF_PITCH/_lith_ref_pitch 处"岩性绘制规则"注释：
# 行状符号=N行×统一行高9px（白云岩54/灰岩36/泥岩36/盐岩36/硬石膏18，
# 砖块行高一致）；点状（砂岩40）/块状（玄武岩28等）保持已确认格距；
# 瓦片行相位对齐+实体全局锚定 → 同道所有符号行线接续。
# ---------------------------------------------------------------------------
_SYMBOL_REF_IMAGE = {
    'dolomite': 'Dolomite.png',   '白云岩': 'Dolomite.png',
    'anhydrite': 'Anhydrite.png', '硬石膏': 'Anhydrite.png',
    'gypsum': 'Anhydrite.png',    '石膏': 'Anhydrite.png',
    'halite': 'Halite.png',       'salt': 'Halite.png',
    '盐岩': 'Halite.png',         '盐': 'Halite.png',
    'basalt': 'basalt.png',       '玄武岩': 'basalt.png',
    # 【2026-10-20 全量参考图化】
    'sandstone': 'Sandstone.png', '砂岩': 'Sandstone.png',
    'mixed': 'Sandstone.png',     '混合': 'Sandstone.png',
    'shale': 'Shale.png', 'mudstone': 'Shale.png',
    '泥岩': 'Shale.png', '页岩': 'Shale.png', '泥页岩': 'Shale.png',
    'limestone': 'Limestone.png', 'carbonate': 'Limestone.png',
    '灰岩': 'Limestone.png', '碳酸盐岩': 'Limestone.png',
    'coal': 'Coal.png', '煤': 'Coal.png', '煤层': 'Coal.png',
    # 煤参考图（Coal*.png/DBOS_Coal.png）均为纯黑无墨迹——按"以参考图为准"
    # 渲染为纯色填充（瓦片零墨迹→只画底色）；如需横线纹理请提供新参考图。
    'volcanic': 'DBOS_Volcanic.png', '火山岩': 'DBOS_Volcanic.png',
    'conglomerate': 'Conglomerate.png', '砾岩': 'Conglomerate.png',
    'unknown': 'Unknown.png',
}

# ---------------------------------------------------------------------------
# 【2026-10-20 用户定案·岩性绘制规则】"同一张图上，符号单行高度一致、一行
# 符号数协调"——按符号类别统一尺度：
#   ① 行状符号（参考图为 N 行重复离散符号：砖块/横线/L括号）：
#      格距 = N × LITH_REF_ROW_PX（统一行高 9px = LITH_PATTERN_PITCH_PX_DASH，
#      与用户已确认的泥岩/灰岩行距一致）。行数由参考图自动量测
#      （_ref_row_phase：横缝/墨迹行带周期）——白云岩 6 行×9=54 与灰岩
#      4 行×9=36 砖块纵向高度一致（根因：白云岩格距 28px→砖高 4.7px，
#      灰岩 36px→砖高 9px，此前"砖块大小不一"）。
#   ② 点状符号（砂岩点阵）：保持历史确认点距 5px → 格距 40（下表特例）。
#   ③ 块状/带状符号（玄武岩倒L、火山岩V、砾岩、未知）：
#      保持用户确认"大小合适"的格距（下表特例）。硬石膏已移出特例表
#      （二次定案：碳酸盐岩剖面每行纹理高度统一 → 2行×9=18）。
#   ④ 行相位：瓦片纵向循环移位把首行 motif 顶到瓦片顶（_lith_ink_tile），
#      实体格网全局锚定绝对深度 0 → 同道相邻段/相邻岩性行线接续对齐。
#   ⑤ 底色以图为准（2026-10-20 二次定案）：瓦片=参考图整图不透明上墙
#      （底色+纹理都来自参考图），不再统一底色；LITH_BG_COLORS 仅兜底。
# ---------------------------------------------------------------------------
LITH_REF_ROW_PX = 9.0    # 行状符号统一行高（像素，=泥岩/灰岩已确认行距）

# 点状/块状符号特例格距（屏幕像素）——均为用户已确认口径，不随行高规则变
# 【2026-10-20 二次定案】硬石膏移出特例表纳入行高统一（2行×9px=18）：
# 用户要求灰岩/白云岩/硬石膏等碳酸盐岩剖面"每行纹理高度统一"
_SYMBOL_REF_PITCH = {
    'Sandstone.png': 40.0,     # 点阵：8行点×5px 点距（历史确认密度）
    'basalt.png': 28.0,        # 块状倒L：2026-10-20 用户确认大小合适
    'DBOS_Volcanic.png': 42.0,
    'Conglomerate.png': 32.0,
    'Unknown.png': 28.0,
}

_REF_ROW_PHASE_CACHE = {}

# ---------------------------------------------------------------------------
# 【2026-10-23 用户反馈修复·R21】参考图**降采样核**注册表（机制化，禁止
# 散落硬编码）：整图缩到瓦片尺寸时用哪种重采样核。
# 根因（实测）：LANCZOS 核有负瓣振铃，参考图缩到 1/3 量级时
#   ① 细墨迹（砖缝竖线/45°斜线）被振铃打断成"点"——用户反馈"碳酸盐岩竖线
#      和白云岩斜线变成点了"；
#   ② 振铃把底色污染：Dolomite.png 128→54 后众数底色由 (0,191,207) 变成
#      (0,0,0)，81% 像素被误判为墨迹（实测），斜线呈断续阶梯。
# BOX（面积平均）无过冲：同图 128→54 后底色保持 (0,191,207)、墨迹连通域
# 完整（缝列纵向连续率 0.178→1.000），斜线恢复为连续斜杠。
# 仅对"细线型"碳酸盐岩启用 BOX；点块型（Unknown 的 X / 玄武岩倒L / 火山岩 V
# / 砾岩）实测 BOX 会把 1px 斜线稀释成断续细线，维持 LANCZOS 不变。
# 泥岩/砂岩走原生 motif 单元模式（本表不适用），其降采样行为 R19 已验证。
# ---------------------------------------------------------------------------
_SYMBOL_REF_RESAMPLE = {
    'Limestone.png': 'BOX',     # 砖砌：错缝竖线最细，振铃即断
    'Dolomite.png': 'BOX',      # 斜砌：45°斜线 + 振铃底色污染
}

# ---------------------------------------------------------------------------
# 【2026-10-23 R21】参考图瓦片**栅格超采样倍数**（屏幕像素 × SS）：
#   参考图 128px 整图缩到"格距像素"（灰岩 36px / 白云岩 54px）= 3.56×/2.37×
#   非整数降采样，8px 宽的砖缝竖线被稀释成 2.25px 灰线、45° 阶梯斜线断裂
#   成"点"（用户反馈"碳酸盐岩竖线和白云岩的斜线变成点了"）；PDF 后端又把
#   栅格原样内嵌（/Interpolate 0 次）⇒ 放大即糊成块状。
#   SS=2 ⇒ 灰岩 72px / 白云岩 108px 栅格，铺排时由 matplotlib 面积缩小，
#   PDF 内嵌 2px/pt ⇒ 放大仍连续。栅格边长不超过参考图原生边长（不插值放大）。
#   注意：dx/dy 仍按"格距像素"算 ⇒ 符号在屏幕上的**物理尺寸不变**，
#         只把栅格变细，不改变用户已确认的间距/大小。
# ---------------------------------------------------------------------------
# 【2026-10-26 R24】参考图栅格边长覆盖表：白云岩 trim+方化后原生 122x122。
# R22 把裁边后的 122x126 BOX 缩到 108x108（非整数、横纵系数不同），
# 45° 阶梯斜杠被重采样打乱——用户反馈"斜线不直/砖块下部莫名向上的短竖线"
# 即阶梯步距不均产生的竖向粘连。改为保留原生像素（见 _lith_ink_tile
# 方化裁剪），渲染时 imshow 一次性 area-average（122→54 单级），阶梯
# 不再被两级重采样破坏。灰岩 motif 为竖线/横缝，对非整数缩放不敏感，
# 维持原 pitch×SS 规则。
_SYMBOL_REF_RASTER = {
    'Dolomite.png': 122,
}

_SYMBOL_REF_SS = 2.0

# 单次 imshow 的瓦片像素上限（RGBA 字节 ≈ 4×）—— 超限时放大格距而非撑爆内存
_LITH_REF_MAX_PIX = 4_000_000

# ---------------------------------------------------------------------------
# 【2026-10-22 用户反馈修复】砂岩/泥岩符号"黑点大小不一、间距不一；泥岩
# 短横线太密"——根因=**整张参考图等比压进一个 pitch 瓦片**：Shale.png
# 512→36px(14.2×)、Sandstone.png 128→40px(3.2×)，非整数降采样使每个 motif
# 落在不同亚像素相位 ⇒ 每个点/线的实际大小与间距都不同（LANCZOS 振铃加重）。
# 修复＝"参考图原生 motif 单元"采样：裁出参考图中**周期整除、边距对称**的
# 干净单元（泥岩=1 行×1 列；砂岩=6 行×3 列），整幅降采样后按单元平铺 →
#   ① 每个 motif 逐像素同源 ⇒ 大小一致、间距一致；
#   ② 形状/底色仍直接取自参考图本身（不重绘、不改形、不动其他岩性）。
# 裁剪区按 motif 网格对齐且整除周期 ⇒ 降采样后所有 motif 同相位 ⇒ 无差异。
# 值 = (crop_x0, crop_y0, crop_w, crop_h, tile_w_px, tile_h_px)
#   Shale.png      原生行周期 128px、列距≈73px（首列 x=13）→ 裁 1 行 × 1 列
#   Sandstone.png  原生行周期 16px、列距 32px（奇偶行错半格）→ 裁 6 行 × 3 列
# 单位：原生像素 / 屏幕像素。
# ---------------------------------------------------------------------------
_SYMBOL_REF_UNIT = {
    'Shale.png': (13, 53, 73, 128, 10, 18),
    'Sandstone.png': (10, 15, 96, 96, 36, 36),
}


def _ref_row_phase(ref_file):
    """量测参考图 motif 行周期 P 与首行相位 O（原生像素）及图高 h。

    优先横向贯穿缝（砖块类：行墨迹率>0.55 的缝带中心差中位数）；无贯穿缝
    则用墨迹行带起点差中位数（横线/L括号/点阵/人字类）。返回 (P, O, h)，
    无法量测返回 (None, None, None)。结果按文件缓存。
    """
    key = str(ref_file)
    if key in _REF_ROW_PHASE_CACHE:
        return _REF_ROW_PHASE_CACHE[key]
    out = (None, None, None)
    try:
        from PIL import Image
        im = Image.open(os.path.join(SYMBOL_DIR, ref_file)).convert('RGB')
        a = np.asarray(im).astype(np.int16)
        h = int(a.shape[0])
        cols, counts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
        bg = cols[int(counts.argmax())]
        ink = (np.abs(a - bg).sum(axis=2) > 60)

        def _centers(idx):
            cs = []
            if not len(idx):
                return cs
            s = p = int(idx[0])
            for i in idx[1:]:
                if i - p <= 2:
                    p = i
                else:
                    cs.append((s + p) / 2.0)
                    s = p = int(i)
            cs.append((s + p) / 2.0)
            return cs

        # ① 横向贯穿缝（砖块类）
        seams = [i for i, v in enumerate(ink.mean(axis=1)) if v > 0.55]
        cents = _centers(seams) if len(seams) >= 3 else []
        # ② 墨迹行带（其余行状类）
        if len(cents) < 3:
            rows_ink = ink.sum(axis=1) > 2
            starts = []
            s = None
            for i, v in enumerate(rows_ink):
                if v and s is None:
                    s = i
                elif not v and s is not None:
                    if i - s >= 2:
                        starts.append(s)
                    s = None
            if s is not None:
                starts.append(s)
            cents = [float(b) for b in starts] if len(starts) >= 2 else []
        if len(cents) >= 2:
            P = float(np.median(np.diff(cents)))
            if P > 1:
                out = (P, float(cents[0] % P), h)
    except Exception as exc:
        logger.debug('参考图行周期量测失败 %s: %s', ref_file, exc)
    _REF_ROW_PHASE_CACHE[key] = out
    return out


def _lith_ref_pitch(ref_file):
    """参考图铺排格距——实体道/剖面道/图例共用（禁止各处自行计算）。

    规则：特例表优先（点状/块状已确认格距）；行状符号 = motif 行数 ×
    LITH_REF_ROW_PX；量测失败回退 _SYMBOL_PITCH['ref']。
    """
    p = _SYMBOL_REF_PITCH.get(str(ref_file))
    if p:
        return float(p)
    P, _O, h = _ref_row_phase(ref_file)
    if P and h and P > 1:
        n_rows = max(1, int(round(h / P)))
        return float(n_rows * LITH_REF_ROW_PX)
    return _SYMBOL_PITCH['ref']


def _lith_ref_tile_size(ref_file):
    """参考图瓦片屏幕像素尺寸 (tw, th)——实体道/剖面道/图例共用。

    【2026-10-22】原生 motif 单元模式：tw/th = 单元降采样后的像素尺寸
    （横纵可不同 ⇒ 泥岩横线与砂岩点阵各自保持参考图比例）；
    其余参考图沿用"整图正方瓦片"（tw=th=格距）。
    """
    u = _SYMBOL_REF_UNIT.get(str(ref_file))
    if u:
        return float(u[4]), float(u[5])
    t = max(8, int(round(_lith_ref_pitch(str(ref_file)))))
    return float(t), float(t)


def _ring_ink(ink_mask, n):
    """取墨迹掩膜最外 n 圈像素（上下左右四条边，原始顺序不去重）。"""
    h, w = ink_mask.shape[:2]
    parts = [ink_mask[:n, :].ravel(), ink_mask[h - n:, :].ravel(),
             ink_mask[:, :n].ravel(), ink_mask[:, w - n:].ravel()]
    return np.concatenate(parts) if parts else np.zeros(0, bool)


def _trim_ref_frame(a, bg):
    """【2026-10-26 R22】裁掉参考图四边的**装饰框线**（如白云岩灰+黑双边框）。

    判据（逐边、最多 4px）：
    - 左/右（几何判据）：近实线列——列内像素与该列自身中位色一致比例>0.92、
      墨迹率>0.9 且 > 3x 内部列墨迹率中位。灰岩边缘真实竖缝（墨迹率~0.6）、
      煤（全黑，内部同为 1.0）均不触发。
    - 上/下（颜色判据）：近实线行且该行中位色与**主墨色**（全部墨迹像素的
      中位色）色距>60。白云岩顶部灰带触发；灰岩/泥岩底部真实黑缝带
      （=主墨色）不触发。
    返回 (裁剪后数组, 顶部裁剪行数, 左侧裁剪列数)。行相位 roll 前调用，
    _sh 按顶部裁剪量修正。
    """
    h, w = a.shape[:2]
    ink = (np.abs(a - bg).sum(axis=2) > 60)
    if float(ink.mean()) < 0.02 or int(ink.sum()) < 50:
        return a, 0, 0
    dom = np.median(a[ink], axis=0)

    def _solid(colors):
        med = np.median(colors, axis=0)
        return float((np.abs(colors - med).sum(axis=1) < 60).mean()) > 0.92

    def _vert_frame(ci):
        # 几何判据：近实线列 + 墨迹率远超内部列中位（白云岩框线 1.0 vs
        # 内部 0.34；灰岩真实竖缝 0.61、煤内部=框线=1.0 均不触发）
        col = a[:, ci]
        if float(ink[:, ci].mean()) < 0.9:
            return False
        if float(ink[:, ci].mean()) < 2.5 * _inner_col_ink:
            return False
        med = np.median(col, axis=0)
        if np.abs(med - bg).sum() < 60:
            return False
        return _solid(col)

    def _horz_color(ri):
        # 颜色判据：**中灰消色差**实线行（装饰灰框；灰岩/泥岩底部真实黑缝带
        # 亮度~0 不触发，白云岩底部青色半缝为彩色不触发，Unknown 灰底
        # 与 bg 同色不触发）
        row = a[ri, :]
        med = np.median(row, axis=0)
        if np.abs(med - bg).sum() < 60:
            return False
        if (med.max() - med.min()) > 40:
            return False
        if not (77.0 < float(med.mean()) < 235.0):
            return False
        return _solid(row)

    _inner_col_ink = (float(np.median(ink[:, 8:max(9, w - 8)].mean(axis=0)))
                      if w > 16 else 0.0)
    top = bottom = left = right = 0
    while top < 4 and _horz_color(top):
        top += 1
    while bottom < 4 and _horz_color(h - 1 - bottom):
        bottom += 1
    while left < 4 and _vert_frame(left):
        left += 1
    while right < 4 and _vert_frame(w - 1 - right):
        right += 1
    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return a, 0, 0
    logger.info('参考图装饰框线裁剪: top=%d bottom=%d left=%d right=%d',
                top, bottom, left, right)
    sub = a[top:h - bottom if bottom else h,
            left:w - right if right else w]
    return np.ascontiguousarray(sub), top, left


_LITH_REF_RASTER_CACHE = {}


def _lith_ref_raster(ref_file, ss=None):
    """参考图瓦片**栅格边长**（像素）——实体道/profile 道/图例共用。

    【2026-10-23 R21】= min(参考图原生边长, 格距像素 × SS)。见
    _SYMBOL_REF_SS 处说明：提高栅格分辨率解决"非整数降采样把 8px 竖缝/45°
    斜线稀释成灰点"，且不超过原生边长（绝不插值放大）。
    """
    key = (str(ref_file), ss)
    if key in _LITH_REF_RASTER_CACHE:
        return _LITH_REF_RASTER_CACHE[key]
    out = 0
    try:
        from PIL import Image
        with Image.open(os.path.join(SYMBOL_DIR, str(ref_file))) as im:
            native = int(min(im.size))
        _ss = float(_SYMBOL_REF_SS if ss is None else ss)
        pitch = _lith_ref_pitch(str(ref_file))
        # 【2026-10-26 R24】覆盖表优先：白云岩用方化后原生 122，
        # 避免 122x126→108x108 非整数缩放破坏 45° 阶梯斜杠
        _ov = _SYMBOL_REF_RASTER.get(str(ref_file))
        if _ov:
            out = int(max(8, int(_ov)))
        else:
            out = int(max(8, min(native, round(pitch * _ss))))
    except Exception as exc:
        logger.warning('参考图栅格尺寸计算失败 %s: %s', ref_file, exc)
        out = int(max(8, round(_lith_ref_pitch(str(ref_file)))))
    _LITH_REF_RASTER_CACHE[key] = out
    return out


_lith_ink_tile_cache = {}


def _lith_ink_tile(ref_file, tpx=None):
    """symbol/ 参考图 → RGBA 整图瓦片（**底色+纹理均以参考图为准**，不透明）。

    【2026-10-20 用户定案】不用统一底色：参考图整图作为瓦片直接上墙
    （LITH_BG_COLORS 仅作瓦片加载失败时的兜底），只做三件事：
    ① 外圈贯穿示意框线（墨迹率>50%）用参考图底色覆盖；
    ② 纵向 roll 行相位对齐（首行 motif 顶到瓦片顶，配合格距=N行×9px
       全局锚定绝对深度 0 → 跨段跨岩性行线接续）；
    ③ LANCZOS 缩放到 tpx×tpx——实体与图例必须传同一 tpx（=格子屏幕像素），
       保证两端逐像素同源。
    """
    # 【2026-10-22】原生 motif 单元模式：砂/泥符号按"参考图干净单元"降采样
    # 后平铺（每个 motif 逐像素同源 ⇒ 大小/间距一致），tpx 参数不适用。
    _unit = _SYMBOL_REF_UNIT.get(str(ref_file))
    if _unit:
        key = ('unit', str(ref_file))
        if key in _lith_ink_tile_cache:
            return _lith_ink_tile_cache[key]
        tile = None
        try:
            from PIL import Image
            im = Image.open(os.path.join(SYMBOL_DIR, ref_file)).convert('RGB')
            _ux, _uy, _uw, _uh = _unit[0], _unit[1], _unit[2], _unit[3]
            _tw, _th = int(_unit[4]), int(_unit[5])
            _cell = im.crop((_ux, _uy, _ux + _uw, _uy + _uh)).resize(
                (_tw, _th), Image.LANCZOS)
            a = np.asarray(_cell).astype(np.float64)
            rgba = np.zeros((_th, _tw, 4), dtype=np.float32)
            rgba[..., :3] = a / 255.0
            rgba[..., 3] = 1.0
            tile = rgba
        except Exception as exc:
            logger.warning('参考图 motif 单元瓦片加载失败 %s: %s', ref_file, exc)
        _lith_ink_tile_cache[key] = tile
        return tile
    tpx = int(tpx) if tpx else 0
    key = (str(ref_file), tpx)
    if key in _lith_ink_tile_cache:
        return _lith_ink_tile_cache[key]
    tile = None
    try:
        from PIL import Image
        im = Image.open(os.path.join(SYMBOL_DIR, ref_file)).convert('RGB')
        a = np.asarray(im).astype(np.float64)
        h, w = a.shape[:2]
        cols, counts = np.unique(
            a.reshape(-1, 3).astype(np.int16), axis=0, return_counts=True)
        bg = cols[int(counts.argmax())].astype(np.float64)
        # ⓪【2026-10-26 R22】装饰框线**裁剪**（先于 roll）：白云岩参考图自带
        #   灰+黑双边框（0/127 列灰线、1-2/125-126 列黑线、顶部 0-1 行灰带），
        #   横向平铺后每格边界出现灰白竖条（用户反馈"中间有5道竖的空白"）。
        #   裁剪后重采样回方瓦，图案本体不受影响。
        a, _ct, _cl = _trim_ref_frame(a, bg)
        # ⓪b【2026-10-26 R24】方化裁剪：trim 后若横纵差 ≤8px，把多余行
        #   从底部整条裁掉（前提：底部多余行是贯穿缝带——如白云岩底部
        #   残余缝 4 行，裁掉不伤斜杠；竖向拼接为"砖→缝"自然衔接，
        #   接缝厚度与内部缝一致）。避免非正方瓦片被强行缩放成正方而
        #   破坏 45° 阶梯斜杠（R22 遗留"斜线不直/短竖线"根因）。
        _h0, _w0 = a.shape[:2]
        if _h0 > _w0 and (_h0 - _w0) <= 8:
            _cut = _h0 - _w0
            _tail_ink = float((np.abs(a[-_cut:] - bg).sum(axis=2) > 60).mean())
            if _tail_ink > 0.85:  # 底部多余行确为贯穿缝带才裁
                a = np.ascontiguousarray(a[:-_cut])
        elif _w0 > _h0 and (_w0 - _h0) <= 8:
            # 列多余时从右裁（仅当右侧多余列近乎无墨，防误切真实纹理）
            _cut = _w0 - _h0
            _tail_ink = float((np.abs(a[:, -_cut:] - bg).sum(axis=2) > 60).mean())
            if _tail_ink < 0.02:
                a = np.ascontiguousarray(a[:, :-_cut])
        h, w = a.shape[:2]
        # ①【2026-10-23 R21 顺序修正】行相位 roll **先于** 外圈清理。
        #   原实现"先清框 → 后 roll"：被清成底色的边框行随后被 np.roll 搬进
        #   瓦片**内部** ⇒ 每个格子中间出现一条纯底色横带（用户反馈"灰岩和
        #   白云岩都有淡色不连续色带"）。改为先 roll 后清框，框永远留在外圈。
        _P, _O = _ref_row_phase(ref_file)[:2]
        _sh = (max(0, int(round(_O)) - int(_ct)) % h) if (_P and _O) else 0
        # ② 装饰外框判定（**真框线**判据）：外 2px 环墨迹率高 **且** 框内侧
        #   紧邻一圈几乎无墨迹（框与内容之间留空）。
        #   旧判据只看外 2px 环均值 > 0.5，实测会误判真实纹理：
        #     Limestone.png ring=0.5078 —— 底部 8 行是**真实砖缝带**、
        #                      右侧 2 列是**真实竖缝**；
        #     Dolomite.png  ring=1.0000 —— 顶部/底部是**真实贯穿粗黑带**；
        #   误清 ⇒ 真实纹理被切断 + 留下纯底色白带。
        #   实测 symbol/ 全部 11 张参考图均**不**满足新判据 ⇒ 全部原样保留。
        _ink = (np.abs(a - bg).sum(axis=2) > 60)
        _frame = None
        _r2 = _ring_ink(_ink, 2)
        if _r2.size and float(np.mean(_r2)) > 0.5:
            _r3 = _ring_ink(_ink, 3)
            _inn_n = int(_r3.size) - int(_r2.size)
            _inn_m = ((float(_r3.sum()) - float(_r2.sum())) / _inn_n
                      if _inn_n > 0 else 1.0)
            if _inn_m < 0.15:
                _frame = np.zeros((h, w), dtype=bool)
                _frame[:2] = True
                _frame[-2:] = True
                _frame[:, :2] = True
                _frame[:, -2:] = True
        # ③ 行相位 roll：首行 motif 顶到瓦片顶（不移位则跨岩性行线错半行）
        if _sh:
            a = np.roll(a, -_sh, axis=0)
            if _frame is not None:
                _frame = np.roll(_frame, -_sh, axis=0)
        # ④ 清框（仅真框线才清；mask 随 roll 搬移 ⇒ 框不会被搬进瓦片内部）
        if _frame is not None:
            a[_frame] = bg
        # ⑤ 缩放到 tpx（实体/图例同一 tpx，两端逐像素同源）
        # 【2026-10-23 R21】降采样核按 _SYMBOL_REF_RESAMPLE 注册表取：
        # 碳酸盐岩用 BOX 面积平均（无 LANCZOS 振铃 ⇒ 细线不断、底色不被
        # 污染）；其余维持 LANCZOS（锐利，点块型符号不稀释）。
        _kern = _SYMBOL_REF_RESAMPLE.get(str(ref_file), 'LANCZOS')
        _res = (Image.BOX if _kern == 'BOX' else Image.LANCZOS)
        if tpx and tpx > 0 and tpx != h:
            _tim = Image.fromarray(a.astype(np.uint8), 'RGB').resize(
                (tpx, tpx), _res)
            a = np.asarray(_tim).astype(np.float64)
        rgba = np.zeros((a.shape[0], a.shape[1], 4), dtype=np.float32)
        rgba[..., :3] = a / 255.0
        rgba[..., 3] = 1.0
        tile = rgba
    except Exception as exc:
        logger.warning('参考图整图瓦片加载失败 %s: %s', ref_file, exc)
    _lith_ink_tile_cache[key] = tile
    return tile


# 【2026-10-27 R26】矢量重绘注册岩性：参考图 motif 含细斜线且原生像素
# 宽度不足以承受"整页 150dpi 栅格→54px 设备格"降采样的岩性，直接在
# 最终显示像素矢量重绘（几何参数按参考图实测提取，见 _lith_vector_tile）。
# 仅注册岩性走此链路，其余 10 张参考图维持"原样瓦片"基线不动。
_SYMBOL_VECTOR = {'Dolomite.png'}


def _lith_vector_tile(ref_file, size_px, ss=8):
    """矢量重绘瓦片（仅 _SYMBOL_VECTOR 注册岩性）：按参考图实测几何在
    **最终显示设备像素**尺寸直接绘制（8x 超采样 → BOX 降采样 → nearest
    1:1 贴图）。

    白云岩（Dolomite.png 128px 实测）：
      - 水平缝：缝距 20.3px（取 6 行/瓦）、缝厚 4.5px；
      - 砖宽 58px（取 0.5 瓦宽 = 2 块/瓦），行间错缝半砖；
      - 斜缝：3 段阶梯、跨层高（缝到缝）、左倾总 Δx≈-7px、段宽 4px。
    底色 (0,191,207) / 笔画 (0,0,0) 均取自参考图众数色。
    返回 (h, w, 4) float32 RGBA（归一化 0-1）。
    """
    try:
        if isinstance(size_px, (tuple, list)):
            _w, _h = int(max(6, round(size_px[0]))), int(max(6, round(size_px[1])))
        else:
            _w = _h = int(max(6, round(size_px)))
        key = ('vec', str(ref_file), _w, _h)
        if key in _lith_ink_tile_cache:
            return _lith_ink_tile_cache[key]
        from PIL import Image, ImageDraw
        S = max(_w, _h)
        C = S * ss
        bg = (0, 191, 207)
        fg = (0, 0, 0)
        im = Image.new('RGB', (C, C), bg)
        dr = ImageDraw.Draw(im)
        _rows, _cols = 6, 2
        rowh = C / _rows
        seam = 0.037 * C          # 缝厚 4.5/122
        stroke = 0.040 * C        # 斜缝段宽 4/122（略加粗保证 54px 可辨）
        dx_step = 0.019 * C       # 每阶梯段左移（总 Δx≈7/122）
        # ① 水平缝（行边界居中，r=0/rows 的半缝与邻瓦互补 → 无缝平铺）
        for r in range(_rows + 1):
            y = r * rowh
            dr.rectangle([0, y - seam / 2.0, C, y + seam / 2.0], fill=fg)
        # ② 斜缝阶梯（跨层高，3 段左倾下行）
        for r in range(_rows):
            y0 = r * rowh + seam / 2.0
            y1 = (r + 1) * rowh - seam / 2.0
            sh = (y1 - y0) / 3.0
            phase = (r % 2) * 0.25 * C     # 行间错缝半砖
            k = -1
            while k * 0.5 * C + phase < C * 1.3:
                xj = phase + k * 0.5 * C
                for i in range(3):
                    xc = xj - i * dx_step
                    yc = y0 + i * sh
                    dr.rectangle([xc - stroke / 2.0, yc - sh * 0.08,
                                  xc + stroke / 2.0, yc + sh * 1.08], fill=fg)
                k += 1
        u8 = np.asarray(im.resize((_w, _h), Image.BOX)).astype(np.float32) / 255.0
        rgba = np.zeros((_h, _w, 4), dtype=np.float32)
        rgba[..., :3] = u8
        rgba[..., 3] = 1.0
        _lith_ink_tile_cache[key] = rgba
        return rgba
    except Exception as exc:
        logger.warning('矢量瓦片绘制失败 %s: %s', ref_file, exc)
        return None


def _axes_px_width(ax):
    """返回 axes 宽度（屏幕像素）；布局未完成时返回 None。"""
    try:
        fig = ax.get_figure()
        pos = ax.get_position()
        dpi = float(fig.dpi) or 100.0
        w_px = pos.width * fig.get_figwidth() * dpi
        return w_px if w_px > 1 else None
    except Exception:
        return None


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
    name = str(lith_name).lower().strip()
    # 【2026-10-19 机制化】无符号类：孔隙度/套管/空名/未知名/NaN → 'none'。
    # 任何路径对 'none' 都不画符号（核心返回空、图例只画底色框）——旧版
    # 未知名落 'image'→图片加载失败后：实体路径静默不画、图例路径掉默认
    # 分支画煤灰线，两路径行为不一致（"孔隙度图例有灰线"即此bug）
    if name in ('', 'none', 'blank', 'porosity', 'casing', '套管', 'nan'):
        return 'none'
    # 【2026-10-20 参考图墨迹机制】白云岩/硬石膏/石膏/盐岩/玄武岩 → 'ref'：
    # 符号几何取参考图墨迹瓦片（_SYMBOL_REF_IMAGE + _lith_ink_tile），优先于
    # 矢量覆盖——形状与 symbol/ 参考图逐形一致（用户要求，机制保证）
    if name in _SYMBOL_REF_IMAGE:
        return 'ref'
    # 【2026-10-16 用户要求】综合图岩性符号改矢量绘制，优先级高于图片瓦片：
    # 砂岩/泥岩沿用快速解释图的点/横线画法；灰岩=错缝砖块、白云岩=错缝斜砖块、
    # 硬石膏=错缝倒三角、盐岩=错缝L形；其余岩性（煤/玄武岩等）仍可用图片瓦片
    if name in _DOLO_NAMES:
        return 'slant_brick'
    if name in _ANHY_NAMES:
        return 'tri'
    if name in _SALT_NAMES:
        return 'ell'
    if name in _SAND_NAMES:
        return 'dots'
    if name in _SHALE_NAMES:
        return 'dash'
    if name in _LIME_NAMES:
        return 'brick'
    # 【2026-10-19 用户要求】火成岩/玄武岩 = 倒L形（Γ：顶横杠+左竖杠，
    # Basalt.bmp，红底）——矢量绘制，优先于图片瓦片判定
    if name in _BASALT_NAMES:
        return 'invL'
    if name in _COAL_NAMES:
        return 'coal'
    if name in LITHOLOGY_TO_SYMBOL:
        img, _ = _load_lithology_symbol(name)
        if img is not None:
            return 'image'
    # 【2026-10-19 机制化】未知名岩性不画符号（旧行为：实体不画/图例画灰线）
    return 'none'


# ---------------------------------------------------------------------------
# 【2026-10-19 统一·图例与实体同一核心】岩性符号几何核心
# 用户定案："绘制其实是图例的重复"——提取图例核心几何，道内实体（岩性道/
# profile道）与各类图例（LEGEND表/道头图例）都调用本函数后各自做坐标映射，
# 保证"全井一致、与符号整体一致"；折线互相独立，无跨特征连接/其他效果。
# ---------------------------------------------------------------------------
def _lith_pattern_core(kind, cx, cy, r_base=0, cw_px=None, ch_px=None):
    """岩性符号几何核心——返回格子坐标下的散点与独立折线。

    格子坐标：x∈[0,cx]（列）、y∈[0,cy]（行），y 向下=深度增大（与数据深度
    同向；图例映射时上下翻转）。1 格=1 单元格；cx/cy 可为小数（段区尺寸/
    单元格尺寸），特征自带边界守卫，不会画出格区。

    参数
    ----
    kind : dots/dash/brick/slant_brick/tri/invL/ell/coal
    cx, cy : 段区宽/高（单元格个数）
    r_base : 全局行相位锚——逐段连续绘制时传入，使段间错缝/错开接续
    cw_px, ch_px : 单元格屏幕像素尺寸（宽/高）。斜线45°/三角60°等屏幕
        等比几何按像素定义，不随图幅纵横比漂移；None 按正方格处理。

    返回 (pts, segs)
        pts  : [(x, y), ...]     散点（砂岩圆点，蜂窝交错）
        segs : [(xs, ys), ...]   独立折线，互不相连（无多余连接）

    【2026-10-19 机制化】全部几何比例从 _SYMBOL_GEOM[kind] 读取（单一几何
    定义源），本函数只实现生成逻辑、不持有任何几何常数——改符号只改注册表。
    """
    if kind == 'none':
        return [], []            # 无符号类：任何路径都不画（图例只画底色框）
    _G = _SYMBOL_GEOM.get(kind, {})
    if cw_px is None or cw_px <= 0:
        cw_px = 1.0
    if ch_px is None or ch_px <= 0:
        ch_px = 1.0
    _EPS = 1e-9
    pts, segs = [], []
    if kind == 'dots':
        # 砂岩 = 蜂窝交错圆点：偶行顶到两端、奇行错半格（位于相邻偶行两点
        # 正中间）——2026-09-29 用户参考图放大确认的最终口径
        r = 0
        while (r + 0.5) <= cy + _EPS:
            stag = _G.get('stagger', 0.5) if ((r_base + r) % 2) else 0.0
            c = 0
            while (c + 0.5 + stag) <= cx + _EPS:
                pts.append((c + 0.5 + stag, r + 0.5))
                c += 1
            r += 1
    elif kind == 'dash':
        # 泥岩 = 行中标横短线（半宽 0.32 格，裁剪到格区内）
        r = 0
        while (r + 0.5) <= cy + _EPS:
            c = 0
            while (c + 0.5) <= cx + _EPS:
                _hw = _G.get('half_w', 0.32)
                xa = max(c + 0.5 - _hw, 0.0)
                xb = min(c + 0.5 + _hw, cx)
                if xb - xa > _EPS:
                    segs.append(([xa, xb], [r + 0.5, r + 0.5]))
                c += 1
            r += 1
    elif kind == 'brick':
        # 灰岩 = 错缝砖墙：横缝在行界线、竖缝纵贯整行（砖宽 2 格）、奇偶行
        # 错开半砖——与 lith281.bmp/Limestone.png 一致
        r = 0
        while r <= cy + _EPS:
            zt = float(r)
            zb = min(r + 1.0, cy)
            if r >= 1:
                segs.append(([0.0, cx], [zt, zt]))      # 排间横缝（行界线）
            off = _G.get('brick_w', 2.0) / 2.0 if ((r_base + r) % 2) else 0.0
            xj = off
            while xj <= cx + _EPS:
                if xj > _EPS and (cx - xj) > _EPS:      # 贴边缝不画（有边框）
                    segs.append(([xj, xj], [zt, zb]))   # 竖缝纵贯整行
                xj += _G.get('brick_w', 2.0)
            r += 1
    elif kind == 'slant_brick':
        # 白云岩 = 行间横缝 + 行中短斜线（╱ 悬空不触上下横缝），行间错开
        # 半砖，无竖缝——以 Dolomite.png 为准；斜线屏幕 45°（hx/hz 像素等距）
        # 【2026-10-19 用户要求】斜线 span 由 0.80 行收窄到 0.56 行（上下各留
        # 0.22 行间隙）——旧版斜线端点离横缝仅 0.1 行(≈0.9px)，线宽半覆盖后
        # 视觉粘连成连通 zigzag（"上下的斜线连在一块"）
        hz = _G.get('hz', 0.28)                   # 斜线半高（格）
        hx = hz * (ch_px / cw_px)                 # 屏幕45°：hx_px=hz_px
        r = 0
        while (r + 0.5) <= cy + _EPS:
            if r >= 1:
                segs.append(([0.0, cx], [float(r), float(r)]))
            off = 1.0 if ((r_base + r) % 2) else 0.0
            xc = off + _G.get('brick_w', 2.0) / 2.0  # 斜线在砖中（偶数行1,3,5…）
            while xc <= cx + _EPS:
                if (xc - hx) > _EPS and (xc + hx) < (cx - _EPS):
                    segs.append(([xc - hx, xc + hx],
                                 [r + 0.5 + hz, r + 0.5 - hz]))
                xc += _G.get('brick_w', 2.0)
            r += 1
    elif kind == 'tri':
        # 硬石膏 = 无底倒三角（∧，无底边，Anhydrite.png），行间错开半格；
        # 顶角 60°（hw=0.577·腿高），屏幕等比不漂移。
        # 【2026-10-19 用户要求】三角行**等距分布**：顶边距=行间隙=底边距，
        # 首排/末排符号与中间排视觉间距一致（旧版首排尖点贴顶边、末排贴底，
        # 行距不齐）
        rows_n = max(1, int(round(cy)))
        py = cy / rows_n                                # 实际行距（格）
        th = _G.get('leg_frac', 0.5) * py               # 腿高=半行距
        g = (cy - rows_n * th) / (rows_n + 1.0)         # 边距=行间隙（等距闭合）
        hw = _G.get('angle_k', 0.577) * th * (ch_px / cw_px)  # 屏幕顶角 60°
        for kk in range(rows_n):
            za = (kk + 1) * g + kk * th                 # 尖点（上/浅）
            zb = za + th                                # 两腿端（下/深）
            stag = 0.5 if ((r_base + kk) % 2) else 0.0
            c = 0
            while (c + stag) <= (cx + 1.0):             # 越界由守卫跳过
                xc = c + stag
                if (xc - hw) >= -_EPS and (xc + hw) <= (cx + _EPS):
                    segs.append(([xc - hw, xc, xc + hw],
                                 [zb, za, zb]))
                c += 2
    elif kind == 'invL':
        # 火成岩/玄武岩 = 倒L形（Γ：顶横杠+左竖杠，Basalt.bmp），红底由
        # 背景色提供；行间错开半格，杠间不相连
        # 【2026-10-19 用户定案】短横线在上、长竖线在左（Basalt.bmp 实测：
        # 横杠 4/8 周期、竖杠 5/8 周期；旧版 gw=0.9/gh=0.55 比例画反）
        gw = _G.get('gw', 0.5)                          # 顶横杠宽（格）——短横
        gh = _G.get('gh', 0.65)                         # 竖杠高（格）——长竖
        r = 0
        while (r + 0.5) <= cy + _EPS:
            ztop = r + _G.get('top_pad', 0.05)
            stag = 0.5 if ((r_base + r) % 2) else 0.0
            c = 0
            while (c + stag) <= (cx + 1.0):
                xc = c + stag
                if (xc + gw) <= (cx + _EPS):
                    segs.append(([xc, xc + gw], [ztop, ztop]))       # 顶横杠
                    segs.append(([xc, xc],                           # 左竖杠
                                 [ztop, min(ztop + gh, cy)]))
                c += 2
            r += 1
    elif kind == 'ell':
        # 盐岩 = 错开L形（竖边+底部右横边），行间错开半格
        vh = _G.get('vh', 0.85)
        hw = _G.get('hw', 0.6)
        r = 0
        while (r + 0.5) <= cy + _EPS:
            stag = 0.5 if ((r_base + r) % 2) else 0.0
            c = 0
            while (c + stag) <= (cx + 1.0):
                xc = c + stag
                if (xc + hw) <= (cx + _EPS):
                    yb = min(r + 0.5 + vh, cy)
                    segs.append(([xc, xc, xc + hw], [r + 0.5, yb, yb]))
                c += 2
            r += 1
    else:
        # coal：行中横线（灰色，由绘制端着色）
        # 【2026-10-20 机制护栏】只有 kind=='coal' 走此分支；未知/ref 等
        # 未注册 kind 一律不画（防止参考图加载失败时冒充煤横线——玄武岩
        # 图例"横线拉伸"即此 bug 的实际表现）
        if kind != 'coal':
            return [], []
        r = 0
        _x0 = _G.get('x0_frac', 0.15) * cx
        _x1 = _G.get('x1_frac', 0.85) * cx
        while (r + 0.5) <= cy + _EPS:
            segs.append(([_x0, _x1], [r + 0.5, r + 0.5]))
            r += 1
    return pts, segs


def _lith_pattern_points(ax, lith_name, z0, z1, x0, x1, tile_origin=None):
    """生成统一岩性符号的坐标点（按**像素**等间距，天然有界、不会拉伸变形）。

    【2026-10-19 统一】几何走 _lith_pattern_core（图例与实体同一核心），
    本函数只负责：像素等距单元格（dx/dy）→ 格子数（cx/cy）→ 行相位全局
    锚定（r_base）→ 格子坐标映射回数据坐标。

    返回 (kind, xs, ys)（xs/ys 以 NaN 分隔各独立折线）
    tile_origin : 全局深度锚点（profile道逐行条带调用时传入）——矢量符号的
        行相位按绝对深度计算，使相邻条带间错缝/错开接续，不会每条带都从
        第0行重来（与图片瓦片同一锚定语义）。
    """
    kind = _lith_pattern_kind(lith_name)
    if kind in ('image', 'ref'):
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
        pitch = _lith_pitch_px(kind)      # 与图例/全程序同一来源（机制化）
        dx = max(pitch * xpi, x0d / LITH_MAX_COLS)
        dy = max(pitch * ypi, z0d / LITH_MAX_ROWS)
    cx = x0d / dx
    cy = z0d / dy
    # 行相位全局锚定：tile_origin 给定时按绝对深度推算首行行号，
    # 使逐行条带（profile道）间错缝/错开接续
    r_base = 0
    if tile_origin is not None and dy > 1e-12:
        r_base = int(math.floor((z0 - tile_origin) / dy + 1e-6))
    # 单元格屏幕像素尺寸（dx=pitch·xpi、dy=pitch·ypi → 除回去即 pitch；
    # 触发防御上限时取实际值，保斜线45°/三角60°屏幕等比）
    if scale is not None and abs(scale[0]) > 0 and abs(scale[1]) > 0:
        cw_px = dx / abs(scale[0])
        ch_px = dy / abs(scale[1])
    else:
        cw_px = ch_px = None      # 退化：核心按正方格处理
    pts, segs = _lith_pattern_core(kind, cx, cy, r_base=r_base,
                                   cw_px=cw_px, ch_px=ch_px)
    xs, ys = [], []
    for (u, v) in pts:
        xs.append(x0 + u * dx)
        ys.append(z0 + v * dy)
    for (us, vs) in segs:
        for u, v in zip(us, vs):
            xs.append(x0 + min(max(u, 0.0), cx) * dx)     # 裁到段内（防御）
            ys.append(z0 + min(max(v, 0.0), cy) * dy)
        xs.append(np.nan)
        ys.append(np.nan)
    return kind, xs, ys


def _plot_lith_points(ax, kind, xs, ys, zorder=10):
    if not len(xs):
        return
    _st = _lith_style(kind)      # 与图例/全程序同一来源（机制化）
    # 【2026-10-19 机制化】snap=False：NaN 复合路径 mpl 本就不 snap（带 AA），
    # 图例端每条独立路径默认 snap（硬边）——显式统一关闭，两端 AA 行为一致
    if kind == 'dots':
        ax.plot(xs, ys, 'o', color=_st['color'], ms=_st['dot_ms'], mew=_st['dot_mew'],
                linestyle='none', zorder=zorder, snap=False)
    else:
        ax.plot(xs, ys, '-', color=_st['color'], lw=_st['lw'], zorder=zorder,
                snap=False)


def draw_lithology_pattern(ax, lith_name, z0, z1, x0=0.0, x1=None,
                           fill_bg=True, bg_color=None, zorder=10,
                           tile_origin=None, clip_patch=None):
    """**统一**岩性符号绘制入口：岩性道、profile道、图例方框都调用本函数。

    参数
    ----
    ax : matplotlib Axes
    lith_name : 岩性名（英文小写或中文）
    z0, z1 : 深度区间（z0 小、z1 大）
    x0, x1 : 道内水平范围（数据坐标）
    fill_bg : 是否绘制背景色
    bg_color : 自定义背景色（profile道按矿物配色时传入）
    tile_origin : 图片瓦片网格全局锚点（绝对深度）。矢量/image 类 None 时锚定
        z0（与旧行为一致）；ref 类 None 时锚定绝对深度 0（行线跨段全局对齐，
        2026-10-20 行相位规则）；剖面道逐行带调用时传全局锚点，使相邻行带
        接续同一瓦片网格，图案连续不重复。
    clip_patch : matplotlib PathPatch（data 坐标），可选
        【2026-10-30 R50】显式可见区域多边形：矿物带/余量带整段绘制时传
        逐点 bounds 线性多边形（_lith_clip_path），锯齿边界保留且符号不越
        界。None=默认矩形 [x0,x1]×[z0,z1]。

    【2026-10-30 R49 防复发不变量】（违反任何一条都会复活 R48 类"大面积
    只有底色/一行有一行没有"的斑驳，改动渲染链路后必须先过
    _test_symbol_texture.py 门禁再出图）：
      1) ref/brick/slant_brick 类一律整段一次调用（允许任意切分——相位由
         全局网格 g0 保证），**严禁**在渲染内部按段边界裁剪瓦片 extent
         （R48 根因）；
      2) 全图所有调用统一传 tile_origin=图幅 depth_min（两道的
         _tile_anchor），行线跨道对齐，image/vector 类不按段顶重启相位；
      3) 分段唯一源 _contiguous_lith_runs（岩性道与 PROFILE 道共用）；
      4) 符号行间距均匀性由 _test_symbol_texture.py 像素级自动检测。
    """
    if x1 is None:
        x1 = SYMBOL_X_EXTENT
    if (x1 - x0) <= 0 or (z1 - z0) <= 0:
        return
    # 【2026-10-09 公英制自适应】符号平铺间距按深度单位换算：
    # 米井 TILE_DEPTH_M=1.0m，英尺井换算为 1/0.3048=3.2808ft
    _du_now = DEPTH_UNIT if DEPTH_UNIT != 'auto' else 'm'
    tile_span = TILE_DEPTH_M if _du_now == 'm' else TILE_DEPTH_M / 0.3048
    name = str(lith_name).lower()
    if fill_bg:
        ax.fill_betweenx([z0, z1], x0, x1,
                         color=bg_color or _lith_bg_color(name),
                         alpha=0.95, zorder=zorder - 1)
    kind, xs, ys = _lith_pattern_points(ax, name, z0, z1, x0, x1,
                                        tile_origin=tile_origin)
    if kind == 'ref':
        # 【2026-10-20 参考图墨迹机制】参考图墨迹瓦片按正方格铺排：
        # 格距 = _SYMBOL_PITCH['ref'] 屏幕像素（与矢量同一间距机制），行相位
        # 全局锚定 tile_origin（与图片瓦片同一锚定语义）；缩放瓦片与图例
        # 同一 tpx（=格距），保证实体=图例逐像素一致。
        ref = _SYMBOL_REF_IMAGE.get(name)
        tile = _lith_ink_tile(ref) if ref else None
        if tile is None:
            return
        scale = _axes_data_per_px(ax)
        # 【2026-10-22】瓦片横纵尺寸可不同（原生 motif 单元模式）：dx 用瓦片
        # 宽、dy 用瓦片高 ⇒ 泥岩横线/砂岩点阵各自保持参考图比例且疏密可调。
        _tw, _th = _lith_ref_tile_size(ref)
        x0d = max(x1 - x0, 1e-9)
        z0d = max(z1 - z0, 1e-9)
        # 【2026-10-23 R21】瓦片**栅格**边长：原生 motif 单元模式按单元像素；
        # 其余按 min(原生, 格距×SS)（见 _lith_ref_raster）。栅格只影响"细节
        # 密度"，dx/dy 仍按格距像素算 ⇒ 符号物理尺寸与用户已确认口径不变。
        _tpx = (int(round(_tw)) if str(ref) in _SYMBOL_REF_UNIT
                else _lith_ref_raster(ref))
        if scale is not None:
            dx = max(_tw * abs(scale[0]), x0d / LITH_MAX_COLS)
            # 【R33】格距只按设备像素密度（原生 motif 行高），不再随段高
            # 放大——旧 dy=max(..., z0d/LITH_MAX_ROWS) 对厚泥岩长段把横线
            # 间距放大（XIMENIA-5 厚泥岩段横线周期 8pt vs 互层段 4pt，
            # 用户反馈"1807m/1997m 以下泥岩符号明显不一样"）。内存防护
            # 由下方按行分块渲染承担。
            dy = _th * abs(scale[1])
        else:
            dx = x0d / 12.0
            dy = z0d / 12.0
        # 【2026-10-20 行相位规则】默认锚定绝对深度 0（非段顶）：同一道内
        # 相邻段/相邻岩性的行线落在同一全局网格上，跨段接续对齐（配合瓦片
        # 行相位对齐与"格距=N行×统一行高"）；tile_origin 显式传入时以其为准。
        _org = 0.0 if tile_origin is None else float(tile_origin)
        # 【2026-10-26 R22】列相位全局锚定 x=0：profile 道按 bounds 漂移切分
        #   的子段各自从自身 x0 起排瓦片 → 段界竖缝/砖缝水平错位（用户反馈
        #   "错开的竖线"）。统一锚定 x=0 后同道内所有段共享同一列网格。
        _x_org = 0.0
        gx0 = _x_org + math.floor((x0 - _x_org) / dx + 1e-9) * dx
        g0 = _org + math.floor((z0 - _org) / dy + 1e-9) * dy
        n_rows = max(1, int(math.ceil((z1 - g0) / dy - 1e-9)))
        n_cols = max(1, int(math.ceil((x1 - gx0) / dx - 1e-9)))
        # 【R33】删除"巨型段放大格距"防御（_f 倍增）：同一符号在任意
        # 厚度井段格距必须一致（与参考图逐形一致铁律）。内存防护由下方
        # 按行分块渲染承担（每块行数受 _LITH_REF_MAX_PIX 约束）。
        # 【2026-10-26 R25】_SYMBOL_REF_RASTER 覆盖图(白云岩)设备1:1模式:
        # 瓦片阵列按**最终显示设备像素数**预采样(PIL BOX), imshow 用
        # nearest 1:1 贴图 —— 消除 mpl antialiased 二次重采样把 2px 斜杠
        # 糊成 ~1px 灰线(整页 150dpi 栅格下 122px 阵列压到 54px 格的
        # 必然结果, 用户反馈"斜线不直/短竖线")。其余参考图维持原链路。
        if str(ref) in _SYMBOL_VECTOR and scale is not None:
            # R26 矢量岩性: 按最终显示设备像素直接重绘(降采样链路对细斜线
            # motif 无解, 见 _lith_vector_tile), nearest 1:1 贴图。
            _dev_w = max(8.0, dx / abs(scale[0]))
            _dev_h = max(8.0, dy / abs(scale[1]))
            _tile = _lith_vector_tile(ref, (_dev_w, _dev_h))
            _im_interp = 'nearest'
        elif str(ref) in _SYMBOL_REF_RASTER and scale is not None:
            _dev_px = (dx / abs(scale[0]) + dy / abs(scale[1])) / 2.0
            _tile = _lith_ink_tile(ref, tpx=int(max(8, round(_dev_px))))
            _im_interp = 'nearest'
        else:
            _tile = _lith_ink_tile(ref, tpx=_tpx)
            _im_interp = 'antialiased'
        if _tile is None:
            return
        # 【2026-10-23 R21】栅格换算一律用**实际瓦片像素数**（_hpx/_vpx），
        # 不再假设"栅格边长 = 格距像素"（高分辨率栅格后二者已不同）。
        _hpx = int(_tile.shape[1])
        _vpx = int(_tile.shape[0])
        # 【R33】按行分块渲染：每块行数受 _LITH_REF_MAX_PIX 约束，格距
        # 恒定不变；块间共享全局网格（g0 行相位锚定 + gx0 列锚）→ 跨块
        # 图案无缝接续。精确裁剪仍以 gx0 为基准（R22），clip_path 限定段区。
        from matplotlib.patches import Rectangle as _Rect
        # 【2026-10-30 R50】clip_patch：调用方传逐点边界多边形时直接使用
        # （矿物带/余量带整段绘制，可见性精确到锯齿边界）；默认矩形段。
        _clip = (clip_patch if clip_patch is not None else
                 _Rect((x0, z0), x1 - x0, z1 - z0, transform=ax.transData))
        _cap_rows = max(16, int(_LITH_REF_MAX_PIX /
                                max(1, n_cols * max(1, _tpx) * max(1, _tpx))))
        _k_a = max(0, int(math.floor((z0 - g0) / dy - 1e-9)))
        _k_b = max(_k_a + 1, int(math.ceil((z1 - g0) / dy + 1e-9)))
        try:
            _ka = _k_a
            while _ka < _k_b:
                _kb = min(_ka + _cap_rows, _k_b)
                _z0c = g0 + _ka * dy
                _nr = _kb - _ka
                big = np.tile(_tile, (_nr, n_cols, 1))
                _cpx = min(big.shape[1], max(1, int(round(
                    (x1 - gx0) / dx * _hpx))))
                big = big[:, :_cpx]
                # 【2026-10-30 R48 相位修复】extent 必须**原样覆盖完整格行**
                # [_z0c, _z0c+_nr*dy]，可见性交给 clip_path——旧逻辑把 extent
                # 按 z0/z1 裁剪（_rpx），瓦片阵列第0行（瓦片顶砖行）被锚到
                # 段边界 z1 而非全局网格边界：段高<1 个瓦片格（灰岩≈1.3m/
                # 白云岩≈2m）时每个薄片段都显示"瓦片顶部同一砖行"或空切片
                # ⇒ PROFILE 道矿物带（漂移切分子段）与岩性道薄互层（交界处）
                # 呈"大多只有底色、砖纹成孤立条纹"的斑驳（111D 用户反馈）。
                # 相位由全局网格 g0/_k_a 保证，段内可见部分落在正确瓦片行。
                im = ax.imshow(big,
                               extent=[gx0, gx0 + _cpx / float(_hpx) * dx,
                                       _z0c + _nr * dy, _z0c],
                               aspect='auto', interpolation=_im_interp,
                               zorder=zorder, snap=False)
                im.set_clip_path(_clip)
                _ka = _kb
        except Exception as exc:
            logger.warning('ref 墨迹瓦片实体绘制失败 %s: %s', name, exc)
        return
    if kind == 'image':
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
        # 【2026-10-15】瓦片网格锚定：默认锚定段顶(z0)——与旧行为一致；
        # 剖面道逐行带调用时传全局 tile_origin，使相邻行带接续同一瓦片网格，
        # 图案连续不出现重复顶条
        _org = z0 if tile_origin is None else tile_origin
        k0 = math.ceil((z0 - _org) / tile_span - 1e-9)
        k1 = math.floor((z1 - _org) / tile_span + 1e-9)
        for k in range(k0, k1 + 1):
            t0 = _org + k * tile_span
            t1 = t0 + tile_span
            lo = max(t0, z0)
            hi = min(t1, z1)
            if hi - lo <= 1e-9:
                continue
            if t0 >= z0 - 1e-9 and t1 <= z1 + 1e-9:
                ax.imshow(tile, extent=[x0, x1, t1, t0],
                          aspect='auto', interpolation='nearest',
                          clip_on=True, zorder=zorder)
            else:
                r_top = max(0, int(round((lo - t0) / tile_span * SYMBOL_TILE_PX)))
                r_bot = min(SYMBOL_TILE_PX,
                            max(r_top + 1, int(round((hi - t0) / tile_span * SYMBOL_TILE_PX))))
                ax.imshow(tile[r_top:r_bot, :, :], extent=[x0, x1, hi, lo],
                          aspect='auto', interpolation='nearest',
                          clip_on=True, zorder=zorder)
        return
    _plot_lith_points(ax, kind, xs, ys, zorder=zorder)


def _place_legend_tile(fig, big, x0, y0, w, h, zorder):
    """把已铺好的图例瓦片数组贴入 fig 坐标系的方框（BboxImage 路径）。"""
    from matplotlib.image import BboxImage
    from matplotlib.transforms import Bbox

    def _bbox_px(renderer, _fx=x0, _fy=y0, _fw=w, _fh=h):
        _cw, _ch = renderer.get_canvas_width_height()
        return Bbox([[_fx * _cw, _fy * _ch],
                     [(_fx + _fw) * _cw, (_fy + _fh) * _ch]])
    bbox_img = BboxImage(_bbox_px, zorder=zorder,
                         interpolation='nearest', origin='upper')
    bbox_img.set_data(big)
    fig.add_artist(bbox_img)


def draw_lithology_pattern_fig(fig, lith_name, x0, y0, w, h,
                               bg_color=None, zorder=6002, pitch_px=None,
                               motif=False):
    """在图形坐标系(fig.transFigure)内绘制统一岩性符号——图例方框专用。

    【2026-10-19 统一】几何与道内实体同一核心：本函数按方框**实际像素**
    尺寸换算行列数后调用 _lith_pattern_core，再做 fig 坐标映射（y 翻转，
    第0行在方框顶部=道内段顶）——图例即实体的重复，两处零偏差、无多余
    连接。间距按岩性类别取（dots=LITH_PATTERN_PITCH_PX、其余=
    LITH_PATTERN_PITCH_PX_DASH），与道内实体完全同一套；pitch_px 参数
    仅为兼容旧调用保留（dots 类取值一致）。

    【2026-10-19 修复】①name=='blank'（孔隙度图例）只画底色方框即返回，
    不再落进默认分支画出灰横线；②砂岩圆点补 mew=0（与实体 _plot_lith_points
    同口径）——旧版默认 markeredgewidth=1pt 使点径 1+1=2pt≈点距，图例小框内
    点粘连呈"大小不一致"；③motif=True：微框（如 LAS 信息区 40×7.5pt swatch）
    固定 4×2 格单 motif，按像素铺排会在微框内退化成不可辨认的碎片。
    """
    name = str(lith_name).lower()
    kind = _lith_pattern_kind(name)
    from matplotlib.lines import Line2D
    if bg_color is not None:
        fig.add_artist(plt.Rectangle((x0, y0), w, h, transform=fig.transFigure,
                                     facecolor=bg_color, edgecolor='black',
                                     lw=0.5, zorder=zorder - 1))
    if kind == 'none':
        return          # 孔隙度/套管/未知名：只画底色框（机制化，全路径同行为）
    if kind == 'ref':
        # 【2026-10-20 参考图墨迹机制】图例 = 实体的重复：同一墨迹瓦片、
        # 同一格距（_SYMBOL_PITCH['ref']）、同一缩放 tpx，铺排后 BboxImage
        # 贴入方框。motif 微框（LAS 信息区）：格子=框高，单行按宽铺排。
        ref = _SYMBOL_REF_IMAGE.get(name)
        tile = _lith_ink_tile(ref) if ref else None
        if tile is not None:
            from matplotlib.image import BboxImage
            from matplotlib.transforms import Bbox
            _dpi = float(fig.dpi or 150)
            _w_px = max(1.0, w * fig.get_figwidth() * _dpi)
            _h_px = max(1.0, h * fig.get_figheight() * _dpi)
            # 【2026-10-22】原生 motif 单元模式（砂/泥）：图例与实体用**同一**
            # 单元瓦片、同一 tw/th ⇒ 图例即实体的重复，两端零偏差。
            _unit = _SYMBOL_REF_UNIT.get(str(ref))
            if _unit:
                _tw, _th = _lith_ref_tile_size(ref)
                _rows = max(1, int(math.ceil(_h_px / _th - 1e-9)))
                _cols = max(1, int(math.ceil(_w_px / _tw - 1e-9)))
                _tile = _lith_ink_tile(ref)
                if _tile is not None:
                    big = np.tile(_tile, (_rows, _cols, 1))
                    _rpx = max(1, min(big.shape[0], int(round(_h_px))))
                    _cpx = max(1, min(big.shape[1], int(round(_w_px))))
                    big = big[:_rpx, :_cpx]
                    _place_legend_tile(fig, big, x0, y0, w, h, zorder)
                    return
            if motif:
                _cell = float(np.clip(_h_px, 8.0, 48.0))
            else:
                _cell = _lith_ref_pitch(ref)       # 与实体同一格距（机制化）
            # 【2026-10-26 R25】小框缩略模式: 框高不足一个格距时, 把**整张
            # 瓦片**单次 BOX 采样到框设备像素(全部 motif 行可见, 与参考图
            # 缩略观感一致), 替代旧"裁角+二次重采样"链(碎斜线/短竖线/
            # 行残缺, 用户反馈图头图例白云岩不可辨)。
            if (not motif) and _h_px < _cell * 0.75:
                _tw2 = max(4, int(round(_w_px)))
                _th2 = max(4, int(round(_h_px)))
                if str(ref) in _SYMBOL_VECTOR:
                    # R26 矢量岩性: 按框设备像素直接绘制(整瓦二次缩样会把
                    # 细斜缝再稀释一次, 图例小样必须与实体同一矢量链路)
                    _tarr = _lith_vector_tile(ref, (_tw2, _th2))
                else:
                    _tarr = _lith_ink_tile(ref)
                if _tarr is not None:
                    from PIL import Image as _PILImg
                    if (str(ref) in _SYMBOL_VECTOR
                            and _tarr.shape[0] == _th2
                            and _tarr.shape[1] == _tw2):
                        _mini = np.clip(_tarr[..., :3], 0.0, 1.0)
                    else:
                        _u8 = (np.clip(_tarr[..., :3], 0.0, 1.0)
                               * 255).astype(np.uint8)
                        _mini = np.asarray(
                            _PILImg.fromarray(_u8, 'RGB').resize(
                                (_tw2, _th2), _PILImg.BOX)).astype(
                                    np.float32) / 255.0
                    _alpha = np.ones(_mini.shape[:2] + (1,),
                                     dtype=np.float32)
                    big = np.concatenate([_mini, _alpha], axis=2)

                    def _bbox_px(renderer, _fx=x0, _fy=y0,
                                 _fw=w, _fh=h):
                        _cw, _ch = renderer.get_canvas_width_height()
                        return Bbox([[_fx * _cw, _fy * _ch],
                                     [(_fx + _fw) * _cw,
                                      (_fy + _fh) * _ch]])
                    bbox_img = BboxImage(_bbox_px, zorder=zorder,
                                         interpolation='nearest',
                                         origin='upper')
                    bbox_img.set_data(big)
                    fig.add_artist(bbox_img)
                    return
            _rows = max(1, int(math.ceil(_h_px / _cell - 1e-9)))
            _cols = max(1, int(math.ceil(_w_px / _cell - 1e-9)))
            # 【2026-10-23 R21】图例与实体道用**同一栅格规格**
            # （_lith_ref_raster：min(原生, 格距×SS)）⇒ 两端同一张瓦片、
            # 同一图案；BboxImage 按框尺寸重采样，PNG/PDF 均可辨。
            # 【R21-4】motif 微框例外：motif 语义是"框里显示**一个** motif"，
            # _cell=框高像素，_tpx 必须等于 _cell 才与框 1:1（否则整张参考图被
            # 缩进框里，与实体道单 motif 不一致）。
            _tpx = (max(8, int(round(_cell))) if motif
                    else _lith_ref_raster(ref))
            if str(ref) in _SYMBOL_VECTOR:
                # R26 矢量岩性: 按格距设备像素绘制, BboxImage nearest 1:1
                _tile = _lith_vector_tile(ref, max(8, int(round(_cell))))
            else:
                _tile = _lith_ink_tile(ref, tpx=_tpx)
            if _tile is not None:
                _hpx_t = int(_tile.shape[1])
                _vpx_t = int(_tile.shape[0])
                big = np.tile(_tile, (_rows, _cols, 1))
                _rpx = max(1, min(big.shape[0],
                                  int(round(_h_px / _cell * _vpx_t))))
                _cpx = max(1, min(big.shape[1],
                                  int(round(_w_px / _cell * _hpx_t))))
                big = big[:_rpx, :_cpx]

                def _bbox_px(renderer, _fx=x0, _fy=y0, _fw=w, _fh=h):
                    _cw, _ch = renderer.get_canvas_width_height()
                    return Bbox([[_fx * _cw, _fy * _ch],
                                 [(_fx + _fw) * _cw, (_fy + _fh) * _ch]])
                bbox_img = BboxImage(_bbox_px, zorder=zorder,
                                     interpolation=('nearest'
                                                    if str(ref) in _SYMBOL_VECTOR
                                                    else 'antialiased'),
                                     origin='upper')
                bbox_img.set_data(big)
                fig.add_artist(bbox_img)
                return
    # 【2026-10-15 用户要求】图片符号岩性：图例方框内铺符号图片（与道内瓦片同源），
    # 不再用线条画法；无图片可用时才落到下方线条分支
    if kind == 'image':
        img, _ = _load_lithology_symbol(name)
        if img is not None:
            from matplotlib.image import BboxImage
            from matplotlib.transforms import Bbox
            # 【2026-10-16 修复】mpl 3.11 BboxImage.get_window_extent 直接返回
            # 构造 bbox（不应用 transform），make_image 又把它当**显示像素**并
            # 除以画布尺寸——fig 分数坐标 bbox 变成亚像素框导致图例图片全部
            # 不可见。改为传以 renderer 为参的 callable，在渲染期换算成像素
            # 坐标（make_image 内部再除回画布尺寸=归一化，整图铺满方框）。
            def _bbox_px(renderer, _fx=x0, _fy=y0, _fw=w, _fh=h):
                _cw, _ch = renderer.get_canvas_width_height()
                return Bbox([[_fx * _cw, _fy * _ch],
                             [(_fx + _fw) * _cw, (_fy + _fh) * _ch]])
            bbox_img = BboxImage(_bbox_px, zorder=zorder,
                                 interpolation='nearest', origin='upper')
            bbox_img.set_data(img)
            if img.ndim == 2:
                bbox_img.set_cmap('gray')
            fig.add_artist(bbox_img)
            return
    # ---------- 【2026-10-19 统一】行列数按方框实际像素/间距计算 ----------
    if motif:
        # 微框单 motif：固定 4×2 格（ LAS 信息区等小 swatch 专用）
        cx, cy = 4.0, 2.0
    else:
        _dpi = float(fig.dpi or 150)
        _w_px = max(1.0, w * fig.get_figwidth() * _dpi)
        _h_px = max(1.0, h * fig.get_figheight() * _dpi)
        _pitch = _lith_pitch_px(kind)   # 与实体/全程序同一来源（机制化）
        cx = max(2.0 if kind == 'dots' else 1.0, _w_px / _pitch)
        cy = max(2.0, _h_px / _pitch)      # ≥2 排：错缝/行界/行间错开才可见
    pts, segs = _lith_pattern_core(kind, cx, cy, r_base=0,
                                   cw_px=_pitch if not motif else 1.0,
                                   ch_px=_pitch if not motif else 1.0)
    # 格子坐标 → fig 坐标（y 翻转：格区第0行落在图例方框顶部，与道内段顶一致）
    def _X(u):
        return x0 + (u / cx) * w

    def _Y(v):
        return y0 + (1.0 - v / cy) * h
    _st = _lith_style(kind)      # 与实体/全程序同一来源（机制化）
    # 【2026-10-19 机制化】snap=False：与实体端 NaN 复合路径的 AA 行为统一
    for (u, v) in pts:
        fig.add_artist(Line2D([_X(u)], [_Y(v)], marker='o', color=_st['color'],
                              markersize=_st['dot_ms'],
                              markeredgewidth=_st['dot_mew'],
                              linestyle='none', snap=False,
                              transform=fig.transFigure, zorder=zorder))
    for (us, vs) in segs:
        fig.add_artist(Line2D([_X(u) for u in us], [_Y(v) for v in vs],
                              color=_st['color'], lw=_st['lw'], snap=False,
                              transform=fig.transFigure, zorder=zorder))


def _contiguous_lith_runs(lith_seq, valid_seq=None):
    """【2026-10-30 R49 防复发】连续同岩性游程——**两道唯一分段源**。

    岩性道分段与 PROFILE 道特殊岩性整带共用本函数，保证两道段界一致，
    消除多处手写 while 游程循环的分叉隐患（R48 相位 bug 的教训：绘制
    链路调用面越碎，几何改动越容易漏掉某一调用模式）。

    参数
    ----
    lith_seq : 岩性字符串序列（调用方先统一 lower()）
    valid_seq : 有效性序列（None=全部有效）；无效点作为分段隔断
    返回 [(i0, i1, lith)] 闭区间游程（跳过空/ nan/none/ mixed/ casing）
    """
    runs = []
    n = len(lith_seq)
    i = 0
    while i < n:
        li = str(lith_seq[i])
        ok = True if valid_seq is None else bool(valid_seq[i])
        if (not ok or not li
                or li in ('nan', 'None', 'none', 'mixed', 'casing')):
            i += 1
            continue
        j = i + 1
        while j < n and str(lith_seq[j]) == li and (
                valid_seq is None or bool(valid_seq[j])):
            j += 1
        runs.append((i, j - 1, li))
        i = j
    return runs


def _lith_clip_path(md_seg, xl_seg, xr_seg, ax):
    """【2026-10-30 R50】逐点边界线性多边形 clip（data 坐标 PathPatch）。

    PROFILE 道矿物带/余量带符号**整段**绘制时用本多边形限定可见区域：
    锯齿状逐点边界保留、符号不越入孔隙度留白/邻带，同时把 imshow 块数
    压到最少（用户定案：绘制总体规划，纵横向一致间距，不加密不空白）。
    """
    from matplotlib.path import Path as _MPath
    from matplotlib.patches import PathPatch as _PathPatch
    _m = np.asarray(md_seg, dtype=float)
    _l = np.asarray(xl_seg, dtype=float)
    _r = np.asarray(xr_seg, dtype=float)
    n = len(_m)
    verts = np.empty((2 * n, 2), dtype=float)
    verts[:n, 0] = _l
    verts[:n, 1] = _m
    verts[n:, 0] = _r[::-1]
    verts[n:, 1] = _m[::-1]
    codes = [_MPath.MOVETO] + [_MPath.LINETO] * (2 * n - 1)
    return _PathPatch(_MPath(verts, codes), transform=ax.transData,
                      facecolor='none', edgecolor='none')


# 兼容旧接口：统一走 draw_lithology_pattern
def _draw_lithology_tiles(ax, lith_name, seg_start_md, seg_end_md,
                          tile_origin=None):
    """岩性道：统一符号（水平范围 0~SYMBOL_X_EXTENT）"""
    draw_lithology_pattern(ax, lith_name, seg_start_md, seg_end_md,
                           0.0, SYMBOL_X_EXTENT, tile_origin=tile_origin)


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
        
        # 处理RGBA图片：【2026-10-16】保留alpha通道（玄武岩 volcanic.png
        # 白底已转透明，道内红色底色需透出）；其余非RGB模式转RGB
        if img_pil.mode != 'RGBA' and img_pil.mode != 'RGB':
            img_pil = img_pil.convert('RGB')
        
        # 等比缩放到 target_size，填满画布
        original_w, original_h = img_pil.size
        scale = target_size / max(original_w, original_h)
        new_w = max(1, int(original_w * scale))
        new_h = max(1, int(original_h * scale))
        img_pil = img_pil.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new(img_pil.mode, (target_size, target_size),
                           (0, 0, 0, 0) if img_pil.mode == 'RGBA'
                           else (255, 255, 255))
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
                # 【2026-10-16 用户要求】玄武岩 = volcanic.png 蓝色十字 +
                # 红色底色：volcanic.png 为不透明白底（自带全255 alpha通道），
                # 近白像素置透明，道内/图例的红色背景才能透出（十字符号
                # 蓝色不透明不变）
                if symbol_file == 'volcanic.png' and img.ndim == 3 \
                        and img.shape[-1] in (3, 4):
                    _white = (img[..., :3] > 0.92).all(axis=-1)
                    _alpha = np.where(_white, 0.0, 1.0)
                    if img.shape[-1] == 4:
                        img[..., 3] = np.minimum(img[..., 3], _alpha)
                    else:
                        img = np.dstack([img, _alpha])
                # 标准化为统一正方形尺寸 + 图案密度归一化
                img, fill_ratio = _resize_symbol_to_square(img, SYMBOL_STANDARD_SIZE)
                _lithology_symbol_cache[lith_name] = (img, fill_ratio)
                return img, fill_ratio
            except Exception as e:
                logger.warning(f"加载岩性符号图片失败 {img_path}: {e}")

    _lithology_symbol_cache[lith_name] = (None, 1.0)
    return None, 1.0


def _merge_thin_layers(segments, min_thickness=None):
    """
    将薄层（厚度 < min_thickness）合并到相邻大层，保持大层连续性。
    
    参数:
        segments: [(start_md, end_md, value), ...] 按深度排序的段列表
                  start_md < end_md（start是较浅=较小值，图上方）
        min_thickness: 最小层厚阈值；None 时按 DEPTH_UNIT 自适应
                      （米井取 MIN_LAYER_THICKNESS_M=0.25m，英尺井换算 0.82ft）
    
    返回:
        合并后的段列表，薄层已吸收到相邻大层
    """
    if min_thickness is None:
        _du_now = DEPTH_UNIT if DEPTH_UNIT != 'auto' else 'm'
        min_thickness = (MIN_LAYER_THICKNESS_M if _du_now == 'm'
                         else MIN_LAYER_THICKNESS_M / 0.3048)
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


# 同砂体流体家族（POSSIBLE归入对应主类）——与 logInt.enforce_fluid_segregation
# 的 FLUID_FAMILY_MAP 同一口径（显示层合并专用映射）
_SAME_BODY_FLUID_FAMILY = {
    'OIL': 'OIL', 'OIL_POSSIBLE': 'OIL',
    'GAS': 'GAS', 'GAS_POSSIBLE': 'GAS',
    'WATER': 'WATER', 'WATER_POSSIBLE': 'WATER',
}

# 隔层岩性（泥质岩类/煤/盐膏/套管）——同砂体合并的岩性屏障
_SAME_BODY_BARRIER_LITHS = {
    'shale', 'mudstone', 'mud', 'claystone', 'clay', 'shalestone',
    'coal', 'anthracite', 'lignite', 'carbonaceous_shale',
    'carbonaceous shale', 'casing', 'anhydrite', 'halite', 'salt',
    'gypsum', 'evaporite',
}


def _barrier_lith_thickness(data, md_lo, md_hi):
    """(md_lo, md_hi)开区间内隔层岩性连续段的最大跨度（与MD同单位）。

    用于同砂体合并的屏障判定：砂肩NonReservoir（LITHOLOGY仍为砂岩）、
    DRY/Undefined等不构成隔层；只有泥质岩类/煤/盐膏等隔层岩性的
    连续跨度 ≥ 阈值 才视为分隔两个砂体。
    """
    if 'LITHOLOGY' not in data.columns or 'MD' not in data.columns:
        return 0.0
    mds = pd.to_numeric(data['MD'], errors='coerce')
    liths = data['LITHOLOGY'].astype(str).str.lower().str.strip()
    m = (mds > md_lo) & (mds < md_hi)
    if not m.any():
        return 0.0
    seg_md = mds[m].values
    seg_bar = liths[m].isin(_SAME_BODY_BARRIER_LITHS).values
    max_t = 0.0
    run0 = None
    prev_md = None
    for md_i, is_bar in zip(seg_md, seg_bar):
        if is_bar:
            if run0 is None:
                run0 = md_i
        else:
            if run0 is not None:
                max_t = max(max_t, float(prev_md - run0))
                run0 = None
        prev_md = md_i
    if run0 is not None:
        max_t = max(max_t, float(prev_md - run0))
    return max_t


def _merge_same_body_fluid(segments, data, barrier_min_thick=3.0):
    """同砂体流体层合并——一层砂岩只能一个解释层（不分流体家族）。

    用户2026-10-09："6,7和8,9在同一个砂体内，2个或多个水层也需要合并"。
    用户2026-10-13："15,16是一个层（上部泥质高电阻率高判油、下部纯砂岩
    低阻判水，整个砂体是一个层，油水同层）；25,26是明显的水层，而不是
    2层"——异家族流体（油上水下）不再打断合并，同一砂体内合并为一个
    解释层：
      - 合并后只剩一个家族 → 标签取该家族内总跨度最长的原始值
        （保留 PROBABLE/POSSIBLE 信息）
      - 多家族并存 → 次要家族（跨度 < _MINOR_FAMILY_FRAC）并入主导家族
        只留一个结论（如 1.75ft 薄油顶 + 9ft 水层 → 水层）；其余按
        [GAS, OIL, WATER] 轻质在上顺序组合复合标签（OIL_WATER=油水同层），
        由 _paint_fluid_segment 斜对角分区绘制
    屏障判定：两段之间隔层岩性（泥质岩类/煤/盐膏）连续跨度 ≥
    barrier_min_thick 才视为真隔层打断（对同/异家族一体适用）；
    砂肩NonReservoir/DRY/薄泥岩条带不打断。
    """
    n = len(segments)
    out = []
    i = 0
    while i < n:
        start, end, val = segments[i]
        fam = _SAME_BODY_FLUID_FAMILY.get(str(val).upper())
        if fam is None:
            out.append((start, end, val))
            i += 1
            continue
        # 向后吞并：同砂体内任意家族流体段（异家族不再打断）；
        # 达标隔层岩性连续段（真隔层）打断
        j = i + 1
        last = i
        cur_end = end
        span = {str(val).upper(): end - start}
        while j < n:
            s2, e2, v2 = segments[j]
            v2u = str(v2).upper()
            f2 = _SAME_BODY_FLUID_FAMILY.get(v2u)
            if f2 is None:
                # DRY/TIGHT/Undefined/砂肩NonReservoir：不构成屏障，跨越探测
                # （真隔层岩性由下一个流体段前的屏障检查覆盖）
                j += 1
                continue
            # 两段之间存在达标隔层岩性连续段 → 真隔层打断（同/异家族同防）
            if _barrier_lith_thickness(data, cur_end, s2) >= barrier_min_thick:
                break
            span[v2u] = span.get(v2u, 0.0) + (e2 - s2)
            last = j
            cur_end = e2
            j += 1
        if last > i:
            label = _merged_body_label(span)
            out.append((start, cur_end, label))
            i = last + 1
        else:
            out.append((start, end, val))
            i += 1
    return out


# 次要流体家族并入主导的跨度占比阈值（用户2026-10-13：25/26 的 1.75ft
# 薄油顶并入 9ft 水层判水层；15/16 油水各占半壁保留油水同层复合标签）
_MINOR_FAMILY_FRAC = 0.25

# 复合标签的家族排序（轻质在上=典型深度顺序：气→油→水）
_MERGED_FAMILY_ORDER = {'GAS': 0, 'OIL': 1, 'WATER': 2}


def _merged_body_label(span):
    """同砂体多家族流体合并标签。

    span: {原始结论值(大写): 跨度}。次要家族（家族总跨度 < 25%）并入主导；
    剩余单家族 → 取该家族内跨度最长的原始值；多家族 → 按 [GAS, OIL, WATER]
    顺序组合复合标签（如 OIL_WATER 油水同层，_paint_fluid_segment 斜对角绘制）。
    """
    total = sum(span.values())
    fam_span = {}
    raw_by_fam = {}
    for v, t in span.items():
        f = _SAME_BODY_FLUID_FAMILY.get(v, str(v).upper())
        fam_span[f] = fam_span.get(f, 0.0) + t
        raw_by_fam.setdefault(f, {}).setdefault(v, 0.0)
        raw_by_fam[f][v] += t
    keep = [f for f, t in fam_span.items() if t >= _MINOR_FAMILY_FRAC * total]
    if not keep:
        keep = [max(fam_span, key=fam_span.get)]
    if len(keep) == 1:
        raws = raw_by_fam[keep[0]]
        return max(raws, key=raws.get)
    keep.sort(key=lambda f: _MERGED_FAMILY_ORDER.get(f, 9))
    return '_'.join(keep)


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


def _draw_logo_pair(fig, company_logo=None, contractor_logo=None,
                    logo_cx=0.5, logo_h_ratio=0.68, title_zone_top=None):
    """在图头页/正图页绘制左上 company 图标、右上 contractor 图标。

    Args:
        fig: 目标 figure
        company_logo/contractor_logo: 图标路径（随井的业主动态更换），
            None 用 symbol 目录默认 company.png/contractor.png
        logo_cx: 图标中心的纵向位置（figure 坐标 y）
        logo_h_ratio: 图标高度（相对标题区高度）
        title_zone_top: 标题区顶部（figure 坐标 y，用于计算图标高度）
    """
    try:
        from PIL import Image as _PIL_IMG
        _sym_dir = Path(SYMBOL_DIR)
        if title_zone_top is None:
            title_zone_top = logo_cx + logo_h_ratio / 2.0
        _logo_h = (title_zone_top - (logo_cx - logo_h_ratio / 2.0)) * logo_h_ratio
        for _side, _fname, _override in (('left', 'company.png', company_logo),
                                         ('right', 'contractor.png', contractor_logo)):
            _logo_p = Path(_override) if _override else (_sym_dir / _fname)
            if not _logo_p.exists():
                logger.warning("图标文件不存在, 跳过: %s", _logo_p)
                continue
            _pil = _PIL_IMG.open(str(_logo_p)).convert('RGBA')
            _ratio = _pil.width / max(_pil.height, 1)
            _logo_w = _logo_h * _ratio
            _x0 = 0.008 if _side == 'left' else 0.992 - _logo_w
            _lax = fig.add_axes([_x0, logo_cx - _logo_h / 2.0, _logo_w, _logo_h],
                                zorder=6000)
            _lax.imshow(_pil, aspect='auto')
            _lax.axis('off')
            for _sp in _lax.spines.values():
                _sp.set_visible(False)
            logger.info("图头图标 %s 已绘制: %s", _side, _logo_p.name)
    except Exception as _le:
        logger.warning('图头图标绘制失败（不影响主图）: %s', _le)


# =====================================================================
# 【2026-10-10 quick look 严格对齐 BET-1 样本版式】竖排工具
# 样本 BET-1_8.5IN_SLAM_Res_MD200_20261003.pdf 页首为 masterlog 老式
# "转置 90 度"竖排表：label 竖排 + value 竖排（列式），右上为竖排标题块。
# =====================================================================

def _vtext(fig, x, y, text, fontsize=7, weight='normal', color='black',
           va='top', fontfamily='Microsoft YaHei', char_dy=None):
    """竖排文字：逐字符从上到下竖排（模拟扫描件 masterlog 转置 90 度）。

    Args:
        x: 列中心（figure 坐标 0-1）
        y: 起始 y（figure 坐标；va='top' 时向下逐字排）
        char_dy: 单字符纵向间距（figure 单位）；None 时按字号自动计算
    Returns:
        结束 y（最后一个字符中心）
    """
    s = str(text)
    if not s:
        return y
    fh = fig.get_figheight()
    if char_dy is None:
        char_dy = fontsize * 1.45 / 72.0 / fh  # 含行距的字符高（figure 单位）
    yy = y
    for _ch in s:
        fig.text(x, yy, _ch, fontsize=fontsize, ha='center', va='center',
                 rotation=-90, fontweight=weight, color=color,
                 fontfamily=fontfamily, zorder=3002)
        yy -= char_dy
    return yy


def _ql_vtable(fig, x_left, x_right, y_top, y_bottom, rows, fontsize=6.5,
               value_color='#0033CC', label_weight='normal'):
    """竖排转置表（样本第 0 页样式）：每列 = 竖排 label（上）+ 竖排 value（下）。

    Args:
        rows: [(label, value), ...] —— 第 1 个字段排在最右列（样本从右到左）
        x_left/x_right: 表区左右边界（figure 坐标）
        y_top/y_bottom: 表区上下边界（figure 坐标）
    返回: (label区底, value区底) 供后续布局参考
    """
    from matplotlib.lines import Line2D
    n = max(len(rows), 1)
    col_w = (x_right - x_left) / n
    # 自适应 label/value 分界：label 区高度 = 最长 label 字符数 × 字符高
    fh = fig.get_figheight()
    _cd = fontsize * 1.45 / 72.0 / fh
    _max_lab = max((len(str(l)) for l, _ in rows), default=1)
    _max_val = max((len(str(v)) for _, v in rows), default=1)
    _lab_h = _max_lab * _cd
    _val_h = _max_val * _cd
    _tot_h = y_top - y_bottom
    # label 区不超过表高 60%，value 区不少于表高 30%
    _lab_frac = min(0.60, max(0.30, _lab_h / _tot_h))
    if _lab_h + _val_h > _tot_h * 1.05:
        _lab_frac = min(0.55, _lab_h / max(_lab_h + _val_h, 1e-9))
    y_mid = y_top - _tot_h * _lab_frac
    for i, (lab, val) in enumerate(rows):
        cx = x_right - (i + 0.5) * col_w  # 从右到左（样本：Corrected BY 最左、Company 最右）
        # 列分隔线
        if i > 0:
            fig.add_artist(Line2D([cx + col_w / 2, cx + col_w / 2],
                                  [y_top, y_bottom], color='black',
                                  linewidth=0.4, transform=fig.transFigure,
                                  zorder=2900))
        # label 竖排（顶部向下）
        _vtext(fig, cx, y_top - 0.002, lab, fontsize=fontsize,
               weight=label_weight, color='black', va='top')
        # value 竖排（label 下方，蓝色）
        _vtext(fig, cx, y_mid - 0.002, val, fontsize=fontsize,
               weight='normal', color=value_color, va='top')
    # label/value 分隔横线
    fig.add_artist(Line2D([x_left, x_right], [y_mid, y_mid], color='black',
                          linewidth=0.4, transform=fig.transFigure, zorder=2900))
    # 【2026-10-10 对齐样本】表外框：上/下横线 + 左右竖线（样本表1/表2 均为完整矩形框）
    fig.add_artist(Line2D([x_left, x_right], [y_top, y_top], color='black',
                          linewidth=0.5, transform=fig.transFigure, zorder=2900))
    fig.add_artist(Line2D([x_left, x_right], [y_bottom, y_bottom], color='black',
                          linewidth=0.5, transform=fig.transFigure, zorder=2900))
    fig.add_artist(Line2D([x_left, x_left], [y_top, y_bottom], color='black',
                          linewidth=0.5, transform=fig.transFigure, zorder=2900))
    fig.add_artist(Line2D([x_right, x_right], [y_top, y_bottom], color='black',
                          linewidth=0.5, transform=fig.transFigure, zorder=2900))
    return y_mid, y_bottom


def _ql_bhcs_table(fig, x_left, x_right, y_top, y_bottom, bh_rows, cs_rows,
                   bh_title='BOREHOLE RECORD', cs_title='CASING RECORD',
                   du='ft'):
    """BOREHOLE RECORD | CASING RECORD 并排 3 列表格（样本第 0 页第二段）。

    rows: [{size, from, to}, ...]（SIZE/FROM/TO 三列）
    du: 深度单位（'ft'/'m'）——SIZE 列统一追加 IN（英寸），FROM/TO 追加深度单位；
        值已自带单位（含字母）时不再重复追加。
    """
    from matplotlib.lines import Line2D
    import re
    _dep_unit = ' FT' if str(du).lower().startswith('ft') else ' M'

    def _u(v, unit):
        s = str(v).strip()
        if not s:
            return ''
        if re.search(r'[A-Za-z]', s):
            return s  # 已带单位（如 "26 IN"）
        return s + unit

    half = (x_right - x_left) / 2
    for _sec, (_x0, _x1, _title, _rows) in enumerate((
            (x_left, x_left + half, bh_title, bh_rows),
            (x_left + half, x_right, cs_title, cs_rows))):
        fig.text((_x0 + _x1) / 2, y_top - 0.004, _title, fontsize=8,
                 fontweight='bold', ha='center', va='top',
                 fontfamily='Microsoft YaHei', color='black')
        _th = y_top - 0.022  # 表头行
        _cw = (_x1 - _x0) / 3
        for _ci, _h in enumerate(('SIZE', 'FROM', 'TO')):
            fig.text(_x0 + (_ci + 0.5) * _cw, _th, _h, fontsize=6.5,
                     fontweight='bold', ha='center', va='center',
                     fontfamily='Microsoft YaHei', color='black')
            fig.add_artist(Line2D([_x0 + _ci * _cw, _x0 + _ci * _cw],
                                  [_th - 0.012, y_bottom], color='black',
                                  linewidth=0.4, transform=fig.transFigure,
                                  zorder=2900))
        _n_rows = max(len(_rows), 1)
        _rh = (y_bottom - _th) / (_n_rows + 1)
        for _ri, _r in enumerate(_rows):
            _ry = _th - (_ri + 1.5) * _rh
            _vals = [_u(_r.get('size', ''), ' IN'),
                     _u(_r.get('from', ''), _dep_unit),
                     _u(_r.get('to', ''), _dep_unit)]
            for _ci, _v in enumerate(_vals):
                fig.text(_x0 + (_ci + 0.5) * _cw, _ry, _v, fontsize=6.5,
                         ha='center', va='center',
                         fontfamily='Microsoft YaHei', color='black')
            fig.add_artist(Line2D([_x0, _x1], [_ry + _rh / 2, _ry + _rh / 2],
                                  color='black', linewidth=0.4,
                                  transform=fig.transFigure, zorder=2900))
        # 表格外框
        fig.add_artist(Line2D([_x0, _x1], [_th - 0.012, _th - 0.012],
                              color='black', linewidth=0.5,
                              transform=fig.transFigure, zorder=2900))
        fig.add_artist(Line2D([_x1, _x1], [_th - 0.012, y_bottom],
                              color='black', linewidth=0.5,
                              transform=fig.transFigure, zorder=2900))


def _ql_rotated_header(rows1, rows2, well_name, title_text, scale_text,
                       company_logo, contractor_logo, bh_rows=None,
                       cs_rows=None, disclaimer='', legend_title='',
                       legend_items=None, header_w_in=22.0, header_h_in=12.0,
                       fig_cfg=None):
    """【2026-10-10 整表右转90°】quick look 页首整体表（样本 BET-1 版式）。

    用户定案："开头是个右转90度的表，可以先把它放正，绘制完表之后再右转90度"。
    实现：独立画布上绘制一张"放正的横向页首表"（行从上到下：
    图标行 → 井名大字 → 图名 Well Logging Interpretation Result Plot →
    比例尺 → 表1 井位 15 字段 → 表2 测量 12 字段 → BOREHOLE/CASING →
    免责声明 → LEGEND 色块），渲染后用 PIL 顺时针旋转 90°（字头朝右）。

    旋转前表尺寸：宽 = 页首区高（header_h_in）、高 = 页首区宽（header_w_in），
    旋转后宽=页首区宽、高=页首区高，正好铺满页首区。

    返回: PIL Image（RGBA），已顺时针旋转 90°。
    """
    import textwrap as _tw
    from PIL import Image as _PIL
    _dpi = int((fig_cfg or {}).get('dpi') or 150)
    _W = max(header_h_in, 4.0)     # 旋转前表宽（=页首区高）
    _H = max(header_w_in, 8.0)     # 旋转前表高（=页首区宽）
    _fig = plt.figure(figsize=(_W, _H), dpi=_dpi)
    _fig.patch.set_facecolor('white')
    _ax = _fig.add_axes([0, 0, 1, 1])
    _ax.set_xlim(0, _W); _ax.set_ylim(0, _H)
    _ax.axis('off')
    for _sp in _ax.spines.values():
        _sp.set_visible(False)

    _bh = bh_rows or []
    _cs = cs_rows or []
    _lg = legend_items or []
    # 【2026-10-12 样本对齐（BET-1 第1页取证）】放正表行结构（用户 2026-10-12 定案）：
    #   行0 图标（company左/contractor右，行高2×，单列无竖线）| 行1 井名大字（2×）|
    #   行2 图名+比例尺分2行（2×，单列无竖线）| 行3-5 Company/Field/Well
    #   Coordinate（各 2 列）| 行6-17 24 字段对每行 2 对（4 列 label|value|label|value）|
    #   免责声明 | LEGEND。整表外框加粗、每行之间行线分隔（1-3 行无列内竖线）。
    #   BOREHOLE/CASING 不进第一页（用户定案拆第二页正放表）。
    _rot_cfg = ((fig_cfg or {}).get('rot') or {}).get('header') or {}
    _top_n = int(_rot_cfg.get('top_2col') or 3)   # 前 N 个字段独立成 2 列行
    _top3 = list(rows1[:_top_n])                  # 行3-5：Company/Field/Well Coordinate（各 2 列 1 行）
    # 【2026-10-12 修复】样本配对铁证（_sp_r0.png OCR）：放正行 = [表1字段|值|表2字段|值]
    #   即 Date Spudded↔Bit Size、Date TD Reached↔Type of Fluid in Hole、Date Logged↔Fluid Density…
    #   表1 余 12 字段与表2 全 12 字段一一 zip 配对成 12 行（每行 2 对 4 列）。
    _pair_rows = [list(pp) for pp in zip(rows1[_top_n:], rows2)]
    _disc_rows = 4 if disclaimer else 0           # 免责声明占 4 行（样本 4 行文字）；为空不占位
    _lg_title_rows = 1 if legend_title else 0
    _n_lg_rows = max(1, (len(_lg) + 5) // 6) if legend_title else 0
    _nrows = (1 + 1 + 1 + len(_top3) + len(_pair_rows)
              + _disc_rows + _lg_title_rows + _n_lg_rows)
    # 【2026-10-12 修复】1-3 行（图标/井名/图名比例尺）行高 = 普通行的 2 倍，
    #   等效总行数 = 3*2 + (nrows-3)，反推普通行高使各行高总和恰好 = _H。
    #   （旧实现 _rh=_H/nrows 使 _heights 总和高出表高 3*_rh，
    #     底部免责声明/LEGEND 行溢出表底外框，旋转后即超出表右端）
    _rh = _H / (3 * 2 + (_nrows - 3))
    # 【2026-10-12 用户定案】1-3 行（图标/井名/图名比例尺）行高 = 普通行的 2 倍
    _rh0 = _rh * 2.0

    _heights = [_rh0, _rh0, _rh0] + [_rh] * (_nrows - 3)  # 行高列表（行0-2 加高 2×）

    def _row_top(i):  # 第 i 行（0起）的上边界 y（y 向上）
        return _H - sum(_heights[:i])

    def _row_y(i):  # 第 i 行中心 y
        return _row_top(i) - _heights[i] / 2.0

    def _row_bot(i):  # 第 i 行下边界 y
        return _row_top(i) - _heights[i]

    # 外框加粗（覆盖整表 0.._H，含行0 图标行）
    # 【2026-10-13 用户要求】外框与表2 一致加粗：add_axes[0,0,1,1] 时画在
    #   画布边缘的线被裁半（实测 2px），内收半线宽保证 2.0pt=4px 完整可见
    _frame_lw = 2.0
    _line_lw = 0.5
    # 内收量 = 半线宽（本 ax 数据单位=英寸，1 单位=1in；2pt/72/2=0.0139 单位）
    _fx = _frame_lw / 72.0 / 2.0
    _fy = _frame_lw / 72.0 / 2.0
    _ax.plot([_fx, _W - _fx], [_H - _fy, _H - _fy], color='black', lw=_frame_lw)
    _ax.plot([_fx, _W - _fx], [_fy, _fy], color='black', lw=_frame_lw)
    _ax.plot([_fx, _fx], [_fy, _H - _fy], color='black', lw=_frame_lw)
    _ax.plot([_W - _fx, _W - _fx], [_fy, _H - _fy], color='black', lw=_frame_lw)
    # 行线：每行之间（图标行/井名行/图名行/2列行/4列行/免责/LEGEND 均分隔）
    # 【2026-10-12 修复】行间线加粗 lw=1.0：旋转后即列间竖线，用户口径"1-3行没有竖表格线"= 原 0.5 太细不可见
    _row_lw = 1.0
    for _i in range(1, _nrows):
        _ax.plot([0, _W], [_row_top(_i), _row_top(_i)], color='black', lw=_row_lw)

    _ri = 0  # 当前行号

    # ---- 行0：图标行（company 左 / contractor 右，统一内容高度）----
    _ico_y = _row_y(0)
    # 【2026-10-10 修复】旋转表内图标统一按"图标行高"驱动：
    # 旧实现沿用整图版 logo_content_frac/logo_width_max_frac，company 横条 logo
    # （内容比3.1）被全局宽度上限压扁导致高度小于 contractor（0.43 vs 0.56 in）。
    # 现统一内容高度 = 行高*0.72，宽度按内容比例自然伸展（上限放宽到半表宽，
    # 实际远不会触及），保证两图标视觉高度一致。
    _logo_in = float((fig_cfg or {}).get('logo_inner_frac') or 0.01) * _W
    _logo_items = []
    for _side, _fname, _override in (('left', 'company.png', company_logo),
                                     ('right', 'contractor.png', contractor_logo)):
        _logo_p = Path(_override) if _override else None
        if _logo_p is None or not _logo_p.exists():
            _src_dir = os.path.dirname(os.path.abspath(__file__))
            _cand = Path(_src_dir) / _fname
            _logo_p = _cand if _cand.exists() else (Path(SYMBOL_DIR) / _fname)
        if not _logo_p.exists():
            logger.warning("旋转表图标不存在, 跳过: %s", _logo_p)
            continue
        try:
            _pil = _PIL.open(str(_logo_p)).convert('RGBA')
            _pa = np.asarray(_pil)
            _alpha = _pa[:, :, 3].astype(int)
            _rgb = _pa[:, :, :3].astype(int)
            _cont = (_alpha > 10) | (np.any(_rgb < 245, axis=2))
            _ys, _xs = np.where(_cont)
            if len(_ys):
                _cw = _xs.max() - _xs.min() + 1
                _ch = _ys.max() - _ys.min() + 1
            else:
                _cw, _ch = _pil.width, _pil.height
            _ratio = _cw / max(_ch, 1)
            # 图标高度取行高的 62%（0.55 偏小，图标不清晰且加剧"空行"感）
            _logo_h = _rh0 * 0.62                  # 统一内容高度（图标行行高驱动，扩大第一行后容下图标）
            _logo_w = _logo_h * _ratio
            _logo_items.append([_side, _logo_p, _pil, _logo_w, _logo_h])
        except Exception as _le:
            logger.warning('旋转表图标失败: %s', _le)
    # 【2026-10-10 修复】两图标高度统一后，宽者还需收敛（用户口径"宽度不能相差太大"）：
    # 样本中 company(CNG)/contractor(CNLC) 均为近方块、宽度接近；
    # 本实现 company 横条 logo（比3.1）自然宽度约为 contractor 方块（比1.67）的 1.87 倍，
    # 故按"宽者 ≤ 1.4× 窄者"动态压宽（轻微压扁、不截断，保持两图标视觉平衡）。
    if _logo_items:
        _min_w = min(_i[3] for _i in _logo_items)
        _cap_w = max(_min_w * 1.4, 0.3)
        _frame_pad = 0.06                     # 【2026-10-10 修复】图标外框边距（in）
        for _side, _logo_p, _pil, _logo_w, _logo_h in _logo_items:
            if _logo_w > _cap_w:
                _logo_w = _cap_w
            # 【2026-10-12 修复】图标收拢至表中部（样本：company 转正 x≈18-35%、contractor x≈60-75%）；
            #   原实现 company 最左/contractor 最右，旋转后同列内相距 15in，用户"第一行只有一列/看不到 CNLC"
            # 【2026-10-14 二十轮定案】两图标距离拉大（用户：第一个图标前留一个空格
            #   左对齐、第二个图标后留一个空格右对齐）——推翻 0.30/0.70 收拢定案，
            #   改为贴边放置，边距 = 32pt 字号一个空格宽（≈0.13in）
            _pad_sp = 32.0 / 72.0 * 0.30
            if _side == 'left':
                _cx = _pad_sp + _logo_w / 2
            else:
                _cx = _W - _pad_sp - _logo_w / 2
            _x0 = _cx - _logo_w / 2
            _lax = _fig.add_axes([_x0 / _W, (_ico_y - _logo_h / 2) / _H,
                                  _logo_w / _W, _logo_h / _H], zorder=6000)
            # 【2026-10-12 修复】图标清晰度：LANCZOS 预放大 2× + lanczos 插值渲染，
            #   解决 company.png（233×75）放大后发糊问题。
            _up = _pil.resize((_pil.width * 2, _pil.height * 2), _PIL.LANCZOS)
            _lax.imshow(_up, aspect='auto', interpolation='lanczos')
            _lax.axis('off')
            for _sp in _lax.spines.values():
                _sp.set_visible(False)
            # 【2026-10-12 修复】图标不加外框（用户定案：图标自带实线边，不需要表格式外框）
            logger.debug("旋转表图标 %s (%.3fx%.3f in): %s", _side, _logo_w, _logo_h, _logo_p.name)
        # 【2026-10-12 用户定案】第1-3行单列、无列内竖线（图标行不再画 0.5W 竖线）
    _ri += 1

    # ---- 行1：井名（大字居中，单列无竖线）/ 行2：图名+比例尺分2行（单列无竖线）----
    # 【2026-10-12 用户定案】2-3 行（井名/图名/比例尺）加粗、字号 = 其他行 2 倍
    #   （字段 16 号 → 2×16 = 32 号）；字体微软雅黑。
    # 【2026-10-14 十八轮定案】表1-3 字体整体加大加粗（与表格适配、全图一致）：
    #   井名/图名/比例尺 28→32，字段行 14→16，正文行 12→14，BH/CS 节 7→9、
    #   单元格 6→8（均加粗），免责 4.2→5.5（小字保持常规字重），图例项 5→6.5
    _fs_well = 32.0
    _fs_title = 32.0
    _fs_scale = 32.0
    _ax.text(_W / 2, _row_y(1), str(well_name), ha='center', va='center',
             fontsize=_fs_well, fontweight='bold', color='black',
             fontfamily='Microsoft YaHei')
    # 【2026-10-12 用户定案】图名与比例尺分2行：图名上行、比例尺下行（同一表格行内）
    # 【2026-10-12 修复】行距 0.5rh 时两行文字分居行2上下端、中间空 1rh
    #   （用户"第一页多了个空行"）→ 收拢为 0.35rh，中间空隙约 0.37in
    _ax.text(_W / 2, _row_top(2) - _rh * 0.35, str(title_text),
             ha='center', va='center', fontsize=_fs_title, fontweight='bold',
             color='black', fontfamily='Microsoft YaHei')
    _ax.text(_W / 2, _row_bot(2) + _rh * 0.35, str(scale_text),
             ha='center', va='center', fontsize=_fs_scale, fontweight='bold',
             color='black', fontfamily='Microsoft YaHei')
    _ri += 2   # 行1 井名、行2 图名+比例尺

    # ---- 行3-5：top 2 列字段（label | value，竖线分隔）----
    # 【2026-10-12 用户定案】4-6 行（Company/Field/Well Coordinate 2 列）的唯一竖线
    #   与后面 4 列行（7-18 行）的第一条竖线对齐（0.22W，10-12 再前移腾出右侧空间）
    _x_sep2 = 0.22 * _W
    # 【2026-10-12 用户定案】字段（Company/Field/Well Coordinate 2 列行）微软雅黑 14 号字
    _fs_top = 16.0
    _vcolor = '#0033CC'
    for _k, (_lab, _val) in enumerate(_top3):
        _yc = _row_y(3 + _k)
        _ax.text(0.06, _yc, str(_lab), ha='left', va='center',
                 fontsize=_fs_top, fontweight='bold', color='black',
                 fontfamily='Microsoft YaHei')
        # 【2026-10-12 用户定案】Well Coordinate 保持同一列、内容分 2 行：
        #   第 1 行 经纬度（Lat./Long.）、第 2 行 XY 坐标（X:/Y:），不加行不拆列。
        _disp = str(_val)
        if str(_lab) == 'Well Coordinate':
            _sp = _ql_split_coord_val(_val)
            if _sp:
                _lat_l, _xy_l = _sp
                _disp = '  '.join(_lat_l) + '\n' + '  '.join(_xy_l)
        _ax.text(_x_sep2 + 0.06, _yc, _disp, ha='left', va='center',
                 fontsize=_fs_top, fontweight='bold', color=_vcolor,
                 fontfamily='Microsoft YaHei')
        _ax.plot([_x_sep2, _x_sep2], [_row_bot(3 + _k), _row_top(3 + _k)],
                 color='black', lw=_line_lw)
    _ri += len(_top3)

    # ---- 行6-17：字段对 4 列（label|value|label|value，每行 2 对）----
    # 【2026-10-12 用户定案】4-17 行内容微软雅黑 12 号字；
    #   10-12 第一根（0.22W）与第三根（0.65W）前移，为右侧 value 列腾出空间
    # 【2026-10-14 用户定案】表2 与表1 同宽：表1 标签列 [0, 0.22W]、值列
    #   [0.22W, 0.5W]；表2 标签列 [0.5W, 0.72W]、值列 [0.72W, 1.0W]，
    #   四列对称 0.22/0.28/0.22/0.28（原 0.66W 分隔使表2 标签列仅 0.16W、
    #   值列 0.34W，与表1 不一致）
    _fs_body = 14.0
    _x4 = [0.22 * _W, 0.5 * _W, 0.72 * _W]
    for _k, (_p1, _p2) in enumerate(_pair_rows):
        _yc = _row_y(6 + _k)
        _cells = [(_p1[0], 0.06), (_p1[1], _x4[0] + 0.06),
                  (_p2[0], _x4[1] + 0.06), (_p2[1], _x4[2] + 0.06)]
        for _j, (_txt, _xx) in enumerate(_cells):
            _ax.text(_xx, _yc, str(_txt), ha='left', va='center',
                     fontsize=_fs_body, fontweight='bold',
                     color=_vcolor if _j % 2 else 'black',
                     fontfamily='Microsoft YaHei')
        for _xx in _x4:
            _ax.plot([_xx, _xx], [_row_bot(6 + _k), _row_top(6 + _k)],
                     color='black', lw=_line_lw)
    _ri += len(_pair_rows)

    # ---- BOREHOLE RECORD / CASING RECORD（标题 + 列头 SIZE|FROM|TO + 数据行）----
    # 【2026-10-10 修复】第一页右转表不再包含 BH/CS（移至第二页正放表）；两者皆空时整段跳过
    if _bh or _cs:
        _fs_sec = max(9, _rh * 0.28)
        _fs_cell = max(8, _rh * 0.24)
        _bhx = [0.06, 0.34 * _W, 0.62 * _W, 0.82 * _W]
        for _title, _rec in (('BOREHOLE RECORD', _bh), ('CASING RECORD', _cs)):
            _y_top = _row_top(_ri)
            _n = 1 + 1 + len(_rec)
            _y_bot = _row_bot(_ri + _n - 1)
            _ax.text(_W / 2, _row_y(_ri), _title, ha='center', va='center',
                     fontsize=_fs_sec, fontweight='bold', color='black',
                     fontfamily='Microsoft YaHei')
            for _cc in (1, 2, 3):
                _ax.plot([_bhx[_cc], _bhx[_cc]], [_y_bot, _y_top],
                         color='black', lw=0.6)
            _hdr_y = _row_y(_ri + 1)
            for _j, _hd in enumerate(('SIZE', 'FROM', 'TO')):
                _ax.text(_bhx[_j + 1] + 0.04, _hdr_y, _hd, ha='left', va='center',
                         fontsize=_fs_cell, fontweight='bold', color='black',
                         fontfamily='Microsoft YaHei')
            for _k, _r in enumerate(_rec):
                _yc = _row_y(_ri + 2 + _k)
                _vals = [_r.get('size', ''), _r.get('from', ''), _r.get('to', '')]
                for _j, _v in enumerate(_vals):
                    _ax.text(_bhx[_j + 1] + 0.04, _yc, str(_v), ha='left',
                             va='center', fontsize=_fs_cell, fontweight='bold',
                             color='black', fontfamily='Microsoft YaHei')
                if _k < len(_rec) - 1:
                    _ax.plot([0, _W], [_row_top(_ri + 2 + _k), _row_top(_ri + 2 + _k)],
                             color='black', lw=0.4)
            _ri += _n

    # ---- 免责声明（小字横排，按行宽自动断行）----
    if disclaimer:
        _fs_disc = max(5.5, _rh * 0.19)
        _chars = max(60, int(_W / ( _fs_disc / 72.0 * 0.55)))
        _lines = _tw.wrap(str(disclaimer), width=_chars)
        if not _lines:
            _lines = [str(disclaimer)]
        for _ll in _lines[:4]:
            _ax.text(_W / 2, _row_y(_ri), _ll, ha='center',
                     va='center', fontsize=_fs_disc, color='black',
                     fontfamily='Microsoft YaHei')
            _ri += 1
        if len(_lines) > 4:
            _ri += len(_lines) - 4  # 多出的行按行高占位（保持表结构）
    # 免责声明为空：不占用任何行（页1 末尾不再出现空行）

    # ---- LEGEND（标题 + 色块行，每行 6 个）----
    if legend_title:
        _fs_lg = max(9, _rh * 0.28)
        _ax.text(_W / 2, _row_y(_ri), legend_title, ha='center',
                 va='center', fontsize=_fs_lg, fontweight='bold', color='black',
                 fontfamily='Microsoft YaHei')
        _ri += 1
        _n_lg_rows = max(1, (len(_lg) + 5) // 6)
        _fs_lgi = max(6.5, _rh * 0.20)
        _sq = min(_rh * 0.5, 0.14)
        for _lr in range(_n_lg_rows):
            _yc = _row_y(_ri)
            _row_items = _lg[_lr * 6:(_lr + 1) * 6]
            _n_it = len(_row_items)
            _slot = _W / max(_n_it, 1)
            for _ii, _it in enumerate(_row_items):
                _lab = str(_it[0]); _col = _it[1]
                _col2 = _it[2] if len(_it) > 2 else None
                _cx = _slot * (_ii + 0.5)
                # 【2026-10-14 用户定案】图例色块加纹理全覆盖（不能只取颜色）
                if _col2 is None:
                    _ax.add_patch(plt.Rectangle((_cx - _sq / 2, _yc - _sq / 2),
                                                _sq, _sq, facecolor=_col,
                                                hatch='///',
                                                edgecolor='black', lw=0.3))
                else:
                    # 双色块并列（与页3 LEGEND 一致）
                    _ax.add_patch(plt.Rectangle((_cx - _sq, _yc - _sq / 2),
                                                _sq, _sq, facecolor=_col,
                                                hatch='///',
                                                edgecolor='black', lw=0.3))
                    _ax.add_patch(plt.Rectangle((_cx, _yc - _sq / 2),
                                                _sq, _sq, facecolor=_col2,
                                                hatch='///',
                                                edgecolor='black', lw=0.3))
                _ax.text(_cx + _sq / 2 + 0.03, _yc, _lab, ha='left',
                         va='center', fontsize=_fs_lgi, fontweight='bold',
                         color='black', fontfamily='Microsoft YaHei')
            _ri += 1
    else:
        _ri += 1

    # 渲染 → PIL → 顺时针旋转 90°
    _fig.canvas.draw()
    _buf = np.asarray(_fig.canvas.buffer_rgba())
    _pil = _PIL.fromarray(_buf).convert('RGBA')
    plt.close(_fig)
    return _pil.rotate(-90, expand=True)


def _save_ql_bhcs_page(well_name, bh_rows, cs_rows, out_dir, timestamp,
                       fig_cfg=None, disclaimer='', tbl_w_in=None, du=None):
    """【2026-10-12 重构】quick look 第二页：BH/CS 正放表（样本 BET-1 结构）。

    用户定案（2026-10-12）：第二个表格为正放表——
      顶部第 1 行 免责声明（横排小字，跨全宽；样本 4 行英文原文）
      第 2 行 2 列：BOREHOLE RECORD（钻头记录）| CASING RECORD（套管记录）
      第 3 行 6 列：SIZE | FROM | TO | SIZE | FROM | TO
      第 4-7 行 实际数据（无数据留白，表结构不变，不编造）
    表格外框加粗（lw=2.0），BOREHOLE|CASING 组分隔线加粗，其余列线/行线 lw=1.0。
    【2026-10-12】tbl_w_in：表宽英寸数（默认 10.5），调用方传页1 转置表宽
      （_hdr_w_in）实现"页2 正放表与页1 转置表宽度一致"（用户定案）。

    返回: 保存的 PNG 绝对路径；无数据时返回 None。
    """
    import textwrap as _tw
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _bh = bh_rows or []
    _cs = cs_rows or []
    if not _bh and not _cs:
        return None
    # 【2026-10-21 用户修正】BH/CS 深度单位跟随检测单位（RP-13 masterlog 明标
    #   "MD(meter)"、GTO 套管设计 Depth(m)，故应为米；此前硬编码 FT 与源/深度轴不符。
    #   du=None 时按全局 DEPTH_UNIT 解析（'auto'→_detect_depth_unit 恒返回 'm'）。
    if du is None:
        du = DEPTH_UNIT
    if str(du).lower() == 'auto':
        du = _detect_depth_unit(0, 1)
    _dep_unit = ' FT' if str(du).lower().startswith('ft') else ' M'
    _dpi = int((fig_cfg or {}).get('dpi') or 150)
    _disc = str(disclaimer or '').strip()
    # 【2026-10-12 修复】免责声明分 3 行（用户定案：可以分成 3 行）；
    # 之前按表宽/字符宽估算 wrap 成 2 行，每行 214 字符贴满表宽，
    # 字符宽系数 0.52 偏小 → 实际文字横向溢出外框被截断。
    _disc_n = 3 if _disc else 0
    _data_n = max(len(_bh), len(_cs), 4)  # 数据行固定 4 行（表结构不变）
    _tbl_n = 2 + _data_n                 # 标题 + 表头 + 数据
    _nrows = _disc_n + _tbl_n
    # 【2026-10-12 修复】表宽与页1 转置表一致（用户：页2 表太小放不下免责声明）
    _tbl_w = float(tbl_w_in or 10.5)
    # 【2026-10-13 用户定案】页2 表体满幅 = 页1/页3 宽：fig 宽直接取表宽
    #   （不再 +1in 边距），表体从 0 到 _fig_w，输出像素宽 = 页1/页3 完全一致，
    #   纵向拼接无需缩放、无质量损失。
    _fig_w = _tbl_w
    _row_h = 0.66
    _fig_h = 0.7 + _nrows * _row_h
    _fig = plt.figure(figsize=(_fig_w, _fig_h), dpi=_dpi)
    _fig.patch.set_facecolor('white')
    # 【2026-10-14 用户反馈】表2 与表1 同宽：axes x 改满幅（0~1），
    # 表体（数据坐标 0~_fig_w）直达页缘，输出像素 0~3600 与页1/页3 一致；
    # y 保持 0.03~0.97 不变（纵向居中布局为 2026-10-12 定案，不动）。
    _ax = _fig.add_axes([0.0, 0.03, 1.0, 0.94])
    _ax.set_xlim(0, _fig_w); _ax.set_ylim(0, _fig_h)
    _ax.axis('off')

    _x0, _x1 = 0.0, _fig_w
    _cw = (_x1 - _x0) / 6.0
    # 【2026-10-12 用户定案】钻头套管记录表上下左右居中：外框顶/底边距均衡。
    #   免责文字中心下移至 _fig_h-0.50，外框顶 _fig_h-0.12：
    #   外框顶在免责文字上方留足空白（约 0.38in），确保"免责声明在表格内"
    #   视觉明确，且第 1 行文字不再压外框顶线。
    _ytop = _fig_h - 0.55
    # 免责声明并入 BH/CS 正放表：整个表（免责行组 + BH/CS）加粗外框，
    # 免责声明为表内第 1 行组（横排小字跨全宽，组内不画行线）。
    _tbl_top = _fig_h - 0.12

    # ---- 表内第 1 行组：免责声明（横排小字，跨全宽，3 行）----
    if _disc:
        # 【2026-10-13 用户定案】免责声明分 3 行；字号 14 优先，放不下自动递减。
        # 【2026-10-14 二十轮定案】1/2 行基本填满表宽、剩余进第 3 行：
        #   按文本自身平均字符宽估每行容量（此前 0.66em 保守估导致换行过早、
        #   1/2 行右侧留白大），逐行估宽校验防溢出（沿用 2026-10-12 防截断
        #   定案），估宽超限缩 _cap 重排；行数超限交外层递减字号。
        def _est_disc_w(_s, _fs):
            _u = 0.0
            for _c in _s:
                if _c == ' ':
                    _u += 0.30
                elif _c.isupper() or _c.isdigit():
                    _u += 0.68
                elif _c.isalpha():
                    _u += 0.52
                else:
                    _u += 0.40
            return _u * _fs / 72.0

        _fs_d = 14.0
        _lines = []
        _wch = _fs_d / 72.0 * 0.66
        for _fs in (14.0, 13.0, 12.0, 11.0, 10.5, 10.0, 9.5, 9.0):
            _wch = _fs / 72.0 * 0.66
            _avail = (_x1 - _x0) - 3.0 * _wch      # 减左缩进2空格 + 右余量≈1空格
            _cap = max(40, int(len(_disc) * _avail /
                               max(_est_disc_w(_disc, _fs), 1e-6)))
            for _try in range(14):
                _lines = _tw.wrap(_disc, width=_cap) or [_disc]
                if len(_lines) > _disc_n:
                    break                           # 行数超限 → 外层缩字号
                if any(_est_disc_w(_l, _fs) > _avail for _l in _lines):
                    _cap -= 2                       # 估宽超限 → 缩容重排
                    continue
                break
            if len(_lines) <= _disc_n:
                _fs_d = _fs
                break
        _lines = _lines[:_disc_n]
        _xpad = 2 * _wch                            # 左侧缩进 2 个空格宽
        for _li, _ll in enumerate(_lines):
            _ax.text(_x0 + _xpad, _ytop - _li * _row_h, _ll,
                     ha='left', va='center', fontsize=_fs_d,
                     color='black', fontfamily='Microsoft YaHei')

    # ---- BH/CS 表（全部行以 _tbl_top 为基准，修 0.38in 错位：文字不再压线/越框）----
    _hdr_top = _tbl_top - _disc_n * _row_h       # 第2行（BOREHOLE|CASING 标题行）顶
    # 第 2 行：BOREHOLE RECORD | CASING RECORD（2 列，各跨 3 列）
    # 【2026-10-14 十八轮定案】表2 字体加大加粗：标题 12→14、列头 10→12、
    #   数据 10→12（加粗），与表1 字号层级协调
    _fs_hdr = 14
    _ax.text(_x0 + _cw * 1.5, _hdr_top - _row_h / 2, 'BOREHOLE RECORD',
             ha='center', va='center', fontsize=_fs_hdr, fontweight='bold',
             color='black', fontfamily='Microsoft YaHei')
    _ax.text(_x0 + _cw * 4.5, _hdr_top - _row_h / 2, 'CASING RECORD',
             ha='center', va='center', fontsize=_fs_hdr, fontweight='bold',
             color='black', fontfamily='Microsoft YaHei')

    _col_top = _hdr_top - _row_h                  # 第3行（6 列表头）顶
    # 第 3 行：SIZE | FROM | TO | SIZE | FROM | TO（6 列表头）
    _fs_col = 12
    for _j in range(6):
        _hd = ('SIZE', 'FROM', 'TO')[_j % 3]
        _ax.text(_x0 + _cw * (_j + 0.5), _col_top - _row_h / 2, _hd,
                 ha='center', va='center', fontsize=_fs_col, fontweight='bold',
                 color='black', fontfamily='Microsoft YaHei')

    # 第 4-7 行：实际数据（BH 左 3 列 / CS 右 3 列，无数据留白）
    # 【2026-10-21 用户修正】SIZE 单位 IN、FROM/TO 单位跟随检测深度单位
    #   （_dep_unit：米制 ' M' / 英制 ' FT'）；无数据留白（表结构不变，不编造）。
    def _qcell(_v, _unit):
        _vs = str(_v or '').strip()
        return f'{_vs} {_unit}' if _vs else ''
    _fs_cell = 12
    for _i in range(_data_n):
        _b = _bh[_i] if _i < len(_bh) else {}
        _c = _cs[_i] if _i < len(_cs) else {}
        _vals = ([_qcell(_b.get('size', ''), 'IN'),
                  _qcell(_b.get('from', ''), _dep_unit),
                  _qcell(_b.get('to', ''), _dep_unit)] +
                 [_qcell(_c.get('size', ''), 'IN'),
                  _qcell(_c.get('from', ''), _dep_unit),
                  _qcell(_c.get('to', ''), _dep_unit)])
        _row_top_i = _col_top - (_i + 1) * _row_h
        for _j, _v in enumerate(_vals):
            _ax.text(_x0 + _cw * (_j + 0.5), _row_top_i - _row_h / 2, _v,
                     ha='center', va='center', fontsize=_fs_cell,
                     fontweight='bold', color='black',
                     fontfamily='Microsoft YaHei')

    _tbl_bot = _col_top - (_data_n + 1) * _row_h

    # ---- 表线：外框加粗、行列线细、BOREHOLE|CASING 组分隔线加粗 ----
    _frame_lw = 2.0
    _line_lw = 1.0
    _hdr_top = _tbl_top - _disc_n * _row_h    # 第2行（BOREHOLE|CASING 标题行）顶
    _col_top = _hdr_top - _row_h              # 第3行（6 列表头）顶
    _ax.plot([_x0, _x1], [_tbl_top, _tbl_top], color='black', lw=_frame_lw)
    _ax.plot([_x0, _x1], [_tbl_bot, _tbl_bot], color='black', lw=_frame_lw)
    # 竖向边框线内收半线宽（数据单位=英寸）：axes 满幅后画在 0/_fig_w 的线
    # 会被画布边缘裁掉一半（三轮定案同款处理），内收后可见线宽仍为完整 4px
    _fx = _frame_lw / 72.0 / 2.0
    _ax.plot([_fx, _fx], [_tbl_bot, _tbl_top], color='black', lw=_frame_lw)
    _ax.plot([_fig_w - _fx, _fig_w - _fx], [_tbl_bot, _tbl_top],
             color='black', lw=_frame_lw)
    # 【2026-10-12 用户定案】第2行（BOREHOLE RECORD | CASING RECORD）只有 2 列：
    #   仅组分隔线（x = 3 列宽）延伸到标题行，6 列表头的其余竖线从第3行（列头）才开始。
    _xx_sep = _x0 + 3 * _cw
    _ax.plot([_xx_sep, _xx_sep], [_hdr_top, _col_top],
             color='black', lw=_frame_lw)
    for _j in range(1, 6):
        _xx = _x0 + _j * _cw
        _lw = _frame_lw if _j == 3 else _line_lw   # 第 3 列/第 4 列间 = 组分隔线
        _ax.plot([_xx, _xx], [_col_top, _tbl_bot], color='black', lw=_lw)
    # 行线：免责行组内不画线，免责组底/标题底/列头底/数据行间各 1 条（3-7 行行线不变）
    for _r in range(1, _nrows):
        if _disc_n and _r < _disc_n:
            continue                    # 免责声明行组内不画行线
        _yy = _tbl_top - _r * _row_h
        _ax.plot([_x0, _x1], [_yy, _yy], color='black', lw=_line_lw)

    # 【2026-10-20 用户定案】不落 PNG：savefig → BytesIO → PIL Image（内存）
    import io as _io
    _buf = _io.BytesIO()
    _fig.savefig(_buf, format='png', dpi=_dpi, metadata={'Software': None})
    plt.close(_fig)
    _buf.seek(0)
    from PIL import Image as _PILB
    _PILB.MAX_IMAGE_PIXELS = None
    _img = _PILB.open(_buf).convert('RGB')
    _buf.close()
    logger.debug('quick look 第二页 BH/CS 正放表已渲染(内存): %dx%d',
                 _img.width, _img.height)
    return _img


def _ql_find_symbol(label, sym_dir=None):
    """在 SYMBOL_DIR 中按标签匹配图例图标文件（PNG/JPG/BMP）。

    【2026-10-12 用户定案】页3 图例"问题太多，只进行文字识别，
    图例图标到 symbol 目录里去取，没有就空着，但文字必须在"。
    匹配规则（宽松、按名称近似）：
      ① 精确映射表（Gas/Oil/Water/Poor Oil/Tight/Possible Hydrocarbon 等
         指向确定文件名，避免 'oil' 误匹配 'oil shale'）；
      ② 规范化后文件名包含标签（或标签包含文件名）；
      ③ 匹配不到返回 None（图例位置留空，文字仍渲染）。

    返回: 匹配到的图标文件 Path；无则 None。
    """
    import unicodedata, re
    _d = Path(sym_dir or SYMBOL_DIR)
    if not _d.is_dir():
        return None
    _key = unicodedata.normalize('NFKC', str(label).lower())
    _key = re.sub(r'[^a-z0-9]', '', _key)

    _map = {
        # 【2026-10-13】油气水结论图标固化至 symbol/fluid_conclusions（英文名），
        # 优先取新图；找不到回退旧文件
        'gas': ['fluid_conclusions/gas.png', 'GAS.png', 'gas.jpg', 'Gas.1.png', 'Gas.png'],
        'poorgas': ['fluid_conclusions/poor_gas.png'],
        'gaswater': ['fluid_conclusions/gas_water.png', 'gas_water.jpg', 'gasy water.jpg', 'Gas&Water.png'],
        'gasbearingwater': ['fluid_conclusions/gas_bearing_water.png'],
        'oil': ['fluid_conclusions/oil.png', 'OIL.png', 'oil.bmp'],
        'pooroil': ['fluid_conclusions/poor_oil.png', 'poor oil.png', 'poor oil0.png'],
        'oilwater': ['fluid_conclusions/oil_water.png', 'OiL_Water.png', 'Oil&Water.png'],
        'oilbearingwater': ['fluid_conclusions/oil_bearing_water.png'],
        'gasoil': ['fluid_conclusions/gas_oil.png'],
        'water': ['fluid_conclusions/water.png', 'water.png', 'water (2).png', 'water.jpg', 'Water.1.png'],
        'tight': ['fluid_conclusions/tight.png', 'Tight.png', 'tight.jpg', 'Tight_2.png'],
        'possiblehydrocarbon': ['possible-oil.bmp', 'poss gas.jpg',
                                'Probable oil.png', 'probable-oil.bmp'],
        'probableoil': ['fluid_conclusions/probable_oil.png', 'probable-oil.bmp'],
        'possibleoil': ['fluid_conclusions/possible_oil.png', 'possible-oil.bmp'],
        'probablegas': ['fluid_conclusions/probable_gas.png'],
        'possiblegas': ['fluid_conclusions/possible_gas.png', 'poss gas.jpg'],
        # logInt 输出的大写下划线形式（GAS_POSSIBLE / OIL_POSSIBLE / GAS_PROBABLE / OIL_PROBABLE）
        'gaspossible': ['fluid_conclusions/possible_gas.png', 'poss gas.jpg'],
        'oilpossible': ['fluid_conclusions/possible_oil.png', 'possible-oil.bmp'],
        'gasprobable': ['fluid_conclusions/probable_gas.png'],
        'oilprobable': ['fluid_conclusions/probable_oil.png', 'probable-oil.bmp'],
        'dry': ['fluid_conclusions/tight.png', 'tight.jpg'],
    }
    for _f in _map.get(_key, []):
        _p = _d / _f
        if _p.is_file():
            return _p

    # 模糊匹配：文件名规范化后互相包含（精确映射未命中时）
    for _p in sorted(_d.iterdir()):
        if _p.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.bmp'):
            continue
        _n = unicodedata.normalize('NFKC', _p.stem.lower())
        _n = re.sub(r'[^a-z0-9]', '', _n)
        if _key and (_key in _n or _n in _key):
            return _p
    return None


def _render_ql_legend_pil(legend_title, items, w_in=24.0, h_in=2.6,
                          fig_cfg=None):
    """【2026-10-12 新增】quick look 第三个表格：LEGEND 正放表。

    用户定案（2026-10-12）：第三个表格正放、第一行大写标题
    LEGEND OF WELL-LOGGING RESULT、第二行起排列测井解释图例，
    其下才是正式的测井解释图。
    【2026-10-12 用户定案】图例图标从 symbol 目录取（_ql_find_symbol），
    取不到留空（槽位空白），但文字必须渲染；放弃逐像素复刻色块样式。

    返回: PIL Image（RGBA，放正不旋转）。
    """
    from PIL import Image as _PIL
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    _dpi = int((fig_cfg or {}).get('dpi') or 150)
    _W, _H = max(w_in, 4.0), max(h_in, 1.2)
    _fig = plt.figure(figsize=(_W, _H), dpi=_dpi)
    _fig.patch.set_facecolor('white')
    _ax = _fig.add_axes([0, 0, 1, 1])
    _ax.set_xlim(0, 1); _ax.set_ylim(0, 1)
    _ax.axis('off')
    for _sp in _ax.spines.values():
        _sp.set_visible(False)

    _items = list(items or [])
    _title = str(legend_title or 'LEGEND OF WELL-LOGGING RESULT')
    # 行结构：标题 1 行 + 图例 3 行（样本 4 列 × 3 行 12 项）
    _cols = 4
    _rows = max(1, (len(_items) + _cols - 1) // _cols)
    _rh = 1.0 / (1 + _rows)

    # 外框加粗 + 标题分隔线
    # 【2026-10-13 用户要求】外框与表2 一致（lw=2.0=4px 完整可见）：画布边缘
    #   线被裁半（实测 2px），内收半线宽修复
    _flw = 2.0
    _fx = _flw / 72.0 / _W / 2
    _fy = _flw / 72.0 / _H / 2
    _ax.plot([_fx, 1 - _fx], [1 - _fy, 1 - _fy], color='black', lw=_flw)
    _ax.plot([_fx, 1 - _fx], [_fy, _fy], color='black', lw=_flw)
    _ax.plot([_fx, _fx], [_fy, 1 - _fy], color='black', lw=_flw)
    _ax.plot([1 - _fx, 1 - _fx], [_fy, 1 - _fy], color='black', lw=_flw)
    _ax.plot([_fx, 1 - _fx], [1 - _rh, 1 - _rh], color='black', lw=1.0)

    # 标题（大写居中）
    # 【2026-10-13 用户要求】字号与表2 协调：标题 12 bold、图例文字 10
    # 【2026-10-14 十八轮定案】表3 字体加大加粗：标题 12→14、图例文字 10→12（加粗）
    _ax.text(0.5, 1 - _rh / 2, _title, ha='center', va='center',
             fontsize=14, fontweight='bold', color='black',
             fontfamily='Microsoft YaHei')

    # 图例项（3 行 × 4 列：图标槽位 + 标签，图标与文字各自严格对齐）
    # 【2026-10-12 用户定案】① 图标上下左右对齐：每列图标固定居中于列中心
    #   （不再按"组宽"居中——组居中导致每项文字宽不同 → 图标水平漂移）；
    #   ② 文字左缘固定 = 列中心 + 槽位半宽 + 间隙；
    #   ③ 图标与文字之间留一点空白（间隙加大）；
    #   ④ 垂直方向：图标 contain 于统一 0.22in 槽位、槽位中心=行中心 → 上下对齐。
    _sq_in = 0.22                       # 图标槽位边长（英寸）
    _sq_h = _sq_in / _H                 # figure 相对高
    _sq_w = _sq_in / _W                 # figure 相对宽
    _lbl_fs = 12.0
    _gap = 0.012                        # 图标与文字间隙（figure 坐标，~0.22in）
    for _r in range(_rows):
        _yc = 1.0 - _rh * (_r + 1.5)
        _row_items = _items[_r * _cols:(_r + 1) * _cols]
        for _c, _it in enumerate(_row_items):
            _lab = str(_it[0])
            _cx = 0.125 + _c * 0.25           # 列中心
            _icon_p = _ql_find_symbol(_lab)
            # 固定布局：图标居中于列中心，文字左缘固定在图标右侧 + 间隙
            _sq_left = _cx - _sq_w / 2.0
            _lbl_left = _cx + _sq_w / 2.0 + _gap
            if _icon_p is not None:
                # 图标贴入槽位（保持纵横比、contain 居中、不加外框）
                try:
                    _ic = _PIL.open(str(_icon_p)).convert('RGBA')
                except Exception:
                    _ic = None
                if _ic is not None:
                    _iw, _ih = _ic.size
                    # zoom：目标显示 = 槽位 0.22in 见方（屏幕 px = in×dpi）
                    _zoom = min(_sq_in * _dpi / max(_iw, 1),
                                _sq_in * _dpi / max(_ih, 1))
                    _oi = OffsetImage(_ic, zoom=_zoom)
                    _ab = AnnotationBbox(
                        _oi, (_cx, _yc), frameon=False)
                    _ax.add_artist(_ab)
            _ax.text(_lbl_left, _yc, _lab, ha='left', va='center',
                     fontsize=_lbl_fs, fontweight='bold', color='black',
                     fontfamily='Microsoft YaHei')

    _fig.canvas.draw()
    _buf = np.asarray(_fig.canvas.buffer_rgba())
    _pil = _PIL.fromarray(_buf)
    plt.close(_fig)
    return _pil


def _combine_ql_legend_main(legend_pil, main_img, header_h_in,
                            dpi=150, blk_y0=None, blk_y1=None):
    """【2026-10-12 新增】页3 拼接：LEGEND 正放表 + 正图主体。

    【2026-10-20 用户定案】全程内存：main_img 为 PIL Image（不再读/写
    PNG 文件），返回 (拼接后 PIL Image, 道头区块 PIL Image 或 None)。

    主图顶部页首区（原右转表区 + 图名区，高 header_h_in 英寸）为留白，
    按页首区高度裁掉后在其上方粘贴 LEGEND 正放表。

    blk_y0/blk_y1（figure 坐标 0..1，正图道头区顶/底）：非空时另裁道头
    区块 Image（1-8 道曲线名/刻度/图例整块），供 _assemble_ql_full 复制
    到图尾作 footer，方便阅读长图底部。
    """
    from PIL import Image as _PIL
    _PIL.MAX_IMAGE_PIXELS = None
    _main = main_img.convert('RGB') if isinstance(main_img, _PIL.Image) \
        else _PIL.open(str(main_img)).convert('RGB')
    _W, _H = _main.size
    _top_px = int(float(header_h_in or 0) * float(dpi or 150))   # 页首区像素高
    _top_px = max(0, min(_top_px, _H - 4))
    _body = _main.crop((0, _top_px, _W, _H))     # 正图主体（图头区+曲线区+图例区）
    _canvas = _PIL.new('RGB', (_W, legend_pil.height + _body.height),
                       'white')
    # 【2026-10-12 修复】LEGEND 表宽与页2/页1 表宽一致（可能小于正图宽）→ 水平居中
    _lx = max(0, (_W - legend_pil.width) // 2)
    _canvas.paste(legend_pil.convert('RGB'), (_lx, 0))
    _canvas.paste(_body, (0, legend_pil.height))
    logger.debug('quick look 第三页 = LEGEND 正放表 + 正图已拼接(内存): '
                 '%dx%d (裁掉页首区 %d px)', _canvas.width, _canvas.height,
                 _top_px)
    # ---- 道头区块（footer 用）----
    _hdr_blk = None
    try:
        if blk_y0 is not None and blk_y1 is not None:
            _y0 = max(0, int(round((1.0 - float(blk_y1)) * _H)) - _top_px)
            _y1 = max(_y0 + 4, int(round((1.0 - float(blk_y0)) * _H)) - _top_px)
            _hdr_blk = _body.crop((0, _y0, _W, _y1))
            logger.debug('道头区块已裁出(footer 用, 内存): %dx%d',
                         _hdr_blk.width, _hdr_blk.height)
    except Exception as _be:
        logger.warning('道头区块裁剪失败(跳过 footer): %s', _be)
        _hdr_blk = None
    return _canvas, _hdr_blk


def _append_header_footer(png_path, blk_y0, blk_y1):
    """【2026-10-14 用户定案】综合图尾部追加与 header 一致的 footer（道头区块）。

    从 PNG 顶部裁出 blk_y0..blk_y1（figure 坐标，道头区：曲线名/刻度/图例
    整块），粘贴到整图最下方，并补 4px 底部外框粗线，就地写回。
    返回 footer 高度(px)，失败返回 0。
    """
    try:
        from PIL import Image as _PIL
        from PIL import ImageDraw as _ID
        _PIL.MAX_IMAGE_PIXELS = None
        _im = _PIL.open(str(png_path)).convert('RGB')
        _W, _H = _im.size
        _y0 = max(0, int(round((1.0 - float(blk_y1)) * _H)))
        _y1 = max(_y0 + 4, int(round((1.0 - float(blk_y0)) * _H)))
        _blk = _im.crop((0, _y0, _W, _y1))
        _canvas = _PIL.new('RGB', (_W, _H + _blk.height), 'white')
        _canvas.paste(_im, (0, 0))
        _canvas.paste(_blk, (0, _H))
        # 底部补 4px 外框粗线（footer 底缘是分隔细线，与页框口径一致）
        # 【2026-10-15 用户反馈】底框线 x 端点必须对齐图外框左右侧线——
        # 此前 [0, _W-1] 横贯整页宽，两端超出外框侧线"出头"。
        # 外框侧线 = footer 区块内贯穿全高的连续深色竖线（最左/最右者），
        # 用列深色占比≥0.9 检出；检测失败回退全宽。
        _xl, _xr = 0, _W - 1
        try:
            _arr_b = np.asarray(_blk.convert('RGB'))
            _dkb = (_arr_b < 100).all(axis=2)
            _line_cols = np.where(_dkb.mean(axis=0) >= 0.9)[0]
            if len(_line_cols) >= 2:
                _xl, _xr = int(_line_cols[0]), int(_line_cols[-1])
        except Exception:
            pass
        _ID.Draw(_canvas).rectangle([_xl, _canvas.height - 4, _xr,
                                     _canvas.height - 1], fill=(0, 0, 0))
        _canvas.save(str(png_path))
        logger.debug('综合图 footer(道头区块)已追加: %s (+%d px)',
                    png_path, _blk.height)
        return _blk.height
    except Exception as _fe:
        logger.warning('综合图 footer 追加失败(跳过): %s', _fe)
        return 0


def _save_single_page_pdf(png_path, pdf_path, dpi=150):
    """【2026-10-13】PNG → 单页 PDF（页面尺寸 = px/dpi*72pt 物理尺寸）。

    快速解释整图与综合图共用。PDF 页面单边上限 14400pt(200in,
    Acrobat 限制)，超限整页等比缩放。
    返回 PDF 绝对路径；失败返回 None（保留 PNG）。
    """
    try:
        import fitz
        from PIL import Image as _PIL2
        # 本地自产超大图（综合图可超 2.8 亿像素）需解除 PIL 解压炸弹保护上限
        _PIL2.MAX_IMAGE_PIXELS = None
        _src = str(png_path)
        _tmp_img = None
        _im = _PIL2.open(_src)
        _w, _h = _im.size
        try:
            # MuPDF 单图解码上限约 2^28≈2.68 亿像素（"Overly large image"），
            # 超限时按面积比轻微降采样（页面物理尺寸不变，仅嵌入图像降 DPI）
            if _w * _h > 250_000_000:
                _f = (250_000_000.0 / (_w * _h)) ** 0.5
                _nw, _nh = max(1, int(_w * _f)), max(1, int(_h * _f))
                _tmp_img = str(Path(png_path).with_name(
                    Path(png_path).stem + '_pdfsrc.png'))
                _im.convert('RGB').resize((_nw, _nh),
                                          getattr(_PIL2, 'LANCZOS', 1)).save(_tmp_img)
                logger.debug('图像超 MuPDF 像素上限，入 PDF 前降采样: %dx%d -> %dx%d',
                            _w, _h, _nw, _nh)
                _src = _tmp_img
        finally:
            _im.close()
        _dpi_eff = float(dpi or 150)
        _w_pt = _w * 72.0 / _dpi_eff
        _h_pt = _h * 72.0 / _dpi_eff
        _scale = min(1.0, 14400.0 / max(_w_pt, _h_pt))
        _w_pt *= _scale
        _h_pt *= _scale
        _doc = fitz.open()
        _page = _doc.new_page(width=_w_pt, height=_h_pt)
        _page.insert_image(fitz.Rect(0, 0, _w_pt, _h_pt), filename=_src)
        _doc.save(str(pdf_path), deflate=True)
        _doc.close()
        if _tmp_img:
            try:
                os.remove(_tmp_img)
            except Exception:
                pass
        logger.debug('单页 PDF 已生成: %s (%.1fx%.1f in%s)',
                    Path(pdf_path).absolute(), _w_pt / 72, _h_pt / 72,
                    ', 页面超限已缩放' if _scale < 1.0 else '')
        return str(Path(pdf_path).absolute())
    except Exception as _e:
        logger.warning('单页 PDF 输出失败(保留 PNG): %s', _e)
        return None


def _save_single_page_pdf_from_image(im, pdf_path, dpi=150):
    """【2026-10-20】PIL Image → 单页 PDF（内存，不落中间 PNG）。

    页面尺寸 = im 尺寸 px/dpi*72pt；单边超 14400pt(200in, Acrobat 限制)
    整页等比缩放；超 MuPDF 单图解码上限（≈2.68 亿像素）时按面积比轻微
    降采样后以 PNG 字节流嵌入（页面物理尺寸不变）。失败返回 None。
    """
    try:
        import io as _io
        import fitz
        from PIL import Image as _PIL2
        _PIL2.MAX_IMAGE_PIXELS = None
        _im = im.convert('RGB') if isinstance(im, _PIL2.Image) \
            else _PIL2.open(str(im)).convert('RGB')
        _w, _h = _im.size
        _src = _im
        _tmp = None
        try:
            if _w * _h > 250_000_000:
                _f = (250_000_000.0 / (_w * _h)) ** 0.5
                _nw, _nh = max(1, int(_w * _f)), max(1, int(_h * _f))
                _tmp = _im.resize((_nw, _nh), getattr(_PIL2, 'LANCZOS', 1))
                logger.debug('图像超 MuPDF 像素上限，入 PDF 前降采样(内存): '
                             '%dx%d -> %dx%d', _w, _h, _nw, _nh)
                _src = _tmp
            _buf = _io.BytesIO()
            _src.save(_buf, format='PNG')
            _png_bytes = _buf.getvalue()
            _buf.close()
        finally:
            if _tmp is not None:
                _tmp.close()
            _im.close()
        _dpi_eff = float(dpi or 150)
        _w_pt = _w * 72.0 / _dpi_eff
        _h_pt = _h * 72.0 / _dpi_eff
        _scale = min(1.0, 14400.0 / max(_w_pt, _h_pt))
        _w_pt *= _scale
        _h_pt *= _scale
        _doc = fitz.open()
        _page = _doc.new_page(width=_w_pt, height=_h_pt)
        _page.insert_image(fitz.Rect(0, 0, _w_pt, _h_pt), stream=_png_bytes)
        _doc.save(str(pdf_path), deflate=True)
        _doc.close()
        logger.debug('单页 PDF 已生成(内存直出): %s (%.1fx%.1f in)',
                     Path(str(pdf_path)).absolute(), _w_pt / 72, _h_pt / 72)
        return str(Path(str(pdf_path)).absolute())
    except Exception as _e:
        logger.warning('内存直出单页 PDF 失败: %s', _e)
        return None


def _assemble_ql_full(well_name, p1_path, p2_path, p3_path, out_dir,
                      timestamp, dpi=150, footer_path=None, pdf_out_dir=None):
    """【2026-10-13 用户定案】quick look 完整一张图（对齐样本格式）。

    样本 BET-1 PDF 为"一张连续图"：页1 右转信息表 → 页2 免责+BH/CS 表 →
    LEGEND → 正图，纵向顺序排列、宽度一致、无分页感。

    将三张 PNG（页1/页2/页3=LEGEND+正图）统一宽度后纵向拼接为一张长图，
    输出 {well}_quicklook_full_{ts}.png，并用 PyMuPDF 输出单页
    {well}_quicklook_{ts}.pdf（页面尺寸=长图物理尺寸 px/dpi*72pt，
    一页连续、不分页）。

    【2026-10-14 用户定案】footer_path：正图道头区块 PNG（1-8 道曲线名/
    刻度/图例），拼接在长图最后作为 footer，方便阅读长图底部（样本惯例：
    长图中重复 header 条）。
    【2026-10-14 只出一次 PDF】pdf_out_dir：最终 PDF 存放目录（输出目录）；
    out_dir 仅存中间长图 PNG（临时目录），出 PDF 后即弃。

    Returns:
        (full_png, pdf_path) 绝对路径；失败返回 (None, None)。
    """
    from PIL import Image as _PIL
    _PIL.MAX_IMAGE_PIXELS = None
    # 【2026-10-20 用户定案】长图不再落盘：页1/页2/页3/footer 均可为
    # PIL Image 或路径；拼接结果仅在内存，直接产单页 PDF。
    # out_dir 仅为旧签名兼容保留（quicklook 内存流程传 None）。
    _out = Path(out_dir) if out_dir else Path('.')
    _pdf = Path(pdf_out_dir) if pdf_out_dir else _out
    _pdf = _pdf / f'{well_name}_quicklook_{timestamp}.pdf'

    def _ql_to_img(_x):
        if _x is None:
            return None
        if isinstance(_x, _PIL.Image):
            return _x.convert('RGB')
        if not Path(_x).exists():
            return None
        return _PIL.open(str(_x)).convert('RGB')

    try:
        # 【2026-10-23 R21-4】缺页不再整体放弃：p1（页1 右转表）、p2（页2
        # BH/CS 表）为**可选页**——_save_ql_bhcs_page 在无钻头/套管数据时正常
        # 返回 None（设计如此），旧逻辑因此让这类井 quicklook 完全出不了 PDF
        # （只剩 PNG）。现在缺可选页即跳过该页继续拼接，只有**正图主体 p3**
        # 缺失才放弃（有 p1/p2 时行为与旧版完全一致）。
        _imgs = []
        _p3 = None
        for _idx, _p in enumerate((p1_path, p2_path, p3_path)):
            _im = _ql_to_img(_p)
            if _im is None:
                logger.warning('整图拼接缺页, 跳过: %s', _p)
                continue
            if _idx == 2:
                _p3 = _im
            else:
                _imgs.append(_im)
        if _p3 is None:
            logger.warning('整图拼接缺正图主体, 放弃 PDF')
            return None, None
        # 统一宽度 = 页3（LEGEND+正图）宽度；页1/页2 等比缩放对齐
        _w3 = _p3.width
        _aligned = []
        for _im in _imgs:
            if _im.width != _w3:
                _h = max(1, round(_im.height * _w3 / _im.width))
                _im = _im.resize((_w3, _h), _PIL.LANCZOS)
            _aligned.append(_im)
        _aligned.append(_p3)
        # 【2026-10-14】footer = 正图道头区块，拼接到长图最后（内存 Image 或路径）
        _ft_img = _ql_to_img(footer_path) if footer_path is not None else None
        if _ft_img is not None:
            try:
                if _ft_img.width != _w3:
                    _h = max(1, round(_ft_img.height * _w3 / _ft_img.width))
                    _ft_img = _ft_img.resize((_w3, _h), _PIL.LANCZOS)
                _aligned.append(_ft_img)
                logger.debug('footer 道头区块已加入长图末尾(内存)')
            except Exception as _fe:
                logger.warning('footer 拼接失败(跳过): %s', _fe)
        _full_h = sum(_im.height for _im in _aligned)
        _canvas = _PIL.new('RGB', (_w3, _full_h), 'white')
        _yy = 0
        for _im in _aligned:
            _canvas.paste(_im, (0, _yy))
            _yy += _im.height
        # 【2026-10-14 用户反馈】长图最底部补 4px 外框粗线（footer 拼接后
        # 底缘是道头/曲线区分隔细线，缺与页1/页3 一致的外框粗线）；
        # 端点 x 对齐正图侧框线（footer 道头区块内实测左右边框位置），
        # 避免底框线两端超出侧框"出头"。
        try:
            from PIL import ImageDraw as _ID
            _xl, _xr = 0, _w3 - 1
            try:
                _ft_h = _aligned[-1].height
                _arr_f = np.asarray(_canvas.crop(
                    (0, max(0, _full_h - _ft_h), _w3, _full_h)).convert('RGB'))
                _dk = (_arr_f < 100).all(axis=2)
                _cs = np.where(_dk.any(axis=0))[0]
                if len(_cs):
                    _xl, _xr = int(_cs[0]), int(_cs[-1])
            except Exception:
                pass
            _ID.Draw(_canvas).rectangle([_xl, _full_h - 4, _xr, _full_h - 1],
                                        fill=(0, 0, 0))
        except Exception as _de:
            logger.warning('长图底部外框线绘制失败(跳过): %s', _de)
        # 【2026-10-20 用户定案】长图不落 PNG：内存画布直接产单页 PDF
        # 【2026-10-13】页面尺寸 = 长图物理尺寸: px/dpi*72pt（此前把像素
        # 当点数导致页面 50x333in、打印比例全错）。默认 150dpi 与出图一致。
        _pdf = _save_single_page_pdf_from_image(_canvas, _pdf, dpi=dpi)
        return None, _pdf
    except Exception as _e:
        logger.warning('整图拼接失败: %s', _e)
        return None, None


def _ql_norm_coord(s):
    """坐标文本规范化：全角→半角、压缩空白（保留 ° ' " 度分秒符号）。

    样本 BET-1 LAS 的 LOC 行含中文全角冒号（"TOP X：341,597.00 m"），
    lasio 按 cp1252 解码会把 UTF-8 全角字符读成 mojibake（ï¼š=：、ï¼Œ=，），
    直接绘制会显示为乱码/方框；统一还原后清洗为半角。
    """
    import re
    s = str(s or '')
    # UTF-8 → cp1252 mojibake 还原（全角标点常见映射）
    s = s.replace('ï¼š', ': ').replace('ï¼Œ', ', ').replace('ï¼ˆ', '(') \
         .replace('ï¼‰', ')').replace('ã€‚', '. ')
    s = s.replace('：', ': ').replace('，', ', ').replace('　', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _ql_extract_xy(s):
    """从 LOC 文本提取 X/Y 坐标对（米制），找不到返回 []。

    样本 Well Coordinate 显示 4 行：Lat./Long. + X/Y；
    LOC 值如 "TOP X：341,597.00 m Y：9,886,901.00 m BOTTOM X Y"
    只保留 X/Y 两行，丢弃多余描述。
    """
    import re
    s = str(s or '').replace('ï¼š', ':').replace('ï¼Œ', ',')
    s = s.replace('：', ':').replace('，', ',')
    out = []
    x = re.search(r'X\s*[:=]\s*([\d,]+\.?\d*)', s)
    y = re.search(r'Y\s*[:=]\s*([\d,]+\.?\d*)', s)
    if x:
        out.append('X: ' + x.group(1) + ' m')
    if y:
        out.append('Y: ' + y.group(1) + ' m')
    return out


def _ql_split_coord_val(v):
    """Well Coordinate 值分 2 列：经纬度列（Lat./Long.）+ XY 列（X:/Y:）。

    【2026-10-12 用户定案】页1 井位坐标经纬度和 XY 坐标分开、分 2 列排列、适当拉开距离。
    返回 (left_lines, right_lines)；不匹配时返回 None（调用方保持单列原样）。
    """
    lines = [ln for ln in str(v).split('\n') if ln.strip()]
    lat = [ln for ln in lines if ln.lower().startswith(('lat', 'long'))]
    xy = [ln for ln in lines if ln.lower().startswith(('x:', 'y:'))]
    if lat and xy:
        return lat, xy
    return None


def _fmt_mud_density(v):
    """泥浆密度智能单位【2026-10-14 二三轮用户定案】。

    值已带单位（非纯数字）→ 原值为主不拼接；纯数字：≤3 补 g/cc、
    >7 补 ppg，3<x≤7 无常见单位区间留原数字。
    """
    _s = str(v or '').strip()
    if not _s:
        return ''
    try:
        _n = float(_s)
    except (ValueError, TypeError):
        return _s
    if _n <= 3:
        return f"{_s}g/cc"
    if _n > 7:
        return f"{_s}ppg"
    return _s


def _fmt_fluid_loss(v):
    """失水统一单位 L【2026-10-14 二四轮用户定案】。

    纯数字补大写 L（升, 大写以与数字 1 区分）；已带单位原值为主,
    仅结尾孤立小写 l（前邻数字/小数点/空格, 非 ml 等组合单位）归一为大写 L。
    """
    _s = str(v or '').strip()
    if not _s:
        return ''
    try:
        float(_s)
        return f"{_s}L"
    except (ValueError, TypeError):
        pass
    if (_s.endswith('l') and len(_s) >= 2
            and (_s[-2].isdigit() or _s[-2] in '. ')):
        return _s[:-1] + 'L'
    return _s


def _last_mud_type(v):
    """Type of Fluid in Hole 取值精简【2026-10-21 用户定案】。

    取泥浆程序串最后一段的泥浆类型：泥浆程序形如
    'Bentonite(10.5-235.00m) / Polymer(235-1523m) / KCl-HIP(1523-3062m) / KCl-HIP(3062-3735m)'，
    取末段 'Kind(..)' 的 Kind；非泥浆程序串（已是单一类型如 'Polymer'/'WATER BASED MUD'）
    原值返回。RP-13 实际末段为 KCl-HIP。"""
    s = str(v or '').strip()
    if not s:
        return s
    segs = [x.strip() for x in s.split('/') if x.strip()]
    if not segs:
        return s
    last = segs[-1]
    kind = last.split('(')[0].strip()
    return kind or last


def _ql_cfg_value(spec, well_info, param_info, du):
    """从 quick look 图版（qlpt.json header.fields_v）字段定义解析取值。

    spec 支持两种形态：
      - 字符串 "well:company" / "param:bit_size" / "special:logged_interval"
      - dict {label, src(well|param|special|join), key, keys?, sep?,
              fmt(float2), prefix, suffix, default}
    返回: str（取不到返回 ''）
    """
    if isinstance(spec, str):
        if ':' in spec:
            _src, _key = spec.split(':', 1)
            spec = {'src': _src, 'key': _key}
        else:
            spec = {'src': 'well', 'key': spec}
    if not isinstance(spec, dict):
        return ''
    src = spec.get('src', 'well')
    key = spec.get('key', '')
    v = ''
    if src == 'special':
        if key == 'logged_interval':
            _s = well_info.get('start_depth', '')
            _t = well_info.get('stop_depth', '')
            if _s or _t:
                v = f"{_s}-{_t} {du}"
        elif key == 'well_coordinate':
            # 【2026-10-12 修复】样本 Well Coordinate 为多行：Lat./Long. + X/Y。
            #   LAS LOC 行含全角冒号与多余描述，规范化后按 X/Y 拆行；
            #   LAS LATI/LONG 段（well_info.latitude/longitude）存在时优先。
            #   【2026-10-14 井设置】UTM X/Y 优先取 well_info.x_coordinate/
            #   y_coordinate（<井名>info.json 坐标组可编辑字段），回退 LOC 解析。
            wc = well_info.get('well_coordinate') or ''
            _lat = str(well_info.get('latitude') or '').strip()
            _lon = str(well_info.get('longitude') or '').strip()
            _xc = str(well_info.get('x_coordinate') or '').strip()
            _yc = str(well_info.get('y_coordinate') or '').strip()
            _lines = []
            if _lat:
                _lines.append('Lat. : ' + _ql_norm_coord(_lat))
            if _lon:
                _lines.append('Long. : ' + _ql_norm_coord(_lon))
            if _xc or _yc:
                if _xc:
                    _lines.append('X: ' + _ql_norm_coord(_xc))
                if _yc:
                    _lines.append('Y: ' + _ql_norm_coord(_yc))
            else:
                _lines.extend(_ql_extract_xy(wc))
            if not _lines:
                _n = _ql_norm_coord(wc)
                if _n:
                    _lines.append(_n)
            v = '\n'.join(_lines)
        elif key == 'processed_by':
            v = well_info.get('processed_by', '')
        elif key == 'corrected_by':
            v = well_info.get('corrected_by', '')
    elif src == 'join':
        _parts = []
        for _k in (spec.get('keys') or []):
            _pv = _ql_cfg_value(_k, well_info, param_info, du)
            if _pv:
                _parts.append(_pv)
        v = spec.get('sep', ' / ').join(_parts)
    elif src == 'param':
        v = param_info.get(key, '')
    else:
        v = well_info.get(key, '')
    if v is None or v == '':
        return spec.get('default', '')
    if spec.get('fmt') == 'float2':
        try:
            v = f"{float(v):.2f}"
        except (ValueError, TypeError):
            pass
    if spec.get('fmt') == 'mud_density':
        # 【2026-10-14 二三轮】泥浆密度智能单位（≤3→g/cc、>7→ppg、带单位原值为主）
        v = _fmt_mud_density(v)
    if spec.get('fmt') == 'fluid_loss':
        # 【2026-10-14 二四轮】失水统一单位 L（纯数字补 L、孤立小写 l 归一）
        v = _fmt_fluid_loss(v)
    if spec.get('prefix'):
        v = spec['prefix'] + str(v)
    if spec.get('suffix'):
        v = str(v) + spec['suffix']
    return str(v)


def _ql_header_rows_from_cfg(_tpl, quicklook_config, well_info, param_info, du):
    """从 quick look 图版（qlpt.json header.fields_v）解析页首两组竖排表。

    返回: (rows1, rows2)；图版未配 fields_v 时回退 None（由调用方用硬编码默认）。
    """
    _hdr = (quicklook_config or {}).get('header') or (_tpl or {}).get('header') or {}
    _fv = _hdr.get('fields_v')
    if not _fv or not isinstance(_fv, dict):
        return None, None
    _mk = lambda _list: [(_f.get('label', ''), _ql_cfg_value(_f, well_info, param_info, du))
                         for _f in (_list or [])]
    return _mk(_fv.get('table1')), _mk(_fv.get('table2'))


def _render_quicklook_header_page(well_info, param_info, results, well_name, output_dir,
                                  company_logo=None, contractor_logo=None,
                                  quicklook_config=None, _du='ft'):
    """两页式 quick look 第 1 页：横向信息表页（转 90 度排布的信息表）。

    页面从上到下依次为：
      1) 标题条：左上 company 图标 / 右上 contractor 图标 / 中央图名
      2) 井信息表（竖向两列 label:value，含 BOREHOLE RECORD / CASING RECORD 分组）
      3) 免责声明（DISCLAIMER，图版 header_page.disclaimer 可配）
      4) 图例（流体类别 12 类，每行 items_per_row 项）
      5) 页脚：出图时间/程序说明

    参照 BET-1_8.5IN_SLAM_Res_MD200_20261003.pdf 第一页版式；
    布局与文案全部读 templates/qlpt.json 的 header_page 段。
    返回保存的 PNG 绝对路径。
    """
    import datetime
    _tpl = load_plot_template('qlpt') or {}
    _fig_cfg = _tpl.get('figure') or {}
    _title_cfg = _tpl.get('title') or {}
    _hp = _tpl.get('header_page') or {}
    _lg = _tpl.get('legend') or {}
    _hdr = _tpl.get('header') or {}
    _font_cfg = _tpl.get('font') or {}

    _du_u = str(_du).upper()
    figwidth = float(_fig_cfg.get('figwidth_inch') or 24)
    dpi = int(_fig_cfg.get('dpi') or 150)
    page_h = float(_hp.get('height_inch') or 13.0)
    fig = plt.figure(figsize=(figwidth, page_h), dpi=dpi)
    fig.patch.set_facecolor('white')

    _family = _font_cfg.get('family') or 'Microsoft YaHei'

    # ---- 甲方固定信息（quicklook_config.header_fixed > 图版 header.fixed > 数据源） ----
    _qfix = {}
    if quicklook_config and isinstance(quicklook_config, dict):
        _qfix = quicklook_config.get('header_fixed') or {}
    if not _qfix:
        _qfix = _hdr.get('fixed') or {}
    _QL_EMPTY = {'', 'unknown', 'n/a', 'na', 'none', 'nan', '-', 'null', 'undefined'}
    for _k, _v in _qfix.items():
        if _v and str(well_info.get(_k, '')).strip().lower() in _QL_EMPTY:
            well_info[_k] = str(_v)

    # 【2026-10-14 用户定案】钻头/套管优先取 <井名>info.json（人工修改生效）
    _qbh = _wellinfo_rec_rows(well_info.get('borehole_record')) or \
        ((quicklook_config or {}).get('borehole_record') if quicklook_config else None)
    if not _qbh:
        _qbh = _hdr.get('borehole_record')
    _qcs = _wellinfo_rec_rows(well_info.get('casing_record')) or \
        ((quicklook_config or {}).get('casing_record') if quicklook_config else None)
    if not _qcs:
        _qcs = _hdr.get('casing_record')

    def _fmt_val(v):
        if v is None or str(v).strip() == '':
            return ''
        try:
            return f'{float(v):.2f}'
        except (ValueError, TypeError):
            return str(v)

    _bh_txt = ('; '.join(f"{r.get('size', '')}in {r.get('from', '')}-{r.get('to', '')}{_du_u}"
                         for r in _qbh) if _qbh else '')
    _cs_txt = ('; '.join(f"{r.get('size', '')}in {r.get('from', '')}-{r.get('to', '')}{_du_u}"
                         for r in _qcs) if _qcs else '')

    # ---- 组装信息表行（读图版 header.fields；__section__ 为分组标题行） ----
    _fields = _hdr.get('fields') or [
        ['Company', 'company'], ['Country', 'country'], ['Field', 'field_name'],
        ['Well Name', 'well_name'], ['Area', 'area'], ['Log Date', 'log_date'],
        ['Datum', 'permanent_datum'], ['TD', 'stop_depth'],
        ['BOREHOLE RECORD', '__section__'], ['Bit Size / Section', 'borehole_section'],
        ['Start Depth', 'start_depth'], ['Stop Depth', 'stop_depth'],
        ['Mud Type', 'drilling_fluid_type'], ['Mud Density', 'drilling_fluid_density'],
        ['Mud Viscosity', 'drilling_fluid_viscosity'], ['Mud Loss', 'drilling_fluid_loss'],
        ['CASING RECORD', '__section__'], ['Casing Size / Section', 'casing_section'],
        ['Casing Shoe', 'casing_shoe_depth'], ['Cement TOC', 'cement_top_depth'],
    ]
    _rows = []
    for _label, _key in _fields:
        if _key == '__section__':
            _rows.append((_label, None, True))
            continue
        if _key == 'borehole_section':
            _val = _bh_txt
        elif _key == 'casing_section':
            _val = _cs_txt
        elif _key in ('start_depth', 'stop_depth', 'casing_shoe_depth', 'cement_top_depth'):
            _raw = well_info.get(_key, '')
            _val = f"{_fmt_val(_raw)} {_du_u}" if _raw else ''
        elif _key in ('drilling_fluid_density', 'drilling_fluid_viscosity',
                      'drilling_fluid_loss', 'bit_size'):
            _val = _fmt_val(param_info.get(_key, ''))
        else:
            _val = str(well_info.get(_key, '') or param_info.get(_key, '') or '')
        _rows.append((_label, _val, False))

    # ---- 1. 标题条 ----
    _title_txt = _hp.get('title') or _title_cfg.get('template') or \
        '{well} Well Logging Interpretation Result Plot'
    try:
        _title_txt = _title_txt.format(
            well=well_name,
            start=well_info.get('start_depth', ''),
            stop=well_info.get('stop_depth', ''),
            unit=_du_u)
    except Exception:
        _title_txt = f'{well_name} Well Logging Interpretation Result Plot'

    _title_h_ratio = float(_hp.get('title_height_ratio') or 0.10)
    _title_bottom = 1.0 - _title_h_ratio
    fig.text(0.5, _title_bottom + _title_h_ratio * 0.42, _title_txt,
             fontsize=int(_hp.get('title_fontsize') or _title_cfg.get('fontsize') or 16),
             fontweight=_title_cfg.get('fontweight') or 'bold',
             color=_title_cfg.get('color') or '#000000',
             ha='center', va='center', fontfamily=_family)
    _draw_logo_pair(fig, company_logo, contractor_logo,
                    logo_cx=_title_bottom + _title_h_ratio * 0.5,
                    logo_h_ratio=0.68,
                    title_zone_top=1.0)

    # ---- 2. 信息表（竖向两列，label 左 value 右；section 行整宽） ----
    _table_x0 = float(_hp.get('table_x0') or 0.02)
    _table_x1 = float(_hp.get('table_x1') or 0.98)
    _table_top = float(_hp.get('table_top') or 0.90)
    _table_bottom = float(_hp.get('table_bottom') or 0.42)
    _n_rows = len(_rows)
    _rh = (_table_top - _table_bottom) / _n_rows if _n_rows else 0.02
    _row_fs = int(_hp.get('table_fontsize') or _hdr.get('table_fontsize') or 8)

    # 边框
    from matplotlib.lines import Line2D
    fig.add_artist(Line2D([_table_x0, _table_x1], [_table_top, _table_top],
                          color='black', linewidth=0.6, transform=fig.transFigure))
    fig.add_artist(Line2D([_table_x0, _table_x1], [_table_bottom, _table_bottom],
                          color='black', linewidth=0.6, transform=fig.transFigure))
    fig.add_artist(Line2D([_table_x0, _table_x0], [_table_top, _table_bottom],
                          color='black', linewidth=0.6, transform=fig.transFigure))
    fig.add_artist(Line2D([_table_x1, _table_x1], [_table_top, _table_bottom],
                          color='black', linewidth=0.6, transform=fig.transFigure))
    _label_w = float(_hp.get('label_width_ratio') or 0.24)
    fig.add_artist(Line2D([_table_x0 + (_table_x1 - _table_x0) * _label_w,
                           _table_x0 + (_table_x1 - _table_x0) * _label_w],
                          [_table_top, _table_bottom], color='black',
                          linewidth=0.4, transform=fig.transFigure))
    for _i, (_label, _val, _is_sec) in enumerate(_rows):
        _yc = _table_top - (_i + 0.5) * _rh
        if _is_sec:
            # 分组标题行：整宽浅灰底 + 粗体
            fig.add_artist(plt.Rectangle((_table_x0, _yc - _rh / 2),
                                         _table_x1 - _table_x0, _rh,
                                         transform=fig.transFigure,
                                         facecolor='#E8E8E8', edgecolor='black',
                                         linewidth=0.4, zorder=3000))
            fig.text((_table_x0 + _table_x1) / 2, _yc, _label,
                     fontsize=_row_fs + 1, fontweight='bold', ha='center',
                     va='center', fontfamily=_family, color='black', zorder=3001)
        else:
            fig.text(_table_x0 + 0.004, _yc, _label, fontsize=_row_fs,
                     ha='left', va='center', fontfamily=_family, color='black')
            fig.text(_table_x0 + (_table_x1 - _table_x0) * _label_w + 0.004,
                     _yc, str(_val), fontsize=_row_fs, ha='left', va='center',
                     fontfamily=_family, color='black')
        if _i < _n_rows - 1:
            fig.add_artist(Line2D([_table_x0, _table_x1], [_yc - _rh / 2, _yc - _rh / 2],
                                  color='#AAAAAA', linewidth=0.3,
                                  transform=fig.transFigure))

    # ---- 3. 免责声明 ----
    _disc = _hp.get('disclaimer') or (
        'DISCLAIMER: This Quick Look interpretation is generated automatically by '
        'computer-aided log interpretation software. Results are preliminary and for '
        'reference only. Final interpretation, reservoir evaluation and well testing '
        'recommendations must be reviewed and confirmed by qualified petrophysicists '
        'and geologists.'
    )
    _disc_top = float(_hp.get('disclaimer_top') or 0.40)
    _disc_bottom = float(_hp.get('disclaimer_bottom') or 0.335)
    _disc_fs = int(_hp.get('disclaimer_fontsize') or 7)
    fig.add_artist(plt.Rectangle((_table_x0, _disc_bottom),
                                 _table_x1 - _table_x0, _disc_top - _disc_bottom,
                                 transform=fig.transFigure,
                                 facecolor='#FAFAFA', edgecolor='#999999',
                                 linewidth=0.4, zorder=3000))
    fig.text((_table_x0 + _table_x1) / 2, (_disc_top + _disc_bottom) / 2,
             _disc, fontsize=_disc_fs, ha='center', va='center',
             fontfamily=_family, color='#444444', zorder=3001)

    # ---- 4. 图例（流体类别，每行 items_per_row 项） ----
    _lg_items = []
    if quicklook_config and quicklook_config.get('legend_items'):
        _lg_items = [(it['label'], it.get('color', '#bdbdbd'))
                     for it in quicklook_config['legend_items']]
    if not _lg_items:
        _lg_items = [(it['label'], it['color']) for it in _lg.get('items') or []]
    _lg_title = (quicklook_config or {}).get('legend_title') or _lg.get('title') or \
        'LEGEND OF WELL-LOGGING RESULT'
    _per_row = int(_lg.get('items_per_row') or 6)
    _lg_rows = max(1, (len(_lg_items) + _per_row - 1) // _per_row)
    _lg_top = float(_hp.get('legend_top') or 0.33)
    _lg_bottom = float(_hp.get('legend_bottom') or 0.09)
    _lg_h = _lg_top - _lg_bottom
    # 标题行
    fig.text((_table_x0 + _table_x1) / 2, _lg_top - _lg_h * 0.10,
             _lg_title + ':', fontsize=int(_hp.get('legend_title_fontsize') or 8),
             ha='center', va='center', fontweight='bold',
             fontfamily=_family, color='black')
    _row_h = (_lg_h * 0.78) / _lg_rows
    _sq = min(_row_h * 0.6, 0.018)
    for _r in range(_lg_rows):
        _items = _lg_items[_r * _per_row: (_r + 1) * _per_row]
        _yc = _lg_top - _lg_h * 0.20 - (_r + 0.5) * _row_h
        _n = len(_items)
        for _j, (_name, _color) in enumerate(_items):
            _cx = _table_x0 + (_table_x1 - _table_x0) * (0.5 - _n * 0.075 + _j * 0.15)
            fig.add_artist(plt.Rectangle((_cx, _yc - _sq / 2), _sq, _sq,
                                         transform=fig.transFigure,
                                         facecolor=_color, edgecolor='black',
                                         linewidth=0.4, zorder=3000))
            fig.text(_cx + _sq + 0.003, _yc, _name,
                     fontsize=int(_lg.get('item_fontsize') or 5),
                     ha='left', va='center', fontfamily=_family, color='black')

    # ---- 5. 页脚 ----
    _foot = f'Quick Look Interpretation  |  Generated: {datetime.datetime.now():%Y-%m-%d %H:%M}  |  logvis (logInt)'
    fig.text((_table_x0 + _table_x1) / 2, 0.035, _foot,
             fontsize=6, ha='center', va='center',
             fontfamily=_family, color='#666666')

    # ---- 保存 ----
    well_output_dir = Path(output_dir) if output_dir else (Path('output') / well_name)
    well_output_dir.mkdir(exist_ok=True, parents=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    _io = _tpl.get('io') or {}
    _fn = (_io.get('header_filename_template') or '{well}_quicklook_header_{timestamp}.png')
    try:
        _fn = _fn.format(well=well_name, timestamp=timestamp)
    except Exception:
        _fn = f'{well_name}_quicklook_header_{timestamp}.png'
    _out = well_output_dir / _fn
    fig.savefig(str(_out), dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    logger.info('quick look 图头页已保存: %s', _out)
    return str(_out)


def fill_gas_effect(ax, md, nphi, den,
                    nphi_range=(1.1, -0.1), den_range=(1.7, 2.9),
                    color='red', alpha=0.45, zorder=1):
    """密度-中子挖掘效应填充（独立方法模块，供其它程序 import 调用）。

    纯相对位置规则（2026-10-13 用户定案）：只填充"中子在右、密度在左"
    （归一化 x_nphi > x_den）深度段两曲线之间的中间部分；
    中子相对在左（x_nphi <= x_den）一律不填。

    参数：
        ax: 目标 matplotlib Axes，其 x 轴刻度须与 nphi_range/den_range
            一致（中子为倒序刻度，密度为正序刻度）
        md: 深度数组（fill_betweenx 的 y，与 nphi/den 等长）
        nphi: 中子曲线值（NPHI/CNL/CNCF 等含氢指数）
        den: 密度曲线值（RHOB/DEN，g/cc）
        nphi_range: (左刻度, 右刻度)，中子倒序惯例 (1.1, -0.1)
        den_range: (左刻度, 右刻度)，密度正序惯例 (1.7, 2.9)
        color / alpha / zorder: 填充样式

    返回：
        实际填充的深度点数（int）
    """
    _md_s = pd.Series(md)
    _n_s = pd.Series(nphi)
    _d_s = pd.Series(den)
    if len({len(_md_s), len(_n_s), len(_d_s)}) != 1:
        logger.warning('fill_gas_effect: md/nphi/den 长度不一致 (%s/%s/%s)，按最短截取',
                       len(_md_s), len(_n_s), len(_d_s))
    _len = min(len(_md_s), len(_n_s), len(_d_s))
    _md = pd.to_numeric(_md_s.iloc[:_len], errors='coerce').reset_index(drop=True)
    _nv = pd.to_numeric(_n_s.iloc[:_len], errors='coerce').reset_index(drop=True)
    _dv = pd.to_numeric(_d_s.iloc[:_len], errors='coerce').reset_index(drop=True)

    # 归一化 x 位置（与 _plot_curve 的 set_xlim 线性映射一致）：
    # x = (v - 左刻度) / (右刻度 - 左刻度)；倒序刻度（右<左）分母为负是合法映射。
    # 防零保护用 abs：不能用 max(span, 1e-9)，否则倒序范围分母被钳成 1e-9 致填充全失。
    _n_lo, _n_hi = float(nphi_range[0]), float(nphi_range[1])
    _d_lo, _d_hi = float(den_range[0]), float(den_range[1])
    _span_n = _n_hi - _n_lo
    _span_d = _d_hi - _d_lo
    if abs(_span_n) > 1e-9:
        _x_n = (_nv - _n_lo) / _span_n
    else:
        _x_n = pd.Series(0.5, index=_nv.index)
    if abs(_span_d) > 1e-9:
        _x_d = (_dv - _d_lo) / _span_d
    else:
        _x_d = pd.Series(0.5, index=_dv.index)
    _mask = (_x_n > _x_d) & _md.notna() & _x_n.notna() & _x_d.notna()
    _nfill = int(_mask.sum())
    if _nfill > 0:
        ax.fill_betweenx(
            _md.to_numpy(), _x_d.to_numpy(), _x_n.to_numpy(),
            where=_mask.to_numpy(),
            color=color, alpha=alpha, zorder=zorder, interpolate=False)
    return _nfill



def ensure_render_gate():
    """【2026-10-30 R52】渲染门禁自动触发：logvis.py 或门禁脚本比上次门禁
    通过时间戳（_gate_pass.stamp）新 → 先跑 _test_symbol_texture.py，
    FAIL 即抛异常中止出图；门禁脚本缺失的部署环境跳过并记日志。
    背景（用户 2026-10-30 定案）：可视化问题已多次反复（R48 底色/R49 断行/
    R50 密疏），检测必须焊进出图流程——不依赖任何人记得手动跑门禁。"""
    import subprocess
    _here = Path(__file__).resolve().parent
    _gate = _here / '_test_symbol_texture.py'
    if not _gate.exists():
        logger.debug('渲染门禁脚本缺失，跳过自动门禁: %s', _gate)
        return
    _stamp = _here / '_gate_pass.stamp'
    _src = Path(__file__).resolve()
    _key = max(_src.stat().st_mtime, _gate.stat().st_mtime)
    if _stamp.exists() and _stamp.stat().st_mtime >= _key:
        return
    logger.info('渲染门禁触发（logvis/门禁脚本有更新），运行 _test_symbol_texture.py ...')
    try:
        _r = subprocess.run([sys.executable, str(_gate)], cwd=str(_here),
                            capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError('渲染门禁超时(600s)，禁止出图')
    _tail = '\n'.join((_r.stdout or '').splitlines()[-10:])
    if _r.returncode != 0:
        logger.error('渲染门禁 FAIL（exit %d）——出图中止。门禁输出尾部:\n%s',
                     _r.returncode, _tail)
        raise RuntimeError('渲染门禁 _test_symbol_texture.py 未通过（exit %d），'
                           '禁止出图，详见运行日志' % _r.returncode)
    _stamp.write_text(str(datetime.datetime.now()))
    logger.info('渲染门禁 PASS（自动触发），时间戳已更新。\n%s', _tail)


# 图面 QC 跳过行距断言的岩性（符号本身天然不规则/随机虚线）：
# 火成岩人字纹/杂斑、蒸发岩 dash 类
_QC_SKIP_LITH_PREFIX = ('basalt', 'ign', 'volcanic', 'andesite', 'rhyolite',
                        'granite', 'diorite', 'porphyry', 'spilit',
                        'halite', 'anhy')


def _qc_window_skip(data, d0, d1):
    """窗口内主岩性属天然不规则类，或主 VALID_CURVES_COUNT<3（岩性道合法
    留空，R33）→ 跳过行距/空白断言。"""
    try:
        if data is None or 'LITHOLOGY' not in getattr(data, 'columns', []):
            return True
        md = data['MD'] if 'MD' in data.columns else data.index
        mask = (md >= min(d0, d1)) & (md <= max(d0, d1))
        if not bool(mask.any()):
            return True
        _v = str(data.loc[mask, 'LITHOLOGY'].mode().iloc[0]).lower()
        if any(_v.startswith(_p) for _p in _QC_SKIP_LITH_PREFIX):
            return True
        if 'VALID_CURVES_COUNT' in data.columns:
            _vc = data.loc[mask, 'VALID_CURVES_COUNT'].mode()
            if len(_vc) and int(_vc.iloc[0]) < 3:
                return True
        return False
    except Exception:
        return True


def figure_texture_qc(fig, well_name='', data=None):
    """【2026-10-30 R52/R52b】出图前图面纹理 QC（报告不阻断，logger.warning 留痕）：
    对打 _lith_qc 标记的符号道（岩性道=整宽 3%-97%、PROFILE 道=矿物带左缘
    2%-20% 窄条），按**岩性游程**（_contiguous_lith_runs 唯一分段源）逐段做
    整段墨迹检查（两道）+ 行距均匀性（**仅岩性道**），兜底抓渲染门禁盲区/
    GUI 路径回归。
    【R52b】分段必须用岩性游程而非固定窗口——不同岩性符号天然行距不同
    （砖纹/点阵/横线混在一个 1400px 窗里 CV 必然虚高，111D 实测假阳性 9 窗）。
    【R52c】行距断言仅限岩性道：PROFILE 道是矿物比例**堆叠带**，各矿物子带
    宽度随深度变化，任何固定窄条都会横穿移动的子带边界混入不同符号行距
    （111D 实测 4 条灰岩游程假阳性，rowcheck 证伪）——PROFILE 带行距由渲染
    门禁的合成矿物抖动场景把关，QC 侧只查空白/墨迹。
    阈值比门禁宽（CV>0.5、空缺>3×中位行距）——本 QC 无逐段符号类别信息，
    只报"肉眼可见"级异常；精细判定仍以 _test_symbol_texture.py 为准。
    返回问题列表（写入 results['render_qc_warnings']）。"""
    problems = []
    arr = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    H, W = arr.shape[:2]
    # 岩性游程（两道唯一分段源），[(i0, i1, lith)] 索引闭区间
    runs = []
    _md = None
    if data is not None and 'LITHOLOGY' in getattr(data, 'columns', []):
        _md = (data['MD'] if 'MD' in data.columns else data.index)
        _liths = data['LITHOLOGY'].astype(str).str.lower().tolist()
        _valid = None
        if 'VALID_CURVES_COUNT' in data.columns:
            _valid = (data['VALID_CURVES_COUNT'] >= 3).tolist()
        runs = _contiguous_lith_runs(_liths, _valid)
    for ax in fig.axes:
        _tag = getattr(ax, '_lith_qc', None)
        if not _tag:
            continue
        xa0, xa1 = ax.get_xlim()
        ya0, ya1 = ax.get_ylim()
        d_top, d_bot = min(ya0, ya1), max(ya0, ya1)
        fx0, fx1 = ((0.03, 0.97) if _tag == 'lith' else (0.02, 0.20))
        x_l = xa0 + (xa1 - xa0) * min(fx0, fx1)
        x_r = xa0 + (xa1 - xa0) * max(fx0, fx1)
        _pa = ax.transData.transform((x_l, d_bot))
        _pb = ax.transData.transform((x_r, d_top))
        r_top = max(0, int(min(H - _pa[1], H - _pb[1])) + 1)
        r_bot = min(H, int(max(H - _pa[1], H - _pb[1])) - 1)
        c0 = max(0, int(min(_pa[0], _pb[0])) + 2)
        c1 = min(W, int(max(_pa[0], _pb[0])) - 2)
        if r_bot - r_top < 200 or c1 - c0 < 8:
            continue

        def _row_of(_d):
            _f = (_d - d_top) / max(d_bot - d_top, 1e-9)
            return int(r_top + _f * (r_bot - r_top))

        for (i0, i1, lith) in runs:
            if _md is None:
                break
            d0 = float(_md.iloc[i0])
            d1 = float(_md.iloc[i1])
            if any(lith.startswith(_p) for _p in _QC_SKIP_LITH_PREFIX):
                continue    # 火成岩人字纹/蒸发岩 dash 类符号天然不规则
            if _tag != 'lith':
                pass        # 【R52c】PROFILE 堆叠带不做行距断言（见 docstring）
            ra, rb = _row_of(d0), _row_of(d1)
            ra2, rb2 = max(ra, r_top), min(rb, r_bot)
            if rb2 - ra2 < 180:
                continue    # 段高不足（<~5m）不做行距断言，薄段由相邻段接续
            reg = arr[ra2:rb2, c0:c1].astype(int)
            med = np.median(reg, axis=1, keepdims=True)
            ink = (np.abs(reg - med).sum(axis=2) > 120)
            tot = float(ink.mean())
            if tot < 0.004:
                problems.append('%s %.0f-%.0fm %s: 整段墨迹率 %.4f——疑似纯底色无符号'
                                % (well_name, d0, d1, lith, tot))
                continue
            rowd = ink.sum(axis=1).astype(float)
            if rowd.max() <= 0:
                continue
            thr = rowd.max() * 0.5
            peaks, i, n = [], 0, len(rowd)
            while i < n:
                if rowd[i] > thr:
                    j = i
                    while j < n and rowd[j] > thr:
                        j += 1
                    peaks.append((i + j) / 2.0)
                    i = j
                else:
                    i += 1
            dd = np.diff(peaks)
            dd = dd[(dd > 4) & (dd < 400)]
            if len(dd) < 10:
                continue
            if _tag != 'lith':
                continue    # 【R52c】PROFILE 堆叠带只查空白，不做行距断言
            pitch = float(np.median(dd))
            cv = float(dd.std() / pitch)
            gaps = int((dd > 3.0 * pitch).sum())
            if cv > 0.5 or gaps:
                problems.append(
                    '%s %.0f-%.0fm %s: 行距 CV=%.2f 空缺=%d (pitch=%.1fpx)'
                    '——疑似间隔不一致/稀疏' % (well_name, d0, d1, lith, cv, gaps, pitch))
    for _p in problems:
        logger.warning('图面纹理QC: %s', _p)
    if not problems:
        logger.info('图面纹理QC: 通过（符号道行距/墨迹无异常段）')
    return problems



def visualize_composite_log(data, results, gas_data=None, quicklook_config=None):
    """综合图绘制流程入口（用户2026-10-15"综合图走可视化综合图的绘制流程，
    快速解释走可视化快速解释的绘制流程，前期处理流程一样"）。

    cmpt 图版 → 图头(18字段信息表/图例) → 正图 → footer → 单页 PDF。
    前期处理流程（数据加载/QC/计算/岩性/沉积相/解释）由调用方 logInt
    主流程完成，与本绘制流程无关。
    """
    return _render_log_plot(data, results, gas_data=gas_data, quicklook=False,
                            quicklook_config=quicklook_config)


def visualize_quicklook_log(data, results, gas_data=None, quicklook_config=None,
                            company_logo=None, contractor_logo=None):
    """快速解释图绘制流程入口（与综合图绘制流程并列、互不混用）。

    qlpt 图版 → 页1 右转表(表1/表2) → 页2 BH/CS → 页3 LEGEND+正图
    → footer 拼装 → 单页 PDF。quicklook_config/图标仅本流程使用。
    """
    return _render_log_plot(data, results, gas_data=gas_data, quicklook=True,
                            quicklook_config=quicklook_config,
                            company_logo=company_logo,
                            contractor_logo=contractor_logo)


def _render_log_plot(data, results, gas_data=None, quicklook=False,
                            company_logo=None, contractor_logo=None,
                            quicklook_config=None):
    """可视化综合测井图，可选气测数据道
    
    Args:
        data: 主测井数据 DataFrame，必须包含MD列
        results: 结果字典，包含 well_name, output_dir, las_info 等
        gas_data: 可选的气测数据 DataFrame，包含MD和气体组分列（如TG, C1, C2等）
        quicklook: 是否为 quick look 快速解释格式
            （True: 图头=Well Logging Interpretation Result Plot + BOREHOLE/CASING RECORD
             + 井位表 + LEGEND 流体类别；False: 标准 Composite Log Plot 版式）
        company_logo: 左上角业主图标路径（随业主动态更换），None 用 symbol/company.png
        contractor_logo: 右上角承包商图标路径（随业主动态更换），None 用 symbol/contractor.png
        quicklook_config: quick look 出图格式配置 dict（图例顺序/颜色/标题可随甲方变化），
            None 用内置默认（BET-1 masterlog 12 类流体）。
            字段: format_name / title_template / legend_title / legend_items[{'label','color'}]
            兼容说明（2026-10-10 图版化）: quicklook_config 仍优先；未传时
            logvis 直接调用 templates/qlpt.json（快速解释图版）出图。
    """
    # 【2026-10-10 图版化】读取图版：quicklook→qlpt.json，综合图→cmpt.json；
    # 显式传入 quicklook_config（旧式配置）时以其覆盖图版同名字段，向后兼容。
    # 【2026-10-30 R52】渲染门禁自动触发（可视化问题多次反复，检测必须
    # 焊进出图流程）：logvis/门禁脚本有更新 → 先跑合成井纹理门禁，FAIL 中止
    ensure_render_gate()
    _tpl = {}
    if quicklook_config and isinstance(quicklook_config, dict):
        _tpl = dict(quicklook_config)
    else:
        _tpl = load_plot_template('qlpt' if quicklook else 'cmpt') or {}
    _fig_cfg = _tpl.get('figure') or {}
    _title_cfg = _tpl.get('title') or {}
    _ds_cfg = _tpl.get('depth_scale') or {}
    _lith_cfg = _tpl.get('lithology') or {}
    _io_cfg = _tpl.get('io') or {}
    global _TPL_DEPTH_SCALE, _TPL_CURVE_SCALE, _WELLINFO_FLAT
    _TPL_DEPTH_SCALE = _ds_cfg or None
    _TPL_CURVE_SCALE = (_fig_cfg.get('curve_scale') or _fig_cfg.get('curve_scale_den') or None)
    # 【2026-10-14】<井名>info.json 非空值优先于图版（深度比例尺 curve_scale_ft/m 等）
    _WELLINFO_FLAT = _load_well_info_json(results)
    _lith_colors_tpl = _lith_cfg.get('colors')
    if isinstance(_lith_colors_tpl, dict) and _lith_colors_tpl:
        LITH_BG_COLORS.update(_lith_colors_tpl)
    # 【2026-10-13 用户要求】图内所有字体一致：未显式指定字体的文字（刻度
    # 数字、Depth 标签等默认 DejaVu Sans）统一为微软雅黑，与表1/表2/表3 一致
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = (['Microsoft YaHei']
                                       + list(plt.rcParams['font.sans-serif']))
    if data is None:
        logger.error("数据未加载")
        return None
    
    try:
        if 'MD' not in data.columns:
            logger.error("数据中缺少Depth列 'MD'")
            return None
        
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
        raw_curves = ['CAL', 'SP', 'GR', 'RT', 'LLD', 'ILD', 'R90', 'MSFL', 'LLS', 
                      'AT10', 'AT20', 'AT30', 'AT60', 'AT90',
                      'M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX',
                      'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'DTCO', 'AC', 'PE']
        
        # 找到有有效曲线的深度范围
        # 顶部：从第一条有有效曲线的深度开始
        # 底部：到最后一条有有效曲线的深度截止
        # 如果某段深度所有10条曲线的值都无效（NaN或超出合理范围），则不绘制这段区域
        
        # 获取数据中实际可用的曲线
        available_curves = [curve for curve in raw_curves if curve in data.columns]

        # 【2026-10-21 R18】绘图前置：套管/水泥块段与「有效曲线 <3 条」段整段置空
        # （只作用于绘图副本，不回写 processed.csv）
        _pr_cfg = _load_plot_range_cfg()
        _minc_draw = int(_pr_cfg.get('start_min_valid_curves', 3) or 3)
        data, _n_blank = _blank_borehole_and_lowcurve(
            data, _minc_draw, '快速解释图' if quicklook else '综合图')

        # 使用数据的实际深度范围，不进行有效曲线过滤
        # 确保完整绘制所有数据，不因为有效曲线判断而裁剪
        # 【2026-10-08 用户要求】可视化出图从套管外（裸眼段）开始：
        # IS_CASING=True 的套管段点测井反映泥浆/钢材，不作为绘图起点，
        # depth_min 取第一个裸眼采样点（BET-1 实测：6307→6456ft）
        actual_first_depth = data['MD'].iloc[0]
        if 'IS_CASING' in data.columns:
            _cs = data['IS_CASING'].fillna(False).astype(str).str.lower().isin(('true', '1', '1.0'))
            _oh = data.loc[~_cs, 'MD']
            if len(_oh) > 0:
                actual_first_depth = float(_oh.iloc[0])
                logger.info('从裸眼段起点 %.1f 开始（套管段已跳过，%d 点）',
                            actual_first_depth, int(_cs.sum()))
        # 【2026-10-21 R18 用户口径】"出图也要参照综合图的要求，少于3条有效曲线
        # 或者在套管内就不绘制，只绘制在裸眼的井段图" —— 综合图起点判据是
        # VALID_CURVES_COUNT >= 3（config plot_range.start_min_valid_curves），
        # 快速解释此前**完全没接**这条规则 ⇒ 导管/表层/未测段（RP-13 占 84%）
        # 整段画成空白道。这里把同一判据接到两种图上。
        _plot_start_cfg = _load_plot_range_cfg()
        if _plot_start_cfg.get('enabled', True):
            _minc = int(_plot_start_cfg.get('start_min_valid_curves', 3) or 3)
            if 'VALID_CURVES_COUNT' in data.columns:
                _vc = pd.to_numeric(data['VALID_CURVES_COUNT'], errors='coerce').fillna(0)
                _ok = data.loc[_vc >= _minc, 'MD']
                if 'IS_CASING' in data.columns:
                    _cs2 = data['IS_CASING'].fillna(False).astype(str).str.lower().isin(
                        ('true', '1', '1.0'))
                    _ok = _ok[~_cs2.reindex(_ok.index, fill_value=False)]
                if len(_ok) > 0:
                    _new_first = float(_ok.iloc[0])
                    if _new_first > actual_first_depth:
                        logger.info(
                            '出图起点裁剪: %.1f → %.1f m'
                            '（首个有效曲线 ≥%d 的深度，其上井段不绘制）',
                            actual_first_depth, _new_first, _minc)
                        actual_first_depth = _new_first
        actual_last_depth = data['MD'].iloc[-1]
        
        # 深度刻度显示范围：向下取整到10个深度单位（顶部），向上取整到10个深度单位（底部）。
        # 【2026-10-09 公英制自适应】10 的倍数在米制（整十米）与英制（整十英尺，
        # 深度道刻度（米制主100/次10；英制主100/次20）均为10的倍数）下都自洽，无需按单位区分步长。
        depth_min = ((int(float(actual_first_depth)) // 10) * 10)
        depth_max = ((int(float(actual_last_depth)) + 9) // 10) * 10
            
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
        # 【2026-10-15 用户要求】侧向电阻率只有 RD/RS/MSFL 等就只绘制3条（一道）；
        # 阵列电阻率 AT/AF/M2R 系列（浅→深 10-90 或 10-120）要完全绘制——
        # 每条阵列曲线自成一条刻度槽；传统与阵列两者都有时增加电阻率道（分两道）。
        traditional_res = {
            'MSFL': ['MSFL', 'RMSL'],
            'LLS': ['LLS', 'RS'],
            'LLD': ['LLD', 'RD', 'RT', 'ILD', 'R90']
        }

        trad_res_cols = []
        for _rt in ('MSFL', 'LLS', 'LLD'):
            for col in traditional_res[_rt]:
                if col in data.columns and col not in trad_res_cols:
                    trad_res_cols.append(col)
                    break

        # 阵列系列：前缀 + 浅→深后缀（用户2026-10-15补充：不只 AT/M2R 开头，
        # 还有 AF 开头，均为 10-90 或 10-120）；取第一个有命中的前缀系列全部曲线
        _ARRAY_SERIES = [
            ('AT', ['AT10', 'AT20', 'AT30', 'AT60', 'AT90']),
            ('AF', ['AF10', 'AF20', 'AF30', 'AF60', 'AF90', 'AF120']),
            ('M2R', ['M2R1', 'M2R2', 'M2R3', 'M2R6', 'M2RX']),
            # 【2026-10-21 R18】补 RAL 系列（HAL7506 等老井的阵列电阻率，1~5 编号；
            #   RAL1 探测最深 → 按浅→深排 RAL5…RAL1，与 AT/AF 的槽位顺序一致）
            ('RAL', ['RAL5', 'RAL4', 'RAL3', 'RAL2', 'RAL1']),
        ]
        array_res_cols = []
        for _pfx, _members in _ARRAY_SERIES:
            _hits = [c for c in _members if c in data.columns]
            if _hits:
                array_res_cols = _hits
                break

        # 【2026-10-16 / 2026-10-21 用户定案】RT 来自阵列回填时不绘旧电阻率道。
        # 【R18 强化】用户口径："没有 RD/RS/MSFL 等曲线只有 RT 的老电阻率道，
        #   在有阵列及其它电阻率道的情况下不用绘制了，但阵列的电阻率道必须绘制"。
        #   ⇒ 判据从"数值一致"放宽为"**无任何原生侧向曲线**"（MSFL/RMSL/LLS/RS/
        #   LLD/RD 全无），此时传统道只剩 RT/ILD/R90 这类回填/单曲线 → 整道不绘。
        #   数值一致检查保留为附加证据（ILT 等多源混合情形下仍能识别）。
        _NATIVE_LATERAL = ('MSFL', 'RMSL', 'LLS', 'RS', 'LLD', 'RD')

        def _drop_trad_backfill_rt(trad_list, arr_cols):
            """传统道仅由回填 RT 构成且存在阵列道 → 传统道置空。"""
            if not trad_list or not arr_cols:
                return trad_list
            if any(c in _NATIVE_LATERAL for c in trad_list):
                return trad_list
            _extra = ''
            _rt_ser = pd.to_numeric(data['RT'], errors='coerce') \
                if 'RT' in data.columns else None
            if _rt_ser is not None:
                for _ac in arr_cols:
                    _ar = pd.to_numeric(data[_ac], errors='coerce')
                    _both = _rt_ser.notna() & _ar.notna()
                    if _both.sum() >= 100 and float(
                            (_rt_ser[_both] == _ar[_both]).mean()) > 0.95:
                        _extra = f'（RT 与 {_ac} 数值一致=回填）'
                        break
            logger.info('传统电阻率道仅含回填 RT/ILD/R90（无 RD/RS/MSFL 等原生'
                        '侧向）且存在阵列道 %s → 不绘传统电阻率道%s',
                        arr_cols, _extra)
            return []

        trad_res_cols = _drop_trad_backfill_rt(trad_res_cols, array_res_cols)

        # 向后兼容：下游（绘图块）沿用分道视图
        resistivity_cols_pre = trad_res_cols + array_res_cols
        has_traditional_pre = bool(trad_res_cols)
        # 【2026-10-15 用户要求】快速图（现场出图）传统道"尽量全"：传统系列池中
        # 所有出现的列都画（如 LLD 与 RT 并存时都保留）；综合图（后方分析）
        # 传统道精选3条（深/中/浅——判岩性油气层核心），沿用上方 alias 归并结果
        _trad_pool = []
        for _aliases in traditional_res.values():
            for col in _aliases:
                if col in data.columns and col not in _trad_pool:
                    _trad_pool.append(col)
        trad_res_all = [c for c in ['MSFL', 'RMSL', 'LLS', 'RS',
                                    'LLD', 'RD', 'RT', 'ILD', 'R90'] if c in _trad_pool]
        # 【2026-10-16 / R18】快速图传统池同样剔除回填 RT（与综合图口径一致）
        trad_res_all = _drop_trad_backfill_rt(trad_res_all, array_res_cols)
        # TG（全烃）在快速图并入传统电阻率道末槽 → 槽位规划需预留 1 个
        has_gas_pre = gas_data is not None and len(gas_data) > 0
        if quicklook:
            _tg_extra = 1 if (has_gas_pre and (trad_res_all or array_res_cols)) else 0
            n_res_curves = max(len(trad_res_all) + _tg_extra, len(array_res_cols))
        else:
            n_res_curves = max(len(trad_res_cols), len(array_res_cols))
        
        # 检查是否有BS曲线
        has_bs = _find_column(data, ['BS', 'BIT', 'BITSIZE', 'BIT_SIZE', 'BSIZE', 'DRILL_BIT']) is not None
        # 【2026-10-21 R18】无 BS 列但有井眼程序时也会占一个槽位（合成 BIT 曲线）
        if not has_bs and (results or {}).get('hole_program'):
            has_bs = True
        
        # ========== 计算最大曲线数量和对齐刻度位置 ==========
        # 第1道（岩性道）：BS(有则算)+CAL+SP+GR = 4(有BS)或3(无BS)，
        #                   +KTH(无铀伽马,有则算)【2026-10-16 用户要求】
        # 第2道（电阻率道）：n_res_curves（传统3条或阵列感应5条）
        # 第3道（孔隙度道）：PE+NPHI+RHOB+DT = 4
        _kth_col_pre = _find_column(data, ['KTH', 'CGR'])
        n_track1_curves = (4 if has_bs else 3) + (1 if _kth_col_pre else 0)
        n_track3_curves = 4
        max_curves = max(n_track1_curves, n_res_curves, n_track3_curves)

        # 确保至少3个刻度位置，最多8个
        max_curves = max(3, min(max_curves, 8))

        # 动态计算图头区高度：每条曲线2.0cm + 底部0.5cm余量
        # 【2026-10-10 图版化】每条曲线高度可配（图版 figure.header_per_curve_cm）
        # 【2026-10-16 用户要求】刻度条纵向间距整体压缩：默认 2.0 → 1.7cm，
        # 为气测道容纳 MCH 等更多刻度槽留出纵向空间
        _hpc = _fig_cfg.get('header_per_curve_cm') or 1.7
        HEADER_HEIGHT_CM_ADJUSTED = max_curves * _hpc + 0.5
        # 计算对齐刻度位置（从底部0.8cm到顶部0.8cm均匀分布）
        ALIGNED_POSITIONS_CM = []
        for i in range(max_curves):
            pos = 0.8 + i * (HEADER_HEIGHT_CM_ADJUSTED - 1.6) / max(max_curves - 1, 1)
            ALIGNED_POSITIONS_CM.append(pos)
        
        cm_to_inch = 1 / 2.54
        header_height_inch = HEADER_HEIGHT_CM_ADJUSTED * cm_to_inch
        title_las_gap_inch = TITLE_LAS_GAP_CM * cm_to_inch
        las_header_gap_inch = LAS_HEADER_GAP_CM * cm_to_inch
        # 【2026-10-10 图版化】标题区高度可配（图版 figure.title_height_cm）
        _title_h_cm = _fig_cfg.get('title_height_cm') or TITLE_HEIGHT_CM
        title_height_inch = _title_h_cm * cm_to_inch

        # 计算曲线区高度（比例尺可配：英制默认 1:240(den=240)，可 1:480(den=480)；
        # 公制默认 1:200(den=200)，可 1:500(den=500)。图版 figure.curve_scale={'ft':'1:240','m':'1:200'}
        # 或 figure.curve_scale_den={'ft':240,'m':200}）
        _du = DEPTH_UNIT if DEPTH_UNIT != 'auto' else _detect_depth_unit(depth_min, depth_max)
        _scale_cfg = _fig_cfg.get('curve_scale')
        _legacy_den = _fig_cfg.get('curve_scale_den')
        # 解析 '1:240' 或 240 两种形态；兼容 dict{ft,m} / 标量 / 字符串旧形态
        def _parse_den(v, default):
            if isinstance(v, (int, float)):
                return int(v)
            if isinstance(v, str) and ':' in v:
                try:
                    return int(v.split(':')[1])
                except Exception:
                    return default
            return default
        if isinstance(_legacy_den, dict) or isinstance(_scale_cfg, dict):
            # dict 形态：curve_scale_den dict 优先，curve_scale dict 兜底
            _d = _legacy_den if isinstance(_legacy_den, dict) else {}
            _s = _scale_cfg if isinstance(_scale_cfg, dict) else {}
            _den_ft = _parse_den(_d.get('ft'), _parse_den(_s.get('ft'), 240))
            _den_m = _parse_den(_d.get('m'), _parse_den(_s.get('m'), 200))
        else:
            # 旧单值形态（cmpt.json）：curve_scale_den=240 / curve_scale='1:200'
            _den_ft = _parse_den(_legacy_den if _legacy_den is not None else _scale_cfg, 240)
            _den_m = _parse_den(_scale_cfg, 200)
        _scale_den = _den_ft if _du == 'ft' else _den_m
        curve_height_cm = depth_range * (30.48 if _du == 'ft' else 100) / _scale_den
        curve_height_inch = curve_height_cm * cm_to_inch

        # 计算LAS信息区高度（4列，5行数据 + 3部分图例*2行，每行约1.3cm）
        # 【2026-10-10 图版化】图版 figure.las_height_cm 可配；null 按自动
        _las_h_tpl = _fig_cfg.get('las_height_cm')
        las_height_cm = _las_h_tpl if _las_h_tpl else (11 * 1.3)
        if quicklook:
            # 【2026-10-10 单页式 quick look】图头区（LAS 区）放竖排转置信息表
            # （表1 井位 15 字段 + 表2 测量 12 字段竖排）+ 免责声明 + BOREHOLE/CASING
            # 并排 3 列表 + LEGEND 两列排布。竖排表占用高度大，默认 32cm
            # （图版 figure.las_height_cm 可配；null 按自动）。
            las_height_cm = _las_h_tpl if _las_h_tpl else 32
        las_height_inch = las_height_cm * cm_to_inch

        # 总高度 = 图名高度 + 图名-LAS间隔 + LAS高度 + 图头区高度 + 曲线区高度
        # 去掉LAS-图头区间隔，让LAS信息区直接紧贴图头区，避免黑色带状区域
        total_height_inch = curve_height_inch + header_height_inch + las_height_inch + title_las_gap_inch + title_height_inch
        # 【2026-10-10 图版化】整图最低高度可配（图版 figure.min_total_height_inch）
        total_height_inch = max(total_height_inch, _fig_cfg.get('min_total_height_inch') or 14)
        
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
        
        # 【2026-10-10 图版化】图宽可配（图版 figure.figwidth_inch，默认24）
        # 【2026-10-27 R27】figure 必须用与 savefig 相同的 dpi 创建：此前缺省
        # dpi=100、savefig 用模板 150 —— 设备像素按 100dpi 计算，最终被
        # nearest 放大 1.5 倍，矢量瓦片斜缝出现锯齿（"毛毛刺刺"），
        # 竖线因轴对齐不受影响。dpi 一致后瓦片 1:1 贴图。
        _fig_w = _fig_cfg.get('figwidth_inch') or 24
        _fig_dpi = int(_fig_cfg.get('dpi') or 150)
        fig = plt.figure(figsize=(_fig_w, total_height_inch), dpi=_fig_dpi)
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
            # 【2026-10-10 图版化】气测道宽度参数可配（图版 figure.gas_track_width_*）
            _gtw_min = _fig_cfg.get('gas_track_width_min') or 0.4
            _gtw_max = _fig_cfg.get('gas_track_width_max') or 2.0
            _gtw_per = _fig_cfg.get('gas_track_width_per_curve') or 0.15
            gas_track_width = max(_gtw_min, min(_gtw_max, gas_curve_count * _gtw_per))
            # 更新max_curves以包含气测曲线数量，确保所有气测曲线都有刻度槽位
            # 【2026-10-16 用户要求】上限 10 → 12：本井气测 C1-C8+MCH+BZ+TL
            # 共 11 条曲线，10 槽会截断 MCH 刻度
            max_curves = max(max_curves, min(gas_curve_count, 12))
            # 更新图头区高度：气测槽位已并入 max_curves 统一均匀分布，
            # 【2026-10-16 用户要求】取消"超4条每条+1.5cm"的额外扩高（改为
            # 压缩槽距），图头高度 = max_curves × _hpc + 余量，与其他道一致
            HEADER_HEIGHT_CM_ADJUSTED = max(HEADER_HEIGHT_CM_ADJUSTED,
                                            max_curves * _hpc + 0.5)
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
        
        if quicklook:
            # 【2026-10-10 严格对齐样本】quick look 正图（样本 BET-1 版式）：
            #   Lithology | Resistivity(传统) | [Resistivity(阵列)] | Depth | Porosity
            #   | Saturation | Permeability | Volume Analysis | RESULT（最右竖排）
            # 气测 TG 并入传统电阻率道（样本无独立气测道）；岩性填充/沉积相合并为 Volume Analysis 道。
            # 【2026-10-13 用户要求正图带油气水】RESULT 道由 0.20 加宽至 0.42。
            # 【2026-10-15 用户要求】电阻率道与综合图逻辑一致：传统道+阵列道分道
            # （两者都有→2道，只有其一→1道）；道宽1.4 与综合图相同（容纳刻度数字）。
            _q_layout = [('LITHO', 1.2)]
            if trad_res_cols:
                _q_layout.append(('RES_TRAD', 1.4))
            if array_res_cols:
                _q_layout.append(('RES_ARRAY', 1.4))
            # 【2026-10-22 用户要求】3 道深度道与 4 道孔隙度曲线道互换位置
            # （与综合图 POR→DEPTH 顺序一致）
            _q_layout += [('POR', 1.0), ('DEPTH', 0.30), ('SW', 0.6), ('POR2', 0.6)]
            # 【2026-10-22 用户要求】quicklook 把气测数据也绘制上 → 独立气测道
            # （原做法仅把 TG 骑在电阻率道末槽，无法呈现组分；此处与综合图同实现）
            # 【2026-10-26 用户要求】气测道与 profile 道互换 → 气测道在前
            if has_gas:
                _q_layout.append(('GAS', min(gas_track_width, 1.6)))
                logger.info("气测道已插入 quicklook 道布局（位于 profile 道之前）")
            _q_layout.append(('PROFILE', 1.0))
            # 【2026-10-27 R27 用户要求】REG 道撤出 quicklook：REG 对比改在
            # 交会图中呈现（CGI-Sw / RTI-孔隙度，作气层或油气层依据）。
            _q_layout.append(('INTERP', 0.42))
            _n_tracks = len(_q_layout)
            # 【2026-10-13 用户要求】解释图与表1/表2/表3 一样宽：近满幅（留半线宽余量）。
            gs = GridSpec(1, _n_tracks, width_ratios=[w for _, w in _q_layout], wspace=0,
                          left=0.002, right=0.998, top=1.0, bottom=0.0)
            axes = [fig.add_subplot(gs[i]) for i in range(_n_tracks)]
            _q_map = {name: i for i, (name, _) in enumerate(_q_layout)}
            IDX_LITHO = _q_map['LITHO']
            IDX_RES_TRAD = _q_map.get('RES_TRAD')
            IDX_RES_ARRAY = _q_map.get('RES_ARRAY')
            IDX_RES = IDX_RES_TRAD if IDX_RES_TRAD is not None else IDX_RES_ARRAY
            IDX_DEPTH = _q_map['DEPTH']
            IDX_POR = _q_map['POR']
            IDX_SW = _q_map['SW']
            IDX_POR2 = _q_map['POR2']
            IDX_PROFILE = _q_map['PROFILE']
            IDX_INTERP = _q_map['INTERP']
            # 【2026-10-22】quicklook 新增独立气测道
            IDX_GAS = _q_map.get('GAS')
            IDX_LITHO_FILL = IDX_FACIES = None
            IDX_REG = _q_map.get('REG')
        else:
            # 【2026-10-15 用户要求】综合图道布局动态化：
            #   ①传统电阻率(RD/RS/MSFL 3条)与阵列电阻率(AT/AF/M2R 全系列)两者都有
            #     →2个电阻率道（道宽1.4 容纳刻度数字与曲线名），只有其一→1道；
            #   ②SW与孔隙度合并一道（Sw 左锚 + 孔隙度反刻度右锚），原第6道取消；
            #   ③气测道在合并道之后。
            _layout = [('LITHO', 1.0)]
            if trad_res_cols:
                _layout.append(('RES_TRAD', 1.4))
            if array_res_cols:
                _layout.append(('RES_ARRAY', 1.4))
            # 【2026-10-16 用户要求】孔隙度道加宽 1.0 → 1.25：刻度数字与
            # 文字不再重叠
            _layout += [('POR', 1.25), ('DEPTH', 0.5), ('SWPOR', 1.0)]
            if has_gas:
                _layout.append(('GAS', gas_track_width))
            _layout += [('LITHO_FILL', 1.0), ('FACIES', 1.0), ('PROFILE', 1.0)]
            # 【2026-10-27 R27 用户要求】REG 道撤出综合图：REG 对比改在交会图
            # 中呈现（CGI-Sw / RTI-孔隙度，作气层或油气层依据）。
            _layout.append(('INTERP', 1.0))
            track_widths = [w for _, w in _layout]
            _n_tracks = len(_layout)
            gs = GridSpec(1, _n_tracks, width_ratios=track_widths, wspace=0)
            axes = [fig.add_subplot(gs[i]) for i in range(_n_tracks)]
            _idx_map = {name: i for i, (name, _) in enumerate(_layout)}
            IDX_LITHO = _idx_map['LITHO']
            IDX_RES_TRAD = _idx_map.get('RES_TRAD')
            IDX_RES_ARRAY = _idx_map.get('RES_ARRAY')
            IDX_RES = IDX_RES_TRAD if IDX_RES_TRAD is not None else IDX_RES_ARRAY
            IDX_POR = _idx_map['POR']
            IDX_DEPTH = _idx_map['DEPTH']
            IDX_SW = _idx_map['SWPOR']
            IDX_GAS = _idx_map.get('GAS')
            IDX_LITHO_FILL = _idx_map['LITHO_FILL']
            IDX_FACIES = _idx_map['FACIES']
            IDX_PROFILE = _idx_map['PROFILE']
            IDX_INTERP = _idx_map['INTERP']
            IDX_POR2 = None  # 综合图孔隙度已并入 SWPOR 合并道
            IDX_REG = _idx_map.get('REG')
        
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
        
        def draw_tick_labels(ax, cm_from_bottom, label, min_val, max_val, color='black', fontsize_label=9, fontsize_value=7, is_log=False, draw_tick_marks=True, end_labels='both', mid_labels='below'):
            """在图头区内绘制刻度标签和首尾数据，确保都在图头区内（使用figure坐标）

            【2026-10-16 用户要求】默认字号 11/9 → 9/7，与电阻率道/气测道既有
            取值一致 —— 各道刻度字体统一（原来第一道/孔隙度道 11/9、电阻率道
            9/7 混用）。显式传参的调用不受影响。

            Args:
                is_log: 是否为对数刻度。True时会在min_val和max_val之间绘制10的幂次刻度线和标签
                draw_tick_marks: 是否绘制对数刻度小竖线标记（气测道设为False避免视觉杂乱）
                end_labels: 首尾数值显示方式 'both'|'min'|'max'|'none'
                    【2026-10-15 用户要求】气测道标起始值+自适应最大值 → 传 'both'
                mid_labels: 对数中间幂次标签 'below'(线下,默认)|'none'
                    【2026-10-15 用户要求】气测道不标中间值 → 传 'none'
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
                # 【2026-10-12 用户定案】对数刻度条：左右首尾显示 min_val/max_val
                # （如 0.2 / 2000，与线性刻度行为一致），中间绘制 10 的幂次
                # 刻度线与数值标签（1/10/100/1000…）。
                # 【2026-10-15 用户要求】end_labels 控制首尾显示（气测道标起始值+最大值）
                if end_labels in ('both', 'min'):
                    ax.text(left_pos, actual_y_pos, f'{min_val:g}', color=color, fontsize=fontsize_value,
                           ha='left', va='bottom', transform=fig.transFigure, zorder=1001)
                if end_labels in ('both', 'max'):
                    # 【2026-10-15 用户要求】最大值 ≥1M 显示 1M/10M…（与幂次标签风格一致）；
                    # 其余用 %g 去掉浮点尾零（10000.0 → 10000）
                    _max_txt = f'{max_val / 1_000_000:g}M' if max_val >= 1_000_000 else f'{max_val:g}'
                    ax.text(right_pos, actual_y_pos, _max_txt, color=color, fontsize=fontsize_value,
                           ha='right', va='bottom', transform=fig.transFigure, zorder=1001)
                if mid_labels == 'none':
                    # 不标中间值：连幂次刻度小竖线一起跳过（气测道）
                    tick_powers = []
                else:
                    log_min = math.log10(min_val)
                    log_max = math.log10(max_val)
                    tick_powers = list(range(int(math.ceil(log_min)), int(math.log10(max_val)) + 1))

                # 中间幂次刻度（跳过已被首尾覆盖的边界幂次）
                for power in tick_powers:
                    val = 10 ** power
                    if val <= min_val or val >= max_val:
                        continue
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
                # 【2026-10-15 用户要求】最大值 ≥1M 显示 1M/10M…（快速图TG槽等线性路径）；
                # 其余用 %g 去掉浮点尾零（10000.0 → 10000）
                _max_txt = f'{max_val / 1_000_000:g}M' if max_val >= 1_000_000 else f'{max_val:g}'
                ax.text(left_pos, actual_y_pos, f'{min_val:g}', color=color, fontsize=fontsize_value,
                       ha='left', va='bottom', transform=fig.transFigure, zorder=1001)
                ax.text(right_pos, actual_y_pos, _max_txt, color=color, fontsize=fontsize_value,
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
        # 【2026-10-13 用户要求】解释图外框加粗 = 表2 口径（lw=2.0）；
        # 道间分隔线/图头分隔线仍用 0.8 细线
        _frame_lw_main = 2.0 if quicklook else linewidth
        # 上边框（图头区顶部）
        fig.add_artist(Line2D([overall_x_left, overall_x_right], [header_top_y, header_top_y],
                              color='black', linewidth=_frame_lw_main, transform=fig.transFigure, zorder=5000))
        # 左边框
        fig.add_artist(Line2D([overall_x_left, overall_x_left], [0, header_top_y],
                              color='black', linewidth=_frame_lw_main, transform=fig.transFigure, zorder=5000))
        # 右边框
        fig.add_artist(Line2D([overall_x_right, overall_x_right], [0, header_top_y],
                              color='black', linewidth=_frame_lw_main, transform=fig.transFigure, zorder=5000))
        # 下边框
        fig.add_artist(Line2D([overall_x_left, overall_x_right], [0, 0],
                              color='black', linewidth=_frame_lw_main, transform=fig.transFigure, zorder=5000))
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
        # 【2026-10-21 R18】LAS 无 BS 时用井眼程序合成阶梯 BIT 曲线
        # （用户："最后一个钻头是 8.5in 的，要以他为 bit 绘制 bit 曲线"）
        _bs_series = None
        if bs_col:
            _bs_series = pd.to_numeric(data[bs_col], errors='coerce')
        else:
            _bs_gen = _build_bs_from_hole_program(depth, results)
            if _bs_gen is not None:
                _bs_series = pd.Series(_bs_gen, index=data.index)
        # 井径刻度自适应：取 BS/CAL 实际量程（老井 8.5in 井 + 6in 井径时
        # 固定 (5.5,16.5) 会把两条曲线全压到左端看不出差别）
        _cal_col_probe = _find_column(data, _CAL_CANDIDATES)
        _rng_vals = []
        for _s in (_bs_series, (pd.to_numeric(data[_cal_col_probe], errors='coerce')
                                if _cal_col_probe else None)):
            if _s is not None:
                _v = pd.to_numeric(_s, errors='coerce').dropna()
                if len(_v):
                    _rng_vals += [_v.min(), _v.max()]
        if _rng_vals:
            _d_lo = max(0.0, min(_rng_vals) - 1.0)
            _d_hi = max(_rng_vals) + 1.5
            _d_t0 = round(_d_lo)
            _d_t1 = round(_d_hi)
        else:
            _d_lo, _d_hi, _d_t0, _d_t1 = 5.5, 16.5, 6, 16
        if _bs_series is not None and _bs_series.notna().any():
            _plot_curve(ax1, _bs_series, depth, 'black', (_d_lo, _d_hi), depth_max, depth_min, curve_height_ratio, header_bottom_y,
                       linestyle='--')
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'black')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'BS (in)', _d_t0, _d_t1, 'black', fontsize_value=7)
            track1_slot += 1
        else:
            _bs_series = None

        # CAL（下一个槽位）
        cal_col = _cal_col_probe
        if cal_col:
            _cal_series = pd.to_numeric(data[cal_col], errors='coerce')
            _plot_curve(ax1, _cal_series, depth, 'red', (_d_lo, _d_hi), depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'red')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'CAL (in)', _d_t0, _d_t1, 'red')
            track1_slot += 1

            # 【2026-10-21 R18 用户定案：统一的井径绘制规则】CAL 与 BS 之间
            # 按方向双色充填——超径(CAL>BS，扩径/井壁坍塌) 淡红、
            # 缩径(CAL<BS，泥饼/侵入) 淡蓝；无 BS 段不填。
            if _bs_series is not None:
                fill_ax = ax1.twiny()
                fill_ax.set_position(ax1.get_position())
                fill_ax.set_ylim(depth_max, depth_min)
                fill_ax.set_xlim(_d_lo, _d_hi)
                for spine in fill_ax.spines.values():
                    spine.set_visible(False)
                fill_ax.tick_params(axis='x', which='both', bottom=False, top=False,
                                    labelbottom=False, labeltop=False, length=0)
                fill_ax.set_xticks([])
                _c, _b = _cal_series, _bs_series
                _ok = _c.notna() & _b.notna()
                if int(_ok.sum()) > 10:
                    _vd, _vc, _vb = depth[_ok], _c[_ok], _b[_ok]
                    _over = _vc >= _vb
                    if _over.any():
                        fill_ax.fill_betweenx(_vd[_over], _vb[_over], _vc[_over],
                                              color=CAL_OVERFILL_COLOR, alpha=0.55,
                                              zorder=1, lw=0)
                    _under = ~_over
                    if _under.any():
                        fill_ax.fill_betweenx(_vd[_under], _vc[_under], _vb[_under],
                                              color=CAL_UNDERFILL_COLOR, alpha=0.55,
                                              zorder=1, lw=0)
        
        # SP（下一个槽位）
        # 【2026-10-15 用户要求】第一道没有曲线的（如SP）就不保留刻度条和曲线名——
        # SP 列缺失或全为 NaN 时不再画刻度条/'SP (mV)' 标签，后续曲线前移补位
        if 'SP' in data.columns and data['SP'].notna().any():
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

        # KTH（无铀伽马）【2026-10-16 用户要求】：碳酸盐岩+火成岩井去铀影响，
        # 刻度与 GR 一致（0-200 API）；列缺失或全 NaN 时不占槽位
        _kth_col = _find_column(data, ['KTH', 'CGR'])
        if _kth_col and data[_kth_col].notna().any():
            _plot_curve(ax1, data[_kth_col], depth, 'darkorange', (-10, 210),
                        depth_max, depth_min, curve_height_ratio, header_bottom_y)
            draw_tick_line(ax1, ALIGNED_POSITIONS_CM[track1_slot], 'darkorange')
            draw_tick_labels(ax1, ALIGNED_POSITIONS_CM[track1_slot],
                             f'{_kth_col} (API)', 0, 200, 'darkorange')
            track1_slot += 1

        # 【2026-10-13 用户要求】第1道图头区不再标注 WASH OUT（样本无需此文字）

        # ========== 电阻率道（quicklook 单一道 / 综合图 传统道+阵列道） ==========
        res_colors = ['green', 'red', 'black', 'blue', 'orange', 'purple']
        # 【2026-10-15 用户要求】电阻率道快速图与综合图逻辑一致：传统道+阵列道
        # 分道绘制（两者都有→2道，只有其一→1道）。差异仅在曲线取舍：
        #   快速图=现场出图：传统道尽量全（传统系列所有列）+ 阵列道全系列；
        #   综合图=后方分析：传统道精选3条（深/中/浅——判岩性油气层核心）+ 阵列道全系列。
        _trad_track_cols = trad_res_all if quicklook else trad_res_cols
        _res_track_specs = []
        if IDX_RES_TRAD is not None and _trad_track_cols:
            _res_track_specs.append((axes[IDX_RES_TRAD], _trad_track_cols, '传统'))
        if IDX_RES_ARRAY is not None and array_res_cols:
            _res_track_specs.append((axes[IDX_RES_ARRAY], array_res_cols, '阵列'))
        resistivity_cols = []
        for _ax_res, _res_cols, _res_tag in _res_track_specs:
            _setup_resistivity_track(_ax_res, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
            for i, col in enumerate(_res_cols):
                color = res_colors[i % len(res_colors)]
                _plot_log_curve(_ax_res, data[col], depth, color, (0.15, 3000), depth_max, depth_min, curve_height_ratio, header_bottom_y)
                draw_tick_line(_ax_res, ALIGNED_POSITIONS_CM[i], color)
                draw_tick_labels(_ax_res, ALIGNED_POSITIONS_CM[i], f'{col} (ohmm)', 0.2, 2000, color,
                                 fontsize_label=9, fontsize_value=7)
            resistivity_cols = _res_cols
            logger.info(f"电阻率道[{_res_tag}]绘制曲线: {_res_cols}")

        # 【2026-10-13 用户定案】quick look 时气测全烃 TG 并入传统电阻率道末槽
        # （无传统道时并入阵列道末槽）。
        # 【2026-10-15 用户要求】气测刻度一致性自适应：起始值固定 10，最大值取
        # 100/1000/10000/100000/1M…中最小的不小于数据最大值，曲线范围与刻度一致。
        # 【2026-10-22】气测已有独立气测道 → 不再在电阻率道末槽骑乘 TG
        if quicklook and has_gas and _res_track_specs and IDX_GAS is None:
            _tg_col = None
            for _c in ('TG', 'GAS_TG', 'TOTALGAS', 'GAS'):
                if _c in (gas_data.columns if gas_data is not None else []):
                    _tg_col = _c
                    break
            if _tg_col:
                # TG 骑乘分道逻辑下的第一道（优先传统道，其次阵列道）末槽
                _tg_ax, _tg_track_cols, _ = _res_track_specs[0]
                _tg_slot = len(_tg_track_cols)
                _gas_depth_col = _find_column(gas_data, ['MD', 'DEPTH', 'DEP', 'DEPT'])
                _gd = gas_data[_gas_depth_col] if _gas_depth_col else gas_data.iloc[:, 0]
                _tg_ser = gas_data[_tg_col]
                # 深度对齐到主深度轴（最近邻插值）
                _tg_aligned = np.interp(depth, _gd, _tg_ser.fillna(0).values)
                # 【2026-10-15 用户要求】TG 刻度自适应：起始 10，最大值取最紧整十倍数上界
                _tg_pos = _tg_aligned[_tg_aligned > 0]
                _tg_peak = float(_tg_pos.max()) if _tg_pos.size else 0.0
                _tg_vmax = 100.0
                while _tg_vmax < _tg_peak:
                    _tg_vmax *= 10.0
                if _tg_peak <= 0:
                    _tg_vmax = 1_000_000.0  # 无有效数据时回退 10-1M
                _plot_curve(_tg_ax, pd.Series(_tg_aligned, index=depth.index), depth,
                            'red', (10, _tg_vmax), depth_max, depth_min,
                            curve_height_ratio, header_bottom_y, linestyle='--')
                draw_tick_line(_tg_ax, ALIGNED_POSITIONS_CM[_tg_slot], 'red')
                draw_tick_labels(_tg_ax, ALIGNED_POSITIONS_CM[_tg_slot],
                                 f'{_tg_col} (ppm)', 10, _tg_vmax, 'red',
                                 fontsize_value=7)
        
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
        
        # 中子曲线（slot1，与CAL对齐，倒序绘制）
        # 第3道优先绘制**真实中子曲线**(NPHI/CNL/CNCF)，直观反映含氢指数；
        # 【2026-10-08】中子是原始测井读数，不受孔隙度有效性/储层判定限制——
        # 此前无 NPHI 时落到计算孔隙度 PHI 且被 mask 置NaN，造成曲线断续/平头
        phi_plot = None
        phi_label = None
        _nphi_col = next((c for c in ('NPHI', 'CNL', 'CNCF') if c in data.columns), None)
        if _nphi_col:
            nphi = data[_nphi_col].copy()
            if nphi.max() > 1:
                x_range = (65, -5)
                phi_label = f'{_nphi_col} (%)'
                tick_vals = [60, 0]
            else:
                x_range = (1.1, -0.1)
                phi_label = f'{_nphi_col} (v/v)'
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
            # 【2026-10-13】固定捕获中子刻度范围：x_range 会被后续 DT 块覆盖，
            # 密度-中子填充必须用此刻的中子范围，不能用后面的 x_range
            _nphi_x_range = x_range
            # 原始中子读数只反映真实缺测，不做任何 mask 置NaN（用户明确要求）
            _plot_curve(ax3, phi_plot, depth, 'green', x_range, depth_max, depth_min, curve_height_ratio, header_bottom_y)
            # 刻度始终绘制
            draw_tick_line(ax3, ALIGNED_POSITIONS_CM[track3_slot], 'green')
            draw_tick_labels(ax3, ALIGNED_POSITIONS_CM[track3_slot], phi_label, tick_vals[0], tick_vals[1], 'green')
            track3_slot += 1
        
        # RHOB（slot2，与SP对齐）
        # 优先使用RHOB，如果没有则使用DEN
        den_col = 'RHOB' if 'RHOB' in data.columns else ('DEN' if 'DEN' in data.columns else None)
        if den_col:
            # 原始密度读数只反映真实缺测，不做任何 mask 置NaN（与中子同规则）
            den_plot = data[den_col].copy()
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
            # 原始声波读数只反映真实缺测，不做任何 mask 置NaN（与中子同规则）
            dt_plot = data[dt_col].copy()
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

        # 【用户定案 2026-10-22】quicklook 孔隙度道图头不再标注 ZDEN>CNCF

        # 【2026-10-13 用户定案】Porosity 道密度-中子填充（挖掘效应）：
        # 调用独立方法模块 fill_gas_effect（quicklook 与综合图共用），
        # 纯相对位置规则：只填"中子在右、密度在左"两曲线之间的中间部分。
        if _nphi_col and den_col and phi_plot is not None and den_plot is not None:
            try:
                _nfill = fill_gas_effect(
                    ax3, data['MD'], data[_nphi_col], data[den_col],
                    nphi_range=_nphi_x_range, den_range=(1.7, 2.9))
                logger.info(f'Porosity 道密度-中子填充(仅中子在右)完成: {_nfill} 点')
            except Exception as _e:
                logger.warning('Porosity 道密度-中子填充失败: %s', _e)
        
        # ========== 深度道 ==========
        ax4 = axes[IDX_DEPTH]
        _setup_depth_track(ax4, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y)
        
        # ========== 含水饱和度 + 孔隙度合并道（Sw 左锚 + PHI 反刻度右锚） ==========
        # 【2026-10-15 用户要求】参照快速解释图，第5道SW和第6道孔隙度合成一道，
        # 孔隙度使用反刻度（0 贴右边框）——SW 与孔隙度分别绘制在道的两边
        ax5 = axes[IDX_SW]
        _setup_track_with_header(ax5, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)

        # 检查是否有足够的有效曲线
        has_valid_curves = False
        if 'VALID_CURVES_COUNT' in data.columns:
            has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3

        # 【2026-10-08】Sw 显示读 SW_DISP（logInt 生成：非储层归0，仅显示用）；
        # 无显示列时回退原始 Sw。判断逻辑一律读原始列，禁止用显示值。
        sw_col = _find_column(data, ['SW_DISP', 'Sw', 'SW'])
        if sw_col and has_valid_curves:
            # 0值保留为0（不设NaN），0即左边框，曲线自然闭合到左边框
            sw_plot = data[sw_col].copy()
            if not quicklook:
                # 综合图：线性 0-1（v/v），0 在左贴左边框；刻度条槽位1（与 quicklook 同序：SW 上/POR 下）
                _plot_curve(ax5, sw_plot, depth, 'blue', (0, 1.0), depth_max, depth_min, curve_height_ratio, header_bottom_y)
                draw_tick_line(ax5, ALIGNED_POSITIONS_CM[1], 'blue')
                draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[1], 'Sw (v/v)', 0, 1, 'blue')
            else:
                # 【2026-10-14 二十一轮定案】SW 刻度反转为 0→100（0 在左、曲线贴
                # 左边框），与 POR（0 在右、贴右边框）各以道左右两边为起点，便于区分；
                # 数据为小数(<1.5)自动 ×100；非储层归 0 显示在 0 刻度（左）。
                _sw_dmax = float(sw_plot.max())
                if _sw_dmax <= 1.5:
                    sw_plot = sw_plot * 100.0
                _plot_curve(ax5, sw_plot, depth, 'blue', (0.0, 100.0), depth_max,
                            depth_min, curve_height_ratio, header_bottom_y)
                # 【2026-10-14 用户定案】第5道2条刻度条与第4道底部往上第1条PE、
                # 第2条CNL横向对齐：SW→槽位1（CNL行），保持 SW 上/POR 下次序
                draw_tick_line(ax5, ALIGNED_POSITIONS_CM[1], 'blue')
                draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[1], 'Sw (%)', 0, 100, 'blue')

        # 【2026-10-16 用户要求】岩心分析含水饱和度点绘制（SW_CORE .V/V :
        # Water saturation predicted using COREANALYSIS）：凡岩心分析点均以
        # 明显黑色菱形点绘制在本道 Sw 侧，并加独立刻度条（槽位2）
        _swc_col = _find_column(data, ['SW_CORE', 'SWCORE'])
        if _swc_col and has_valid_curves:
            _swc = pd.to_numeric(data[_swc_col], errors='coerce')
            _swc_md = (pd.to_numeric(data['MD'], errors='coerce')
                       if 'MD' in data.columns else pd.Series(depth))
            _m = _swc.notna() & _swc_md.notna() & (_swc >= 0) & (_swc <= 1.5)
            if _m.sum() > 0:
                _sx = _swc_md[_m].values.astype(float)
                _sy = _swc[_m].values.astype(float)
                # 岩心点抽稀：原始采样过密（如 0.076m 间距 5288 点）连片不成"点"，
                # 按 ~0.5m 间隔取样（1:200 图上点距约 2.5mm），岩心点清晰可辨
                _uniq = np.unique(_sx)
                _dstep = (float(np.median(np.diff(_uniq)))
                          if len(_uniq) > 1 else 0.5)
                _thin = max(int(round(0.5 / max(abs(_dstep), 1e-3))), 1)
                # 道内曲线约定 x=测量值、y=深度MD：x=SW_CORE值，y=MD
                _px, _py = _sy[::_thin], _sx[::_thin]
                if not quicklook:
                    # 综合图：与道内 Sw 同为 v/v 线性 0-1
                    ax5.plot(_px, _py, 'D', ms=3.2, mfc='black', mec='white',
                             mew=0.4, linestyle='none', zorder=15, clip_on=True)
                    draw_tick_line(ax5, ALIGNED_POSITIONS_CM[2], 'black')
                    draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[2],
                                     f'{_swc_col} (v/v)', 0, 1, 'black')
                else:
                    # quicklook：与道内 Sw 同为 % 0-100
                    ax5.plot(_px * 100.0, _py, 'D', ms=3.2, mfc='black',
                             mec='white', mew=0.4, linestyle='none',
                             zorder=15, clip_on=True)
                    draw_tick_line(ax5, ALIGNED_POSITIONS_CM[2], 'black')
                    draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[2],
                                     f'{_swc_col} (%)', 0, 100, 'black')
                logger.info('岩心含水饱和度点绘制: %s %d点(抽稀@%.0fcm) %.1f-%.1fm',
                            _swc_col, len(_px), _dstep * 100,
                            _sx.min(), _sx.max())

        if not quicklook:
            # 【2026-10-15 用户要求】综合图合并道右侧：孔隙度反刻度 0.5→0
            # （0 贴右边框，与左边 SW 相对），读 PHI_DISP（非储层归0，仅显示用）
            _por_sw_col = _find_column(data, ['PHI_DISP', 'PHI', 'PHIE', 'POR'])
            if _por_sw_col and has_valid_curves:
                _por_sw = data[_por_sw_col].copy()
                _plot_curve(ax5, _por_sw, depth, 'green', (0.5, 0.0), depth_max,
                            depth_min, curve_height_ratio, header_bottom_y)
                draw_tick_line(ax5, ALIGNED_POSITIONS_CM[0], 'green')
                draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[0],
                                 f'{_por_sw_col} (v/v)', 0.5, 0, 'green')
        else:
            # 【2026-10-10 严格对齐样本】quick look 饱和度道加孔隙度双刻度
            # 【2026-10-12 用户定案】孔隙度刻度条 50→0、与 SW 刻度条分开；
            # 数据为小数(<0.6)自动 ×100；非储层归 0 显示在 0 刻度。
            # 【2026-10-26 R22b 用户修正】画 **PHI_DISP**（非储层归0后的
            # 孔隙度），与 profile 道留白同一列同一口径——此前 POR 优先
            # 导致归零口径不一致（POR 未归零、PHI_DISP 归零）。
            _por_sw_col = _find_column(data, ['PHI_DISP', 'PHI', 'PHIE', 'POR'])
            if _por_sw_col:
                _por_sw = data[_por_sw_col].copy()
                _por_dmax = float(_por_sw.max())
                if _por_dmax <= 0.6:
                    _por_sw = _por_sw * 100.0
                _plot_curve(ax5, _por_sw, depth, 'green', (50.0, 0.0), depth_max,
                            depth_min, curve_height_ratio, header_bottom_y)
                # 【2026-10-14 用户定案】POR→槽位0（PE行），与第4道底部刻度条横向对齐
                draw_tick_line(ax5, ALIGNED_POSITIONS_CM[0], 'green')
                draw_tick_labels(ax5, ALIGNED_POSITIONS_CM[0],
                                 f'{_por_sw_col} (%)', 50, 0, 'green')

        # ========== 孔隙度/渗透率道（quick look 正图第6道） ==========
        # 【2026-10-15 用户要求】综合图孔隙度已并入第5道（Sw+PHI 合并道），
        # 本道仅 quick look 保留：优先画渗透率（PERM），无渗透率列时回退 PHI。
        if quicklook:
            ax6 = axes[IDX_POR2]
            _setup_track_with_header(ax6, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)

            # 【2026-10-12 用户定案】PERM 为对数刻度 0.2-2000 mD；非储层归 0
            # 在对数轴上无法显示 → ≤0 置 NaN 自动断开（仅储层段显示曲线）。
            # 【2026-10-16】候选移除 'K'——K 是能谱钾曲线非渗透率，避免误匹配
            _perm_col = _find_column(data, ['PERM', 'PERMEABILITY', 'PERM_K', 'KH'])
            if _perm_col:
                perm_plot = data[_perm_col].copy()
                # 【2026-10-14 用户要求】渗透率道补刻度：图头对数刻度条(0.2-2000 mD)
                # + 曲线区对数网格线，样式与电阻率道一致
                _plot_log_curve(ax6, perm_plot, depth, 'green', (0.2, 2000.0),
                                depth_max, depth_min, curve_height_ratio, header_bottom_y)
                _draw_log_gridlines(ax6, header_bottom_y, 0.2, 2000.0)
                draw_tick_line(ax6, ALIGNED_POSITIONS_CM[0], 'green')
                # 【2026-10-14 用户定案】图头不显示竖向的4条对数刻度条（1/10/100/1000
                # 小竖线），样式与电阻率道一致：仅首尾 0.2/2000；曲线区对数网格线保留
                draw_tick_labels(ax6, ALIGNED_POSITIONS_CM[0], f'{_perm_col} (mD)',
                                 0.2, 2000, 'green', fontsize_value=7)
            else:
                # 无渗透率列时回退画 PHI（有效孔隙度）
                # 【2026-10-08】优先读 PHI_DISP（logInt 生成：非储层归0，仅显示用）
                por_col = _find_column(data, ['PHI_DISP', 'PHI', 'PHIE', 'POR'])
                if por_col:
                    _plot_curve(ax6, data[por_col], depth, 'green', (0, 0.5), depth_max, depth_min, curve_height_ratio, header_bottom_y)
                    draw_tick_line(ax6, TICK_POSITIONS_CM['upper_middle'], 'green')
                    draw_tick_labels(ax6, TICK_POSITIONS_CM['upper_middle'], f'{por_col} (v/v)', 0, 0.5, 'green')

        # ========== 岩性剖面道（quick look 简化正图不画） ==========
        if not quicklook:
            ax7 = axes[IDX_LITHO_FILL]
            _setup_lithology_track(ax7, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)

        # ========== 沉积相道（quick look 简化正图不画） ==========
        if not quicklook:
            ax8 = axes[IDX_FACIES]
            _setup_facies_track(ax8, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 矿物剖面道 ==========
        ax_profile = axes[IDX_PROFILE]
        # 【2026-10-26 R22】孔隙度留白列与"第5道"曲线**完全同源**。
        # 【2026-10-26 R22b 用户修正】第5道绿曲线应画 **PHI_DISP**（非储层
        # 归0后的孔隙度），quicklook 与综合图同口径——留白列两模式统一
        # PHI_DISP 优先（与第5道同一候选链、同一归零语义）。
        _prof_phi = _find_column(data, ['PHI_DISP', 'PHI', 'PHIE', 'POR'])
        _setup_profile_track(ax_profile, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves, phi_col=_prof_phi)

        # ========== REG 法综合气层指示道 ==========
        try:
            if IDX_REG is not None:
                ax_reg = axes[IDX_REG]
                _reg_scales = {'RTI':[-0.5,1.0],'NDI':[-0.05,0.15],'GSI':[-0.5,2.0],'CGI':[0,1.5]}
                _reg_colors = {'RTI':'#c0392b','NDI':'#2471a3','GSI':'#b9770e','CGI':'#27ae60'}
                _reg_thr = {'RTI':0.20,'NDI':0.05,'GSI':0.5,'CGI':0.6}
                _reg_order = ['RTI','NDI','GSI','CGI']
                _n_reg = len(_reg_order)
                # 图头标签用 figure 坐标绘制（ax_reg 的 y 轴是深度轴，不能用数据坐标）
                _reg_pos = ax_reg.get_position()
                _slot_w = (_reg_pos.x1 - _reg_pos.x0) / float(_n_reg)
                # 【2026-10-23 R21-5】4 个子槽是**横向并列**（x 方向把道宽
                # 四等分），不是纵向堆叠 ⇒ 必须**共用同一条刻度线高度**。
                # 此前每个子槽各取 ALIGNED_POSITIONS_CM[i]（那是"纵向堆叠的
                # 曲线槽位"高度）⇒ 4 个标签被画在 4 个不同 y 上（实测
                # 0.8706/0.8772/0.8837/0.8903），标签阶梯错落、阈值悬空。
                # 改为统一取一个偏上的槽位：阈值画在曲线名正下方仍落在图头区内。
                _reg_slot_idx = min(2, len(ALIGNED_POSITIONS_CM) - 1)
                _reg_hdr_y = get_tick_position_in_header(
                    ALIGNED_POSITIONS_CM[_reg_slot_idx])
                for _i, _cn in enumerate(_reg_order):
                    if _cn not in data.columns: continue
                    _vmin,_vmax = _reg_scales[_cn]
                    _col = _reg_colors[_cn]
                    _x0 = _i/float(_n_reg); _x1 = (_i+1)/float(_n_reg)
                    _vals = pd.to_numeric(data[_cn], errors='coerce')
                    _norm = ((_vals - _vmin)/max(_vmax-_vmin,1e-9)).clip(0,1)
                    _xcurve = _x0 + _norm.values*(_x1-_x0)
                    ax_reg.plot(_xcurve, depth.values, color=_col, linewidth=0.7)
                    if _cn in _reg_thr:
                        _tv = _reg_thr[_cn]
                        if _vmin < _tv < _vmax:
                            _tx = _x0+(_tv-_vmin)/max(_vmax-_vmin,1e-9)*(_x1-_x0)
                            ax_reg.axvline(_tx, color=_col, linestyle='--', linewidth=0.5, alpha=0.6)
                            # 【2026-10-22 用户要求】按当前（暂时）阈值标准，把基线
                            # （阈值虚线）与指示曲线之间填充为指示气层
                            _mask = (_vals > _tv).fillna(False).values
                            if _mask.any():
                                ax_reg.fill_betweenx(depth.values, _tx, _xcurve,
                                                     where=_mask, color=_col,
                                                     alpha=0.28, linewidth=0, zorder=1)
                    # 【2026-10-22 用户要求】图头补曲线名与起止刻度（每个子槽
                    # 各占一行刻度，横线只画在本格范围内，线中央为曲线名+阈值）
                    _fx0 = _reg_pos.x0 + _i*_slot_w
                    _fx1 = _fx0 + _slot_w
                    _y = _reg_hdr_y
                    fig.add_artist(Line2D([_fx0, _fx1], [_y, _y], color=_col,
                                          linewidth=1.0, zorder=6000,
                                          transform=fig.transFigure))
                    # 【2026-10-23 R21】标签压叠修复（两轮）：
                    # ①R21：原写法把"阈值+起止值+曲线名"挤在同一行
                    #   （"0CGI>=0.65"）→ 互相覆盖；且 4 个子槽各取一个
                    #   纵向刻度高度（ALIGNED_POSITIONS_CM[i]）⇒ 标签阶梯
                    #   错落（补丁五已统一为同一高度）。
                    # ②R21-6：REG 道总宽仅约 83pt、4 子槽各约 21pt，
                    #   "曲线名(居中)+起止值(左右内缩)" 三元素同行仍会重叠
                    #   （其它道整道宽≈270px 才放得下）。改为**三行分层**：
                    #   行1 阈值 / 行2 曲线名 / 行3 起止值（贴曲线区）。
                    #   方向以 _hh 符号为准（实测 _hh<0 ⇒ y 越大越靠上）。
                    _lbl = _cn
                    _lbl_x = (_fx0+_fx1)/2.0
                    _hh = header_top_y - header_bottom_y
                    _row = abs(_hh) * 0.075      # 一行的纵向间距
                    # 行2：曲线名（主标签）
                    fig.text(_lbl_x, _y, _lbl, ha='center', va='bottom',
                             fontsize=7, color=_col, weight='bold',
                             transform=fig.transFigure, zorder=1001)
                    # 行1：阈值
                    if _cn in _reg_thr:
                        fig.text(_lbl_x, _y + _row,
                                 f'>{_reg_thr[_cn]:g}', ha='center', va='bottom',
                                 fontsize=6, color=_col,
                                 transform=fig.transFigure, zorder=1001)
                    # 行3/行4：起止刻度值**各占一行**（【R21-7】REG 道 4 子槽
                    # 每槽仅约 21pt，"-0.05"与"0.15"同行必然重叠——实测 NDI
                    # 子槽叠成 "-0.0⑮"；改为 min 一行、max 一行，彻底分开）
                    _m = 0.08
                    fig.text(_fx0+(_fx1-_fx0)*_m, _y - _row, f'{_vmin:g}',
                             ha='left', va='bottom', fontsize=6, color=_col,
                             transform=fig.transFigure, zorder=1001)
                    fig.text(_fx1-(_fx1-_fx0)*_m, _y - 1.5*_row, f'{_vmax:g}',
                             ha='right', va='bottom', fontsize=6, color=_col,
                             transform=fig.transFigure, zorder=1001)
                ax_reg.set_xlim(0,1)
                ax_reg.set_ylim(depth_max, depth_min)
                ax_reg.set_xticks([])
                ax_reg.tick_params(axis='y', left=False, labelleft=False)
                for _sp in ax_reg.spines.values(): _sp.set_visible(False)
                for _k in range(1,4):
                    ax_reg.axvline(_k/4.0, color='gray', linewidth=0.3, alpha=0.5)
                _posr = ax_reg.get_position()
                _vtext(fig, _posr.x0+_posr.width/2, (header_bottom_y+header_top_y)/2,
                       'REG', fontsize=8, weight='bold', color='black')
                logger.info("REG 道: RTI/NDI/GSI/CGI 四条曲线已绘制")
        except Exception as _re2:
            logger.warning("REG 道绘制失败（不影响主图）: %s", _re2)
        
        # ========== 测井解释道 ==========
        ax9 = axes[IDX_INTERP]
        if quicklook:
            # 【2026-10-13 用户要求：正图必须带油气水解释结论】
            # 原实现只画竖排 RESULT 标签，解释段色块/油气水图标/层编号全部缺失，
            # 正图 RESULT 道空白。现在与综合图一致调用 _setup_interpretation_track
            # 绘制解释结论（色块 + fluid_conclusions 图标 + 层编号），
            # 并在图头保留竖排 RESULT 道名（样本版式）。
            _setup_interpretation_track(ax9, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
            _pos9 = ax9.get_position()
            _vtext(fig, _pos9.x0 + _pos9.width / 2,
                   (header_bottom_y + header_top_y) / 2
                   + (header_top_y - header_bottom_y) * 0.12,
                   'RESULT', fontsize=9, weight='bold', color='black')
        else:
            _setup_interpretation_track(ax9, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves)
        
        # ========== 气测道 ==========
        # 【2026-10-22 用户要求】quicklook 也要把气测数据绘制上 → 与综合图同实现
        if has_gas and IDX_GAS is not None:
            ax_gas = axes[IDX_GAS]
            _setup_gas_track(ax_gas, depth_max, depth_min, curve_height_ratio, header_bottom_y, header_top_y)
            
            # 识别气测组分列
            gas_depth_col = _find_column(gas_data, ['MD', 'DEPTH', 'DEP', 'DEPT'])
            gas_curve_cols = _find_gas_columns(gas_data)
            
            if gas_curve_cols:
                # 对齐深度
                gas_depth = gas_data[gas_depth_col] if gas_depth_col else gas_data.iloc[:, 0]
                
                # 判断气测数据是否包含C5+组分（C6/C7/C8/BZ/TL）
                # 包含C5+时绘制C4/C5，否则绘制IC4/NC4/IC5/NC5
                # 【2026-10-15 用户要求】不要MCH曲线——MCH 从 C5+ 判定关键词中移除
                c5plus_keywords = ['C6', 'C7', 'C8', 'BZ', 'TL']
                has_c5plus = any(
                    any(kw in col.upper().strip() for kw in c5plus_keywords)
                    for col in gas_curve_cols
                )
                
                # 分离TG（全烃）和烃类组分
                tg_col = None
                component_cols = []
                for col in gas_curve_cols:
                    col_upper = col.upper().strip()
                    # 【2026-10-16 用户要求】恢复 MCH 绘制（甲基环己烷），
                    # 气测道保留其曲线与刻度槽
                    if col_upper in tg_keywords:
                        tg_col = col
                    else:
                        # 判断是否为C4/C5/IC4/NC4/IC5/NC5相关的列
                        is_c4_total = col_upper in ['C4', 'C4PCT', 'C4%', 'C4_PCT', 'BUTANE']
                        is_c5_total = col_upper in ['C5', 'C5PCT', 'C5%', 'C5_PCT', 'PENTANE']
                        is_ic4_nc4 = any(kw in col_upper for kw in ['IC4', 'NC4'])
                        is_ic5_nc5 = any(kw in col_upper for kw in ['IC5', 'NC5'])
                        is_c1_c3 = any(kw in col_upper for kw in ['C1', 'C2', 'C3'])
                        is_c5plus = any(kw in col_upper for kw in ['C6', 'C7', 'C8', 'BZ', 'TL'])
                        is_mch = 'MCH' in col_upper

                        if has_c5plus:
                            # 有C5+：保留C4/C5/C6/C7/C8/MCH/BZ/TL/C1/C2/C3，排除IC4/NC4/IC5/NC5
                            if is_ic4_nc4 or is_ic5_nc5:
                                continue
                            if (is_c4_total or is_c5_total or is_c1_c3
                                    or is_c5plus or is_mch):
                                component_cols.append(col)
                        else:
                            # 只有C5及以下：保留IC4/NC4/IC5/NC5/C1/C2/C3，排除C4/C5
                            if is_c4_total or is_c5_total:
                                continue
                            if is_ic4_nc4 or is_ic5_nc5 or is_c1_c3 or is_mch:
                                component_cols.append(col)

                # 【2026-10-15 用户要求】气测道全部曲线统一刻度：起始值固定 10，
                # 最大值取 100/1000/10000/100000/1M…中最小的不小于数据最大值
                # （按 TG+组分联合峰值自适应），道头只标起始值和该最大值
                _gas_peak = 0.0
                for _c in ([tg_col] if tg_col else []) + component_cols:
                    _gs = pd.to_numeric(gas_data[_c], errors='coerce')
                    _gm = _gs.where(_gs > 0).max()
                    if pd.notna(_gm) and float(_gm) > _gas_peak:
                        _gas_peak = float(_gm)
                _gas_vmax = 100.0
                while _gas_vmax < _gas_peak:
                    _gas_vmax *= 10.0
                if _gas_peak <= 0:
                    _gas_vmax = 1_000_000.0  # 无有效数据时回退 10-1M

                # 颜色方案：TG用红色粗线，C1-C8用不同颜色区分
                # 【2026-10-15 用户要求】每条曲线使用不同的颜色，不能同色——
                # NC4/NC5 不再与 IC4/IC5 同色
                # 【2026-10-16 用户要求】补 C4/C5 总组分色（DataLoader 模糊匹配
                # 会把 IC4/IC5 重命名为 C4/C5，原表缺键导致两者都落默认蓝色）；
                # MCH 改品红与 TG 红区分
                gas_color_map = {
                    'C1': '#1A7A1A',    # 深绿
                    'C2': '#1A5B9C',    # 深蓝
                    'C3': '#E67E22',    # 橙
                    'C4': '#C0392B',    # 砖红（总丁烷）
                    'IC4': '#9B59B6',   # 紫
                    'NC4': '#E91E63',   # 玫红
                    'C5': '#16A085',    # 青绿（总戊烷）
                    'IC5': '#8B4513',   # 褐
                    'NC5': '#DAA520',   # 金褐
                    'C6': '#34495E',    # 深灰蓝
                    'C7': '#7F8C8D',    # 灰
                    'C8': '#BDC3C7',    # 浅灰
                    'MCH': '#FF00FF',   # 品红（甲基环己烷，与TG红区分）
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
                                       (10, _gas_vmax), depth_max, depth_min,
                                       curve_height_ratio, header_bottom_y, linewidth=2.0)
                        draw_tick_line(ax_gas, ALIGNED_POSITIONS_CM[gas_slot], 'red')
                        draw_tick_labels(ax_gas, ALIGNED_POSITIONS_CM[gas_slot],
                                        f'{tg_col} (ppm)', 10, _gas_vmax, 'red',
                                        fontsize_value=7, is_log=True, draw_tick_marks=False,
                                        end_labels='both', mid_labels='none')
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
                                       (10, _gas_vmax), depth_max, depth_min,
                                       curve_height_ratio, header_bottom_y, linewidth=1.0)
                        draw_tick_line(ax_gas, ALIGNED_POSITIONS_CM[gas_slot], color)
                        draw_tick_labels(ax_gas, ALIGNED_POSITIONS_CM[gas_slot],
                                        f'{col} (ppm)', 10, _gas_vmax, color,
                                        fontsize_value=7, is_log=True, draw_tick_marks=False,
                                        end_labels='both', mid_labels='none')
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
        
        # 【2026-10-10 图版化】标题文本与样式可配（图版 title 段）：
        # quicklook 优先旧式 quicklook_config.title_template，其次 qlpt 图版 title.template；
        # 综合图用 cmpt 图版 title.template（默认 "{well} Composite Log Plot"）。
        if quicklook:
            _winfo = (results.get('las_info') or {}).get('well') or {}
            _start_v = _winfo.get('start_depth', '')
            _stop_v = _winfo.get('stop_depth', '')
            _ql_title_tpl = None
            if quicklook_config and quicklook_config.get('title_template'):
                _ql_title_tpl = quicklook_config['title_template']
            elif _title_cfg.get('template'):
                _ql_title_tpl = _title_cfg['template']
            if _ql_title_tpl:
                try:
                    _title_text = _ql_title_tpl.format(
                        well=well_name, start=_start_v, stop=_stop_v,
                        unit=str(_du).upper())
                except Exception:
                    _title_text = 'Well Logging Interpretation Result Plot'
            else:
                # 【2026-10-10 严格对齐样本】主标题单行（无井名前缀/无换行符；
                # 井名在竖排标题块单独成项，井段在表1 Logged Interval）
                _title_text = 'Well Logging Interpretation Result Plot'
        else:
            _cm_tpl = _title_cfg.get('template') or '{well} Composite Log Plot'
            try:
                _title_text = _cm_tpl.format(well=well_name)
            except Exception:
                _title_text = f"{well_name} Composite Log Plot"
        _title_fs = _title_cfg.get('fontsize') or 16
        _title_fw = _title_cfg.get('fontweight') or 'bold'
        _title_color = _title_cfg.get('color') or '#000000'
        _title_family = _title_cfg.get('family') or 'Microsoft YaHei'
        if not quicklook:
            # 标准综合图：标题居中横排
            fig.text(0.5, title_bottom_y, _title_text, fontsize=_title_fs,
                     fontweight=_title_fw, color=_title_color,
                     ha='center', va='bottom', fontfamily=_title_family)
        else:
            # 【2026-10-10 quick look 严格对齐样本】标题竖排放在页首右侧
            # （样本右上为竖排标题块：比例尺 / 主标题 / 井名 / 公司徽标文字），
            # 在页首主体绘制段（_ql_header_rows 区）统一绘制，此处仅预留。
            pass
        
        # 【2026-10-10 quick look】图头图标：左上 company / 右上 contractor
        # 【2026-10-15 用户定案】标准综合图不绘制业主/承包商图标
        # （对齐 TITAS-31 参照格式；quick look 图标仍在页首"表1 图标行"内
        # 绘制，见 _ql_render_ql_header_rows）。

        # 在图名和道名之间添加井信息表格（4列布局，与图头区曲线区同宽）
        las_info = results.get('las_info', {})
        if las_info:
            well_info = las_info.get('well', {})
            param_info = las_info.get('parameter', {})
            # 【2026-10-14 用户定案】<井名>info.json（快速解释图井信息收集文件）
            # 仅快速解释图使用——标准综合图 las 信息区只用 LAS 自带 ~W/~P 段
            # 信息，此前无条件合并致综合图头显示快速图的 Company/Field/日期等
            # （用户："综合图las信息区也错误，和快速图的信息混淆了"）。
            if quicklook:
                try:
                    _wl_cfg = _load_well_info_json(results)
                    if _wl_cfg:
                        well_info = dict(well_info)
                        well_info.update(_wl_cfg)
                except Exception as _wie:
                    logger.warning('井信息 json 读取失败（不影响出图）: %s', _wie)
            
            # 收集图例数据
            lith_types_raw = []
            if has_enough_curves and 'LITHOLOGY' in data.columns:
                unique_liths = set(data['LITHOLOGY'].dropna().unique())
                lith_types_raw = sorted([str(l).strip().title() for l in unique_liths if str(l).strip()])
            if not lith_types_raw:
                lith_types_raw = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
            # 【2026-10-08 用户要求】套管段不绘制不用符号 → 图例也不含套管
            lith_types = [lt for lt in lith_types_raw if lt.lower() not in ('mixed', 'casing')]
            if not lith_types:
                lith_types = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
            # 【2026-10-14 井信息收集】图例文字优先取 <井名>info.json（逗号分隔）：
            # 岩性空=数据自动提取；沉积微相/解释结论空=程序默认
            def _leg_items(_k, _d):
                _ls = [s.strip() for s in str(well_info.get(_k) or '').split(',') if s.strip()]
                return _ls or list(_d)
            _lith_cfg = [s.strip() for s in str(well_info.get('lithology_legend') or '').split(',') if s.strip()]
            if _lith_cfg:
                lith_types = _lith_cfg
            facies_items = _leg_items('facies_legend', ['Channel', 'Floodplain', 'Delta Front', 'Prodelta'])
            interp_items = _leg_items('interpretation_legend', ['Oil', 'Gas', 'Water'])
            engi_name = (well_info.get('engi', '') or well_info.get('engineer', '')
                         or well_info.get('field_recorded_by', '') or '')
            
            # 图例颜色映射
            # 【2026-10-08 统一符号/颜色】岩性背景色引用 LITH_BG_COLORS（_lith_bg_color）
            # —— 与岩性道/PROFILE道/交汇图同一套，不再各写一份；
            # 解释结论颜色与 FLUID_COLOR（交会图）保持同一套色值。
            # 【2026-10-23 R21】碳酸盐岩改为引用 LITH_BG_COLORS（= 参考图自身
            # 底色 Limestone.png=#97CFF4 / Dolomite.png=#00BFCF）。此前此处是
            # 第二份独立硬编码色表且仍是旧值 #87CEEB/#B0E0E6 ⇒ 与符号区不同色，
            # 在 profile 道/图例露出"淡色不连续色带"。引用统一表后只有一份真值。
            fallback_colors = {'Sandstone': _lith_bg_color('sandstone'),
                              'Shale': _lith_bg_color('shale'),
                              'Mudstone': _lith_bg_color('mudstone'),
                              'Limestone': _lith_bg_color('limestone'),
                              'Dolomite': _lith_bg_color('dolomite'),
                              'Anhydrite': _lith_bg_color('anhydrite'),
                              'Gypsum': _lith_bg_color('gypsum'),
                              'Halite': _lith_bg_color('halite'),
                              'Salt': _lith_bg_color('salt'),
                              'Coal': _lith_bg_color('coal'),
                              'Carbonaceous Shale': _lith_bg_color('carbonaceous shale'),
                              'Pyrite': _lith_bg_color('pyrite'),
                              'Volcanic': _lith_bg_color('volcanic'),
                              'Conglomerate': _lith_bg_color('conglomerate')}
            facies_color_map = {'Channel': 'firebrick', 'Floodplain': 'sandybrown',
                                'Delta Front': 'wheat', 'Prodelta': 'darkolivegreen'}
            # 与 FLUID_COLOR 保持同一套色值；
            # 【2026-10-13】油/气/水主色切换为 fluid_conclusions 图标色系
            interp_color_map = {'Oil': '#006400', 'Gas': '#ff0000', 'Water': '#0066ff',
                                'Dry': '#8a8a8a'}
            
            # 预加载岩性纹理图片
            lithology_image_map = {}
            for lith_name in lith_types:
                img, _ = _load_lithology_symbol(lith_name.lower())
                if img is not None:
                    lithology_image_map[lith_name] = img
            
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
            
            if quicklook:
                # 【2026-10-10 quick look 严格对齐 BET-1 样本版式】
                # 样本页首为 masterlog 老式竖排转置表（label 竖排+value 竖排，列式）：
                #   表1 井位信息 15 字段；表2 钻井液/测量参数 12 字段；
                #   随后 BOREHOLE/CASING 并排 3 列表 + LEGEND 4列×3行 + 免责声明。
                _du_u = str(_du).upper()
                # 甲方固定信息以 quicklook_config 为准（header_fixed 优先于
                # LAS/知识文件提取——甲方更换时改配置即可, 不依赖数据源）
                _qfix = (quicklook_config or {}).get('header_fixed') or {}
                for _k, _v in _qfix.items():
                    if _v and not well_info.get(_k):
                        well_info[_k] = str(_v)
                # 【2026-10-14 用户定案】钻头/套管数据优先取 <井名>info.json
                # （json 字符串可人工修改, 解析回 rows 生效; 空回退 quicklook_config/提取值）
                _qbh = _wellinfo_rec_rows(well_info.get('borehole_record')) or \
                    (quicklook_config or {}).get('borehole_record')
                if _qbh:
                    param_info['borehole_record_rows'] = _qbh
                _qcs = _wellinfo_rec_rows(well_info.get('casing_record')) or \
                    (quicklook_config or {}).get('casing_record')
                if _qcs:
                    param_info['casing_record_rows'] = _qcs
                # 【2026-10-14 用户定案】表 Bit Size 取最后一个钻头尺寸
                # （裸眼段钻头 = 钻头记录最后一段 SIZE）
                _bh_rows_all = _wellinfo_rec_rows(well_info.get('borehole_record')) \
                    or (_qbh if isinstance(_qbh, list) else [])
                if _bh_rows_all:
                    param_info['bit_size'] = str(
                        _bh_rows_all[-1].get('size') or '').strip()
                # 【2026-10-10 用户定案】BH/CS 在第一页右转表不再绘制，移入第二页正放表；
                # 无数据时按图版 bhcs 结构行数生成空白行（表结构不变、数据留白，不编造）
                _bhcs_cfg = (_tpl.get('header') or {}).get('bhcs') or {}
                _nb = int(_bhcs_cfg.get('borehole_rows') or 0)
                _nc = int(_bhcs_cfg.get('casing_rows') or 0)
                _bh_rows = param_info.get('borehole_record_rows') or (
                    [{'size': '', 'from': '', 'to': ''} for _ in range(_nb)] if _nb else [])
                _cs_rows = param_info.get('casing_record_rows') or (
                    [{'size': '', 'from': '', 'to': ''} for _ in range(_nc)] if _nc else [])
                _well_coord = well_info.get('well_coordinate') or ''
                if not _well_coord and well_info.get('latitude') and well_info.get('longitude'):
                    _well_coord = f"Lat: {well_info.get('latitude')} / Long: {well_info.get('longitude')}"
                if not _well_coord and (well_info.get('x_coordinate') or well_info.get('y_coordinate')):
                    _well_coord = (f"X: {well_info.get('x_coordinate', '')} "
                                   f"Y: {well_info.get('y_coordinate', '')}")
                # ---- 表1：井位信息 15 字段（样本字段顺序） ----
                # 【2026-10-10 参数化】字段定义优先读图版 qlpt.json header.fields_v
                # （解析函数 _ql_header_rows_from_cfg），未配时回退下方硬编码默认。
                _ql_rows_cfg1, _ql_rows_cfg2 = _ql_header_rows_from_cfg(
                    _tpl, quicklook_config, well_info, param_info, _du_u)
                if _ql_rows_cfg1 is not None:
                    _ql_rows1 = _ql_rows_cfg1
                    _ql_rows2 = _ql_rows_cfg2 or []
                else:
                    _ql_rows1 = [
                        ('Company', well_info.get('company', '')),
                        ('Field', well_info.get('field_name', '')),
                        ('Well Coordinate', _well_coord),
                        ('Spud Date', well_info.get('spud_date', '')),
                        ('TD Date', well_info.get('td_date', '')),
                        ('Log Date', well_info.get('log_date', '')),
                        ('Process Date', well_info.get('process_date', '')),
                        ('Logged Interval', f"{_fmt_val(well_info.get('start_depth', ''))}-{_fmt_val(well_info.get('stop_depth', ''))} {_du_u}"),
                        ('Ele. KB', well_info.get('elevation_kb', '')),
                        ('Ele. GL', well_info.get('elevation_gl', '')),
                        ('Well Type', well_info.get('well_type', '')),
                        ('Equip. NO.', well_info.get('equipment_no', '')),
                        ('RIG Name', well_info.get('rig_name', '')),
                        ('processed By', well_info.get('processed_by', '')),
                        ('Corrected BY', well_info.get('corrected_by', '')),
                    ]
                    # ---- 表2：钻井液/测量参数 12 字段（样本字段顺序） ----
                    _ql_rows2 = [
                        ('Bit Size', f"{_fmt_val(param_info.get('bit_size', ''))} IN"),
                        ('Type of Fluid in Hole', _last_mud_type(param_info.get('drilling_fluid_type', ''))),
                        # 【2026-10-14 二三轮】去掉图版自带单位拼接（LB/G、C3）：
                        # 密度智能补单位（≤3→g/cc、>7→ppg、带单位原值为主）
                        # 【2026-10-14 二四轮】失水统一单位 L
                        ('Fluid Density / Visvosity',
                         f"{_fmt_mud_density(param_info.get('drilling_fluid_density', ''))} / {_fmt_val(param_info.get('drilling_fluid_viscosity', ''))}"),
                        ('Fluid PH / Fluid Loss',
                         f"{_fmt_val(param_info.get('drilling_fluid_ph', ''))} / {_fmt_fluid_loss(param_info.get('drilling_fluid_loss', ''))}"),
                        ('RM at Meas. Temp.', param_info.get('rm_meas_temp', '')),
                        ('RMF at Meas. Temp.', param_info.get('rmf_meas_temp', '')),
                        ('RMC at Meas. Temp.', param_info.get('rmc_meas_temp', '')),
                        ('RM at BHT', param_info.get('rm_bht', '')),
                        ('Time Since Circulation', param_info.get('time_since_circulation', '')),
                        ('Max. Record Temp.', param_info.get('max_record_temp', '')),
                        ('Field Recorded By', well_info.get('field_recorded_by', '')),
                        ('Field Witnessed By', well_info.get('field_witnessed_by', '')),
                    ]
                _ql_bh_rows = _bh_rows or [{'size': r.get('size'), 'from': r.get('from'),
                                            'to': r.get('to')} for r in []]
                _ql_cs_rows = _cs_rows
                # 无结构化套管记录时回退简表
                if not _ql_cs_rows and param_info.get('current_casing_size'):
                    _ql_cs_rows = [{'size': param_info.get('current_casing_size'),
                                    'from': param_info.get('casing_depth_from', ''),
                                    'to': param_info.get('casing_shoe_depth', '')}]
            else:
                # 【2026-10-14 用户定案】综合图信息表参照 TITAS-31_composite_log
                # 格式：18 字段 4列×5行（井位 12 字段 + 钻参数 6 字段
                # Bit Size/Casing Size/Mud 系列，值取 LAS ~P 参数段）。
                # 行列按 num_cols 网格定位（row_idx=i//num_cols，2026-10-14
                # 错位修复）——此前字段坠入图例区显"不知道从哪儿来"即此根因。
                table_data = [
                    ['Company', well_info.get('company', '')],
                    ['Country', well_info.get('country', '')],
                    ['Contractor', well_info.get('service_company_name', '')],
                    ['Field', well_info.get('field_name', '')],
                    ['Well Name', well_info.get('well_name', '')],
                    ['State/Prov', well_info.get('state_or_province', '')],
                    ['Log Date', well_info.get('log_date', '')],
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
            
            if quicklook:
                # 【2026-10-10 单页式 quick look 严格对齐样本】
                # 页首为竖排转置表（表1 井位 15 字段 + 表2 测量 12 字段）
                # + BOREHOLE/CASING 并排 3 列表 + LEGEND 4列×3行 + 免责声明。
                # num_cols/num_rows 仅对非 quicklook 的 4 列横排表有意义；
                # quicklook 走 _ql_vtable 竖排，table_data 置空占位。
                table_data = []
                num_cols = 2
                _sec_rows_set = {'BOREHOLE RECORD', 'CASING RECORD'}
                _label_frac = 0.34
                num_rows = 1
            else:
                num_cols = 4
                _sec_rows_set = set()
                _label_frac = 0.4
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
            # 【2026-10-10 修复】quick look 竖排表（表1/表2/BHCS）各自画完整外框，
            # 此处不再画贯穿整个页首区的左右框线——否则会形成"多一条贯穿长竖线"
            # （用户反馈：表内竖线长度不齐，第1条贯穿、其余只到部分行）。
            if not quicklook:
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
            # 列分隔线（标准表画各列分隔线；quick look 竖排表由 _ql_vtable 内部画）
            if not quicklook:
                for col_idx in range(1, num_cols):
                    x_pos = table_x_left + col_idx * cell_width
                    fig.add_artist(Line2D([x_pos, x_pos], [table_y_start, table_y_end],
                                          color='black', linewidth=0.5, transform=fig.transFigure))
            # 总行数（数据行 + 图例行6行）
            total_rows = num_rows + 6  # 5数据行 + 6图例行(3部分×2行)
            cell_height = table_height_ratio / total_rows
        
            # 行分隔线（只绘制数据行之间）
            if not quicklook:
                for row_idx in range(1, num_rows):
                    y_pos = table_y_start - row_idx * cell_height
                    fig.add_artist(Line2D([table_x_left, table_x_right], [y_pos, y_pos], 
                                          color='black', linewidth=0.5, transform=fig.transFigure))
        
            # 绘制数据行
            for i, (label, value) in enumerate(table_data):
                # 【2026-10-14 错位修复】按 num_cols 列网格的行号定位
                # （row_idx = i // num_cols）——原按项序号 i 逐项递减
                # cell_height，第 2 行起全部下坠越界，与图例行/道区重叠
                # （Bit Size/Mud 等字段混进图例区的直接根因）。
                col_idx = i % num_cols
                row_idx = i // num_cols
                y_pos = table_y_start - (row_idx + 0.5) * cell_height
                if quicklook:
                    # 【2026-10-10 单页式 quick look 严格对齐样本】竖排转置表在下方
                    # _ql_render_ql_header_rows 统一绘制（表1/表2 竖排 + BOREHOLE/CASING
                    # 并排 3 列表）；此处的 table_data 仅用于占位布局（row 计数）。
                    pass
                else:
                    x_start = table_x_left + col_idx * cell_width
                    fig.text(x_start + 0.003, y_pos, label, fontsize=8, ha='left', va='center',
                            fontfamily='Microsoft YaHei', color='black')
                    fig.text(x_start + cell_width * 0.4, y_pos, str(value), fontsize=8, ha='left', va='center',
                            fontfamily='Microsoft YaHei', color='black')

            # ========== 【2026-10-10 quick look 严格对齐样本】页首主体竖排绘制 ==========
            # 页首区 y 从 table_y_start 向下，按样本比例划分：
            #   右侧 22% 竖排标题块（比例尺/主标题/井名/公司徽标文字，样本右上）
            #   左侧表区：表1 井位竖排表（~34%）| 表2 测量竖排表（~30%）
            #   | 免责声明（~7%）| BOREHOLE/CASING 并排 3 列表（~15%）| LEGEND（~16%）
            if quicklook:
                # ========== 【2026-10-10 整表右转90°】页首整体表 ==========
                # 用户定案："开头是个右转90度的表，可以先把它放正，绘制完表之后再右转90度"。
                # 整表行序（放正时从上到下）：图标行（表内第一行，company左/contractor右）
                # → 井名大字 → 图名 Well Logging Interpretation Result Plot → 比例尺
                # → 表1 井位 15 字段 → 表2 测量 12 字段 → BOREHOLE/CASING →
                # 免责声明 → LEGEND 色块；渲染后 PIL 顺时针旋转 90°（字头朝右）。
                _hh = table_y_start - table_y_end
                _ql_hdr_cfg = (quicklook_config or {}).get('header') or (_tpl or {}).get('header') or {}
                _ql_scale_text = f"1:{_scale_den} ({_du_u} MD)"
                if str(_du).upper() == 'M':
                    _ql_scale_text = f"1:{_scale_den} (MD)"
                _ql_disp_name = (results.get('display_name') or well_info.get('display_name')
                                 or well_name)
                # 图例项（甲方可变：quicklook_config > 图版 legend.items > 内置默认 12 类）
                if quicklook_config and quicklook_config.get('legend_items'):
                    _ql_fluid = [(it['label'], it.get('color', '#bdbdbd'))
                                 for it in quicklook_config['legend_items']]
                elif _tpl and _tpl.get('legend', {}).get('items'):
                    _ql_fluid = [(it.get('label', ''), it.get('color', '#bdbdbd'))
                                 for it in _tpl['legend']['items'] if it.get('label')]
                else:
                    _ql_fluid = [
                        ('Gas', '#d73027'), ('Poor Gas', '#f39b7f'),
                        ('Gas & Water', '#e67e22'), ('Gas-bearing Water', '#fdbf6f'),
                        ('Oil', '#1a9850'), ('Poor Oil', '#a6d96a'),
                        ('Oil & Water', '#8c6bb1'), ('Oil-bearing Water', '#c994c7'),
                        ('Gas & Oil', '#f4a582'), ('Water', '#00a8f8'),
                        ('Possible Hydrocarbon', '#ffd700'),
                    ]
                # 【2026-10-12 修复】LEGEND 双色块：复合流体项（Gas&Water 等）样本为
                #   双色块并列（红+蓝/绿+蓝/红+绿），第三页正放表按 (label, color, color2)
                #   渲染；旧版页内图例 legend_sections 仍用 2 元组 _ql_fluid。
                if quicklook_config and quicklook_config.get('legend_items'):
                    _ql_fluid2 = [(it['label'], it.get('color', '#bdbdbd'),
                                   it.get('color2')) for it in quicklook_config['legend_items']]
                elif _tpl and _tpl.get('legend', {}).get('items'):
                    _ql_fluid2 = [(it.get('label', ''), it.get('color', '#bdbdbd'),
                                   it.get('color2'))
                                  for it in _tpl['legend']['items'] if it.get('label')]
                else:
                    _ql_fluid2 = [(f, c, None) for f, c in _ql_fluid]
                _ql_legend_title = (quicklook_config or {}).get(
                    'legend_title') or (_tpl or {}).get('legend', {}).get(
                    'title') or 'LEGEND OF WELL-LOGGING RESULT'
                # 【2026-10-14 井信息收集】免责声明优先取 <井名>info.json（非空值优先）
                _ql_disclaimer = str(well_info.get('disclaimer') or '').strip() or \
                    (quicklook_config or {}).get(
                    'disclaimer') or (_tpl or {}).get('legend', {}).get(
                    'disclaimer') or ''
                # 页首区尺寸（figure 分数 → inch）
                # 【2026-10-13 用户定案】表1/表2/LEGEND 与解释正图宽度一致：
                #   页首区宽不再取 table_width*_fig_w（窄于正图），而是直接取
                #   正图 figsize 全宽 _fig_w（默认 24in = 3600px @150dpi），
                #   三张表与正图输出像素宽度完全一致，可纵向拼接为完整一张图。
                _hdr_w_in = _fig_w
                _hdr_h_in = _hh * total_height_inch
                # 放正绘制 → 右转 90° → 第一页（右转表单独一页，不再铺入正图页）
                # 【2026-10-12 三页拆分】页1=右转表（信息表）；免责声明移至第二页
                # BH/CS 表顶部、LEGEND 移至第三页正放表（正图上方）→ 此处均传空。
                _hdr_pil = _ql_rotated_header(
                    _ql_rows1, _ql_rows2, _ql_disp_name, _title_text, _ql_scale_text,
                    company_logo, contractor_logo,
                    # 【2026-10-10 用户定案】BOREHOLE/CASING 不在第一页右转表面上，
                    # 已移至第二页正放表（_save_ql_bhcs_page 输出）。
                    bh_rows=None, cs_rows=None,
                    disclaimer=None,
                    legend_title=None, legend_items=[],
                    header_w_in=_hdr_w_in, header_h_in=_hdr_h_in,
                    fig_cfg=_fig_cfg)
                logger.debug("quick look 第一页右转表已生成 (%.1f x %.1f in)",
                            _hdr_w_in, _hdr_h_in)
                # 【2026-10-12 第三个表格】LEGEND 正放表（标题 + 3行×4列图例），
                # 与正图拼接为第三页（正图上方）。
                # 【2026-10-12 修复】表宽与页1 转置表一致（用户：页3 与页2 对齐放大）
                _ql_legend_pil = _render_ql_legend_pil(
                    _ql_legend_title, _ql_fluid2, w_in=_hdr_w_in, h_in=2.8,
                    fig_cfg=_fig_cfg)

        
            # ========== 图例绘制（在数据行下方，使用3部分×2行，所有方块为统一大小正方形） ==========
            # 数据行底部
            data_bottom_y = table_y_start - num_rows * cell_height
            # 图例区域总高度
            legend_total_height = data_bottom_y - table_y_end
        
            if quicklook:
                # 【2026-10-10 quick look】LEGEND OF WELL-LOGGING RESULT —— 流体类别
                # 默认 BET-1 masterlog 12 类（参照 BET-1_8.5IN_SLAM_Res_MD200_20261003.pdf）;
                # 甲方格式不同时由 quicklook_config['legend_items'] 覆盖
                # （图例顺序/颜色/类别随甲方变化）
                if quicklook_config and quicklook_config.get('legend_items'):
                    _ql_fluid = [(it['label'], it.get('color', '#bdbdbd'))
                                 for it in quicklook_config['legend_items']]
                elif _tpl and _tpl.get('legend', {}).get('items'):
                    # 【2026-10-10 图版化】甲方格式变化改 qlpt.json legend.items 即可
                    _ql_fluid = [(it.get('label', ''), it.get('color', '#bdbdbd'))
                                 for it in _tpl['legend']['items'] if it.get('label')]
                else:
                    _ql_fluid = [
                        ('Gas', '#d73027'), ('Poor Gas', '#f39b7f'),
                        ('Gas & Water', '#e67e22'), ('Gas-bearing Water', '#fdbf6f'),
                        ('Oil', '#1a9850'), ('Poor Oil', '#a6d96a'),
                        ('Oil & Water', '#8c6bb1'), ('Oil-bearing Water', '#c994c7'),
                        ('Gas & Oil', '#f4a582'), ('Water', '#00a8f8'),
                        ('Possible Hydrocarbon', '#ffd700'),
                    ]
                _ql_legend_title = (quicklook_config or {}).get(
                    'legend_title') or (_tpl or {}).get('legend', {}).get(
                    'title') or 'LEGEND OF WELL-LOGGING RESULT'
                legend_sections = [
                    (_ql_legend_title, [f for f, _ in _ql_fluid], None,
                     dict(_ql_fluid), 'color'),
                ]
            else:
                # 图例区域划分：3部分（岩性、沉积相、解释），每部分2行
                legend_sections = [
                    ('Litho:', lith_types, lithology_image_map, fallback_colors, 'texture'),
                    ('Facies:', facies_items, None, facies_color_map, 'color'),
                    ('Interp:', interp_items, None, interp_color_map, 'color'),
                ]
            n_sections = len(legend_sections)
            section_height = legend_total_height / n_sections  # 每部分高度
            row_height = section_height / 2  # 每行高度
            if quicklook and legend_sections and legend_sections[0][1]:
                # 【2026-10-10 quick look】图例项数随甲方配置可变，
                # 每行最多6个，行数动态分配（如 12 项=2行、16 项=3行）；
                # 标题独占 1 行；图例区占 80% 高度，底部 20% 留给免责声明
                _ql_n = len(legend_sections[0][1])
                _ql_rows = max(3, (_ql_n + 5) // 6 + 1)
                section_height = legend_total_height * 0.80
                row_height = section_height / _ql_rows
        
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
                # 【2026-10-10 quick look】行数动态：每行最多6个图例项
                _sec_rows = max(2, (len(items) + 5) // 6)
                if quicklook:
                    # 【2026-10-10 整表右转90°】图例已并入页首旋转表
                    # （_ql_rotated_header 内 LEGEND 段），主图不再重复绘制。
                    pass
                # 【2026-10-10 严格对齐样本】免责声明在页首最底部（LEGEND 之后）
                if quicklook:
                    # 【2026-10-10 整表右转90°】免责声明已并入页首旋转表
                    # （_ql_rotated_header 内免责段），主图不再重复绘制。
                    pass
                else:
                    for row_in_sec in range(_sec_rows):
                        # 行中心y坐标
                        y_center = data_bottom_y - (sec_idx * _sec_rows + row_in_sec + 0.5) * row_height
                    
                        # 该行应显示的图例项（每行最多6个）
                        items_in_row = items[row_in_sec * 6 : (row_in_sec + 1) * 6]
                    
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
                            
                                # 绘制符号方块
                                if draw_type == 'texture' and name:
                                    # 【2026-10-19】微框 motif 模式：固定 4×2 格
                                    # 单符号（40×7.5pt 小方块内按像素铺排会退化
                                    # 成不可辨认的碎片——"不知道是哪儿来的"）
                                    draw_lithology_pattern_fig(
                                        fig, name, x_pos, y_center - sub_sq_h / 2,
                                        sub_sq_w, sub_sq_h,
                                        bg_color=_lith_bg_color(name), zorder=6002,
                                        motif=True)
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

            # ========== quick look 免责声明（竖排表段已绘制；此处禁用旧短文本） ==========
            # 【2026-10-10 严格对齐样本】免责声明已在 _ql_disc_text 竖排页首段
            # 横排绘制（样本原文两行），不再重复绘制旧短文本。
            if quicklook:
                pass

            # ========== 绘制分隔横线 ==========
            # 1. 数据行与图例之间的分隔线（图例顶部）
            fig.add_artist(Line2D([table_x_left, table_x_right], [data_bottom_y, data_bottom_y],
                                  color='black', linewidth=0.5, transform=fig.transFigure))
            # 2. Interp图例项与Eng信息之间的分隔线（quick look 模式 12 类流体单部分，不画）
            if not quicklook:
                # Interp部分第2行（Eng信息）与第1行之间的边界 = data_bottom_y - 5 * row_height
                interp_sep_y = data_bottom_y - 5 * row_height
                fig.add_artist(Line2D([table_x_left, table_x_right], [interp_sep_y, interp_sep_y],
                                  color='black', linewidth=0.5, transform=fig.transFigure))
    
        # 必须先绘制一次才能确保布局正确
        fig.canvas.draw()
        # 【2026-10-30 R52】出图前图面纹理 QC（报告不阻断）：兜底抓门禁盲区/
        # GUI 路径回归，异常窗写 warning 日志并记入 results
        try:
            _qc_problems = figure_texture_qc(fig, well_name=well_name, data=data)
            if _qc_problems:
                results['render_qc_warnings'] = _qc_problems
        except Exception as _qce:
            logger.warning('图面纹理 QC 执行失败(跳过): %s', _qce)

        # 保存文件
        if 'output_dir' in results:
            well_output_dir = Path(results['output_dir'])
        else:
            well_output_dir = Path('output') / well_name
        
        well_output_dir.mkdir(exist_ok=True, parents=True)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        # 【2026-10-14 用户定案】出图只出一次、只交付单页 PDF：三种出图
        # （综合图/快速解释图/交汇图）统一只在输出目录保留一个 PDF 成果。
        # 【2026-10-20 用户定案（RASHIDPUR_13）】quick look 不生成 PNG：
        # 三页全部内存渲染（BytesIO/PIL Image），PyMuPDF 直接产 PDF，
        # 全程不落任何 PNG 文件（综合图仍走临时 PNG→PDF 旧路径）。
        _tmp_dir = None
        _main_img = None
        if quicklook:
            output_path = None       # 无 PNG 文件；兜底名见 PDF 失败分支
        else:
            _tmp_dir = Path(tempfile.mkdtemp(prefix=f'{well_name}_plot_'))
            output_path = _tmp_dir / f'{well_name}_composite_log_{timestamp}.png'
        
        # 【2026-10-09 去除程序生成水印】matplotlib 默认在 PNG 元数据写入
        # "Software = Matplotlib version..., https://matplotlib.org/"，在
        # Windows 文件属性"详细信息-程序名称"等处显示为程序生成标记；
        # metadata={'Software': None} 可完全去除该字段（实测键值均不写入）。
        # 【2026-10-10 图版化】输出分辨率可配（图版 figure.dpi，默认150）
        _dpi = _fig_cfg.get('dpi') or 150

        # 【2026-10-12】页1：右转表（quicklook 时）——内存保留 PIL Image，不落 PNG
        _p1_img = None
        if quicklook:
            try:
                _p1_img = _hdr_pil.convert('RGB')
                results['header_page'] = _p1_img
                logger.debug('quick look 第一页右转表已渲染(内存): %dx%d',
                             _p1_img.width, _p1_img.height)
            except Exception as _p1e:
                logger.warning('quick look 第一页右转表渲染失败: %s', _p1e)

        if quicklook:
            # 【2026-10-20 用户定案】页3 不写 PNG：savefig → BytesIO → PIL Image
            import io as _io
            _buf = _io.BytesIO()
            plt.savefig(_buf, format='png', dpi=_dpi, metadata={'Software': None})
            _buf.seek(0)
            from PIL import Image as _PIL3
            _PIL3.MAX_IMAGE_PIXELS = None
            _main_img = _PIL3.open(_buf).convert('RGB')
            _buf.close()
        else:
            plt.savefig(output_path, dpi=_dpi, metadata={'Software': None})

        # 【2026-10-12】页3：LEGEND 正放表 + 正图主体拼接（quicklook 时）
        # 【2026-10-14】同时裁出道头区块（1-8道曲线名/刻度整块）作 footer 用
        # 【2026-10-20】拼接全程内存（输入/输出均为 PIL Image）
        _hdr_blk = None
        if quicklook:
            try:
                _main_img, _hdr_blk = _combine_ql_legend_main(
                    _ql_legend_pil, _main_img, _hdr_h_in,
                    dpi=_dpi, blk_y0=header_bottom_y, blk_y1=header_top_y)
            except Exception as _ce:
                logger.warning('quick look 第三页 LEGEND+正图拼接失败, 保留正图: %s', _ce)

        plt.close(fig)

        # 【2026-10-10 新增】quick look 第二页：BOREHOLE/CASING 正放表（用户定案：
        # 钻头/套管数据在第二页、是另一个正放的表、不在第一页右转表面上）
        # 【2026-10-12】免责声明移至本页顶部第一行（样本 BET-1 结构）
        if quicklook:
            try:
                _bhcs_img = _save_ql_bhcs_page(
                    well_name, _ql_bh_rows, _ql_cs_rows, _tmp_dir,
                    timestamp, fig_cfg=_fig_cfg, disclaimer=_ql_disclaimer,
                    tbl_w_in=_hdr_w_in, du=_du)
                if _bhcs_img is not None:
                    results['bhcs_page'] = _bhcs_img
            except Exception as _be:
                logger.warning('quick look 第二页 BH/CS 表渲染失败: %s', _be)

        # 【2026-10-13 用户定案】完整一张图：页1+页2+页3 纵向拼接为一张
        # 宽度一致的长图，并输出单页 PDF（对齐样本格式，不再分 3 页）。
        # 【2026-10-20 用户定案】拼接与 PDF 产出全程内存，仅 PDF 落输出目录。
        _final_out = None
        if quicklook:
            _full_png, _full_pdf = _assemble_ql_full(
                well_name, results.get('header_page'), results.get('bhcs_page'),
                _main_img, _tmp_dir, timestamp, dpi=_dpi,
                footer_path=_hdr_blk, pdf_out_dir=well_output_dir)
            if _full_pdf:
                results['quicklook_full_pdf'] = _full_pdf
                _final_out = _full_pdf
            for _k in ('header_page', 'bhcs_page', 'quicklook_full'):
                results.pop(_k, None)

        # 【2026-10-13 用户要求】综合图（非 quicklook）同样输出单页 PDF
        #（页面=图面物理尺寸 px/dpi*72pt，与快速解释整图一致）
        if not quicklook:
            # 【2026-10-14 用户定案】综合图尾部也追加与 header 一致的 footer
            #（道头区块），再输出单页 PDF
            try:
                _append_header_footer(str(output_path),
                                      header_bottom_y, header_top_y)
            except Exception as _cfe:
                logger.warning('综合图 footer 处理失败(跳过): %s', _cfe)
            _comp_pdf = well_output_dir / f'{well_name}_composite_log_{timestamp}.pdf'
            _pdf_out = _save_single_page_pdf(str(output_path), str(_comp_pdf),
                                             dpi=_dpi)
            if _pdf_out:
                results['composite_log_pdf'] = _pdf_out
                _final_out = _pdf_out

        # 【2026-10-14】PDF 失败兜底：避免零交付。
        # quicklook（内存流程）：正图 PIL Image 存为输出目录 PNG（唯一落盘场景）；
        # 综合图：临时正图 PNG 移入输出目录。
        if _final_out is None:
            try:
                if quicklook and _main_img is not None:
                    _fb = well_output_dir / f'{well_name}_qlplot_{timestamp}.png'
                    _main_img.save(str(_fb))
                    _final_out = str(_fb.absolute())
                elif output_path is not None:
                    _fb = well_output_dir / output_path.name
                    shutil.move(str(output_path), str(_fb))
                    _final_out = str(_fb.absolute())
                else:
                    _final_out = None
                if _final_out:
                    logger.warning('PDF 生成失败, 已保留正图 PNG: %s', _final_out)
            except Exception as _mve:
                logger.warning('正图 PNG 保留失败: %s', _mve)
        # 清理中间产物临时目录
        if _tmp_dir:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

        # 【2026-10-14】最终保存消息与出图格式匹配（综合测井图/快速解释图），
        # 且指向最终交付文件（单页 PDF）
        _kind = '快速解释图' if quicklook else '综合测井图'
        logger.info(f"{_kind}已保存: {Path(str(_final_out)).absolute()}")
        results['visualization_results'] = {'well_log_composite': str(Path(str(_final_out)).absolute())}
        
        return str(Path(str(_final_out)).absolute())
        
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
    
    # 绘制深度刻度线（只在曲线区）——三档100/10/1(米)/100/10/2(英尺)统一入口（2026-10-15）
    _draw_depth_gridlines(ax, depth_min, depth_max, header_bottom_y)


def _draw_log_gridlines(ax, header_bottom_y, log_lo=0.2, log_hi=2000.0):
    """【2026-10-14 新增】曲线区对数网格线（次/主刻度竖线），样式与电阻率道一致。

    次刻度：每个数量级内 2-9（含起点 log_lo 对应的 0.2 等）；
    主刻度：1/10/100/1000 加粗。只画曲线区（0 ~ header_bottom_y）。
    """
    fig = ax.figure
    pos = ax.get_position()
    ax_left, ax_right = pos.x0, pos.x1
    log_min, log_max = np.log10(log_lo), np.log10(log_hi)
    _minor = [np.log10(i / 10.0) for i in range(3, 11)]          # 0.3-1.0
    _minor += [np.log10(i) for i in range(2, 10)]                # 2-9
    for _dec in (10, 100, 1000):
        _minor += [np.log10(i * _dec) for i in range(2, 10)]     # 20-90 ...
    for lv in _minor:
        if log_min <= lv <= log_max:
            xp = ax_left + (ax_right - ax_left) * (lv - log_min) / (log_max - log_min)
            ax.plot([xp, xp], [0, header_bottom_y], transform=fig.transFigure,
                    color='black', linewidth=0.6, zorder=500)
    for lv in (np.log10(1), np.log10(10), np.log10(100), np.log10(1000)):
        if log_min <= lv <= log_max:
            xp = ax_left + (ax_right - ax_left) * (lv - log_min) / (log_max - log_min)
            ax.plot([xp, xp], [0, header_bottom_y], transform=fig.transFigure,
                    color='black', linewidth=1.0, zorder=500)


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
    
    # 绘制深度刻度线（只在曲线区）——三档100/10/1(米)/100/10/2(英尺)统一入口（2026-10-15）
    _draw_depth_gridlines(ax, depth_min, depth_max, header_bottom_y)


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
    
    # 绘制深度刻度线（只在曲线区）——三档100/10/1(米)/100/10/2(英尺)统一入口（2026-10-15）
    _draw_depth_gridlines(ax, depth_min, depth_max, header_bottom_y)


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
    """单位回退：仅在调用方未传入单位时使用，默认按米处理。

    正常路径：单位来自 LAS 文件 ~C 区深度曲线（如 DEPT.FEET）的 unit 字段，
    由 logInt 加载 LAS 后通过 set_depth_unit('ft'/'m') 传入；
    不再按深度数值猜测（超深米井 >4500 m 曾被误判为英尺，该逻辑已废弃）。
    """
    return 'm'


def _setup_depth_track(ax, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y):
    """设置深度道（【2026-10-15】横线三档100/10/1，公制每10m标深度、英制每20ft标深度）"""
    unit = DEPTH_UNIT
    if unit == 'auto':
        unit = _detect_depth_unit(depth_min, depth_max)
    if unit == 'ft':
        unit_label = 'Depth (ft)'
    else:
        unit_label = 'Depth (m)'
    # 【2026-10-15 用户定案】深度刻度：横线三档公制100/10/1、英制100/10/2，
    # 公制每10m标深度、英制每20ft标深度
    major_step, minor_step, _fine_step, label_step = _tpl_depth_steps(unit)
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
    # 【2026-10-16 用户要求】Depth 与单位分两行显示——"Depth (m)" 单行时
    # 括号与道外框线重叠
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.72,
            'Depth', ha='center', va='center', fontsize=11, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.50,
            f'({unit})', ha='center', va='center', fontsize=9, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)
    # 比例尺在单位行下方（【2026-10-13】模板化：ft 默认 1:240、m 默认 1:200，
    # 图版 figure.curve_scale 可配 1:480 / 1:500 等）
    _scale_den_txt = _tpl_curve_scale_den(unit)
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.26,
            f'1:{_scale_den_txt}', ha='center', va='center', fontsize=10, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)

    # 深度数字标签（用户2026-10-15定案：公制每10m、英制每20ft标注一个深度）
    base = (int(depth_min) // label_step) * label_step
    major_ticks = np.arange(base, depth_max + label_step, label_step)
    major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
    label_x_center = ax_center

    for depth_val in major_ticks:
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        if fig_y < header_bottom_y - 0.01:
            ax.text(label_x_center, fig_y, f'{depth_val:.0f}', ha='center', va='center',
                    fontsize=11, fontfamily='Microsoft YaHei', transform=fig.transFigure, zorder=501)

    # 次刻度：短横线（每10m/每10ft），不标数字
    sub_base = (int(depth_min) // minor_step) * minor_step
    minor_ticks = np.arange(sub_base, depth_max + minor_step, minor_step)
    minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
    for depth_val in minor_ticks:
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        if fig_y >= header_bottom_y - 0.005:
            continue
        ax.plot([ax_left, ax_left + (ax_right - ax_left) * 0.18], [fig_y, fig_y],
                color='black', lw=0.5, transform=fig.transFigure, zorder=500, clip_on=False)


def _draw_track_name(fig, ax_left, ax_right, header_top_y, header_bottom_y, track_name, display_name):
    """在图头区绘制道名（用于无有效曲线时的占位显示）"""
    header_mid_y = (header_top_y + header_bottom_y) / 2
    header_mid_x = (ax_left + ax_right) / 2
    fig.text(header_mid_x, header_mid_y, display_name, ha='center', va='center',
             fontsize=7, fontfamily='Microsoft YaHei', transform=fig.transFigure,
             color='gray', style='italic')


def _setup_lithology_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """设置岩性剖面道（有效曲线不足3条的井段留空白）"""
    # 【2026-10-20 过界修复】xlim 必须与符号宽度 SYMBOL_X_EXTENT(0.8) 一致：
    # 旧 xlim(0,0.5) 而符号画 0→0.8，ref/image 分支的显式 set_clip_path
    # 矩形(0→0.8)绕过 axes 裁剪 → 岩性符号越界 60% 道宽压到沉积相道上
    ax.set_xlim(0, SYMBOL_X_EXTENT)
    ax.set_ylim(depth_max, depth_min)
    ax._lith_qc = 'lith'   # 【R52】图面纹理 QC 标记
    # 【2026-10-30 R49 防复发】全图统一瓦片锚：两道所有
    # draw_lithology_pattern 调用传同一锚点，行线跨道对齐；
    # image/vector 类不再按段顶重启相位
    _tile_anchor = float(depth_min)
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
    # 【2026-10-08 用户要求】套管段不绘制不用符号 → 图例也不含套管
    lith_types = [lt for lt in lith_types if lt.lower() not in ('mixed', 'casing')]
    if not lith_types:
        lith_types = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
    
    # ========== 曲线区：使用符号图片填充岩性 ==========
    if has_enough_curves and 'LITHOLOGY' in data.columns:
        # 岩性值到符号的映射（统一转小写）
        lithology_symbol_map = {k.lower(): k for k in lith_types}
        
        # 分组：连续相同岩性的深度段
        # 【2026-10-30 R49 防复发】游程分段收敛到唯一分段源
        # _contiguous_lith_runs（与 PROFILE 道特殊岩性整带共用），
        # 消除两道各自手写 while 游程的分叉隐患
        n = len(data)
        _valid = ((data['VALID_CURVES_COUNT'] >= 3).tolist()
                  if 'VALID_CURVES_COUNT' in data.columns else None)
        raw_segments = []  # [(start_md, end_md, lith_key), ...]
        for _a, _b, _li in _contiguous_lith_runs(
                [str(v).lower() for v in data['LITHOLOGY']], _valid):
            raw_segments.append((float(data.iloc[_a]['MD']),
                                 float(data.iloc[min(_b + 1, n - 1)]['MD']),
                                 _li))
        
        # 第二步：合并薄层到相邻大层
        merged_segments = _merge_thin_layers(raw_segments)
        
        # 第三步：绘制合并后的段
        for seg_start_md, seg_end_md, lith_key in merged_segments:
            _draw_lithology_tiles(ax, lith_key, seg_start_md, seg_end_md,
                                  tile_origin=_tile_anchor)


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
            'sandy_deposit': 'wheat',
            'transition': 'khaki',
            'muddy_deposit': 'darkolivegreen',
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



def _setup_profile_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves, phi_col=None):
    """矿物比例堆叠 profile 道：储层按 (1-φ) 归一、非储层主矿物填满、孔隙度区留白；
    图头图例小方框（砂岩点/泥岩线/灰岩砖），孔隙度图例空白。

    【2026-10-26 R22】phi_col：孔隙度留白列显式指定——调用方按"第5道曲线
    实际画的列"传入，保证留白边界与第5道曲线逐点一致（此前固定 PHI_DISP，
    quicklook 两列有 581 行 >0.005 差异 ⇒ 用户反馈"孔隙度台阶明显"）。
    【2026-10-26 R22b 用户修正】第5道绿曲线改画 PHI_DISP（非储层归0孔隙度），
    两模式候选链统一 PHI_DISP→PHI→PHIE→POR。
    矿物重调：合格点矿物带按 scale=total/s 归一到 (1-φ)——φ 取 PHI_DISP
    归零口径 ⇒ 非储层段 φ=0、矿物铺满整带，矿物+孔隙度恒=1。"""

    PROFILE_MINERALS = [
        # 【2026-10-08 统一符号】颜色统一引用 LITH_BG_COLORS（_lith_bg_color）——
        # 与岩性道/图例/交汇图完全同一套（此前泥岩#7CC47C/砂岩#FFE066 与统一表
        # #228B22/#FFFF00 不一致）
        # 【2026-10-14 十九轮定案】全图英文一致：图头图例标签改英文
        # （cname 仅第7道图头图例使用，原地改英文安全）
        # 【2026-10-16 用户要求】矿物源优先 VOL_* 元素测井反演列（与岩性识别
        # 同源），解决 V* 矿物列失效段（如蚀变火成岩段 VClay 恒1.0）导致
        # profile 道与岩性道不一致；白云岩符号=错缝斜砖块
        (['VOL_ILLITE', 'VClay', 'VSH'], 'shale',     'Shale',     _lith_bg_color('shale'),     'ref'),
        (['VQuartz', 'VSAND'],           'sandstone', 'Sandstone', _lith_bg_color('sandstone'), 'ref'),
        (['VOL_CALCITE', 'VCalcite'],    'limestone', 'Limestone', _lith_bg_color('limestone'), 'ref'),
        (['VOL_DOLOM', 'VDolomite'],     'dolomite',  'Dolomite',  _lith_bg_color('dolomite'),  'ref'),
    ]

    # 【2026-10-19 机制化】删除 _sym_dots/_sym_dash/_sym_brick/_SYM 死代码：
    # 早期 profile 道图例自带一套 3x3 点阵几何（从未被调用），与统一核心
    # 并存即分叉隐患；图例统一走 draw_lithology_pattern_fig（同一几何核心）。
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax._lith_qc = 'profile'   # 【R52】图面纹理 QC 标记
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    ax.tick_params(axis='y', which='both', left=False, right=False,
                   labelleft=False, labelright=False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig = ax.figure
    pos = ax.get_position()
    logger.info(f"PROFILE道位置: x0={pos.x0:.4f} x1={pos.x1:.4f} y0={pos.y0:.4f} y1={pos.y1:.4f}")
    # 【2026-10-30 R49 防复发】全图统一瓦片锚（与岩性道同一 _tile_anchor 语义）
    _tile_anchor = float(depth_min)
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
    # 【2026-10-08】孔隙度留白读显示列 PHI_DISP（非储层归0，仅第5/6道显示语义）；
    # 无显示列时回退原始 PHI。任何解释判断逻辑仍读原始 PHI/PHIE/Sw。
    _phi_src = (phi_col if phi_col else
                ('PHI_DISP' if 'PHI_DISP' in t.columns else 'PHI'))
    phi = (pd.to_numeric(t[_phi_src], errors='coerce').values
           if _phi_src in t.columns else np.zeros(len(t)))
    phi = np.clip(np.nan_to_num(phi, nan=0.0), 0.0, 1.0)
    liths = (t['LITHOLOGY'].astype(str).str.lower().str.strip().values
             if 'LITHOLOGY' in t.columns else np.array([''] * len(t)))
    k = len(PROFILE_MINERALS)
    mv = np.zeros((len(t), k))
    for j, cc in enumerate(col_of):
        if cc:
            mv[:, j] = np.clip(np.nan_to_num(
                pd.to_numeric(t[cc], errors='coerce').values), 0, 1)
    # 【2026-10-19 用户要求】4矿物之外的特殊岩性段（玄武岩/硬石膏/煤等），
    # 若其对应矿物候选列失效（如蚀变玄武岩段 VClay≈1 被回填，与真实岩性
    # 矛盾），清零该点全部 mv —— 让下方 s≤1e-9 分支退回 LITHOLOGY 整带
    # 符号（spec_present 路径），profile道与岩性道同一套符号数据。
    _lith2cand = {item[1]: item[0] for item in PROFILE_MINERALS}
    _special = [li for li in dict.fromkeys(str(v) for v in liths)
                if li and li not in _lith2cand and li in LITHOLOGY_TO_SYMBOL
                and li != 'casing']
    if _special:
        # 特殊岩性段：清 0 全部 4 矿物 mv，退回 LITHOLOGY 整带符号路径
        _sp_mask = np.isin(liths, _special)
        mv[_sp_mask, :] = 0.0

    # 【2026-10-20 用户定案 3-SPS-111D】次要矿物剔除：单点占比<10% 的
    # 矿物不绘制（元素反演噪声级分量，如 6905-6906m 泥岩段 5-7% 石英
    # 被画成一条砂质填充带，影响整体美观）。清零后带宽并入"岩性定名
    # 余量带"，不产生空白。主成分（≥10%）不受影响。
    _row_sum = mv.sum(axis=1)
    _minor = (mv > 0) & (_row_sum[:, None] > 0) \
        & (mv / np.maximum(_row_sum, 1e-9)[:, None] < 0.10)
    # 【2026-10-26 R25 用户反馈】泥质(j=0)豁免<10%剔除: R24-2 已按
    # ECS↔伽马关系补全全井连续 VSH, 但 6490m 以下 VSH 多为 0.05-0.08,
    # 仍被本规则清零 ⇒ 泥质带断续(用户复看未解决)。泥质带保留真实
    # 宽度(窄带按既有规则只画底色, 连续无空缺); 其余矿物维持<10%剔除
    # (泥岩段石英噪声带, 2026-10-20 定案不变)。
    _minor[:, 0] = False
    if _minor.any():
        mv[_minor] = 0.0
        logger.info("PROFILE道次要矿物剔除(<10%%): %d 个分量清零", int(_minor.sum()))

    # ---------- 累积边界【2026-10-19 用户规格】----------
    # ①先按岩性定名检查矿物组分与孔隙度：特殊岩性→孔隙度归0、整带按定名填
    #   （spec_present 路径）；Σmv≤0（矿物列失效）或定名主矿物占比<15%
    #   （组分与定名不符）→ 整带按岩性定名填充。
    # ②合格点：矿物带按**真实比例**累积（不放大），余量（1-Σmv-φ）为
    #   "岩性定名余量带"，孔隙度区留白（φ=PHI_DISP，与第5道同源）→
    #   组分+孔隙度恒=1，各成分之间无空白。
    # bounds 布局：[0,b1)=泥岩 [b1,b2)=砂岩 [b2,b3)=灰岩 [b3,b4)=白云岩
    #              [b4,b5)=余量(岩性定名填充) [b5,1)=孔隙度(留白)
    bounds = np.zeros((len(t), k + 2))
    lith2j = {item[1]: j for j, item in enumerate(PROFILE_MINERALS)}
    # 【2026-10-08 一致性→2026-10-20 用户定案】孔隙度留白与第5道**完全同源**：
    # 直接用 PHI_DISP（第5道绿色曲线同一列、同一归零口径），不再按
    # INTERPRETATION 二次过滤——否则第5道有孔隙度的地方 profile 道没有
    # （NonReservoir 储层岩性按归零口径保留真实 PHI，两端必须一致）。
    bounds = np.zeros((len(t), k + 2))
    lith2j = {item[1]: j for j, item in enumerate(PROFILE_MINERALS)}
    # 岩性定名 → 期望主矿物带序号（检查组分是否符合定名）
    _expected_j = {'shale': 0, 'mudstone': 0, '泥岩': 0, '页岩': 0,
                   'sandstone': 1, '砂岩': 1,
                   'limestone': 2, 'carbonate': 2, '灰岩': 2, '碳酸盐岩': 2,
                   'dolomite': 3, '白云岩': 3}
    for i in range(len(t)):
        named = liths[i]
        p = float(phi[i])
        p = min(max(p, 0.0), 1.0)
        s = float(mv[i].sum())
        ej = _expected_j.get(named)
        # 组分检查：矿物失效 / 定名主矿物占比<15% → 与定名不符
        bad = (named in _special or s <= 1e-9
               or (ej is not None and mv[i, ej] < 0.15 * s))
        if bad:
            # 整带按岩性定名填充：余量带承担除孔隙度外全部宽度（特殊岩性由
            # spec_present 绘制，此处 bounds 矿物带置零避免误填；孔隙度区
            # 同样留白，与第5道同源）
            bounds[i, 1:k + 1] = 0.0
            bounds[i, k + 1] = 1.0 - p
            continue
        total = 1.0 - p
        # 【2026-10-22 用户反馈修复】"灰岩和白云岩含量之后、孔隙度之前又出现
        # 灰岩符号"——根因：Σmv(清零次要矿物后) < (1-φ)，多出的宽度被"岩性
        # 定名余量带"占用，而余量带位置固定在**白云岩带之后** ⇒ 灰岩定名段
        # 出现"灰岩…白云岩…灰岩"夹心；余量带又窄（0.012~0.13）⇒ 时而只有
        # 底色、时而只有半截符号。
        # 修复：把保留矿物**重新归一到 (1-φ)**（被剔除次要矿物的体积按比例
        # 并入主矿物）⇒ 余量带宽度恒为 0、夹心消失、无空白；"整带按定名
        # 填充"仅保留给组分与定名确实不符的坏点（该情形余量带=整带，
        # 用户已认可"单独只有灰岩"的表现）。
        scale = total / s if s > 1e-9 else 1.0
        acc = 0.0
        for j in range(k):
            acc += mv[i, j] * scale
            bounds[i, j + 1] = acc
        bounds[i, k + 1] = total         # 余量带右界；其右为孔隙度留白
    for j in range(1, k + 2):
        bounds[:, j] = np.maximum(bounds[:, j], bounds[:, j - 1])

    # ---------- 逐矿物带 + 统一符号（与岩性道同一函数、同一物理间距） ----------
    # 【2026-10-08 用户要求】套管段不绘制（留白）：填充 where 跳过套管点，
    # 符号点同步跳过，整段空白
    _nodraw = np.array([v == 'casing' for v in liths])
    for j, (cand, lname, cname, color, kind) in enumerate(PROFILE_MINERALS):
        xl = bounds[:, j]
        xr = bounds[:, j + 1]
        if (xr - xl).max() <= 1e-4:
            continue
        ax.fill_betweenx(md, xl, xr, color=color, alpha=1.0, lw=0, zorder=8,
                         where=(~_nodraw))
        # 【2026-10-15 用户要求】岩性符号统一图片填充：逐行带调用统一入口
        # draw_lithology_pattern(fill_bg=False)——image类铺PNG瓦片（瓦片网格
        # 锚定全局 md.min()，相位接续不重复顶条），无图片岩性走点线，
        # 与岩性道同一函数同一符号
        scale = _axes_data_per_px(ax)
        if scale is not None:
            pitch = _lith_pitch_px(kind)   # 与图例/全程序同一来源（机制化）
            # 【2026-10-22】原生 motif 单元模式（砂/泥）：窄带判定按**单元
            # 像素宽**（瓦片实际宽）⇒ 单元模式下的窄带门槛与实体一致。
            _ref_f = _SYMBOL_REF_IMAGE.get(lname)
            if _ref_f and str(_ref_f) in _SYMBOL_REF_UNIT:
                pitch = _lith_ref_tile_size(_ref_f)[0]
            dy = max(pitch * abs(scale[1]), 1e-6)
        else:
            dy = max((md.max() - md.min()) / 200.0, 1e-6)
        if kind in ('brick', 'slant_brick', 'ref'):
            # 【2026-10-19 用户要求】灰岩/白云岩段：按连续段**整段**调用统一
            # 入口——竖缝纵贯行界与上下横线相连、斜线端点顶到横缝；横缝位于
            # 全局网格线上（tile_origin 锚定），段间接续无缝。逐行带调用会把
            # 竖缝截在半行内、斜线漂浮，profile道图案断裂。
            # 【2026-10-20】ref（参考图墨迹）同走整段：瓦片网格全局锚定，
            # 整段一次 imshow 优于逐行带多次 imshow（相位连续且更快）
            # 【2026-10-30 R50 用户定案：绘制总体规划，解耦逐点切分】旧逻辑
            # 按 bounds 漂移>0.02 切 0.3-0.7m 子段逐块 imshow——每块独立
            # 光栅化的亚像素映射相位逐块重置，跨块点间距忽大忽小（111D
            # 6493/6534/6629/6725 密集成黑、6598/6602/6779 间隔变大实测）。
            # 改为：仅按套管/窄带游程分段，每游程**整段一次**调用；可见性
            # clip 到逐点 bounds 线性多边形（锯齿边界保留、符号绝不越入
            # 孔隙度留白），瓦片相位由全局网格保证，纵横间距一致不加密。
            # 带宽不足 0.6×pitch 的窄带仍只画底色不画符号（防蒙皮伪迹）。
            _trk_px = _axes_px_width(ax)
            n_pts = len(md)
            i0 = 0
            while i0 < n_pts:
                if _nodraw[i0] or xr[i0] - xl[i0] < 0.012:
                    i0 += 1
                    continue
                i1 = i0
                while (i1 + 1 < n_pts and not _nodraw[i1 + 1]
                       and xr[i1 + 1] - xl[i1 + 1] >= 0.012):
                    i1 += 1
                _wmax = float(np.max(xr[i0:i1 + 1] - xl[i0:i1 + 1]))
                _w_px = (_wmax * _trk_px) if _trk_px else 1e9
                if _trk_px is None or _w_px >= 0.6 * pitch:
                    seg_z1 = float(md[i1]) + (float(md[i1] - md[i1 - 1])
                                              if i1 > i0 else dy / 2.0)
                    draw_lithology_pattern(
                        ax, lname, float(md[i0]), seg_z1,
                        x0=float(np.min(xl[i0:i1 + 1])),
                        x1=float(np.max(xr[i0:i1 + 1])), fill_bg=False,
                        zorder=10, tile_origin=_tile_anchor,
                        clip_patch=_lith_clip_path(
                            md[i0:i1 + 1], xl[i0:i1 + 1], xr[i0:i1 + 1], ax))
                i0 = i1 + 1
            continue
        for dd in np.arange(md.min() + dy / 2.0, md.max(), dy):
            if _nodraw[int(np.argmin(np.abs(md - dd)))]:
                continue
            xll = float(np.interp(dd, md, xl))
            xrr = float(np.interp(dd, md, xr))
            if xrr - xll < 0.012:
                continue
            draw_lithology_pattern(ax, lname, dd - dy / 2.0, dd + dy / 2.0,
                                   x0=xll, x1=xrr, fill_bg=False, zorder=10,
                                   tile_origin=_tile_anchor)

    # ---------- 余量带【2026-10-19 用户规格】：矿物之外剩余按岩性定名填充 ----------
    # bounds[:,k]→bounds[:,k+1]；孔隙度区（bounds[:,k+1]→1）留白不填。
    # 特殊岩性段由 spec_present 整带绘制，此处跳过；套管段不绘制。
    xLr = bounds[:, k]
    xRr = bounds[:, k + 1]
    if (xRr - xLr).max() > 1e-4:
        scale = _axes_data_per_px(ax)
        _trk_px_r = _axes_px_width(ax)
        # 【2026-10-30 R48】dy_r 兜底初始化：全部点被跳过（套管/特殊岩性/
        # 余量带<0.012）时下方逐行带循环不再 UnboundLocalError 崩溃
        # （111D 纯灰岩+盐膏窗口复现实测，正式井靠特殊段侥幸避开）
        dy_r = max((md.max() - md.min()) / 200.0, 1e-6)
        # 背景：按岩性定名连续段填充（同段同色；brick/slant 段整段画符号）
        n_pts = len(md)
        i0 = 0
        while i0 < n_pts:
            li = str(liths[i0])
            if _nodraw[i0] or li in _special or xRr[i0] - xLr[i0] < 0.012:
                i0 += 1
                continue
            # 行带采样距按本段岩性 kind 取（与矿物带/_lith_pitch_px 同源，机制化）
            if scale is not None:
                dy_r = max(_lith_pitch_px(_lith_pattern_kind(li)) * abs(scale[1]), 1e-6)
            else:
                dy_r = max((md.max() - md.min()) / 200.0, 1e-6)
            i1 = i0
            while (i1 + 1 < n_pts and not _nodraw[i1 + 1]
                   and str(liths[i1 + 1]) == li
                   and xRr[i1 + 1] - xLr[i1 + 1] >= 0.012):
                i1 += 1
            ax.fill_betweenx(md[i0:i1 + 1], xLr[i0:i1 + 1], xRr[i0:i1 + 1],
                             color=_lith_bg_color(li), alpha=1.0, lw=0,
                             zorder=8)
            kind_r = _lith_pattern_kind(li)
            _wmax_r = float(np.max(xRr[i0:i1 + 1] - xLr[i0:i1 + 1]))
            _w_px_r = (_wmax_r * _trk_px_r) if _trk_px_r else 1e9
            if (kind_r in ('brick', 'slant_brick', 'ref')
                    and (_trk_px_r is None
                         or _w_px_r >= 0.6 * _lith_pitch_px(kind_r))):
                seg_z1 = float(md[i1]) + (float(md[i1] - md[i1 - 1])
                                          if i1 > i0 else dy_r / 2.0)
                # 【2026-10-30 R50】同矿物带：整段一次调用+逐点边界 clip
                # 多边形（锯齿边界保留、不越入孔隙度留白、块数最少）
                draw_lithology_pattern(
                    ax, li, float(md[i0]), seg_z1,
                    x0=float(np.min(xLr[i0:i1 + 1])),
                    x1=float(np.max(xRr[i0:i1 + 1])), fill_bg=False,
                    zorder=10, tile_origin=_tile_anchor,
                    clip_patch=_lith_clip_path(
                        md[i0:i1 + 1], xLr[i0:i1 + 1], xRr[i0:i1 + 1], ax))
            i0 = i1 + 1
        # 符号：逐行带（点/横线/人字/倒L/图片类），边缘按深度插值
        for dd in np.arange(md.min() + dy_r / 2.0, md.max(), dy_r):
            ii = int(np.argmin(np.abs(md - dd)))
            if _nodraw[ii] or str(liths[ii]) in _special:
                continue
            if _lith_pattern_kind(str(liths[ii])) in ('brick', 'slant_brick', 'ref'):
                continue   # 已按连续段整段绘制
            xll = float(np.interp(dd, md, xLr))
            xrr = float(np.interp(dd, md, xRr))
            if xrr - xll < 0.012:
                continue
            draw_lithology_pattern(ax, str(liths[ii]), dd - dy_r / 2.0,
                                   dd + dy_r / 2.0, x0=xll, x1=xrr,
                                   fill_bg=False, zorder=10,
                                   tile_origin=_tile_anchor)

    # ---------- 特殊岩性非储层点：整带统一符号（与岩性道同一套数据/符号） ----------
    # 【2026-10-08】煤/碳质泥岩等不在4矿物表内的岩性，此前走 argmax(mv)
    # 兜底被填成砂岩/泥岩，与岩性道不一致。这里按 LITHOLOGY 列整带填统一
    # 背景色+符号，与岩性道完全同一套。
    # 【2026-10-08 用户要求】套管段不绘制不用符号 → spec_present 排除 casing
    spec_present = [li for li in dict.fromkeys(str(v) for v in liths)
                    if li and li not in lith2j
                    and li in LITHOLOGY_TO_SYMBOL and li != 'casing']
    if spec_present:
        # 【2026-10-09 符号一致】逐连续段整带直接调用统一入口
        # draw_lithology_pattern——与岩性道完全同一函数：点线类
        # (dots/dash/brick/coal)走像素等间距点阵，image类(碳质泥岩等)
        # 走PNG标准瓦片。此前 _lith_pattern_points 对image类返回空点、
        # k2 != 'image' 守卫整类跳过，profile道只剩灰底无符号，与岩性道
        # 的PNG符号不一致。套管段不在 spec_present，整段自然留白。
        n_pts = len(md)
        # 【2026-10-30 R49 防复发】特殊岩性整带分段收敛到唯一分段源
        # _contiguous_lith_runs（与岩性道共用同一游程逻辑）
        for _a, _b, li in _contiguous_lith_runs([str(v) for v in liths]):
            if li not in spec_present:
                continue
            # 段末取下一点MD（与岩性道 seg_end_md 同口径），单点段也有厚度
            # 【2026-10-20】段内若 PHI_DISP>0（与第5道同源），整带右端收缩
            # 出孔隙度留白（特殊岩性现口径 PHI_DISP=0，此为守卫）
            _p_seg = float(np.max(phi[_a:_b + 1])) if len(phi) else 0.0
            draw_lithology_pattern(ax, li, float(md[_a]),
                                   float(md[min(_b + 1, n_pts - 1)]),
                                   0.0, 1.0 - min(max(_p_seg, 0.0), 0.9),
                                   fill_bg=True,
                                   bg_color=_lith_bg_color(li), zorder=10,
                                   tile_origin=_tile_anchor)

    ax.plot([0, 0, 1, 1, 0],
            [md.min(), md.max(), md.max(), md.min(), md.min()],
            color='k', lw=0.5, zorder=12)

    # ---------- 图头图例：横向填满道宽、纵向叠置无间隙、文字居中 ----------
    # 【2026-10-08 用户要求】每个图例横向完全填充道宽，纵向上不留空白每个
    # 图例叠置，孔隙度图例空白，文字在图例中央居中
    hh = header_top_y - header_bottom_y
    vis = [j for j in range(k)
           if (bounds[:, j + 1] - bounds[:, j]).max() >= 0.05]
    # (标签, 颜色, 符号kind, 岩性名) —— 岩性名显式携带，避免循环变量残留
    items = [(PROFILE_MINERALS[j][2], PROFILE_MINERALS[j][3],
              PROFILE_MINERALS[j][4], PROFILE_MINERALS[j][1]) for j in vis]
    # 特殊岩性（煤/碳质泥岩等）出现在剖面中时追加图例（套管不绘制故无图例）
    # 【2026-10-14 十九轮定案】标签改英文（全图英文一致），与 fallback_colors 术语一致
    _SPEC_EN = {'coal': 'Coal', 'carbonaceous_shale': 'Carbonaceous Shale',
                'pyrite': 'Pyrite',
                'conglomerate': 'Conglomerate', 'volcanic': 'Volcanic',
                'basalt': 'Basalt', 'anhydrite': 'Anhydrite',
                'gypsum': 'Gypsum', 'halite': 'Halite'}
    for li in spec_present:
        items.append((_SPEC_EN.get(li, li), _lith_bg_color(li),
                      _lith_pattern_kind(li), li))
    items.append(('Porosity', 'white', 'blank', 'blank'))
    n = len(items)
    ih = hh / n          # 每项占满总高均分，纵向叠置无间隙
    tw = pos.x1 - pos.x0
    bx = pos.x0          # 横向完全填充道宽
    bw = tw
    for i, (label, color, kind, lith_name) in enumerate(items):
        by = header_top_y - (i + 1) * ih
        rect = plt.Rectangle((bx, by), bw, ih, transform=fig.transFigure,
                             facecolor=color, edgecolor='k', lw=0.6, zorder=6000)
        fig.add_artist(rect)
        # 【2026-10-19 机制化】图头图例全纹理填充：间距/样式一律由图例函数
        # 按 kind 从 SYMBOL_SPECS 取（与实体同一来源）——禁止调用点传参分叉
        draw_lithology_pattern_fig(fig, lith_name, bx, by, bw, ih,
                                   bg_color=color, zorder=6002)
        # 文字在图例中央居中
        # 【2026-10-14 用户定案】第7道图头所有图例文字：白底黑字方框
        # （此前仅泥岩，现扩展到该道全部图例项）
        _tb = dict(boxstyle='square,pad=0.25', facecolor='white',
                   edgecolor='black', lw=0.5)
        fig.text(bx + bw / 2.0, by + ih / 2.0, label, fontsize=8, ha='center',
                 va='center', fontfamily='Microsoft YaHei', color='black',
                 bbox=_tb, transform=fig.transFigure, zorder=6003)

def _paint_fluid_segment(ax, seg_start_md, seg_end_md, interpretation, colors, clip_rect=None):
    """【2026-10-13 用户要求】解释结论按 fluid_conclusions 图例思路绘制**整段**，
    【2026-10-13 二次定案】图例只占道宽左半 50%（x: 0~0.5），右半留给层编号。

    图例样式规则（与 symbol/fluid_conclusions 图标一致；坐标按 0~1 归一后
    经 _X() 映射到道内左半 0~0.5）：
      - 纯色结论（OIL/GAS/WATER/DRY/TIGHT/PROBABLE_*/POSSIBLE_*）→ 整段铺满该色
      - GAS_WATER / OIL_WATER / GAS_OIL → 斜对角（向右上→左下）分 2 半：
        左上半 = 前组分色，右下半 = 后组分色（如气水同层：左上半红=气、右下半蓝=水）
      - POOR_GAS / POOR_OIL（差气/差油层）→ 整段边框 + 左 1/3 组分色
      - GAS_BEARING_WATER / OIL_BEARING_WATER（含气/含水层）→ 左 20% 组分色 + 右 80% 水色
    """
    seg_h = float(seg_end_md - seg_start_md)
    if seg_h <= 0:
        return
    key = str(interpretation).upper().strip().replace(' ', '_').replace('-', '_')
    _X_R = 0.5  # 【2026-10-13】图例占道宽 50%（左半），右半绘制层编号

    def _X(u):
        # 归一 0~1 → 道内左半 0~_X_R
        return u * _X_R

    def _fill(x0, x1, color, alpha=0.85):
        if color is None:
            return
        p = ax.fill_betweenx([seg_start_md, seg_end_md], _X(x0), _X(x1),
                             color=color, alpha=alpha, zorder=2)
        if clip_rect is not None:
            p.set_clip_path(clip_rect)

    def _c(tag):
        # colors 键形态兼容：大写 / 标题 / 原始
        for k in (tag, tag.title(), tag.lower(), tag.capitalize()):
            if k in colors:
                return colors[k]
        return None

    # 斜对角分区：右上(浅端 x=_X_R) → 左下(深端 x=0)，左上半 vs 右下半
    def _fill_diag(color_upper, color_lower):
        _y = np.array([seg_start_md, seg_end_md], dtype=float)
        _diag_x = _X_R - (_y - seg_start_md) / seg_h * _X_R
        _pu = ax.fill_betweenx(_y, 0.0, _diag_x, color=color_upper, alpha=0.85, zorder=2)
        _pl = ax.fill_betweenx(_y, _diag_x, _X_R, color=color_lower, alpha=0.85, zorder=2)
        if clip_rect is not None:
            _pu.set_clip_path(clip_rect)
            _pl.set_clip_path(clip_rect)

    # 边框：整段矩形框（图例均为矩形框样式；probable/possible 图标无外框，也保留细框便于识别段边界）
    _box = plt.Rectangle((0, seg_start_md), _X_R, seg_h,
                         fill=False, edgecolor='black', lw=0.35, alpha=0.45, zorder=3)
    ax.add_patch(_box)
    if clip_rect is not None:
        _box.set_clip_path(clip_rect)

    if 'OIL_BEARING_WATER' in key or 'WATER_BEARING_OIL' in key:
        _fill(0.0, 0.2, _c('OIL'))
        _fill(0.2, 1.0, _c('WATER'))
    elif 'GAS_BEARING_WATER' in key or 'WATER_BEARING_GAS' in key:
        _fill(0.0, 0.2, _c('GAS'))
        _fill(0.2, 1.0, _c('WATER'))
    elif 'POOR_OIL' in key:
        _fill(0.0, 1.0 / 3.0, _c('OIL'))
    elif 'POOR_GAS' in key:
        _fill(0.0, 1.0 / 3.0, _c('GAS'))
    elif 'GAS_WATER' in key:
        _fill_diag(_c('GAS'), _c('WATER'))
    elif 'OIL_WATER' in key:
        _fill_diag(_c('OIL'), _c('WATER'))
    elif 'GAS_OIL' in key or 'OIL_GAS' in key:
        _fill_diag(_c('GAS'), _c('OIL'))
    else:
        # 纯色结论整段铺满
        _color = colors.get(key)
        if _color is None:
            _color = colors.get(interpretation)
        _fill(0.0, 1.0, _color)


def _well_info_json_path(well_dir, well_name=''):
    """<井名>info.json 路径（井文件夹下, 井名与 info 间无连字符）。"""
    wd = Path(well_dir)
    _name = str(well_name or wd.name or 'well').strip() or 'well'
    return wd / f"{_name}info.json"


def _flatten_well_info_cfg(cfg):
    """分组 json → 展平 dict（跳过 _ 开头说明键；仅保留非空值）。"""
    flat = {}
    if not isinstance(cfg, dict):
        return flat
    for _sec in cfg.values():
        if not isinstance(_sec, dict):
            continue
        for _k, _v in _sec.items():
            if _k.startswith('_') or _v is None:
                continue
            _sv = str(_v).strip()
            if _sv and not _sv.startswith('-999'):
                flat[_k] = _sv
    return flat


def _wellinfo_rec_rows(s):
    """<井名>info.json 钻头/套管字符串 → rows。

    【2026-10-14 用户定案】钻头/套管数据进 json 可人工修改：
    '20in 0-118ft; 13.375in 0-2630.97ft' → [{'size':'20','from':'0','to':'118'}, ...]
    （size/to 渲染端补单位, 与 LAS/录井图提取的 rows 形态一致）
    """
    import re as _re
    rows = []
    for pt in str(s or '').split(';'):
        pt = pt.strip()
        m = _re.match(
            r'^([0-9]+(?:\.[0-9]+)?)\s*(?:in|IN|")?\s+'
            r'([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*'
            r'([0-9]+(?:\.[0-9]+)?)\s*(?:ft|FT|m|M)?$', pt)
        if m:
            rows.append({'size': m.group(1), 'from': m.group(2), 'to': m.group(3)})
    return rows


def _load_well_info_json(results):
    """供可视化读取: 从 results 定位 <井名>info.json 并展平（找不到→{}）。

    定位顺序: results['well_info_json']（logInt 收集时写入）→
    results['well_dir']/<井名>info.json。json 由 logInt 井信息收集模块
    生成/维护（人工可修改, 非空值优先生效）。
    """
    if not isinstance(results, dict):
        return {}
    _cands = []
    _p = results.get('well_info_json')
    if _p:
        _cands.append(Path(_p))
    _wd = results.get('well_dir')
    _wn = str((results.get('las_info') or {}).get('well', {}).get('well_name')
              or results.get('well_name') or '')
    if _wd:
        _cands.append(_well_info_json_path(_wd, _wn))
    for p in _cands:
        try:
            if p.exists():
                return _flatten_well_info_cfg(
                    json.loads(p.read_text(encoding='utf-8')))
        except Exception as e:
            logger.warning("井信息 json 读取失败 %s: %s", p, e)
    return {}


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
        # 【2026-10-13 统一流体图标色系】与 symbol/fluid_conclusions 图标一致：
        # oil=深绿#006400、gas=正红#ff0000、water=蓝#0066ff、dry/tight=灰#8a8a8a、
        # probable_oil=亮绿#22b14c、possible_oil=青#00c7c7、probable_gas=橙红#ff5500、possible_gas=洋红#ff00ff
        'Oil': '#006400',
        'Gas': '#ff0000',
        'Water': '#0066ff',
        'Dry': '#8a8a8a'
    }

    if has_enough_curves and 'INTERPRETATION' in data.columns:
        interp_color_map = {
            # 【2026-10-13 统一流体图标色系】与 symbol/fluid_conclusions 图标一致
            'OIL': '#006400',
            'GAS': '#ff0000',
            'WATER': '#0066ff',
            'DRY': '#8a8a8a',
            'TIGHT': '#8a8a8a',
            'OIL_POSSIBLE': '#00c7c7',
            'GAS_POSSIBLE': '#ff00ff',
            'OIL_PROBABLE': '#22b14c',
            'GAS_PROBABLE': '#ff5500',
            'Undefined': 'gray',
            'Oil': '#006400',
            'Gas': '#ff0000',
            'Water': '#0066ff',
            'Dry': '#8a8a8a',
            '可疑层': 'palegreen'
        }
        
        # clip_rect：限制绘制范围在解释层道内。
        # 【2026-10-09 修复】原实现高度误用 curve_height_ratio（figure坐标比例，
        # 约0.9）作为 Axes 坐标高度，导致 Axes 顶部（井顶浅部约9%深度区间）被裁剪，
        # 编号1、2等井顶最浅的解释层不可见（BET-1 等 ft 井曲线区占比大，症状明显）。
        # Axes 高度单位是1.0，曲线区=整个Axes（header为figure坐标绘制），故高度取1.0。
        clip_rect = plt.Rectangle((0, 0), 1, 1.0, transform=ax.transAxes,
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

        # 第二步半：【2026-10-09】同砂体同家族流体合并——一层砂岩只能
        # 一个水/油/气层（用户：6,7和8,9及11,12等在同一个砂体内需合并）。
        # 屏障判定基于隔层岩性连续厚度≥3个深度单位（泥质岩类/煤/盐膏），
        # 砂肩NonReservoir/DRY/薄泥岩条带(<3ft)不打断（与logInt分异整饰同口径）。
        merged_segments = _merge_same_body_fluid(merged_segments, data)

        # 第二步半之二：【2026-10-21 R18】解释结论框覆盖"整个岩层的孔隙度符合
        # 部分或解释部分"——用户："解释结论的框需要覆盖整个岩层的孔隙度符合部分
        # 或者解释部分，而不是像 1-3 层那样只覆盖很少部分"。
        # 根因：逐点 INTERPRETATION 分组被 NonReservoir/DRY 逐点噪声切碎，
        # 一个 7m 的含气砂层只画出 1m 宽的框（RP-13 层1 = 3726-3727 GAS）。
        merged_segments = _fuse_fluid_segments_by_reservoir_unit(merged_segments, data)

        # 第三步：绘制合并后的段，油气水层从顶到底统一编号
        # NonReservoir段留白不绘制（作为分隔屏障阻止合并，但不绘制任何色块/线）
        layer_num = 0
        hc_count = 0
        _num_log = []
        for seg_start_md, seg_end_md, interpretation in merged_segments:
            # 干层DRY不绘制
            if interpretation == 'DRY':
                continue
            # NonReservoir段留白，不绘制任何元素
            if interpretation in ('NonReservoir', 'Non-Reservoir'):
                continue
            hc_count += 1
            # 【2026-10-13 用户定案】解释结论按图例思路绘制**整段**，但图例只
            # 占道宽左半 50%（0~0.5，右半留给层编号），不在道中间放小矩形框/
            # 贴图标 png；复合结论（油水/气水/含油水/差油等）按 fluid_conclusions
            # 图例分区绘制。
            # 【2026-10-13 二次定案】图例区不再铺岩性符号细点填充——只按图例
            # 颜色绘制（纯色/斜对角复合色），岩性由左侧岩性道表达。
            _paint_fluid_segment(ax, seg_start_md, seg_end_md, interpretation,
                                 interp_color_map, clip_rect=clip_rect)

            # 统一编号：从井顶部到底部，每个油气水层依次编号
            layer_num += 1
            mid_md = (seg_start_md + seg_end_md) / 2.0
            _num_log.append((layer_num, round(float(mid_md), 2), str(interpretation)))
            # 【2026-10-13 用户要求】层编号不加外框, 字号与深度刻度数字一致(11)
            txt = ax.text(0.75, mid_md, str(layer_num),
                          ha='center', va='center', fontsize=11, fontweight='bold',
                          color='black', clip_on=True, zorder=5)
            txt.set_clip_path(clip_rect)

        logger.info(f'解释道绘制完成: 油气水层{hc_count}个; 编号序列前12: {_num_log[:12]}')


def _find_column(data, possible_names):
    """查找可能的列名"""
    for name in possible_names:
        if name in data.columns:
            return name
    return None


# 【2026-10-21 R18】井径候选列（RP-13 的 LAS 里井径叫 CAL_AVERAGE）
_CAL_CANDIDATES = ['CALS', 'CALI', 'CAL', 'CAL_AVERAGE', 'CAL-AVG', 'CALAVG',
                   'CAL_MEAN', 'CALMEAN', 'CALIPER', 'HCAL', 'CALX', 'CALY']

_PLOT_RANGE_CACHE = {}


def _load_plot_range_cfg():
    """读 logint.json → plot_range（模块级惰性读 + 缓存）。

    【2026-10-21 R18】综合图起点裁剪规则此前只在 log_visualizer 侧实现，
    logvis 的两种图都没接 ⇒ 快速解释图把导管/表层/未测段整段画成空白道。
    此处把同一配置项接进来。
    """
    import json as _json
    path = Path(__file__).parent / 'logint.json'
    key = str(path)
    if key not in _PLOT_RANGE_CACHE:
        cfg = {}
        try:
            if path.exists():
                cfg = (_json.loads(path.read_text(encoding='utf-8'))
                       .get('plot_range') or {})
        except Exception as e:
            logger.warning('plot_range 配置读取失败(用内置默认): %s', e)
        _PLOT_RANGE_CACHE[key] = cfg if isinstance(cfg, dict) else {}
    return dict(_PLOT_RANGE_CACHE[key])


def _blank_borehole_and_lowcurve(data, min_valid_curves=3, log_tag='图'):
    """绘图前置：把「套管/水泥块」与「有效曲线不足 N 条」的井段整段置空。

    【2026-10-21 R18 用户定案】"少于3条有效曲线或者在套管内就不绘制，
    只绘制在裸眼的井段图"。

    置空口径：MD 之外所有列 —— 数值→NaN、文本→''、布尔→False，并把
    VALID_CURVES_COUNT 显式置 0（留 NaN 时 `NaN<3` 为 False，会被误判成
    "有效曲线"而继续绘制）。
    ⚠️ 只在**绘图副本**上做，不得回写 processed.csv（否则伽玛族 VSH 刻度
    P10/P90 会变 → 段外结论被改判）。
    """
    d = data
    mask = pd.Series(False, index=d.index)
    if 'IS_CASING' in d.columns:
        mask |= d['IS_CASING'].fillna(False).astype(str).str.lower().isin(
            ('true', '1', '1.0'))
    for _bc in ('_BOREHOLE', 'BOREHOLE'):
        if _bc in d.columns:
            mask |= d[_bc].fillna('').astype(str).str.strip().isin(
                ('套管', '水泥块', 'casing', 'cement'))
    if 'VALID_CURVES_COUNT' in d.columns:
        _vc = pd.to_numeric(d['VALID_CURVES_COUNT'], errors='coerce')
        mask |= _vc.isna() | (_vc < int(min_valid_curves))
    if not bool(mask.any()):
        return d, 0
    d = d.copy()
    for c in d.columns:
        if c == 'MD':
            continue
        col = d[c]
        try:
            if pd.api.types.is_bool_dtype(col):
                d.loc[mask, c] = False
            elif pd.api.types.is_numeric_dtype(col):
                d.loc[mask, c] = np.nan
            else:
                d.loc[mask, c] = ''
        except Exception:
            continue
    if 'VALID_CURVES_COUNT' in d.columns:
        d.loc[mask, 'VALID_CURVES_COUNT'] = 0
    _md = d.loc[mask, 'MD']
    logger.info('%s 井筒/低有效曲线段置空: %d 点（%.1f-%.1f m）—— 该段不绘制',
                log_tag, int(mask.sum()),
                float(_md.min()) if len(_md) else float('nan'),
                float(_md.max()) if len(_md) else float('nan'))
    return d, int(mask.sum())


def _build_bs_from_hole_program(md, results):
    """由井眼程序（results['hole_program']）生成 BIT/BS 阶梯曲线。

    【2026-10-21 R18 用户口径】"在基础资料中很容易找到最后一个钻头是 8.5in 的，
    要以他为 bit 绘制 bit 曲线，之间的部分按统一的井径绘制规则由颜色冲填"
    —— 即：没有 BS 曲线时，用井眼程序（各段钻头尺寸 + 起止井深）合成一条
    阶梯状 BS 曲线；最后一段延伸到井底（最后钻头打到底）。

    返回 np.ndarray（与 md 等长，英寸）或 None。
    """
    hp = (results or {}).get('hole_program')
    if not hp or md is None or len(md) == 0:
        return None
    try:
        _md = np.asarray(md, dtype=float)
        _lo, _hi = float(_md.min()), float(_md.max())
        _seg = sorted((float(x['from_md']), float(x['to_md']), float(x['bit']))
                      for x in hp if x.get('bit') is not None)
        if not _seg:
            return None
        _bs = np.full(len(_md), np.nan, dtype=float)
        _last_bit = _seg[-1][2]
        _i = 0
        for _k, (_f, _t, _b) in enumerate(_seg):
            _end = max(_t, _hi) if _k == len(_seg) - 1 else _t
            while _i < len(_md) and _md[_i] < _f:
                _bs[_i] = _last_bit      # 井口以上（表层管外）用最后钻头
                _i += 1
            while _i < len(_md) and _md[_i] <= _end:
                _bs[_i] = _b
                _i += 1
        while _i < len(_md):
            _bs[_i] = _last_bit
            _i += 1
        if not np.isfinite(_bs).any():
            return None
        logger.info('由井眼程序合成 BS(BIT) 曲线: %d 段, 尺寸 %s, 井底延伸至 %.1fm',
                    len(_seg), [('%g' % x[2]) for x in _seg], _hi)
        return _bs
    except Exception as e:
        logger.warning('井眼程序合成 BS 曲线失败: %s', e)
        return None


# 流体结论归并用的"储层岩性"判定（非储层白名单同源：泥岩/煤/膏盐/火成岩…）
_NONRES_LITH_KEYS = frozenset({
    'shale', 'mudstone', 'claystone', 'silty_shale', 'carbonaceous_shale',
    'coal', 'pyrite', 'anhydrite', 'gypsum', 'salt', 'halite', 'evaporite',
    'volcanic', 'basalt', 'tuff', 'andesite', 'basement', 'granite',
    'casing', '未知', 'unknown', '泥岩', '页岩', '煤层', '煤', '硬石膏',
    '石膏', '盐岩', '膏盐', '火山岩', '玄武岩', '花岗岩', '黄铁矿', '水泥块',
    '套管', '凝灰岩', 'carbonate_shale',
})
# 视为"流体结论"的标签（NonReservoir / DRY / 空 不算）
_FLUID_TAGS = ('OIL', 'GAS', 'WATER', 'CONDENSATE',
               'OIL_POSSIBLE', 'GAS_POSSIBLE', 'OIL_PROBABLE', 'GAS_PROBABLE',
               'POOR_OIL', 'POOR_GAS', 'GAS_WATER', 'OIL_WATER', 'GAS_OIL',
               'OIL_GAS', 'GAS_BEARING_WATER', 'OIL_BEARING_WATER',
               'WATER_BEARING_OIL', 'WATER_BEARING_GAS')


def _fuse_fluid_segments_by_reservoir_unit(segments, data):
    """【2026-10-21 R18】解释结论按**储层段**归并（用户：框要覆盖整个岩层）。

    逐点 INTERPRETATION 分组会把一个完整砂层切碎成 1m 的碎框（相邻点被判
    NonReservoir/DRY 就断开）。这里改为：
      ① 找"储层段" = 连续且非非储层岩性的区间（泥岩/煤/膏盐/火成岩等断开）；
      ② 段内任一点是流体结论 → 整段出一个框，标签 = 段内流体结论**厚度占优者**
         （同厚度时油气优先于水）；
      ③ 框的顶底 = 段内**孔隙度达标点**（PHI_DISP>0）的首末深度；若段内无孔隙度
         达标点，退回段的首末深度（保底覆盖整层）；
      ④ 段内无任何流体结论 → 不产出（保持留白）；
      ⑤ 相邻段若流体标签相同则再合并一次（消除段边界处 1 个采样点的碎框）。

    返回: 归并后的段列表（NonReservoir 段被丢弃 —— 它们只是分隔屏障，不绘框）。
    """
    if not segments or data is None or 'MD' not in data.columns:
        return segments
    _md = pd.to_numeric(data['MD'], errors='coerce').to_numpy(dtype=float)
    n = len(_md)
    if n == 0:
        return segments

    if 'LITHOLOGY' in data.columns:
        _lith = (data['LITHOLOGY'].fillna('').astype(str).str.lower()
                 .str.strip().str.replace(r'\s+', '_', regex=True))
    else:
        _lith = pd.Series([''] * n, index=data.index)
    _phi = np.zeros(n)
    for c in ('PHI_DISP', 'PHI_LOG', 'PHI', 'PHIE'):
        if c in data.columns:
            _phi = pd.to_numeric(data[c], errors='coerce').fillna(0.0).to_numpy()
            break
    if 'VALID_CURVES_COUNT' in data.columns:
        _vc = (pd.to_numeric(data['VALID_CURVES_COUNT'], errors='coerce')
               .fillna(0).to_numpy())
    else:
        _vc = np.ones(n)
    # 储层点：有效曲线达标 且 岩性非非储层
    _res_pt = (_vc >= 3) & ~_lith.isin(_NONRES_LITH_KEYS).to_numpy()

    _units = []
    _i = 0
    while _i < n:
        if not _res_pt[_i]:
            _i += 1
            continue
        _j = _i
        while _j + 1 < n and _res_pt[_j + 1]:
            _j += 1
        _units.append((_i, _j))
        _i = _j + 1
    if not _units:
        return segments

    _itp = (data['INTERPRETATION'].fillna('').astype(str).str.upper().str.strip()
            if 'INTERPRETATION' in data.columns
            else pd.Series([''] * n, index=data.index))
    _HC_RANK = {'OIL': 3, 'GAS': 3, 'OIL_POSSIBLE': 2, 'GAS_POSSIBLE': 2,
                'OIL_PROBABLE': 2, 'GAS_PROBABLE': 2, 'CONDENSATE': 2,
                'WATER': 1}

    out = []
    for (_a, _b) in _units:
        _cnt = {}
        for _t in _itp.iloc[_a:_b + 1]:
            if _t in _FLUID_TAGS:
                _cnt[_t] = _cnt.get(_t, 0) + 1
        if not _cnt:
            continue    # 段内无流体结论 → 不绘框
        _lab = max(_cnt.items(), key=lambda kv: (kv[1], _HC_RANK.get(kv[0], 0)))[0]
        _sub_phi = _phi[_a:_b + 1]
        _ok = np.where(_sub_phi > 0)[0]
        if _ok.size:
            _top = _md[_a + _ok[0]]
            _bot = _md[_a + _ok[-1]]
        else:
            _top, _bot = _md[_a], _md[_b]
        if _bot <= _top:
            continue
        if out and out[-1][2] == _lab and _top - out[-1][1] <= 2.0:
            out[-1] = (out[-1][0], float(_bot), _lab)
        else:
            out.append((float(_top), float(_bot), _lab))
    return out if out else segments


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
# 流体交会图与深度单位适配（2026-10-14 由 visualization_fluid.py 原生并入）
#   可视化统一由 logvis 实现，不再依赖外部模块与猴子补丁：
#   patch_depth_unit('ft')            —— 深度道单位设置（直调 set_depth_unit）
#   visualize_fluid_crossplots(...)   —— 油绿/气红/水蓝 交会图，按层号标注
# ============================================================================
_DEPTH_UNIT = {'m': 'm', 'ft': 'ft', '米': 'm', '英尺': 'ft'}


def setup_chinese_font(font_names=('Microsoft YaHei', 'SimHei', 'SimSun')):
    """注册系统中文字体并设为 matplotlib 默认。返回实际使用的字体名。"""
    import matplotlib
    import matplotlib.font_manager as fm

    win_fonts = [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyhbd.ttc',
                 r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\simsun.ttc']
    for p in win_fonts:
        if os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
            except Exception:
                pass

    available = {f.name for f in fm.fontManager.ttflist}
    for name in font_names:
        if name in available:
            matplotlib.rcParams['font.sans-serif'] = [name]
            matplotlib.rcParams['axes.unicode_minus'] = False
            return name
    # 兜底：模糊匹配
    for f in fm.fontManager.ttflist:
        if any(k in f.name for k in ('YaHei', 'SimHei', 'SimSun', 'DengXian')):
            matplotlib.rcParams['font.sans-serif'] = [f.name]
            matplotlib.rcParams['axes.unicode_minus'] = False
            return f.name
    print('[可视化] 警告：未找到中文字体，图中中文可能乱码')
    return None


def cjk_table_family():
    """交汇图右侧层段清单用的字体族（返回 None = 用 rcParams 默认中文字体）。

    2026-10-06 实测：matplotlib 虽然能扫到 NSimSun / SimSun 字族名，但这两个
    .ttc 在 matplotlib 里取不到中文字形，一旦指定 family= 就会把"层号/流体/
    顶深/底深"整列中文吞掉（只剩 ASCII 还能显示），表现为乱码/空白。
    因此这里统一返回 None，使用 setup_chinese_font() 配置好的默认中文字体
    （微软雅黑），中文与数字都能正常显示；列对齐靠格式串中的固定空格。
    """
    return None


# ---------------------------------------------------------------------------
# 流体分类（与 visualize_composite_log 的 interp_color_map 体系配套）
# ---------------------------------------------------------------------------
FLUID_CLASS = {
    'OIL':            ['Oil', 'OIL', 'oil'],
    'GAS':            ['Gas', 'GAS', 'gas'],
    'OIL_POSSIBLE':   ['OIL_POSSIBLE', 'Poor Oil', 'PoorOil', 'Oil_Water'],
    'GAS_POSSIBLE':   ['GAS_POSSIBLE', 'Possible Gas'],
    'WATER':          ['Water', 'WATER', 'Water_Bearing', 'Oil-Bearing Water'],
    'DRY':            ['Dry', 'DRY', 'Tight'],
}
FLUID_COLOR = {
    'OIL':          '#1a9850',   # 绿
    'GAS':          '#d73027',   # 红
    'OIL_POSSIBLE': '#a6d96a',   # 浅绿
    'GAS_POSSIBLE': '#fc8d59',   # 橙
    'WATER':        '#00a8f8',   # 蓝——取自 symbol/water.png 水层符号主色(用户2026-10-09)
    'DRY':          '#bdbdbd',   # 灰
}
FLUID_LABEL_CN = {
    'OIL': '油层',
    'GAS': '气层',
    'OIL_POSSIBLE': '弱油/油水过渡',
    'GAS_POSSIBLE': '含气可能',
    'WATER': '水层',
    'DRY': '致密/干层',
    'OTHER': '非储层',
}
_LOOKUP = {}
for _k, _v in FLUID_CLASS.items():
    for _s in _v:
        _LOOKUP[str(_s).strip().lower()] = _k


def classify_fluid(interp_value):
    """把 INTERPRETATION 值映射为流体类别。

    Returns
    -------
    str: OIL / GAS / OIL_POSSIBLE / GAS_POSSIBLE / WATER / DRY / OTHER
    """
    if interp_value is None:
        return 'OTHER'
    s = str(interp_value).strip()
    if s == '' or s.lower() in ('nan', 'none', 'undefined', 'nonreservoir',
                                'non-reservoir'):
        return 'OTHER'
    return _LOOKUP.get(s.lower(), 'OTHER')


def _build_segments(data, min_thickness=3.0):
    """把逐点 INTERPRETATION 归并成层段。

    Returns
    -------
    list of dict: {no, fluid, top, bot, thick, cls}
        no      层号（自上而下，从 1 开始）
        fluid   流体类别
        top/bot 起止深度
        cls     该段中部点所在的行索引（用于取代表值）
    """
    if 'MD' not in data.columns or 'INTERPRETATION' not in data.columns:
        return []

    md = pd.to_numeric(data['MD'], errors='coerce').values
    labels = [classify_fluid(v) for v in data['INTERPRETATION'].values]
    n = len(data)

    # 收集连续同类段
    raw = []
    i = 0
    while i < n:
        lab = labels[i]
        if pd.isna(md[i]):
            i += 1
            continue
        j = i + 1
        while j < n and labels[j] == lab:
            j += 1
        raw.append((lab, md[i], md[max(j - 1, i)], i, j))
        i = j

    # 合并薄层到相邻同类段（不同类之间不合并，避免把油气水混在一起）
    merged = []
    for lab, t, b, i0, j0 in raw:
        if merged and merged[-1]['fluid'] == lab:
            merged[-1]['bot'] = b
            merged[-1]['i1'] = j0
        else:
            merged.append({'fluid': lab, 'top': t, 'bot': b, 'i0': i0, 'i1': j0})

    # 厚度过滤 + 统一编号（自上而下）
    out = []
    for seg in merged:
        seg['thick'] = seg['bot'] - seg['top']
        if seg['thick'] < min_thickness:
            continue
        seg['cls'] = (seg['i0'] + seg['i1']) // 2
        out.append(seg)
    for k, seg in enumerate(out):
        seg['no'] = k + 1
    return out


# ---------------------------------------------------------------------------
# 交会图组合表
# (x列候选, y列候选, x标签, y标签, 物理含义, 着色模式)
# 注意 Sw 的候选顺序：SW_A（本次 Archie 重算）优先于 SW/Sw（logInt 或厂家预置）。
# 原因：本井 LAS 自带 SW 全段 100%（厂家在非储层置满），直接用会把所有点判为水层。
# 着色模式（2026-10-08 统一岩性符号）：'fluid'=按流体类型（FLUID_COLOR）；
#   'lith'=按岩性着色，颜色由 LITH_BG_COLORS 提供，
#   与综合图岩性道/PROFILE道/图例完全同一套。
# ---------------------------------------------------------------------------
CROSSPLOTS = [
    (['RT', 'RD', 'LLD', 'R90'], ['PHI_DN', 'PHI', 'PHIE', 'POR', 'PHI_DN_c'],
     '电阻率 RT (Ω·m, 对数)', '孔隙度 φ (%)', '储集岩物性：电阻率-孔隙度', 'fluid'),
    (['SW_A', 'SW', 'Sw'], ['PHI_DN_c', 'PHI', 'PHIE', 'POR'],
     '含水饱和度 Sw (%)', '孔隙度 φ (%)', '含油气性：含水饱和度-孔隙度', 'fluid'),
    (['GR', 'GR_XMAC'], ['DEN', 'ZDEN', 'RHOB'],
     '自然伽马 GR (API)', '密度 DEN (g/cm³)', '岩性识别：伽马-密度', 'lith'),
    (['GR', 'GR_XMAC'], ['CNL', 'CNCF', 'NPHI'],
     '自然伽马 GR (API)', '中子 CNL (%)', '岩性识别：伽马-中子', 'lith'),
    (['RT', 'RD'], ['VSH_GR', 'VSH', 'VSHALE'],
     '电阻率 RT (Ω·m, 对数)', '泥质含量 Vsh (%)', '储层评价：电阻率-泥质', 'fluid'),
]


def _pick_column(data, cands):
    for c in cands:
        if c in data.columns:
            return c
    return None


def _pct(series, lo, hi):
    """按分位数设轴范围，避免离群点压扁主体。"""
    v = pd.to_numeric(series, errors='coerce').dropna()
    if len(v) == 0:
        return (0, 1)
    a, b = np.percentile(v, [lo, hi])
    if b <= a:
        b = a + 1
    pad = (b - a) * 0.05
    return (max(a - pad, 0 if a >= 0 else a - pad), b + pad)

def _pct_robust(series, lo, hi):
    """【2026-10-29 R41 用户定案】岩性面板稳健截轴。

    先 IQR 围栏（P25-5×IQR, P75+5×IQR）剔除物理不可能的饱和/哨兵值
    （如 CNL=1371.8 的坏点占 1.15%>0.5%，单次 P99.5 本身被污染——
    伽马-中子面板 y 轴曾被拉到 1400%），再取 P0.5-P99.5 分位截断。
    仅岩性面板（mode=lith，数据含全部岩性点）使用；流体面板数据
    已经储层过滤，沿用单次 _pct。
    """
    v = pd.to_numeric(series, errors='coerce').dropna()
    if len(v) == 0:
        return (0, 1)
    p25, p75 = np.percentile(v, [25, 75])
    iqr = p75 - p25
    if iqr > 0:
        _v = v[(v >= p25 - 5 * iqr) & (v <= p75 + 5 * iqr)]
        if len(_v) >= 10:      # 围栏几乎全剔时退回原值（防误杀窄分布）
            v = _v
    a, b = np.percentile(v, [lo, hi])
    if b <= a:
        b = a + 1
    pad = (b - a) * 0.05
    return (max(a - pad, 0 if a >= 0 else a - pad), b + pad)


def _segment_table(segs, d, xv, yv, unit='ft'):
    """生成右侧层段清单文本。"""
    lines = ['层号  流体      顶深     底深     厚度    %s' % unit,
             '-' * 46]
    shown = 0
    for s in segs:
        if s['fluid'] == 'OTHER':
            continue
        i = s['cls']
        a = xv.iloc[i]
        b = yv.iloc[i]
        fa = '-' if pd.isna(a) else '%.3g' % a
        fb = '-' if pd.isna(b) else '%.3g' % b
        lines.append('%-4d  %-9s %-7.0f  %-7.0f  %-6.1f  %s / %s'
                     % (s['no'], FLUID_LABEL_CN.get(s['fluid'], s['fluid'])[:4],
                        s['top'], s['bot'], s['thick'], fa, fb))
        shown += 1
        if shown >= 34:
            lines.append('... 其余见成果表')
            break
    if shown == 0:
        lines.append('（无可解释的油气水层段）')
    return '\n'.join(lines)


def _now():
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def patch_depth_unit(unit='ft', major_step=None, minor_step=None, scale_den=None):
    """设置深度道单位（'ft' / 'm'）。

    【2026-10-14 融合】logvis 原生 _setup_depth_track 已支持 m/ft：
    单位由 DEPTH_UNIT 全局控制，主/次刻度步长读图版 depth_scale，
    比例尺读 figure.curve_scale（英制 1:240 / 公制 1:200），
    因此不再猴子补丁替换 _setup_depth_track，仅直调 set_depth_unit。
    major_step/minor_step/scale_den 参数仅为兼容旧调用签名保留，不再使用。
    """
    unit = _DEPTH_UNIT.get(str(unit).lower(), 'ft')
    set_depth_unit(unit)
    _ms = _tpl_depth_steps(unit)[0]
    print('[可视化] 深度道已适配为 %s（主刻度 %g %s）' % (unit, _ms, unit))
    return True


def visualize_fluid_crossplots(data, results=None, output_dir='output',
                               depth_unit='ft', min_thickness=3.0,
                               gas_data=None, dpi=150, verbose=True,
                               lith_colors=None, lith_cn=None,
                               crossplots=None, figsize=None):
    """生成流体交会图（气红 / 油深绿 / 水蓝，info.json 流体颜色组可改，按层号标注）。

    Parameters
    ----------
    data : DataFrame
        需含 MD、INTERPRETATION 两列，以及交会图所需的曲线列
        （RT/RD、PHI/POR、SW、GR、DEN、CNL、VSH 等，列名可多选）
    lith_colors : dict, optional
        岩性→颜色映射（logvis.LITH_BG_COLORS，统一符号表）。
        提供时岩性识别交会图按 LITHOLOGY 列着色，与综合图同一套颜色。
    lith_cn : dict, optional
        岩性英文→中文名映射（logInt LITHOLOGY_RULES 的 cn），用于岩性图例。
    results : dict, optional
        含 well_name、output_dir 等，用于图头标注
    output_dir : str
        输出目录，将按井名创建子目录
    depth_unit : str
        深度单位标签，仅用于轴标注
    min_thickness : float
        层段最小厚度（小于该值不参与编号，避免碎层）
    gas_data : DataFrame, optional
        气测数据，若提供则与气层段合并成图版（副图）
    dpi : int
        输出分辨率
    crossplots : list[dict], optional
        交会图组合表（cppt.json 图版 crossplots）：每项
        {x_curves, y_curves, x_label, y_label, purpose, mode}；
        None 用内置 CROSSPLOTS。
    figsize : tuple, optional
        画布尺寸（英寸）；None 用内置 (11.5, 8.6)。

    Returns
    -------
    list[str]: 生成的图片路径
    """
    from matplotlib.lines import Line2D

    if data is None or 'MD' not in data.columns:
        print('[交会图] 数据缺少 MD 列，无法生成')
        return []

    results = results or {}

    # 【2026-10-14 用户定案】流体家族统一色：气=红 / 油=深绿 / 水=蓝（与全局一致）。
    # <井名>info.json "流体颜色"组非空值优先（gas_color/oil_color/water_color，
    # 人工修改后直接生效）；OIL/OIL_POSSIBLE→油色, GAS/GAS_POSSIBLE→气色,
    # WATER→水色, DRY 保持灰
    _xw = _load_well_info_json(results)
    _fam_color = {
        'OIL':          str(_xw.get('oil_color') or '').strip() or '#1a9850',
        'OIL_POSSIBLE': str(_xw.get('oil_color') or '').strip() or '#1a9850',
        'GAS':          str(_xw.get('gas_color') or '').strip() or '#d73027',
        'GAS_POSSIBLE': str(_xw.get('gas_color') or '').strip() or '#d73027',
        'WATER':        str(_xw.get('water_color') or '').strip() or '#00a8f8',
        'DRY':          '#bdbdbd',
    }
    well = str(results.get('well_name', 'Unknown'))
    # 【2026-10-14 修复】调用方(logInt Step6/quicklook)传来的 output_dir 已是
    # 井目录(output/<井名>)，原无条件再追加井名致双嵌套 output/<井名>/<井名>/
    # (旧版PNG同样错位，PDF成为唯一交付物后暴露)——已带井名时不再追加
    if os.path.basename(os.path.normpath(str(output_dir))).lower() == well.lower():
        outdir = str(output_dir)
    else:
        outdir = os.path.join(output_dir, well)
    os.makedirs(outdir, exist_ok=True)

    d = data.copy().sort_values('MD').reset_index(drop=True)
    segs = _build_segments(d, min_thickness=min_thickness)
    if verbose:
        print('[交会图] 识别层段 %d 个' % len(segs))
        cnt = {}
        for s in segs:
            cnt[s['fluid']] = cnt.get(s['fluid'], 0) + 1
        for k, v in sorted(cnt.items()):
            print('        %-14s %3d 段  (%s)' % (FLUID_LABEL_CN.get(k, k), v, k))

    # 每个层段的代表点（取段中部，避免边界效应）
    xs, ys, ns, fs, tops, bots = [], [], [], [], [], []
    for s in segs:
        m = (d.MD >= s['top']) & (d.MD <= s['bot'])
        if not m.any():
            continue
        xs.append(s['cls'])
        ys.append(s['cls'])
        ns.append(s['no'])
        fs.append(s['fluid'])
        tops.append(s['top'])
        bots.append(s['bot'])

    paths = []
    # 【2026-10-14 只出一次 PDF】各交会图 PNG 为中间产物写临时目录，
    # 循环结束后合并为单文件多页 PDF 交付
    _xp_tmpdir = None

    # 【2026-10-10 图版化】交会图组合表可配：crossplots 参数（cppt.json 图版）
    # 未传时用内置 CROSSPLOTS（5 组：RT-PHI流体 / SW-PHI流体 / GR-DEN岩性 / GR-CNL岩性 / RT-VSH流体）
    _plots = crossplots or CROSSPLOTS
    _figsize_use = figsize or (11.5, 8.6)

    for _cp in _plots:
        if isinstance(_cp, dict):
            xc = _cp.get('x_curves') or []
            yc = _cp.get('y_curves') or []
            xlab = _cp.get('x_label') or ''
            ylab = _cp.get('y_label') or ''
            purpose = _cp.get('purpose') or ''
            mode = _cp.get('mode') or 'fluid'
        else:
            xc, yc, xlab, ylab, purpose, mode = _cp
        # 【R37 用户定案】面板级开关：包含非储层点——煤/碳质泥岩判别
        # 面板需要泥岩基线与煤/碳质泥岩点本身（默认交会图只绘储层数据）
        include_nonres = (bool(_cp.get('include_nonres'))
                          if isinstance(_cp, dict) else False)
        cx = _pick_column(d, xc)
        cy = _pick_column(d, yc)
        if cx is None or cy is None:
            if verbose:
                print('[交会图] 跳过 ' + str(purpose) + '（缺列: ' + str(cx) + ' / ' + str(cy) + '）')
            continue

        xlog = '对数' in xlab
        xv = pd.to_numeric(d[cx], errors='coerce')
        yv = pd.to_numeric(d[cy], errors='coerce')
        # 百分数化：SW/GR/VSH 若为 0-1 小数则乘 100
        for arr, cols in ((xv, xc), (yv, yc)):
            pass
        if xv.max(skipna=True) and xv.max(skipna=True) <= 1.01:
            xv = xv * 100
        if yv.max(skipna=True) and yv.max(skipna=True) <= 1.01:
            yv = yv * 100

        fig, ax = plt.subplots(figsize=_figsize_use)
        fig.subplots_adjust(top=0.885, bottom=0.085, left=0.085, right=0.975)

        # 【2026-10-15 用户定案】交会图只用储层数据——泥岩等非储层点不画
        # （此前灰色底色点已去除，INTERPRETATION∈{OIL,GAS,WATER,DRY,*_POSSIBLE}
        # 才上图；other 掩码仍用于岩性交会图 _res_mask 过滤）
        if include_nonres:
            other = pd.Series(False, index=d.index)   # 非储层点也上图
        else:
            other = d['INTERPRETATION'].map(classify_fluid) == 'OTHER'

        _seen = []
        if mode == 'lith' and lith_colors and 'LITHOLOGY' in d.columns:
            # 【2026-10-08 统一岩性符号】岩性交会图按 LITHOLOGY 着色，
            # 颜色来自 LITH_BG_COLORS —— 与岩性道/PROFILE道/
            # 图例完全同一套（一处一功能：颜色只维护一份）
            _liths = d['LITHOLOGY'].astype(str).str.lower().str.strip()
            _res_mask = ~other
            for lk in _liths[_res_mask].value_counts().index:
                m = (_liths == lk) & _res_mask
                if not m.any():
                    continue
                _seen.append(lk)
                ax.scatter(xv[m], yv[m], s=13,
                           c=lith_colors.get(lk, '#D3D3D3'),
                           alpha=0.80, lw=0.3, edgecolors='k',
                           label='%s (%s)' % ((lith_cn or {}).get(lk, lk), lk),
                           zorder=3)
        else:
            # 三类流体
            order = ['OIL', 'GAS', 'OIL_POSSIBLE', 'GAS_POSSIBLE', 'WATER', 'DRY']
            for fk in order:
                m = d['INTERPRETATION'].map(classify_fluid) == fk
                if not m.any():
                    continue
                ax.scatter(xv[m], yv[m], s=13, c=_fam_color[fk], alpha=0.80,
                           lw=0.3, edgecolors='k',
                           label='%s (%s)' % (FLUID_LABEL_CN[fk], fk), zorder=3)

        # 层号标注（按层段中点，深度递增向上排）
        ann = []
        for k, s in enumerate(segs):
            i = s['cls']
            xv_i, yv_i = xv.iloc[i], yv.iloc[i]
            if pd.isna(xv_i) or pd.isna(yv_i):
                continue
            if s['fluid'] == 'OTHER':
                continue
            ann.append((xv_i, yv_i, s['no'], s['fluid'], s['top'], s['bot']))
        for xv_i, yv_i, no, fk, tp, bt in ann:
            ax.annotate(str(no), (xv_i, yv_i), fontsize=7.5,
                        fontweight='bold', color='k', ha='center', va='center',
                        zorder=6,
                        bbox=dict(boxstyle='circle,pad=0.18', fc='white',
                                  ec=_fam_color[fk], lw=1.1, alpha=0.92))

        if xlog:
            ax.set_xscale('log')
        ax.set_xlabel(xlab, fontsize=11)
        ax.set_ylabel(ylab, fontsize=11)
        ax.grid(alpha=0.3, lw=0.5)
        # 【R41 用户定案】岩性面板（含全部数据，可能有饱和坏点）用稳健截轴；
        # 流体面板（只绘储层数据）维持单次分位截断
        if mode == 'lith':
            ax.set_xlim(_pct_robust(xv, 0.5, 99.5))
            ax.set_ylim(_pct_robust(yv, 0.5, 99.5))
        else:
            ax.set_xlim(_pct(xv, 0.5, 99.5))
            ax.set_ylim(_pct(yv, 0.5, 99.5))

        # 右侧层段清单
        txt = _segment_table(segs, d, xv, yv, depth_unit)
        ax.text(1.012, 0.5, txt, transform=ax.transAxes, fontsize=7.2,
                va='center', ha='left', family=cjk_table_family(),
                bbox=dict(boxstyle='round,pad=0.5', fc='#fbfbfb', ec='#999'))

        # 图例按 mode 分支：【2026-10-08 统一岩性符号】lith 模式用方形+岩性色
        # （与综合图岩性道/PROFILE道同一套 LITH_BG_COLORS），流体模式保持原样
        if mode == 'lith' and _seen:
            handles = [Line2D([0], [0], marker='s', color='w',
                              markerfacecolor=lith_colors.get(k, '#D3D3D3'),
                              markeredgecolor='k', markersize=9,
                              label='%s (%s)' % ((lith_cn or {}).get(k, k), k))
                       for k in _seen]
            _legend_title = '岩性'
        else:
            handles = [Line2D([0], [0], marker='o', color='w',
                              markerfacecolor=_fam_color[k],
                              markeredgecolor='k', markersize=9, label=FLUID_LABEL_CN[k])
                       for k in FLUID_COLOR if k in cnt]
            _legend_title = '流体类型'
        ax.legend(handles=handles, loc='upper left', fontsize=8.5,
                  title=_legend_title, title_fontsize=9, framealpha=0.92)

        fig.suptitle('%s  %s' % (well, purpose), fontsize=14, y=0.975)
        if mode == 'lith':
            _note = ('点色 = 岩性（与综合图岩性道同一套图例颜色）；'
                     '圆圈内数字为层号（自上而下）')
        else:
            _note = '油 = 深绿，气 = 红，水 = 蓝；圆圈内数字为层号（自上而下）'
        fig.text(0.5, 0.935, _note,
                 ha='center', fontsize=9.5, color='#444')
        fig.text(0.5, 0.912,
                 '数据源：%s　层段最小厚度 %.1f %s　共 %d 个可解释层段'
                 % (cx, min_thickness, depth_unit, len(segs)),
                 ha='center', fontsize=8.5, color='#777')

        ts = results.get('timestamp') or _now()
        # 文件名带轴名，避免同"用途"的多个交会图相互覆盖
        slug = '%s-%s' % (purpose.split('：')[0], '%s_vs_%s' % (cx, cy))
        slug = ''.join(ch if ch.isalnum() or ch in '-_.' else '_'
                       for ch in slug)
        fn = '%s_fluid_crossplot_%s_%s.png' % (well, slug, ts)
        # 【2026-10-14 只出一次 PDF】PNG 写临时目录（中间产物）
        if _xp_tmpdir is None:
            _xp_tmpdir = tempfile.mkdtemp(prefix='%s_xplot_' % well)
        p = os.path.join(_xp_tmpdir, fn)
        fig.savefig(p, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(p)
        if verbose:
            logger.debug('[交会图] %s 中间图已生成: %s',
                         purpose, os.path.basename(p))

    # ---- 【2026-10-14 只出一次 PDF】合并为单文件多页 PDF ----
    # 页面尺寸 = 各交会图 px/dpi*72pt 物理尺寸（与综合图/快速解释图同口径）
    _pdf_out = None
    try:
        import fitz as _fitz
        from PIL import Image as _PILx
        _PILx.MAX_IMAGE_PIXELS = None
        _pdf_out = os.path.join(outdir, '%s_crossplot_%s.pdf' % (well, ts))
        _doc = _fitz.open()
        for _p in paths:
            if not _p or not os.path.exists(_p):
                continue
            _imx = _PILx.open(_p)
            _wpx, _hpx = _imx.size
            _imx.close()
            _wp = _wpx * 72.0 / float(dpi or 150)
            _hp = _hpx * 72.0 / float(dpi or 150)
            _pg = _doc.new_page(width=_wp, height=_hp)
            _pg.insert_image(_fitz.Rect(0, 0, _wp, _hp), filename=_p)
        if _doc.page_count:
            _doc.save(_pdf_out, deflate=True)
            _doc.close()
        else:
            _doc.close()
            _pdf_out = None
    except Exception as _pe:
        logger.warning('交会图 PDF 合并失败(保留PNG): %s', _pe)
        _pdf_out = None
    if _pdf_out:
        # PDF 成功：中间 PNG 随临时目录一并删除，只交付一个 PDF
        shutil.rmtree(_xp_tmpdir, ignore_errors=True) if _xp_tmpdir else None
        paths = [_pdf_out]
        if verbose:
            print('[交会图] 已保存: %s' % _pdf_out)
    else:
        # PDF 失败兜底：中间 PNG 移入输出目录，避免零交付
        _moved = []
        for _p in paths:
            try:
                if _p and os.path.exists(_p):
                    _dst = os.path.join(outdir, os.path.basename(_p))
                    shutil.move(_p, _dst)
                    _moved.append(_dst)
            except Exception:
                pass
        if _moved:
            paths = _moved
            if verbose:
                print('[交会图] PDF 生成失败, 已保留 PNG %d 张' % len(paths))

    return paths


def enhance_visualization(data, results, gas_data=None,
                          output_dir=None, depth_unit='ft'):
    """logInt 的一站式扩展：深度单位适配 + 流体交会图。

    在 logInt 的可视化步骤后调用即可（见 logInt 中 visualize_all 扩展点）。
    """
    out = output_dir or results.get('output_dir', 'output')
    setup_chinese_font()
    patch_depth_unit(depth_unit)
    return visualize_fluid_crossplots(
        data, results, output_dir=out, depth_unit=depth_unit,
        gas_data=gas_data)


def visualize_fluid(data, results, output_dir=None, gas_data=None,
                    depth_unit='auto', min_thickness=3.0):
    """logvis 的流体交会图入口（功能已于 2026-10-14 原生并入本模块）。

    【2026-10-08 统一岩性符号】岩性交会图的着色/图例传 入 LITH_BG_COLORS
    （与岩性道/PROFILE道/图头图例同一套颜色）与 logInt.LITHOLOGY_RULES
    的中文岩性名。logInt 顶层 import 本模块，故这里必须延迟 import 防循环。
    """
    setup_chinese_font()
    if depth_unit and str(depth_unit).lower() in ('m', 'ft'):
        patch_depth_unit(str(depth_unit).lower())
    out = output_dir or results.get('output_dir', 'output')
    # 岩性统一符号传参（延迟 import 避免与 logInt 循环导入）
    _lith_colors = LITH_BG_COLORS
    _lith_cn = {}
    try:
        from logInt import LITHOLOGY_RULES
        _lith_cn = {r['key']: r['cn'] for r in LITHOLOGY_RULES if 'cn' in r}
    except Exception as _e:
        logger.debug('读取 LITHOLOGY_RULES 中文岩性名失败: %s', _e)
    # 【2026-10-10 图版化】交汇图直接调用 templates/cppt.json 图版：
    # crossplots（组合表）/ figure.figsize / figure.dpi / min_thickness 可配
    _tpl = load_plot_template('cppt') or {}
    _tpl_fig = _tpl.get('figure') or {}
    _crossplots = _tpl.get('crossplots') or None
    _figsize = _tpl_fig.get('figsize') or None
    _dpi = _tpl_fig.get('dpi') or None
    _mt = _tpl.get('min_thickness')
    if isinstance(_mt, (int, float)):
        min_thickness = float(_mt)
    return visualize_fluid_crossplots(
        data, results, output_dir=out, depth_unit=depth_unit or 'ft',
        gas_data=gas_data, min_thickness=min_thickness,
        lith_colors=_lith_colors, lith_cn=_lith_cn,
        crossplots=_crossplots, figsize=_figsize, dpi=_dpi)
