import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import ndimage
from scipy.ndimage import binary_dilation, binary_erosion
from skimage import filters, measure
from skimage.segmentation import watershed
from skimage.feature import canny
from skimage.morphology import remove_small_objects, closing, opening
import os
from pathlib import Path
import logging
import cv2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MicroresistivityImagingProcessor:
    """微电阻率成像处理器"""
    
    def __init__(self, config=None):
        """初始化处理器"""
        self.config = config or self._get_default_config()
        self.data = None
        self.processed_data = None
        self.results = {}
        self.output_dir = Path(self.config.get('output_dir', 'output/microresistivity'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'output_dir': 'output/microresistivity',
            'resistivity_threshold': 0.5,  # 相对阈值
            'min_pore_size': 5,  # 最小孔隙尺寸（像素）
            'min_fracture_length': 10,  # 最小裂缝长度（像素）
            'sigma': 2,  # 高斯滤波标准差
            'canny_sigma': 1,  # Canny边缘检测标准差
            'closing_kernel_size': 3,  # 闭运算核大小
            'opening_kernel_size': 2,  # 开运算核大小
            'porosity_calculation_method': 'area_fraction',  # 孔隙度计算方法
            'min_area': 50,  # 最小面积阈值
            'vug_area_threshold': 200,  # 溶孔面积阈值
            'vug_elongation_threshold': 0.5,  # 溶孔细长度阈值
            'fracture_elongation_threshold': 0.7  # 裂缝细长度阈值
        }
    
    def load_data(self, file_path):
        """加载微电阻率成像数据"""
        try:
            file_path = Path(file_path)
            file_ext = file_path.suffix.lower()
            
            logger.info(f"正在加载微电阻率成像数据: {file_path}")
            
            if file_ext in ['.csv', '.las']:
                # 加载数据文件
                if file_ext == '.csv':
                    # 假设CSV格式为：深度, 极板1通道1, 极板1通道2, ..., 极板n通道m
                    self.data = pd.read_csv(file_path)
                elif file_ext == '.las':
                    try:
                        import lasio
                        las = lasio.read(file_path)
                        self.data = las.df().reset_index()
                    except ImportError:
                        logger.error("需要安装lasio库: pip install lasio")
                        return None
                
                # 按深度排序
                depth_cols = ['MD', 'DEPTH', 'Depth', 'depth']
                depth_col = next((col for col in depth_cols if col in self.data.columns), None)
                if depth_col:
                    self.data = self.data.sort_values(depth_col).reset_index(drop=True)
                    # 统一深度列名为MD
                    if depth_col != 'MD':
                        self.data = self.data.rename(columns={depth_col: 'MD'})
                
                logger.info(f"数据加载成功，共 {len(self.data)} 条记录")
                return self.data
            elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
                # 加载图像文件，支持中文路径
                try:
                    # 使用np.fromfile和cv2.imdecode处理中文路径
                    image_data = np.fromfile(str(file_path), dtype=np.uint8)
                    self.image_data = cv2.imdecode(image_data, cv2.IMREAD_GRAYSCALE)
                    if self.image_data is None:
                        raise FileNotFoundError(f"无法加载图像，请检查路径: {file_path}")
                    logger.info(f"图像加载成功，尺寸: {self.image_data.shape}")
                    return self.image_data
                except Exception as e:
                    logger.error(f"加载图像时出错: {e}")
                    raise FileNotFoundError(f"无法加载图像，请检查路径: {file_path}")
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            return None
    
    def preprocess_data(self):
        """预处理数据"""
        if hasattr(self, 'image_data') and self.image_data is not None:
            # 处理图像数据
            # 高斯模糊，减少噪声的影响
            blurred = cv2.GaussianBlur(self.image_data, (5, 5), 0)
            
            # 使用Otsu's方法自动找到最佳阈值，将低电阻率区域分离出来
            _, binary_mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # 形态学操作，开运算（先腐蚀后膨胀）用于去除小的白色噪点
            kernel = np.ones((3,3), np.uint8)
            cleaned_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel, iterations=1)
            
            # 闭运算（先膨胀后腐蚀）用于填充孔洞内部的小黑点，使区域更完整
            filled_mask = cv2.morphologyEx(cleaned_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            
            self.processed_data = {
                'image': self.image_data,
                'blurred': blurred,
                'binary_mask': binary_mask,
                'filled_mask': filled_mask
            }
            
            logger.info("图像数据预处理完成")
            return self.processed_data
        elif self.data is not None:
            # 处理数据文件
            # 提取电阻率数据列（排除深度列）
            depth_col = 'MD'
            resistivity_cols = [col for col in self.data.columns if col != depth_col]
            
            # 标准化电阻率数据（0-1范围）
            resistivity_data = self.data[resistivity_cols].values
            min_res = np.min(resistivity_data)
            max_res = np.max(resistivity_data)
            normalized_data = (resistivity_data - min_res) / (max_res - min_res)
            
            # 保存预处理后的数据
            self.processed_data = {
                'depth': self.data[depth_col].values,
                'resistivity': normalized_data,
                'min_res': min_res,
                'max_res': max_res
            }
            
            logger.info("数据文件预处理完成")
            return self.processed_data
        else:
            logger.error("数据未加载")
            return None
    
    def analyze_image(self):
        """分析微电阻率成像图，识别溶孔和裂缝并计算孔隙度"""
        if not hasattr(self, 'processed_data') or self.processed_data is None:
            logger.error("数据未预处理")
            return None
        
        if 'filled_mask' in self.processed_data:
            # 处理图像数据
            filled_mask = self.processed_data['filled_mask']
            image = self.processed_data['image']
            
            height, width = image.shape
            total_pixels = height * width
            
            # 查找连通组件，即独立的孔隙或裂缝区域
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(filled_mask, connectivity=8)
            
            # 过滤掉背景标签 (label 0)
            vug_count = 0
            fracture_count = 0
            total_pore_area = 0
            
            # 用于可视化的彩色图像
            color_img = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            
            for i in range(1, num_labels): # 从1开始，跳过背景
                area = stats[i, cv2.CC_STAT_AREA]
                
                # 定义一个最小面积阈值，过滤掉太小的噪点
                min_area = self.config['min_area']
                if area < min_area:
                    continue

                # 获取该连通区域的轮廓，用于计算周长等特征
                mask_single_component = (labels == i).astype(np.uint8) * 255
                contours, _ = cv2.findContours(mask_single_component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                if not contours:
                    continue
                    
                cnt = contours[0]
                perimeter = cv2.arcLength(cnt, True)
                
                if perimeter == 0:
                    continue

                # 计算细长度 (Elongation)，这是区分溶孔和裂缝的关键指标
                # 细长度接近0表示圆形（溶孔），接近1表示线性（裂缝）
                elongation = 1 - (4 * area) / (perimeter * perimeter)

                # 根据面积和细长度进行分类
                if area > self.config['vug_area_threshold'] and elongation < self.config['vug_elongation_threshold']: # 大面积且不细长 -> 溶孔
                    vug_count += 1
                    # 溶孔用绿色绘制
                    cv2.drawContours(color_img, [cnt], 0, (0, 255, 0), 1)
                elif area > min_area and elongation > self.config['fracture_elongation_threshold']: # 小面积但很细长 -> 裂缝
                    fracture_count += 1
                    # 裂缝用红色绘制
                    cv2.drawContours(color_img, [cnt], 0, (0, 0, 255), 1)
                
                # 累加所有有效孔隙的面积
                total_pore_area += area

            # 计算孔隙度
            porosity = (total_pore_area / total_pixels) * 100
            
            # 保存结果
            result = {
                'porosity': porosity,
                'vug_count': vug_count,
                'fracture_count': fracture_count,
                'total_pore_area': total_pore_area,
                'total_pixels': total_pixels,
                'color_img': color_img
            }
            
            return result
        else:
            logger.error("不是图像数据")
            return None
    
    def interpolate_pad_gaps(self, pad_image, gap_width=5):
        """处理极板间的空白区域，使用插值方法填充
        
        Args:
            pad_image: 极板数据图像，形状为 (num_pads, pad_length)
            gap_width: 极板间空白区域的宽度（像素）
            
        Returns:
            full_wellbore_image: 全井眼图像，包含插值后的空白区域
        """
        num_pads, pad_length = pad_image.shape
        
        # 计算全井眼图像的宽度
        full_width = pad_length * num_pads + gap_width * (num_pads - 1)
        full_wellbore_image = np.zeros((num_pads, full_width))
        
        # 填充极板数据
        for i in range(num_pads):
            start_col = i * (pad_length + gap_width)
            end_col = start_col + pad_length
            full_wellbore_image[:, start_col:end_col] = pad_image
        
        # 对极板间的空白区域进行插值
        for i in range(num_pads - 1):
            # 计算当前极板的结束列和下一个极板的开始列
            current_end = (i + 1) * pad_length + i * gap_width
            next_start = current_end + gap_width
            
            # 提取当前极板的最后一列和下一个极板的第一列
            current_col = pad_image[:, -1]
            next_col = pad_image[:, 0]
            
            # 在空白区域进行线性插值
            for j in range(gap_width):
                # 计算插值权重
                weight = (j + 1) / (gap_width + 1)
                interpolated_col = current_col * (1 - weight) + next_col * weight
                full_wellbore_image[:, current_end + j] = interpolated_col
        
        return full_wellbore_image
    
    def identify_features(self, depth_index):
        """识别特定深度的溶孔和裂缝"""
        if self.processed_data is None:
            logger.error("数据未预处理")
            return None
        
        # 获取该深度的电阻率数据
        resistivity_slice = self.processed_data['resistivity'][depth_index, :]
        
        # 假设数据是8个极板，每个极板有N个传感器
        # 这里我们将数据重塑为8行N列的图像
        num_pads = 8
        pad_length = len(resistivity_slice) // num_pads
        pad_image = resistivity_slice.reshape(num_pads, pad_length)
        
        # 处理极板间的空白区域，生成全井眼图像
        full_wellbore_image = self.interpolate_pad_gaps(pad_image)
        
        # 1. 高斯滤波降噪
        image_smoothed = filters.gaussian(full_wellbore_image, sigma=self.config['sigma'])
        
        # 2. 阈值分割识别低电阻率区域（可能是孔隙或裂缝）
        threshold = self.config['resistivity_threshold']
        binary_image = image_smoothed < threshold
        
        # 3. 形态学操作
        # 闭运算（先膨胀后腐蚀）填充小空洞
        closing_kernel = np.ones((self.config['closing_kernel_size'], self.config['closing_kernel_size']))
        binary_image = closing(binary_image, closing_kernel)
        
        # 开运算（先腐蚀后膨胀）去除小物体
        opening_kernel = np.ones((self.config['opening_kernel_size'], self.config['opening_kernel_size']))
        binary_image = opening(binary_image, opening_kernel)
        
        # 4. 移除小物体
        # 使用max_size参数替代min_size参数以适应scikit-image 0.26+版本
        binary_image = remove_small_objects(binary_image, max_size=self.config['min_pore_size'] - 1)
        
        # 5. 分割连通区域
        labels = measure.label(binary_image)
        regions = measure.regionprops(labels)
        
        # 6. 识别溶孔和裂缝
        pores = []
        fractures = []
        
        for region in regions:
            # 计算区域的长宽比
            if region.area > 0:
                minr, minc, maxr, maxc = region.bbox
                width = maxc - minc
                height = maxr - minr
                aspect_ratio = max(width, height) / min(width, height) if min(width, height) > 0 else 0
                
                # 裂缝通常是长条形的，长宽比大
                if aspect_ratio > 3 and (width > self.config['min_fracture_length'] or height > self.config['min_fracture_length']):
                    fractures.append(region)
                else:
                    pores.append(region)
        
        # 7. 计算孔隙度
        total_pixels = full_wellbore_image.size
        pore_pixels = np.sum(binary_image)
        porosity = pore_pixels / total_pixels
        
        result = {
            'image': full_wellbore_image,
            'binary_image': binary_image,
            'labels': labels,
            'pores': pores,
            'fractures': fractures,
            'porosity': porosity
        }
        
        return result
    
    def process_all_depths(self):
        """处理所有深度"""
        if self.processed_data is None:
            logger.error("数据未预处理")
            return None
        
        if 'depth' in self.processed_data:
            # 处理数据文件
            depths = self.processed_data['depth']
            porosity_values = []
            pore_counts = []
            fracture_counts = []
            
            for i, depth in enumerate(depths):
                if i % 10 == 0:  # 每10个深度打印一次进度
                    logger.info(f"处理深度: {depth:.2f}m ({i+1}/{len(depths)})")
                
                result = self.identify_features(i)
                if result:
                    porosity_values.append(result['porosity'])
                    pore_counts.append(len(result['pores']))
                    fracture_counts.append(len(result['fractures']))
                else:
                    porosity_values.append(0)
                    pore_counts.append(0)
                    fracture_counts.append(0)
            
            # 保存结果
            self.results['depth'] = depths
            self.results['porosity'] = np.array(porosity_values)
            self.results['pore_count'] = np.array(pore_counts)
            self.results['fracture_count'] = np.array(fracture_counts)
            
            # 保存到CSV文件
            results_df = pd.DataFrame({
                'MD': depths,
                'Porosity': porosity_values,
                'Pore_Count': pore_counts,
                'Fracture_Count': fracture_counts
            })
            output_csv = self.output_dir / 'microresistivity_results.csv'
            results_df.to_csv(output_csv, index=False)
            logger.info(f"结果保存至: {output_csv}")
            
            return self.results
        else:
            logger.error("不是深度数据")
            return None
    
    def visualize_results(self):
        """可视化结果"""
        if not self.results and not hasattr(self, 'processed_data'):
            logger.error("无结果可可视化")
            return None
        
        # 创建输出目录
        viz_dir = self.output_dir / 'visualization'
        viz_dir.mkdir(exist_ok=True)
        
        if 'depth' in self.results:
            # 处理深度数据
            # 1. 孔隙度随深度变化图
            fig, ax = plt.subplots(figsize=(10, 12))
            ax.plot(self.results['porosity'], self.results['depth'])
            ax.set_xlabel('Porosity')
            ax.set_ylabel('Depth (m)')
            ax.set_title('Porosity vs Depth')
            ax.invert_yaxis()  # 深度向下增加
            plt.tight_layout()
            porosity_plot_path = viz_dir / 'porosity_depth.png'
            plt.savefig(porosity_plot_path)
            plt.close()
            
            # 2. 孔隙和裂缝数量随深度变化图
            fig, ax = plt.subplots(figsize=(10, 12))
            ax.plot(self.results['pore_count'], self.results['depth'], label='Pore Count')
            ax.plot(self.results['fracture_count'], self.results['depth'], label='Fracture Count')
            ax.set_xlabel('Count')
            ax.set_ylabel('Depth (m)')
            ax.set_title('Pore and Fracture Count vs Depth')
            ax.invert_yaxis()
            ax.legend()
            plt.tight_layout()
            count_plot_path = viz_dir / 'pore_fracture_count.png'
            plt.savefig(count_plot_path)
            plt.close()
            
            # 3. 示例深度的成像图和识别结果
            # 选择几个代表性深度
            sample_indices = [0, len(self.results['depth'])//4, len(self.results['depth'])//2, 3*len(self.results['depth'])//4, -1]
            
            for i in sample_indices:
                if i < len(self.results['depth']):
                    depth = self.results['depth'][i]
                    result = self.identify_features(i)
                    
                    if result:
                        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
                        
                        # 原始电阻率图像
                        im1 = axes[0].imshow(result['image'], cmap='gray', vmin=0, vmax=1)
                        axes[0].set_title(f'Original Resistivity Image (Depth: {depth:.2f}m)')
                        plt.colorbar(im1, ax=axes[0])
                        
                        # 识别结果
                        im2 = axes[1].imshow(result['binary_image'], cmap='binary')
                        axes[1].set_title(f'Pores and Fractures (Porosity: {result["porosity"]:.4f})')
                        plt.colorbar(im2, ax=axes[1])
                        
                        plt.tight_layout()
                        sample_plot_path = viz_dir / f'sample_{i}_depth_{depth:.2f}.png'
                        plt.savefig(sample_plot_path)
                        plt.close()
        
        if 'color_img' in self.results:
            # 处理图像数据
            output_image_path = viz_dir / 'processed_image.png'
            cv2.imwrite(str(output_image_path), self.results['color_img'])
            logger.info(f"处理完成，结果已保存至: {output_image_path}")
        
        logger.info(f"可视化结果保存至: {viz_dir}")
        return str(viz_dir)
    
    def run_workflow(self, file_path):
        """运行完整工作流"""
        logger.info("开始微电阻率成像处理工作流")
        
        try:
            # 1. 数据加载
            logger.info("Step 1: 数据加载")
            data = self.load_data(file_path)
            
            # 2. 数据预处理
            logger.info("Step 2: 数据预处理")
            self.preprocess_data()
            
            # 3. 处理数据
            logger.info("Step 3: 数据处理")
            file_ext = Path(file_path).suffix.lower()
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                # 处理图像数据
                result = self.analyze_image()
                if result:
                    self.results = result
                    # 保存结果到CSV
                    results_df = pd.DataFrame({
                        'Porosity (%)': [result['porosity']],
                        'Vug Count': [result['vug_count']],
                        'Fracture Count': [result['fracture_count']],
                        'Total Pore Area (pixels)': [result['total_pore_area']],
                        'Total Pixels': [result['total_pixels']]
                    })
                    output_csv = self.output_dir / 'microresistivity_results.csv'
                    results_df.to_csv(output_csv, index=False)
                    logger.info(f"结果保存至: {output_csv}")
            else:
                # 处理深度数据
                self.process_all_depths()
            
            # 4. 结果可视化
            logger.info("Step 4: 结果可视化")
            self.visualize_results()
            
            logger.info("微电阻率成像处理工作流完成")
            return self.results
            
        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            return None

if __name__ == "__main__":
    # 示例用法
    processor = MicroresistivityImagingProcessor()
    # 替换为实际的微电阻率成像数据文件路径
    data_file = "path/to/microresistivity_data.csv"
    processor.run_workflow(data_file)
