# =============================================================================
# 报告生成模块
# =============================================================================
# 支持单独运行：python report_generator.py <file_path>
# =============================================================================

import os
import sys
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('report_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ReportGenerator:
    """报告生成类"""
    
    def __init__(self):
        """初始化报告生成器"""
        self.data = None
        self.results = None
        self.summary = None
    
    def set_data(self, data, results=None):
        """设置数据"""
        self.data = data.copy()
        self.results = results
        if results and 'interpretation_summary' in results:
            self.summary = results['interpretation_summary']
        return self
    
    def generate_markdown_report(self, well_name='Unknown Well', output_dir='output'):
        """生成Markdown格式报告"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        report_content = []
        
        # 报告标题
        report_content.append(f"# 测井解释报告")
        report_content.append(f"## {well_name}")
        report_content.append(f"\n**报告生成时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        report_content.append(f"**数据记录数**: {len(self.data)}")
        report_content.append(f"\n---\n")
        
        # 一、数据概况
        report_content.append("## 一、数据概况")
        report_content.append("### 1.1 曲线列表")
        report_content.append("| 曲线名称 | 数据类型 |")
        report_content.append("|---------|---------|")
        for col in self.data.columns:
            dtype = str(self.data[col].dtype)
            report_content.append(f"| {col} | {dtype} |")
        
        if 'MD' in self.data.columns:
            report_content.append(f"\n### 1.2 深度范围")
            report_content.append(f"- 起始深度: {self.data['MD'].min():.2f} m")
            report_content.append(f"- 终止深度: {self.data['MD'].max():.2f} m")
            report_content.append(f"- 深度间隔: {self.data['MD'].max() - self.data['MD'].min():.2f} m")
        
        report_content.append("\n---\n")
        
        # 二、解释结果摘要
        report_content.append("## 二、解释结果摘要")
        if self.summary:
            report_content.append("### 2.1 油气层统计")
            report_content.append("| 类别 | 数量 |")
            report_content.append("|------|------|")
            report_content.append(f"| 油层 | {self.summary.get('oil_zones', 0)} |")
            report_content.append(f"| 气层 | {self.summary.get('gas_zones', 0)} |")
            report_content.append(f"| 水层 | {self.summary.get('water_zones', 0)} |")
            report_content.append(f"| 干层 | {self.summary.get('dry_zones', 0)} |")
            
            report_content.append("\n### 2.2 储层参数统计")
            report_content.append("| 参数 | 平均值 |")
            report_content.append("|------|--------|")
            report_content.append(f"| 孔隙度 (PHI) | {self.summary.get('avg_porosity', 0):.2f} |")
            report_content.append(f"| 含水饱和度 (Sw) | {self.summary.get('avg_saturation', 0):.2f} |")
            report_content.append(f"| 渗透率 (K) | {self.summary.get('avg_permeability', 0):.2f} mD |")
        
        report_content.append("\n---\n")
        
        # 三、储层参数曲线数据
        report_content.append("## 三、储层参数数据")
        report_content.append("### 3.1 参数曲线")
        
        # 列出可用的曲线
        curve_groups = {
            '测井曲线': ['GR', 'SP', 'RT', 'LLD', 'LLS', 'MSFL', 'CAL', 'CALS', 'CALI'],
            '孔隙度曲线': ['PHI', 'RHOB', 'NPHI', 'DT', 'POR'],
            '饱和度曲线': ['Sw', 'So', 'SW'],
            '岩性参数': ['VSH', 'LITHOLOGY'],
            '油气层解释': ['HYDROCARBON']
        }
        
        for group_name, curves in curve_groups.items():
            available_curves = [c for c in curves if c in self.data.columns]
            if available_curves:
                report_content.append(f"\n#### {group_name}")
                report_content.append(f"可用曲线: {', '.join(available_curves)}")
        
        report_content.append("\n---\n")
        
        # 四、解释结论
        report_content.append("## 四、解释结论")
        
        if self.summary:
            oil_zones = self.summary.get('oil_zones', 0)
            gas_zones = self.summary.get('gas_zones', 0)
            water_zones = self.summary.get('water_zones', 0)
            dry_zones = self.summary.get('dry_zones', 0)
            
            conclusion = []
            if oil_zones > 0:
                conclusion.append(f"识别出 **{oil_zones} 个油层**，建议进一步分析其含油性和产能潜力。")
            if gas_zones > 0:
                conclusion.append(f"识别出 **{gas_zones} 个气层**，需注意气层的电阻率特征和声波时差特征。")
            if water_zones > 0:
                conclusion.append(f"识别出 **{water_zones} 个水层**，为油水界面识别提供依据。")
            if dry_zones > 0:
                conclusion.append(f"识别出 **{dry_zones} 个干层**，这些层段储集性能较差。")
            
            if conclusion:
                report_content.append("\n".join(conclusion))
            else:
                report_content.append("本次解释未识别出明确的油气层或水层。")
        
        report_content.append("\n---\n")
        
        # 五、附录（可选数据表格）
        report_content.append("## 五、附录")
        report_content.append("### 5.1 数据预览")
        report_content.append("以下为解释结果数据预览（前10条记录）：")
        report_content.append("")
        
        # 选择要显示的列
        display_cols = ['MD', 'GR', 'RT', 'PHI', 'Sw', 'So', 'VSH', 'LITHOLOGY', 'HYDROCARBON']
        available_cols = [c for c in display_cols if c in self.data.columns]
        
        if available_cols:
            # 生成表格头
            report_content.append("| " + " | ".join(available_cols) + " |")
            report_content.append("| " + " | ".join(["---"] * len(available_cols)) + " |")
            
            # 生成数据行
            preview_data = self.data[available_cols].head(10)
            for _, row in preview_data.iterrows():
                row_str = []
                for col in available_cols:
                    val = row[col]
                    if isinstance(val, float):
                        row_str.append(f"{val:.3f}")
                    else:
                        row_str.append(str(val))
                report_content.append("| " + " | ".join(row_str) + " |")
        
        report_content.append("\n---\n")
        report_content.append("*报告结束*")
        
        # 保存报告
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f"{well_name}_interpretation_report_{timestamp}.md"
        report_path = output_path / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))
        
        logger.info(f"报告已生成: {report_path}")
        return report_path
    
    def generate_summary_report(self):
        """生成简洁的摘要报告"""
        if self.data is None:
            logger.error("数据未加载")
            return None
        
        summary = []
        summary.append("="*60)
        summary.append("        测井解释结果摘要")
        summary.append("="*60)
        
        if 'MD' in self.data.columns:
            summary.append(f"深度范围: {self.data['MD'].min():.1f} - {self.data['MD'].max():.1f} m")
        
        if self.summary:
            summary.append("")
            summary.append("【油气层统计】")
            summary.append(f"  油层: {self.summary.get('oil_zones', 0)} 层")
            summary.append(f"  气层: {self.summary.get('gas_zones', 0)} 层")
            summary.append(f"  水层: {self.summary.get('water_zones', 0)} 层")
            summary.append(f"  干层: {self.summary.get('dry_zones', 0)} 层")
            
            summary.append("")
            summary.append("【储层参数】")
            summary.append(f"  平均孔隙度: {self.summary.get('avg_porosity', 0):.2f}")
            summary.append(f"  平均含水饱和度: {self.summary.get('avg_saturation', 0):.2f}")
            summary.append(f"  平均渗透率: {self.summary.get('avg_permeability', 0):.2f} mD")
        
        summary.append("="*60)
        
        return '\n'.join(summary)


def main():
    """模块独立运行入口"""
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        print("请提供数据文件路径作为参数")
        print("用法: python report_generator.py <file_path>")
        sys.exit(1)
    
    # 尝试导入其他模块
    try:
        from data_loader import DataLoader
        from log_interpreter import LogInterpreter
        
        loader = DataLoader()
        data = loader.load_data(file_path)
        
        if data is not None:
            interpreter = LogInterpreter()
            results = interpreter.run_full_interpretation(data)
    except ImportError:
        logger.warning("无法导入其他模块，直接读取CSV")
        data = pd.read_csv(file_path)
        results = None
    
    if data is not None:
        generator = ReportGenerator()
        generator.set_data(data, results)
        
        # 打印摘要报告
        summary = generator.generate_summary_report()
        print(summary)
        
        # 生成完整报告
        well_name = Path(file_path).stem
        report_path = generator.generate_markdown_report(well_name, 'reports')
        
        if report_path:
            print(f"\n完整报告已生成: {report_path}")


if __name__ == "__main__":
    main()
