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
    'halite': 'Halite.png',
    'salt': 'Salt.png',
    'volcanic': 'DBOS_Volcanic.png',
    'carbonate': 'Limestone.png',
    'mixed': 'Sandstone.png',
    'coal': 'Coal.png',
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
    '碳酸盐岩': 'Limestone.png',
    '煤': 'Coal.png',
    '煤层': 'Coal.png',
    '黄铁矿': 'Pyrite.png',
    '砾岩': 'Conglomerate.png',
    'unknown': 'Unknown.png',
}
# ======================================


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
                _lithology_symbol_cache[lith_name] = (img, fill_ratio)
                return img, fill_ratio
            except Exception as e:
                logger.warning(f"加载岩性符号图片失败 {img_path}: {e}")

    _lithology_symbol_cache[lith_name] = (None, 1.0)
    return None, 1.0


def _draw_lithology_tiles(ax, lith_name, seg_start_md, seg_end_md):
    """
    在岩性道上用固定大小的单元图案逐块平铺。
    
    **关键保证**：每个完整 tile 使用独立的 imshow，extent 精确为 TILE_DEPTH_M 米。
    无论段长多少，每个 tile 的像素和深度跨度完全一致，绝不拉伸压缩。
    段尾不足一个 tile 的部分用裁剪后的图像精确填充剩余深度。
    
    参数:
        ax: matplotlib Axes
        lith_name: 岩性名称（小写）
        seg_start_md: 段顶深度（较小值）
        seg_end_md: 段底深度（较大值）
    """
    # 岩性背景色映射（先绘制背景色，再叠符号图案）
    lith_bg_colors = {
        'sandstone': '#FFFF00', 'shale': '#228B22', 'mudstone': '#228B22',
        'limestone': '#87CEEB', 'dolomite': '#B0E0E6',
        'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
        'halite': '#FF69B4', 'salt': '#FF69B4',
        'volcanic': '#FF0000', 'coal': '#333333', 'pyrite': '#FFD700',
        'carbonate': '#87CEEB', 'mixed': '#D3D3D3', 'conglomerate': '#D2B48C',
        'unknown': '#D3D3D3',
        # 中文名称
        '砂岩': '#FFFF00', '泥岩': '#228B22', '页岩': '#228B22',
        '灰岩': '#87CEEB', '白云岩': '#B0E0E6',
        '硬石膏': '#FFC0CB', '石膏': '#FFC0CB',
        '盐岩': '#FF69B4', '盐': '#FF69B4',
        '火山岩': '#FF0000', '煤': '#333333', '煤层': '#333333',
        '黄铁矿': '#FFD700', '砾岩': '#D2B48C',
        '碳酸盐岩': '#87CEEB', 'mixed': '#D3D3D3',
    }
    bg_color = lith_bg_colors.get(lith_name, '#D3D3D3')
    # 先绘制背景色
    ax.fill_betweenx([seg_start_md, seg_end_md], 0, SYMBOL_X_EXTENT, color=bg_color, alpha=0.9)

    # 砂岩使用scatter绘制真正的圆点，避免image tile在1:200比例下点被拉伸成横线
    if lith_name in ('sandstone', '砂岩'):
        dot_spacing = 0.4  # 每0.4米一排，排间距大一些
        # 4排循环，每排4-5个点，位置交错不规则
        rows_pattern = [
            [0.10, 0.30, 0.55, 0.80],           # 排0: 4点
            [0.05, 0.25, 0.50, 0.70, 0.90],     # 排1: 5点
            [0.15, 0.40, 0.60, 0.85],           # 排2: 4点
            [0.08, 0.35, 0.50, 0.75, 0.92],     # 排3: 5点
        ]
        depths = np.arange(seg_start_md + dot_spacing / 2, seg_end_md, dot_spacing)
        for i, depth in enumerate(depths):
            x_pos = rows_pattern[i % 4]
            for x in x_pos:
                ax.plot(x * SYMBOL_X_EXTENT, depth, 'o', color='black',
                        markersize=1.5, markeredgewidth=0, zorder=10)
        return

    img, fill_ratio = _load_lithology_symbol(lith_name)
    if img is None:
        return
    
    # 准备单个 tile 图像（缩放为统一尺寸）
    try:
        from PIL import Image
        img_pil = Image.fromarray((img * 255).astype(np.uint8) if img.max() <= 1.0 else img.astype(np.uint8))
        img_pil = img_pil.resize((SYMBOL_TILE_PX, SYMBOL_TILE_PX), Image.NEAREST)
        tile = np.array(img_pil) / 255.0
    except Exception:
        tile = img
    
    # 逐个放置 tile，深度从上往下增大
    # seg_start_md = 较小深度（图上方）, seg_end_md = 较大深度（图下方）
    current_top = seg_start_md      # 较小深度（图上方）
    seg_bottom = seg_end_md         # 较大深度（图下方）
    
    while seg_bottom - current_top > 1e-6:  # 尚未到达段底（向下推进）
        remaining = seg_bottom - current_top
        if remaining >= TILE_DEPTH_M:
            # 完整 tile：向下推进 TILE_DEPTH_M 米
            tile_bottom = current_top + TILE_DEPTH_M  # 更深 = 值更大
            ax.imshow(tile, extent=[0, SYMBOL_X_EXTENT, tile_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            current_top = tile_bottom  # 推进到 tile 底部，继续向下
        else:
            # 尾部不完整 tile：填充剩余深度
            frac = remaining / TILE_DEPTH_M
            crop_pixels = max(1, int(SYMBOL_TILE_PX * frac + 0.5))
            partial_tile = tile[:crop_pixels, :, :]
            ax.imshow(partial_tile, extent=[0, SYMBOL_X_EXTENT, seg_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            break


def _draw_lithology_tiles_profile(ax, lith_name, seg_start_md, seg_end_md):
    """
    在profile道上用固定大小的单元图案逐块平铺，与岩性道(_draw_lithology_tiles)完全一致的绘制规则。
    唯一区别：profile道占满整个道宽(0-1)，岩性道占SYMBOL_X_EXTENT。
    
    参数:
        ax: matplotlib Axes
        lith_name: 岩性名称（小写）
        seg_start_md: 段顶深度（较小值）
        seg_end_md: 段底深度（较大值）
    """
    # 岩性背景色映射（与_draw_lithology_tiles一致）
    lith_bg_colors = {
        'sandstone': '#FFFF00', 'shale': '#228B22', 'mudstone': '#228B22',
        'limestone': '#87CEEB', 'dolomite': '#B0E0E6',
        'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
        'halite': '#FF69B4', 'salt': '#FF69B4',
        'volcanic': '#FF0000', 'coal': '#333333', 'pyrite': '#FFD700',
        'carbonate': '#87CEEB', 'mixed': '#D3D3D3', 'conglomerate': '#D2B48C',
        'unknown': '#D3D3D3',
        '砂岩': '#FFFF00', '泥岩': '#228B22', '页岩': '#228B22',
        '灰岩': '#87CEEB', '白云岩': '#B0E0E6',
        '硬石膏': '#FFC0CB', '石膏': '#FFC0CB',
        '盐岩': '#FF69B4', '盐': '#FF69B4',
        '火山岩': '#FF0000', '煤': '#333333', '煤层': '#333333',
        '黄铁矿': '#FFD700', '砾岩': '#D2B48C',
        '碳酸盐岩': '#87CEEB',
    }
    bg_color = lith_bg_colors.get(lith_name, '#D3D3D3')
    # profile道占满整个道宽(0-1)
    ax.fill_betweenx([seg_start_md, seg_end_md], 0, 1.0, color=bg_color, alpha=0.9)

    # 砂岩使用scatter绘制圆点（与岩性道完全一致的图案参数）
    if lith_name in ('sandstone', '砂岩'):
        dot_spacing = 0.4
        rows_pattern = [
            [0.10, 0.30, 0.55, 0.80],
            [0.05, 0.25, 0.50, 0.70, 0.90],
            [0.15, 0.40, 0.60, 0.85],
            [0.08, 0.35, 0.50, 0.75, 0.92],
        ]
        depths = np.arange(seg_start_md + dot_spacing / 2, seg_end_md, dot_spacing)
        for i, depth in enumerate(depths):
            x_pos = rows_pattern[i % 4]
            for x in x_pos:
                # profile道宽度为1.0，x位置直接按比例放置
                ax.plot(x * 1.0, depth, 'o', color='black',
                        markersize=1.5, markeredgewidth=0, zorder=10)
        return

    # 其他岩性：使用与岩性道相同的tile绘制规则
    img, fill_ratio = _load_lithology_symbol(lith_name)
    if img is None:
        return

    try:
        from PIL import Image
        img_pil = Image.fromarray((img * 255).astype(np.uint8) if img.max() <= 1.0 else img.astype(np.uint8))
        img_pil = img_pil.resize((SYMBOL_TILE_PX, SYMBOL_TILE_PX), Image.NEAREST)
        tile = np.array(img_pil) / 255.0
    except Exception:
        tile = img

    current_top = seg_start_md
    seg_bottom = seg_end_md

    while seg_bottom - current_top > 1e-6:
        remaining = seg_bottom - current_top
        if remaining >= TILE_DEPTH_M:
            tile_bottom = current_top + TILE_DEPTH_M
            # profile道占满整个道宽(0-1)
            ax.imshow(tile, extent=[0, 1.0, tile_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            current_top = tile_bottom
        else:
            frac = remaining / TILE_DEPTH_M
            crop_pixels = max(1, int(SYMBOL_TILE_PX * frac + 0.5))
            partial_tile = tile[:crop_pixels, :, :]
            ax.imshow(partial_tile, extent=[0, 1.0, seg_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            break


def _draw_lithology_in_xrange(ax, lith_name, seg_start_md, seg_end_md, x_left, x_right):
    """
    在指定的x范围内绘制岩性符号，使用与岩性道(_draw_lithology_tiles)完全相同的绘制规则。
    用于profile道，确保符号密度和样式与岩性道一致。
    
    tile填满band宽度（extent=[x_left, x_right]），背景色+tile图案一体化，
    保证颜色纹理始终对应，无空白无外扩。

    参数:
        ax: matplotlib Axes
        lith_name: 岩性名称（小写）
        seg_start_md: 段顶深度（较小值）
        seg_end_md: 段底深度（较大值）
        x_left: x范围左边界
        x_right: x范围右边界
    """
    seg_width = x_right - x_left
    if seg_width < 0.001:  # 太窄不绘制（降低阈值）
        return

    # 岩性背景色映射（与_draw_lithology_tiles一致）
    lith_bg_colors = {
        'sandstone': '#FFFF00', 'shale': '#228B22', 'mudstone': '#228B22',
        'limestone': '#87CEEB', 'dolomite': '#B0E0E6',
        'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
        'halite': '#FF69B4', 'salt': '#FF69B4',
        'volcanic': '#FF0000', 'coal': '#333333', 'pyrite': '#FFD700',
        'carbonate': '#87CEEB', 'mixed': '#D3D3D3', 'conglomerate': '#D2B48C',
        'unknown': '#D3D3D3',
        '砂岩': '#FFFF00', '泥岩': '#228B22', '页岩': '#228B22',
        '灰岩': '#87CEEB', '白云岩': '#B0E0E6',
        '硬石膏': '#FFC0CB', '石膏': '#FFC0CB',
        '盐岩': '#FF69B4', '盐': '#FF69B4',
        '火山岩': '#FF0000', '煤': '#333333', '煤层': '#333333',
        '黄铁矿': '#FFD700', '砾岩': '#D2B48C',
        '碳酸盐岩': '#87CEEB',
    }
    bg_color = lith_bg_colors.get(lith_name, '#D3D3D3')
    # 背景色精确填充到x_left~x_right（保证无空白、无外扩）
    ax.fill_betweenx([seg_start_md, seg_end_md], x_left, x_right, color=bg_color, alpha=0.95, zorder=9)

    # 砂岩使用scatter绘制圆点（与岩性道完全一致）
    if lith_name in ('sandstone', '砂岩'):
        dot_spacing = 0.4
        rows_pattern = [
            [0.10, 0.30, 0.55, 0.80],
            [0.05, 0.25, 0.50, 0.70, 0.90],
            [0.15, 0.40, 0.60, 0.85],
            [0.08, 0.35, 0.50, 0.75, 0.92],
        ]
        depths = np.arange(seg_start_md + dot_spacing / 2, seg_end_md, dot_spacing)
        for i, depth in enumerate(depths):
            x_pos = rows_pattern[i % 4]
            for x in x_pos:
                ax.plot(x_left + x * seg_width, depth, 'o', color='black',
                        markersize=1.5, markeredgewidth=0, zorder=10)
        return

    # 其他岩性：使用tile图片填充（与岩性道相同的图片，填满band宽度）
    img, fill_ratio = _load_lithology_symbol(lith_name)
    if img is None:
        return

    try:
        from PIL import Image
        img_pil = Image.fromarray((img * 255).astype(np.uint8) if img.max() <= 1.0 else img.astype(np.uint8))
        # 使用256px tile（与岩性道一致），NEAREST插值（快速）
        tile_px = 256
        img_pil = img_pil.resize((tile_px, tile_px), Image.NEAREST)
        tile = np.array(img_pil) / 255.0
    except Exception:
        tile = img

    current_top = seg_start_md
    seg_bottom = seg_end_md

    while seg_bottom - current_top > 1e-6:
        remaining = seg_bottom - current_top
        if remaining >= TILE_DEPTH_M:
            tile_bottom = current_top + TILE_DEPTH_M
            ax.imshow(tile, extent=[x_left, x_right, tile_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            current_top = tile_bottom
        else:
            frac = remaining / TILE_DEPTH_M
            crop_pixels = max(1, int(tile_px * frac + 0.5))
            partial_tile = tile[:crop_pixels, :, :]
            ax.imshow(partial_tile, extent=[x_left, x_right, seg_bottom, current_top],
                     aspect='auto', interpolation='nearest',
                     clip_on=True, zorder=10)
            break


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


def visualize_composite_log(data, results, gas_data=None):
    """可视化综合测井图，可选气测数据道
    
    Args:
        data: 主测井数据 DataFrame，必须包含MD列
        results: 结果字典，包含 well_name, output_dir, las_info 等
        gas_data: 可选的气测数据 DataFrame，包含MD和气体组分列（如TG, C1, C2等）
    """
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
            'MSFL': ['MSFL'],
            'LLS': ['LLS'],
            'LLD': ['LLD', 'RT', 'ILD', 'R90']
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
        
        # 计算曲线区高度（1:200比例）
        curve_height_cm = depth_range * 100 / 200
        curve_height_inch = curve_height_cm * cm_to_inch
        
        # 计算LAS信息区高度（4列，5行数据 + 3部分图例*2行，每行约1.3cm）
        las_height_cm = 11 * 1.3  # 5行数据 + 6行图例，增加高度使图例方块更清晰
        las_height_inch = las_height_cm * cm_to_inch
        
        # 总高度 = 图名高度 + 图名-LAS间隔 + LAS高度 + 图头区高度 + 曲线区高度
        # 去掉LAS-图头区间隔，让LAS信息区直接紧贴图头区，避免黑色带状区域
        total_height_inch = curve_height_inch + header_height_inch + las_height_inch + title_las_gap_inch + title_height_inch
        total_height_inch = max(total_height_inch, 14)
        
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
            
            # 收集图例数据
            lith_types_raw = []
            if has_enough_curves and 'LITHOLOGY' in data.columns:
                unique_liths = set(data['LITHOLOGY'].dropna().unique())
                lith_types_raw = sorted([str(l).strip().title() for l in unique_liths if str(l).strip()])
            if not lith_types_raw:
                lith_types_raw = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
            lith_types = [lt for lt in lith_types_raw if lt.lower() not in ('mixed',)]
            if not lith_types:
                lith_types = ['Sandstone', 'Shale', 'Limestone', 'Dolomite']
            facies_items = ['Channel', 'Floodplain', 'Delta Front', 'Prodelta']
            interp_items = ['Oil', 'Gas', 'Water']
            engi_name = well_info.get('engi', '') or well_info.get('engineer', '') or ''
            
            # 图例颜色映射
            fallback_colors = {'Sandstone': '#FFFF00', 'Shale': '#228B22', 'Mudstone': '#228B22',
                              'Limestone': '#87CEEB', 'Dolomite': '#B0E0E6',
                              'Anhydrite': '#FFC0CB', 'Gypsum': '#FFC0CB',
                              'Halite': '#FF69B4', 'Salt': '#FF69B4',
                              'Coal': '#333333', 'Pyrite': '#FFD700',
                              'Volcanic': '#FF0000', 'Conglomerate': '#D2B48C'}
            facies_color_map = {'Channel': 'firebrick', 'Floodplain': 'sandybrown', 
                                'Delta Front': 'wheat', 'Prodelta': 'darkolivegreen'}
            interp_color_map = {'Oil': 'green', 'Gas': 'red', 'Water': 'blue', 'Dry': 'saddlebrown'}
            
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
            legend_sections = [
                ('Litho:', lith_types, lithology_image_map, fallback_colors, 'texture'),
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
                            
                            # 绘制符号方块
                            if draw_type == 'texture' and img_map and name in img_map:
                                _draw_legend_image(fig, x_pos, y_center, sub_sq_w, img_map[name])
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
        
        plt.savefig(output_path, dpi=200)
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


def _setup_depth_track(ax, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y):
    """设置深度道"""
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
    
    # 图头区只显示"深度 (m)"标签和比例尺（使用figure坐标）
    # 深度标签在上部
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.6, 
            'Depth (m)', ha='center', va='center', fontsize=12, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)
    # 比例尺在深度标签下方
    ax.text(ax_center, header_bottom_y + (header_top_y - header_bottom_y) * 0.35, 
            '1:200', ha='center', va='center', fontsize=10, fontfamily='Microsoft YaHei',
            transform=fig.transFigure)
    
    # 深度道曲线区只显示深度数字标签，不显示横线
    # 深度数字只在有数据的深度范围内显示
    major_step = 10
    
    # 从depth_min开始显示深度刻度（depth_min已经是整十米）
    min_display_depth = depth_min
    # 到depth_max结束显示深度刻度（depth_max已经是整十米）
    max_display_depth = depth_max
    
    # 生成整十米刻度，包含起始和结束刻度
    major_ticks = np.arange(min_display_depth, max_display_depth + major_step, major_step)
    # 确保只在显示范围内
    major_ticks = major_ticks[(major_ticks >= min_display_depth) & (major_ticks <= max_display_depth)]
    
    # 使用figure坐标绘制深度数字，确保只在曲线区内显示
    # 深度数字水平居中于道内
    label_x_center = ax_center
    
    for depth_val in major_ticks:
        # 计算深度值对应的figure y坐标
        # depth_max 在底部 (fig_y=0), depth_min 在顶部 (fig_y=header_bottom_y)
        norm_y = (depth_max - depth_val) / (depth_max - depth_min)
        fig_y = norm_y * header_bottom_y
        
        # 确保深度数字在曲线区内，距离图头区底部至少1%的figure高度
        if fig_y < header_bottom_y - 0.01:
            ax.text(label_x_center, fig_y, f'{depth_val:.0f}', ha='center', va='center', 
                    fontsize=11, fontfamily='Microsoft YaHei', transform=fig.transFigure, zorder=501)


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
            'floodplain': 'sandybrown',
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



def _setup_profile_track(ax, data, depth, depth_min, depth_max, curve_height_ratio, header_bottom_y, header_top_y, has_enough_curves):
    """设置矿物剖面道：按比例绘制各种矿物含量和孔隙度，使用symbol图片，孔隙在最后，有效曲线不足3条的井段留空白"""
    # 常量定义
    SMOOTH_WINDOW = 100  # 100点滑动平均（10米），确保岩性边界平滑过渡
    MERGE_THRESHOLD = 0.05  # 5%变化阈值
    
    ax.set_xlim(0, 1)
    ax.set_ylim(depth_max, depth_min)
    ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    
    # 隐藏所有spine（使用自定义边框）
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig = ax.figure
    pos = ax.get_position()
    ax_left = pos.x0
    ax_right = pos.x1
    logger.info(f"PROFILE道位置: x0={pos.x0:.4f} x1={pos.x1:.4f} y0={pos.y0:.4f} y1={pos.y1:.4f}")
    has_valid_curves = False
    if 'VALID_CURVES_COUNT' in data.columns:
        has_valid_curves = data['VALID_CURVES_COUNT'].max() >= 3
    
    # 矿物组分定义：名称、列名备选列表、显示名称
    # 孔隙度放在最后
    # 注意：只使用V*列（经过_sync_minerals_with_lithology同步的权威数据），
    # 禁止使用VOL_*列（LAS原始列，从未被同步，会导致岩性道与profile道不一致）
    profile_components = [
        ('Quartz',    ['VQuartz', 'VSAND'],                  'Qtz'),
        ('Calcite',   ['VCalcite'],                          'Cal'),
        ('Dolomite',  ['VDolomite'],                         'Dol'),
        ('Anhydrite', ['VAnhydrite'],                        'Anh'),
        ('Halite',    ['VHalite'],                           'Hal'),
        ('Clay',      ['VClay', 'VSH'],                      'Clay'),
        ('Porosity',  ['PHI', 'POR', 'PHIE'],                'Phi'),
    ]
    
    # 预加载所有symbol图片
    loaded_images = {}
    for name, _, _ in profile_components:
        loaded_images[name] = _load_mineral_symbol(name)

    # 计算每种矿物在全井段的最大含量，过滤掉微量矿物（<5%的矿物不显示图例）
    MINERAL_DISPLAY_THRESHOLD = 0.05  # 5%阈值
    mineral_max_values = {}
    for name, cols, _ in profile_components:
        if name == 'Porosity':
            continue
        col = None
        for c in cols:
            if c in data.columns:
                col = c
                break
        if col is not None:
            vals = data[col].replace(-999, np.nan).replace(-999.25, np.nan).dropna()
            mineral_max_values[name] = float(vals.max()) if len(vals) > 0 else 0.0
        else:
            mineral_max_values[name] = 0.0

    # 只显示最大含量>=5%的矿物图例（Porosity始终显示）
    visible_components = [(name, cols, label) for name, cols, label in profile_components
                          if name == 'Porosity' or mineral_max_values.get(name, 0) >= MINERAL_DISPLAY_THRESHOLD]

    # ========== 图头区：使用图片作为图例，占满整个道宽 ==========
    header_height = header_top_y - header_bottom_y
    n_components = len(visible_components)
    # 每个图例项占图头区高度的 1/n_components
    legend_item_height = header_height / n_components

    for i, (name, cols, label) in enumerate(visible_components):
        # 图例项的y中心位置（从上到下叠置）
        y_center = header_top_y - (i + 0.5) * legend_item_height
        
        # 使用图片作为图例背景，占满整个道宽（不留空白）
        img = loaded_images.get(name)
        if img is not None:
            # 扩展数据到整个道宽范围
            track_width = ax_right - ax_left
            x0 = ax_left
            x1 = ax_right
            y0 = y_center - legend_item_height / 2
            y1 = y_center + legend_item_height / 2
            
            # 用imshow显示图片作为背景（不拉伸，保持原始比例居中）
            ax_bg = fig.add_axes([x0, y0, track_width, legend_item_height], 
                                frameon=False, zorder=5999)
            ax_bg.set_xlim(0, 1)
            ax_bg.set_ylim(0, 1)
            ax_bg.imshow(img, aspect='auto', extent=[0, 1, 0, 1], zorder=5999)
            ax_bg.set_xticks([])
            ax_bg.set_yticks([])
        else:
            # 没有图片时，绘制浅灰色背景
            track_width = ax_right - ax_left
            x0 = ax_left
            y0 = y_center - legend_item_height / 2
            sq = plt.Rectangle((x0, y0),
                               track_width, legend_item_height,
                               transform=fig.transFigure, facecolor='#E8E8E8',
                               linewidth=0, zorder=5999)
            fig.add_artist(sq)
        
        # 在图例项正中标注文字（白色背景文字以保证可读性）
        ax_center = (ax_left + ax_right) / 2
        fig.text(ax_center, y_center, label,
                 fontsize=7, ha='center', va='center',
                 fontfamily='Microsoft YaHei', color='black',
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.85),
                 transform=fig.transFigure, zorder=6001)
    
    # ========== 曲线区：累计曲线 + 岩性符号充填 ==========
    if not has_valid_curves or not has_enough_curves:
        return
    
    # 查找各矿物列名（只使用visible_components，跳过微量矿物）
    col_map = {}
    for name, cols, _ in visible_components:
        found = False
        for col in cols:
            if col in data.columns:
                col_map[name] = col
                found = True
                break
        if not found:
            col_map[name] = None

    # 如果没有任何矿物列，跳过
    has_any_mineral = any(col_map.get(name) is not None for name, _, _ in visible_components if name != 'Porosity')
    if not has_any_mineral:
        return
    
    depth_col = 'MD' if 'MD' in data.columns else data.index.name or 'index'
    depths_arr = data[depth_col].values if depth_col in data.columns else data.index.values
    n = len(data)
    
    # 找出有效曲线(>=3)的深度范围
    valid_mask = data['VALID_CURVES_COUNT'] >= 3 if 'VALID_CURVES_COUNT' in data.columns else pd.Series([False] * n, index=data.index)
    
    if not valid_mask.any():
        return
    
    valid_indices = data.index[valid_mask].tolist()
    if not valid_indices:
        return
    
    first_valid_idx = valid_indices[0]
    last_valid_idx = valid_indices[-1]
    
    data_valid = data.loc[first_valid_idx:last_valid_idx].copy()
    depths_valid = data_valid[depth_col].values if depth_col in data_valid.columns else data_valid.index.values
    n_valid = len(data_valid)
    
    # ========== 收集有效深度段数据 ==========
    # 关键修改：孔隙度使用实际PHI值，矿物组分归一化到(1-PHI)空间
    # 这样profile孔隙度边界与主曲线PHI完全一致
    valid_groups = []
    current_group_depths = []
    current_group_values = []  # 存储原始矿物含量
    current_group_phi = []     # 存储实际PHI值
    current_group_lith = []    # 存储LITHOLOGY
    
    # 矿物组分列表（不含孔隙度），只使用visible_components
    mineral_components = [pc for pc in visible_components if pc[0] != 'Porosity']
    porosity_col_name = None
    for name, cols, _ in visible_components:
        if name == 'Porosity':
            for col in cols:
                if col in data.columns:
                    porosity_col_name = col
                    break
            break
    
    for i in range(n_valid):
        row = data_valid.iloc[i]
        valid_count = row.get('VALID_CURVES_COUNT', 0)
        
        if valid_count < 3:
            if current_group_depths:
                valid_groups.append((current_group_depths, current_group_values, current_group_phi, current_group_lith))
                current_group_depths = []
                current_group_values = []
                current_group_phi = []
                current_group_lith = []
            continue
        
        # 获取实际PHI值（与第6道孔隙度曲线保持一致）
        # 使用_porosity_valid掩码，与track 6处理方式相同
        phi_val = 0.0
        phi_is_valid = True
        if porosity_col_name is not None:
            phi_raw = row.get(porosity_col_name, 0)
            if phi_raw is None or (isinstance(phi_raw, float) and np.isnan(phi_raw)) or phi_raw < -100:
                phi_val = 0.0
            else:
                phi_val = max(0.0, min(1.0, float(phi_raw)))
        # 检查_porosity_valid掩码（与track 6一致）
        if '_POROSITY_VALID' in data.columns:
            pv = row.get('_POROSITY_VALID', True)
            if not pv:
                phi_is_valid = False
        # PHI无效时断开当前组（与track 6的NaN断开行为一致）
        if not phi_is_valid:
            if current_group_depths:
                valid_groups.append((current_group_depths, current_group_values, current_group_phi, current_group_lith))
                current_group_depths = []
                current_group_values = []
                current_group_phi = []
                current_group_lith = []
            continue
        
        # 获取矿物组分含量
        mineral_values = []
        skip_point = False
        for name, cols, _ in mineral_components:
            col = col_map.get(name)
            if col is not None:
                v = row.get(col, 0)
                if v is None or (isinstance(v, float) and np.isnan(v)) or v < -100:
                    # 关键矿物（Quartz）数据缺失时跳过该深度点
                    if name == 'Quartz':
                        skip_point = True
                        break
                    v = 0.0
                v = max(0.0, float(v))
            else:
                v = 0.0
            mineral_values.append(v)

        if skip_point:
            if current_group_depths:
                valid_groups.append((current_group_depths, current_group_values, current_group_phi, current_group_lith))
                current_group_depths = []
                current_group_values = []
                current_group_phi = []
                current_group_lith = []
            continue

        # NOTE: LITHOLOGY与矿物含量的一致性现已由数据层处理
        # (logInt.py的_sync_minerals_with_lithology方法)，无需在此显示层调整。

        # 存储原始矿物含量（不归一化，后面统一处理）
        mineral_raw = list(mineral_values)
        lith_val = str(row.get('LITHOLOGY', '')).lower().strip()
        
        current_group_depths.append(depths_valid[i])
        current_group_values.append(mineral_raw)
        current_group_phi.append(phi_val)
        current_group_lith.append(lith_val)
    
    if current_group_depths:
        valid_groups.append((current_group_depths, current_group_values, current_group_phi, current_group_lith))
    
    # ========== 合并所有有效段为一个连续序列（消除段间台阶） ==========
    # 关键：将所有valid_groups合并后统一平滑，避免段间矿物比例突变产生台阶
    all_depths = []
    all_values = []
    all_phi = []
    all_lith = []
    for g_d, g_v, g_p, g_l in valid_groups:
        all_depths.extend(g_d)
        all_values.extend(g_v)
        all_phi.extend(g_p)
        all_lith.extend(g_l)
    
    if not all_depths:
        return
    
    # ========== 直接使用合并后的数据（不滑动窗口平滑） ==========
    # 关键：不使用滑动窗口平滑，避免两个问题：
    # 1. 组边界处混合不相邻点产生台阶
    # 2. PHI被平均导致非储层PHI≠0
    # 平滑由后面的三次样条插值实现（渲染时自动平滑）
    seg_depths_arr = np.array(all_depths)
    seg_mineral_arr = np.array(all_values)    # shape: (n_depths, n_minerals) 原始含量
    seg_phi_arr = np.array(all_phi)            # shape: (n_depths,) 原始孔隙度
    seg_lith_arr = list(all_lith)              # LITHOLOGY列表
    n_mineral_components = len(mineral_components)
    n_depths = len(seg_depths_arr)
    
    if n_depths < 2:
        d = seg_depths_arr[0]
        seg_depths_arr = np.array([d, d + 0.3])
        seg_mineral_arr = np.array([seg_mineral_arr[0], seg_mineral_arr[0]])
        seg_phi_arr = np.array([seg_phi_arr[0], seg_phi_arr[0]])
        seg_lith_arr = [seg_lith_arr[0], seg_lith_arr[0]]
        n_depths = 2

    # 矿物名称到索引的映射（用于LITHOLOGY回退）
    mineral_name_to_idx = {name: idx for idx, (name, _, _) in enumerate(mineral_components)}
    
    n_total = n_mineral_components + 2
    
    # ========== 关键：忠实跟随测井曲线，不做人为平滑 ==========
    # 孔隙度边界 = 1-PHI，直接来自数据（第6道PHI曲线本身就是平滑的）
    # 矿物比例直接来自数据，储层/非储层之间自然突变
    # 线性插值仅用于提高渲染分辨率，不改变数据形态
    
    from scipy.ndimage import gaussian_filter1d
    
    # 1. 从原始矿物比例直接构建累积数组
    #    非储层（PHI=0）用LITHOLOGY对应的矿物填充100%
    #    储层使用原始矿物比例，按1-PHI缩放
    cumulative = np.zeros((n_depths, n_mineral_components + 3))  # +3: 左边界+矿物边界+孔隙度边界+右边界
    cumulative[:, 0] = 0.0
    dominant_mineral_idx = np.zeros(n_depths, dtype=int)  # 记录每个深度的主矿物索引（用于非储层填充）
    for i in range(n_depths):
        phi = float(seg_phi_arr[i])
        if phi <= 1e-10:
            # 非储层：LITHOLOGY对应矿物填充100%
            lith_name = seg_lith_arr[i] if i < len(seg_lith_arr) else 'unknown'
            lith_to_mineral = {
                'sandstone': 'Quartz', 'shale': 'Clay', 'limestone': 'Calcite',
                'dolomite': 'Dolomite', 'anhydrite': 'Anhydrite', 'halite': 'Halite',
                '砂岩': 'Quartz', '泥岩': 'Clay', '灰岩': 'Calcite', '白云岩': 'Dolomite',
            }
            target_mineral = lith_to_mineral.get(lith_name, None)
            if target_mineral and target_mineral in mineral_name_to_idx:
                dominant_j = mineral_name_to_idx[target_mineral]
            else:
                mineral_values = [max(float(seg_mineral_arr[i, j]), 0.0) for j in range(n_mineral_components)]
                dominant_j = int(np.argmax(mineral_values))
            dominant_mineral_idx[i] = dominant_j
            # 主矿物填充整个band：cumulative[i, dominant_j+1] = 1.0，其他矿物边界=0.0
            for j in range(n_mineral_components):
                if j == dominant_j:
                    cumulative[i, j + 1] = 1.0
                else:
                    cumulative[i, j + 1] = 0.0
        else:
            # 储层：使用原始矿物比例
            for j in range(n_mineral_components):
                cumulative[i, j + 1] = cumulative[i, j] + max(float(seg_mineral_arr[i, j]), 0.0)
            mineral_sum = cumulative[i, n_mineral_components]
            target = max(1.0 - phi, 0.0)
            if mineral_sum > target and mineral_sum > 1e-10:
                scale = target / mineral_sum
                for j in range(n_mineral_components):
                    cumulative[i, j + 1] = cumulative[i, j] + (cumulative[i, j + 1] - cumulative[i, j]) * scale
        # 孔隙度边界 = 1-PHI（列n_mineral_components+1）
        cumulative[i, n_mineral_components + 1] = max(1.0 - phi, 0.0)
    # 最后一列（右边界）= 1.0
    cumulative[:, -1] = 1.0
    
    # 2. 确保单调递增（矿物边界不能回退）
    for i in range(n_depths):
        for j in range(1, n_mineral_components + 1):  # 列1到列n_mineral_components（矿物边界）
            if cumulative[i, j] < cumulative[i, j - 1]:
                cumulative[i, j] = cumulative[i, j - 1]
        # 最后一种矿物边界不能超过孔隙度边界
        if cumulative[i, n_mineral_components] > cumulative[i, n_mineral_components + 1]:
            cumulative[i, n_mineral_components] = cumulative[i, n_mineral_components + 1]
        # 右边界=1.0
        cumulative[i, -1] = 1.0
    
    # ========== 渲染：按比例堆叠矿物 ==========
    MINERAL_TO_LITH = {
        'Quartz': 'sandstone',
        'Calcite': 'limestone',
        'Dolomite': 'dolomite',
        'Anhydrite': 'anhydrite',
        'Halite': 'halite',
        'Clay': 'shale',
    }
    
    # 1. 线性插值所有边界曲线（仅提高渲染分辨率，不改变数据形态）
    #    分辨率0.1m/点：保留0.3m以上薄岩性层（如薄泥岩夹层），且曲线边界更平滑
    depth_min_seg = seg_depths_arr[0]
    depth_max_seg = seg_depths_arr[-1]
    n_smooth = min(int((depth_max_seg - depth_min_seg) / 0.1) + 1, 30000)
    n_smooth = max(n_smooth, 500)
    
    if depth_max_seg > depth_min_seg and n_depths >= 2:
        depths_interp = np.linspace(depth_min_seg, depth_max_seg, n_smooth)
        cumulative_smooth = np.zeros((n_smooth, n_mineral_components + 3))  # 与cumulative数组大小一致
        for j in range(n_mineral_components + 2):  # 插值列0到列n_mineral_components+1
            cumulative_smooth[:, j] = np.interp(depths_interp, seg_depths_arr, cumulative[:, j])
        phi_interp = np.interp(depths_interp, seg_depths_arr, seg_phi_arr)
        phi_interp = np.clip(phi_interp, 0.0, 1.0)
    else:
        depths_interp = seg_depths_arr
        cumulative_smooth = cumulative.copy()
        phi_interp = seg_phi_arr.copy()
    
    # 2. 最终单调性修复 + 非储层点强制恢复
    for i in range(n_smooth):
        # 非储层点：用主矿物填满整个band（主矿物宽度=1.0，其他矿物宽度=0）
        if phi_interp[i] <= 1e-10:
            # 找到最近的原始点的主矿物索引
            orig_idx = int(np.searchsorted(seg_depths_arr, depths_interp[i]))
            orig_idx = min(max(orig_idx, 0), n_depths - 1)
            dom_j = int(dominant_mineral_idx[orig_idx])
            # 关键修复：主矿物及其之后所有边界都=1.0，保证单调性
            # 主矿物之前的边界=0.0
            cumulative_smooth[i, 0] = 0.0
            for j in range(n_mineral_components):
                if j < dom_j:
                    cumulative_smooth[i, j + 1] = 0.0
                else:
                    cumulative_smooth[i, j + 1] = 1.0
            cumulative_smooth[i, n_mineral_components + 1] = 1.0  # 孔隙度边界=1.0（PHI=0）
            cumulative_smooth[i, -1] = 1.0  # 右边界=1.0
            continue
        
        # 储层点：确保单调递增
        for j in range(1, n_mineral_components + 1):  # 列1到列n_mineral_components
            if cumulative_smooth[i, j] < cumulative_smooth[i, j - 1]:
                cumulative_smooth[i, j] = cumulative_smooth[i, j - 1]
        # 最后一种矿物边界不能超过孔隙度边界
        phi_boundary = cumulative_smooth[i, n_mineral_components + 1]  # 孔隙度边界在列n_mineral_components+1
        if cumulative_smooth[i, n_mineral_components] > phi_boundary:
            cumulative_smooth[i, n_mineral_components] = phi_boundary
        # 右边界=1.0
        cumulative_smooth[i, -1] = 1.0
    
    porosity_boundary = cumulative_smooth[:, n_mineral_components + 1]  # = 1-PHI
    seg_top = depths_interp[0]
    seg_bottom = depths_interp[-1]
    
    # ========== 渲染策略：分段平铺岩性符号（与岩性道完全一致） ==========
    # 核心思路：
    # 1. 按"矿物构成"把深度分成连续段（相邻点构成相同则合并，减少绘制调用）
    # 2. 每段每种矿物：fill_betweenx背景色 + symbol岩性符号图片
    #    砂岩 = 规则圆点（scatter），其他 = tile图片平铺并裁剪到曲线之间
    # 3. 非储层段（PHI=0）：主矿物占满0-1，自动成为单一矿物段，填满无空白
    # 4. 孔隙度区域（x > 1-PHI）不填充，留白
    
    # 岩性背景色映射（与岩性道一致）
    lith_bg_colors = {
        'sandstone': '#FFFF00', 'shale': '#228B22', 'mudstone': '#228B22',
        'limestone': '#87CEEB', 'dolomite': '#B0E0E6',
        'anhydrite': '#FFC0CB', 'gypsum': '#FFC0CB',
        'halite': '#FF69B4', 'salt': '#FF69B4',
        'volcanic': '#FF0000', 'coal': '#333333', 'pyrite': '#FFD700',
        'carbonate': '#87CEEB', 'mixed': '#D3D3D3', 'conglomerate': '#D2B48C',
        'unknown': '#D3D3D3',
    }
    
    # 逐点矿物构成掩码（宽度>0.5%才算存在）
    min_width = 0.005
    masks = np.zeros(n_smooth, dtype=np.uint8)
    bounds = cumulative_smooth[:, :n_mineral_components + 1]
    for k in range(n_mineral_components):
        masks[(bounds[:, k + 1] - bounds[:, k]) > min_width] |= (1 << k)
    
    # 合并连续相同构成的段
    segments = []
    i = 0
    while i < n_smooth:
        j = i + 1
        while j < n_smooth and masks[j] == masks[i]:
            j += 1
        segments.append((i, j, int(masks[i])))
        i = j
    
    # 预加载矿物符号tile（尺寸统一为SYMBOL_TILE_PX，与岩性道一致）
    mineral_tiles = {}
    for k in range(n_mineral_components):
        mname = mineral_components[k][0]
        lname = MINERAL_TO_LITH.get(mname, 'unknown')
        img, _ = _load_lithology_symbol(lname)
        if img is None:
            continue
        try:
            from PIL import Image as PILImage
            img_pil = PILImage.fromarray((img * 255).astype(np.uint8) if img.max() <= 1.0 else img.astype(np.uint8))
            img_pil = img_pil.resize((SYMBOL_TILE_PX, SYMBOL_TILE_PX), PILImage.NEAREST)
            tile = np.array(img_pil)
            if tile.ndim == 2:
                tile = np.stack([tile] * 3, axis=-1)
            mineral_tiles[k] = tile
        except Exception:
            continue
    
    # 砂岩圆点模式（与岩性道一致）
    rows_pattern = [
        [0.10, 0.30, 0.55, 0.80],
        [0.05, 0.25, 0.50, 0.70, 0.90],
        [0.15, 0.40, 0.60, 0.85],
        [0.08, 0.35, 0.50, 0.75, 0.92],
    ]
    
    # 逐段渲染
    for i0, i1, mask in segments:
        if mask == 0:
            continue
        d_seg = depths_interp[i0:i1]
        seg_top = d_seg[0]
        seg_bottom = d_seg[-1]
        for k in range(n_mineral_components):
            if not (mask & (1 << k)):
                continue
            mname = mineral_components[k][0]
            lname = MINERAL_TO_LITH.get(mname, 'unknown')
            xl = bounds[i0:i1, k]
            xr = bounds[i0:i1, k + 1]
            bg_color = lith_bg_colors.get(lname, '#D3D3D3')
            # 1. 背景色（曲线之间）
            # alpha=1.0：不透明纯色，避免段与段叠放时透色导致色块模糊
            ax.fill_betweenx(d_seg, xl, xr, color=bg_color, alpha=1.0, zorder=8)
            
            # 2. 砂岩：与岩性道完全一致的圆点图案（plot 'o' markersize=1.5，4排交错不规则）
            # 与 _draw_lithology_tiles 的参数完全一致，保证点的大小和密度一致
            if lname in ('sandstone', '砂岩'):
                dot_spacing = 0.4
                row_depths = np.arange(seg_top + dot_spacing / 2, seg_bottom, dot_spacing)
                for ii, dd in enumerate(row_depths):
                    xll = float(np.interp(dd, d_seg, xl))
                    xrr = float(np.interp(dd, d_seg, xr))
                    # 极窄条带（<0.5%道宽）才跳过，保证窄条带内点不缺失
                    if xrr - xll < 0.005:
                        continue
                    for fx in rows_pattern[ii % 4]:
                        ax.plot(xll + fx * (xrr - xll), dd, 'o', color='black',
                                markersize=1.5, markeredgewidth=0, zorder=10)
                continue
            
            # 3. 其他矿物：tile平铺 + 裁剪到曲线之间
            tile = mineral_tiles.get(k)
            if tile is None:
                continue
            seg_len = seg_bottom - seg_top
            n_tiles_total = max(1, int(np.ceil(seg_len / TILE_DEPTH_M)))
            MAX_TILES_PER_IMG = 64  # 限制单张图像大小，避免超大imshow
            tile_start = 0
            while tile_start < n_tiles_total:
                tile_end = min(tile_start + MAX_TILES_PER_IMG, n_tiles_total)
                top_d = seg_top + tile_start * TILE_DEPTH_M
                bot_d = min(seg_top + tile_end * TILE_DEPTH_M, seg_bottom)
                n_tiles = tile_end - tile_start
                tiled = np.tile(tile, (n_tiles, 1, 1))
                # 尾部不足一个tile时裁剪行
                if tile_end == n_tiles_total:
                    remain = seg_len - tile_start * TILE_DEPTH_M
                    frac = remain / TILE_DEPTH_M
                    crop_rows = max(1, int(SYMBOL_TILE_PX * frac + 0.5))
                    tiled = tiled[:crop_rows, :, :]
                im = ax.imshow(tiled, extent=[0, 1, bot_d, top_d],
                               aspect='auto', interpolation='nearest', zorder=10)
                # 用多边形裁剪到矿物曲线之间（PathPatch）
                # 关键：clip多边形用加密插值点（至少8个），与fill_betweenx背景完全贴合，
                # 避免薄段/粗插值导致纹理与背景分离
                sel = (d_seg >= top_d - 1e-9) & (d_seg <= bot_d + 1e-9)
                d_sel = d_seg[sel]
                if len(d_sel) < 2:
                    d_sel = np.array([top_d, bot_d])
                # 加密clip点，确保与背景色边界平滑一致
                if len(d_sel) < 8:
                    d_sel = np.linspace(d_sel[0], d_sel[-1], 8)
                xl_sel = np.interp(d_sel, d_seg, xl)
                xr_sel = np.interp(d_sel, d_seg, xr)
                verts = list(zip(xl_sel, d_sel)) + list(zip(xr_sel[::-1], d_sel[::-1]))
                clip = PathPatch(MplPath(verts), transform=ax.transData)
                im.set_clip_path(clip)
                tile_start = tile_end
    
    # 绘制外边框
    ax.plot([0, 0, 1, 1, 0], 
            [seg_depths_arr[0], seg_depths_arr[-1], seg_depths_arr[-1],
             seg_depths_arr[0], seg_depths_arr[0]],
            color='black', linewidth=0.5, zorder=12)


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
            return 'floodplain'
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
# 流体交会图扩展（由 visualization_fluid 模块提供）
# ----------------------------------------------------------------------------
# 说明：本段为增量追加，不改变以上原有绘制逻辑。
#   patch_depth_unit('ft')            —— 深度道适配英尺井（标签/刻度/比例尺）
#   visualize_fluid_crossplots(...)   —— 油绿/气红/水蓝 交会图，按层号标注
# ============================================================================
try:
    from visualization_fluid import (patch_depth_unit, visualize_fluid_crossplots,
                                     setup_chinese_font, enhance_visualization,
                                     classify_fluid, FLUID_LABEL_CN, FLUID_COLOR)
    HAS_FLUID_VIZ = True
except ImportError as _e:
    HAS_FLUID_VIZ = False
    _FLUID_VIZ_IMPORT_ERR = _e


def visualize_fluid(data, results, output_dir=None, gas_data=None,
                    depth_unit='ft', min_thickness=3.0):
    """log_visualizer 的流体交会图入口。

    若 visualization_fluid 模块不可用，返回 None 并给出提示，
    不影响综合测井图的正常绘制。
    """
    if not HAS_FLUID_VIZ:
        logger.warning('流体交会图不可用（visualization_fluid 未安装）: %s',
                       getattr(_FLUID_VIZ_IMPORT_ERR, '__str__', lambda: '?')())
        return None
    setup_chinese_font()
    out = output_dir or results.get('output_dir', 'output')
    return visualize_fluid_crossplots(
        data, results, output_dir=out, depth_unit=depth_unit,
        gas_data=gas_data, min_thickness=min_thickness)
