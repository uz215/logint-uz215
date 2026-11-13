import re

def main():
    # 读取清理后的文件
    with open(r"f:\360\Pythonwork\project\src\logInt_cleaned.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 在 DataProcessor 类的 interpretation 方法前添加 calculation 方法
    
    # 找到 interpretation 方法的位置
    interpretation_start = content.find("def interpretation(self):")
    if interpretation_start == -1:
        print("未找到 interpretation 方法")
        return
    
    # 创建 calculation 方法内容
    calculation_method = """    def calculation(self):
        \"\"\"计算泥质含量、孔隙度、饱和度等参数\"\"\"
        if self.data is None:
            logger.error(\"Data not loaded\")
            return None
        
        data = self.data.copy()
        
        # 确保VSH（泥质含量）列存在
        if 'VSH' not in data.columns:
            if 'GR' in data.columns:
                # 使用自然伽马计算泥质含量
                GR_min = data['GR'].min()
                GR_max = data['GR'].max()
                if GR_max > GR_min:
                    data['VSH'] = (data['GR'] - GR_min) / (GR_max - GR_min)
                    data['VSH'] = data['VSH'].clip(0, 1)
                else:
                    data['VSH'] = 0
            elif 'RHOB' in data.columns and 'NPHI' in data.columns:
                # 使用密度-中子交汇计算泥质含量
                rho_sand = 2.65
                rho_shale = 2.55
                nphi_sand = -0.02
                nphi_shale = 0.35
                
                rho_vsh = (data['RHOB'] - rho_sand) / (rho_shale - rho_sand)
                nphi_vsh = (data['NPHI'] - nphi_sand) / (nphi_shale - nphi_sand)
                data['VSH'] = (rho_vsh + nphi_vsh) / 2
                data['VSH'] = data['VSH'].clip(0, 1)
            else:
                data['VSH'] = 0
        
        # 计算孔隙度 (φ)
        if 'POR' in data.columns:
            data['PHI'] = data['POR']
            data['PHI'] = data['PHI'].clip(0, 1)
        elif 'RHOB' in data.columns:
            # 密度测井计算孔隙度
            if 'LITHOLOGY' in data.columns:
                matrix_densities = {
                    '砂岩': 2.65,
                    '灰岩': 2.71,
                    '白云岩': 2.87,
                    '碳酸盐岩': 2.71
                }
                fluid_density = 1.0
                
                def calculate_phi(row):
                    lithology = row.get('LITHOLOGY', '其他')
                    rhob = row.get('RHOB', 2.65)
                    if lithology in matrix_densities:
                        matrix_density = matrix_densities[lithology]
                        phi = (matrix_density - rhob) / (matrix_density - fluid_density)
                        return max(0, min(1, phi))
                    else:
                        return 0
                
                data['PHI'] = data.apply(calculate_phi, axis=1)
            else:
                data['PHI'] = (2.65 - data['RHOB']) / (2.65 - 1.0)
                data['PHI'] = data['PHI'].clip(0, 1)
        elif 'NPHI' in data.columns:
            data['PHI'] = data['NPHI']
            data['PHI'] = data['PHI'].clip(0, 1)
        elif 'DT' in data.columns:
            data['PHI'] = (data['DT'] - 55.5) / (189 - 55.5)
            data['PHI'] = data['PHI'].clip(0, 1)
        else:
            data['PHI'] = 0.2
        
        # 计算Sw（含水饱和度）
        if 'SW' in data.columns:
            data['Sw'] = data['SW']
            data['Sw'] = data['Sw'].clip(0, 1)
        elif 'RT' in data.columns and 'PHI' in data.columns:
            Rw = 0.05
            a = 1.0
            m = 2.0
            n = 2.0
            
            data['Sw'] = (a * Rw / (data['PHI']**m * data['RT']))**(1/n)
            data['Sw'] = data['Sw'].clip(0, 1)
            
            if 'VSH' in data.columns:
                Rsh = 2.0
                data.loc[data['VSH'] > 0.2, 'Sw'] = (a * Rw / (data.loc[data['VSH'] > 0.2, 'PHI']**m * data.loc[data['VSH'] > 0.2, 'RT']) + 
                                                      data.loc[data['VSH'] > 0.2, 'VSH'] / Rsh)**(-1)
                data['Sw'] = data['Sw'].clip(0, 1)
        else:
            data['Sw'] = 1.0
        
        self.data = data
        logger.info("Calculation completed")
        return data

"""
    
    # 在 interpretation 方法前插入 calculation 方法
    before_interpretation = content[:interpretation_start]
    after_interpretation = content[interpretation_start:]
    result = before_interpretation + calculation_method + after_interpretation
    print("添加 calculation 方法完成")

    # 2. 删除 run_workflow 中的重复计算代码
    # 找到计算代码的开始和结束位置
    calc_start = result.find("# 确保VSH（泥质含量）列存在")
    calc_end = result.find("# 生成INTERPRETATION列", calc_start)
    
    if calc_start != -1 and calc_end != -1:
        # 替换为调用 calculation 方法
        replacement = """                        # 调用 calculation 方法计算参数
                        data = self.data_processor.calculation()
                        
                        # 生成INTERPRETATION列"""
        final_result = result[:calc_start] + replacement + result[calc_end:]
        print("删除重复计算代码完成")
    else:
        final_result = result
        print("未找到需要删除的计算代码")

    # 写入最终文件
    with open(r"f:\360\Pythonwork\project\src\logInt_final.py", "w", encoding="utf-8") as f:
        f.write(final_result)

    print("计算代码整合完成！")

if __name__ == "__main__":
    main()
