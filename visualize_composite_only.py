import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib.colors import LogNorm, Normalize
import pandas as pd
import datetime
from pathlib import Path
import logging
from matplotlib.lines import Line2D
import matplotlib.patches as patches

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('well_log_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 设置matplotlib中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'Heiti TC', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.default'] = 'regular'

# 统一刻度设置参数
TICK_PARAMS = {
    'axis': 'x',
    'top': True,
    'bottom': False,
    'labeltop': True,
    'labelbottom': False,
    'pad': 10,
    'length': 0,
    'direction': 'in',
    'labelsize': 8,
    'labelfontfamily': 'Microsoft YaHei'
}

# 统一标签设置参数
LABEL_PARAMS = {
    'fontsize': 12,
    'labelpad': 1,
    'fontfamily': 'Microsoft YaHei'
}

class DataVisualizer:
    """数据可视化类"""
    
    def __init__(self, output_dir):
        """初始化可视化器"""
        self.output_dir = Path(output_dir)
        self.viz_dir = self.output_dir / 'visualization'
        self.viz_dir.mkdir(exist_ok=True, parents=True)
        self.results = {}
    
    def visualize_composite_log(self, data, results):
        """可视化8道综合测井曲线"""
        if data is None:
            logger.error("Data not loaded")
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
            depth_min = depth.min()
            depth_max = depth.max()
            depth_range = depth_max - depth_min
            
            if depth_range <= 0:
                logger.error("Depth范围无效")
                return None
            
            import matplotlib.gridspec as gridspec
            fig = plt.figure(figsize=(24, 15))
            gs = gridspec.GridSpec(1, 8, width_ratios=[1, 1, 1, 0.5, 1, 1, 1, 1], wspace=0)
            axes = [fig.add_subplot(gs[i]) for i in range(8)]
            for i in range(1, 8):
                axes[i].sharey(axes[0])
            
            # 道头区域固定为6厘米
            header_height_cm = 6
            header_height_inches = header_height_cm / 2.54
            
            actual_depth_range = depth_max - depth_min
            curve_height_cm = actual_depth_range * 100 / 200
            curve_height_inches = curve_height_cm / 2.54
            
            total_fig_height_inches = header_height_inches + curve_height_inches
            total_fig_height_inches = max(total_fig_height_inches, 12)
            fig.set_figheight(total_fig_height_inches)
            
            header_height = header_height_inches / total_fig_height_inches
            curve_height = 1 - header_height
            
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
            
            ax1.set_ylabel('')
            ax1.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax1.set_ylim(depth_max, depth_min)
            ax1.spines['left'].set_position(('axes', 0))
            ax1.set_yticks([])
            
            clip_rect1 = plt.Rectangle((0, 0), 1, curve_height, transform=ax1.transAxes, clip_on=False, fill=False)
            ax1.add_patch(clip_rect1)
            header_clip_rect1 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax1.transAxes, clip_on=False, fill=False)
            ax1.add_patch(header_clip_rect1)
            
            ax1.spines['left'].set_bounds(depth_max, depth_min)
            
            for depth_val in major_ticks:
                line = ax1.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
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
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 1.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                gr_ax.tick_params(**TICK_PARAMS)
                gr_ax.set_xticks([0, 200])
                gr_ax.set_xlim(-10, 210)
                gr_ax.spines['top'].set_visible(True)
                gr_ax.tick_params(axis='x', colors='green', pad=10)
                gr_ax.spines['top'].set_color('green')
                gr_ax.set_xlabel('GR (API)', color='green', **LABEL_PARAMS)
                
                for tick in gr_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in gr_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                gr_ax.spines['top'].set_clip_path(header_clip_rect1)
                gr_ax.spines['top'].set_zorder(1000)
                gr_ax.xaxis.set_clip_path(header_clip_rect1)
                gr_ax.xaxis.set_zorder(1000)
                gr_ax.set_zorder(2)
            
            if 'SP' in processed_data.columns:
                sp_ax = ax1.twiny()
                line, = sp_ax.plot(processed_data['SP'], depth, color='blue', linewidth=1.5, label='SP')
                line.set_clip_path(clip_rect1)
                line.set_zorder(2000)
                
                sp_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in sp_ax.spines.items():
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 2.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                sp_ax.tick_params(**TICK_PARAMS)
                sp_ax.set_xticks([-100, 100])
                sp_ax.set_xlim(-110, 110)
                sp_ax.spines['top'].set_visible(True)
                sp_ax.tick_params(axis='x', colors='blue', pad=10)
                sp_ax.spines['top'].set_color('blue')
                sp_ax.set_xlabel('SP (mV)', color='blue', **LABEL_PARAMS)
                
                for tick in sp_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in sp_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                sp_ax.spines['top'].set_clip_path(header_clip_rect1)
                sp_ax.spines['top'].set_zorder(1000)
                sp_ax.xaxis.set_clip_path(header_clip_rect1)
                sp_ax.xaxis.set_zorder(1000)
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
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 3.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                cal_ax.tick_params(**TICK_PARAMS)
                cal_ax.set_xticks([6, 12])
                cal_ax.set_xlim(5.5, 12.5)
                cal_ax.spines['top'].set_visible(True)
                cal_ax.tick_params(axis='x', colors='red', pad=10)
                cal_ax.spines['top'].set_color('red')
                cal_ax.set_xlabel('CAL (in)', color='red', **LABEL_PARAMS)
                
                for tick in cal_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in cal_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect1)
                    tick.label2.set_clip_path(header_clip_rect1)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                cal_ax.spines['top'].set_clip_path(header_clip_rect1)
                cal_ax.spines['top'].set_zorder(1000)
                cal_ax.xaxis.set_clip_path(header_clip_rect1)
                cal_ax.xaxis.set_zorder(1000)
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
            ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
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
            ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax2.set_yticks([])
            
            for depth_val in major_ticks:
                line = ax2.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
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
                        if spine_name != 'top':
                            spine.set_visible(False)
                        else:
                            spine.set_position(('axes', 1.0 - (1.5 + (i % len(res_positions))) * one_cm_ratio))
                            spine.set_visible(True)
                    
                    res_ax.tick_params(**TICK_PARAMS)
                    res_ax.set_xticks([0.2, 2000])
                    res_ax.set_xlim(0.01, 5000)
                    res_ax.spines['top'].set_visible(True)
                    res_ax.tick_params(axis='x', colors=res_colors[i], pad=10)
                    res_ax.spines['top'].set_color(res_colors[i])
                    res_ax.set_xlabel(f'{col} (ohm-m)', color=res_colors[i], **LABEL_PARAMS)
                    
                    for tick in res_ax.xaxis.get_major_ticks():
                        tick.label1.set_clip_path(header_clip_rect2)
                        tick.label2.set_clip_path(header_clip_rect2)
                        tick.label1.set_zorder(1000)
                        tick.label2.set_zorder(1000)
                    for tick in res_ax.xaxis.get_minor_ticks():
                        tick.label1.set_clip_path(header_clip_rect2)
                        tick.label2.set_clip_path(header_clip_rect2)
                        tick.label1.set_zorder(1000)
                        tick.label2.set_zorder(1000)
                    res_ax.spines['top'].set_clip_path(header_clip_rect2)
                    res_ax.spines['top'].set_zorder(1000)
                    res_ax.xaxis.set_clip_path(header_clip_rect2)
                    res_ax.xaxis.set_zorder(1000)
                    res_ax.set_zorder(i+2)
            
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
            ax3.plot([0, 1], [curve_height, curve_height], transform=ax3.transAxes, color='black', linewidth=1)
            
            clip_rect3 = plt.Rectangle((0, 0), 1, curve_height, transform=ax3.transAxes, clip_on=False, fill=False)
            ax3.add_patch(clip_rect3)
            header_clip_rect3 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax3.transAxes, clip_on=False, fill=False)
            ax3.add_patch(header_clip_rect3)
            
            ax3.set_ylabel('')
            ax3.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax3.set_yticks([])
            
            for spine in ax3.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            for depth_val in major_ticks:
                line = ax3.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(clip_rect3)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax3.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect3)
            
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
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 1.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                rhob_ax.tick_params(**TICK_PARAMS)
                rhob_ax.set_xticks([1.6, 3])
                rhob_ax.set_xlim(1.8, 2.8)
                rhob_ax.spines['top'].set_visible(True)
                rhob_ax.tick_params(axis='x', colors='blue', pad=10)
                rhob_ax.spines['top'].set_color('blue')
                rhob_ax.set_xlabel('RHOB (g/cc)', color='blue', **LABEL_PARAMS)
                
                for tick in rhob_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in rhob_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                rhob_ax.spines['top'].set_clip_path(header_clip_rect3)
                rhob_ax.spines['top'].set_zorder(1000)
                rhob_ax.xaxis.set_clip_path(header_clip_rect3)
                rhob_ax.xaxis.set_zorder(1000)
                rhob_ax.set_zorder(2)
            
            if 'NPHI' in processed_data.columns:
                nphi_ax = ax3.twiny()
                line, = nphi_ax.plot(processed_data['NPHI'], depth, color='green', linewidth=1.5, label='NPHI')
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                nphi_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in nphi_ax.spines.items():
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 2.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                nphi_ax.tick_params(**TICK_PARAMS)
                
                nphi_min = processed_data['NPHI'].min()
                nphi_max = processed_data['NPHI'].max()
                if nphi_max > 1:
                    nphi_ax.set_xticks([0, 60])
                    nphi_ax.set_xlim(-10, 70)
                    nphi_ax.set_xlabel('NPHI (%)', color='green', **LABEL_PARAMS)
                else:
                    nphi_ax.set_xticks([0, 1])
                    nphi_ax.set_xlim(-0.1, 1.1)
                    nphi_ax.set_xlabel('NPHI (v/v)', color='green', **LABEL_PARAMS)
                
                nphi_ax.spines['top'].set_visible(True)
                nphi_ax.tick_params(axis='x', colors='green', pad=10)
                nphi_ax.spines['top'].set_color('green')
                
                for tick in nphi_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in nphi_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                nphi_ax.spines['top'].set_clip_path(header_clip_rect3)
                nphi_ax.spines['top'].set_zorder(1000)
                nphi_ax.xaxis.set_clip_path(header_clip_rect3)
                nphi_ax.xaxis.set_zorder(1000)
                nphi_ax.set_zorder(3)
            
            if 'DT' in processed_data.columns:
                dt_ax = ax3.twiny()
                line, = dt_ax.plot(processed_data['DT'], depth, color='red', linewidth=1.5, label='DT')
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                dt_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in dt_ax.spines.items():
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 3.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                dt_ax.tick_params(**TICK_PARAMS)
                
                dt_max = processed_data['DT'].max()
                if dt_max > 200:
                    dt_ax.set_xticks([100, 600])
                    dt_ax.set_xlim(80, 620)
                    dt_ax.set_xlabel('DT (us/m)', color='red', **LABEL_PARAMS)
                else:
                    dt_ax.set_xticks([40, 140])
                    dt_ax.set_xlim(30, 150)
                    dt_ax.set_xlabel('DT (us/ft)', color='red', **LABEL_PARAMS)
                
                dt_ax.spines['top'].set_visible(True)
                dt_ax.tick_params(axis='x', colors='red', pad=10)
                dt_ax.spines['top'].set_color('red')
                
                for tick in dt_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in dt_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                dt_ax.spines['top'].set_clip_path(header_clip_rect3)
                dt_ax.spines['top'].set_zorder(1000)
                dt_ax.xaxis.set_clip_path(header_clip_rect3)
                dt_ax.xaxis.set_zorder(1000)
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
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 4.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                pe_ax.tick_params(**TICK_PARAMS)
                pe_ax.set_xticks([0, 10])
                pe_ax.set_xlim(-1, 11)
                pe_ax.spines['top'].set_visible(True)
                pe_ax.tick_params(axis='x', colors='orange', pad=10)
                pe_ax.spines['top'].set_color('orange')
                pe_ax.set_xlabel(f'{pe_curve} (b/e)', color='orange', **LABEL_PARAMS)
                
                left_half_clip = plt.Rectangle((0, 0), 0.5, 0.88, transform=ax3.transAxes, clip_on=False, facecolor='none', edgecolor='none')
                ax3.add_patch(left_half_clip)
                line.set_clip_path(left_half_clip)
                
                for tick in pe_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in pe_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                pe_ax.spines['top'].set_clip_path(header_clip_rect3)
                pe_ax.spines['top'].set_zorder(1000)
                pe_ax.xaxis.set_clip_path(header_clip_rect3)
                pe_ax.xaxis.set_zorder(1000)
                pe_ax.set_zorder(5)
            
            # ========== 第4道: 深度道 ==========
            ax4 = axes[3]
            for spine in ax4.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
                spine.set_linestyle('-')
            
            ax4.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax4.set_xlim(0, 1)
            ax4.set_ylim(depth_max, depth_min)
            
            ax4.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax4.transAxes)
            ax4.text(0.5, curve_height + (1 - curve_height)/2, 'Depth (m)', ha='center', va='center', transform=ax4.transAxes, fontsize=12, fontfamily='Microsoft YaHei')
            
            ax4.set_yticks(major_ticks)
            ax4.set_yticks(minor_ticks, minor=True)
            ax4.set_yticklabels([f'{int(tick)}' for tick in major_ticks], fontsize=12, fontfamily='Microsoft YaHei', visible=True)
            
            ax4.tick_params(axis='y', which='major', left=True, right=True, labelsize=8, labelfontfamily='Microsoft YaHei', length=6, direction='in', zorder=1001, pad=10)
            ax4.tick_params(axis='y', which='minor', left=True, right=True, labelsize=8, labelfontfamily='Microsoft YaHei', length=3, labelleft=False, labelright=False, direction='in', zorder=1001, pad=10)
            
            ax4.spines['left'].set_bounds(depth_max, depth_min)
            ax4.spines['right'].set_bounds(depth_max, depth_min)
            
            depth_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax4.transAxes, clip_on=False, fill=False)
            ax4.add_patch(depth_clip_rect)
            
            for label in ax4.get_yticklabels():
                label.set_clip_path(depth_clip_rect)
                label.set_zorder(1002)
                label.set_visible(True)
                label.set_clip_on(False)
            for line in ax4.get_yticklines():
                line.set_clip_path(depth_clip_rect)
                line.set_zorder(1002)
                line.set_visible(True)
                line.set_clip_on(False)
            
            ax4.spines['left'].set_clip_path(depth_clip_rect)
            ax4.spines['right'].set_clip_path(depth_clip_rect)
            ax4.spines['left'].set_zorder(1001)
            ax4.spines['right'].set_zorder(1001)
            
            ax4.yaxis.set_tick_params(which='both', pad=10)
            ax4.set_ylabel('')
            ax4.set_zorder(1000)
            
            for depth_val in major_ticks:
                line = ax4.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(depth_clip_rect)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax4.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(depth_clip_rect)
            
            ax4.spines['left'].set_linestyle('-')
            ax4.spines['left'].set_visible(True)
            
            # ========== 第5道: 含水饱和度 ==========
            ax5 = axes[4]
            for spine in ax5.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax5.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax5.set_xlim(0, 1)
            ax5.set_ylim(depth_max, depth_min)
            
            ax5.set_ylabel('')
            ax5.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax5.set_yticks([])
            
            ax5.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax5.transAxes)
            
            header_clip_rect5 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax5.transAxes, clip_on=False, fill=False)
            ax5.add_patch(header_clip_rect5)
            
            clip_rect5 = plt.Rectangle((0, 0), 1, curve_height, transform=ax5.transAxes, clip_on=False, fill=False)
            ax5.add_patch(clip_rect5)
            
            for depth_val in major_ticks:
                line = ax5.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(clip_rect5)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax5.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(clip_rect5)
            
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
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        spine.set_position(('axes', 1.0 - 1.5 * one_cm_ratio))
                        spine.set_visible(True)
                
                sw_ax.tick_params(**TICK_PARAMS)
                sw_ax.set_xticks([0, 1])
                sw_ax.set_xlim(0.1, 1.1)
                sw_ax.spines['top'].set_visible(True)
                sw_ax.tick_params(axis='x', colors='blue', pad=10)
                sw_ax.spines['top'].set_color('blue')
                sw_ax.set_xlabel('Sw (v/v)', color='blue', **LABEL_PARAMS)
                
                for tick in sw_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect5)
                    tick.label2.set_clip_path(header_clip_rect5)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in sw_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect5)
                    tick.label2.set_clip_path(header_clip_rect5)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                sw_ax.spines['top'].set_clip_path(header_clip_rect5)
                sw_ax.spines['top'].set_zorder(1000)
                sw_ax.xaxis.set_clip_path(header_clip_rect5)
                sw_ax.xaxis.set_zorder(1000)
                sw_ax.set_zorder(2)
            
            # ========== 第6道: 岩性剖面 ==========
            ax6 = axes[5]
            for spine in ax6.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax6.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax6.set_xlim(0, 1)
            ax6.set_ylim(depth_max, depth_min)
            
            ax6.set_ylabel('')
            ax6.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax6.set_yticks([])
            
            ax6.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax6.transAxes)
            
            clip_rect6 = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax6.add_patch(clip_rect6)
            ax6.spines['left'].set_position(('axes', 0))
            ax6.spines['left'].set_visible(True)
            
            litho_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes, clip_on=False, fill=False)
            ax6.add_patch(litho_clip_rect)
            
            for depth_val in major_ticks:
                line = ax6.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(litho_clip_rect)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax6.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(litho_clip_rect)
            
            for i in range(1, 10):
                x = i / 10.0
                if i == 5:
                    line = ax6.axvline(x=x, color='black', linewidth=1.0, zorder=500)
                else:
                    line = ax6.axvline(x=x, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(litho_clip_rect)
            
            if 'LITHOLOGY' in processed_data.columns:
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
            for spine in ax7.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax7.set_ylabel('')
            ax7.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax7.set_yticks([])
            
            ax7.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax7.set_xlim(0, 1)
            ax7.set_ylim(depth_max, depth_min)
            
            ax7.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax7.transAxes)
            
            clip_rect7 = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax7.add_patch(clip_rect7)
            ax7.spines['left'].set_position(('axes', 0))
            ax7.spines['left'].set_visible(True)
            
            facies_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes, clip_on=False, fill=False)
            ax7.add_patch(facies_clip_rect)
            
            for depth_val in major_ticks:
                line = ax7.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(facies_clip_rect)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax7.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(facies_clip_rect)
            
            # ========== 第8道: 测井解释 ==========
            ax8 = axes[7]
            ax8.set_ylabel('')
            ax8.tick_params(axis='y', which='both', left=False, right=False, labelsize=8, labelfontfamily='Microsoft YaHei', pad=10)
            ax8.set_yticks([])
            
            for spine in ax8.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1)
            
            ax8.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False, pad=10)
            ax8.set_xlim(0, 1)
            ax8.set_ylim(depth_max, depth_min)
            
            ax8.plot([0, 1], [curve_height, curve_height], color='black', linewidth=1, transform=ax8.transAxes)
            
            clip_rect8 = plt.Rectangle((0, 0), 1, curve_height, transform=ax8.transAxes, clip_on=False, facecolor='none', edgecolor='none')
            ax8.add_patch(clip_rect8)
            ax8.spines['left'].set_position(('axes', 0))
            ax8.spines['left'].set_visible(True)
            
            interp_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=ax8.transAxes, clip_on=False, fill=False)
            ax8.add_patch(interp_clip_rect)
            
            for depth_val in major_ticks:
                line = ax8.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
                line.set_clip_path(interp_clip_rect)
            for depth_val in minor_ticks:
                if depth_val not in major_ticks:
                    line = ax8.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                    line.set_clip_path(interp_clip_rect)
            
            if 'FACIES' in processed_data.columns:
                facies_colors = {
                    '分流河道': 'red',
                    '河口坝': 'orange',
                    '远砂坝': 'yellow',
                    '席状砂': 'lightyellow',
                    '泛滥平原': 'green',
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
            
            if 'INTERPRETATION' in processed_data.columns:
                interpretation_colors = {
                    '油层': 'green',
                    '气层': 'yellow',
                    '水层': 'orange',
                    '干层': 'red',
                    '可疑层': 'white'
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
                    interpretation_legend.append(plt.Line2D([0], [0], color=color, lw=4, label=interp))
                ax8.legend(handles=interpretation_legend, loc='upper center', bbox_to_anchor=(0.5, curve_height + (1 - curve_height)/2), ncol=2, fontsize=6)
            
            # ========== 隐藏所有道的深度轴标签和刻度 ==========
            for i, ax in enumerate(axes):
                if i == 3:
                    continue
                ax.set_ylabel('')
                ax.set_yticklabels([])
                ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False, labelright=False, pad=10)
                ax.spines['left'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.set_yticks([])
                ax.set_ylim(depth_max, depth_min)
                ax.yaxis.set_visible(False)
                ax.yaxis.set_ticks([])
                ax.yaxis.set_ticklabels([])
            
            for ax in axes:
                ax.set_ylim(depth_max, depth_min)
                ax.spines['left'].set_position(('axes', 0))
                for spine_name, spine in ax.spines.items():
                    if i != 3 and (spine_name == 'left' or spine_name == 'right'):
                        spine.set_visible(False)
                    else:
                        spine.set_visible(True)
                        spine.set_color('black')
                        spine.set_linewidth(1)
                        spine.set_zorder(0)
            
            axes[3].set_zorder(1000)
            axes[3].tick_params(axis='y', which='major', left=True, right=True, labelsize=8, labelfontfamily='Microsoft YaHei', zorder=1001, length=6, pad=20)
            axes[3].tick_params(axis='y', which='minor', left=True, right=True, labelsize=8, labelfontfamily='Microsoft YaHei', zorder=1001, length=3, labelleft=False, labelright=False, pad=10)
            axes[3].yaxis.label.set_visible(False)
            axes[3].yaxis.label.set_zorder(1001)
            
            depth_clip_rect = plt.Rectangle((0, 0), 1, curve_height, transform=axes[3].transAxes, clip_on=False, fill=False)
            axes[3].add_patch(depth_clip_rect)
            
            for label in axes[3].get_yticklabels():
                label.set_clip_path(depth_clip_rect)
                label.set_zorder(1002)
                label.set_visible(True)
                label.set_clip_on(False)
            for line in axes[3].get_yticklines():
                line.set_clip_path(depth_clip_rect)
                line.set_zorder(1002)
                line.set_visible(True)
                line.set_clip_on(False)
            
            axes[3].spines['left'].set_visible(True)
            axes[3].spines['left'].set_zorder(1001)
            axes[3].spines['right'].set_visible(True)
            axes[3].spines['right'].set_zorder(1001)
            axes[3].spines['left'].set_bounds(depth_max, depth_min)
            axes[3].spines['right'].set_bounds(depth_max, depth_min)
            axes[3].yaxis.set_visible(True)
            
            major_ticks = np.arange(np.ceil(depth_min / 10) * 10, np.floor(depth_max / 10) * 10 + 10, 10)
            major_ticks = major_ticks[(major_ticks >= depth_min) & (major_ticks <= depth_max)]
            minor_ticks = np.arange(np.ceil(depth_min / 1) * 1, np.floor(depth_max / 1) * 1 + 1, 1)
            minor_ticks = minor_ticks[(minor_ticks >= depth_min) & (minor_ticks <= depth_max)]
            
            axes[3].set_yticks(major_ticks)
            axes[3].set_yticks(minor_ticks, minor=True)
            axes[3].set_yticklabels([f'{int(tick)}' for tick in major_ticks], fontsize=12, fontfamily='Microsoft YaHei', visible=True)
            axes[3].tick_params(axis='y', pad=20)
            axes[3].spines['left'].set_clip_path(depth_clip_rect)
            axes[3].spines['right'].set_clip_path(depth_clip_rect)
            
            # 添加图名和道名
            one_cm_inches = 1 / 2.54
            one_cm_ratio = one_cm_inches / total_fig_height_inches
            
            well_name = results.get('well_name', 'Unknown Well')
            fig.suptitle(f"Composite Log - {well_name}", fontsize=16, fontweight='bold', fontfamily='Microsoft YaHei', y=1.0 + 1 * one_cm_ratio, ha='center')
            
            ax1.text(0.5, 1.0, 'Lithology', ha='center', va='bottom', transform=ax1.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax2.text(0.5, 1.0, 'Resistivity', ha='center', va='bottom', transform=ax2.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax3.text(0.5, 1.0, 'Porosity', ha='center', va='bottom', transform=ax3.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax4.text(0.5, 1.0, 'Depth', ha='center', va='bottom', transform=ax4.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax5.text(0.5, 1.0, 'Water Saturation', ha='center', va='bottom', transform=ax5.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax6.text(0.5, 1.0, 'Lithology Profile', ha='center', va='bottom', transform=ax6.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax7.text(0.5, 1.0, 'Sedimentary Facies', ha='center', va='bottom', transform=ax7.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            ax8.text(0.5, 1.0, 'Log Interpretation', ha='center', va='bottom', transform=ax8.transAxes, fontsize=14, fontweight='bold', fontfamily='Microsoft YaHei')
            
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
                    self.results['visualization_results'] = {'well_log_composite': str(abs_path)}   
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
