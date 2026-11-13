# =============================================================================
# 测井资料处理系统 - 主程序
# =============================================================================
# 运行方式：python main.py --input <file_path>
# 调用顺序：数据加载 -> 测井解释 -> 可视化 -> 报告生成
# =============================================================================

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'well_log_main_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """检查依赖是否安装"""
    print("="*60)
    print("  测井资料处理系统 - 依赖检查")
    print("="*60)
    print()
    
    dependencies = [
        ('pandas', 'pip install pandas', True),
        ('numpy', 'pip install numpy', True),
        ('matplotlib', 'pip install matplotlib', True),
        ('lasio', 'pip install lasio', True),
    ]
    
    missing_deps = []
    for name, cmd, required in dependencies:
        try:
            __import__(name)
            print(f"  {name:15s} - ✓ 已安装")
        except ImportError:
            status = "✗ 未安装" if required else "○ 未安装（可选）"
            print(f"  {name:15s} - {status}")
            if required:
                missing_deps.append((name, cmd))
    
    print()
    
    if missing_deps:
        print("="*60)
        print("  [警告] 缺少核心依赖！")
        print("="*60)
        print()
        print("请运行以下命令安装缺失的依赖：")
        for name, cmd in missing_deps:
            print(f"  {cmd}")
        print()
        return False
    
    return True


def main():
    """主程序入口"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='测井资料处理系统')
    parser.add_argument('--input', '-i', required=True, help='输入测井数据文件路径')
    parser.add_argument('--output', '-o', default='output', help='输出目录')
    parser.add_argument('--skip-visualization', '-sv', action='store_true', help='跳过可视化')
    parser.add_argument('--skip-report', '-sr', action='store_true', help='跳过报告生成')
    parser.add_argument('--well-name', '-n', help='井名')
    args = parser.parse_args()
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # 确定井名
    well_name = args.well_name if args.well_name else Path(args.input).stem
    
    print("\n" + "="*60)
    print(f"  开始处理: {well_name}")
    print("="*60)
    print()
    
    # 1. 数据加载
    print("[1/4] 数据加载...")
    from data_loader import DataLoader
    loader = DataLoader()
    data = loader.load_data(args.input)
    
    if data is None:
        logger.error("数据加载失败")
        sys.exit(1)
    
    # 数据质量检查
    qc_report = loader.data_quality_check()
    if qc_report:
        print(f"  ✓ 数据加载成功，共 {qc_report['total_records']} 条记录")
    
    # 2. 测井解释
    print("\n[2/4] 测井解释处理...")
    from log_interpreter import LogInterpreter
    interpreter = LogInterpreter()
    results = interpreter.run_full_interpretation(data)
    
    if results:
        interpreter.print_summary()
    
    # 3. 可视化
    if not args.skip_visualization:
        print("\n[3/4] 生成可视化图版...")
        from visualizer import WellLogVisualizer
        visualizer = WellLogVisualizer()
        visualizer.set_data(interpreter.data, results)
        
        # 生成综合测井图
        fig = visualizer.visualize_composite_log(f'测井综合图 - {well_name}')
        visualizer.save_figure(fig, f'{well_name}_composite_log.png', output_dir)
        
        # 生成油气层识别图版
        fig = visualizer.visualize_hydrocarbon_plot()
        visualizer.save_figure(fig, f'{well_name}_hydrocarbon_plot.png', output_dir)
        
        # 生成解释成果图版
        fig = visualizer.visualize_interpretation_chart()
        visualizer.save_figure(fig, f'{well_name}_interpretation_chart.png', output_dir)
        
        # 生成孔隙度-电阻率交会图
        fig = visualizer.visualize_porosity_resistivity_crossplot()
        visualizer.save_figure(fig, f'{well_name}_crossplot.png', output_dir)
        
        print(f"  ✓ 可视化图版已保存到 {output_dir}")
    
    # 4. 报告生成
    if not args.skip_report:
        print("\n[4/4] 生成报告...")
        from report_generator import ReportGenerator
        generator = ReportGenerator()
        generator.set_data(interpreter.data, results)
        
        report_path = generator.generate_markdown_report(well_name, output_dir)
        if report_path:
            print(f"  ✓ 报告已生成: {report_path}")
    
    # 保存处理后的数据
    output_data_path = output_dir / f'{well_name}_processed.csv'
    interpreter.data.to_csv(output_data_path, index=False, encoding='utf-8')
    print(f"\n  ✓ 处理后数据已保存: {output_data_path}")
    
    print("\n" + "="*60)
    print("  处理完成！")
    print("="*60)


if __name__ == "__main__":
    main()
