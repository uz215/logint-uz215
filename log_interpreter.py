# =============================================================================
# 测井解释处理模块
# =============================================================================
# 支持单独运行：python log_interpreter.py <file_path>
# =============================================================================

import os
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log_interpreter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LogInterpreter:
    """测井解释处理类"""
    
    def __init__(self):
        """初始化测井解释器"""
        self.data = None
        self.results = {}
        self.config = {
            'default_matrix_density': 2.65,
            'default_fluid_density': 1.0,
            'default_Rw': 0.05,
            'archie_a': 1.0,
            'archie_m': 2.0,
            'archie_n': 2.0
        }
    
    def set_data(self, data):
        """设置数据"""
        self.data = data.copy()
        return self.data
    
    def calculate_vsh(self, data=None):
        """计算泥质含量"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        if 'VSH' in result.columns:
            result['VSH'] = result['VSH'].clip(0, 1)
        elif 'GR' in result.columns:
            # 使用自然伽马计算泥质含量
            gr_max = result['GR'].quantile(0.95)
            gr_min = result['GR'].quantile(0.05)
            
            def vsh_from_gr(gr):
                if gr_max == gr_min:
                    return 0.5
                return (gr - gr_min) / (gr_max - gr_min)
            
            result['VSH'] = result['GR'].apply(vsh_from_gr).clip(0, 1)
        else:
            # 默认泥质含量设为0.3
            result['VSH'] = 0.3
        
        self.data = result
        return result['VSH']
    
    def calculate_porosity(self, data=None):
        """计算孔隙度"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        if 'POR' in result.columns:
            result['PHI'] = result['POR'].clip(0, 1)
        elif 'RHOB' in result.columns:
            if 'LITHOLOGY' in result.columns:
                matrix_densities = {
                    '砂岩': 2.65,
                    '灰岩': 2.71,
                    '白云岩': 2.87,
                    '碳酸盐岩': 2.71,
                    '泥岩': 2.65
                }
                fluid_density = self.config['default_fluid_density']
                
                def calculate_phi(row):
                    lithology = row.get('LITHOLOGY', '其他')
                    rhob = row.get('RHOB', self.config['default_matrix_density'])
                    if lithology in matrix_densities:
                        matrix_density = matrix_densities[lithology]
                    else:
                        matrix_density = self.config['default_matrix_density']
                    
                    phi = (matrix_density - rhob) / (matrix_density - fluid_density)
                    return max(0, min(1, phi))
                
                result['PHI'] = result.apply(calculate_phi, axis=1)
            else:
                matrix_density = self.config['default_matrix_density']
                fluid_density = self.config['default_fluid_density']
                result['PHI'] = (matrix_density - result['RHOB']) / (matrix_density - fluid_density)
                result['PHI'] = result['PHI'].clip(0, 1)
        elif 'NPHI' in result.columns:
            result['PHI'] = result['NPHI'].clip(0, 1)
        elif 'DT' in result.columns:
            # Wyllie时间平均方程
            result['PHI'] = (result['DT'] - 55.5) / (189 - 55.5)
            result['PHI'] = result['PHI'].clip(0, 1)
        else:
            # 默认孔隙度设为0.2
            result['PHI'] = 0.2
        
        self.data = result
        return result['PHI']
    
    def calculate_water_saturation(self, data=None):
        """计算含水饱和度（使用Archie公式）"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        if 'SW' in result.columns:
            result['Sw'] = result['SW'].clip(0, 1)
        elif 'RT' in result.columns and 'PHI' in result.columns:
            # 使用Archie公式
            Rw = self.config['default_Rw']
            a = self.config['archie_a']
            m = self.config['archie_m']
            n = self.config['archie_n']
            
            def calculate_sw(row):
                rt = row.get('RT', 100)
                phi = row.get('PHI', 0.2)
                
                if phi <= 0 or rt <= 0:
                    return 1.0
                
                # Archie公式: Sw = (a * Rw / (Rt * phi^m))^(1/n)
                try:
                    sw = (a * Rw / (rt * (phi ** m))) ** (1 / n)
                    return max(0, min(1, sw))
                except:
                    return 1.0
            
            result['Sw'] = result.apply(calculate_sw, axis=1)
        else:
            # 默认含水饱和度设为0.5
            result['Sw'] = 0.5
        
        # 计算含油饱和度
        result['So'] = (1 - result['Sw']).clip(0, 1)
        
        self.data = result
        return result['Sw']
    
    def calculate_permeability(self, data=None):
        """计算渗透率（使用Wyllie-Rose公式）"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        if 'PERM' in result.columns:
            result['K'] = result['PERM']
        elif 'PHI' in result.columns:
            # Wyllie-Rose公式
            # K = (phi^3 / (1 - phi)^2) * (10^10 / 141.2)
            result['K'] = np.where(
                result['PHI'] > 0,
                (result['PHI'] ** 3) / ((1 - result['PHI']) ** 2) * 1000,
                0.1
            )
        else:
            # 默认渗透率设为10 mD
            result['K'] = 10.0
        
        self.data = result
        return result['K']
    
    def identify_lithology(self, data=None):
        """识别岩性"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        def classify_lithology(row):
            # 根据测井曲线特征识别岩性
            gr = row.get('GR', 50)
            rhob = row.get('RHOB', 2.65)
            nphi = row.get('NPHI', 0.3)
            dt = row.get('DT', 70)
            
            # 泥岩/页岩
            if gr > 80:
                return '泥岩'
            # 砂岩
            elif gr < 50 and rhob < 2.65:
                return '砂岩'
            # 碳酸盐岩
            elif rhob > 2.7 and nphi < 0.1:
                return '碳酸盐岩'
            # 泥质砂岩
            elif 50 <= gr <= 80:
                return '泥质砂岩'
            else:
                return '其他'
        
        result['LITHOLOGY'] = result.apply(classify_lithology, axis=1)
        self.data = result
        return result['LITHOLOGY']
    
    def identify_hydrocarbon(self, data=None):
        """识别油气层"""
        if data is None:
            data = self.data
        
        if data is None:
            logger.error("数据未加载")
            return None
        
        result = data.copy()
        
        def classify_zone(row):
            sw = row.get('Sw', 0.5)
            phi = row.get('PHI', 0.2)
            rt = row.get('RT', 10)
            
            # 油层：低含水饱和度，较高电阻率
            if sw < 0.4 and phi > 0.15:
                return '油层'
            # 气层：高电阻率，可能有周波跳跃
            elif rt > 100 and phi > 0.15:
                return '气层'
            # 水层：高含水饱和度
            elif sw > 0.7:
                return '水层'
            # 干层：低孔隙度
            elif phi < 0.1:
                return '干层'
            else:
                return '过渡带'
        
        result['HYDROCARBON'] = result.apply(classify_zone, axis=1)
        self.data = result
        return result['HYDROCARBON']
    
    def run_full_interpretation(self, data=None):
        """运行完整的测井解释流程"""
        if data is not None:
            self.set_data(data)
        
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        logger.info("开始测井解释...")
        
        # 计算泥质含量
        self.calculate_vsh()
        logger.info("泥质含量计算完成")
        
        # 计算孔隙度
        self.calculate_porosity()
        logger.info("孔隙度计算完成")
        
        # 计算含水饱和度
        self.calculate_water_saturation()
        logger.info("饱和度计算完成")
        
        # 计算渗透率
        self.calculate_permeability()
        logger.info("渗透率计算完成")
        
        # 识别岩性
        self.identify_lithology()
        logger.info("岩性识别完成")
        
        # 识别油气层
        self.identify_hydrocarbon()
        logger.info("油气层识别完成")
        
        self.results = {
            'processed_data': self.data,
            'interpretation_summary': self.get_interpretation_summary()
        }
        
        logger.info("测井解释完成")
        return self.results
    
    def get_interpretation_summary(self):
        """获取解释结果摘要"""
        if self.data is None:
            return None
        
        summary = {
            'total_zones': len(self.data),
            'oil_zones': (self.data['HYDROCARBON'] == '油层').sum(),
            'gas_zones': (self.data['HYDROCARBON'] == '气层').sum(),
            'water_zones': (self.data['HYDROCARBON'] == '水层').sum(),
            'dry_zones': (self.data['HYDROCARBON'] == '干层').sum(),
            'avg_porosity': self.data['PHI'].mean(),
            'avg_saturation': self.data['Sw'].mean(),
            'avg_permeability': self.data['K'].mean()
        }
        return summary
    
    def print_summary(self):
        """打印解释结果摘要"""
        summary = self.get_interpretation_summary()
        if not summary:
            return
        
        print("\n" + "="*60)
        print("          测井解释结果摘要")
        print("="*60)
        print(f"总层数: {summary['total_zones']}")
        print(f"油层: {summary['oil_zones']} 层")
        print(f"气层: {summary['gas_zones']} 层")
        print(f"水层: {summary['water_zones']} 层")
        print(f"干层: {summary['dry_zones']} 层")
        print(f"\n平均孔隙度: {summary['avg_porosity']:.2f}")
        print(f"平均含水饱和度: {summary['avg_saturation']:.2f}")
        print(f"平均渗透率: {summary['avg_permeability']:.2f} mD")
        print("="*60 + "\n")


def main():
    """模块独立运行入口"""
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        print("请提供数据文件路径作为参数")
        print("用法: python log_interpreter.py <file_path>")
        sys.exit(1)
    
    # 尝试导入数据加载模块
    try:
        from data_loader import DataLoader
        loader = DataLoader()
        data = loader.load_data(file_path)
    except ImportError:
        # 如果无法导入，直接读取CSV
        logger.warning("无法导入data_loader模块，直接读取CSV")
        data = pd.read_csv(file_path)
    
    if data is not None:
        interpreter = LogInterpreter()
        results = interpreter.run_full_interpretation(data)
        
        if results:
            print("\n解释完成！")
            interpreter.print_summary()
            
            # 显示部分结果
            print("\n解释结果预览:")
            preview_cols = ['MD', 'PHI', 'Sw', 'So', 'K', 'VSH', 'LITHOLOGY', 'HYDROCARBON']
            available_cols = [col for col in preview_cols if col in interpreter.data.columns]
            print(interpreter.data[available_cols].head())


if __name__ == "__main__":
    main()
