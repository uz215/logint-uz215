#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
岩性识别模块
负责基于测井曲线进行岩性识别和矿物含量计算
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize, Bounds, LinearConstraint
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LithologyIdentifier:
    """岩性识别类"""
    
    def __init__(self):
        """初始化岩性识别器"""
        # 定义矿物及流体响应矩阵
        # 矿物名称列表
        self.minerals = ['Quartz', 'Calcite', 'Dolomite', 'Clay']
        # 流体列表
        self.fluids = ['Water', 'Oil', 'Gas']
        
        # 响应参数表（每行为一种组分，列为不同测井曲线）
        # 曲线顺序：DEN, CNL, AC, PE, GR
        # 单位：DEN(g/cm3), CNL(小数), AC(us/ft), PE(b/e), GR(API)
        self.params = {
            'Quartz':  [2.65, -0.02, 55.5, 1.81, 30],
            'Calcite': [2.71,  0.00, 47.5, 5.08, 15],
            'Dolomite':[2.87,  0.02, 43.5, 3.14, 20],
            'Clay':    [2.55,  0.35, 80.0, 3.45, 150],
            'Water':   [1.00,  1.00, 189.0, 0.00, 0],
            'Oil':     [0.85,  0.80, 220.0, 0.00, 0],
            'Gas':     [0.25,  0.20, 350.0, 0.00, 0]
        }
        
        # 构建矩阵
        self.n_min = len(self.minerals)
        self.n_flu = len(self.fluids)
        self.n_curves = len(self.params['Quartz'])
        
        # 提取矿物响应矩阵
        self.A_min = np.array([self.params[m] for m in self.minerals])
        # 流体响应矩阵
        self.A_flu = np.array([self.params[f] for f in self.fluids])
        
        # 岩性颜色映射
        self.lithology_colors = {
            '砂岩': '#F4A460',
            '粉砂岩': '#D2691E',
            '泥岩': '#8B4513',
            '灰岩': '#A9A9A9',
            '白云岩': '#C0C0C0',
            '泥质砂岩': '#CD853F',
            '砂质泥岩': '#A0522D',
            '未知': '#808080'
        }
    
    def calculate_mineral_content(self, data):
        """
        使用最优化方法计算矿物含量和孔隙度
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含矿物含量和孔隙度的数据
        """
        if data is None:
            logger.error("数据未提供")
            return None
        
        # 检查必需的曲线
        required_curves = ['DEN', 'CNL', 'AC', 'PE', 'GR']
        available_curves = [c for c in required_curves if c in data.columns]
        
        if len(available_curves) < 2:
            logger.warning(f"有效曲线少于2条（{len(available_curves)}条），不进行岩性分析")
            return data
        
        logger.info(f"使用 {len(available_curves)} 条曲线进行岩性分析: {available_curves}")
        
        # 构建响应矩阵（只使用可用的曲线）
        curve_indices = [i for i, c in enumerate(required_curves) if c in data.columns]
        A_min_subset = self.A_min[:, curve_indices]
        
        # 选择流体响应（假设为水）
        fluid_resp = self.A_flu[self.fluids.index('Water'), curve_indices]
        
        # 目标函数
        def objective(x, measured, A_min, A_fluid):
            V_min = x[:-1]
            phi = x[-1]
            pred = V_min @ A_min + phi * A_fluid
            return np.sum((measured - pred) ** 2)
        
        # 边界：所有变量 >= 0
        bounds = Bounds([0] * (self.n_min + 1), [1] * (self.n_min + 1))
        
        # 线性约束：sum(V_min) + phi = 1
        A_eq = np.ones((1, self.n_min + 1))
        lin_constraint = LinearConstraint(A_eq, lb=1, ub=1)
        
        # 初始值：均匀分配
        x0 = np.ones(self.n_min + 1) / (self.n_min + 1)
        
        results = np.zeros((len(data), self.n_min + 1))
        valid_mask = ~data[available_curves].isnull().any(axis=1)
        
        for i in range(len(data)):
            if not valid_mask.iloc[i]:
                results[i] = np.nan
                continue
            
            meas = data[available_curves].iloc[i].values
            res = minimize(objective, x0, args=(meas, A_min_subset, fluid_resp),
                          method='SLSQP', bounds=bounds, constraints=[lin_constraint])
            
            if res.success:
                results[i] = res.x
                x0 = res.x  # 使用当前解作为下一次的初始值
            else:
                results[i] = np.nan
        
        # 将结果添加到数据中
        result_data = data.copy()
        for i, mineral in enumerate(self.minerals):
            result_data[f'V_{mineral}'] = results[:, i]
        
        result_data['PHI'] = results[:, -1]
        
        logger.info("矿物含量计算完成")
        return result_data
    
    def identify_lithology(self, data):
        """
        根据矿物含量识别岩性
        
        参数:
            data: 包含矿物含量的数据
        
        返回:
            包含岩性识别结果的数据
        """
        if data is None:
            logger.error("数据未提供")
            return None
        
        # 检查是否有矿物含量数据
        mineral_cols = [f'V_{m}' for m in self.minerals]
        if not all(col in data.columns for col in mineral_cols):
            logger.warning("没有矿物含量数据，无法识别岩性")
            return data
        
        # 计算有效曲线数量
        required_curves = ['DEN', 'CNL', 'AC', 'PE', 'GR']
        available_count = sum(1 for c in required_curves if c in data.columns)
        
        if available_count < 2:
            logger.warning(f"有效曲线少于2条，不进行岩性识别")
            data['LITHOLOGY'] = '未知'
            return data
        
        result_data = data.copy()
        
        # 根据矿物含量识别岩性
        def classify_lithology(row):
            quartz = row['V_Quartz']
            calcite = row['V_Calcite']
            dolomite = row['V_Dolomite']
            clay = row['V_Clay']
            phi = row['PHI']
            
            # 处理NaN情况
            if np.isnan(quartz) or np.isnan(clay):
                return '未知'
            
            # 岩性判定规则
            if clay > 0.5:
                if quartz > 0.2:
                    return '砂质泥岩'
                else:
                    return '泥岩'
            elif calcite > 0.4:
                return '灰岩'
            elif dolomite > 0.3:
                return '白云岩'
            elif quartz > 0.5:
                if clay > 0.2:
                    return '泥质砂岩'
                else:
                    return '砂岩'
            elif quartz > 0.3:
                return '粉砂岩'
            else:
                return '未知'
        
        result_data['LITHOLOGY'] = result_data.apply(classify_lithology, axis=1)
        
        logger.info("岩性识别完成")
        return result_data
    
    def calculate_vsh(self, data):
        """
        计算泥质含量
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含泥质含量的数据
        """
        if data is None:
            logger.error("数据未提供")
            return None
        
        result_data = data.copy()
        
        # 使用GR计算泥质含量
        if 'GR' in data.columns:
            gr = data['GR']
            gr_min = gr.min()
            gr_max = gr.max()
            
            if gr_max > gr_min:
                vsh_gr = (gr - gr_min) / (gr_max - gr_min)
                result_data['VSH_GR'] = vsh_gr.clip(0, 1)
                logger.info("使用GR计算泥质含量完成")
        
        # 使用密度-中子交汇计算泥质含量
        if 'RHOB' in data.columns and 'NPHI' in data.columns:
            # 简化计算：基于密度-中子差值
            rho_nphi_diff = data['RHOB'] - data['NPHI']
            result_data['VSH_DN'] = (rho_nphi_diff - rho_nphi_diff.min()) / (rho_nphi_diff.max() - rho_nphi_diff.min() + 1e-10)
            result_data['VSH_DN'] = result_data['VSH_DN'].clip(0, 1)
            logger.info("使用密度-中子交汇计算泥质含量完成")
        
        # 综合泥质含量
        vsh_cols = [c for c in ['VSH_GR', 'VSH_DN'] if c in result_data.columns]
        if vsh_cols:
            result_data['VSH'] = result_data[vsh_cols].mean(axis=1)
            logger.info("综合泥质含量计算完成")
        
        return result_data
    
    def run_lithology_analysis(self, data):
        """
        运行完整的岩性分析流程
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含岩性分析结果的数据
        """
        if data is None:
            logger.error("数据未提供")
            return None
        
        # 检查有效曲线数量
        required_curves = ['DEN', 'CNL', 'AC', 'PE', 'GR', 'RT']
        available_count = sum(1 for c in required_curves if c in data.columns and data[c].notnull().any())
        
        if available_count < 2:
            logger.warning(f"有效曲线少于2条（{available_count}条），跳过岩性分析")
            data['LITHOLOGY'] = '未知'
            return data
        
        logger.info(f"开始岩性分析，有效曲线数: {available_count}")
        
        # 计算泥质含量
        result_data = self.calculate_vsh(data)
        
        # 计算矿物含量
        result_data = self.calculate_mineral_content(result_data)
        
        # 识别岩性
        result_data = self.identify_lithology(result_data)
        
        logger.info("岩性分析完成")
        return result_data
