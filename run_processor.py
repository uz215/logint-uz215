import sys
from pathlib import Path
from logging_processor import LoggingDataProcessor

# 添加当前目录到Python路径
sys.path.append(str(Path(__file__).parent))

def main():
    """主函数，用于运行测录井资料处理"""
    # 创建处理器实例
    processor = LoggingDataProcessor()
    
    # 示例数据文件路径
    # 请替换为实际的测井数据文件
    data_file = "f:\\360\\Pythonwork\\project\\data\\example_log.las"
    
    # 检查文件是否存在
    if not Path(data_file).exists():
        print(f"数据文件不存在: {data_file}")
        print("请替换为实际的测井数据文件路径")
        return
    
    # 运行完整工作流
    print("开始处理测录井资料...")
    results = processor.run_workflow(data_file)
    
    if results:
        print("\n处理完成！")
        print(f"处理后的数据行数: {len(processor.processed_data)}")
        print(f"处理后的数据列: {list(processor.processed_data.columns)}")
        
        # 显示前10行处理后的数据
        print("\n处理后的数据前10行:")
        print(processor.processed_data.head(10))
        
        # 显示解释结果统计
        if 'INTERPRETATION' in processor.processed_data.columns:
            print("\n解释结果统计:")
            print(processor.processed_data['INTERPRETATION'].value_counts())
        
        print("\n处理结果已保存至:")
        print(f"- 可视化结果: {processor.output_dir / 'visualization'}")
        print(f"- 解释报告: {processor.output_dir / 'reports'}")
        print(f"- 经验参数: {processor.output_dir / 'interpretation_params.json'}")
    else:
        print("处理失败！")

if __name__ == "__main__":
    main()
