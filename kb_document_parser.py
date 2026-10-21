"""
增强型文档解析模块 - 支持docling、mineru、paddleocr及多语言OCR
用于替换/增强 logIntKnowledge.py 中的 DocumentConverter
"""

import os
import re
import threading
import hashlib
from datetime import datetime

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    from docling.document_converter import DocumentConverter as DoclingConverter
    from docling.datamodel.base_models import InputFormat
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

try:
    from magic_pdf.pipe.UNIPipe import UNIPipe
    from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
    MINERU_AVAILABLE = True
except ImportError:
    MINERU_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

try:
    from langdetect import detect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

try:
    from rapidocr import RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    RAPIDOCR_AVAILABLE = False


def generate_file_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _setup_tesseract_path():
    """自动定位 Tesseract 可执行文件（Windows 默认不在 PATH）"""
    import shutil
    cands = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
        shutil.which("tesseract") or "",
    ]
    for c in cands:
        if c and os.path.exists(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return True
    return False


def _ocr_langs_dynamic():
    """检测 tessdata 可用语言, 按测井资料优先级组合"""
    import glob
    base = os.path.dirname(pytesseract.pytesseract.tesseract_cmd)
    tessdata = os.path.join(base, "tessdata")
    avail = set()
    try:
        for p in glob.glob(os.path.join(tessdata, "*.traineddata")):
            avail.add(os.path.splitext(os.path.basename(p))[0])
    except Exception:
        pass
    prio = ["chi_sim", "eng", "spa", "rus", "por", "ara", "fra", "chi_tra", "deu"]
    langs = [l for l in prio if l in avail]
    if not langs:
        return "eng" if "eng" in avail else (sorted(avail)[0] if avail else "eng")
    return "+".join(langs)


def _ocr_preprocess_image(img):
    """OCR 前图像增强: 灰度 + 对比度增强"""
    try:
        from PIL import ImageOps
        if img.mode == "P":
            img = img.convert("RGB")
        if img.mode != "L":
            img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=1)
    except Exception:
        pass
    return img


def filter_logging_content(text):
    if not text:
        return ""
    paragraphs = re.split(r'\n\n+', text)
    filtered = []
    keywords = ["测井", "logging", "poço", "скважина", "pozo", "registro", "каротаж",
                "porosity", "porosidad", "пористость", "porosidade",
                "permeability", "permeabilidad", "проницаемость", "permeabilidade",
                "resistivity", "resistividad", "сопротивление", "resistividade"]
    for para in paragraphs:
        p_lower = para.lower()
        if any(k.lower() in p_lower for k in keywords) or len(para) > 300:
            filtered.append(para)
    return '\n\n'.join(filtered)


class MultiLanguageOCR:
    """基于PaddleOCR的多语言OCR，支持中/英/西/俄/葡"""

    def __init__(self):
        self.ocr_engines = {}
        self._init_engines()

    def _init_engines(self):
        if not PADDLEOCR_AVAILABLE:
            return
        # PaddleOCR支持的多语言模型代码
        self.lang_map = {
            'zh': 'ch',
            'en': 'en',
            'es': 'es',
            'ru': 'ru',
            'pt': 'pt'
        }
        # 默认初始化中英文模型
        try:
            self.ocr_engines['ch'] = PaddleOCR(
                use_angle_cls=True,
                lang='ch'
            )
        except Exception as e:
            print(f"PaddleOCR初始化失败: {e}")

    def _get_engine(self, lang='ch'):
        if not PADDLEOCR_AVAILABLE:
            return None
        paddle_lang = self.lang_map.get(lang, 'ch')
        if paddle_lang not in self.ocr_engines:
            try:
                self.ocr_engines[paddle_lang] = PaddleOCR(
                    use_angle_cls=True,
                    lang=paddle_lang
                )
            except Exception:
                # 回退到ch模型
                paddle_lang = 'ch'
        return self.ocr_engines.get(paddle_lang)

    def ocr_image(self, image_path, lang='ch'):
        engine = self._get_engine(lang)
        if not engine:
            return ""
        try:
            result = engine.ocr(image_path, cls=True)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line:
                        texts.append(line[1][0])
            return '\n'.join(texts)
        except Exception as e:
            print(f"OCR识别失败 {image_path}: {e}")
            return ""

    def ocr_pdf(self, pdf_path, lang='ch', max_pages=30):
        if not PDF2IMAGE_AVAILABLE:
            return ""
        try:
            images = convert_from_path(pdf_path, first_page=1, last_page=max_pages, dpi=300)
            parts = []
            for i, image in enumerate(images):
                # 临时保存图片
                temp_path = f"_temp_ocr_page_{i}.png"
                image.save(temp_path, 'PNG')
                text = self.ocr_image(temp_path, lang=lang)
                if text and len(text.strip()) > 10:
                    parts.append(f"--- 第 {i+1} 页 (OCR) ---\n{text.strip()}")
                os.remove(temp_path)
            return '\n\n'.join(parts)
        except Exception as e:
            print(f"PDF OCR失败 {pdf_path}: {e}")
            return ""


class DocumentParserPipeline:
    """文档解析流水线：docling -> mineru -> pdfplumber -> paddleOCR"""

    def __init__(self):
        self.docling_converter = None
        self._docling_init_failed = False
        if DOCLING_AVAILABLE:
            try:
                self.docling_converter = DoclingConverter()
            except Exception as e:
                # 离线环境无法下载HuggingFace模型时静默跳过
                self._docling_init_failed = True
                print(f"[Docling] 初始化失败（离线环境将自动跳过）: {type(e).__name__}")
        self.ocr = MultiLanguageOCR()

    def parse_pdf(self, file_path, timeout=300):
        """多级PDF解析流水线"""
        result = {'success': False, 'content': '', 'method': ''}

        # 1. 尝试 docling（版面分析+表格+公式）
        if DOCLING_AVAILABLE and self.docling_converter and not self._docling_init_failed:
            try:
                conv_result = self.docling_converter.convert(file_path)
                if conv_result and conv_result.document:
                    content = conv_result.document.export_to_markdown()
                    if content and len(content.strip()) > 100:
                        result['content'] = content
                        result['method'] = 'docling'
                        result['success'] = True
                        return result
            except Exception:
                # Docling解析失败时静默回退，不打印冗长错误
                pass

        # 2. 尝试 mineru（复杂学术PDF）
        if MINERU_AVAILABLE:
            try:
                print(f"[MinerU] 解析PDF: {os.path.basename(file_path)}")
                content = self._parse_with_mineru(file_path)
                if content and len(content.strip()) > 100:
                    result['content'] = content
                    result['method'] = 'mineru'
                    result['success'] = True
                    return result
            except Exception as e:
                print(f"[MinerU] 失败: {e}")

        # 3. 尝试 pdfplumber（文本型PDF）
        if PDFPLUMBER_AVAILABLE:
            try:
                print(f"[pdfplumber] 解析PDF: {os.path.basename(file_path)}")
                content = self._parse_with_pdfplumber(file_path)
                if content and len(content.strip()) > 100:
                    result['content'] = content
                    result['method'] = 'pdfplumber'
                    result['success'] = True
                    return result
            except Exception as e:
                print(f"[pdfplumber] 失败: {e}")

        # 4. rapidocr（扫描版PDF, 本地onnx免配置, PP-OCRv6 中英/多语言强）
        if RAPIDOCR_AVAILABLE and PDF2IMAGE_AVAILABLE:
            try:
                print(f"[RapidOCR] 识别扫描PDF: {os.path.basename(file_path)}")
                content = self._parse_with_rapidocr(file_path)
                if content and len(content.strip()) > 50:
                    result['content'] = content
                    result['method'] = 'rapidocr'
                    result['success'] = True
                    return result
            except Exception as e:
                print(f"[RapidOCR] 失败: {e}")

        # 5. 尝试 PaddleOCR（扫描版PDF）
        if PADDLEOCR_AVAILABLE and PDF2IMAGE_AVAILABLE:
            try:
                print(f"[PaddleOCR] 识别扫描PDF: {os.path.basename(file_path)}")
                content = self.ocr.ocr_pdf(file_path, max_pages=30)
                if content and len(content.strip()) > 50:
                    result['content'] = content
                    result['method'] = 'paddleocr'
                    result['success'] = True
                    return result
            except Exception as e:
                print(f"[PaddleOCR] 失败: {e}")

        # 注: 按要求不使用 Tesseract, 扫描件统一走 RapidOCR (PP-OCRv6 onnx)
        return result

    def _parse_with_rapidocr(self, file_path, max_pages=15, timeout=120):
        """使用 RapidOCR (PP-OCRv6, 本地onnx) 识别扫描PDF
        加时间上限与图片尺寸限制, 防超大扫描件卡死; 损坏PDF直接跳过"""
        import time as _time
        import fitz
        from PIL import Image
        import io
        # 预检: 损坏/非PDF直接跳过, 避免 poppler 渲染挂起
        try:
            doc = fitz.open(file_path)
            if doc.page_count == 0:
                print(f"[RapidOCR] 空PDF跳过: {os.path.basename(file_path)}", flush=True)
                return ""
            images = []
            for i in range(min(max_pages, doc.page_count)):
                pm = doc[i].get_pixmap(dpi=150)
                im = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
                images.append(im)
            doc.close()
        except Exception as e:
            print(f"[RapidOCR] PDF打开失败跳过: {os.path.basename(file_path)} ({e})", flush=True)
            return ""
        t0 = _time.monotonic()
        _engine = RapidOCR()
        parts = []
        for i, image in enumerate(images):
            if _time.monotonic() - t0 > timeout:
                print(f"[RapidOCR] 达到时间上限 {timeout}s, 停止于第 {i+1} 页", flush=True)
                break
            try:
                # 限制图片最大边长, 防 1 亿像素图卡死
                w, h = image.size
                scale = min(1.0, 1800.0 / max(w, h))
                if scale < 1.0:
                    image = image.resize((int(w*scale), int(h*scale)))
                temp_path = f"_temp_rapid_page_{i}.png"
                image.save(temp_path, 'PNG')
                res = _engine(temp_path)
                texts = list(getattr(res, 'txts', None) or [])
                os.remove(temp_path)
                if texts:
                    block = '\n'.join(' '.join(str(t).split()) for t in texts)
                    if len(block.strip()) > 10:
                        parts.append(f"--- 第 {i+1} 页 (RapidOCR) ---\n{block.strip()}")
            except Exception as e:
                print(f"[RapidOCR] 第{i+1}页失败: {e}")
                continue
        return '\n\n'.join(parts)

    def _parse_with_mineru(self, file_path):
        """使用MinerU解析PDF"""
        try:
            import json
            file_name = os.path.basename(file_path).replace('.pdf', '')
            output_dir = f"_mineru_temp_{file_name}"
            os.makedirs(output_dir, exist_ok=True)

            writer = FileBasedDataWriter(output_dir)
            reader = FileBasedDataReader()
            pdf_bytes = reader.read(file_path)

            pipe = UNIPipe(pdf_bytes, {"_pdf_type": "", "model_list": []}, image_writer=writer)
            pipe.pipe_classify()
            pipe.pipe_parse()
            pipe.pipe_mk_markdown(output_dir, f"{file_name}.md")

            md_path = os.path.join(output_dir, f"{file_name}.md")
            if os.path.exists(md_path):
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 清理临时文件
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
                return content
        except Exception:
            return ""
        return ""

    def _parse_with_pdfplumber(self, file_path):
        """使用pdfplumber解析文本型PDF"""
        content = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 20:
                    content.append(f"--- 第 {i+1} 页 ---\n{text.strip()}")
                # 表格提取
                try:
                    tables = page.extract_tables()
                    for t_idx, table in enumerate(tables):
                        if table and len(table) >= 2:
                            header = table[0]
                            rows = ["| " + " | ".join(str(c or "") for c in header) + " |"]
                            rows.append("| " + " | ".join("---" for _ in header) + " |")
                            for row in table[1:]:
                                rows.append("| " + " | ".join(str(c or "") for c in row) + " |")
                            content.append(f"\n**表格 {t_idx+1} (第{i+1}页)**\n" + "\n".join(rows))
                except Exception:
                    pass
        return '\n\n'.join(content)

    def _parse_with_tesseract(self, file_path, max_pages=0):
        """使用Tesseract OCR作为最终回退（PyMuPDF 渲染, 动态语言, 图像增强）

        Args:
            max_pages: 最大页数限制, 0=无限制
        """
        import fitz  # PyMuPDF
        from PIL import Image
        if not _setup_tesseract_path():
            print("[Tesseract] 未找到可执行文件, OCR 跳过")
            return ""
        langs = _ocr_langs_dynamic()
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            print(f"[Tesseract] PDF 打开失败: {e}")
            return ""
        parts = []
        total = doc.page_count
        limit = max_pages if max_pages > 0 else total
        for i in range(min(limit, total)):
            try:
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))  # ~180dpi
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img = _ocr_preprocess_image(img)
                text = pytesseract.image_to_string(img, lang=langs)
                if text and len(text.strip()) > 20:
                    parts.append(f"--- 第 {i+1} 页 (OCR) ---\n{text.strip()}")
            except Exception as e:
                print(f"[Tesseract] 第 {i+1} 页失败: {e}")
                continue
        doc.close()
        return '\n\n'.join(parts)

    def parse_image(self, image_path, lang_hint='ch'):
        """解析图片：优先PaddleOCR，回退Tesseract"""
        if PADDLEOCR_AVAILABLE:
            text = self.ocr.ocr_image(image_path, lang=lang_hint)
            if text and len(text.strip()) > 10:
                return text
        if PYTESSERACT_AVAILABLE:
            try:
                from PIL import Image
                img = Image.open(image_path)
                return pytesseract.image_to_string(img, lang='chi_sim+eng').strip()
            except Exception:
                return ""
        return ""
