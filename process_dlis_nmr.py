"""
处理DLIS文件并提取NMR T2谱数据
使用dlisio 1.0.x API
"""
from dlisio import dlis
import numpy as np
import pandas as pd
from pathlib import Path
import json

def process_dlis_file(file_path):
    """处理DLIS文件并提取NMR数据"""
    
    print(f"正在处理DLIS文件: {file_path}")
    
    try:
        # dlisio 1.0.x使用dlis.load
        physical_file = dlis.load(file_path)
        print(f"\n文件包含 {len(physical_file)} 个逻辑文件")
        
        all_data = []
        
        for i, logical_file in enumerate(physical_file):
            print(f"\n=== 逻辑文件 {i+1} ===")
            
            # 获取文件头信息
            try:
                fileheader = logical_file.fileheader
                print(f"文件头: {fileheader.id}")
            except:
                pass
            
            # 获取所有通道
            channels = list(logical_file.channels)
            print(f"通道数量: {len(channels)}")
            
            # 打印所有通道名称
            channel_names = [ch.name for ch in channels]
            print(f"\n所有通道名称: {channel_names}")
            
            # 查找深度通道
            depth_channel = None
            depth_candidates = ['TDEP', 'MD', 'DEPTH', 'DEPT', 'TVD', 'TVDSS']
            
            for ch in channels:
                if ch.name.upper() in depth_candidates:
                    depth_channel = ch
                    print(f"\n找到深度通道: {ch.name}")
                    print(f"  单位: {ch.units}")
                    break
            
            # 查找T2谱通道
            t2_channels = []
            for ch in channels:
                name_upper = ch.name.upper()
                # 匹配T2谱通道名称
                if any(keyword in name_upper for keyword in ['T2', 'TCMR', 'CMR', 'NMR', 'T2DIST', 'T2SPECTRUM']):
                    t2_channels.append(ch)
            
            print(f"\n找到 {len(t2_channels)} 个T2相关通道")
            for ch in t2_channels:
                print(f"  - {ch.name} (单位: {ch.units}, 维度: {ch.dimension})")
            
            # 获取帧数据
            frames = list(logical_file.frames)
            print(f"\n帧数量: {len(frames)}")
            
            for j, frame in enumerate(frames):
                print(f"\n--- 帧 {j+1}: {frame.name} ---")
                
                try:
                    # 获取帧的所有通道
                    frame_channels = list(frame.channels)
                    print(f"帧通道数量: {len(frame_channels)}")
                    
                    # 读取数据
                    curves = frame.curves()
                    print(f"数据形状: {curves.shape}")
                    print(f"数据类型: {curves.dtype}")
                    
                    # 处理结构化数组
                    if curves.dtype.names:
                        # 结构化数组 - 需要展平多维数据
                        print(f"结构化数组字段: {curves.dtype.names}")
                        
                        data_dict = {}
                        for name in curves.dtype.names:
                            col_data = curves[name]
                            # 如果数据是多维的，需要展平
                            if col_data.ndim > 1:
                                print(f"  字段 {name} 是多维的: {col_data.shape}")
                                # 为每个维度创建单独的列
                                for dim_idx in range(col_data.shape[1]):
                                    new_name = f"{name}_{dim_idx}"
                                    data_dict[new_name] = col_data[:, dim_idx]
                            else:
                                data_dict[name] = col_data
                        
                        df = pd.DataFrame(data_dict)
                    else:
                        # 普通数组
                        df = pd.DataFrame(curves)
                    
                    print(f"\nDataFrame形状: {df.shape}")
                    print(f"列名: {list(df.columns)}")
                    
                    # 查找T2谱列
                    t2_columns = []
                    for col in df.columns:
                        col_str = str(col).upper()
                        if any(keyword in col_str for keyword in ['T2', 'TCMR', 'CMR', 'NMR']):
                            t2_columns.append(col)
                    
                    print(f"\nT2谱列: {t2_columns}")
                    
                    # 显示前几行数据
                    if len(df) > 0:
                        print(f"\n前5行数据:")
                        print(df.head())
                    
                    # 保存数据
                    if len(df) > 0:
                        all_data.append({
                            'logical_file': i+1,
                            'frame': j+1,
                            'frame_name': frame.name,
                            'data': df,
                            't2_columns': t2_columns
                        })
                    
                except Exception as e:
                    print(f"处理帧时出错: {e}")
                    import traceback
                    traceback.print_exc()
        
        return all_data
            
    except Exception as e:
        print(f"处理DLIS文件时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_nmr_data(data_list, output_dir):
    """保存NMR数据到CSV"""
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for item in data_list:
        lf_num = item['logical_file']
        frame_num = item['frame']
        frame_name = item['frame_name']
        df = item['data']
        t2_cols = item['t2_columns']
        
        # 保存完整数据
        filename = f"dlis_lf{lf_num}_frame{frame_num}_{frame_name}.csv"
        filepath = output_path / filename
        df.to_csv(filepath, index=False)
        print(f"\n保存数据到: {filepath}")
        print(f"  记录数: {len(df)}")
        print(f"  列数: {len(df.columns)}")
        
        # 如果有T2谱数据，单独保存
        if t2_cols:
            t2_filename = f"dlis_lf{lf_num}_frame{frame_num}_{frame_name}_T2.csv"
            t2_filepath = output_path / t2_filename
            
            # 查找深度列
            depth_col = None
            for col in df.columns:
                if str(col).upper() in ['TDEP', 'MD', 'DEPTH', 'DEPT']:
                    depth_col = col
                    break
            
            if depth_col:
                t2_df = df[[depth_col] + t2_cols].copy()
            else:
                t2_df = df[t2_cols].copy()
            
            t2_df.to_csv(t2_filepath, index=False)
            print(f"  保存T2谱数据到: {t2_filepath}")

def main():
    """主函数"""
    
    # DLIS文件路径
    dlis_file = Path("data/CuraCao-2 CMR.dlis")
    
    if not dlis_file.exists():
        print(f"错误: 文件不存在 {dlis_file}")
        return
    
    print(f"文件大小: {dlis_file.stat().st_size / 1024 / 1024:.2f} MB")
    
    # 处理DLIS文件
    data = process_dlis_file(str(dlis_file))
    
    if data:
        print(f"\n\n成功提取 {len(data)} 个数据集")
        
        # 保存数据
        save_nmr_data(data, "output/dlis_data")
        
        print("\n处理完成!")
    else:
        print("\n未能提取数据")

if __name__ == "__main__":
    main()
