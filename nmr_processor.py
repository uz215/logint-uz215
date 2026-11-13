#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NMR测井数据处理模块
负责T1、D计算，T2谱显示和T1/T2,T2/D交汇图
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import pandas as pd
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NMRLogProcessing:
    """
    核磁测井数据处理类
    支持T2谱bin显示、T1/T2和T2/D交汇图计算
    """
    
    def __init__(self, t2_times=None, t2_amplitudes=None):
        """
        初始化
        :param t2_times: T2时间数组 (ms)
        :param t2_amplitudes: T2幅度数组 (孔隙度分量)
        """
        self.t2_times = t2_times  # T2时间轴
        self.t2_amplitudes = t2_amplitudes  # T2幅度谱
        self.t1_data = None
        self.d_data = None
        self.bin_edges = None
        self.bin_centers = None
        self.binned_amplitudes = None
        self.t1_t2_ratio = None
    
    def set_standard_bins(self, num_bins=32, t2_min=0.3, t2_max=3000):
        """
        设置标准T2 bin边界（对数刻度）
        """
        # 对数等间距bin边界
        log_min = np.log10(t2_min)
        log_max = np.log10(t2_max)
        self.bin_edges = np.logspace(log_min, log_max, num_bins + 1)
        self.bin_centers = np.sqrt(self.bin_edges[:-1] * self.bin_edges[1:])
        return self.bin_centers, self.bin_edges
    
    def rebin_t2_spectrum(self, method='sum'):
        """
        将原始T2谱重新分bin
        :param method: 'sum'或'mean'
        :return: binned_amplitudes
        """
        if self.bin_edges is None:
            self.set_standard_bins()
            
        binned_amp = np.zeros(len(self.bin_centers))
        
        for i in range(len(self.bin_centers)):
            mask = (self.t2_times >= self.bin_edges[i]) &  \
                   (self.t2_times < self.bin_edges[i+1])
            
            if np.any(mask):
                if method == 'sum':
                    binned_amp[i] = np.sum(self.t2_amplitudes[mask])
                else:
                    binned_amp[i] = np.mean(self.t2_amplitudes[mask])
                    
        self.binned_amplitudes = binned_amp
        return binned_amp
    
    def plot_t2_bin_spectrum(self, figsize=(10, 6), show_cumulative=False):
        """
        绘制T2 Bin谱显示
        """
        fig, ax = plt.subplots(figsize=figsize)
        
        # 绘制柱状图（bin谱）
        bars = ax.bar(self.bin_centers, self.binned_amplitudes,  
                     width=np.diff(self.bin_edges),  
                     edgecolor='black', alpha=0.7, color='steelblue',
                     align='edge')
        
        # 设置对数刻度
        ax.set_xscale('log')
        ax.set_xlabel('T2 Relaxation Time (ms)', fontsize=12)
        ax.set_ylabel('Amplitude (Porosity Unit)', fontsize=12)
        ax.set_title('NMR T2 Bin Spectrum', fontsize=14, fontweight='bold')
        
        # 添加网格
        ax.grid(True, which='both', linestyle='--', alpha=0.5)
        ax.set_xlim(self.bin_edges[0], self.bin_edges[-1])
        
        # 添加累积曲线（可选）
        if show_cumulative:
            ax2 = ax.twinx()
            cumulative = np.cumsum(self.binned_amplitudes)
            ax2.plot(self.bin_centers, cumulative, 'r-', linewidth=2,  
                    marker='o', markersize=4, label='Cumulative')
            ax2.set_ylabel('Cumulative Amplitude', color='red')
            ax2.tick_params(axis='y', labelcolor='red')
            
        plt.tight_layout()
        return fig
    
    def calculate_t1_from_t2(self, method='default', c1=3.0, c2=1.0):
        """
        根据T2计算T1
        方法1: T1 = c1 * T2 (经验关系，c1通常在1-3之间)
        方法2: 基于扩散的复杂模型
        """
        if method == 'default':
            # 简单线性关系 T1/T2 ≈ 常数
            self.t1_data = c1 * self.t2_times
            self.t1_t2_ratio = np.full_like(self.t2_times, c1)
        elif method == 'variable':
            # 可变T1/T2比（根据T2时间变化）
            # 粘土束缚水: T1/T2 ≈ 1-2
            # 毛细管束缚水: T1/T2 ≈ 1.5-3
            # 自由流体: T1/T2 ≈ 2-4
            ratio = np.where(self.t2_times < 3, 1.5,
                    np.where(self.t2_times < 33, 2.0, 3.0))
            self.t1_data = ratio * self.t2_times
            self.t1_t2_ratio = ratio
            
        return self.t1_data
    
    def calculate_d_from_t2(self, temperature=25, method='looyestijn'):
        """
        根据T2计算扩散系数D
        使用Looyestijn经验公式或物理模型
        
        :param temperature: 温度(°C)
        :param method: 'looyestijn'或'physical'
        """
        # 温度校正因子
        temp_factor = (temperature + 273.15) / 298.15
        
        if method == 'looyestijn':
            # Looyestijn公式: D = a * T2^b
            # 对于水: a ≈ 2.5e-9, b ≈ 0.5 (经验值)
            a = 2.5e-9 * temp_factor
            b = 0.5
            self.d_data = a * (self.t2_times ** b)
        else:
            # 物理模型: D = k * T / (η * r)
            # 简化模型
            self.d_data = 2.5e-9 * temp_factor * np.ones_like(self.t2_times)
            
        return self.d_data
    
    def plot_t1_t2_crossplot(self, figsize=(8, 8)):
        """
        绘制T1/T2交汇图
        """
        if self.t1_data is None:
            self.calculate_t1_from_t2()
            
        fig, ax = plt.subplots(figsize=figsize)
        
        # 计算T1/T2比
        t1_t2_ratio = self.t1_data / self.t2_times
        
        # 创建散点图，颜色表示幅度
        scatter = ax.scatter(self.t2_times, t1_t2_ratio,  
                           c=self.t2_amplitudes,  
                           s=100, cmap='viridis',  
                           edgecolors='black', alpha=0.7)
        
        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Amplitude', fontsize=10)
        
        # 设置坐标轴
        ax.set_xscale('log')
        ax.set_xlabel('T2 (ms)', fontsize=12)
        ax.set_ylabel('T1/T2 Ratio', fontsize=12)
        ax.set_title('T1/T2 vs T2 Crossplot', fontsize=14, fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.5)
        
        # 添加典型流体区域标注
        ax.axhspan(1.0, 2.0, alpha=0.2, color='blue', label='Clay-bound water')
        ax.axhspan(2.0, 3.0, alpha=0.2, color='green', label='Capillary-bound water')
        ax.axhspan(3.0, 4.0, alpha=0.2, color='red', label='Free fluid')
        ax.legend(loc='upper left')
        
        return fig
    
    def plot_t2_d_crossplot(self, figsize=(8, 8)):
        """
        绘制T2/D交汇图（用于流体识别）
        """
        if self.d_data is None:
            self.calculate_d_from_t2()
            
        fig, ax = plt.subplots(figsize=figsize)
        
        # 计算T2/D
        t2_d_ratio = self.t2_times / (self.d_data * 1e9)  # 转换为合适的单位
        
        scatter = ax.scatter(self.d_data * 1e9, self.t2_times,  
                           c=self.t2_amplitudes, 
                           s=100, cmap='plasma', 
                           edgecolors='black', alpha=0.7)
        
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Amplitude', fontsize=10)
        
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel('Diffusion Coefficient D (10^-9 m²/s)', fontsize=12)
        ax.set_ylabel('T2 (ms)', fontsize=12)
        ax.set_title('T2 vs D Crossplot (Fluid Typing)',  
                    fontsize=14, fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.5)
        
        # 添加典型流体线
        # 水线
        d_water = np.linspace(1, 10, 100)
        t2_water = 1000 * d_water  # 经验关系
        ax.plot(d_water, t2_water, 'b--', linewidth=2, label='Water line')
        
        # 油线（D较小）
        d_oil = np.full_like(d_water, 2.0)
        ax.plot(d_oil, np.linspace(10, 1000, 100), 'g--',  
               linewidth=2, label='Oil line')
        
        ax.legend()
        return fig
    
    def multi_dimension_analysis(self):
        """
        综合多维分析：T1-T2-D三维交汇
        """
        if self.t1_data is None:
            self.calculate_t1_from_t2()
        if self.d_data is None:
            self.calculate_d_from_t2()
            
        fig = plt.figure(figsize=(12, 4))
        
        # 子图1: T2谱
        ax1 = fig.add_subplot(131)
        ax1.semilogx(self.t2_times, self.t2_amplitudes, 'b-', linewidth=2)
        ax1.fill_between(self.t2_times, self.t2_amplitudes, alpha=0.3)
        ax1.set_xlabel('T2 (ms)')
        ax1.set_ylabel('Amplitude')
        ax1.set_title('T2 Spectrum')
        ax1.grid(True)
        
        # 子图2: T1-T2交汇
        ax2 = fig.add_subplot(132)
        ax2.loglog(self.t2_times, self.t1_data, 'ro', markersize=6)
        ax2.plot([0.1, 10000], [0.1, 10000], 'k--', label='T1=T2')
        ax2.set_xlabel('T2 (ms)')
        ax2.set_ylabel('T1 (ms)')
        ax2.set_title('T1-T2 Crossplot')
        ax2.legend()
        ax2.grid(True)
        
        # 子图3: T2-D交汇
        ax3 = fig.add_subplot(133)
        ax3.loglog(self.d_data * 1e9, self.t2_times, 'gs', markersize=6)
        ax3.set_xlabel('D (10^-9 m²/s)')
        ax3.set_ylabel('T2 (ms)')
        ax3.set_title('T2-D Crossplot')
        ax3.grid(True)
        
        plt.tight_layout()
        return fig


def example_usage():
    """
    完整使用示例
    """
    # 1. 生成模拟的T2数据（实际应用中替换为真实测井数据）
    # 模拟一个双峰T2分布（束缚水+自由水）
    t2_times = np.logspace(-1, 4, 64)  # 0.1ms 到 10000ms，64个采样点
    
    # 模拟幅度谱（双峰：粘土水+毛细管水+自由水）
    amp1 = 0.3 * np.exp(-((np.log10(t2_times) - 0.5)**2) / 0.2)  # 粘土水 ~3ms
    amp2 = 0.5 * np.exp(-((np.log10(t2_times) - 1.5)**2) / 0.3)  # 毛细管水 ~30ms  
    amp3 = 0.2 * np.exp(-((np.log10(t2_times) - 2.8)**2) / 0.2)  # 自由水 ~600ms
    t2_amplitudes = amp1 + amp2 + amp3
    
    # 2. 初始化处理器
    nmr = NMRLogProcessing(t2_times, t2_amplitudes)
    
    # 3. 设置bin并重新分bin
    bin_centers, bin_edges = nmr.set_standard_bins(num_bins=16)
    binned_amp = nmr.rebin_t2_spectrum(method='sum')
    
    print("Bin边界:", bin_edges)
    print("Bin中心:", bin_centers)
    print("分bin后幅度:", binned_amp)
    
    # 4. 绘制T2 Bin谱
    fig1 = nmr.plot_t2_bin_spectrum(show_cumulative=True)
    plt.savefig('t2_bin_spectrum.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 5. 计算T1和D
    nmr.calculate_t1_from_t2(method='variable')
    nmr.calculate_d_from_t2(temperature=80, method='looyestijn')
    
    # 6. 绘制T1/T2交汇图
    fig2 = nmr.plot_t1_t2_crossplot()
    plt.savefig('t1_t2_crossplot.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 7. 绘制T2/D交汇图
    fig3 = nmr.plot_t2_d_crossplot()
    plt.savefig('t2_d_crossplot.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 8. 综合分析
    fig4 = nmr.multi_dimension_analysis()
    plt.savefig('nmr_multi_analysis.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    return nmr


if __name__ == "__main__":
    processor = example_usage()
