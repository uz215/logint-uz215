#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测井数据可视化模块
基于 logInt.py 的可视化代码构建
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize
from matplotlib.lines import Line2D
import matplotlib.patches as patches
from pathlib import Path
import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DataVisualizer:
    """数据可视化类"""
    
    def __init__(self, output_dir):
        """初始化数据可视化器"""
        self.output_dir = Path(output_dir)
        self.viz_dir = self.output_dir / 'visualization'
        self.viz_dir.mkdir(exist_ok=True, parents=True)
    
    def visualize_composite_log(self, data, results=None):
        """可视化8道综合测井曲线"""
        if data is None:
            logger.error("Data not loaded")
            return None
        
        try:
            if results is None:
                results = {}
                
            if 'MD' not in data.columns:
                logger.error("数据中缺少Depth列 'MD'")
                return None
            
            data = data.sort_values('MD').reset_index(drop=True)
            
            if len(data) == 0:
                logger.error("数据为空")
                return None
            
            depth = data['MD']
            depth_min = depth.min()
            depth_max = depth.max()
            depth_range = depth_max - depth_min
            
            if depth_range <= 0:
                logger.error("Depth范围无效")
                return None
            
            # 检查有效曲线数量，决定是否绘制岩性、沉积相和测井解释道
            valid_curves = ['GR', 'RT', 'LLD', 'ILD', 'R90', 'DEN', 'RHOB', 'NPHI', 'CNL', 'DT', 'AC']
            available_curves = [curve for curve in valid_curves if curve in data.columns]
            has_enough_curves = len(available_curves) >= 2
            
            import matplotlib.gridspec as gridspec
            fig = plt.figure(figsize=(24, 15))
            gs = gridspec.GridSpec(1, 8, width_ratios=[1, 1, 1, 0.5, 1, 1, 1, 1], wspace=0)
            axes = [fig.add_subplot(gs[i]) for i in range(8)]
            for i in range(1, 8):
                axes[i].sharey(axes[0])
            
            # 道头区域固定为6厘米
            header_height_cm = 6
            header_height_inches = header_height_cm / 2.54
            
            # 图名到道名的距离：1厘米
            title_trackname_gap_cm = 1
            title_trackname_gap_inches = title_trackname_gap_cm / 2.54
            
            actual_depth_range = depth_max - depth_min
            curve_height_cm = actual_depth_range * 100 / 200
            curve_height_inches = curve_height_cm / 2.54
            
            # 总高度 = 曲线区高度 + 道头区高度(6cm) + 图名到道名间距(1cm)
            # 道名在道头区顶部，不需要额外间距
            total_fig_height_inches = curve_height_inches + header_height_inches + title_trackname_gap_inches
            total_fig_height_inches = max(total_fig_height_inches, 12)
            fig.set_figheight(total_fig_height_inches)
            
            # 计算各部分占figure的比例（从底部往上）
            # curve_height: 曲线区占比（底部到curve_height是曲线区）
            # header_height: 道头区占比（曲线区上面）
            # title_trackname_gap: 图名到道名间距占比（道名上面）
            curve_height = curve_height_inches / total_fig_height_inches
            header_height = header_height_inches / total_fig_height_inches
            title_trackname_gap = title_trackname_gap_inches / total_fig_height_inches
            
            # 刻度线在道头区域的垂直位置（使用绝对厘米距离，从道头底部向上偏移）
            # 使用绝对距离确保各道刻度线垂直对齐，不受图大小影响
            # 为每个道定义独立的刻度位置（最多4个刻度）
            # 道头区高度6厘米，刻度间距约1.2厘米，避免重叠
            track_tick_positions = {
                0: [1.0, 2.5, 4.0],      # 岩性道: CAL, SP, GR (3个刻度) - 从底部算起
                1: [4.0, 2.5, 1.0],      # 电阻率道: LLD, LLS, MSFL (3个刻度)
                2: [0.8, 2.3, 3.8, 5.3], # 孔隙度道: PE, DT, NPHI, RHOB (4个刻度)
                4: [3.0],                 # 含水饱和度道: Sw (1个刻度) - 居中
            }
            
            # 将厘米转换为轴坐标比例
            def get_tick_position(track_idx, tick_idx):
                positions = track_tick_positions.get(track_idx, [0.5, 1.8, 3.1, 4.4])
                if tick_idx < len(positions):
                    cm = positions[tick_idx]
                    return curve_height + (cm / header_height_cm) * (1 - curve_height)
                return curve_height + 0.5 * (1 - curve_height)
            
            cm_to_inches = 0.3937
            one_cm_inches = 1 * cm_to_inches
            one_cm_ratio = one_cm_inches / total_fig_height_inches
            
            major_step = 10
            minor_step = 1
            start_depth = int(np.ceil(depth_min / major_step) * major_step)
            
            major_ticks = np.arange(start_depth, depth_max + major_step, major_step)
            major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
            
            minor_ticks = np.arange(start_depth, depth_max + minor_step, minor_step)
            minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
            
            plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
            plt.rcParams['font.family'] = ['Microsoft YaHei']
            plt.rcParams['font.size'] = 12
            
            processed_data = data
            depth = data['MD']
            
            # ========== 第1道: 岩性 ==========
            ax1 = axes[0]
            for spine in ax1.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax1.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax1.plot([0, 1], [curve_height, curve_height], transform=ax1.transAxes, color='black', linewidth=1)
            
            ax1.set_xlim(0, 1)
            ax1.set_ylabel('')
            ax1.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax1.set_ylim(depth_max, depth_min)
            ax1.spines['left'].set_position(('axes', 0))
            ax1.set_yticks([])
            
            clip_rect1 = plt.Rectangle((0, 0), 1, curve_height, transform=ax1.transAxes, clip_on=False, fill=False)
            ax1.add_patch(clip_rect1)
            header_clip_rect1 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax1.transAxes, clip_on=False, fill=False)
            ax1.add_patch(header_clip_rect1)
            
            ax1.spines['left'].set_bounds(depth_max, depth_min)
            
            for depth_val in major_ticks:
                line = ax1.axhline(y=depth_val, color='black', linewidth=1, zorder=500)
                line.set_clip_path(clip_rect1)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax1.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect1)
            
            for i in range(1, 10):
                x = i / 10.0
                if i == 5:
                    line = ax1.axvline(x=x, color='black', linewidth=1.0, zorder=500)
                else:
                    line = ax1.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect1)
            
            if 'GR' in processed_data.columns:
                gr_ax = ax1.twiny()
                line, = gr_ax.plot(processed_data['GR'], depth, color='green', linewidth=1.5, label='GR')
                line.set_clip_path(clip_rect1)
                line.set_clip_on(True)
                line.set_zorder(2000)
                
                gr_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in gr_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                gr_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                  labelbottom=False, labeltop=False, length=0)
                gr_ax.set_xticks([])
                gr_ax.set_xlim(-10, 210)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(0, 2)
                gr_ax.plot([0, 1], [tick_pos, tick_pos], transform=gr_ax.transAxes, color='green', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                gr_ticks = [0, 200]
                for tick_val in gr_ticks:
                    # 计算刻度值在轴上的位置（归一化到0-1）
                    x_pos = (tick_val - (-10)) / (210 - (-10))
                    # tick_pos 已经是axes坐标，直接使用
                    ax1.text(x_pos, tick_pos, f'{tick_val}', color='green', fontsize=8, 
                             ha='center', va='center', transform=ax1.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax1.text(label_pos_x, tick_pos, 'GR (API)', 
                         color='green', fontsize=8, ha='right', va='center', transform=ax1.transAxes, zorder=1001)
                
                gr_ax.set_zorder(2)
                # 不使用set_xlabel，使用手动方式添加标签
            
            if 'SP' in processed_data.columns:
                sp_ax = ax1.twiny()
                line, = sp_ax.plot(processed_data['SP'], depth, color='blue', linewidth=1.5, label='SP')
                line.set_clip_path(clip_rect1)
                line.set_zorder(2000)
                
                sp_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in sp_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                sp_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                  labelbottom=False, labeltop=False, length=0)
                sp_ax.set_xticks([])
                sp_ax.set_xlim(-110, 110)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(0, 1)
                sp_ax.plot([0, 1], [tick_pos, tick_pos], transform=sp_ax.transAxes, color='blue', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                sp_ticks = [-100, 100]
                for tick_val in sp_ticks:
                    x_pos = (tick_val - (-110)) / (110 - (-110))
                    ax1.text(x_pos, tick_pos, f'{tick_val}', color='blue', fontsize=8, 
                             ha='center', va='center', transform=ax1.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax1.text(label_pos_x, tick_pos, 'SP (mV)', 
                         color='blue', fontsize=8, ha='right', va='center', transform=ax1.transAxes, zorder=1001)
                
                sp_ax.set_zorder(3)
            
            cal_column = None
            if 'CALS' in processed_data.columns:
                cal_column = 'CALS'
            elif 'CALI' in processed_data.columns:
                cal_column = 'CALI'
            elif 'CAL' in processed_data.columns:
                cal_column = 'CAL'
            
            if cal_column:
                cal_ax = ax1.twiny()
                line, = cal_ax.plot(processed_data[cal_column], depth, color='red', linewidth=1.5, label='CAL')
                line.set_clip_path(clip_rect1)
                line.set_zorder(2000)
                
                cal_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in cal_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                cal_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                   labelbottom=False, labeltop=False, length=0)
                cal_ax.set_xticks([])
                cal_ax.set_xlim(5.5, 12.5)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(0, 0)
                cal_ax.plot([0, 1], [tick_pos, tick_pos], transform=cal_ax.transAxes, color='red', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                cal_ticks = [6, 12]
                for tick_val in cal_ticks:
                    x_pos = (tick_val - 5.5) / (12.5 - 5.5)
                    ax1.text(x_pos, tick_pos, f'{tick_val}', color='red', fontsize=8, 
                             ha='center', va='center', transform=ax1.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax1.text(label_pos_x, tick_pos, 'CAL (in)', 
                         color='red', fontsize=8, ha='right', va='center', transform=ax1.transAxes, zorder=1001)
                
                cal_ax.set_zorder(4)
            
            ax1.set_zorder(1)
            for spine in ax1.spines.values():
                spine.set_zorder(0)
            
            # ========== 第2道: 电阻率 ==========
            ax2 = axes[1]
            for spine in ax2.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax2.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax2.set_ylabel('')
            ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax2.set_yticks([])
            ax2.plot([0, 1], [curve_height, curve_height], transform=ax2.transAxes, color='black', linewidth=1)
            
            clip_rect2 = plt.Rectangle((0, 0), 1, curve_height, transform=ax2.transAxes, clip_on=False, fill=False)
            ax2.add_patch(clip_rect2)
            header_clip_rect2 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax2.transAxes, clip_on=False, fill=False)
            ax2.add_patch(header_clip_rect2)
            
            for spine in ax2.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax2.set_ylabel('')
            ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax2.set_yticks([])
            
            for depth_val in major_ticks:
                line = ax2.axhline(y=depth_val, color='black', linewidth=1, zorder=500)
                line.set_clip_path(clip_rect2)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax2.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect2)
            
            resistivity_cols = ['LLD', 'LLS', 'MSFL']
            res_colors = ['black', 'red', 'green']
            res_positions = [0, 1, 2]
            for i, col in enumerate(resistivity_cols):
                if col in processed_data.columns:
                    res_ax = ax2.twiny()
                    line, = res_ax.semilogx(processed_data[col], depth, color=res_colors[i], linewidth=1.5, label=col)
                    line.set_clip_path(clip_rect2)
                    line.set_zorder(2000)
                    
                    res_ax.set_ylim(depth_max, depth_min)
                    for spine_name, spine in res_ax.spines.items():
                        spine.set_visible(False)  # 隐藏所有spine
                    
                    # 完全隐藏默认刻度和标签
                    res_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                       labelbottom=False, labeltop=False, length=0)
                    res_ax.set_xticks([])
                    res_ax.set_xlim(0.15, 3000)
                    
                    # 在道头区内绘制刻度横线（代替spine）
                    tick_pos = get_tick_position(1, i)
                    res_ax.plot([0, 1], [tick_pos, tick_pos], transform=res_ax.transAxes, color=res_colors[i], linewidth=1, zorder=1000)
                    
                    # 手动在道头区内绘制刻度标签（对数刻度，使用axes坐标）
                    res_ticks = [0.2, 2000]
                    for tick_val in res_ticks:
                        x_pos = (np.log10(tick_val) - np.log10(0.15)) / (np.log10(3000) - np.log10(0.15))
                        ax2.text(x_pos, tick_pos, f'{tick_val}', color=res_colors[i], fontsize=8, 
                                 ha='center', va='center', transform=ax2.transAxes, zorder=1001)
                    
                    # 在刻度线旁边添加曲线标签
                    label_pos_x = 0.95  # 右侧位置
                    ax2.text(label_pos_x, tick_pos, f'{col} (ohm-m)', 
                             color=res_colors[i], fontsize=8, ha='right', va='center', transform=ax2.transAxes, zorder=1001)
                    
                    res_ax.set_zorder(i+2)
            
            # 电阻率道的网格线
            first_grid_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 2]
            for val in first_grid_values:
                x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
                line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect2)
            
            second_grid_values = [3, 4, 5, 6, 7, 8, 9, 10, 20]
            for val in second_grid_values:
                x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
                line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect2)
            
            third_grid_values = [30, 40, 50, 60, 70, 80, 90, 100, 200]
            for val in third_grid_values:
                x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
                line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect2)
            
            fourth_grid_values = [300, 400, 500, 600, 700, 800, 900, 1000]
            for val in fourth_grid_values:
                x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
                line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect2)
            
            # ========== 第3道: 孔隙度 ==========
            ax3 = axes[2]
            for spine in ax3.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax3.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax3.set_xlim(0, 1)  # 设置x轴范围确保十等分线均匀
            ax3.plot([0, 1], [curve_height, curve_height], transform=ax3.transAxes, color='black', linewidth=1)
            
            clip_rect3 = plt.Rectangle((0, 0), 1, curve_height, transform=ax3.transAxes, clip_on=False, fill=False)
            ax3.add_patch(clip_rect3)
            header_clip_rect3 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax3.transAxes, clip_on=False, fill=False)
            ax3.add_patch(header_clip_rect3)
            
            ax3.set_ylabel('')
            ax3.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax3.set_yticks([])
            
            for spine in ax3.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            for depth_val in major_ticks:
                line = ax3.axhline(y=depth_val, color='black', linewidth=1, zorder=500)
                line.set_clip_path(clip_rect3)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax3.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect3)
            
            # 十等分线：确保每份大小一致，仿照饱和度道的绘制方式
            # 使用数据坐标范围来绘制十等分线
            for i in range(1, 10):
                x = i / 10.0
                if i == 5:
                    line = ax3.axvline(x=x, color='black', linewidth=1.0, zorder=500)
                else:
                    line = ax3.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect3)
            
            if 'RHOB' in processed_data.columns:
                rhob_ax = ax3.twiny()
                line, = rhob_ax.plot(processed_data['RHOB'], depth, color='blue', linewidth=1.5, label='RHOB')
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                rhob_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in rhob_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                rhob_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                   labelbottom=False, labeltop=False, length=0)
                rhob_ax.set_xticks([])
                rhob_ax.set_xlim(1.7, 2.9)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(2, 3)
                rhob_ax.plot([0, 1], [tick_pos, tick_pos], transform=rhob_ax.transAxes, color='blue', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                rhob_ticks = [1.8, 2.8]
                for tick_val in rhob_ticks:
                    x_pos = (tick_val - 1.7) / (2.9 - 1.7)
                    ax3.text(x_pos, tick_pos, f'{tick_val}', color='blue', fontsize=8, 
                             ha='center', va='center', transform=ax3.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax3.text(label_pos_x, tick_pos, 'RHOB (g/cc)', 
                         color='blue', fontsize=8, ha='right', va='center', transform=ax3.transAxes, zorder=1001)
                
                rhob_ax.set_zorder(2)
            
            if 'NPHI' in processed_data.columns:
                nphi_ax = ax3.twiny()
                line, = nphi_ax.plot(processed_data['NPHI'], depth, color='green', linewidth=1.5, label='NPHI')
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                nphi_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in nphi_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                nphi_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                    labelbottom=False, labeltop=False, length=0)
                nphi_ax.set_xticks([])
                
                nphi_min = processed_data['NPHI'].min()
                nphi_max = processed_data['NPHI'].max()
                if nphi_max > 1:
                    nphi_ax.set_xlim(-5, 65)
                    nphi_label = 'NPHI (%)'
                else:
                    nphi_ax.set_xlim(-0.1, 1.1)
                    nphi_label = 'NPHI (v/v)'
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(2, 2)
                nphi_ax.plot([0, 1], [tick_pos, tick_pos], transform=nphi_ax.transAxes, color='green', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签
                if nphi_max > 1:
                    nphi_ticks = [0, 60]
                    x_min, x_max = -5, 65
                else:
                    nphi_ticks = [0, 1]
                    x_min, x_max = -0.1, 1.1
                
                for tick_val in nphi_ticks:
                    x_pos = (tick_val - x_min) / (x_max - x_min)
                    ax3.text(x_pos, tick_pos, f'{tick_val}', color='green', fontsize=8, 
                             ha='center', va='center', transform=ax3.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax3.text(label_pos_x, tick_pos, nphi_label, 
                         color='green', fontsize=8, ha='right', va='center', transform=ax3.transAxes, zorder=1001)
                
                nphi_ax.set_zorder(3)
            
            if 'DT' in processed_data.columns:
                dt_ax = ax3.twiny()
                line, = dt_ax.plot(processed_data['DT'], depth, color='red', linewidth=1.5, label='DT')
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                dt_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in dt_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                dt_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                   labelbottom=False, labeltop=False, length=0)
                dt_ax.set_xticks([])
                
                dt_max = processed_data['DT'].max()
                if dt_max > 200:
                    dt_ax.set_xlim(80, 620)
                    dt_label = 'DT (us/m)'
                else:
                    dt_ax.set_xlim(30, 150)
                    dt_label = 'DT (us/ft)'
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(2, 1)
                dt_ax.plot([0, 1], [tick_pos, tick_pos], transform=dt_ax.transAxes, color='red', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签
                if dt_max > 200:
                    dt_ticks = [100, 600]
                    x_min, x_max = 80, 620
                else:
                    dt_ticks = [40, 140]
                    x_min, x_max = 30, 150
                
                for tick_val in dt_ticks:
                    x_pos = (tick_val - x_min) / (x_max - x_min)
                    ax3.text(x_pos, tick_pos, f'{tick_val}', color='red', fontsize=8, 
                             ha='center', va='center', transform=ax3.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax3.text(label_pos_x, tick_pos, dt_label, 
                         color='red', fontsize=8, ha='right', va='center', transform=ax3.transAxes, zorder=1001)
                
                dt_ax.set_zorder(4)
            
            pe_curve = None
            if 'PEF' in processed_data.columns:
                pe_curve = 'PEF'
            elif 'PE' in processed_data.columns:
                pe_curve = 'PE'
            
            if pe_curve:
                pe_ax = ax3.twiny()
                line, = pe_ax.plot(processed_data[pe_curve], depth, color='orange', linewidth=1.5, label=pe_curve)
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                pe_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in pe_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                pe_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                  labelbottom=False, labeltop=False, length=0)
                pe_ax.set_xticks([])
                pe_ax.set_xlim(-1, 11)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(2, 0)
                pe_ax.plot([0, 1], [tick_pos, tick_pos], transform=pe_ax.transAxes, color='orange', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                pe_ticks = [0, 10]
                for tick_val in pe_ticks:
                    x_pos = (tick_val - (-1)) / (11 - (-1))
                    ax3.text(x_pos, tick_pos, f'{tick_val}', color='orange', fontsize=8, 
                             ha='center', va='center', transform=ax3.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax3.text(label_pos_x, tick_pos, f'{pe_curve} (b/e)', 
                         color='orange', fontsize=8, ha='right', va='center', transform=ax3.transAxes, zorder=1001)
                
                left_half_clip = plt.Rectangle((0, 0), 0.5, 0.88, transform=ax3.transAxes, clip_on=False, facecolor='none', edgecolor='none')
                ax3.add_patch(left_half_clip)
                line.set_clip_path(left_half_clip)
                
                pe_ax.set_zorder(5)
            
            # ========== 第4道: 深度道 ==========
            ax4 = axes[3]
            for spine in ax4.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
                spine.set_linestyle('-')
            ax4.spines['top'].set_visible(False)  # 一开始就隐藏顶部边框
            
            ax4.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
           
            ax4.set_ylim(depth_max, depth_min)
            
            # 绘制道头区和曲线区分界线
            ax4.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax4.transAxes)
            ax4.text(0.5, curve_height + (1 - curve_height)/2, '深度 (m)', ha='center', va='center', transform=ax4.transAxes, fontsize=12, fontfamily='Microsoft YaHei')
            
            # 创建道头区的裁剪矩形
            header_clip_rect4 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax4.transAxes, clip_on=False, fill=False)
            ax4.add_patch(header_clip_rect4)
            
            # 创建曲线区的裁剪矩形
            depth_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax4.transAxes, clip_on=False, fill=False)
            ax4.add_patch(depth_clip_rect)
            
            # 隐藏y轴刻度和标签
            ax4.set_yticks([])
            ax4.set_yticklabels([])
            
            # 在曲线区绘制短线刻度线（长度6像素，方向向内）和深度标签
            for depth_val in major_ticks:
                # 计算相对位置（注意y轴是倒置的）
                relative_pos = 1 - (depth_val - depth_min) / (depth_max - depth_min)
                # 只在曲线区绘制（relative_pos <= curve_height）
                if relative_pos <= curve_height:
                    # 在左侧绘制短线刻度（向内）
                    ax4.plot([0.02, 0.08], [depth_val, depth_val], color='black', linewidth=1, zorder=1001)
                    # 在右侧绘制短线刻度（向内）
                    ax4.plot([0.92, 0.98], [depth_val, depth_val], color='black', linewidth=1, zorder=1001)
                    # 在中间绘制深度标签
                    ax4.text(0.5, depth_val, f'{int(depth_val)}', ha='center', va='center', fontsize=10, fontfamily='Microsoft YaHei', zorder=1002)
            
            # 设置边框只在曲线区显示（不延伸到道头区）
            ax4.spines['left'].set_bounds(depth_max, depth_min)  # 只在曲线区显示左边框
            ax4.spines['right'].set_bounds(depth_max, depth_min)  # 只在曲线区显示右边框
            ax4.spines['left'].set_position(('axes', 0))
            ax4.spines['right'].set_position(('axes', 1))
            ax4.spines['top'].set_visible(False)  # 隐藏顶部边框，避免道名上方出现竖线
            ax4.spines['bottom'].set_visible(True)

            # 绘制道头区的外框（只绘制底部和顶部横线，不绘制左右边框，避免道名上方出现竖线）
            # 底部横线（已经在前面绘制了）
            # 顶部横线
            ax4.plot([0, 1], [1, 1], color='black', linewidth=1, transform=ax4.transAxes)
            
            ax4.set_ylabel('')
            ax4.set_zorder(1000)
            
            # ========== 第5道: 含水饱和度 ==========
            ax5 = axes[4]
            # 设置完整的黑实线边框
            for spine in ax5.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
                spine.set_linestyle('-')
            ax5.spines['top'].set_visible(False)  # 一开始就隐藏顶部边框
            
            ax5.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax5.set_xlim(0, 1)
            ax5.set_ylim(depth_max, depth_min)
            
            ax5.set_ylabel('')
            ax5.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax5.set_yticks([])
            
            # 绘制道头区和曲线区分界线
            ax5.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax5.transAxes)
            
            # 绘制道头区的完整外框
            header_rect5 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax5.transAxes, 
                                         fill=False, edgecolor='black', linewidth=1, linestyle='-')
            ax5.add_patch(header_rect5)
            
            # 绘制曲线区的外框 - 确保边框延伸到整个轴
            ax5.spines['left'].set_bounds(0, 1)
            ax5.spines['right'].set_bounds(0, 1)
            ax5.spines['top'].set_visible(False)  # 隐藏顶部边框，避免道名上方出现竖线
            ax5.spines['bottom'].set_visible(True)
            # 设置边框位置
            ax5.spines['left'].set_position(('axes', 0))
            ax5.spines['right'].set_position(('axes', 1))

            header_clip_rect5 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax5.transAxes, clip_on=False, fill=False)
            ax5.add_patch(header_clip_rect5)
            
            clip_rect5 = plt.Rectangle((0, 0), 1, curve_height, transform=ax5.transAxes, clip_on=False, fill=False)
            ax5.add_patch(clip_rect5)
            
            # 绘制10米横线（主刻度，粗线）
            for depth_val in major_ticks:
                line = ax5.axhline(y=depth_val, color='black', linewidth=1, zorder=500)
                line.set_clip_path(clip_rect5)
            
            # 绘制1米横线（次刻度，细线）
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax5.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect5)
            
            # 只在第5道中间位置绘制垂直十等分线（不延伸到道头区）
            for i in range(1, 10):
                x = i / 10.0
                if i == 5:
                    line = ax5.axvline(x=x, color='black', linewidth=1.0, zorder=500)
                else:
                    line = ax5.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect5)
            
            sw_column = 'Sw' if 'Sw' in processed_data.columns else 'SW' if 'SW' in processed_data.columns else None
            if sw_column:
                sw_ax = ax5.twiny()
                line, = sw_ax.plot(processed_data[sw_column], depth, color='blue', linewidth=1.5, label='Sw')
                line.set_clip_path(clip_rect5)
                line.set_zorder(2000)
                
                sw_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in sw_ax.spines.items():
                    spine.set_visible(False)  # 隐藏所有spine
                
                # 完全隐藏默认刻度和标签
                sw_ax.tick_params(axis='x', which='both', bottom=False, top=False, 
                                   labelbottom=False, labeltop=False, length=0)
                sw_ax.set_xticks([])
                sw_ax.set_xlim(-0.1, 1.1)
                
                # 在道头区内绘制刻度横线（代替spine）
                tick_pos = get_tick_position(4, 0)
                sw_ax.plot([0, 1], [tick_pos, tick_pos], transform=sw_ax.transAxes, color='blue', linewidth=1, zorder=1000)
                
                # 手动在道头区内绘制刻度标签（使用axes坐标）
                sw_ticks = [0, 1]
                for tick_val in sw_ticks:
                    x_pos = (tick_val - (-0.1)) / (1.1 - (-0.1))
                    ax5.text(x_pos, tick_pos, f'{tick_val}', color='blue', fontsize=8, 
                             ha='center', va='center', transform=ax5.transAxes, zorder=1001)
                
                # 在刻度线旁边添加曲线标签
                label_pos_x = 0.95  # 右侧位置
                ax5.text(label_pos_x, tick_pos, 'Sw (v/v)', 
                         color='blue', fontsize=8, ha='right', va='center', transform=ax5.transAxes, zorder=1001)
                
                sw_ax.set_zorder(2)
            
            # ========== 第6道: 岩性剖面 ==========
            ax6 = axes[5]
            # 设置完整的黑实线边框
            for spine in ax6.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
                spine.set_linestyle('-')
            ax6.spines['top'].set_visible(False)  # 一开始就隐藏顶部边框
            
            ax6.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax6.set_xlim(0, 1)
            ax6.set_ylim(depth_max, depth_min)
            
            ax6.set_ylabel('')
            ax6.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax6.set_yticks([])
            
            # 绘制道头区和曲线区分界线
            ax6.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax6.transAxes)
            
            # 绘制道头区的顶部横线（不绘制左右边框，避免道名上方出现竖线）
            ax6.plot([0, 1], [1, 1], color='black', linewidth=1, transform=ax6.transAxes)
            
            # 设置spine只在曲线区显示
            ax6.spines['left'].set_bounds(depth_max, depth_min)
            ax6.spines['right'].set_bounds(depth_max, depth_min)
            ax6.spines['top'].set_visible(False)
            ax6.spines['bottom'].set_visible(True)

            clip_rect6 = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax6.add_patch(clip_rect6)
            
            litho_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes, clip_on=False, fill=False)
            ax6.add_patch(litho_clip_rect)

            # 绘制曲线区的完整外框（使用矩形覆盖整个曲线区）
            curve_rect6 = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes,
                                        fill=False, edgecolor='black', linewidth=1, linestyle='-')
            ax6.add_patch(curve_rect6)
            
            if has_enough_curves and 'LITHOLOGY' in processed_data.columns:
                lithology_colors = {
                    '砂岩': 'yellow',
                    '泥岩': 'brown',
                    '碳酸盐岩': 'gray',
                    '混合岩': 'lightgray'
                }
                
                for i in range(len(processed_data) - 1):
                    md1 = processed_data.iloc[i]['MD']
                    md2 = processed_data.iloc[i+1]['MD']
                    lithology = processed_data.iloc[i]['LITHOLOGY']
                    color = lithology_colors.get(lithology, 'white')
                    patch = ax6.fill_betweenx([md1, md2], 0, 0.5, color=color, alpha=0.8)
                    patch.set_clip_path(litho_clip_rect)
                
                lithology_legend = []
                for lith, color in lithology_colors.items():
                    lithology_legend.append(plt.Line2D([0], [0], color=color, lw=4, label=lith))
                ax6.legend(handles=lithology_legend, loc='upper center', bbox_to_anchor=(0.5, curve_height + (1 - curve_height)/2), ncol=2, fontsize=6)
                
                ax6.set_ylim(depth_max, depth_min)
            
            # ========== 第7道: 沉积相 ==========
            ax7 = axes[6]
            # 设置完整的黑实线边框
            for spine in ax7.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
                spine.set_linestyle('-')
            ax7.spines['top'].set_visible(False)  # 一开始就隐藏顶部边框
            
            ax7.set_ylabel('')
            ax7.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax7.set_yticks([])
            
            ax7.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax7.set_xlim(0, 1)
            ax7.set_ylim(depth_max, depth_min)
            
            # 绘制道头区和曲线区分界线
            ax7.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax7.transAxes)
            
            # 绘制道头区的顶部横线（不绘制左右边框，避免道名上方出现竖线）
            ax7.plot([0, 1], [1, 1], color='black', linewidth=1, transform=ax7.transAxes)

            # 设置spine只在曲线区显示
            ax7.spines['left'].set_bounds(depth_max, depth_min)
            ax7.spines['right'].set_bounds(depth_max, depth_min)
            ax7.spines['top'].set_visible(False)
            ax7.spines['bottom'].set_visible(True)

            clip_rect7 = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax7.add_patch(clip_rect7)

            facies_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes, clip_on=False, fill=False)
            ax7.add_patch(facies_clip_rect)

            # 绘制曲线区的完整外框（使用矩形覆盖整个曲线区）
            curve_rect7 = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes,
                                        fill=False, edgecolor='black', linewidth=1, linestyle='-')
            ax7.add_patch(curve_rect7)

            # ========== 第8道: 测井解释 ==========
            ax8 = axes[7]
            ax8.set_ylabel('')
            ax8.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, pad=10)
            ax8.set_yticks([])
            
            ax8.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax8.set_xlim(0, 1)
            ax8.set_ylim(depth_max, depth_min)
            
            # 绘制道头区和曲线区分界线
            ax8.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax8.transAxes)

            clip_rect8 = plt.Rectangle((0, 0), 1, curve_height, transform=ax8.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax8.add_patch(clip_rect8)
            
            interp_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax8.transAxes, clip_on=False, fill=False)
            ax8.add_patch(interp_clip_rect)
            
            # 只有当曲线数量足够时才绘制沉积相
            if has_enough_curves and 'FACIES' in processed_data.columns:
                facies_colors = {
                    # 三角洲前缘亚相
                    '水下分流河道': 'darkred',
                    '河口坝': 'orange',
                    '远砂坝': 'gold',
                    '席状砂': 'lightyellow',
                    '分流间湾': 'lightblue',
                    # 三角洲平原亚相
                    '分流河道': 'red',
                    '天然堤': 'coral',
                    '决口扇': 'tomato',
                    '泛滥平原': 'limegreen',
                    '沼泽': 'forestgreen',
                    # 前三角洲亚相
                    '前三角洲泥': 'olive',
                    # 湖泊相
                    '深湖泥': 'slategray',
                    '浅湖泥': 'lightgray',
                    # 河流相
                    '河床亚相': 'firebrick',
                    '河漫滩': 'sandybrown',
                    # 默认分类
                    '砂质沉积': 'wheat',
                    '过渡带': 'khaki',
                    '泥质沉积': 'darkolivegreen',
                    '其他': 'white'
                }
                
                for i in range(len(processed_data) - 1):
                    md1 = processed_data.iloc[i]['MD']
                    md2 = processed_data.iloc[i+1]['MD']
                    facies = processed_data.iloc[i]['FACIES']
                    color = facies_colors.get(facies, 'white')
                    patch = ax7.fill_betweenx([md1, md2], 0, 0.5, color=color, alpha=0.8)
                    patch.set_clip_path(facies_clip_rect)
                
                facies_legend = []
                for facies, color in facies_colors.items():
                    facies_legend.append(plt.Line2D([0], [0], color=color, lw=4, label=facies))
                ax7.legend(handles=facies_legend, loc='upper center', bbox_to_anchor=(0.5, curve_height + (1 - curve_height)/2), ncol=2, fontsize=6)
                
                ax7.set_ylim(depth_max, depth_min)
            
            if has_enough_curves and 'INTERPRETATION' in processed_data.columns:
                interpretation_colors = {
                    '油层': 'green',
                    '气层': 'yellow',
                    '水层': 'blue',
                    '干层': 'saddlebrown',
                    '可疑层': 'palegreen',
                    'OIL': 'green',
                    'GAS': 'yellow',
                    'WATER': 'blue',
                    'DRY': 'saddlebrown',
                    'Undefined': 'gray'
                }

                for i in range(len(processed_data) - 1):
                    md1 = processed_data.iloc[i]['MD']
                    md2 = processed_data.iloc[i+1]['MD']
                    interpretation = processed_data.iloc[i]['INTERPRETATION']
                    color = interpretation_colors.get(interpretation, 'white')
                    patch = ax8.fill_betweenx([md1, md2], 0, 0.5, color=color, alpha=0.8)
                    patch.set_clip_path(interp_clip_rect)

                interpretation_legend = []
                for interp, color in interpretation_colors.items():
                    if interp in ['油层', '气层', '水层', '干层', '可疑层']:
                        interpretation_legend.append(plt.Line2D([0], [0], color=color, lw=4, label=interp))
                ax8.legend(handles=interpretation_legend, loc='upper center', bbox_to_anchor=(0.5, curve_height + (1 - curve_height)/2), ncol=2, fontsize=6)
            
            # ========== 隐藏所有道（除深度道、后3道外）的深度轴标签、刻度和边框 ==========
            for i, ax in enumerate(axes):
                if i == 3:  # 深度道单独处理
                    continue
                if i >= 5:  # 后3道（第6、7、8道）保持边框显示
                    continue
                ax.set_ylabel('')
                ax.set_yticklabels([])
                ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False, labelright=False, pad=10, length=0)
                ax.set_yticks([])
                ax.set_ylim(depth_max, depth_min)
                ax.yaxis.set_visible(False)
                ax.yaxis.set_ticks([])
                ax.yaxis.set_ticklabels([])
                # 隐藏左右边框（只有深度道和后3道保留边框）
                ax.spines['left'].set_visible(False)
                ax.spines['right'].set_visible(False)
            
            # 为所有道设置下边框（作为道之间的分隔线）
            # 注意：不设置顶部边框，因为道头区已经有外框，顶部边框会出现在道名上方形成不明竖线
            for ax in axes:
                ax.set_ylim(depth_max, depth_min)
                ax.spines['top'].set_visible(False)  # 隐藏顶部边框，避免道名上方出现不明竖线
                ax.spines['bottom'].set_visible(True)
                ax.spines['bottom'].set_color('black')
                ax.spines['bottom'].set_linewidth(1)

            # 为后3道（第6、7、8道）绘制完整的黑实线外框
            ax6 = axes[5]
            ax7 = axes[6]
            ax8 = axes[7]

            # 为第6、7、8道绘制完整的外框（使用矩形）
            for ax, track_name in [(ax6, 'Lithology Profile'), (ax7, 'Sedimentary Facies'), (ax8, 'Log Interpretation')]:
                # 绘制曲线区的完整外框
                curve_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax.transAxes,
                                           fill=False, edgecolor='black', linewidth=1, linestyle='-')
                ax.add_patch(curve_rect)

                # 绘制道头区的完整外框
                header_rect = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax.transAxes,
                                           fill=False, edgecolor='black', linewidth=1, linestyle='-')
                ax.add_patch(header_rect)

            # 深度道（第4道）设置 - 保持与前面设置一致
            ax4 = axes[3]
            ax4.set_zorder(1000)
            
            # 添加图名和道名
            # 布局结构（从底部到顶部）：
            # 1. 曲线区
            # 2. 道头区（6厘米，包含标签、首尾数字和刻度线）
            # 3. 道名到道头区间距（1厘米）
            # 4. 道名
            # 5. 图名到道名间距（1厘米）
            # 6. 图名
            
            well_name = results.get('well_name', 'Unknown Well')

            # 道名位置：在道头区顶部上方1厘米处
            # 道头区顶部 = curve_height + header_height
            # 道名位置 = 道头区顶部 + 道名到道头区间距
            # 道名位置：在道头区顶部
            track_name_y_axes = curve_height + header_height
            
            # 图名位置：在道名上方1厘米处
            title_y = track_name_y_axes + title_trackname_gap
            # 确保图名不超出figure边界
            title_y = min(title_y, 0.98)

            fig.suptitle(f"Composite Log - {well_name}", fontsize=16, fontweight='bold', fontfamily='Microsoft YaHei', y=title_y, ha='center')
            
            # 使用axes坐标绘制道名，位于道头区上方
            ax1.text(0.5, track_name_y_axes, 'Lithology', ha='center', va='center', transform=ax1.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax2.text(0.5, track_name_y_axes, 'Resistivity', ha='center', va='center', transform=ax2.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax3.text(0.5, track_name_y_axes, 'Porosity', ha='center', va='center', transform=ax3.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax4.text(0.5, track_name_y_axes, 'Depth', ha='center', va='center', transform=ax4.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax5.text(0.5, track_name_y_axes, 'Water Saturation', ha='center', va='center', transform=ax5.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax6.text(0.5, track_name_y_axes, 'Lithology Profile', ha='center', va='center', transform=ax6.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax7.text(0.5, track_name_y_axes, 'Sedimentary Facies', ha='center', va='center', transform=ax7.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax8.text(0.5, track_name_y_axes, 'Log Interpretation', ha='center', va='center', transform=ax8.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            
            # 保存文件
            well_output_dir = Path('output') / well_name
            viz_dir = well_output_dir / 'visualization'
            viz_dir.mkdir(exist_ok=True, parents=True)
            
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            well_log_composite_path = viz_dir / f'well_log_composite_{timestamp}.png'
            
            # 打印绝对路径
            abs_path = well_log_composite_path.absolute()
            logger.info(f"尝试保存Composite Log到绝对路径: {abs_path}")
            
            # 保存文件
            logger.info("开始保存Composite Log...")
            logger.info(f"Number of data points: {len(data)}")
            logger.info(f"Figure size: {fig.get_size_inches()}")
            
            try:
                # 保存文件，使用较低的dpi以减少内存使用
                logger.info(f"尝试保存Composite Log到: {abs_path}")
                plt.savefig(abs_path, dpi=80, bbox_inches='tight')
                plt.close(fig)
                logger.info("已保存Composite Log")

                # 检查文件是否存在并记录
                if abs_path.exists():
                    results['visualization_results'] = {'well_log_composite': str(abs_path)}
                    return str(abs_path)
                else:
                    logger.error(f"Composite Log保存失败: {abs_path}, File does not exist")    
            except Exception as e:
                logger.error(f"保存Composite Log时发生错误: {e}")
                import traceback
                traceback.print_exc()
                return None
        except Exception as e:
            logger.error(f"生成Composite Log时发生错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def visualize_all(self, results):
        """可视化所有结果"""
        if not results:
            logger.error("无结果可可视化")
            return None
        
        try:
            # 可视化其他曲线
            if 'processed_data' in results:
                return self.visualize_composite_log(results['processed_data'], results)
            
            logger.info("所有结果可视化完成")
            return str(self.viz_dir)
        except Exception as e:
            logger.error(f"可视化所有结果失败: {e}")
            return None
