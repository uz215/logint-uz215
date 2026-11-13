# =============================================================================
# 可视化模块
# =============================================================================
# 支持单独运行：python visualizer.py <file_path>
# 包含：综合测井图、交会图、油气层图版、解释图版
# =============================================================================

import os
import sys
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('visualizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['font.family'] = ['sans-serif']
plt.rcParams['axes.unicode_minus'] = False


class WellLogVisualizer:
    """测井可视化类"""
    
    def __init__(self):
        """初始化可视化器"""
        self.data = None
        self.results = None
    
    def set_data(self, data, results=None):
        """设置数据"""
        self.data = data.copy()
        self.results = results
        return self
    
    def visualize_single_curve(self, curve_name, depth_col='MD', title=None):
        """绘制单条测井曲线"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        if curve_name not in self.data.columns:
            logger.error(f"曲线 {curve_name} 不存在")
            return None
        
        fig, ax = plt.subplots(figsize=(8, 12))
        ax.plot(self.data[curve_name], self.data[depth_col], color='blue', linewidth=1.5)
        
        ax.set_ylim(self.data[depth_col].max(), self.data[depth_col].min())
        ax.set_xlabel(curve_name)
        ax.set_ylabel('深度 (m)')
        ax.set_title(title or f'{curve_name} 测井曲线')
        ax.grid(True, linestyle='--', alpha=0.7)
        
        return fig
    
    def visualize_crossplot(self, x_col, y_col, color_col=None, title=None):
        """绘制交会图"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        if x_col not in self.data.columns or y_col not in self.data.columns:
            logger.error("指定的列不存在")
            return None
        
        fig, ax = plt.subplots(figsize=(8, 8))
        
        if color_col and color_col in self.data.columns:
            scatter = ax.scatter(self.data[x_col], self.data[y_col], 
                               c=self.data[color_col], cmap='viridis', alpha=0.7)
            plt.colorbar(scatter, label=color_col)
        else:
            ax.scatter(self.data[x_col], self.data[y_col], color='blue', alpha=0.7)
        
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(title or f'{x_col} vs {y_col} 交会图')
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.set_aspect('equal')
        
        return fig
    
    def visualize_porosity_resistivity_crossplot(self):
        """绘制孔隙度-电阻率交会图（用于流体识别）"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        if 'PHI' not in self.data.columns or 'RT' not in self.data.columns:
            logger.error("缺少PHI或RT列")
            return None
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # 绘制数据点
        scatter = ax.scatter(self.data['PHI'], self.data['RT'], 
                           c=self.data.get('Sw', np.zeros(len(self.data))), 
                           cmap='coolwarm', alpha=0.7)
        
        # 添加Archie趋势线
        phi_vals = np.linspace(0.05, 0.4, 100)
        Rw = 0.05
        a, m, n = 1.0, 2.0, 2.0
        
        for sw in [0.2, 0.4, 0.6, 0.8, 1.0]:
            rt_vals = a * Rw / (sw ** n * phi_vals ** m)
            ax.plot(phi_vals, rt_vals, '--', label=f'Sw={sw}', alpha=0.7)
        
        ax.set_xlabel('孔隙度 (PHI)')
        ax.set_ylabel('电阻率 (RT, ohm.m)')
        ax.set_title('孔隙度-电阻率交会图（Archie图版）')
        ax.set_yscale('log')
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()
        plt.colorbar(scatter, label='含水饱和度 (Sw)')
        
        return fig
    
    def visualize_hydrocarbon_plot(self):
        """绘制油气层识别图版"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # 左侧：Sw-PHI交会图
        if 'Sw' in self.data.columns and 'PHI' in self.data.columns:
            scatter1 = ax1.scatter(self.data['PHI'], self.data['Sw'], 
                                  c=self.data.get('RT', np.zeros(len(self.data))),
                                  cmap='viridis', alpha=0.7)
            ax1.set_xlabel('孔隙度 (PHI)')
            ax1.set_ylabel('含水饱和度 (Sw)')
            ax1.set_title('Sw-PHI 油气层识别图版')
            ax1.grid(True, linestyle='--', alpha=0.7)
            plt.colorbar(scatter1, ax=ax1, label='电阻率 (RT)')
            
            # 添加油气层区域标记
            ax1.axhline(y=0.4, color='red', linestyle='--', label='油层下限')
            ax1.axhline(y=0.7, color='blue', linestyle='--', label='水层上限')
            ax1.axvline(x=0.15, color='green', linestyle='--', label='有效孔隙度下限')
            ax1.legend()
        
        # 右侧：RT-PHI交会图（油气识别）
        if 'RT' in self.data.columns and 'PHI' in self.data.columns:
            scatter2 = ax2.scatter(self.data['PHI'], self.data['RT'],
                                  c=self.data.get('Sw', np.zeros(len(self.data))),
                                  cmap='coolwarm', alpha=0.7)
            ax2.set_xlabel('孔隙度 (PHI)')
            ax2.set_ylabel('电阻率 (RT, ohm.m)')
            ax2.set_title('RT-PHI 油气层识别图版')
            ax2.set_yscale('log')
            ax2.grid(True, linestyle='--', alpha=0.7)
            plt.colorbar(scatter2, ax=ax2, label='含水饱和度 (Sw)')
            
            # 添加Archie趋势线
            phi_vals = np.linspace(0.05, 0.4, 100)
            Rw = 0.05
            for sw in [0.2, 0.5, 0.8]:
                rt_vals = Rw / (sw ** 2 * phi_vals ** 2)
                ax2.plot(phi_vals, rt_vals, '--', label=f'Sw={sw}', alpha=0.5)
            ax2.legend()
        
        plt.tight_layout()
        return fig
    
    def visualize_interpretation_chart(self):
        """绘制解释成果图版"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
        # 岩性分布饼图
        if 'LITHOLOGY' in self.data.columns:
            lith_counts = self.data['LITHOLOGY'].value_counts()
            axes[0].pie(lith_counts.values, labels=lith_counts.index, autopct='%1.1f%%', startangle=90)
            axes[0].set_title('岩性分布')
        
        # 油气层分布柱状图
        if 'HYDROCARBON' in self.data.columns:
            hc_counts = self.data['HYDROCARBON'].value_counts()
            axes[1].bar(hc_counts.index, hc_counts.values, color=['green', 'blue', 'red', 'gray', 'yellow'])
            axes[1].set_title('油气层分布')
            axes[1].tick_params(axis='x', rotation=45)
        
        # 储层参数分布箱线图
        params = []
        labels = []
        if 'PHI' in self.data.columns:
            params.append(self.data['PHI'])
            labels.append('孔隙度')
        if 'Sw' in self.data.columns:
            params.append(self.data['Sw'])
            labels.append('含水饱和度')
        if 'K' in self.data.columns:
            params.append(np.log10(self.data['K']))
            labels.append('log(渗透率)')
        
        if params:
            axes[2].boxplot(params, labels=labels)
            axes[2].set_title('储层参数分布')
        
        plt.tight_layout()
        return fig
    
    def visualize_composite_log(self, title='测井综合图'):
        """绘制8道综合测井曲线"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        fig = plt.figure(figsize=(24, 15))
        
        # 创建8道布局
        import matplotlib.gridspec as gridspec
        gs = gridspec.GridSpec(1, 8, width_ratios=[1, 1, 1, 0.5, 1, 1, 1, 1], wspace=0)
        axes = [fig.add_subplot(gs[i]) for i in range(8)]
        
        depth = self.data['MD']
        depth_max = depth.max()
        depth_min = depth.min()
        
        # 第1道：GR/SP/CAL
        ax1 = axes[0]
        ax1.set_ylim(depth_max, depth_min)
        
        if 'GR' in self.data.columns:
            ax1.plot(self.data['GR'], depth, color='green', linewidth=1.5, label='GR')
            ax1.set_xlabel('GR')
        
        if 'SP' in self.data.columns:
            sp_ax = ax1.twiny()
            sp_ax.plot(self.data['SP'], depth, color='blue', linewidth=1.5, label='SP')
            sp_ax.set_xlabel('SP')
            sp_ax.set_ylim(depth_max, depth_min)
        
        ax1.set_title('GR/SP')
        
        # 第2道：电阻率曲线
        ax2 = axes[1]
        ax2.set_ylim(depth_max, depth_min)
        
        if 'LLD' in self.data.columns:
            ax2.semilogx(self.data['LLD'], depth, color='red', linewidth=1.5, label='LLD')
        elif 'RT' in self.data.columns:
            ax2.semilogx(self.data['RT'], depth, color='red', linewidth=1.5, label='RT')
        
        ax2.set_xlabel('Resistivity')
        ax2.set_title('Resistivity')
        
        # 第3道：孔隙度曲线
        ax3 = axes[2]
        ax3.set_ylim(depth_max, depth_min)
        
        if 'RHOB' in self.data.columns:
            ax3.plot(self.data['RHOB'], depth, color='blue', linewidth=1.5, label='RHOB')
            ax3.set_xlabel('RHOB')
        
        if 'NPHI' in self.data.columns:
            np_ax = ax3.twiny()
            np_ax.plot(self.data['NPHI'], depth, color='green', linewidth=1.5, label='NPHI')
            np_ax.set_xlabel('NPHI')
            np_ax.set_ylim(depth_max, depth_min)
        
        ax3.set_title('Porosity')
        
        # 第4道：深度
        ax4 = axes[3]
        ax4.set_ylim(depth_max, depth_min)
        ax4.set_xlabel('Depth')
        ax4.set_title('Depth')
        
        # 添加深度标签
        major_ticks = np.arange(int(depth_min), int(depth_max)+1, 10)
        for d in major_ticks:
            if depth_min <= d <= depth_max:
                ax4.text(0.5, d, str(d), ha='center', va='center', fontsize=10)
        
        # 第5道：含水饱和度
        ax5 = axes[4]
        ax5.set_ylim(depth_max, depth_min)
        
        if 'Sw' in self.data.columns:
            ax5.plot(self.data['Sw'], depth, color='blue', linewidth=1.5, label='Sw')
            ax5.fill_betweenx(depth, self.data['Sw'], 0, alpha=0.3, color='blue')
        
        ax5.set_xlabel('Sw')
        ax5.set_title('Water Saturation')
        
        # 第6道：岩性
        ax6 = axes[5]
        ax6.set_ylim(depth_max, depth_min)
        ax6.set_title('Lithology')
        
        if 'LITHOLOGY' in self.data.columns:
            # 简单的岩性颜色映射
            lith_colors = {'砂岩': '#F5DEB3', '泥岩': '#8B4513', '碳酸盐岩': '#FFE4B5', '泥质砂岩': '#DEB887'}
            for i in range(len(depth)-1):
                lith = self.data['LITHOLOGY'].iloc[i]
                color = lith_colors.get(lith, '#D3D3D3')
                ax6.fill_between([0, 1], depth.iloc[i], depth.iloc[i+1], color=color)
        
        # 第7道：油气层
        ax7 = axes[6]
        ax7.set_ylim(depth_max, depth_min)
        ax7.set_title('Hydrocarbon')
        
        if 'HYDROCARBON' in self.data.columns:
            hc_colors = {'油层': '#FF4500', '气层': '#00CED1', '水层': '#4169E1', '干层': '#808080', '过渡带': '#FFD700'}
            for i in range(len(depth)-1):
                hc = self.data['HYDROCARBON'].iloc[i]
                color = hc_colors.get(hc, '#D3D3D3')
                ax7.fill_between([0, 1], depth.iloc[i], depth.iloc[i+1], color=color)
        
        # 第8道：渗透率
        ax8 = axes[7]
        ax8.set_ylim(depth_max, depth_min)
        
        if 'K' in self.data.columns:
            ax8.semilogx(self.data['K'], depth, color='green', linewidth=1.5, label='K')
        
        ax8.set_xlabel('Permeability')
        ax8.set_title('Permeability')
        
        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        return fig
    
    def save_figure(self, fig, filename, output_dir='output'):
        """保存图形"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)
        
        full_path = output_path / filename
        fig.savefig(full_path, dpi=150, bbox_inches='tight')
        logger.info(f"图形已保存: {full_path}")
        return full_path
    
    def show_plot(self, fig):
        """显示图形"""
        plt.show()


def main():
    """模块独立运行入口"""
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        print("请提供数据文件路径作为参数")
        print("用法: python visualizer.py <file_path>")
        sys.exit(1)
    
    # 尝试导入数据加载模块
    try:
        from data_loader import DataLoader
        from log_interpreter import LogInterpreter
        
        loader = DataLoader()
        data = loader.load_data(file_path)
        
        if data is not None:
            # 运行解释
            interpreter = LogInterpreter()
            interpreter.run_full_interpretation(data)
            data = interpreter.data
    except ImportError:
        logger.warning("无法导入其他模块，直接读取CSV")
        data = pd.read_csv(file_path)
    
    if data is not None:
        visualizer = WellLogVisualizer()
        visualizer.set_data(data)
        
        print("请选择要生成的图版:")
        print("1. 综合测井图")
        print("2. 孔隙度-电阻率交会图")
        print("3. 油气层识别图版")
        print("4. 解释成果图版")
        print("5. 全部生成")
        
        choice = input("请输入选择 (1-5): ")
        
        output_dir = 'visualization_output'
        
        if choice == '1' or choice == '5':
            fig = visualizer.visualize_composite_log()
            visualizer.save_figure(fig, 'composite_log.png', output_dir)
        
        if choice == '2' or choice == '5':
            fig = visualizer.visualize_porosity_resistivity_crossplot()
            visualizer.save_figure(fig, 'crossplot_phi_rt.png', output_dir)
        
        if choice == '3' or choice == '5':
            fig = visualizer.visualize_hydrocarbon_plot()
            visualizer.save_figure(fig, 'hydrocarbon_plot.png', output_dir)
        
        if choice == '4' or choice == '5':
            fig = visualizer.visualize_interpretation_chart()
            visualizer.save_figure(fig, 'interpretation_chart.png', output_dir)
        
        print(f"\n图形已保存到 {output_dir} 目录")


if __name__ == "__main__":
    main()
