# =============================================================================
# 修复后的测井综合图可视化函数
# =============================================================================
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def visualize_composite_log_fixed(data, results):
    """修复后的可视化8道综合测井曲线"""
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
        
        # ============== 布局参数 ==============
        # 道头区高度（固定为6厘米）
        HEADER_HEIGHT_CM = 6
        # 道名到道头区的距离（1厘米）
        TRACKNAME_HEADER_GAP_CM = 1
        # 图名到道名的距离（1厘米）
        TITLE_TRACKNAME_GAP_CM = 1
        # 曲线区比例（1:200）
        CURVE_SCALE = 1/200  # 深度范围(米) * 100 / 200 = 曲线区高度(厘米)
        
        # 计算各部分高度（厘米）
        curve_height_cm = depth_range * 100 * CURVE_SCALE
        header_height_cm = HEADER_HEIGHT_CM
        trackname_header_gap_cm = TRACKNAME_HEADER_GAP_CM
        title_trackname_gap_cm = TITLE_TRACKNAME_GAP_CM
        
        # 转换为英寸
        curve_height_inches = curve_height_cm / 2.54
        header_height_inches = header_height_cm / 2.54
        trackname_header_gap_inches = trackname_header_gap_cm / 2.54
        title_trackname_gap_inches = title_trackname_gap_cm / 2.54
        
        # 计算总高度（英寸）
        total_height_inches = curve_height_inches + header_height_inches + trackname_header_gap_inches + title_trackname_gap_inches
        total_height_inches = max(total_height_inches, 14)  # 最小高度14英寸
        
        # 计算各部分占figure的比例
        curve_height_ratio = curve_height_inches / total_height_inches
        header_height_ratio = header_height_inches / total_height_inches
        trackname_header_gap_ratio = trackname_header_gap_inches / total_height_inches
        title_trackname_gap_ratio = title_trackname_gap_inches / total_height_inches
        
        # 计算垂直位置（figure坐标，0在底部，1在顶部）
        curve_top = curve_height_ratio  # 曲线区顶部
        header_top = curve_top + header_height_ratio  # 道头区顶部
        trackname_y = header_top + trackname_header_gap_ratio  # 道名位置
        title_y = trackname_y + title_trackname_gap_ratio  # 图名位置
        title_y = min(title_y, 0.98)  # 确保不超出边界
        
        print(f"布局参数:")
        print(f"  曲线区顶部: {curve_top:.4f}")
        print(f"  道头区顶部: {header_top:.4f}")
        print(f"  道名位置: {trackname_y:.4f}")
        print(f"  图名位置: {title_y:.4f}")
        
        # ============== 创建Figure和Axes ==============
        fig = plt.figure(figsize=(24, total_height_inches))
        
        # 定义8道的宽度比例
        track_widths = [1, 1, 1, 0.5, 1, 1, 1, 1]
        total_width = sum(track_widths)
        
        # 计算道边界（figure坐标）
        track_boundaries = []
        current_pos = 0
        for w in track_widths:
            left = current_pos / total_width
            right = (current_pos + w) / total_width
            track_boundaries.append((left, right))
            current_pos += w
        
        gs = gridspec.GridSpec(1, 8, width_ratios=track_widths, wspace=0)
        axes = [fig.add_subplot(gs[i]) for i in range(8)]
        for i in range(1, 8):
            axes[i].sharey(axes[0])
        
        # ============== 辅助函数 ==============
        def draw_tick_line(fig, track_idx, tick_y, color):
            """在指定道的道头区内绘制刻度线"""
            left, right = track_boundaries[track_idx]
            line = Line2D([left, right], [tick_y, tick_y], 
                         transform=fig.transFigure, color=color, linewidth=1, zorder=1000)
            fig.add_artist(line)
            print(f"刻度线: 道{track_idx+1} y={tick_y:.4f} (在道头区内: {curve_top <= tick_y <= header_top})")
        
        def draw_tick_labels(fig, track_idx, tick_y, x_min, x_max, tick_values, curve_label, color, log_scale=False):
            """绘制刻度标签和曲线标签"""
            left, right = track_boundaries[track_idx]
            label_offset = 0.015
            
            # 确定标签位置
            if tick_y > header_top - label_offset * 3:
                label_y = tick_y - label_offset
            else:
                label_y = tick_y + label_offset
            
            # 确保标签在道头区内
            label_y = max(curve_top + 0.005, min(label_y, header_top - 0.005))
            
            # 绘制首尾数据
            for tick_val in tick_values:
                if log_scale:
                    x_pos = left + ((np.log10(tick_val) - np.log10(x_min)) / (np.log10(x_max) - np.log10(x_min))) * (right - left)
                else:
                    x_pos = left + ((tick_val - x_min) / (x_max - x_min)) * (right - left)
                
                # 确保在道边界内
                x_pos = max(left + 0.005, min(x_pos, right - 0.005))
                
                fig.text(x_pos, label_y, str(tick_val), 
                         color=color, fontsize=10, ha='center', va='center', 
                         transform=fig.transFigure, zorder=10000)
            
            # 绘制曲线标签
            label_x = (left + right) / 2
            fig.text(label_x, label_y, curve_label, 
                     color=color, fontsize=10, ha='center', va='center', 
                     transform=fig.transFigure, zorder=10000)
        
        def get_tick_position(cm_from_bottom):
            """计算刻度线位置（从道头区底部向上偏移cm_from_bottom厘米）"""
            return curve_top + (cm_from_bottom / HEADER_HEIGHT_CM) * header_height_ratio
        
        # ============== 刻度位置定义 ==============
        # 道头区高度6厘米，刻度从底部向上偏移的厘米数
        tick_positions = {
            # 道索引: [曲线标签, 颜色, 刻度位置(cm), x_min, x_max, 刻度值]
            0: [  # 岩性道
                ('GR (API)', 'green', 3.2, -10, 210, [0, 200]),
                ('SP (mV)', 'blue', 2.0, -110, 110, [-100, 100]),
                ('CAL (in)', 'red', 0.8, 5.5, 12.5, [6, 12]),
            ],
            1: [  # 电阻率道
                ('LLD (ohm-m)', 'black', 3.2, 0.15, 3000, [0.2, 2000]),
                ('LLS (ohm-m)', 'red', 2.0, 0.15, 3000, [0.2, 2000]),
                ('MSFL (ohm-m)', 'green', 0.8, 0.15, 3000, [0.2, 2000]),
            ],
            2: [  # 孔隙度道
                ('PE (b/e)', 'orange', 0.8, -1, 11, [0, 10]),
                ('DT (us/ft)', 'red', 2.0, 30, 150, [40, 140]),
                ('NPHI (v/v)', 'green', 3.2, -0.1, 1.1, [0, 1]),
                ('RHOB (g/cc)', 'blue', 4.4, 1.7, 2.9, [1.8, 2.8]),
            ],
            4: [  # 饱和度道
                ('Sw (v/v)', 'blue', 2.0, -0.1, 1.1, [0, 1]),
            ],
        }
        
        # ============== 绘制各道 ==============
        for track_idx in range(8):
            ax = axes[track_idx]
            
            # 设置坐标轴
            ax.set_xlim(0, 1)
            ax.set_ylim(depth_max, depth_min)
            ax.set_yticks([])
            ax.set_xticks([])
            
            # 隐藏所有spine
            for spine in ax.spines.values():
                spine.set_visible(False)
            
            # 绘制道头区和曲线区分界线
            ax.plot([0, 1], [curve_top, curve_top], transform=ax.transAxes, color='black', linewidth=1)
            
            # 如果是有刻度的道，绘制刻度
            if track_idx in tick_positions:
                for curve_label, color, cm_pos, x_min, x_max, tick_vals in tick_positions[track_idx]:
                    tick_y = get_tick_position(cm_pos)
                    draw_tick_line(fig, track_idx, tick_y, color)
                    if track_idx == 1:  # 电阻率道使用对数刻度
                        draw_tick_labels(fig, track_idx, tick_y, x_min, x_max, tick_vals, curve_label, color, log_scale=True)
                    else:
                        draw_tick_labels(fig, track_idx, tick_y, x_min, x_max, tick_vals, curve_label, color)
        
        # ============== 绘制深度道（第4道） ==============
        ax4 = axes[3]
        ax4.set_ylim(depth_max, depth_min)
        ax4.text(0.5, (curve_top + header_top) / 2, '深度 (m)', ha='center', va='center', transform=ax4.transAxes, fontsize=12)
        
        # ============== 绘制道名 ==============
        track_names = [
            'Lithology', 'Resistivity', 'Porosity', 'Depth',
            'Water Saturation', 'Lithology Profile', 'Sedimentary Facies', 'Log Interpretation'
        ]
        for i, name in enumerate(track_names):
            left, right = track_boundaries[i]
            center = (left + right) / 2
            fig.text(center, trackname_y, name, ha='center', va='center', fontsize=14, fontweight='bold')
            print(f"道{i+1} 道名 '{name}' 位置: x={center:.4f}, y={trackname_y:.4f}")
        
        # ============== 绘制图名 ==============
        well_name = results.get('well_name', 'Unknown Well')
        fig.suptitle(f"Composite Log - {well_name}", fontsize=16, fontweight='bold', y=title_y, ha='center')
        
        # ============== 保存文件 ==============
        well_output_dir = Path(results.get('output_dir', 'output')) / well_name
        well_output_dir.mkdir(exist_ok=True, parents=True)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = well_output_dir / f'{well_name}_composite_log_{timestamp}.png'
        
        plt.savefig(output_path, dpi=80, bbox_inches='tight')
        plt.close(fig)
        
        print(f"保存到: {output_path}")
        results['visualization_results'] = {'well_log_composite': str(output_path)}
        return str(output_path)
        
    except Exception as e:
        logger.error(f"生成Composite Log时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============== 测试 ==============
if __name__ == '__main__':
    import pandas as pd
    
    # 创建测试数据
    depth = np.arange(1000, 1050, 0.1)
    test_data = pd.DataFrame({
        'MD': depth,
        'GR': np.random.uniform(0, 200, len(depth)),
        'SP': np.random.uniform(-100, 100, len(depth)),
        'CAL': np.random.uniform(6, 12, len(depth)),
        'LLD': np.random.uniform(0.2, 2000, len(depth)),
        'LLS': np.random.uniform(0.2, 2000, len(depth)),
        'MSFL': np.random.uniform(0.2, 2000, len(depth)),
        'RHOB': np.random.uniform(1.85, 2.85, len(depth)),
        'NPHI': np.random.uniform(0, 0.45, len(depth)),
        'DT': np.random.uniform(50, 150, len(depth)),
        'PE': np.random.uniform(1, 10, len(depth)),
        'Sw': np.random.uniform(0, 1, len(depth)),
    })
    
    results = {'well_name': 'TestWell_Fixed', 'output_dir': 'output'}
    visualize_composite_log_fixed(test_data, results)