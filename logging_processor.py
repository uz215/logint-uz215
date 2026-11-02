import os
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
import lasio
import dlisio
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LoggingDataProcessor:
    """测井资料处理核心类"""
    
    def __init__(self, config=None):
        """初始化处理器"""
        self.config = config or self._get_default_config()
        self.data = None
        self.processed_data = None
        self.results = {}
        self.output_dir = Path(self.config.get('output_dir', 'output'))
        self.output_dir.mkdir(exist_ok=True)
        
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'output_dir': 'output',
            'data_formats': ['csv', 'las', 'dlis', 'xlsx'],
            'quality_check': True,
            'environmental_correction': True,
            'data_processing': True,
            'interpretation': True,
            'visualization': True,
            'report_generation': True,
            'well_test_correction': True
        }
        
    def load_data(self, file_path):
        """加载测井数据"""
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            
            logger.info(f"正在加载数据: {file_path}")
            
            if file_ext == '.csv':
                self.data = pd.read_csv(file_path)
            elif file_ext == '.las':
                try:
                    las = lasio.read(file_path)
                    self.data = las.df().reset_index()
                except ImportError:
                    logger.error("需要安装lasio库: pip install lasio")
                    return None
            elif file_ext == '.dlis':
                try:
                    with dlisio.load(file_path) as f:
                        self.data = pd.DataFrame()
                        for channel in f.channels():
                            self.data[channel.name] = channel.data
                except ImportError:
                    logger.error("需要安装dlisio库: pip install dlisio")
                    return None
            elif file_ext == '.xlsx':
                self.data = pd.read_excel(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
            
            # 按深度排序
            depth_cols = ['MD', 'DEPTH', 'Depth', 'depth', 'DEPT']
            depth_col = next((col for col in depth_cols if col in self.data.columns), None)
            if depth_col:
                self.data = self.data.sort_values(depth_col).reset_index(drop=True)
                # 统一深度列名为MD
                if depth_col != 'MD':
                    logger.info(f"将深度列 '{depth_col}' 重命名为 'MD'")
                    self.data = self.data.rename(columns={depth_col: 'MD'})
            else:
                # 如果没有找到深度列，尝试使用第一个列作为深度列
                if len(self.data.columns) > 0:
                    depth_col = self.data.columns[0]
                    logger.warning(f"未找到标准深度列，使用第一列 '{depth_col}' 作为深度列")
                    self.data = self.data.sort_values(depth_col).reset_index(drop=True)
                    self.data = self.data.rename(columns={depth_col: 'MD'})
                else:
                    logger.error("数据文件中没有列")
                    return None
            
            logger.info(f"数据加载成功，共 {len(self.data)} 条记录")
            logger.info(f"处理后的数据列: {list(self.data.columns)}")
            return self.data
        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            return None
    
    def data_quality_check(self):
        """数据质量检查"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        qc_report = {
            'total_records': len(self.data),
            'missing_values': self.data.isnull().sum().to_dict(),
            'outliers': {},
            'data_types': self.data.dtypes.to_dict()
        }
        
        # 去重
        duplicate_rows = self.data.duplicated().sum()
        if duplicate_rows > 0:
            logger.info(f"发现 {duplicate_rows} 条重复记录，已去重")
            self.data = self.data.drop_duplicates().reset_index(drop=True)
            qc_report['duplicates_removed'] = duplicate_rows
        
        # 异常值检测
        numeric_cols = self.data.select_dtypes(include=['float64', 'int64']).columns
        for col in numeric_cols:
            if self.data[col].notnull().any():
                Q1 = self.data[col].quantile(0.25)
                Q3 = self.data[col].quantile(0.75)
                IQR = Q3 - Q1
                outliers = self.data[(self.data[col] < Q1 - 1.5*IQR) | (self.data[col] > Q3 + 1.5*IQR)]
                qc_report['outliers'][col] = len(outliers)
        
        # 数据完整性检查
        required_cols = ['MD']
        missing_cols = [col for col in required_cols if col not in self.data.columns]
        if missing_cols:
            qc_report['missing_required_columns'] = missing_cols
        
        self.results['qc_report'] = qc_report
        logger.info("数据质量检查完成")
        return qc_report
    
    def environmental_correction(self):
        """环境校正，包括井眼校正"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        self.processed_data = self.data.copy()
        
        # 井眼校正
        # 1. 计算井眼体积
        if 'CAL' in self.processed_data.columns and 'BIT_SIZE' in self.processed_data.columns:
            self.processed_data['HOLE_VOLUME'] = np.pi * ((self.processed_data['CAL']/2)**2 - (self.processed_data['BIT_SIZE']/2)**2)
        
        # 2. 井眼校正（示例：密度测井井眼校正）
        if 'RHOB' in self.processed_data.columns and 'CAL' in self.processed_data.columns:
            # 简单的井眼校正公式，实际应用中需要更复杂的模型
            self.processed_data['RHOB_CORRECTED'] = self.processed_data['RHOB'] - 0.1 * (self.processed_data['CAL'] - 8.5)  # 假设钻头尺寸为8.5英寸
        
        # 3. 自然伽马校正
        if 'GR' in self.processed_data.columns:
            # 简单的泥岩基线校正
            gr_min = self.processed_data['GR'].min()
            gr_max = self.processed_data['GR'].max()
            self.processed_data['GR_CORRECTED'] = (self.processed_data['GR'] - gr_min) / (gr_max - gr_min) * 100
        
        logger.info("环境校正完成")
        return self.processed_data
    
    def data_processing(self):
        """资料处理，计算各个参数值"""
        if self.processed_data is None:
            self.processed_data = self.data.copy()
        
        # 计算泥质含量VSH
        if 'GR' in self.processed_data.columns:
            # 基于自然伽马的泥质含量计算
            gr_min = self.processed_data['GR'].min()
            gr_max = self.processed_data['GR'].max()
            self.processed_data['VSH'] = (self.processed_data['GR'] - gr_min) / (gr_max - gr_min)
        
        # 计算孔隙度
        # 1. 密度孔隙度
        if 'RHOB' in self.processed_data.columns:
            # 假设骨架密度为2.65 g/cc，流体密度为1.0 g/cc
            self.processed_data['PHI_D'] = (2.65 - self.processed_data['RHOB']) / (2.65 - 1.0)
        
        # 2. 声波孔隙度
        if 'DT' in self.processed_data.columns:
            # 假设骨架声波时差为47.5 us/ft，流体声波时差为189 us/ft
            self.processed_data['PHI_S'] = (self.processed_data['DT'] - 47.5) / (189 - 47.5)
        
        # 3. 中子孔隙度
        if 'NPHI' in self.processed_data.columns:
            self.processed_data['PHI_N'] = self.processed_data['NPHI']
        
        # 计算含水饱和度Sw
        if 'LLD' in self.processed_data.columns and 'PHI_D' in self.processed_data.columns:
            # 阿尔奇公式：Sw = (a*Rw)/(φ^m*Rt)^(1/n)
            # 假设a=1, m=2, n=2, Rw=0.01
            self.processed_data['Sw'] = (1 * 0.01) / (self.processed_data['PHI_D']**2 * self.processed_data['LLD'])**(1/2)
        
        logger.info("资料处理完成")
        return self.processed_data
    
    def log_interpretation(self):
        """测井解释，根据图版法和相似性原理解释油水层"""
        if self.processed_data is None:
            logger.error("数据未处理")
            return None
        
        # 基于相似性原理的流体类型识别
        # 定义流体类型的特征向量
        fluid_signatures = {
            '油层': {'LLD': 10, 'PHI_D': 0.2, 'Sw': 0.3},
            '气层': {'LLD': 50, 'PHI_D': 0.25, 'Sw': 0.2},
            '水层': {'LLD': 2, 'PHI_D': 0.2, 'Sw': 0.9},
            '干层': {'LLD': 5, 'PHI_D': 0.05, 'Sw': 0.5}
        }
        
        # 计算每个深度点与每种流体类型的欧氏距离
        self.processed_data['INTERPRETATION'] = '干层'  # 默认值
        
        if all(col in self.processed_data.columns for col in ['LLD', 'PHI_D', 'Sw']):
            for idx, row in self.processed_data.iterrows():
                min_distance = float('inf')
                best_match = '干层'
                
                for fluid, signature in fluid_signatures.items():
                    distance = np.sqrt(
                        (row['LLD'] - signature['LLD'])**2 +
                        (row['PHI_D'] - signature['PHI_D'])**2 +
                        (row['Sw'] - signature['Sw'])**2
                    )
                    
                    if distance < min_distance:
                        min_distance = distance
                        best_match = fluid
                
                self.processed_data.at[idx, 'INTERPRETATION'] = best_match
        
        logger.info("测井解释完成")
        return self.processed_data
    
    def visualize_results(self):
        """可视化，根据测井专业惯例绘制测井综合图"""
        if self.processed_data is None:
            logger.error("数据未处理")
            return None
        
        # 创建输出目录
        viz_dir = self.output_dir / 'visualization'
        viz_dir.mkdir(exist_ok=True)
        
        # 绘制测井综合图
        fig, axes = plt.subplots(8, 1, figsize=(12, 20), sharex=False, sharey=True)
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 深度范围
        depth = self.processed_data['MD'].values
        depth_min = depth.min()
        depth_max = depth.max()
        
        # 道头与曲线区高度比例
        header_height_ratio = 0.12  # 道头占12%高度
        curve_height = 1 - header_height_ratio
        
        # 1厘米的比例（用于道头区的刻度位置计算）
        one_cm_ratio = 0.025  # 假设1厘米占图高的2.5%
        
        # 深度刻度（每10米一个大刻度，每1米一个小刻度）
        major_ticks = np.arange(int(depth_min) - (int(depth_min) % 10), int(depth_max) + 10, 10)
        minor_ticks = np.arange(int(depth_min) - (int(depth_min) % 1), int(depth_max) + 1, 1)
        
        # 第1道: GR和SP
        ax1 = axes[0]
        # 显示完整的外框，确保是黑实线
        for spine in ax1.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax1.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax1.set_ylabel('')
        ax1.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax1.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax1.plot([0, 1], [curve_height, curve_height], transform=ax1.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect1 = plt.Rectangle((0, 0), 1, curve_height, transform=ax1.transAxes, 
                                   clip_on=False, fill=False)
        ax1.add_patch(clip_rect1)
        
        # 创建道头区域裁剪路径，限制刻度和标签只在道头区域（y从curve_height到1.0）内显示
        header_clip_rect1 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax1.transAxes, 
                                        clip_on=False, fill=False)
        ax1.add_patch(header_clip_rect1)
        
        # 确保所有边框完整可见
        for spine in ax1.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax1.set_ylabel('')
        ax1.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax1.set_yticks([])
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax1.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect1)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax1.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect1)
        
        # 第一道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax1.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax1.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect1)
        
        # 绘制GR曲线
        if 'GR' in self.processed_data.columns:
            gr_ax = ax1.twiny()
            # 确保使用processed_data
            line, = gr_ax.plot(self.processed_data['GR'], depth, color='green', linewidth=1.5, label='GR')
            # 应用裁剪，使曲线只在曲线区域内显示
            line.set_clip_path(clip_rect1)
            # 确保曲线在最上层显示
            line.set_zorder(2000)
            
            gr_ax.set_ylim(depth_max, depth_min)
            for spine_name, spine in gr_ax.spines.items():
                if spine_name != 'top':
                    spine.set_visible(False)
                else:
                    # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                    # 道头区域高度为4厘米，从curve_height开始到1.0
                    # GR曲线刻度放在道头区顶部下方1.5厘米处，避免与道名重叠
                    cm_to_axes = one_cm_ratio
                    spine.set_position(('axes', 1.0 - 1.5 * cm_to_axes))
                    spine.set_visible(True)
            # 调整刻度位置，确保与道的左右边一致，只标首尾数字
            gr_ax.tick_params(axis='x', top=True, bottom=False, labeltop=True, labelbottom=False, 
                             length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
            # 只设置首尾刻度，不显示中间刻度
            gr_ax.set_xticks([0, 200])
            gr_ax.set_xlim(0, 200)
            gr_ax.spines['top'].set_visible(True)
            gr_ax.tick_params(axis='x', colors='green')
            gr_ax.spines['top'].set_color('green')
            # 减小标签字体大小，确保不超出道头区
            gr_ax.set_xlabel('GR (API)', fontsize=12, color='green', labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
            # 应用裁剪，使刻度和标签只在道头区域内显示
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
            # 确保gr_ax的z-order低于曲线，这样曲线可以显示在上面
            gr_ax.set_zorder(2)
        
        # 绘制SP曲线
        if 'SP' in self.processed_data.columns:
            sp_ax = ax1.twiny()
            # 确保使用processed_data
            line, = sp_ax.plot(self.processed_data['SP'], depth, color='blue', linewidth=1.5, label='SP')
            # 应用裁剪，使曲线只在曲线区域内显示
            line.set_clip_path(clip_rect1)
            # 确保曲线在最上层显示
            line.set_zorder(2000)
            
            sp_ax.set_ylim(depth_max, depth_min)
            for spine_name, spine in sp_ax.spines.items():
                if spine_name != 'top':
                    spine.set_visible(False)
                else:
                    # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                    # 道头区域高度为4厘米，从curve_height开始到1.0
                    # SP曲线刻度放在GR曲线下方1厘米处
                    cm_to_axes = one_cm_ratio
                    spine.set_position(('axes', 1.0 - 2.5 * cm_to_axes))
                    spine.set_visible(True)
            # 调整刻度位置，确保与道的左右边一致，只标首尾数字
            sp_ax.tick_params(axis='x', top=True, bottom=False, labeltop=True, labelbottom=False, 
                             length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
            # 只设置首尾刻度，不显示中间刻度
            sp_ax.set_xticks([-100, 100])
            # 设置SP刻度为-100到100
            sp_ax.set_xlim(-100, 100)
            sp_ax.spines['top'].set_visible(True)
            sp_ax.tick_params(axis='x', colors='blue')
            sp_ax.spines['top'].set_color('blue')
            # 减小标签字体大小，确保不超出道头区
            sp_ax.set_xlabel('SP (mV)', fontsize=12, color='blue', labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
            # 应用裁剪，使刻度和标签只在道头区域内显示
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
            # 确保sp_ax的z-order低于曲线，这样曲线可以显示在上面
            sp_ax.set_zorder(3)
        
        # 绘制CAL曲线
        cal_column = None
        if 'CALS' in self.processed_data.columns:
            cal_column = 'CALS'
        elif 'CALI' in self.processed_data.columns:
            cal_column = 'CALI'
        elif 'CAL' in self.processed_data.columns:
            cal_column = 'CAL'
        
        if cal_column:
            cal_ax = ax1.twiny()
            # 确保使用processed_data
            line, = cal_ax.plot(self.processed_data[cal_column], depth, color='red', linewidth=1.5, label='CAL')
            # 应用裁剪，使曲线只在曲线区域内显示
            line.set_clip_path(clip_rect1)
            # 确保曲线在最上层显示
            line.set_zorder(2000)
            
            cal_ax.set_ylim(depth_max, depth_min)
            for spine_name, spine in cal_ax.spines.items():
                if spine_name != 'top':
                    spine.set_visible(False)
                else:
                    # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                    # 道头区域高度为4厘米，从curve_height开始到1.0
                    # CAL曲线刻度放在SP曲线下方1厘米处
                    cm_to_axes = one_cm_ratio
                    spine.set_position(('axes', 1.0 - 3.5 * cm_to_axes))
                    spine.set_visible(True)
            # 调整刻度位置，确保与道的左右边一致，只标首尾数字
            cal_ax.tick_params(axis='x', top=True, bottom=False, labeltop=True, labelbottom=False, 
                             length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
            # 只设置首尾刻度，不显示中间刻度
            cal_ax.set_xticks([6, 12])
            cal_ax.set_xlim(6, 12)
            cal_ax.spines['top'].set_visible(True)
            cal_ax.tick_params(axis='x', colors='red')
            cal_ax.spines['top'].set_color('red')
            # 减小标签字体大小，确保不超出道头区
            cal_ax.set_xlabel('CAL (in)', fontsize=12, color='red', labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
            # 应用裁剪，使刻度和标签只在道头区域内显示
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
            # 确保cal_ax的z-order低于曲线，这样曲线可以显示在上面
            cal_ax.set_zorder(4)
        
        # 确保Lithology曲线在最上层显示
        ax1.set_zorder(1)  # 确保ax1的zorder低于曲线，这样曲线可以显示在上面
        
        # 确保曲线的z-order高于其他元素
        if 'GR' in self.processed_data.columns:
            for line in gr_ax.lines:
                line.set_zorder(1000)
            gr_ax.set_zorder(2)
        if 'SP' in self.processed_data.columns:
            for line in sp_ax.lines:
                line.set_zorder(1000)
            sp_ax.set_zorder(3)
        if cal_column:
            for line in cal_ax.lines:
                line.set_zorder(1000)
            cal_ax.set_zorder(4)
        
        # 确保ax1的边框在曲线下方
        for spine in ax1.spines.values():
            spine.set_zorder(0)
        
        # 第2道: 电阻率
        ax2 = axes[1]
        # 显示完整的外框，确保是黑实线
        for spine in ax2.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax2.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax2.set_ylabel('')
        ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax2.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax2.plot([0, 1], [curve_height, curve_height], transform=ax2.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect2 = plt.Rectangle((0, 0), 1, curve_height, transform=ax2.transAxes, 
                                   clip_on=False, fill=False)
        ax2.add_patch(clip_rect2)
        
        # 创建道头区域裁剪路径，限制刻度和标签只在道头区域（y从curve_height到1.0）内显示
        header_clip_rect2 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax2.transAxes, 
                                        clip_on=False, fill=False)
        ax2.add_patch(header_clip_rect2)
        
        # 确保所有边框完整可见
        for spine in ax2.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax2.set_ylabel('')
        ax2.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax2.set_yticks([])
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax2.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect2)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax2.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect2)
        
        # 电阻率道曲线区分成按0.2-2，2-200，200-2000分成4格
        # 绘制电阻率曲线
        resistivity_cols = ['LLD', 'LLS', 'MSFL']
        res_colors = ['black', 'red', 'green']
        # 每个刻度长度1厘米
        res_positions = [0, 1, 2]  # 用于循环索引
        for i, col in enumerate(resistivity_cols):
            if col in self.processed_data.columns:
                res_ax = ax2.twiny()
                line, = res_ax.semilogx(self.processed_data[col], depth, color=res_colors[i], linewidth=1.5, label=col)
                # 应用裁剪，使曲线只在曲线区域内显示
                line.set_clip_path(clip_rect2)
                line.set_zorder(2000)
                
                res_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in res_ax.spines.items():
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                        # 道头区域高度为4厘米，从curve_height开始到1.0
                        # 电阻率曲线刻度依次放在道头区内，每1厘米一个
                        cm_to_axes = one_cm_ratio
                        spine.set_position(('axes', 1.0 - (1.5 + (i % len(res_positions))) * cm_to_axes))
                        spine.set_visible(True)
                # 调整刻度和标签设置，确保与道的左右边一致，只标首尾数字
                res_ax.tick_params(axis='x', top=False, bottom=False, labeltop=True, labelbottom=False, 
                                 length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
                # 只设置首尾刻度，不显示中间刻度
                res_ax.set_xticks([0.2, 2000])
                res_ax.set_xlim(0.2, 2000)
                res_ax.spines['top'].set_visible(True)
                res_ax.tick_params(axis='x', colors=res_colors[i])
                res_ax.spines['top'].set_color(res_colors[i])
                # 减小标签字体大小和边距，确保不超出道头区
                res_ax.set_xlabel(f'{col} (ohm-m)', fontsize=12, color=res_colors[i], labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
                # 应用裁剪，使刻度和标签只在道头区域内显示
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
        
        # 电阻率道曲线区分成按0.2-2，2-200，200-2000分成4格
        # 第一格绘制0.3，0.4，0.5，0.6，0.7，0.8，0.9，1，2
        first_grid_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 2]
        for val in first_grid_values:
            # 将对数坐标转换为线性坐标
            x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
            line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect2)
        
        # 第二格绘制，3，4，5，6，7，8，9，10，20竖线
        second_grid_values = [3, 4, 5, 6, 7, 8, 9, 10, 20]
        for val in second_grid_values:
            x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
            line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect2)
        
        # 第三格绘制21，22，23，24，25，26，27，28，29，30，40，50，60，70，80，90，100，200竖线
        third_grid_values = [21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 40, 50, 60, 70, 80, 90, 100, 200]
        for val in third_grid_values:
            x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
            line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect2)
        
        # 第四格绘制201，202，203，204，205，206，207，208，209，210，220，230，240，250，260，270，280，290，300，400，500，600，700，800，900，1000，2000竖线
        fourth_grid_values = [201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 400, 500, 600, 700, 800, 900, 1000, 2000]
        for val in fourth_grid_values:
            x = (np.log10(val) - np.log10(0.2)) / (np.log10(2000) - np.log10(0.2))
            line = ax2.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect2)
        
        # 第3道: 孔隙度
        ax3 = axes[2]
        # 显示完整的外框，确保是黑实线
        for spine in ax3.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax3.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax3.set_ylabel('')
        ax3.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax3.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax3.plot([0, 1], [curve_height, curve_height], transform=ax3.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect3 = plt.Rectangle((0, 0), 1, curve_height, transform=ax3.transAxes, 
                                   clip_on=False, fill=False)
        ax3.add_patch(clip_rect3)
        
        # 创建道头区域裁剪路径，限制刻度和标签只在道头区域（y从curve_height到1.0）内显示
        header_clip_rect3 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax3.transAxes, 
                                        clip_on=False, fill=False)
        ax3.add_patch(header_clip_rect3)
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax3.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect3)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax3.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect3)
        
        # 第三道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax3.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax3.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect3)
        
        # 绘制孔隙度曲线
        porosity_cols = ['RHOB', 'NPHI', 'DT']
        por_colors = ['blue', 'green', 'red']
        por_labels = ['RHOB', 'NPHI', 'DT']
        por_limits = [(1.9, 2.9), (-0.1, 0.6), (40, 120)]
        
        for i, (col, color, label, limits) in enumerate(zip(porosity_cols, por_colors, por_labels, por_limits)):
            if col in self.processed_data.columns:
                por_ax = ax3.twiny()
                line, = por_ax.plot(self.processed_data[col], depth, color=color, linewidth=1.5, label=label)
                # 应用裁剪，使曲线只在曲线区域内显示
                line.set_clip_path(clip_rect3)
                line.set_zorder(2000)
                
                por_ax.set_ylim(depth_max, depth_min)
                for spine_name, spine in por_ax.spines.items():
                    if spine_name != 'top':
                        spine.set_visible(False)
                    else:
                        # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                        # 道头区域高度为4厘米，从curve_height开始到1.0
                        # 孔隙度曲线刻度依次放在道头区内，每1厘米一个
                        cm_to_axes = one_cm_ratio
                        spine.set_position(('axes', 1.0 - (1.5 + i) * cm_to_axes))
                        spine.set_visible(True)
                # 调整刻度位置，确保与道的左右边一致，只标首尾数字
                por_ax.tick_params(axis='x', top=True, bottom=False, labeltop=True, labelbottom=False, 
                                 length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
                # 只设置首尾刻度，不显示中间刻度
                por_ax.set_xticks([limits[0], limits[1]])
                por_ax.set_xlim(limits[0], limits[1])
                por_ax.spines['top'].set_visible(True)
                por_ax.tick_params(axis='x', colors=color)
                por_ax.spines['top'].set_color(color)
                # 减小标签字体大小，确保不超出道头区
                por_ax.set_xlabel(f'{label}', fontsize=12, color=color, labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
                # 应用裁剪，使刻度和标签只在道头区域内显示
                for tick in por_ax.xaxis.get_major_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                for tick in por_ax.xaxis.get_minor_ticks():
                    tick.label1.set_clip_path(header_clip_rect3)
                    tick.label2.set_clip_path(header_clip_rect3)
                    tick.label1.set_zorder(1000)
                    tick.label2.set_zorder(1000)
                por_ax.spines['top'].set_clip_path(header_clip_rect3)
                por_ax.spines['top'].set_zorder(1000)
                por_ax.xaxis.set_clip_path(header_clip_rect3)
                por_ax.xaxis.set_zorder(1000)
                por_ax.set_zorder(i+2)
        
        # 第4道: 深度道
        ax4 = axes[3]
        # 显示完整的外框，确保是黑实线
        for spine in ax4.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax4.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 设置深度轴范围
        ax4.set_ylim(depth_max, depth_min)
        
        # 绘制深度刻度（使用微软雅黑字体）
        ax4.set_yticks(major_ticks)
        ax4.set_yticklabels([f'{int(tick)}' for tick in major_ticks], fontsize=8, fontfamily='Microsoft YaHei')
        ax4.tick_params(axis='y', left=True, right=True, labelsize=8, labelfontfamily='Microsoft YaHei')
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            ax4.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                ax4.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
        
        # 第5道: 含水饱和度
        ax5 = axes[4]
        # 显示完整的外框，确保是黑实线
        for spine in ax5.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax5.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax5.set_ylabel('')
        ax5.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax5.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax5.plot([0, 1], [curve_height, curve_height], transform=ax5.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect5 = plt.Rectangle((0, 0), 1, curve_height, transform=ax5.transAxes, 
                                   clip_on=False, fill=False)
        ax5.add_patch(clip_rect5)
        
        # 创建道头区域裁剪路径，限制刻度和标签只在道头区域（y从curve_height到1.0）内显示
        header_clip_rect5 = plt.Rectangle((0, curve_height), 1, 1 - curve_height, transform=ax5.transAxes, 
                                        clip_on=False, fill=False)
        ax5.add_patch(header_clip_rect5)
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax5.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect5)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax5.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect5)
        
        # 第五道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax5.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax5.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect5)
        
        # 绘制含水饱和度曲线
        if 'Sw' in self.processed_data.columns:
            sw_ax = ax5.twiny()
            line, = sw_ax.plot(self.processed_data['Sw'], depth, color='blue', linewidth=1.5, label='Sw')
            # 应用裁剪，使曲线只在曲线区域内显示
            line.set_clip_path(clip_rect5)
            line.set_zorder(2000)
            
            sw_ax.set_ylim(depth_max, depth_min)
            for spine_name, spine in sw_ax.spines.items():
                if spine_name != 'top':
                    spine.set_visible(False)
                else:
                    # 调整顶部边框的位置，确保在道头区域内（使用绝对值计算）
                    # 道头区域高度为4厘米，从curve_height开始到1.0
                    # Sw曲线刻度放在道头区顶部下方1.5厘米处
                    cm_to_axes = one_cm_ratio
                    spine.set_position(('axes', 1.0 - 1.5 * cm_to_axes))
                    spine.set_visible(True)
            # 调整刻度位置，确保与道的左右边一致，只标首尾数字
            sw_ax.tick_params(axis='x', top=True, bottom=False, labeltop=True, labelbottom=False, 
                             length=0, direction='in', labelsize=8, pad=2, labelfontfamily='Microsoft YaHei')  # 使用微软雅黑8号字，隐藏刻度线
            # 只设置首尾刻度，不显示中间刻度
            sw_ax.set_xticks([0, 1])
            sw_ax.set_xlim(0, 1)
            sw_ax.spines['top'].set_visible(True)
            sw_ax.tick_params(axis='x', colors='blue')
            sw_ax.spines['top'].set_color('blue')
            # 减小标签字体大小，确保不超出道头区
            sw_ax.set_xlabel('Sw', fontsize=12, color='blue', labelpad=1, fontfamily='Microsoft YaHei')  # 使用微软雅黑12号字
            # 应用裁剪，使刻度和标签只在道头区域内显示
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
        
        # 第6道: 岩性
        ax6 = axes[5]
        # 显示完整的外框，确保是黑实线
        for spine in ax6.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax6.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax6.set_ylabel('')
        ax6.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax6.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax6.plot([0, 1], [curve_height, curve_height], transform=ax6.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect6 = plt.Rectangle((0, 0), 1, curve_height, transform=ax6.transAxes, 
                                   clip_on=False, fill=False)
        ax6.add_patch(clip_rect6)
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax6.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect6)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax6.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect6)
        
        # 第六道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax6.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax6.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect6)
        
        # 绘制岩性柱状图
        # 假设我们有岩性数据
        if 'LITHOLOGY' in self.processed_data.columns:
            lithology_map = {
                '砂岩': 'yellow',
                '泥岩': 'brown',
                '碳酸盐岩': 'gray',
                '混合岩': 'lightgray'
            }
            
            for i in range(len(self.processed_data) - 1):
                md1 = self.processed_data.iloc[i]['MD']
                md2 = self.processed_data.iloc[i+1]['MD']
                lithology = self.processed_data.iloc[i]['LITHOLOGY']
                color = lithology_map.get(lithology, 'white')
                ax6.fill_betweenx([md1, md2], 0, 1, color=color, alpha=0.8)
        
        # 第7道: 沉积相
        ax7 = axes[6]
        # 显示完整的外框，确保是黑实线
        for spine in ax7.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax7.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax7.set_ylabel('')
        ax7.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax7.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax7.plot([0, 1], [curve_height, curve_height], transform=ax7.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect7 = plt.Rectangle((0, 0), 1, curve_height, transform=ax7.transAxes, 
                                   clip_on=False, fill=False)
        ax7.add_patch(clip_rect7)
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax7.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect7)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax7.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect7)
        
        # 第七道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax7.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax7.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect7)
        
        # 绘制沉积相柱状图
        # 假设我们有沉积相数据
        if 'FACIES' in self.processed_data.columns:
            facies_map = {
                '分流河道': 'red',
                '河口坝': 'orange',
                '远砂坝': 'yellow',
                '席状砂': 'lightyellow',
                '泛滥平原': 'green',
                '其他': 'white'
            }
            
            for i in range(len(self.processed_data) - 1):
                md1 = self.processed_data.iloc[i]['MD']
                md2 = self.processed_data.iloc[i+1]['MD']
                facies = self.processed_data.iloc[i]['FACIES']
                color = facies_map.get(facies, 'white')
                ax7.fill_betweenx([md1, md2], 0, 1, color=color, alpha=0.8)
        
        # 第8道: 测井解释
        ax8 = axes[7]
        # 显示完整的外框，确保是黑实线
        for spine in ax8.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)
        
        # 隐藏主x轴刻度
        ax8.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        
        # 隐藏深度轴刻度和标签，只在深度道显示
        ax8.set_ylabel('')
        ax8.tick_params(axis='y', which='both', left=False, right=False, labelsize=0, labelfontfamily='Microsoft YaHei')
        ax8.set_yticks([])
        
        # 绘制道头与曲线区域的分隔线（使用相对坐标系）
        ax8.plot([0, 1], [curve_height, curve_height], transform=ax8.transAxes, color='black', linewidth=1)
        
        # 创建裁剪区域，限制曲线只在曲线区域（y从0到curve_height）内显示
        clip_rect8 = plt.Rectangle((0, 0), 1, curve_height, transform=ax8.transAxes, 
                                   clip_on=False, fill=False)
        ax8.add_patch(clip_rect8)
        
        # 绘制深度横线 - 每10米一条深线，每米一条浅线
        for depth_val in major_ticks:
            line = ax8.axhline(y=depth_val, color='black', linewidth=1.5, zorder=500)
            line.set_clip_path(clip_rect8)
        for depth_val in minor_ticks:
            if depth_val not in major_ticks:
                line = ax8.axhline(y=depth_val, color='black', linewidth=0.5, zorder=500)
                line.set_clip_path(clip_rect8)
        
        # 第八道曲线部分十等分，绘制9条垂直的10等分竖线（只在曲线区显示）
        for i in range(1, 10):
            x = i / 10.0
            if i == 5:
                # 第五条竖线为微软雅黑10号
                line = ax8.axvline(x=x, color='black', linewidth=1.0, zorder=500)
            else:
                # 其他竖线为微软雅黑8号
                line = ax8.axvline(x=x, color='black', linewidth=0.5, zorder=500)
            line.set_clip_path(clip_rect8)
        
        # 绘制测井解释结论柱状图
        if 'INTERPRETATION' in self.processed_data.columns:
            interpretation_map = {
                '油层': 'green',
                '气层': 'yellow',
                '水层': 'orange',
                '干层': 'red',
                '可疑层': 'white'
            }
            
            for i in range(len(self.processed_data) - 1):
                md1 = self.processed_data.iloc[i]['MD']
                md2 = self.processed_data.iloc[i+1]['MD']
                interpretation = self.processed_data.iloc[i]['INTERPRETATION']
                color = interpretation_map.get(interpretation, 'white')
                ax8.fill_betweenx([md1, md2], 0, 1, color=color, alpha=0.8)
        
        # 调整所有子图的布局
        plt.tight_layout()
        
        # 保存测井综合图
        output_path = viz_dir / 'log_composite.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"可视化完成，保存至: {output_path}")
        return str(output_path)
    
    def run_workflow(self):
        """运行完整工作流"""
        logger.info("开始测录井资料处理工作流")
        
        try:
            # 1. 数据加载
            logger.info("Step 1: 数据加载")
            if self.data is None:
                logger.error("数据未加载")
                return None
            
            # 2. 数据质量检查
            if self.config.get('quality_check', True):
                logger.info("Step 2: 数据质量检查")
                self.data_quality_check()
            
            # 3. 环境校正
            if self.config.get('environmental_correction', True):
                logger.info("Step 3: 环境校正")
                self.environmental_correction()
            
            # 4. 资料处理
            if self.config.get('data_processing', True):
                logger.info("Step 4: 资料处理")
                self.data_processing()
            
            # 5. 测井解释
            if self.config.get('interpretation', True):
                logger.info("Step 5: 测井解释")
                self.log_interpretation()
            
            # 6. 结果可视化
            if self.config.get('visualization', True):
                logger.info("Step 6: 结果可视化")
                self.visualize_results()
            
            # 7. 生成报告
            if self.config.get('report_generation', True):
                logger.info("Step 7: 生成报告")
                self.generate_report()
            
            logger.info("测录井资料处理工作流完成")
            return self.results
            
        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            return None
    
    def generate_report(self):
        """生成测井解释报告"""
        if self.processed_data is None:
            logger.error("数据未处理")
            return None
        
        # 创建输出目录
        report_dir = self.output_dir / 'reports'
        report_dir.mkdir(exist_ok=True)
        
        # 生成HTML报告
        report_path = report_dir / 'interpretation_report.html'
        
        # 报告内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>测录井资料解释报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .summary {{ background-color: #f5f5f5; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .success {{ color: green; }}
                .warning {{ color: orange; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1>测录井资料解释报告</h1>
            
            <div class="section summary">
                <h2>摘要</h2>
                <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>数据记录数: {len(self.processed_data)}</p>
                <p>处理流程: 数据加载 → 质量检查 → 环境校正 → 资料处理 → 测井解释 → 可视化 → 报告生成</p>
            </div>
            
            <div class="section">
                <h2>数据质量检查</h2>
                <table>
                    <tr>
                        <th>检查项</th>
                        <th>结果</th>
                    </tr>
                    <tr>
                        <td>总记录数</td>
                        <td>{len(self.processed_data)}</td>
                    </tr>
                    <tr>
                        <td>缺失值</td>
                        <td>已处理</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h2>处理结果</h2>
                <p>计算的曲线列表: GR, SP, CAL, LLD, LLS, MSFL, RHOB, NPHI, DT, Sw</p>
            </div>
            
            <div class="section">
                <h2>可视化结果</h2>
                <p>测井综合图已生成: <a href="../visualization/logging_composite.png">查看测井综合图</a></p>
            </div>
        </body>
        </html>
        """
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"报告生成完成，保存至: {report_path}")
        return str(report_path)