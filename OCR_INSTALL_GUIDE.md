# OCR功能安装指南

## 概述

为了提高扫描生成的PDF文件的识别正确率，系统增加了OCR（光学字符识别）功能。此功能依赖以下组件：

1. **Tesseract OCR引擎** - 核心OCR识别引擎
2. **pdf2image库** - 将PDF转换为图像
3. **poppler工具** - PDF转图像的底层工具

## 安装步骤

### 1. 安装Python依赖包

```bash
pip install pytesseract pdf2image Pillow
```

### 2. 安装Tesseract OCR引擎

#### Windows系统：
1. 下载安装包：https://github.com/UB-Mannheim/tesseract/wiki
2. 运行安装程序，建议安装到默认路径 `C:\Program Files\Tesseract-OCR`
3. 确保安装中文语言包（在安装选项中勾选）

#### Linux系统：
```bash
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-chinese-simplified
```

#### macOS系统：
```bash
brew install tesseract
brew install tesseract-lang  # 安装所有语言包
```

### 3. 安装poppler工具

#### Windows系统：
1. 下载poppler：https://github.com/oschwartz10612/poppler-windows/releases
2. 解压到 `C:\Program Files\poppler-24.02.0`（版本号可能不同）
3. 将 `C:\Program Files\poppler-24.02.0\Library\bin` 添加到系统环境变量PATH

#### Linux系统：
```bash
sudo apt-get install poppler-utils
```

#### macOS系统：
```bash
brew install poppler
```

### 4. 验证安装

创建测试脚本验证OCR功能：

```python
import pytesseract
from pdf2image import convert_from_path

# 测试Tesseract
print("Tesseract版本:", pytesseract.get_tesseract_version())

# 测试基本OCR
test_text = pytesseract.image_to_string('test.png', lang='chi_sim+eng')
print("OCR测试成功!")
```

## 配置说明

### 自定义Tesseract路径

如果Tesseract未安装在默认路径，可以在代码中指定：

```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### 自定义poppler路径

代码中已内置了默认路径，如果安装路径不同，请修改 `_convert_scanned_pdf` 方法中的 `poppler_path` 变量。

## 常见问题

### Q1: OCR识别中文乱码？
- 确保安装了中文语言包
- 检查语言参数是否正确：`lang='chi_sim+eng'`

### Q2: pdf2image报错找不到poppler？
- 确保poppler已正确安装
- 检查poppler路径是否正确
- 重启Python进程使环境变量生效

### Q3: OCR识别率低？
- 确保图像清晰
- 调整图像预处理参数（对比度、阈值等）
- 尝试使用更高分辨率的PDF文件

## 性能优化建议

1. **限制处理页数**：对于超大PDF，建议限制处理前20-30页
2. **多线程处理**：使用多线程并行处理多页
3. **图像压缩**：在OCR前压缩图像尺寸
4. **选择性OCR**：只对扫描页面进行OCR，跳过文本页面

## 技术支持

如遇到安装或使用问题，请检查：
- Python版本 >= 3.7
- 所有依赖包为最新版本
- 系统环境变量配置正确
