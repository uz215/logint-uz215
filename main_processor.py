#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测井资料处理主程序
整合所有功能模块的入口
"""

import numpy as np
import pandas as pd
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WellLogMainProcessor:
    """测井资料处理主程序类"""
    
    def __init__(self, output_dir='output'):
        """初始化主处理器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # 延迟导入模块，避免循环依赖
        self.data_loader = None
        self.data_processor = None
        self.lithology_identifier = None
        self.facies_analyzer = None
        self.well_log_interpreter = None
        self.spring_detector = None
        self.visualizer = None
        
        self._import_modules()
    
    def _import_modules(self):
        """延迟导入各个模块"""
        try:
            from data_loader import DataLoader
            self.data_loader = DataLoader()
            logger.info("数据加载模块导入成功")
        except ImportError as e:
            logger.error(f"数据加载模块导入失败: {e}")
        
        try:
            from data_processor import DataProcessor
            self.data_processor = DataProcessor()
            logger.info("数据处理模块导入成功")
        except ImportError as e:
            logger.error(f"数据处理模块导入失败: {e}")
        
        try:
            from lithology_identifier import LithologyIdentifier
            self.lithology_identifier = LithologyIdentifier()
            logger.info("岩性识别模块导入成功")
        except ImportError as e:
            logger.error(f"岩性识别模块导入失败: {e}")
        
        try:
            from facies_analyzer import FaciesAnalyzer
            self.facies_analyzer = FaciesAnalyzer()
            logger.info("沉积相分析模块导入成功")
        except ImportError as e:
            logger.error(f"沉积相分析模块导入失败: {e}")
        
        try:
            from well_log_interpreter import WellLogInterpreter
            self.well_log_interpreter = WellLogInterpreter()
            logger.info("测井解释模块导入成功")
        except ImportError as e:
            logger.error(f"测井解释模块导入失败: {e}")
        
        try:
            from spring_detector import SpringSegmentDetector
            self.spring_detector = SpringSegmentDetector()
            logger.info("弹簧段检测模块导入成功")
        except ImportError as e:
            logger.error(f"弹簧段检测模块导入失败: {e}")
        
        try:
            from visualizer import DataVisualizer
            self.visualizer = DataVisualizer(output_dir=str(self.output_dir))
            logger.info("可视化模块导入成功")
        except ImportError as e:
            logger.error(f"可视化模块导入失败: {e}")
    
    def load_data(self, file_path):
        """
        加载测井数据
        
        参数:
            file_path: 数据文件路径
        
        返回:
            加载的数据DataFrame
        """
        if self.data_loader is None:
            logger.error("数据加载模块未初始化")
            return None
        
        data = self.data_loader.load_data(file_path)
        return data
    
    def quality_check(self, data):
        """
        数据质量检查
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            质量检查报告
        """
        if self.data_processor is None:
            logger.error("数据处理模块未初始化")
            return None
        
        self.data_processor.set_data(data)
        return self.data_processor.data_quality_check()
    
    def feature_engineering(self, data):
        """
        特征工程
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            处理后的数据
        """
        if self.data_processor is None:
            logger.error("数据处理模块未初始化")
            return None
        
        self.data_processor.set_data(data)
        return self.data_processor.feature_engineering()
    
    def detect_spring_segments(self, data, curve_names=None):
        """
        检测弹簧段
        
        参数:
            data: 测井数据DataFrame
            curve_names: 要检测的曲线名称列表
        
        返回:
            弹簧段检测结果
        """
        if self.spring_detector is None:
            logger.error("弹簧段检测模块未初始化")
            return None
        
        if curve_names is None:
            curve_names = ['MSFL', 'RHOB']
        
        results = {}
        for curve_name in curve_names:
            if curve_name in data.columns:
                segments = self.spring_detector.detect_spring_segments(data, curve_name)
                results[curve_name] = segments
        
        return results
    
    def correct_spring_segments(self, data, curve_names=None, depth_range=None):
        """
        校正弹簧段
        
        参数:
            data: 测井数据DataFrame
            curve_names: 要校正的曲线名称列表
            depth_range: 校正深度范围
        
        返回:
            校正后的数据
        """
        if self.spring_detector is None:
            logger.error("弹簧段检测模块未初始化")
            return None
        
        return self.spring_detector.correct_spring_segments(data, curve_names, depth_range)
    
    def lithology_analysis(self, data):
        """
        岩性分析
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含岩性分析结果的数据
        """
        if self.lithology_identifier is None:
            logger.error("岩性识别模块未初始化")
            return None
        
        return self.lithology_identifier.run_lithology_analysis(data)
    
    def facies_analysis(self, data):
        """
        沉积相分析
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含沉积相分析结果的数据
        """
        if self.facies_analyzer is None:
            logger.error("沉积相分析模块未初始化")
            return None
        
        return self.facies_analyzer.run_facies_analysis(data)
    
    def well_log_interpretation(self, data):
        """
        测井解释
        
        参数:
            data: 测井数据DataFrame
        
        返回:
            包含解释结果的数据
        """
        if self.well_log_interpreter is None:
            logger.error("测井解释模块未初始化")
            return None
        
        return self.well_log_interpreter.run_interpretation(data)
    
    def visualize(self, data, well_name='Unknown'):
        """
        可视化
        
        参数:
            data: 测井数据DataFrame
            well_name: 井名
        
        返回:
            可视化结果字典
        """
        if self.visualizer is None:
            logger.error("可视化模块未初始化")
            return None
        
        # 综合测井图
        composite_path = self.visualizer.visualize_composite_log(data, well_name)
        
        # 孔隙度堆叠图
        porosity_path = self.visualizer.visualize_porosity_stack(data)
        
        # 解释结果
        interp_path = self.visualizer.visualize_interpretation(data)
        
        results = {
            'composite_log': composite_path,
            'porosity_stack': porosity_path,
            'interpretation': interp_path
        }
        
        return results
    
    def run_complete_workflow(self, file_path, well_name='Unknown', depth_range=None):
        """
        运行完整的测井资料处理流程
        
        参数:
            file_path: 数据文件路径
            well_name: 井名
            depth_range: 处理深度范围
        
        返回:
            处理结果字典
        """
        logger.info("=" * 60)
        logger.info(f"开始测井资料处理 - 井名: {well_name}")
        logger.info("=" * 60)
        
        results = {
            'well_name': well_name,
            'data': None,
            'processed_data': None,
            'spring_segments': None,
            'lithology_result': None,
            'facies_result': None,
            'interpretation_result': None,
            'visualization': None,
            'errors': []
        }
        
        try:
            # 1. 数据加载
            logger.info("步骤1: 数据加载")
            data = self.load_data(file_path)
            if data is None:
                raise ValueError("数据加载失败")
            results['data'] = data
            logger.info(f"数据加载成功，共 {len(data)} 条记录")
            
            # 2. 数据质量检查
            logger.info("步骤2: 数据质量检查")
            qc_report = self.quality_check(data)
            if qc_report:
                logger.info(f"总记录数: {qc_report['total_records']}")
                logger.info(f"缺失值: {qc_report['missing_values']}")
            
            # 3. 特征工程
            logger.info("步骤3: 特征工程")
            processed_data = self.feature_engineering(data)
            results['processed_data'] = processed_data
            
            # 4. 弹簧段检测与校正
            logger.info("步骤4: 弹簧段检测与校正")
            spring_segments = self.detect_spring_segments(processed_data)
            results['spring_segments'] = spring_segments
            
            if spring_segments:
                for curve, segments in spring_segments.items():
                    if segments:
                        logger.info(f"{curve} 曲线检测到 {len(segments)} 个弹簧段")
                        for seg in segments:
                            logger.info(f"  - {seg[0]:.1f}m - {seg[1]:.1f}m")
                
                # 校正弹簧段
                processed_data = self.correct_spring_segments(processed_data, depth_range=depth_range)
                logger.info("弹簧段校正完成")
            
            # 检查有效曲线数量
            required_curves = ['GR', 'RT', 'LLD', 'RHOB', 'NPHI', 'AC', 'DTC']
            available_count = sum(1 for c in required_curves if c in processed_data.columns and processed_data[c].notnull().any())
            logger.info(f"有效曲线数量: {available_count}")
            
            # 5. 岩性分析（有效曲线 >= 2条时进行）
            logger.info("步骤5: 岩性分析")
            if available_count >= 2:
                processed_data = self.lithology_analysis(processed_data)
                results['lithology_result'] = processed_data
                logger.info("岩性分析完成")
            else:
                logger.warning("有效曲线少于2条，跳过岩性分析")
            
            # 6. 沉积相分析（有效曲线 >= 2条时进行）
            logger.info("步骤6: 沉积相分析")
            if available_count >= 2:
                processed_data = self.facies_analysis(processed_data)
                results['facies_result'] = processed_data
                logger.info("沉积相分析完成")
            else:
                logger.warning("有效曲线少于2条，跳过沉积相分析")
            
            # 7. 测井解释（有效曲线 >= 2条时进行）
            logger.info("步骤7: 测井解释")
            if available_count >= 2:
                processed_data = self.well_log_interpretation(processed_data)
                results['interpretation_result'] = processed_data
                logger.info("测井解释完成")
            else:
                logger.warning("有效曲线少于2条，跳过测井解释")
            
            # 8. 可视化
            logger.info("步骤8: 可视化")
            visualization_results = self.visualize(processed_data, well_name)
            results['visualization'] = visualization_results
            
            # 9. 保存处理后的数据
            output_path = self.output_dir / f"{well_name}_processed.csv"
            processed_data.to_csv(output_path, index=False, encoding='utf-8-sig')
            logger.info(f"处理后的数据已保存至: {output_path}")
            
            logger.info("=" * 60)
            logger.info("测井资料处理完成")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"处理流程失败: {e}")
            import traceback
            traceback.print_exc()
            results['errors'].append(str(e))
        
        return results


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='测井资料处理程序')
    parser.add_argument('file_path', help='测井数据文件路径')
    parser.add_argument('--well_name', default='Unknown', help='井名')
    parser.add_argument('--output_dir', default='output', help='输出目录')
    parser.add_argument('--start_depth', type=float, help='起始深度')
    parser.add_argument('--end_depth', type=float, help='结束深度')
    
    args = parser.parse_args()
    
    # 创建主处理器
    processor = WellLogMainProcessor(output_dir=args.output_dir)
    
    # 构建深度范围
    depth_range = None
    if args.start_depth is not None and args.end_depth is not None:
        depth_range = (args.start_depth, args.end_depth)
    
    # 运行处理流程
    results = processor.run_complete_workflow(
        file_path=args.file_path,
        well_name=args.well_name,
        depth_range=depth_range
    )
    
    # 输出结果摘要
    print("\n" + "=" * 60)
    print("处理结果摘要")
    print("=" * 60)
    print(f"井名: {results['well_name']}")
    
    if results['spring_segments']:
        print("\n弹簧段检测结果:")
        for curve, segments in results['spring_segments'].items():
            print(f"  {curve}: {len(segments)} 个弹簧段")
    
    if results['visualization']:
        print("\n可视化结果:")
        for key, path in results['visualization'].items():
            if path:
                print(f"  {key}: {path}")
    
    if results['errors']:
        print("\n错误信息:")
        for error in results['errors']:
            print(f"  - {error}")


if __name__ == '__main__':
    main()
