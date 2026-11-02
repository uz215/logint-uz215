import re

# 读取原始文件
with open('f:/360/Pythonwork/project/src/logIntKnowledge.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到_convert_pdf方法的开始和结束位置
start_pattern = r'def _convert_pdf\(self, file_path, timeout=300\):'
end_pattern = r'\n    def _convert_txt'

start_match = re.search(start_pattern, content)
end_match = re.search(end_pattern, content)

if start_match and end_match:
    start_pos = start_match.start()
    end_pos = end_match.start()
    
    # 新的方法内容
    new_method = '''    def _convert_pdf(self, file_path, timeout=300):
        """转换PDF为Markdown（优先使用liteparse，带超时处理和OCR回退）"""
        import pdfplumber
        import threading
        
        result = {
            'success': False,
            'content': "",
            'method': ""
        }
        
        def worker():
            try:
                content = []
                
                # 优先使用liteparse解析PDF（不设页数上限）
                if LITEPARSE_AVAILABLE:
                    try:
                        print(f"使用liteparse解析PDF: {file_path}")
                        parser = PDFParser()
                        pdf_content = parser.parse(file_path)
                        
                        if pdf_content and len(pdf_content.strip()) > 50:
                            # 按页面分割内容
                            pages = pdf_content.split(chr(12))  # 换页符
                            for i, page_text in enumerate(pages):
                                if page_text and len(page_text.strip()) > 50:
                                    content.append(f"--- 第 {i+1} 页 ---\\\\n{page_text.strip()}")
                        result['method'] = "liteparse"
                    except Exception as liteparse_error:
                        print(f"liteparse解析失败，回退到pdfplumber: {str(liteparse_error)}")
                        # 继续使用pdfplumber（不设页数上限）
                        with pdfplumber.open(file_path) as pdf:
                            for i, page in enumerate(pdf.pages):
                                text = page.extract_text()
                                if text and len(text.strip()) > 50:
                                    content.append(f"--- 第 {i+1} 页 ---\\\\n{text}")
                        result['method'] = "pdfplumber"
                else:
                    # 使用pdfplumber解析（不设页数上限）
                    with pdfplumber.open(file_path) as pdf:
                        for i, page in enumerate(pdf.pages):
                            text = page.extract_text()
                            if text and len(text.strip()) > 50:
                                content.append(f"--- 第 {i+1} 页 ---\\\\n{text}")
                    result['method'] = "pdfplumber"
                
                text_content = '\\\\n\\\\n'.join(content)
                
                # 即使内容较少也保留，而不是直接跳过
                if len(text_content.strip()) < 50 and self.ocr_enabled:
                    print(f"提示: PDF文本内容较少，尝试OCR识别: {file_path}")
                    ocr_content = self._convert_scanned_pdf(file_path, 30)
                    if ocr_content and len(ocr_content.strip()) > len(text_content.strip()):
                        result['content'] = ocr_content
                        result['method'] = "OCR"
                    else:
                        result['content'] = text_content
                else:
                    result['content'] = text_content
                
                result['success'] = True
            except Exception as e:
                # OCR回退机制
                if self.ocr_enabled:
                    try:
                        result['content'] = self._convert_scanned_pdf(file_path, 20)
                        result['method'] = "OCR"
                        result['success'] = True
                    except Exception as ocr_e:
                        result['content'] = ""
                        result['success'] = False
                else:
                    result['content'] = ""
                    result['success'] = False
        
        # 创建线程并启动
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # 超时情况下尝试OCR
            print(f"警告: PDF文本提取超时，尝试OCR识别: {file_path}")
            if self.ocr_enabled:
                try:
                    ocr_content = self._convert_scanned_pdf(file_path, 10)
                    if ocr_content:
                        # 过滤非测井相关内容
                        filtered_content = self._filter_logging_content(ocr_content)
                        print(f"OCR识别成功: {file_path}")
                        return filtered_content
                except Exception as e:
                    print(f"OCR识别失败: {file_path} - {str(e)}")
            return ""
        
        if result['success']:
            # 过滤非测井相关内容
            filtered_content = self._filter_logging_content(result['content'])
            print(f"PDF转换成功 ({result['method']}): {file_path}")
            return filtered_content
        else:
            print(f"PDF转换失败: {file_path}")
            return ""'''
    
    # 替换内容
    new_content = content[:start_pos] + new_method + content[end_pos:]
    
    # 写入文件
    with open('f:/360/Pythonwork/project/src/logIntKnowledge.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print('文件更新成功')
else:
    print('未找到匹配的方法')
