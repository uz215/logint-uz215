
# 测井解释知识库系统
# 支持本地Markdown文档、网络知识更新、全文检索和大模型问答

import os
import re
import yaml
import json
import time
import threading
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID, DATETIME, KEYWORD
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.query import Or
from whoosh import scoring
import jieba
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

# 尝试导入liteparse用于PDF解析
try:
    from liteparse import PDFParser
    LITEPARSE_AVAILABLE = True
except ImportError:
    LITEPARSE_AVAILABLE = False
    print("提示: liteparse未安装，将使用pdfplumber作为PDF解析器")

# 尝试导入playwright用于JS渲染页面爬取
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# 尝试导入docling用于高质量文档解析
try:
    from docling.document_converter import DocumentConverter as DoclingConverter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import ConversionResult
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

# 尝试导入mineru用于复杂PDF解析
try:
    from magic_pdf.data.data_reader_writer import FileBasedDataWriter
    from magic_pdf.pipe.UNIPipe import UNIPipe
    MINERU_AVAILABLE = True
except ImportError:
    try:
        from magic_pdf.pipe.OCRPipe import OCRPipe
        MINERU_AVAILABLE = True
    except ImportError:
        MINERU_AVAILABLE = False

# 尝试导入paddleocr用于多语言OCR
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

# 尝试导入langdetect用于多语言检测
try:
    from langdetect import detect, detect_langs
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

# 导入增强型文档解析和翻译模块（本地辅助模块）
try:
    from kb_document_parser import DocumentParserPipeline
    DOC_PIPELINE_AVAILABLE = True
except ImportError:
    DOC_PIPELINE_AVAILABLE = False

try:
    from kb_translator import MultiLanguageTranslator
    ML_TRANSLATOR_AVAILABLE = True
except ImportError:
    ML_TRANSLATOR_AVAILABLE = False

# 配置参数
DEFAULT_CONFIG = {
    "paths": {
        "data_dir": "data",
        "local_docs": "data/local",
        "crawled_docs": "data/crawled",
        "index_dir": "index",
        "cache_dir": "cache",
        "backup_dir": "backup"
    },
    "crawler": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "max_depth": 3,
        "timeout": 30,
        "max_pages": 500,
        "request_interval": 1.0,
        "max_workers": 5,
        "follow_links": True,
        "allowed_domains": [
            # 中文网站
            "cnki.net", "cnpc.com.cn", "petrochina.com.cn", "sinopec.com", 
            "baike.baidu.com", "zh.wikipedia.org", "zh.wikiversity.org",
            "zh.wikibooks.org", "researchgate.net", "arxiv.org",
            # SPE相关网站
            "spe.org", "petroleumengineering.org", "petrophysics.org",
            "loganalysis.org", "reservoirengineering.org",
            # 学术数据库
            "sciencedirect.com", "elsevier.com", "springer.com",
            "tandfonline.com", "wiley.com", "nature.com", "science.org",
            # 技术厂商
            "schlumberger.com", "halliburton.com", "bakerhughes.com",
            "weatherford.com", "nov.com", "geoservices.slb.com",
            # 其他专业网站
            "scientific.net", "petro.org", "energycentral.com",
            "oilfieldtechnology.com", "worldoil.com", "oilandgasiq.com",
            "offshore-mag.com", "jpt.spe.org", "reservoir-modeling.org",
            # 国内可访问的技术网站
            "iqiyi.com", "sina.com.cn", "sohu.com", "163.com",
            "csdn.net", "cnblogs.com", "oschina.net", "github.com",
            "zhihu.com", "weibo.com", "baidu.com", "tieba.baidu.com",
            "doc88.com", "max.book118.com", "wenku.baidu.com", "xueshu.baidu.com",
            # 新增石油测井专业网站
            "onepetro.org", "spwla.org", "segdl.org", "earthdoc.org",
            "petrowiki.spe.org", "mdpi.com", "geoscienceworld.org",
            "hindawi.com", "iopscience.org",
            # 微信公众号
            "mp.weixin.qq.com", "weixin.qq.com",
            "weixin.sogou.com", "sogou.com"
        ],
        "blocked_patterns": ["login", "register", "download", ".pdf", ".doc", ".xls", ".ppt"],
        # 代理配置 - 默认禁用以避免系统代理干扰
        "proxy_enabled": False,
        "proxy_http": "proxy1.bj.petrochina.cn",
        "proxy_https": "proxy1.bj.petrochina.cn",
        "proxy_user": "",
        "proxy_pass": "",
        "proxy_port": "8080",
        # 无需代理的域名模式（与系统浏览器配置一致）
        "no_proxy_domains": [
            "*.cnpc",
            "*.petrochina.*",
            "10.*",
            "*.petrochina",
            "11.*",
            "*.cnpc.*",
            "*.cnpcint.com",
            "mail.cnlc.cn"
        ],
        "use_playwright": True,
        "playwright_timeout": 30
    },
    "llm": {
        "provider": "ollama",
        "model": "qwen2:7b",
        "temperature": 0.7,
        "max_tokens": 2048,
        "api_base": "http://localhost:11434"
    },
    "search": {
        "top_n": 10,
        "min_score": 0.1,
        "similarity_threshold": 0.8
    },
    "api": {
        "host": "0.0.0.0",
        "port": 8000
    },
    "auto_update": {
        "enabled": True,
        "interval_hours": 24,
        "auto_start": True,
        "enable_merge": True,
        "merge_interval_days": 7,
        "max_docs_per_category": 0,  # 0表示不限制
        "update_sources": [
            # 百度百科（中文测井知识主要来源）
            "https://baike.baidu.com/item/%E6%B5%8B%E4%BA%95",
            "https://zh.wikipedia.org/zh-cn/%E6%B5%8B%E4%BA%95%E6%96%87%E4%BB%B6",
            "https://zh.wikipedia.org/zh-cn/%E6%B5%8B%E4%BA%95%E6%9C%BA%E5%99%A8",
            "https://zh.wikipedia.org/zh-cn/%E5%AE%9A%E7%A9%BA%E5%BA%A6",
            "https://zh.wikipedia.org/zh-cn/%E5%AE%9A%E7%A9%BA%E5%BA%A6%E8%AE%A1%E7%AE%97",
            "https://zh.wikipedia.org/zh-cn/%E6%B3%84%E9%80%9A%E7%8E%87",
            "https://zh.wikipedia.org/zh-cn/%E9%98%BF%E5%B0%94%E5%A5%87%E5%85%AC%E5%BC%8F",
            "https://zh.wikipedia.org/zh-cn/%E6%B0%B4%E5%90%AB%E5%9C%BA%E5%9F%BA",
            "https://zh.wikipedia.org/zh-cn/%E6%B5%8B%E4%BA%95%E8%A7%A3%E9%87%8A",
            "https://zh.wikipedia.org/zh-cn/%E5%AD%90%E5%AD%90%E6%B5%8B%E4%BA%95",
            "https://zh.wikipedia.org/zh-cn/%E5%AF%86%E5%BA%A6%E6%B5%8B%E4%BA%95",
            # 百度百科作为补充
            "https://baike.baidu.com/item/%E6%B5%8B%E4%BA%95",
            "https://baike.baidu.com/item/%E6%B5%8B%E4%BA%95%E8%A7%A3%E9%87%8A",
            "https://baike.baidu.com/item/%E5%AE%9A%E7%A9%BA%E5%BA%A6",
            "https://baike.baidu.com/item/%E6%B3%84%E9%80%9A%E7%8E%87",
            # 专业网站
            "https://waiwenwenxian.top/energy_AI.html",
            # 石油行业网站
            "https://www.petroleumengineering.org",
            "https://www.spe.org",
            "https://www.petrophysics.org",
            "https://www.loganalysis.org",
            "https://www.reservoirmodeling.org",
            "https://www.scientific.net/AMR",
            "https://www.elsevier.com/books-and-journals",
            "https://www.sciencedirect.com",
            # 测井仪器厂商
            "https://www.schlumberger.com",
            "https://www.halliburton.com",
            "https://www.bakerhughes.com",
            "https://www.weatherford.com",
            # 学术期刊
            "https://www.sciencedirect.com/journal/petrophysics",
            "https://www.sciencedirect.com/journal/journal-of-petroleum-science-and-engineering",
            "https://www.spe.org/en/jpt/jpt-home",
            # 微信公众号文章（通过搜狗微信搜索）
            "https://weixin.sogou.com/weixin?type=2&query=%E6%B5%8B%E4%BA%95%E8%A7%A3%E9%87%8A",
            "https://weixin.sogou.com/weixin?type=2&query=%E6%B5%8B%E4%BA%95%E8%AF%84%E4%BB%B7",
            "https://weixin.sogou.com/weixin?type=2&query=%E5%82%A8%E5%B1%82%E8%AF%84%E4%BB%B7",
            "https://weixin.sogou.com/weixin?type=2&query=%E7%9F%B3%E6%B2%B9%E5%9C%B0%E8%B4%A8",
            "https://weixin.sogou.com/weixin?type=2&query=%E8%AF%95%E6%B2%B9",
            "https://weixin.sogou.com/weixin?type=2&query=%E6%B5%8B%E4%BA%95%E6%9B%B2%E7%BA%BF"
        ]
    },
    "logging": {
        "level": "INFO",
        "log_file": "kb.log"
    }
}

# ------------------------------
# 地区和井名提取模块
# ------------------------------
class WellLocationExtractor:
    """从文件名中提取地区、井名、油田等信息"""
    
    # 已知油田和地区名称列表
    OIL_FIELDS = [
        # 中国主要油田
        '大庆', '胜利', '长庆', '塔里木', '辽河', '华北', '吉林', '新疆', 
        '青海', '玉门', '延长', '渤海', '南海', '中海油', '中石油', '中石化',
        # 海外油田
        '中东', '北海', '非洲', '尼日尔', '乍得', '乌兹别克斯坦', '缅甸', 
        '巴西', '秘鲁', '苏丹', '中亚', '阿姆河', '卡拉库姆', 'Agadem', 'Muglad'
    ]
    
    # 国家映射（用于从油田/地区推断国家）
    COUNTRY_MAP = {
        '巴西': 'Brazil', 'Brazil': '巴西',
        '秘鲁': 'Peru', 'Peru': '秘鲁',
        '苏丹': 'Sudan', 'Sudan': '苏丹',
        '尼日尔': 'Niger', 'Niger': '尼日尔',
        '乍得': 'Chad', 'Chad': '乍得',
        '乌兹别克斯坦': 'Uzbekistan', 'Uzbekistan': '乌兹别克斯坦',
        '缅甸': 'Myanmar', 'Myanmar': '缅甸',
        '大庆': '中国', '胜利': '中国', '长庆': '中国', '塔里木': '中国',
        '辽河': '中国', '华北': '中国', '吉林': '中国', '新疆': '中国',
        '青海': '中国', '玉门': '中国', '延长': '中国', '渤海': '中国',
        '南海': '中国', '中东': '中东地区', '北海': '北海地区',
        '非洲': '非洲地区', '中亚': '中亚地区',
        '阿姆河': '中亚', '卡拉库姆': '中亚',
        'Agadem': 'Niger', 'Muglad': 'Sudan'
    }
    
    # 测井测量项目关键词
    LOGGING_PROGRAMS = [
        '常规测井', '综合测井', '标准测井', '成像测井', '核磁测井', 'NMR',
        '声波测井', '阵列声波', 'DSI', 'XMAC', 'Sonic Scanner',
        '电阻率测井', '双侧向', '双感应', '阵列感应', 'AIT', 'HDIL',
        '密度测井', '中子测井', '伽马测井', '自然电位', '井径',
        '地层倾角', 'FMI', 'CMI', 'EMI', 'XRMI', 'STAR',
        '元素俘获', 'ECS', 'GEM', 'FLEX',
        '模块式地层测试', 'MDT', 'RDT', 'RCI', 'RFT',
        '核磁共振', 'CMR', 'MRIL', 'MREX',
        '偶极声波', '正交偶极', 'VSP', '井间地震',
        '随钻测井', 'LWD', 'MWD',
        '生产测井', 'PLT', 'RST', 'RPM'
    ]
    
    # 试油/测试信息关键词
    WELL_TEST_KEYWORDS = [
        '试油', 'DST', '完井测试', '产能测试', '系统试井',
        '生产测试', '酸化', '压裂', '措施', '投产',
        '日产油', '日产气', '日产水', '累计产油', '累计产气',
        '油嘴', '油压', '套压', '流压', '静压',
        '表皮系数', '渗透率', '产能', '无阻流量',
        'well test', 'production test', 'flow rate', 'deliverability'
    ]
    
    # 常见井名模式
    WELL_PATTERNS = [
        # 中文井名模式
        r'([A-Za-z]{1,2}\d{1,4})',  # 如 W123, L1, XJ234
        r'(井号?\d+)',              # 如 井123, 井号456
        r'(\d+号井)',              # 如 123号井
        r'(^\d{1,4}[A-Za-z]?)',     # 如 123, 123A
        r'([A-Za-z]+\d+)',          # 如 Well123, WellA1
    ]
    
    # 构造/区块名称
    STRUCTURES = [
        '构造', '区块', '断块', '凹陷', '凸起', '斜坡', '潜山', '背斜', '向斜'
    ]
    
    def __init__(self):
        pass
    
    def extract_from_filename(self, filename):
        """
        从文件名中提取井名、地区、油田、国家、测量项目等信息
        
        Args:
            filename: 文件名（不含路径）
        
        Returns:
            dict: 包含 extracted_well_name, region, oil_field, country, 
                  structure, depth_range, logging_programs, well_test_info 等信息
        """
        result = {
            'extracted_well_name': None,
            'region': None,
            'oil_field': None,
            'country': None,
            'structure': None,
            'depth_range': None,
            'file_type': None,
            'logging_programs': [],
            'well_test_info': None
        }
        
        # 移除文件扩展名
        basename = os.path.splitext(filename)[0]
        
        # 1. 提取油田/地区信息
        for field in self.OIL_FIELDS:
            if field in basename:
                result['oil_field'] = field
                result['region'] = field
                break
        
        # 2. 提取构造/区块信息
        for structure in self.STRUCTURES:
            if structure in basename:
                result['structure'] = structure
                break
        
        # 3. 提取井名
        well_name = self._extract_well_name(basename)
        if well_name:
            result['extracted_well_name'] = well_name
        
        # 4. 提取深度范围
        depth_range = self._extract_depth_range(basename)
        if depth_range:
            result['depth_range'] = depth_range
        
        # 5. 提取文件类型
        file_type = self._extract_file_type(basename)
        if file_type:
            result['file_type'] = file_type
        
        # 6. 推断国家（从油田/地区映射）
        region_or_field = result['region'] or result['oil_field']
        if region_or_field:
            for key, country in self.COUNTRY_MAP.items():
                if key in region_or_field or region_or_field in key:
                    result['country'] = country
                    break
        
        # 7. 识别测井测量项目（从文件名关键词）
        for program in self.LOGGING_PROGRAMS:
            if program.lower() in basename.lower():
                if program not in result['logging_programs']:
                    result['logging_programs'].append(program)
        
        return result
    
    def _extract_well_name(self, text):
        """提取井名"""
        for pattern in self.WELL_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def _extract_depth_range(self, text):
        """提取深度范围，如 1000-2000m"""
        patterns = [
            r'(\d+)-(\d+)[m米]',
            r'深度(\d+)-(\d+)',
            r'(\d+)_(\d+)[m米]',
            r'(\d+)至(\d+)[m米]'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return f"{match.group(1)}-{match.group(2)}m"
        return None
    
    def _extract_file_type(self, text):
        """提取文件类型"""
        file_types = {
            '测井': 'log_data',
            '解释': 'interpretation',
            '报告': 'report',
            '成果': 'result',
            '分析': 'analysis',
            '评价': 'evaluation',
            '图版': 'crossplot',
            '曲线': 'curve',
            '数据': 'data',
            'LAS': 'las_data',
            'DLIS': 'dlis_data'
        }
        for keyword, file_type in file_types.items():
            if keyword in text:
                return file_type
        return 'other'
    
    def extract_from_path(self, filepath):
        """
        从完整文件路径中提取信息
        
        Args:
            filepath: 完整文件路径
        
        Returns:
            dict: 提取的信息
        """
        filename = os.path.basename(filepath)
        result = self.extract_from_filename(filename)
        
        # 从路径中提取额外信息
        dir_parts = os.path.dirname(filepath).split(os.sep)
        for part in dir_parts:
            # 检查目录名是否包含油田/地区信息
            for field in self.OIL_FIELDS:
                if field in part:
                    if not result['region']:
                        result['region'] = field
                    if not result['oil_field']:
                        result['oil_field'] = field
            # 检查是否包含构造信息
            for structure in self.STRUCTURES:
                if structure in part:
                    if not result['structure']:
                        result['structure'] = structure
        
        return result

# 扩展的测井相关关键词列表
LOGGING_KEYWORDS = [
    # 中文关键词 - 测井类型
    "测井", "录井", "生产测井", "光纤测井", "随钻测井", "LWD", "MWD",
    "裸眼井测井", "套管井测井", "电法测井", "声波测井", "放射性测井",
    "核磁共振测井", "NMR测井", "CMR", "成像测井", "电缆测井", "过套管测井",
    "碳氧比测井", "中子寿命测井", "脉冲中子测井", "密度测井", "中子测井",
    "自然伽马测井", "SP测井", "自然电位测井", "井径测井", "井斜测井",
    "地层倾角测井", "微电阻率测井", "感应测井", "侧向测井", "双侧向测井",
    "微球测井", "微侧向测井", "电磁波传播测井", "介电测井", "偶极子声波测井",
    "交叉偶极声波测井", "全波列测井", "阵列感应测井", "高分辨率感应测井",
    # 特殊测井方法
    "FMI", "EMS", "电成像测井", "声波成像测井", "MAC", "UIT", "元素测井", "ECS",
    "成像测井", "微电阻率成像", "声成像", "超声成像", "井下电视", "井壁成像",
    
    # 中文关键词 - 测井解释与资料
    "测井解释", "测井资料", "测井曲线", "测井数据", "测井报告", "测井成果",
    "综合解释", "储层评价", "储量计算", "产能预测", "测井评价", "测井分析",
    "资料处理", "数据处理", "测井校正", "环境校正", "井眼校正", "深度校正",
    "测井标准化", "曲线对比", "测井标定", "刻度", "测井质量", "质量控制",
    
    # 中文关键词 - 地质与岩性
    "岩性识别", "沉积相", "沉积微相", "沉积环境", "地层对比", "层序地层",
    "砂岩", "泥岩", "碳酸盐岩", "页岩", "煤层", "花岗岩", "玄武岩", "石灰岩",
    "白云岩", "泥灰岩", "粉砂岩", "细砂岩", "中砂岩", "粗砂岩", "砾岩",
    "火山岩", "变质岩", "碎屑岩", "火成岩", "储层", "非储层", "隔层", "盖层",
    
    # 中文关键词 - 测井参数与曲线
    "孔隙度", "渗透率", "电阻率", "自然伽马", "GR", "声波时差", "AC", "DT",
    "密度", "DEN", "中子", "CNL", "自然电位", "SP", "井径", "CAL", "井斜",
    "温度", "压力", "深侧向", "LLD", "浅侧向", "LLS", "微球", "MSFL",
    "感应", "双侧向", "深感应", "浅感应", "中感应", "介电常数", "光电吸收截面",
    "PE", "体积密度", "骨架密度", "流体密度", "中子孔隙度", "含氢指数",
    "声波速度", "岩石力学参数", "泊松比", "杨氏模量", "体积模量", "剪切模量",
    
    # 中文关键词 - 储层流体
    "油气水层", "油层", "气层", "水层", "干层", "可疑层", "油水同层",
    "气水同层", "泥质含量", "Vsh", "含水饱和度", "Sw", "含油饱和度", "So",
    "含气饱和度", "Sg", "束缚水", "残余油", "可动油", "可动水", "地层水",
    "原油", "天然气", "凝析气", "煤层气", "页岩气", "致密气", "稠油", "轻质油",
    
    # 中文关键词 - 测井仪器与设备
    "测井仪", "测井工具", "测井设备", "探头", "传感器", "探测器", "井下仪器",
    "地面系统", "电缆", "遥测系统", "数据采集", "记录系统", "刻度器", "标准井",
    "放射性源", "中子源", "伽马源", "探测器晶体", "光电倍增管", "声波发射器",
    "声波接收器", "电极系", "线圈系", "天线",
    
    # 中文关键词 - 处理方法与模型
    "反演", "建模", "解释模型", "最优化", "神经网络", "机器学习", "深度学习",
    "随机森林", "支持向量机", "聚类分析", "主成分分析", "PCA", "因子分析",
    "岩石物理模型", "体积模型", "多矿物模型", "泥质砂岩模型", "碳酸盐岩模型",
    "阿尔奇公式", "印尼公式", "饱和度模型", "渗透率模型", "孔隙度模型",
    "测井响应方程", "环境影响", "井眼影响", "侵入影响", "校正方法", "数值模拟",
    
    # 中文关键词 - 测井图版与解释标准
    "解释图版", "交会图", "直方图", "频率分布", "岩性图版", "孔隙度图版",
    "饱和度图版", "油气水判别", "解释标准", "行业标准", "国家标准", "API标准",
    "测井规范", "资料验收", "质量评定", "解释结论", "储层分类", "产能评价",
    
    # 英文关键词 - 测井类型
    "logging", "well log", "wireline logging", "logging while drilling", 
    "production logging", "casing logging", "through casing logging",
    "electrical logging", "sonic logging", "acoustic logging", 
    "radioactive logging", "NMR logging", "nuclear magnetic resonance", 
    "CMR", "combinable magnetic resonance",
    "imaging logging", "FMI", "formation microscanner", "CBIL", "STAR", "UBI", 
    "ARI", "AIT", "microresistivity imaging", "acoustic imaging", "sonic imaging",
    "MAC", "multi-array acoustic", "UIT", "ultrasonic imaging tool", 
    "ECS", "elemental capture spectroscopy", "elemental logging",
    "array induction", "laterolog", "microlog", "microresistivity",
    "density logging", "neutron logging", "gamma ray logging",
    "spontaneous potential", "caliper logging", "directional logging",
    "dipmeter logging", "formation tester", "RFT", "MDT", "FMT",
    
    # 英文关键词 - 测井解释
    "log interpretation", "well log analysis", "formation evaluation", 
    "reservoir characterization", "petrophysical analysis", "rock physics",
    "log processing", "data conditioning", "environmental correction",
    "borehole correction", "depth matching", "log correlation",
    "crossplot analysis", "cluster analysis", "pattern recognition",
    
    # 英文关键词 - 地质与岩性
    "lithology", "facies", "sedimentary facies", "microfacies", "stratigraphy",
    "sandstone", "shale", "limestone", "dolomite", "carbonate", "coal",
    "clay", "mudstone", "siltstone", "conglomerate", "breccia",
    "volcanic", "igneous", "metamorphic", "reservoir rock", "cap rock",
    "source rock", "seal rock", "pay zone", "non-pay", "tight formation",
    
    # 英文关键词 - 测井参数
    "porosity", "permeability", "resistivity", "gamma ray", "GR",
    "sonic transit time", "interval transit time", "density", 
    "neutron porosity", "spontaneous potential", "SP", "caliper", 
    "borehole diameter", "deep resistivity", "shallow resistivity",
    "induction", "laterolog", "microservices", "dielectric constant",
    "photoelectric factor", "PE", "hydrogen index", "sonic velocity",
    "Poisson's ratio", "Young's modulus", "bulk modulus", "shear modulus",
    
    # 英文关键词 - 储层流体
    "oil", "gas", "water", "hydrocarbon", "formation water",
    "water saturation", "Sw", "oil saturation", "So", "gas saturation", "Sg",
    "shale volume", "Vsh", "clay volume", "effective porosity", "total porosity",
    "irreducible water", "residual oil", "movable oil", "bound water",
    "connate water", "crude oil", "natural gas", "condensate", "coalbed methane",
    "shale gas", "tight gas", "heavy oil", "light oil",
    
    # 英文关键词 - 解释模型
    "Archie equation", "Simandoux equation", "Waxman-Smits", "dual water",
    "effective medium theory", "Hashin-Shtrikman", "self-consistent approximation",
    "rock physics template", "multi-mineral model", "optimization",
    "inversion", "machine learning", "deep learning", "neural network",
    "random forest", "support vector machine", "SVM", "principal component analysis",
    
    # 英文关键词 - 其他
    "formation", "reservoir", "borehole", "wellbore", "depth", "interval",
    "core analysis", "petrophysics", "crossplot", "log correlation",
    "pay zone", "net pay", "gross pay", "reserves estimation",
    
    # 中文关键词 - 公式参数与经验系数
    "阿尔奇参数", "a参数", "b参数", "m参数", "n参数", "饱和度指数", "胶结指数",
    "岩性系数", "孔隙度指数", "地区经验", "经验系数", "区域参数", "标定参数",
    "地区系数", "区块参数", "油田参数", "Timur公式", "Coates公式",
    "Wyllie公式", "Waxman-Smits公式", "印尼公式", "Simandoux公式",
    
    # 中文关键词 - 油田名称
    "大庆油田", "胜利油田", "长庆油田", "塔里木油田", "辽河油田", "中海油",
    "中石油", "中石化", "华北油田", "吉林油田", "新疆油田", "青海油田",
    "玉门油田", "延长油田", "渤海油田", "南海油田",
    
    # 中文关键词 - 海外地区
    "中东", "北海油田", "非洲", "尼日尔", "乍得", "乌兹别克斯坦", "缅甸",
    "巴西", "秘鲁", "苏丹", "中亚", "阿姆河", "卡拉库姆",
    
    # 英文关键词 - 公式参数
    "Archie parameters", "cementation exponent", "saturation exponent",
    "lithology factor", "formation factor", "a-value", "m-value", "n-value",
    "regional parameters", "empirical coefficients", "calibration",
    "field calibration", "reservoir parameters", "petrophysical parameters",
    "productivity prediction", "well test", "pressure transient", "试井",
    
    # 英文关键词 - 油田名称
    "Daqing", "Shengli", "Changqing", "Tarim", "Liaohe", "Huabei",
    "Jilin", "Xinjiang", "Qinghai", "Yumen", "Bohai", "South China Sea",
    
    # 英文关键词 - 海外地区
    "Middle East", "North Sea", "Africa", "Niger", "Chad", "Uzbekistan",
    "Myanmar", "Brazil", "Peru", "Sudan", "Central Asia", "Amu Darya", "Karakum",
    
    # SPE相关关键词 - 学会与期刊
    "SPE", "Society of Petroleum Engineers", "SPE Journal", "Petrophysics",
    "Journal of Petroleum Science and Engineering", "SPE Annual Technical Conference",
    "ATCE", "SPE Reservoir Evaluation & Engineering", "SPE Production & Operations",
    
    # SPE相关关键词 - 技术领域
    "well logging", "wireline", "formation evaluation", "reservoir engineering",
    "petroleum engineering", "oilfield", "drilling", "completion", "production",
    "enhanced oil recovery", "EOR", "reservoir simulation", "well testing",
    "pressure transient analysis", "PTA", "production logging", "PLT",
    "cased hole logging", "open hole logging", "mud logging", "M/LWD",
    
    # SPE相关关键词 - 储层描述
    "reservoir characterization", "reservoir description", "rock typing",
    "facies modeling", "diagenesis", "porosity classification", "permeability prediction",
    "reservoir heterogeneity", "fracture characterization", "vuggy reservoir",
    "tight reservoir", "shale reservoir", "carbonate reservoir", "sandstone reservoir",
    
    # SPE相关关键词 - 测井新技术
    "nuclear magnetic resonance logging", "NMR", "pulsed neutron capture", "PNC",
    "spectral gamma ray", "elemental logging", "dielectric logging", "EMI",
    "azimuthal resistivity", "cross-dipole sonic", "monopole sonic",
    "Stoneley wave", "flexural wave", "shear wave", "compressional wave",
    
    # SPE相关关键词 - 数据处理
    "log normalization", "depth shift", "log editing", "quality control",
    "data validation", "log calibration", "environmental corrections",
    "borehole effects", "invaded zone", "mud cake", "standoff",
    "tool eccentricity", "temperature correction", "pressure correction",
    
    # SPE相关关键词 - 解释方法
    "deterministic interpretation", "probabilistic interpretation",
    "bayesian inversion", "markov chain monte carlo", "machine learning",
    "artificial neural network", "ANN", "support vector machine", "SVM",
    "random forest", "gradient boosting", "deep learning", "convolutional neural network",
    "recurrent neural network", "RNN", "long short-term memory", "LSTM",
    
    # SPE相关关键词 - 行业标准
    "API RP 20", "API RP 40", "API standard", "ISO 14807", "log quality",
    "log specification", "minimum logging requirements", "logging program",
    "open hole logging suite", "cased hole logging suite",
    
    # 更多英文关键词 - 测井曲线
    "MSFL", "microspherically focused", "LLD", "laterolog deep",
    "LLS", "laterolog shallow", "AIT", "array induction tool", "HDIL",
    "high definition induction", "SFL", "spherically focused log",
    "CNL", "compensated neutron log", "FDC", "formation density",
    "SNP", "sidewall neutron porosity", "DTC", "compressional slowness",
    "DTS", "shear slowness", "DTT", "Stoneley slowness",
    
    # 更多英文关键词 - 岩石物理
    "matrix density", "fluid density", "bulk density", "apparent density",
    "lithology identification", "mineralogy", "XRD", "X-ray diffraction",
    "core analysis", "plug analysis", "porosity measurement", "permeability measurement",
    "capillary pressure", "relative permeability", "wettability",
    
    # 更多英文关键词 - 饱和度模型
    "dual-water model", "triple-water model", "shaly sand model",
    "clay bound water", "free water", "water cut", "oil cut", "gas cut",
    "residual oil saturation", "Sor", "residual gas saturation", "Sgr",
    
    # 更多英文关键词 - 特殊测井
    "cased hole saturation logging", "pulse neutron logging", "thermal decay time",
    "TDT", "carbon oxygen logging", "C/O log", "sigma log", "neutron activation",
    "gamma ray spectroscopy", "GR spectroscopy", "spectrometry",
    
    # 更多英文关键词 - 成像测井
    "borehole imaging", "microresistivity imaging", "acoustic borehole imaging",
    "ultrasonic imaging", "borehole televiewer", "borehole wall imaging",
    "fracture detection", "dip measurement", "strike measurement",
    "bedding plane", "fault detection", "karst feature",
    
    # 更多英文关键词 - 生产测井
    "flowmeter", "spinner flowmeter", "thermal flowmeter", "optical flowmeter",
    "water holdup", "oil holdup", "gas holdup", "phase fraction",
    "temperature log", "pressure log", "noise log", "casing collar locator",
    
    # 更多中文关键词 - SPE相关
    "石油工程师学会", "SPE年会", "石油学报", "石油勘探开发", "石油地质",
    "油藏工程", "采油工程", "钻井工程", "完井工程", "提高采收率",
    "数值模拟", "试井分析", "产能预测", "储量计算", "动态分析",
    
    # 更多中文关键词 - 储层类型
    "致密油藏", "页岩油藏", "碳酸盐岩油藏", "裂缝性油藏", "溶洞型油藏",
    "低渗透油藏", "特低渗透油藏", "高含水油藏", "稠油油藏", "凝析气藏",
    
    # 更多中文关键词 - 测井新技术
    "随钻测井", "随钻测井仪", "阵列感应", "高分辨率感应", "核磁共振",
    "偶极声波", "交叉偶极", "全波列", "斯通利波", "横波测井",
    
    # 更多中文关键词 - 资料处理
    "测井标准化", "曲线校正", "深度匹配", "环境影响校正", "井眼扩大校正",
    "侵入带校正", "泥浆影响校正", "温度压力校正", "刻度检查", "质量验收",
    
    # 更多中文关键词 - 解释成果
    "测井综合图", "成果图", "解释成果表", "储层参数表", "油气层综合评价",
    "储量报告", "开发方案", "油藏描述报告", "测井专题报告", "科研报告",
    "Myanmar", "Brazil", "Peru", "Sudan", "Central Asia", "Amu Darya",
    "Karakum", "Agadem", "Muglad"
]

def is_logging_related(text):
    """检查文本是否与测井相关"""
    if not text:
        return False
    text_lower = text.lower()
    for keyword in LOGGING_KEYWORDS:
        if keyword.lower() in text_lower:
            return True
    return False

def filter_logging_content(text):
    """过滤文本，只保留与测井相关的内容段落"""
    if not text:
        return ""
    
    paragraphs = re.split(r'\n\n+', text)
    filtered_paragraphs = []
    
    for paragraph in paragraphs:
        paragraph_lower = paragraph.lower()
        has_logging_keyword = False
        for keyword in LOGGING_KEYWORDS:
            if keyword.lower() in paragraph_lower:
                has_logging_keyword = True
                break
        
        if has_logging_keyword or len(paragraph) > 300:
            filtered_paragraphs.append(paragraph)
    
    return '\n\n'.join(filtered_paragraphs)

def generate_file_hash(content):
    """生成内容哈希值，用于检测重复"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

# ------------------------------
# 中文分词器（模块级别，可序列化）
# ------------------------------
from whoosh.analysis import Tokenizer, Token

class JiebaTokenizer(Tokenizer):
    """支持中文分词的Tokenizer"""
    def __call__(self, text, **kwargs):
        words = jieba.cut(text)
        pos = 0
        for word in words:
            word = word.strip()
            if word:
                # 创建正确的 Token 对象
                token = Token()
                token.text = word
                token.pos = pos
                token.stopped = False
                pos += 1
                yield token

def get_jieba_analyzer():
    """获取中文分词Analyzer"""
    return JiebaTokenizer()

# ------------------------------
# 全文检索模块 (Whoosh)
# ------------------------------
class WhooshIndexer:
    """基于Whoosh的全文索引器，支持增量更新和优化"""
    
    def __init__(self, index_dir="index"):
        self.index_dir = index_dir
        self.lock = threading.Lock()
        
    def _create_schema(self):
        """创建Schema（延迟创建，避免序列化问题）"""
        return Schema(
            title=TEXT(stored=True),
            content=TEXT(stored=True, analyzer=get_jieba_analyzer()),
            source=ID(stored=True, unique=True),
            category=KEYWORD(stored=True, commas=True),
            timestamp=DATETIME(stored=True),
            content_hash=ID(stored=True),
            # 添加地区和井名相关字段
            well_name=TEXT(stored=True),
            region=KEYWORD(stored=True, commas=True),
            oil_field=KEYWORD(stored=True, commas=True),
            structure=TEXT(stored=True),
            depth_range=TEXT(stored=True),
            file_type=TEXT(stored=True)
        )
    
    def create_index(self):
        """创建新索引"""
        with self.lock:
            # 删除旧索引（如果存在）
            if os.path.exists(self.index_dir):
                import shutil
                attempts = 0
                max_attempts = 3
                while attempts < max_attempts:
                    try:
                        shutil.rmtree(self.index_dir)
                        break
                    except PermissionError:
                        attempts += 1
                        time.sleep(0.5)
                        if attempts == max_attempts:
                            print(f"警告: 无法删除旧索引目录，尝试跳过")
            
            if not os.path.exists(self.index_dir):
                os.makedirs(self.index_dir)
            schema = self._create_schema()
            ix = create_in(self.index_dir, schema)
        return ix
    
    def get_index(self, create=True):
        """获取索引对象"""
        if os.path.exists(self.index_dir):
            # 检查目录是否为空或索引是否存在
            if not os.listdir(self.index_dir):
                # 目录为空，创建新索引
                return self.create_index()
            try:
                return open_dir(self.index_dir)
            except Exception:
                # 索引不存在或损坏，创建新索引
                if create:
                    return self.create_index()
                return None
        elif create:
            return self.create_index()
        else:
            return None
    
    def add_document(self, title, content, source, category="", timestamp=None, content_hash=None, 
                     well_name=None, region=None, oil_field=None, structure=None, 
                     depth_range=None, file_type=None):
        """添加文档到索引（支持增量更新）"""
        ix = self.get_index()
        writer = ix.writer()
        
        # 检查是否已存在相同内容
        if content_hash:
            with ix.searcher() as searcher:
                query = QueryParser("content_hash", ix.schema).parse(content_hash)
                results = searcher.search(query)
                if results:
                    writer.delete_by_term("content_hash", content_hash)
        
        writer.add_document(
            title=title,
            content=content,
            source=source,
            category=category,
            timestamp=timestamp or datetime.now(),
            content_hash=content_hash or generate_file_hash(content),
            well_name=well_name or "",
            region=region or "",
            oil_field=oil_field or "",
            structure=structure or "",
            depth_range=depth_range or "",
            file_type=file_type or ""
        )
        writer.commit()
    
    def add_documents(self, documents, batch_size=100, skip_duplicates=True):
        """批量添加文档，支持分批提交优化性能"""
        ix = self.get_index()
        
        # 获取已存在的文档哈希值用于去重
        existing_hashes = set()
        if skip_duplicates:
            try:
                with ix.searcher() as searcher:
                    for doc in searcher.all_stored_fields():
                        if 'content_hash' in doc:
                            existing_hashes.add(doc['content_hash'])
            except Exception:
                pass
        
        total_docs = len(documents)
        added_count = 0
        
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i+batch_size]
            writer = ix.writer()
            
            for doc in batch:
                content_hash = doc.get("content_hash") or generate_file_hash(doc.get("content", ""))
                
                # 跳过重复文档
                if skip_duplicates and content_hash in existing_hashes:
                    continue
                
                writer.add_document(
                    title=doc.get("title", ""),
                    content=doc.get("content", ""),
                    source=doc.get("source", ""),
                    category=doc.get("category", ""),
                    timestamp=doc.get("timestamp", datetime.now()),
                    content_hash=content_hash,
                    well_name=doc.get("well_name", ""),
                    region=doc.get("region", ""),
                    oil_field=doc.get("oil_field", ""),
                    structure=doc.get("structure", ""),
                    depth_range=doc.get("depth_range", ""),
                    file_type=doc.get("file_type", "")
                )
                added_count += 1
                # 将新添加的哈希值加入集合，避免同一批次内重复
                existing_hashes.add(content_hash)
            
            writer.commit()  # 标准commit方式
            print(f"已索引 {min(i+batch_size, total_docs)}/{total_docs} 个文档")
        
        if added_count != total_docs and skip_duplicates:
            print(f"跳过了 {total_docs - added_count} 个重复文档")
        
        return added_count
    
    def search(self, query_str, top_n=10, min_score=0.1, region=None, well_name=None):
        """搜索文档，支持评分过滤和地区/井名筛选"""
        ix = self.get_index(create=False)
        if not ix:
            return []
        
        # 构建基础查询
        parser = MultifieldParser(["title", "content"], ix.schema)
        query = parser.parse(query_str)
        
        # 添加地区过滤
        if region:
            region_parser = QueryParser("region", ix.schema)
            region_query = region_parser.parse(region)
            query = query & region_query
        
        # 添加井名过滤
        if well_name:
            well_parser = QueryParser("well_name", ix.schema)
            well_query = well_parser.parse(well_name)
            query = query & well_query
        
        results = []
        with ix.searcher(weighting=scoring.TF_IDF()) as searcher:
            hits = searcher.search(query, limit=top_n)
            for hit in hits:
                if hit.score >= min_score:
                    results.append({
                        "title": hit["title"],
                        "content": hit["content"],
                        "source": hit["source"],
                        "category": hit["category"],
                        "timestamp": hit["timestamp"],
                        "score": hit.score,
                        "well_name": hit.get("well_name", ""),
                        "region": hit.get("region", ""),
                        "oil_field": hit.get("oil_field", ""),
                        "structure": hit.get("structure", ""),
                        "depth_range": hit.get("depth_range", ""),
                        "file_type": hit.get("file_type", "")
                    })
        return results
    
    def search_similar(self, content, top_n=5):
        """搜索相似文档，用于去重"""
        ix = self.get_index(create=False)
        if not ix:
            return []
        
        content_hash = generate_file_hash(content)
        with ix.searcher() as searcher:
            query = QueryParser("content_hash", ix.schema).parse(content_hash)
            results = searcher.search(query)
            return [hit["source"] for hit in results]
    
    def delete_document(self, source):
        """删除指定来源的文档"""
        ix = self.get_index(create=False)
        if ix:
            writer = ix.writer()
            writer.delete_by_term("source", source)
            writer.commit()
    
    def delete_old_documents(self, days_old=30):
        """删除指定天数前的旧文档"""
        cutoff_date = datetime.now() - timedelta(days=days_old)
        ix = self.get_index(create=False)
        if ix:
            writer = ix.writer()
            writer.delete_by_query(
                QueryParser("timestamp", ix.schema).parse(f"timestamp:[* TO {cutoff_date}]")
            )
            writer.commit()
    
    def clear_index(self):
        """清空索引"""
        with self.lock:
            if os.path.exists(self.index_dir):
                import shutil
                shutil.rmtree(self.index_dir)
            self.create_index()
    
    def optimize_index(self):
        """优化索引，提升查询性能"""
        ix = self.get_index(create=False)
        if ix:
            ix.optimize()
            print("索引优化完成")
    
    def get_document_count(self):
        """获取索引中文档数量"""
        ix = self.get_index(create=False)
        if ix:
            with ix.searcher() as searcher:
                return searcher.doc_count()
        return 0

# ------------------------------
# 多语言翻译模块
# ------------------------------
class Translator:
    """多语言翻译工具，支持中/英互译"""
    
    def __init__(self):
        self.supported_languages = ['zh', 'en']
    
    def translate(self, text, target_lang='zh'):
        """翻译文本到目标语言"""
        if not text:
            return text
        
        # 检测源语言
        source_lang = self._detect_language(text)
        
        # 如果已经是目标语言，直接返回
        if source_lang == target_lang:
            return text
        
        # 使用简单规则进行翻译（可扩展为调用翻译API）
        return self._simple_translate(text, source_lang, target_lang)
    
    def _detect_language(self, text):
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        
        if chinese_chars > english_chars:
            return 'zh'
        return 'en'
    
    def _simple_translate(self, text, source_lang, target_lang):
        """简单翻译（基于关键词映射）"""
        # 测井专业术语词典
        term_dict = {
            # 中文到英文
            '测井': 'logging',
            '录井': 'mud logging',
            '孔隙度': 'porosity',
            '渗透率': 'permeability',
            '电阻率': 'resistivity',
            '含水饱和度': 'water saturation',
            '泥质含量': 'shale volume',
            '阿尔奇公式': 'Archie equation',
            '自然伽马': 'gamma ray',
            '声波时差': 'sonic transit time',
            '密度': 'density',
            '中子': 'neutron',
            '油层': 'oil layer',
            '气层': 'gas layer',
            '水层': 'water layer',
            '储层': 'reservoir',
            '砂岩': 'sandstone',
            '泥岩': 'shale',
            '碳酸盐岩': 'carbonate',
            '油田': 'oil field',
            '区块': 'block',
            '构造': 'structure',
            
            # 英文到中文
            'logging': '测井',
            'mud logging': '录井',
            'porosity': '孔隙度',
            'permeability': '渗透率',
            'resistivity': '电阻率',
            'water saturation': '含水饱和度',
            'shale volume': '泥质含量',
            'Archie equation': '阿尔奇公式',
            'gamma ray': '自然伽马',
            'sonic transit time': '声波时差',
            'density': '密度',
            'neutron': '中子',
            'oil layer': '油层',
            'gas layer': '气层',
            'water layer': '水层',
            'reservoir': '储层',
            'sandstone': '砂岩',
            'shale': '泥岩',
            'carbonate': '碳酸盐岩',
            'oil field': '油田',
            'block': '区块',
            'structure': '构造'
        }
        
        # 替换术语
        result = text
        for term, translation in term_dict.items():
            if source_lang == 'zh' and target_lang == 'en':
                result = result.replace(term, translation)
            elif source_lang == 'en' and target_lang == 'zh':
                result = result.replace(term, translation)
        
        return result

# ------------------------------
# 项目/地区知识库管理器
# ------------------------------
class ProjectKnowledgeManager:
    """管理特定项目或地区的知识库"""
    
    def __init__(self, base_dir="projects"):
        self.base_dir = base_dir
        self.translator = Translator()
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
    
    def create_project(self, project_name, description="", region="", keywords=[], source_dirs=None):
        """创建新项目知识库
        
        Args:
            project_name: 项目名称
            description: 项目描述
            region: 地区/区块名称
            keywords: 关键词列表
            source_dirs: 初始导入的文件夹路径列表，可选
        
        Returns:
            项目目录路径
        """
        project_dir = os.path.join(self.base_dir, project_name)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
        
        # 创建项目配置文件
        config = {
            'name': project_name,
            'description': description,
            'region': region,
            'keywords': keywords,
            'source_dirs': source_dirs or [],
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'document_count': 0
        }
        
        with open(os.path.join(project_dir, 'project_config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 创建文档目录
        os.makedirs(os.path.join(project_dir, 'documents'), exist_ok=True)
        
        print(f"已创建项目: {project_name}")
        
        # 如果指定了初始文件夹，自动导入文档
        if source_dirs and len(source_dirs) > 0:
            total_imported = 0
            for src_dir in source_dirs:
                if os.path.exists(src_dir):
                    imported = self.import_documents(project_name, src_dir, recursive=True)
                    total_imported += imported
            print(f"已从指定文件夹导入 {total_imported} 个文档")
        
        return project_dir
    
    def import_documents(self, project_name, source_dir, recursive=True, filter_logging=True):
        """导入文档到指定项目
        
        Args:
            project_name: 项目名称
            source_dir: 源文件夹路径
            recursive: 是否递归子目录
            filter_logging: 是否只导入测井相关文档
        
        Returns:
            成功导入的文档数量
        """
        project_dir = os.path.join(self.base_dir, project_name)
        if not os.path.exists(project_dir):
            print(f"项目不存在: {project_name}")
            return 0
        
        docs_dir = os.path.join(project_dir, 'documents')
        converter = DocumentConverter()
        
        # 设置是否过滤非测井文档
        original_convert = converter.convert
        def filtered_convert(file_path, output_dir=None, check_duplicate=True):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in converter.supported_formats:
                try:
                    content = converter.supported_formats[ext](file_path)
                    if not content:
                        return None
                    # 如果启用过滤，检查是否与测井相关
                    if filter_logging and not is_logging_related(content):
                        print(f"文件 {file_path} 不包含测井相关内容，已跳过")
                        return None
                    return original_convert(file_path, output_dir, check_duplicate)
                except Exception as e:
                    print(f"转换 {file_path} 失败: {e}")
                    return None
            return None
        
        if filter_logging:
            converter.convert = filtered_convert
        
        converted_count, _ = converter.batch_convert(source_dir, docs_dir, recursive)
        
        # 翻译非中文文档
        self._translate_project_docs(project_dir)
        
        # 更新项目配置
        config_path = os.path.join(project_dir, 'project_config.yaml')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            config['document_count'] += converted_count
            config['last_updated'] = datetime.now().isoformat()
            # 添加源目录到配置
            if source_dir not in config.get('source_dirs', []):
                config['source_dirs'] = config.get('source_dirs', []) + [source_dir]
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"已向项目 {project_name} 导入 {converted_count} 个文档")
        return converted_count
    
    def crawl_for_project(self, project_name, urls, region_keywords=[], translate=True):
        """针对特定项目/地区爬取网络知识
        
        Args:
            project_name: 项目名称
            urls: 要爬取的URL列表
            region_keywords: 地区关键词，用于过滤爬取内容
            translate: 是否翻译非中文文档
        
        Returns:
            成功爬取的网页数量
        """
        project_dir = os.path.join(self.base_dir, project_name)
        if not os.path.exists(project_dir):
            print(f"项目不存在: {project_name}")
            return 0
        
        # 获取项目配置中的地区信息
        config = self.get_project_info(project_name)
        region = config.get('region', '')
        
        docs_dir = os.path.join(project_dir, 'documents')
        crawler = EnhancedCrawler()
        
        # 更新爬取配置，添加地区关键词过滤
        crawler.config['allowed_domains'] = crawler.config.get('allowed_domains', [])
        crawler.config['region_keywords'] = region_keywords + [region] if region else region_keywords
        
        crawled_count = 0
        for url in urls:
            print(f"爬取 ({region}): {url}")
            result = crawler.fetch_and_save(url, docs_dir, max_depth=2)
            if result:
                crawled_count += len(result)
        
        # 翻译非中文文档
        if translate:
            self._translate_project_docs(project_dir)
        
        # 更新项目配置
        config_path = os.path.join(project_dir, 'project_config.yaml')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            config['document_count'] += crawled_count
            config['last_updated'] = datetime.now().isoformat()
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"已为项目 {project_name} 爬取 {crawled_count} 个网页")
        return crawled_count
    
    def _translate_project_docs(self, project_dir):
        """翻译项目中的非中文文档（支持中英互译）"""
        docs_dir = os.path.join(project_dir, 'documents')
        
        if not os.path.exists(docs_dir):
            return
        
        for filename in os.listdir(docs_dir):
            # 跳过已翻译的文件
            if filename.endswith('.md') and not filename.endswith('_zh.md') and not filename.endswith('_en.md'):
                filepath = os.path.join(docs_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 检测语言并翻译
                    lang = self.translator._detect_language(content)
                    if lang == 'en':
                        translated = self.translator.translate(content, 'zh')
                        base_name = os.path.splitext(filename)[0]
                        translated_path = os.path.join(docs_dir, f"{base_name}_zh.md")
                        with open(translated_path, 'w', encoding='utf-8') as f:
                            f.write(translated)
                        print(f"已翻译为中文: {filename}")
                    elif lang == 'zh':
                        translated = self.translator.translate(content, 'en')
                        base_name = os.path.splitext(filename)[0]
                        translated_path = os.path.join(docs_dir, f"{base_name}_en.md")
                        with open(translated_path, 'w', encoding='utf-8') as f:
                            f.write(translated)
                        print(f"已翻译为英文: {filename}")
                except Exception as e:
                    print(f"翻译 {filename} 失败: {e}")
    
    def get_project_info(self, project_name):
        """获取项目信息"""
        project_dir = os.path.join(self.base_dir, project_name)
        config_path = os.path.join(project_dir, 'project_config.yaml')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return None
    
    def list_projects(self):
        """列出所有项目"""
        projects = []
        if os.path.exists(self.base_dir):
            for name in os.listdir(self.base_dir):
                path = os.path.join(self.base_dir, name)
                if os.path.isdir(path):
                    info = self.get_project_info(name)
                    if info:
                        projects.append(info)
        return projects
    
    def build_project_index(self, project_name):
        """为项目构建独立索引"""
        project_dir = os.path.join(self.base_dir, project_name)
        if not os.path.exists(project_dir):
            print(f"项目不存在: {project_name}")
            return 0
        
        docs_dir = os.path.join(project_dir, 'documents')
        index_dir = os.path.join(project_dir, 'index')
        
        indexer = WhooshIndexer(index_dir)
        loader = MarkdownLoader(docs_dir)
        
        docs = loader.load_all()
        if docs:
            indexer.add_documents(docs)
            print(f"已为项目 {project_name} 构建索引，共 {len(docs)} 个文档")
            return len(docs)
        
        return 0
    
    def search_project(self, project_name, query, top_n=10):
        """搜索项目知识库"""
        project_dir = os.path.join(self.base_dir, project_name)
        if not os.path.exists(project_dir):
            print(f"项目不存在: {project_name}")
            return []
        
        index_dir = os.path.join(project_dir, 'index')
        indexer = WhooshIndexer(index_dir)
        
        # 如果项目索引不存在，先构建
        if not os.path.exists(index_dir) or not os.listdir(index_dir):
            self.build_project_index(project_name)
        
        return indexer.search(query, top_n=top_n)
    
    def update_project(self, project_name, crawl_urls=None, reimport=False):
        """更新项目知识库
        
        Args:
            project_name: 项目名称
            crawl_urls: 要爬取的URL列表，如果为None则使用默认更新源
            reimport: 是否重新导入源目录中的文档
        
        Returns:
            更新的文档数量
        """
        updated_count = 0
        
        # 如果需要重新导入
        if reimport:
            config = self.get_project_info(project_name)
            if config and 'source_dirs' in config:
                for src_dir in config['source_dirs']:
                    if os.path.exists(src_dir):
                        updated_count += self.import_documents(project_name, src_dir, recursive=True)
        
        # 如果需要爬取
        if crawl_urls is not None:
            updated_count += self.crawl_for_project(project_name, crawl_urls)
        
        # 更新索引
        self.build_project_index(project_name)
        
        return updated_count
    
    def delete_project(self, project_name):
        """删除项目"""
        import shutil
        project_dir = os.path.join(self.base_dir, project_name)
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
            print(f"已删除项目: {project_name}")
            return True
        return False

# ------------------------------
# 测井数据文件解析模块
# ------------------------------
class WellLogDataParser:
    """解析测井数据文件，提取井信息并生成知识条目"""
    
    def __init__(self):
        self.supported_formats = {
            '.las': self._parse_las,
            '.dlis': self._parse_dlis,
            '.csv': self._parse_csv,
            '.xlsx': self._parse_excel,
            '.xls': self._parse_excel
        }
    
    def parse_file(self, file_path):
        """解析测井数据文件"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext not in self.supported_formats:
            return None
        
        try:
            return self.supported_formats[ext](file_path)
        except Exception as e:
            print(f"解析 {file_path} 失败: {e}")
            return None
    
    def batch_parse(self, input_dir, output_dir="data/local", recursive=True):
        """批量解析测井数据文件"""
        parsed_count = 0
        
        if not os.path.exists(input_dir):
            return parsed_count
        
        for root, dirs, files in os.walk(input_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                if ext in self.supported_formats:
                    well_info = self.parse_file(file_path)
                    if well_info:
                        self._save_as_markdown(well_info, file_path, output_dir)
                        parsed_count += 1
            
            if not recursive:
                break
        
        print(f"已解析 {parsed_count} 个测井数据文件")
        return parsed_count
    
    def _parse_las(self, file_path):
        """解析LAS文件"""
        try:
            import lasio
            las = lasio.read(file_path)
            
            info = {
                'type': 'well_data',
                'well_name': las.well.WELL.value if hasattr(las.well, 'WELL') else os.path.basename(file_path),
                'field': las.well.FIELD.value if hasattr(las.well, 'FIELD') else '',
                'location': las.well.LOC.value if hasattr(las.well, 'LOC') else '',
                'country': las.well.COUNTRY.value if hasattr(las.well, 'COUNTRY') else '',
                'province': las.well.PROVINCE.value if hasattr(las.well, 'PROVINCE') else '',
                'uom': las.well.UOM.value if hasattr(las.well, 'UOM') else '',
                'start_depth': las.well.STRT.value if hasattr(las.well, 'STRT') else '',
                'stop_depth': las.well.STOP.value if hasattr(las.well, 'STOP') else '',
                'step': las.well.STEP.value if hasattr(las.well, 'STEP') else '',
                'curves': [str(c) for c in las.curves],
                'params': dict(las.params) if hasattr(las, 'params') else {},
                'source_file': file_path
            }
            return info
        except ImportError:
            print("需要安装 lasio: pip install lasio")
            return None
        except Exception as e:
            print(f"LAS解析错误: {e}")
            return None
    
    def _parse_dlis(self, file_path):
        """解析DLIS文件"""
        try:
            import dlisio
            with dlisio.load(file_path) as f:
                info = {
                    'type': 'well_data',
                    'well_name': os.path.basename(file_path),
                    'field': '',
                    'location': '',
                    'curves': [],
                    'source_file': file_path
                }
                
                for frame in f.frames:
                    info['curves'].extend(frame.curves)
                
                return info
        except ImportError:
            print("需要安装 dlisio: pip install dlisio")
            return None
        except Exception as e:
            print(f"DLIS解析错误: {e}")
            return None
    
    def _parse_csv(self, file_path):
        """解析CSV文件"""
        try:
            import pandas as pd
            df = pd.read_csv(file_path)
            
            info = {
                'type': 'well_data',
                'well_name': os.path.basename(file_path).replace('.csv', ''),
                'field': '',
                'location': '',
                'curves': list(df.columns),
                'row_count': len(df),
                'source_file': file_path
            }
            
            # 尝试从文件名提取井名信息
            name_parts = os.path.basename(file_path).replace('.csv', '').split('_')
            if len(name_parts) > 0:
                info['well_name'] = name_parts[0]
                if len(name_parts) > 1:
                    info['field'] = '_'.join(name_parts[1:])
            
            return info
        except Exception as e:
            print(f"CSV解析错误: {e}")
            return None
    
    def _parse_excel(self, file_path):
        """解析Excel文件"""
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            
            info = {
                'type': 'well_data',
                'well_name': os.path.basename(file_path).replace('.xlsx', '').replace('.xls', ''),
                'field': '',
                'location': '',
                'curves': list(df.columns),
                'row_count': len(df),
                'source_file': file_path
            }
            
            return info
        except Exception as e:
            print(f"Excel解析错误: {e}")
            return None
    
    def _save_as_markdown(self, well_info, source_file, output_dir):
        """将井信息保存为Markdown"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        title = f"测井数据 - {well_info['well_name']}"
        filename = f"well_data_{well_info['well_name']}.md".replace('/', '_').replace('\\', '_')
        filepath = os.path.join(output_dir, filename)
        
        content = f"""# {well_info['well_name']}

## 基本信息

| 属性 | 值 |
|------|------|
| 井名 | {well_info.get('well_name', '')} |
| 油田/区块 | {well_info.get('field', '')} |
| 位置 | {well_info.get('location', '')} |
| 国家 | {well_info.get('country', '')} |
| 省份 | {well_info.get('province', '')} |

## 测量信息

| 属性 | 值 |
|------|------|
| 起始深度 | {well_info.get('start_depth', '')} |
| 结束深度 | {well_info.get('stop_depth', '')} |
| 采样间隔 | {well_info.get('step', '')} |
| 单位 | {well_info.get('uom', '')} |

## 测井曲线

{', '.join(well_info.get('curves', []))}

## 数据来源

- **文件**: {source_file}
- **记录数**: {well_info.get('row_count', '未知')}

---

*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        import frontmatter
        post = frontmatter.Post(content)
        post["title"] = title
        post["category"] = "well_data"
        post["date"] = datetime.now()
        post["well_name"] = well_info['well_name']
        post["field"] = well_info.get('field', '')
        post["source_file"] = source_file
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
        
        print(f"已生成: {filepath}")

# ------------------------------
# 文档转换模块（支持多种格式转Markdown）
# ------------------------------
class DocumentConverter:
    """文档格式转换器，支持PPT/DOC/PDF转Markdown"""
    
    def __init__(self):
        self.supported_formats = {
            # 文档格式
            '.ppt': self._convert_ppt,
            '.pptx': self._convert_ppt,
            '.doc': self._convert_doc,
            '.docx': self._convert_docx,
            '.pdf': self._convert_pdf,
            '.txt': self._convert_txt,
            '.md': self._convert_md,
            # 表格格式
            '.xls': self._convert_excel,
            '.xlsx': self._convert_excel,
            '.csv': self._convert_csv,
            # 网页格式
            '.html': self._convert_html,
            '.htm': self._convert_html,
            # 数据格式
            '.json': self._convert_json,
            '.xml': self._convert_xml,
            # 图片格式（OCR）
            '.png': self._convert_image,
            '.jpg': self._convert_image,
            '.jpeg': self._convert_image,
            '.bmp': self._convert_image,
            '.tiff': self._convert_image,
            '.tif': self._convert_image,
            '.gif': self._convert_image
        }
        self.existing_hashes = set()  # 用于去重的内容哈希集合
        self.scan_history = {}  # 记录已扫描文件的时间戳
        self.ocr_enabled = self._check_ocr_available()
        self.location_extractor = WellLocationExtractor()  # 地区和井名提取器
        self.region_detector = RegionDetector()  # 地区地质特征自动检测器
        # 初始化增强型解析流水线
        if DOC_PIPELINE_AVAILABLE:
            self.parser_pipeline = DocumentParserPipeline()
        else:
            self.parser_pipeline = None
        # 初始化多语言翻译器
        if ML_TRANSLATOR_AVAILABLE:
            self.translator = MultiLanguageTranslator()
        else:
            self.translator = Translator()
    
    def _load_existing_hashes(self, output_dir):
        """加载已存在文件的哈希值，用于去重"""
        if not os.path.exists(output_dir):
            return
        
        for filename in os.listdir(output_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(output_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        content_hash = generate_file_hash(content)
                        self.existing_hashes.add(content_hash)
                except:
                    pass
    
    def _chunk_document(self, content, chunk_size=3000, overlap=300):
        """将大文档分割为重叠的文本块，提高搜索精度"""
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        start = 0
        while start < len(content):
            end = start + chunk_size
            # 尽量在段落边界处分割
            if end < len(content):
                last_para = content[start:end].rfind('\n\n')
                if last_para > chunk_size // 2:
                    end = start + last_para
            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap
            if start >= len(content):
                break
        return chunks if chunks else [content]
    
    def convert(self, file_path, output_dir=None, check_duplicate=True, verbose=False):
        """转换文档为Markdown"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext not in self.supported_formats:
            if verbose:
                print(f"不支持的格式: {ext}")
            return None
        
        try:
            content = self.supported_formats[ext](file_path)
            if not content or not is_logging_related(content):
                # 不显示非测井内容的跳过信息，保持界面简洁
                return None
            
            # 去重检查
            content_hash = generate_file_hash(content)
            if check_duplicate and content_hash in self.existing_hashes:
                # 不显示重复内容的跳过信息，保持界面简洁
                return None
            
            # 生成输出路径
            if output_dir is None:
                output_dir = "data/local"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 记录哈希值
            self.existing_hashes.add(content_hash)
            
            filename = os.path.basename(file_path)
            
            # 从文件名提取地区和井名信息
            location_info = self.location_extractor.extract_from_path(file_path)
            
            # 自动检测地区地质特征（从文件内容 + LAS数据）
            region_detection = None
            ext_lower = ext.lower()
            # 如果是LAS/CSV/XLSX数据文件，尝试从曲线统计检测
            if ext_lower in ['.las', '.csv', '.xlsx', '.xls']:
                region_detection = self.region_detector.detect_from_file(file_path)
            # 同时从文本内容中检测（补充文本模式匹配）
            text_detection = self.region_detector.detect_from_text(content)
            # 合并两种检测结果
            if region_detection is None and text_detection and text_detection.get('matched_signatures'):
                region_detection = text_detection
            elif region_detection and text_detection and text_detection.get('matched_signatures'):
                # 合并tags和knowledge
                existing_tags = set(region_detection.get('detected_tags', []))
                region_detection['detected_tags'] = list(existing_tags | set(text_detection.get('detected_tags', [])))
                existing_kb = set(region_detection.get('linked_knowledge', []))
                region_detection['linked_knowledge'] = list(existing_kb | set(text_detection.get('linked_knowledge', [])))
            
            # 将检测到的地区信息合并到location_info
            if region_detection and region_detection.get('matched_signatures'):
                detected_tags = region_detection.get('detected_tags', [])
                linked_kb = region_detection.get('linked_knowledge', [])
                # 如果文件名没有提取到地区，用检测结果补充
                if not location_info.get('region') and detected_tags:
                    location_info['region'] = ', '.join(detected_tags[:3])
                if not location_info.get('oil_field') and detected_tags:
                    location_info['detected_region_type'] = region_detection['matched_signatures'][0]['name'] if region_detection['matched_signatures'] else ''
                if linked_kb:
                    location_info['linked_knowledge'] = linked_kb
            
            # 对大文档进行分块处理
            chunks = self._chunk_document(content)
            base_name = os.path.splitext(filename)[0]
            saved_paths = []
            
            for chunk_idx, chunk_content in enumerate(chunks):
                if len(chunks) == 1:
                    md_filename = base_name + ".md"
                else:
                    md_filename = f"{base_name}_chunk_{chunk_idx+1}.md"
                md_path = os.path.join(output_dir, md_filename)
                
                import frontmatter
                post = frontmatter.Post(chunk_content)
                post["title"] = base_name if len(chunks) == 1 else f"{base_name} (第{chunk_idx+1}部分)"
                post["category"] = "local"
                post["date"] = datetime.now()
                post["source_file"] = file_path
                post["content_hash"] = generate_file_hash(chunk_content)
                if len(chunks) > 1:
                    post["chunk_index"] = chunk_idx + 1
                    post["chunk_total"] = len(chunks)
                
                if location_info.get('extracted_well_name'):
                    post["well_name"] = location_info['extracted_well_name']
                if location_info.get('region'):
                    post["region"] = location_info['region']
                if location_info.get('oil_field'):
                    post["oil_field"] = location_info['oil_field']
                if location_info.get('structure'):
                    post["structure"] = location_info['structure']
                if location_info.get('depth_range'):
                    post["depth_range"] = location_info['depth_range']
                if location_info.get('file_type'):
                    post["file_type"] = location_info['file_type']
                if location_info.get('country'):
                    post["country"] = location_info['country']
                if location_info.get('logging_programs'):
                    post["logging_programs"] = ', '.join(location_info['logging_programs'])
                if location_info.get('well_test_info'):
                    post["well_test_info"] = location_info['well_test_info']
                # 自动检测的地区地质特征
                if location_info.get('detected_region_type'):
                    post["detected_region_type"] = location_info['detected_region_type']
                if location_info.get('linked_knowledge'):
                    post["linked_knowledge"] = ', '.join(location_info['linked_knowledge'])
                if region_detection and region_detection.get('matched_signatures'):
                    post["auto_detected"] = True
                    post["detection_confidence"] = region_detection.get('confidence', 0)
                
                
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(frontmatter.dumps(post))
                saved_paths.append(md_path)
            
            return saved_paths[0] if len(saved_paths) == 1 else saved_paths
            
        except Exception:
            return None
    
    def batch_convert(self, input_dir, output_dir=None, recursive=True):
        """批量转换目录中的文档"""
        converted_count = 0
        skipped_count = 0
        
        if not os.path.exists(input_dir):
            print(f"目录不存在: {input_dir}")
            return converted_count, skipped_count
        
        # 加载已存在文件的哈希值用于去重
        if output_dir is None:
            output_dir = "data/local"
        self._load_existing_hashes(output_dir)
        
        for root, dirs, files in os.walk(input_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                if ext in self.supported_formats:
                    result = self.convert(file_path, output_dir)
                    if result:
                        converted_count += 1
                    else:
                        skipped_count += 1
            
            if not recursive:
                break
        
        return converted_count, skipped_count
    
    def _convert_ppt(self, file_path):
        """转换PPT/PPTX为Markdown（文本形状 + 图片RapidOCR）"""
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(file_path)
        content = []

        def _ocr_img_bytes(img_bytes, idx):
            """对图片字节做 RapidOCR 识别，失败回退 pytesseract"""
            try:
                from PIL import Image
                import io, os, tempfile
                im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                tmp = os.path.join(tempfile.gettempdir(), f"_ppt_ocr_{os.getpid()}_{idx}.png")
                im.save(tmp, 'PNG')
                try:
                    from rapidocr import RapidOCR
                    res = RapidOCR()(tmp)
                    texts = list(getattr(res, 'txts', None) or [])
                    return '\n'.join(' '.join(str(t).split()) for t in texts) if texts else ""
                except Exception:
                    import pytesseract
                    try:
                        import kb_document_parser as _kbp
                        _kbp._setup_tesseract_path()
                    except Exception:
                        pass
                    return pytesseract.image_to_string(im, lang='chi_sim+eng').strip()
                finally:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
            except Exception:
                return ""

        img_idx = 0
        for slide in prs.slides:
            slide_parts = []
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    slide_parts.append(shape.text)
                elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE or (hasattr(shape, 'image')):
                    try:
                        img_bytes = shape.image.blob
                        ocr_text = _ocr_img_bytes(img_bytes, img_idx)
                        img_idx += 1
                        if ocr_text and len(ocr_text.strip()) > 5:
                            slide_parts.append(f"[图片OCR]\n{ocr_text.strip()}")
                    except Exception:
                        continue
            if slide_parts:
                content.append('\n'.join(slide_parts))

        return '\n\n'.join(content)
    
    def _convert_doc(self, file_path):
        """转换DOC为Markdown"""
        # 使用textract或其他工具
        try:
            import textract
            text = textract.process(file_path).decode('utf-8')
            return text.strip()
        except:
            # 备用方法
            return self._convert_docx_fallback(file_path)
    
    def _convert_docx(self, file_path):
        """转换DOCX为Markdown"""
        from docx import Document
        
        doc = Document(file_path)
        content = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                content.append(para.text)
        
        # 添加表格内容
        for table in doc.tables:
            for row in table.rows:
                row_text = "| " + " | ".join(cell.text.strip() for cell in row.cells) + " |"
                content.append(row_text)
        
        return '\n\n'.join(content)
    
    def _convert_docx_fallback(self, file_path):
        """DOC转换备用方法"""
        try:
            import subprocess
            result = subprocess.run(
                ['antiword', file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout.strip()
        except:
            return ""
    
    def _extract_pdf_tables(self, page, page_num):
        """从pdfplumber页面提取表格并格式化为Markdown"""
        try:
            tables = page.extract_tables()
            if not tables:
                return ""
            parts = []
            for t_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                header = table[0]
                parts.append(f"\n**表格 {t_idx+1} (第{page_num}页)**\n")
                parts.append("| " + " | ".join(str(c or "") for c in header) + " |")
                parts.append("| " + " | ".join("---" for _ in header) + " |")
                for row in table[1:]:
                    parts.append("| " + " | ".join(str(c or "") for c in row) + " |")
                parts.append("")
            return '\n'.join(parts)
        except Exception:
            return ""
    
    def _convert_pdf(self, file_path, timeout=300):
        """转换PDF为Markdown：多级智能回退管道
        
        回退优先级:
        1. DocumentParserPipeline (外部管道，内部编排docling/mineru/pdfplumber/paddleOCR)
        2. Docling 直接转换 (高质量结构化解析)
        3. MinerU 直接转换 (复杂PDF专业解析)
        4. pdfplumber + liteparse (传统文本提取+表格)
        5. PaddleOCR (多语言OCR：中/英/西/俄/葡)
        6. pytesseract (回退OCR)
        """
        # 级别1: 增强流水线（若可用）
        if self.parser_pipeline:
            try:
                result = self.parser_pipeline.parse_pdf(file_path, timeout=timeout)
                if result['success'] and len(result['content'].strip()) > 100:
                    filtered = self._filter_logging_content(result['content'])
                    return filtered
            except Exception:
                pass
        
        # 级别2: Docling 直接转换
        if DOCLING_AVAILABLE:
            try:
                converter = DoclingConverter()
                doc_result = converter.convert(file_path)
                if doc_result and hasattr(doc_result, 'document'):
                    doc = doc_result.document
                    content = doc.export_to_markdown() if hasattr(doc, 'export_to_markdown') else str(doc)
                    if content and len(content.strip()) > 100:
                        filtered = self._filter_logging_content(content)
                        return filtered
            except Exception:
                pass
        
        # 级别3: MinerU 直接转换（复杂PDF）
        if MINERU_AVAILABLE:
            try:
                content = self._convert_with_mineru(file_path)
                if content and len(content.strip()) > 100:
                    filtered = self._filter_logging_content(content)
                    return filtered
            except Exception:
                pass
        
        # 级别4: 传统文本提取（liteparse + pdfplumber）
        import pdfplumber
        import threading
        
        result = {'success': False, 'content': "", 'method': ""}
        
        def legacy_worker():
            try:
                content_parts = []
                if LITEPARSE_AVAILABLE:
                    try:
                        parser = PDFParser()
                        pdf_content = parser.parse(file_path)
                        if pdf_content and len(pdf_content.strip()) > 50:
                            pages = pdf_content.split(chr(12))
                            for i, page_text in enumerate(pages):
                                if page_text and len(page_text.strip()) > 50:
                                    content_parts.append(f"--- 第 {i+1} 页 ---\n{page_text.strip()}")
                            result['method'] = "liteparse"
                        else:
                            raise Exception("Empty liteparse output")
                    except Exception:
                        content_parts = []
                        with pdfplumber.open(file_path) as pdf:
                            for i, page in enumerate(pdf.pages):
                                text = page.extract_text()
                                if text and len(text.strip()) > 50:
                                    content_parts.append(f"--- 第 {i+1} 页 ---\n{text}")
                                table_text = self._extract_pdf_tables(page, i+1)
                                if table_text:
                                    content_parts.append(table_text)
                        result['method'] = "pdfplumber"
                else:
                    with pdfplumber.open(file_path) as pdf:
                        for i, page in enumerate(pdf.pages):
                            text = page.extract_text()
                            if text and len(text.strip()) > 50:
                                content_parts.append(f"--- 第 {i+1} 页 ---\n{text}")
                            table_text = self._extract_pdf_tables(page, i+1)
                            if table_text:
                                content_parts.append(table_text)
                    result['method'] = "pdfplumber"
                
                result['content'] = '\n\n'.join(content_parts)
                result['success'] = True
            except Exception:
                result['success'] = False
        
        thread = threading.Thread(target=legacy_worker)
        thread.daemon = True
        thread.start()
        thread.join(timeout=min(timeout, 180))
        
        if thread.is_alive():
            result['success'] = False
        
        # 级别5: 如果传统方法结果太少，尝试PaddleOCR（多语言）
        text_content = result.get('content', '') if result['success'] else ''
        if len(text_content.strip()) < 200:
            ocr_content = self._convert_with_paddleocr(file_path)
            if ocr_content and len(ocr_content.strip()) > len(text_content.strip()):
                return self._filter_logging_content(ocr_content)
            
            # 级别6: pytesseract OCR（回退）
            if self.ocr_enabled:
                ocr_content = self._convert_scanned_pdf(file_path, max_pages=0)
                if ocr_content and len(ocr_content.strip()) > 50:
                    return self._filter_logging_content(ocr_content)
        
        if result['success']:
            return self._filter_logging_content(result['content'])
        return ""
    
    def _convert_with_mineru(self, file_path):
        """使用MinerU解析复杂PDF（表格、公式、多栏布局）"""
        try:
            from magic_pdf.data.data_reader_writer import FileBasedDataWriter
            from magic_pdf.pipe.UNIPipe import UNIPipe
            
            import tempfile
            output_dir = tempfile.mkdtemp(prefix='mineru_')
            image_writer = FileBasedDataWriter(output_dir)
            
            pipe = UNIPipe(file_path, image_writer)
            pipe.pipe_classify()
            pipe.pipe_parse()
            
            # 收集所有页面的markdown内容
            import glob
            md_files = sorted(glob.glob(os.path.join(output_dir, '*.md')))
            content_parts = []
            for i, md_file in enumerate(md_files):
                with open(md_file, 'r', encoding='utf-8') as f:
                    md_content = f.read()
                if md_content.strip():
                    content_parts.append(f"--- 第 {i+1} 页 ---\n{md_content}")
            
            return '\n\n'.join(content_parts) if content_parts else ""
        except Exception:
            return ""
    
    def _convert_with_paddleocr(self, file_path):
        """使用PaddleOCR进行多语言OCR识别（中/英/西/俄/葡）"""
        if not PADDLEOCR_AVAILABLE:
            return ""
        
        try:
            from pdf2image import convert_from_path
            from paddleocr import PaddleOCR
            
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',  # 中文模型包含英文
                use_gpu=False,
                show_log=False
            )
            
            images = convert_from_path(file_path, first_page=1, last_page=50, dpi=300)
            content_parts = []
            
            for i, image in enumerate(images):
                import numpy as np
                img_array = np.array(image)
                results = ocr.ocr(img_array, cls=True)
                
                if results and results[0]:
                    page_text = []
                    for line in results[0]:
                        if line and len(line) >= 2:
                            text = line[1][0]
                            if text and len(text.strip()) > 1:
                                page_text.append(text)
                    if page_text:
                        content_parts.append(f"--- 第 {i+1} 页 (PaddleOCR) ---\n" + '\n'.join(page_text))
            
            return '\n\n'.join(content_parts) if content_parts else ""
        except Exception:
            return ""
    def _convert_txt(self, file_path):
        """转换TXT为Markdown"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _convert_md(self, file_path):
        """复制Markdown文件"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _check_ocr_available(self):
        """检查OCR是否可用"""
        try:
            import pytesseract
            from pdf2image import convert_from_path
            return True
        except ImportError:
            return False
    
    def _convert_scanned_pdf(self, file_path, max_pages=0):
        """OCR识别扫描PDF页面（多语言：中/英/西/俄/葡）
        
        Args:
            max_pages: 最大页数限制，0=无限制
        """
        # 优先使用PaddleOCR（多语言支持更好）
        if PADDLEOCR_AVAILABLE:
            try:
                from pdf2image import convert_from_path
                from paddleocr import PaddleOCR
                
                ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False, show_log=False)
                
                images = convert_from_path(file_path, first_page=1, 
                                          last_page=max_pages if max_pages > 0 else None, 
                                          dpi=300)
                content_parts = []
                for i, image in enumerate(images):
                    import numpy as np
                    img_array = np.array(image)
                    results = ocr.ocr(img_array, cls=True)
                    if results and results[0]:
                        page_text = []
                        for line in results[0]:
                            if line and len(line) >= 2:
                                text = line[1][0]
                                if text and len(text.strip()) > 1:
                                    page_text.append(text)
                        if page_text:
                            content_parts.append(f"--- 第 {i+1} 页 (PaddleOCR) ---\n" + '\n'.join(page_text))
                return '\n\n'.join(content_parts) if content_parts else ""
            except Exception:
                pass
        
        # 回退到pytesseract
        try:
            import pytesseract
            from pdf2image import convert_from_path
            
            images = convert_from_path(file_path, first_page=1, 
                                      last_page=max_pages if max_pages > 0 else None, 
                                      dpi=300)
            content_parts = []
            for i, image in enumerate(images):
                # 多语言OCR配置
                text = pytesseract.image_to_string(image, lang='chi_sim+eng+spa+rus+por')
                if text and len(text.strip()) > 20:
                    content_parts.append(f"--- 第 {i+1} 页 (OCR) ---\n{text.strip()}")
            return '\n\n'.join(content_parts)
        except ImportError:
            print("OCR依赖未安装(pytesseract/pdf2image)")
            return ""
        except Exception as e:
            print(f"OCR识别失败: {e}")
            return ""
    
    def _filter_logging_content(self, text):
        """过滤非测井相关内容（委托给模块级函数）"""
        return filter_logging_content(text)
    
    def _convert_image(self, file_path):
        """使用OCR识别图片中的文字（多语言：中/英/西/俄/葡）"""
        if not self.ocr_enabled:
            return ""
        
        # 优先使用PaddleOCR
        if PADDLEOCR_AVAILABLE:
            try:
                from paddleocr import PaddleOCR
                from PIL import Image
                import numpy as np
                
                ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False, show_log=False)
                img = Image.open(file_path)
                img_array = np.array(img)
                results = ocr.ocr(img_array, cls=True)
                
                if results and results[0]:
                    text_lines = []
                    for line in results[0]:
                        if line and len(line) >= 2:
                            text = line[1][0]
                            if text and len(text.strip()) > 1:
                                text_lines.append(text)
                    return '\n'.join(text_lines)
            except Exception:
                pass
        
        # 回退到pytesseract
        try:
            import pytesseract
            from PIL import Image
            
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang='chi_sim+eng+spa+rus+por')
            return text.strip()
        except Exception:
            return ""
    
    def _convert_excel(self, file_path):
        """转换Excel文件为Markdown"""
        try:
            import pandas as pd
            
            df = pd.read_excel(file_path, sheet_name=None)
            content = []
            
            for sheet_name, sheet_data in df.items():
                content.append(f"## {sheet_name}")
                content.append(sheet_data.to_markdown(index=False))
            
            return '\n\n'.join(content)
        except Exception:
            return ""
    
    def _convert_csv(self, file_path):
        """转换CSV文件为Markdown"""
        try:
            import pandas as pd
            
            df = pd.read_csv(file_path, low_memory=False)
            return df.to_markdown(index=False)
        except Exception:
            return ""
    
    def _convert_html(self, file_path):
        """转换HTML文件为Markdown"""
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            
            # 提取文本内容
            content = []
            for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'li', 'table']):
                if tag.name == 'h1':
                    content.append(f"# {tag.get_text(strip=True)}")
                elif tag.name == 'h2':
                    content.append(f"## {tag.get_text(strip=True)}")
                elif tag.name == 'h3':
                    content.append(f"### {tag.get_text(strip=True)}")
                elif tag.name == 'p':
                    content.append(tag.get_text(strip=True))
                elif tag.name == 'li':
                    content.append(f"- {tag.get_text(strip=True)}")
                elif tag.name == 'table':
                    # 简单转换表格
                    rows = []
                    for tr in tag.find_all('tr'):
                        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        rows.append('| ' + ' | '.join(cells) + ' |')
                    content.append('\n'.join(rows))
            
            return '\n\n'.join(content)
        except Exception:
            return ""
    
    def _convert_json(self, file_path):
        """转换JSON文件为Markdown"""
        try:
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换为格式化的JSON字符串
            return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"
        except Exception:
            return ""
    
    def _convert_xml(self, file_path):
        """转换XML文件为Markdown"""
        try:
            import xml.dom.minidom
            
            with open(file_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            
            dom = xml.dom.minidom.parseString(xml_content)
            return "```xml\n" + dom.toprettyxml(indent="  ") + "\n```"
        except Exception:
            return ""

# ------------------------------
# 文档加载模块
# ------------------------------
class MarkdownLoader:
    """加载本地Markdown文档，支持缓存和增量加载"""
    
    def __init__(self, local_dir="data/local"):
        self.local_dir = local_dir
        self.cache = {}
        self.cache_updated = False
        
    def load_all(self, use_cache=True):
        """加载所有本地Markdown文档"""
        if use_cache and self.cache and not self.cache_updated:
            return list(self.cache.values())
        
        documents = []
        if not os.path.exists(self.local_dir):
            return documents
        
        for filename in os.listdir(self.local_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(self.local_dir, filename)
                doc = self._load_file(filepath)
                if doc:
                    documents.append(doc)
        
        self.cache = {doc["source"]: doc for doc in documents}
        self.cache_updated = False
        return documents
    
    def _load_file(self, filepath):
        """加载单个Markdown文件"""
        try:
            import frontmatter
            post = frontmatter.load(filepath)
            
            title = post.get("title", os.path.basename(filepath))
            content = filter_logging_content(post.content)
            
            if not content:
                return None
            
            return {
                "title": title,
                "content": content,
                "source": filepath,
                "category": post.get("category", "local"),
                "timestamp": post.get("date", datetime.now()),
                "content_hash": generate_file_hash(content),
                # 添加从文件名提取的地区和井名信息
                "well_name": post.get("well_name", ""),
                "region": post.get("region", ""),
                "oil_field": post.get("oil_field", ""),
                "structure": post.get("structure", ""),
                "depth_range": post.get("depth_range", ""),
                "file_type": post.get("file_type", "")
            }
        except Exception as e:
            print(f"加载文件 {filepath} 失败: {e}")
            return None
    
    def add_document(self, content, title, category="local"):
        """添加新的Markdown文档"""
        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir)
        
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = os.path.join(self.local_dir, filename)
        
        import frontmatter
        post = frontmatter.Post(content)
        post["title"] = title
        post["category"] = category
        post["date"] = datetime.now()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
        
        self.cache_updated = True
        return filepath
    
    def get_file_modified_time(self, filepath):
        """获取文件修改时间"""
        if os.path.exists(filepath):
            return datetime.fromtimestamp(os.path.getmtime(filepath))
        return None
    
    def has_new_files(self, last_check_time):
        """检查是否有新文件或修改过的文件"""
        if not os.path.exists(self.local_dir):
            return False
        
        for filename in os.listdir(self.local_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(self.local_dir, filename)
                mtime = self.get_file_modified_time(filepath)
                if mtime and mtime > last_check_time:
                    return True
        return False

# ------------------------------
# 网页爬虫模块（增强版）
# ------------------------------
class EnhancedCrawler:
    """增强版网页爬虫，支持多线程、URL过滤、增量爬取"""
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG["crawler"]
        
        # 在创建Session之前先处理代理环境变量
        if not self.config.get("proxy_enabled", False):
            os.environ.pop('http_proxy', None)
            os.environ.pop('https_proxy', None)
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
        
        self.session = requests.Session()
        
        # 添加更多User-Agent轮换
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/119.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        self.current_agent_index = 0
        
        # 初始化session配置，添加完整的浏览器特征
        self._init_session()
        
        self.visited = set()
        self.crawled_count = 0
        self.lock = threading.Lock()
        self.start_time = None
        self.results = []
        self.retry_count = 3  # 重试次数
        
        # 速率限制：每个域名的请求时间间隔
        self.domain_last_request = {}
        self.domain_min_interval = 2.0  # 同域名最小间隔秒数
    
    def _init_session(self):
        """初始化Session配置，添加完整的浏览器特征"""
        headers = {
            "User-Agent": self.user_agents[self.current_agent_index],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }
        self.session.headers.update(headers)
        # 添加cookie以模拟已访问状态
        self.session.cookies.update({
            "BAIDUID": "test_cookie_value",
            "BDUSS": "test_bduss_value"
        })
        
        # 配置代理
        if self.config.get("proxy_enabled", False):
            proxies = {}
            proxy_http = self.config.get("proxy_http", "")
            proxy_port = self.config.get("proxy_port", "")
            proxy_user = self.config.get("proxy_user", "")
            proxy_pass = self.config.get("proxy_pass", "")
            
            # 处理proxy_http的不同格式
            if proxy_http:
                # 如果已经是完整的URL（包含http://），直接使用
                if proxy_http.startswith("http://"):
                    base_url = proxy_http
                else:
                    # 如果只是主机名，需要构建完整URL
                    if proxy_port:
                        base_url = f"http://{proxy_http}:{proxy_port}"
                    else:
                        base_url = f"http://{proxy_http}"
                
                # 如果有认证信息，添加到代理URL中
                if proxy_user and proxy_pass:
                    # 解析基础URL，添加认证信息
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(base_url)
                    # 添加认证信息: http://user:pass@host:port
                    auth_url = urlunparse((parsed.scheme, f"{proxy_user}:{proxy_pass}@{parsed.netloc}", parsed.path, parsed.params, parsed.query, parsed.fragment))
                    proxies["http"] = auth_url
                    proxies["https"] = auth_url
                else:
                    proxies["http"] = base_url
                    proxies["https"] = base_url
            
            # 使用配置的代理
            self.session.proxies = proxies
            if proxy_user:
                print(f"已配置带认证的代理: http://{proxy_user}:***@{proxy_http}:{proxy_port}")
            else:
                print(f"已配置代理: {proxies}")
            
            # 测试代理连接
            if not self._test_proxy_connection():
                print("警告：代理连接测试失败，将尝试直接连接")
                # 代理失败时回退到直接连接
                self.session.proxies = {"http": None, "https": None}
                os.environ.pop('http_proxy', None)
                os.environ.pop('https_proxy', None)
                os.environ.pop('HTTP_PROXY', None)
                os.environ.pop('HTTPS_PROXY', None)
        else:
            # 禁用代理配置，显式设置为空以绕过系统代理
            self.session.proxies = {"http": None, "https": None}
            # 确保清除环境变量中的代理设置
            os.environ.pop('http_proxy', None)
            os.environ.pop('https_proxy', None)
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
            print("代理已禁用，使用直接连接")
    
    def _test_proxy_connection(self):
        """测试代理连接是否正常"""
        try:
            # 测试代理访问一个简单的HTTP网站
            test_url = "http://httpbin.org/ip"
            response = self.session.get(test_url, timeout=10)
            if response.status_code == 200:
                print(f"代理测试成功: {response.text[:50]}")
                return True
            else:
                print(f"代理测试失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"代理测试异常: {type(e).__name__}: {e}")
            return False
    
    def _rotate_user_agent(self):
        """轮换User-Agent"""
        self.current_agent_index = (self.current_agent_index + 1) % len(self.user_agents)
        self.session.headers["User-Agent"] = self.user_agents[self.current_agent_index]
    
    def _get_random_referer(self):
        """获取随机Referer，模拟真实浏览器行为"""
        import random
        referers = [
            "https://www.baidu.com/",
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://zh.wikipedia.org/",
            "https://baike.baidu.com/",
            "https://www.sciencedirect.com/",
            "https://www.spe.org/",
            "https://www.cnpc.com.cn/",
            "https://www.petroleumengineering.org/",
            "https://www.google.com/search?q=%E6%B5%8B%E4%BA%95"
        ]
        return random.choice(referers)
    
    def _build_request_headers(self, url):
        """构建完整的请求头，模拟真实浏览器"""
        import random
        
        # 随机选择Accept语言
        accept_langs = [
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9",
            "zh;q=1.0,en;q=0.5"
        ]
        
        # 随机Sec-Ch-Ua组合
        sec_ch_ua_options = [
            "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
            "\"Google Chrome\";v=\"120\", \"Chromium\";v=\"120\", \"Not=A?Brand\";v=\"99\"",
            "\"Microsoft Edge\";v=\"120\", \"Chromium\";v=\"120\", \"Not=A?Brand\";v=\"99\""
        ]
        
        headers = {
            "Referer": self._get_random_referer(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": random.choice(accept_langs),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": random.choice(["keep-alive", "close"]),
            "Cache-Control": random.choice(["max-age=0", "no-cache", "no-store"]),
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": random.choice(sec_ch_ua_options),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": random.choice(["same-origin", "cross-site", "none"]),
            "Sec-Fetch-User": "?1",
            "DNT": "1",
            "TE": "Trailers"
        }
        
        # 根据域名添加特定的请求头
        domain = self._extract_domain(url)
        if "baidu.com" in domain:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Origin"] = "https://" + domain
        
        return headers
    
    def _is_url_allowed(self, url):
        """检查URL是否允许爬取"""
        # 检查黑名单模式
        for pattern in self.config["blocked_patterns"]:
            if pattern.lower() in url.lower():
                return False
        
        # 检查允许的域名
        if self.config["allowed_domains"]:
            domain = self._extract_domain(url)
            if domain and not any(domain.endswith(d) for d in self.config["allowed_domains"]):
                return False
        
        return True
    
    def _extract_domain(self, url):
        """提取URL的域名"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    
    def _normalize_url(self, url):
        """标准化URL"""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    
    def fetch_and_save(self, url, save_dir="data/crawled", max_depth=None):
        """爬取网页并保存为Markdown（主入口）"""
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        self.visited = set()
        self.crawled_count = 0
        self.results = []
        self.start_time = datetime.now()
        max_depth = max_depth or self.config["max_depth"]
        
        print(f"开始爬取: {url}")
        print(f"最大深度: {max_depth}, 最大页数: {self.config['max_pages']}")
        
        if self.config["max_workers"] > 1:
            # 多线程爬取
            self._crawl_multithread(url, save_dir, max_depth)
        else:
            # 单线程爬取
            self._crawl_recursive(url, save_dir, max_depth, 0)
        
        print(f"\n爬取完成! 共爬取 {self.crawled_count} 个页面")
        return self.results
    
    def _crawl_multithread(self, url, save_dir, max_depth):
        """多线程递归爬取（修复版：正确累积新提交的futures）"""
        with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
            active_futures = {executor.submit(
                self._crawl_single_page, url, save_dir, max_depth, 0
            ): url}
            
            max_links_per_page = self.config.get("max_links_per_page", 10)  # 可配置
            
            while active_futures and self.crawled_count < self.config["max_pages"]:
                done_futures = []
                try:
                    for future in as_completed(active_futures, timeout=30):
                        done_futures.append(future)
                        break  # 每次只处理一个完成的future
                except Exception:
                    if not done_futures and list(active_futures.keys()):
                        done_futures = [list(active_futures.keys())[0]]
                
                if not done_futures:
                    continue
                
                new_futures = {}
                for key in active_futures:
                    if key not in done_futures:
                        # 保留未完成的futures
                        new_futures[key] = active_futures[key]
                active_futures = new_futures
                
                for future in done_futures:
                    try:
                        result = future.result()
                    except Exception:
                        continue
                    
                    if result and result.get("links") and self.config.get("follow_links", True):
                        links_to_crawl = result["links"][:max_links_per_page]
                        for link in links_to_crawl:
                            # 速率限制
                            if not self._check_rate_limit(link):
                                continue
                            if link not in self.visited and self.crawled_count < self.config["max_pages"]:
                                depth = result.get("depth", 0) + 1
                                if depth <= max_depth:
                                    active_futures[executor.submit(
                                        self._crawl_single_page, link, save_dir, max_depth, depth
                                    )] = link
                
                time.sleep(self.config.get("request_interval", 1))
    
    def _check_rate_limit(self, url):
        """检查URL对应的域名是否超出速率限制"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        if not domain:
            return True
        now = time.time()
        with self.lock:
            if domain in self.domain_last_request:
                elapsed = now - self.domain_last_request[domain]
                if elapsed < self.domain_min_interval:
                    return False
            self.domain_last_request[domain] = now
        return True
    
    def _crawl_recursive(self, url, save_dir, max_depth, current_depth):
        """单线程递归爬取"""
        if self.crawled_count >= self.config["max_pages"]:
            return
        
        result = self._crawl_single_page(url, save_dir, max_depth, current_depth)
        if result and result.get("links") and self.config["follow_links"]:
            for link in result["links"][:5]:
                if link not in self.visited and self.crawled_count < self.config["max_pages"]:
                    depth = current_depth + 1
                    if depth <= max_depth:
                        time.sleep(self.config["request_interval"])
                        self._crawl_recursive(link, save_dir, max_depth, depth)
    
    def _crawl_single_page(self, url, save_dir, max_depth, current_depth):
        """爬取单个页面"""
        normalized_url = self._normalize_url(url)
        
        with self.lock:
            if normalized_url in self.visited or self.crawled_count >= self.config["max_pages"]:
                return None
            self.visited.add(normalized_url)
        
        if not self._is_url_allowed(url):
            return None
        
        try:
            # 添加随机延迟，模拟人类行为
            import random
            time.sleep(self.config["request_interval"] + random.uniform(0.5, 1.5))
            
            # 添加重试机制
            response = None
            for attempt in range(self.retry_count):
                try:
                    # 每次请求前轮换User-Agent
                    self._rotate_user_agent()
                    
                    # 添加随机请求头
                    headers = {
                        "Referer": self._get_random_referer(),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Connection": "keep-alive",
                        "Cache-Control": "max-age=0",
                        "Upgrade-Insecure-Requests": "1"
                    }
                    
                    # 使用空字典让requests使用系统默认设置（包括系统代理）
                    # 如果配置禁用了代理，则使用session已配置的空代理设置
                    if self.config.get("proxy_enabled", False):
                        response = self.session.get(url, timeout=self.config["timeout"], headers=headers)
                    else:
                        # 禁用代理时使用空字典（允许系统代理生效）
                        response = self.session.get(url, timeout=self.config["timeout"], headers=headers, proxies={})
                    
                    # 如果遇到403，等待更长时间并重试
                    if response.status_code == 403:
                        print(f"遇到403，等待 {self.config['request_interval'] * (attempt + 2)} 秒后重试")
                        time.sleep(self.config["request_interval"] * (attempt + 2))
                        continue
                    
                    # 如果遇到412（预处理失败），尝试添加更多请求头并重试
                    if response.status_code == 412:
                        print(f"遇到412，尝试添加更多请求头并重试")
                        time.sleep(2)
                        # 重新初始化session以获取新的请求头
                        self._init_session()
                        continue
                    
                    break
                except requests.exceptions.RequestException as e:
                    if attempt < self.retry_count - 1:
                        print(f"请求失败 ({attempt+1}/{self.retry_count}): {e}")
                        time.sleep(self.config["request_interval"] * (attempt + 2))
                        continue
                    raise
            
            if response is None:
                print(f"爬取 {url} 失败: 重试次数用尽")
                return None
            
            # 检查状态码（放宽条件，接受更多状态码）
            if response.status_code not in [200, 201, 202, 301, 302]:
                print(f"爬取 {url} 失败: HTTP状态码 {response.status_code}")
                return None
            
            # 处理重定向
            if response.status_code in [301, 302]:
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    print(f"跟随重定向: {redirect_url}")
                    response = self.session.get(redirect_url, timeout=self.config["timeout"], headers=headers)
                    if response.status_code != 200:
                        print(f"爬取重定向URL失败: {response.status_code}")
                        return None
            
            response.encoding = response.apparent_encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取标题
            title = soup.title.string if soup.title else "Untitled"
            
            # 检查是否是安全验证页面（多种语言）
            security_keywords = ["安全验证", "验证码", "Security Check", "Captcha", "验证"]
            if any(keyword in title for keyword in security_keywords):
                if self.config.get("use_playwright", False):
                    print(f"遇到安全验证页面，尝试Playwright渲染: {url}")
                    pw_result = self._fetch_with_playwright(url)
                    if pw_result:
                        soup = BeautifulSoup(pw_result['html'], 'html.parser')
                        title = pw_result.get('title', title)
                    else:
                        print(f"Playwright不可用或失败，跳过: {url}")
                        return None
                else:
                    print(f"爬取 {url} 失败: 遇到安全验证页面")
                    return None
            
            # 提取正文内容
            content = self._extract_content(soup)
            content = filter_logging_content(content)
            
            # 内容过短时尝试Playwright渲染（可能是JS渲染的SPA页面）
            if len(content) < 200 and self.config.get("use_playwright", False) and PLAYWRIGHT_AVAILABLE:
                print(f"内容过短({len(content)}字符)，尝试Playwright渲染: {url}")
                pw_result = self._fetch_with_playwright(url)
                if pw_result:
                    soup = BeautifulSoup(pw_result['html'], 'html.parser')
                    content = self._extract_content(soup)
                    content = filter_logging_content(content)
                    title = pw_result.get('title', title)
            
            # 放宽内容检查条件，允许更多内容通过
            if not content:
                print(f"爬取 {url} 失败: 内容为空")
                return None
            
            # 检查与测井相关性（放宽条件）
            if not is_logging_related(content):
                # 如果内容与测井无关但长度足够，也保存
                if len(content) < 500:
                    print(f"爬取 {url} 失败: 内容与测井无关且太短")
                    return None
                else:
                    print(f"警告: 内容与测井相关性较低，但长度足够，保存")
            
            # 提取链接
            links = []
            if self.config["follow_links"] and current_depth < max_depth:
                links = self._extract_links(soup, url)
            
            # 保存为Markdown
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(url) % 10000}.md"
            filepath = os.path.join(save_dir, filename)
            
            import frontmatter
            post = frontmatter.Post(content)
            post["title"] = title
            post["category"] = "crawled"
            post["date"] = datetime.now()
            post["source_url"] = url
            post["depth"] = current_depth
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            
            with self.lock:
                self.crawled_count += 1
                result = {
                    "title": title,
                    "source": filepath,
                    "url": url,
                    "depth": current_depth,
                    "links": links
                }
                self.results.append(result)
            
            print(f"[{self.crawled_count}] 已爬取: {url} -> {os.path.basename(filepath)}")
            return result
            
        except Exception as e:
            print(f"爬取 {url} 失败: {e}")
            return None
    
    def _fetch_with_playwright(self, url, timeout=30):
        """使用Playwright获取JS渲染页面内容"""
        if not PLAYWRIGHT_AVAILABLE:
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.user_agents[self.current_agent_index],
                    locale='zh-CN'
                )
                page = context.new_page()
                page.goto(url, wait_until='networkidle', timeout=timeout*1000)
                page.wait_for_timeout(3000)
                html = page.content()
                title = page.title()
                browser.close()
                return {'html': html, 'title': title}
        except Exception as e:
            print(f"Playwright获取失败 {url}: {e}")
            return None
    
    def generate_simulation_knowledge(self, save_dir="data/crawled", count=10):
        """生成模拟测井知识（当网络不可用时使用）"""
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        simulation_topics = [
            {
                "title": "测井技术概述",
                "content": """测井是一种用于探测地下岩层性质的地球物理方法。通过在井眼中放置各种传感器，可以测量地层的物理特性，如电阻率、密度、中子孔隙度、声波速度等。

测井技术在石油勘探开发中起着至关重要的作用，它可以帮助地质学家和工程师了解地下储层的性质，包括岩性、孔隙度、渗透率、含流体饱和度等。

常见的测井方法包括：
1. 电法测井：测量地层电阻率，用于识别油气层
2. 声波测井：测量声波在地层中的传播速度，用于计算孔隙度
3. 放射性测井：包括自然伽马测井和中子测井，用于识别岩性和计算孔隙度
4. 成像测井：提供井壁的高分辨率图像，用于识别裂缝和沉积构造

测井资料的解释需要综合运用地质学、岩石物理学和工程知识，通过建立解释模型来推断地下储层的性质。"""
            },
            {
                "title": "阿尔奇公式及其应用",
                "content": """阿尔奇公式是测井解释中最常用的公式之一，用于计算含水饱和度。

基本公式：
Sw^n = (a * Rw) / (phi^m * Rt)

其中：
- Sw：含水饱和度
- n：饱和度指数，通常为2
- a：岩性系数，通常为1
- Rw：地层水电阻率
- phi：孔隙度
- m：胶结指数，通常为1.8-2.0
- Rt：地层真电阻率

阿尔奇公式适用于纯净砂岩储层。当储层含有泥质时，需要使用其他公式如印尼公式或Waxman-Smits公式。

在实际应用中，阿尔奇公式的参数需要通过岩心分析数据进行标定，以提高解释的准确性。"""
            },
            {
                "title": "孔隙度计算方法",
                "content": """孔隙度是储层评价的重要参数，通常可以通过以下几种测井方法计算：

1. 密度测井计算孔隙度：
phi_d = (rho_matrix - rho_b) / (rho_matrix - rho_fluid)

2. 中子测井计算孔隙度：
中子测井直接测量地层的含氢指数，经过刻度后可以得到孔隙度值。

3. 声波测井计算孔隙度：
phi_s = (Delta_t - Delta_t_matrix) / (Delta_t_fluid - Delta_t_matrix)

4. 密度-中子交汇法：
通过密度孔隙度和中子孔隙度的交汇图，可以识别岩性并计算准确的孔隙度。

在实际应用中，通常采用多种方法综合计算孔隙度，以提高结果的可靠性。"""
            },
            {
                "title": "泥质含量计算",
                "content": """泥质含量是评价储层质量的重要参数，通常可以通过以下方法计算：

1. 自然伽马法：
Vsh = (GR - GR_min) / (GR_max - GR_min)

2. 密度-中子交汇法：
利用密度和中子测井曲线的差异来计算泥质含量。

3. 电阻率法：
通过深、浅电阻率的差异来估算泥质含量。

泥质含量对储层的渗透性和饱和度计算有重要影响。当泥质含量超过一定限度时，需要使用泥质砂岩模型进行解释。"""
            },
            {
                "title": "测井曲线标准化",
                "content": """测井曲线标准化是测井资料处理的重要步骤，目的是消除不同测井仪器和测量条件带来的系统误差。

标准化的主要步骤包括：
1. 选择标准层：选择具有稳定岩性和物性的地层作为标准层
2. 计算校正系数：根据标准层的测井响应计算校正系数
3. 应用校正：将校正系数应用到整个测井曲线

常用的标准化方法包括：
- 直方图匹配法
- 均值校正法
- 趋势面分析法

标准化后的测井曲线可以更准确地进行井间对比和储层评价。"""
            },
            {
                "title": "油气水层识别方法",
                "content": """油气水层识别是测井解释的核心任务，通常采用以下方法：

1. 电阻率法：油气层通常表现为高电阻率，水层表现为低电阻率
2. 孔隙度-电阻率交汇图：可以直观地区分油气水层
3. 测井响应组合：综合利用多种测井曲线进行识别
4. 神经网络方法：利用机器学习算法进行自动识别

解释标准通常根据地区经验制定，主要考虑以下参数：
- 电阻率比值（深/浅）
- 孔隙度大小
- 含水饱和度
- 泥质含量

在实际解释中，需要结合地质背景和试油结果进行综合判断。"""
            },
            {
                "title": "储层渗透率估算",
                "content": """渗透率是储层产能评价的关键参数，通常通过以下方法估算：

1. 经验公式法：
常用的公式有Timur公式、Coates公式等，通过孔隙度和束缚水饱和度计算渗透率。

2. 神经网络方法：
利用测井曲线作为输入，通过训练好的神经网络预测渗透率。

3. 岩心标定法：
建立岩心渗透率与测井响应之间的关系，然后应用到整个井段。

渗透率估算的准确性直接影响储量计算和开发方案设计。"""
            },
            {
                "title": "成像测井解释",
                "content": """成像测井提供了井壁的高分辨率图像，在储层描述中发挥着重要作用。

主要的成像测井类型包括：
1. 电成像测井（FMI、EMI）：测量井壁的电阻率分布
2. 声成像测井（CBIL、UBI）：测量井壁的声波反射
3. 超声成像测井：提供井眼几何形状和套管状况信息

成像测井的主要应用包括：
- 裂缝识别和评价
- 沉积构造分析
- 井眼稳定性评估
- 储层非均质性描述

成像测井解释需要结合地质知识和测井原理进行综合分析。"""
            },
            {
                "title": "测井资料质量控制",
                "content": """测井资料质量控制是确保解释结果可靠的前提，主要包括以下方面：

1. 环境校正：
对测井曲线进行井眼、泥浆、温度压力等环境因素的校正。

2. 曲线对比：
检查不同测井曲线之间的一致性和相关性。

3. 异常值检测：
识别和处理测井曲线中的异常数据点。

4. 质量评价：
根据测井原始资料验收标准对测井质量进行评定。

高质量的测井资料是准确解释的基础。"""
            },
            {
                "title": "多矿物模型解释",
                "content": """多矿物模型是一种先进的测井解释方法，通过最优化算法同时计算多种矿物的含量。

基本原理：
假设地层由多种矿物和孔隙流体组成，每种测井响应是各组分响应的线性加权和。

多矿物模型的优点：
1. 可以同时计算多种矿物含量
2. 考虑了矿物之间的相互作用
3. 提高了解释的准确性和可靠性

在实际应用中，需要根据地区地质特征选择合适的矿物类型和模型参数。"""
            },
            {
                "title": "测井资料质量评价与预处理",
                "content": """测井资料质量评价是保证解释精度的基础工作。

主要评价内容：
1. 深度系统检查：对比电缆深度和钻杆深度，进行深度校正
2. 重复段质量评价：主曲线与重复曲线的相对误差应满足标准
3. 曲线基线稳定性检查：确保基线不漂移
4. 环境校正：井径、泥浆、温度等环境因素的影响校正

预处理流程包括深度对齐、跳尖编辑、曲线拼接等步骤。

数据质量等级分为A（优质）、B（可用）、C（参考）、D（不可用）。

高质量的测井资料是准确解释的前提，必须在解释前完成全面的质量控制。"""
            },
            {
                "title": "沉积环境测井识别方法",
                "content": """利用测井曲线识别沉积环境是测井地质分析的重要方法。

GR曲线形态与沉积环境的关系：
- 钟形（向上变细）：指示河流或三角洲前缘沉积，正韵律
- 漏斗形（向上变粗）：指示三角洲前缘或河口坝沉积，反韵律
- 箱形/柱状：指示浊积岩或河道砂体，粒度均匀
- 锯齿形：指示滨浅湖或潮坪环境，频繁互层

成像测井可以辅助识别沉积构造：
- 交错层理呈楔形或弧形纹理
- 平行层理呈均匀条纹
- 冲刷面呈明显的突变界面

沉积环境识别对储层预测和地质建模具有重要指导意义。"""
            },
            {
                "title": "试油测试与测井解释整合",
                "content": """试油测试数据是验证测井解释结果的关键依据。

钻杆测试（DST）资料解释要点：
1. 压力卡片识别：初关井压力、终关井压力、流动压力
2. 产能评价：根据日产油气水量划分产能等级
3. 渗透率对比：DST渗透率（有效渗透率）与测井渗透率（绝对渗透率）对比

试油资料反馈机制：
- 建立试油验证数据库
- 统计解释符合率（目标>80%）
- 根据试油结果调整解释标准和参数
- 持续优化流体识别图版

MDT/RFT流体取样可以确定地层流体PVT参数和地层水矿化度，为测井解释提供关键输入参数。"""
            },
            {
                "title": "松辽盆地测井解释经验",
                "content": """松辽盆地（大庆油田）是中国最大的油田，测井解释经验丰富。

主要油层特征：
- 萨尔图油层（S）：主力油层，砂岩发育好，GR低值，RT高值
- 葡萄花油层（P）：次主力油层，砂泥岩互层
- 高台子油层（G）：薄互层为主，解释难度大
- 扶余油层（F）：特低渗透，需压裂改造

水淹层识别是松辽盆地测井解释的核心问题：
- 高含水期RT明显降低（注入水矿化度低于地层水）
- 水淹级别划分：强水淹(Rt/Rxo<1.5)、中水淹(1.5-3.0)、弱水淹(3.0-5.0)

阿尔奇参数经验值：a=0.81, b=1.0, m=1.94, n=1.84（长垣砂岩）"""
            },
            {
                "title": "中国主要盆地测井响应特征",
                "content": """中国主要含油气盆地的测井响应具有各自特征。

松辽盆地（大庆长垣）：
- 萨尔图油层：GR 40-70 API, DEN 2.20-2.45, RT 5-50 Ω·m

渤海湾盆地（胜利油田）：
- 东营组：GR 40-100 API, DEN 2.15-2.50, RT 2-20 Ω·m
- 沙河街组：GR 35-80 API, 砂体厚但横向变化大

鄂尔多斯盆地（长庆油田）：
- 长6段：GR 60-100 API, DEN 2.40-2.60, 致密砂岩
- 低阻油层识别是关键难题

塔里木盆地：
- 奥陶系碳酸盐岩：GR 10-30 API, DEN 2.55-2.75
- 缝洞型储层非均质性极强

了解区域测井响应特征是正确选择解释模型和参数的前提。"""
            },
            {
                "title": "测井仪器组合设计与选型指南",
                "content": """合理的测井仪器组合是获取高质量测井资料的关键。

常规测井系列包括标准九条曲线：
GR（自然伽马）、SP（自然电位）、CAL（井径）、RT（深电阻率）、RXO（冲洗带电阻率）、DEN（密度）、CNL（补偿中子）、AC（声波）、PE（光电效应）

增强型测井项目：
- 阵列感应（AIT）：多深度电阻率，反演侵入剖面
- 核磁共振（CMR/MRIL）：孔隙度分布、渗透率、流体识别
- 元素俘获（ECS）：元素含量，多矿物分析

LWD随钻测井优势：
- 实时监测，减少井眼影响
- 侵入前测量，更接近原状地层
- 支持地质导向

根据井类型（探井/评价井/开发井/水平井）选择不同的测井系列组合。"""
            }
        ]
        
        import frontmatter
        
        for i, topic in enumerate(simulation_topics[:count], 1):
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_simulation_{i}.md"
            filepath = os.path.join(save_dir, filename)
            
            post = frontmatter.Post(topic["content"])
            post["title"] = topic["title"]
            post["category"] = "crawled"
            post["date"] = datetime.now()
            post["source_url"] = "simulation"
            post["depth"] = 0
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            
            result = {
                "title": topic["title"],
                "source": filepath,
                "url": "simulation",
                "depth": 0,
                "links": []
            }
            self.results.append(result)
            self.crawled_count += 1
            print(f"[{self.crawled_count}] 生成模拟知识: {topic['title']}")
        
        return self.results
    
    def _extract_content(self, soup):
        """从HTML中提取正文内容"""
        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
        
        # 尝试提取主要内容
        content_selectors = [
            'article', 'main', 
            'div[class*="content"]', 'div[class*="article"]', 'div[class*="main"]',
            'div[id*="content"]', 'div[id*="article"]',
            '.entry-content', '.post-content', '.article-content'
        ]
        
        content_text = ""
        for selector in content_selectors:
            content_tags = soup.select(selector)
            if content_tags:
                content_text = '\n\n'.join(tag.get_text(separator='\n', strip=True) for tag in content_tags)
                if content_text.strip():
                    break
        
        if not content_text:
            # 如果没有找到特定标签，提取所有段落
            paragraphs = soup.find_all('p')
            content_text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
        
        # 清理多余空行和空格
        content_text = re.sub(r'\n{3,}', '\n\n', content_text)
        content_text = re.sub(r' {2,}', ' ', content_text)
        return content_text.strip()
    
    def _extract_links(self, soup, base_url):
        """提取页面中的链接"""
        from urllib.parse import urljoin
        
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            
            # 只保留HTTP/HTTPS链接
            if full_url.startswith(('http://', 'https://')):
                # 跳过锚点和邮件链接
                if '#' in full_url and full_url.split('#')[0] == base_url.split('#')[0]:
                    continue
                if full_url.startswith('mailto:'):
                    continue
                
                links.add(full_url)
        
        return list(links)[:20]  # 最多返回20个链接
    
    def get_stats(self):
        """获取爬取统计信息"""
        return {
            "crawled_count": self.crawled_count,
            "visited_count": len(self.visited),
            "start_time": self.start_time,
            "duration": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        }

# ------------------------------
# LLM接口模块
# ------------------------------
class LLMInterface:
    """大语言模型接口，支持Ollama和OpenAI"""
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG["llm"]
        self.provider = self.config["provider"]
        self.model = self.config["model"]
        self.temperature = self.config["temperature"]
        self.max_tokens = self.config["max_tokens"]
        self.api_base = self.config["api_base"]
    
    def generate(self, prompt, context=""):
        """生成回答"""
        full_prompt = self._build_prompt(prompt, context)
        
        if self.provider == "ollama":
            return self._call_ollama(full_prompt)
        elif self.provider == "openai":
            return self._call_openai(full_prompt)
        else:
            return "未知的LLM提供商"
    
    def _build_prompt(self, prompt, context):
        """构建完整的提示词"""
        if context:
            return f"""
你是一位专业的测井解释工程师，请根据以下参考资料，回答用户的测井相关问题。

参考资料：
{context}

用户问题：
{prompt}

要求：
1. 优先使用参考资料中的信息进行回答
2. 回答要准确、简洁，符合测井专业术语规范
3. 如果参考资料中没有相关信息，请基于你的专业知识回答
4. 对于不确定的内容，请明确说明
"""
        else:
            return f"""
你是一位专业的测井解释工程师，请回答以下测井相关问题：
{prompt}

要求：
1. 回答要准确、专业，使用正确的测井术语
2. 提供详细的解释和必要的公式说明
3. 如果涉及计算，请给出示例
"""
    
    def _call_ollama(self, prompt):
        """调用Ollama API"""
        try:
            response = requests.post(
                f"{self.api_base}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens
                },
                stream=True,
                timeout=120
            )
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    if "response" in data:
                        full_response += data["response"]
                    if data.get("done", False):
                        break
            
            return full_response.strip()
        except Exception as e:
            return f"调用Ollama失败: {str(e)}"
    
    def _call_openai(self, prompt):
        """调用OpenAI API"""
        try:
            import openai
            client = openai.OpenAI(base_url=self.api_base)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"调用OpenAI失败: {str(e)}"

# ------------------------------
# 内置测井知识模块
# ------------------------------
class BuiltInKnowledge:
    """内置测井专业知识，提供基础解释规则和图版数据"""
    
    def __init__(self):
        self.knowledge_base = self._load_builtin_knowledge()
    
    def _load_builtin_knowledge(self):
        """加载内置知识"""
        return {
            "archie_equation": {
                "title": "阿尔奇公式",
                "content": """
阿尔奇公式是测井解释中计算含水饱和度的基本公式：

Sw^n = (a * Rw) / (φ^m * Rt)

其中：
- Sw：含水饱和度
- n：饱和度指数，通常取2
- a：岩性系数，通常取1
- Rw：地层水电阻率（Ω·m）
- φ：孔隙度（小数）
- m：胶结指数，通常取1.8-2.2

应用条件：
1. 适用于纯净砂岩储层（泥质含量<10%）
2. 地层水矿化度相对稳定
3. 岩石颗粒分选较好

当泥质含量较高时（Vsh>15%），应使用印尼公式或Waxman-Smits公式。
""",
                "category": "interpretation_model"
            },
            "archie_parameters": {
                "title": "阿尔奇公式参数取值与地区经验系数",
                "content": """
## 一、阿尔奇公式参数（a, b, m, n）取值范围

| 参数 | 符号 | 物理意义 | 典型取值范围 | 说明 |
|------|------|----------|--------------|------|
| 岩性系数 | a | 与岩石性质相关的系数 | 0.6-1.5 | 纯净砂岩通常取1.0 |
| 饱和度指数 | n | 饱和度对电阻率的影响指数 | 1.8-2.5 | 大多数砂岩取2.0 |
| 胶结指数 | m | 孔隙结构对电阻率的影响指数 | 1.5-2.5 | 取决于岩石胶结程度 |
| 孔隙度指数 | b | 孔隙度对电阻率的影响指数 | 1.0-2.0 | 通常取1.0 |

## 二、不同岩性的参数取值

### 砂岩储层
- a = 0.8-1.2（平均1.0）
- m = 1.8-2.2（平均2.0）
- n = 1.9-2.1（平均2.0）

### 碳酸盐岩储层
- a = 0.6-0.9
- m = 2.0-2.5
- n = 2.0-2.2

### 疏松砂岩（未胶结）
- a = 1.0-1.5
- m = 1.5-1.8
- n = 1.8-2.0

## 三、地区经验系数示例

### 中国主要油田

| 油田/区块 | a | m | n | 备注 |
|-----------|---|---|---|------|
| 大庆油田 | 0.9 | 2.0 | 2.0 | 松辽盆地砂岩 |
| 胜利油田 | 0.85 | 1.9 | 2.0 | 济阳坳陷 |
| 辽河油田 | 1.0 | 2.1 | 2.0 | 辽河盆地 |
| 长庆油田 | 0.95 | 2.0 | 2.0 | 鄂尔多斯盆地 |
| 塔里木油田 | 0.8 | 2.2 | 2.1 | 塔中地区碳酸盐岩 |

### 海外地区

| 地区 | a | m | n | 备注 |
|------|---|---|---|------|
| 中东地区 | 0.8-1.0 | 1.8-2.0 | 2.0 | 阿拉伯砂岩 |
| 北海油田 | 0.9-1.1 | 1.9-2.1 | 2.0 | 北海砂岩 |
| 北美地区 | 1.0-1.2 | 1.8-2.0 | 2.0 | 威利斯顿盆地 |
| 非洲地区 | 0.85-1.0 | 1.9-2.1 | 2.0 | 尼日尔、乍得 |

## 四、参数确定方法

1. **岩心标定法**：利用岩心分析数据进行回归计算
2. **试油资料反算法**：根据试油结果反推参数
3. **区域经验法**：参考邻井或区块经验值
4. **交会图法**：利用电阻率-孔隙度交会图确定

## 五、注意事项

1. 参数取值应根据实际岩心分析数据进行标定
2. 不同沉积相带的参数可能存在差异
3. 成岩作用强烈的储层m值偏大
4. 疏松砂岩m值偏小
""",
                "category": "interpretation_model"
            },
            "simandoux_equation": {
                "title": "印尼公式（Simandoux）参数取值",
                "content": """
## 印尼公式（适用于泥质砂岩）

Sw^n = (a * Rw) / (φ^m * Rt * (1 + Vsh * (Rsh/Rw - 1)))

### 参数取值范围

| 参数 | 符号 | 典型取值 | 说明 |
|------|------|----------|------|
| 岩性系数 | a | 0.8-1.2 | 通常取1.0 |
| 胶结指数 | m | 1.8-2.2 | 取决于岩石胶结程度 |
| 饱和度指数 | n | 1.9-2.2 | 通常取2.0 |
| 泥质电阻率 | Rsh | 0.2-2.0 Ω·m | 需实际测量或计算 |
| 地层水电阻率 | Rw | 0.01-1.0 Ω·m | 随温度和矿化度变化 |

### 地区经验系数

| 地区/油田 | a | m | n | 适用条件 |
|-----------|---|---|---|----------|
| 大庆油田 | 1.0 | 2.0 | 2.0 | 泥质含量10-30% |
| 胜利油田 | 0.9 | 1.9 | 2.0 | 三角洲沉积 |
| 长庆油田 | 1.0 | 2.1 | 2.0 | 低渗透储层 |
| 中东地区 | 0.85 | 2.0 | 2.0 | 碳酸盐岩 |

## 适用条件
- 泥质含量5-40%的泥质砂岩储层
- 地层水矿化度变化较大的地区
- 需要考虑泥质导电影响的情况
""",
                "category": "interpretation_model"
            },
            "waxman_smits": {
                "title": "Waxman-Smits公式参数",
                "content": """
## Waxman-Smits公式（考虑粘土阳离子导电）

Rt = (a * Rw * φ^(-m)) / (Sw^n + B * Qv * Sw^(-0.5) / F)

### 参数说明与取值

| 参数 | 符号 | 取值范围 | 说明 |
|------|------|----------|------|
| 岩性系数 | a | 0.8-1.2 | 通常取1.0 |
| 胶结指数 | m | 1.8-2.2 | 胶结程度影响 |
| 饱和度指数 | n | 1.8-2.2 | 通常取2.0 |
| 阳离子交换容量 | Qv | 0.5-3.0 meq/100g | 粘土含量相关 |
| 平衡常数 | B | 0.2-0.6 | 温度相关 |

### Qv值参考（不同粘土类型）

| 粘土类型 | Qv (meq/100g) | 说明 |
|----------|---------------|------|
| 蒙脱石 | 80-120 | 高阳离子交换 |
| 伊利石 | 10-40 | 中等交换能力 |
| 高岭石 | 1-10 | 低交换能力 |

### 应用条件
- 粘土含量较高的储层
- 需要精确计算低饱和度地层
- 高温高压条件下的深层储层
""",
                "category": "interpretation_model"
            },
            "permeability_models": {
                "title": "渗透率经验公式及参数",
                "content": """
## 常用渗透率计算公式

### 1. Timur公式
K = 0.136 * (φ^4.4 / Sw^2)

适用条件：固结砂岩，φ=10-30%，Sw=20-80%

### 2. Coates公式
K = (φ^3 * (1 - Sw)^2 / Sw^2) * C

其中C为常数，需根据岩心标定，通常C=100-500

### 3. Wyllie-Rose公式
K = (φ^2 * 10^8) / (τ^2)

其中τ为迂曲度，砂岩通常τ=1.5-2.5

### 4. 核磁共振公式
K ∝ (T2gm * φ)^2 / T2lm

其中T2gm为几何平均T2，T2lm为对数平均T2

### 地区经验系数

| 地区/油田 | 公式类型 | 经验系数 | 适用条件 |
|-----------|----------|----------|----------|
| 大庆油田 | Timur | C=1.0 | 河流相砂岩 |
| 胜利油田 | Coates | C=250 | 三角洲砂岩 |
| 长庆油田 | Timur | C=0.8 | 低渗透砂岩 |
| 塔里木油田 | Coates | C=300 | 碳酸盐岩 |
| 中东地区 | Timur | C=1.2 | 高孔隙砂岩 |

### 注意事项
1. 渗透率估算误差较大（±50%）
2. 需根据区域岩心资料标定
3. 不同沉积相带参数差异较大
""",
                "category": "calculation"
            },
            "shale_volume_params": {
                "title": "泥质含量计算参数与地区经验",
                "content": """
## 泥质含量计算方法与参数

### 1. 自然伽马法
Vsh = (GR - GRmin) / (GRmax - GRmin)

**Steiber公式（更精确）**：
Vsh = 0.083 * (2^(3.7*Ish) - 1)
其中：Ish = (GR - GRmin) / (GRmax - GRmin)

### 2. 声波时差法
Vsh_AC = (Δt - Δtma) / (Δtsh - Δtma)

### 地区经验参数

| 地区/油田 | GRmin (API) | GRmax (API) | Δtma (μs/ft) | Δtsh (μs/ft) |
|-----------|-------------|-------------|--------------|--------------|
| 大庆油田 | 20 | 120 | 55 | 90 |
| 胜利油田 | 25 | 130 | 56 | 95 |
| 长庆油田 | 20 | 140 | 55 | 100 |
| 塔里木油田 | 15 | 100 | 47 | 85 |
| 中东地区 | 10 | 80 | 55 | 85 |

### 注意事项
1. GR基线需根据实际资料确定
2. 不同岩性的骨架时差不同
3. 泥岩时差受压实程度影响
""",
                "category": "calculation"
            },
            "formation_evaluation_params": {
                "title": "储层评价地区经验参数",
                "content": """
## 储层评价关键参数

### 一、孔隙度下限标准

| 地区/油田 | 孔隙度下限(%) | 渗透率下限(mD) | 说明 |
|-----------|---------------|----------------|------|
| 大庆油田 | 10 | 1 | 河流相砂岩 |
| 胜利油田 | 8 | 0.5 | 三角洲砂岩 |
| 长庆油田 | 6 | 0.1 | 低渗透砂岩 |
| 塔里木油田 | 5 | 0.1 | 碳酸盐岩 |
| 中东地区 | 12 | 5 | 高孔隙砂岩 |

### 二、饱和度标准

| 流体类型 | Sw界限(%) | 说明 |
|----------|-----------|------|
| 油层 | <50 | 含油饱和度>50% |
| 油水同层 | 40-60 | 过渡带 |
| 水层 | >60 | 含水为主 |

### 三、电阻率标准

| 地区/油田 | 油层Rt(Ω·m) | 水层Rt(Ω·m) | 比值 |
|-----------|-------------|-------------|------|
| 大庆油田 | >15 | <5 | >3 |
| 胜利油田 | >20 | <8 | >2.5 |
| 长庆油田 | >30 | <10 | >3 |
| 塔里木油田 | >50 | <15 | >3.5 |

### 四、解释图版参数

| 参数 | 砂岩 | 碳酸盐岩 | 页岩 |
|------|------|----------|------|
| 骨架密度(g/cm³) | 2.65 | 2.71-2.87 | 2.55 |
| 骨架时差(μs/ft) | 55.5 | 45-50 | 80 |
| 骨架PE(b/e) | 1.81 | 3-5 | 3.45 |
| 流体密度(g/cm³) | 1.0 | 1.0 | - |
| 流体时差(μs/ft) | 189 | 189 | - |

### 五、地区经验认识

1. **松辽盆地**：GR基线稳定，泥质含量计算可靠
2. **渤海湾盆地**：需考虑压实作用影响
3. **鄂尔多斯盆地**：低孔低渗，需精细评价
4. **塔里木盆地**：碳酸盐岩储层，裂缝发育
5. **中东地区**：高孔隙砂岩，成岩作用弱
""",
                "category": "evaluation"
            },
            "porosity_calculation": {
                "title": "孔隙度计算方法",
                "content": """
测井孔隙度计算主要有三种方法：

1. **密度孔隙度**：
   φDEN = (ρma - ρb) / (ρma - ρf)
   其中：ρma=2.65 g/cm³（砂岩骨架密度），ρf=1.0 g/cm³（流体密度）

2. **中子孔隙度**：
   直接读取CNL曲线值（注意单位转换）

3. **声波孔隙度**：
   φAC = (Δt - Δtma) / (Δtf - Δtma)
   其中：Δtma=55.5 μs/ft（砂岩骨架时差），Δtf=189 μs/ft（流体时差）

综合孔隙度通常采用密度-中子交会方法确定。
""",
                "category": "calculation"
            },
            "shale_volume": {
                "title": "泥质含量计算",
                "content": """
泥质含量计算常用方法：

1. **自然伽马法**：
   Vsh_GR = (GR - GRmin) / (GRmax - GRmin)
   或使用Steiber公式：Vsh = 0.083 * (2^(3.7*Ish) - 1)
   其中：Ish = (GR - GRmin) / (GRmax - GRmin)

2. **密度-中子交会法**：
   利用密度和中子孔隙度的差异计算泥质含量

3. **声波时差法**：
   Vsh_AC = (Δt - Δtma) / (Δtsh - Δtma)

实际应用中通常采用多种方法综合确定泥质含量。
""",
                "category": "calculation"
            },
            "lithology_identification": {
                "title": "岩性识别标准",
                "content": """
基于测井曲线的岩性识别：

| 岩性 | GR (API) | DEN (g/cm³) | CNL (%) | AC (μs/ft) | 特征 |
|------|----------|-------------|---------|------------|------|
| 纯净砂岩 | <50 | ~2.65 | -2~5 | 55~65 | 低GR，高密度，低声波时差 |
| 泥质砂岩 | 50~100 | 2.4~2.6 | 10~30 | 65~80 | 中等GR |
| 泥岩 | >100 | <2.5 | >35 | >80 | 高GR，低密度，高声波时差 |
| 石灰岩 | <30 | ~2.71 | 0~5 | 45~55 | 高密度，低声波时差 |
| 白云岩 | <30 | ~2.87 | 5~15 | 40~50 | 最高密度 |

实际解释需结合区域经验和岩心标定。
""",
                "category": "interpretation"
            },
            "fluid_identification": {
                "title": "油气水层判别标准",
                "content": """
基于测井资料的流体识别：

**油层特征**：
- 深电阻率高（Rt > 30 Ω·m）
- 中子-密度交会出现明显"挖掘效应"
- 自然电位负异常（淡水泥浆）
- 孔隙度适中（通常>10%）
- Sw < 50%

**气层特征**：
- 深电阻率极高（Rt > 50 Ω·m）
- 密度孔隙度明显高于中子孔隙度（"周波跳跃"）
- 声波时差增大，出现"周波跳跃"
- 中子孔隙度明显降低
- 可能出现挖掘效应

**水层特征**：
- 深电阻率低（Rt < 10 Ω·m）
- 中子-密度重合或接近
- 自然电位异常幅度小
- Sw > 50%

**干层特征**：
- 低孔隙度（<10%）
- 电阻率中等
- 无明显流体响应
""",
                "category": "interpretation"
            },
            "permeability": {
                "title": "渗透率估算方法",
                "content": """
渗透率估算常用经验公式：

1. **Timur公式**：
   K = 0.136 * (φ^4.4 / Sw^2)
   适用于固结砂岩

2. **Coates公式**：
   K = (φ^3 * (1 - Sw)^2) / (Sw^2) * C
   其中C为常数，需根据岩心标定

3. **Wyllie-Rose公式**：
   K = (φ^2 * 10^8) / (τ^2)
   其中τ为迂曲度

4. **基于核磁共振**：
   K ∝ (T2gm * φ)^2 / T2lm
   其中T2gm为几何平均T2，T2lm为对数平均T2

渗透率估算受多种因素影响，需结合区域经验。
""",
                "category": "calculation"
            },
            "resistivity_correction": {
                "title": "电阻率校正方法",
                "content": """
环境因素对电阻率的影响及校正：

1. **井眼校正**：
   - 井径扩大导致测量电阻率偏低
   - 校正公式：Rt_corrected = Rt_measured * (CAL / DH)^n
   其中DH为钻头直径，n为指数（通常取1.5-2.0）

2. **侵入校正**：
   - 泥浆滤液侵入形成侵入带
   - 深探测电阻率反映原状地层
   - 浅探测电阻率反映侵入带
   - 侵入半径可通过双侧向曲线计算

3. **温度校正**：
   - 电阻率随温度升高而降低
   - 校正公式：Rt(T) = Rt_measured * (T0 / T)^m
   其中T0为参考温度，m为温度系数

4. **泥浆电阻率校正**：
   - 泥浆电阻率随温度和盐度变化
   - 需根据实际测量值进行校正
""",
                "category": "correction"
            },
            "crossplot_analysis": {
                "title": "交会图分析方法",
                "content": """
常用测井交会图及其应用：

1. **密度-中子交会图**：
   - 识别岩性和孔隙度
   - 区分油层和气层（挖掘效应）
   - 计算泥质含量

2. **电阻率-孔隙度交会图**：
   - 确定含水饱和度
   - 识别油气水层
   - 建立解释图版

3. **自然伽马-电阻率交会图**：
   - 识别泥质含量
   - 划分储层和非储层

4. **声波-密度交会图**：
   - 确定岩石骨架类型
   - 估算孔隙度

5. **PE-密度交会图**：
   - 识别岩性（特别是碳酸盐岩）
   - 区分不同矿物成分

交会图解释需结合区域岩心资料进行标定。
""",
                "category": "analysis"
            },
            "quality_control": {
                "title": "测井资料质量控制",
                "content": """
测井资料质量控制要点：

1. **曲线检查**：
   - 曲线连续性检查（无跳变）
   - 曲线幅度合理性检查
   - 曲线相关性检查（如GR与SP的相关性）

2. **深度对齐**：
   - 所有曲线深度必须一致
   - 检查深度误差（通常<0.5m）

3. **环境影响评估**：
   - 井眼扩大影响
   - 侵入带影响
   - 温度压力影响

4. **刻度验证**：
   - 检查刻度点是否在标准范围内
   - 对比重复曲线

5. **异常值处理**：
   - 剔除明显异常点（扩径、仪器故障等）
   - 采用插值或邻井对比方法修复

6. **资料完整性**：
   - 检查曲线数量是否齐全
   - 检查测量井段是否完整

质量控制是测井解释的基础，直接影响解释结果的可靠性。
""",
                "category": "quality_control"
            },
            "reservoir_evaluation": {
                "title": "储层综合评价标准",
                "content": """
储层综合评价等级划分：

**I类储层（优质储层）**：
- 孔隙度 > 20%
- 渗透率 > 100 mD
- 含油饱和度 > 50%
- 泥质含量 < 10%
- 储层厚度 > 5m

**II类储层（中等储层）**：
- 孔隙度 15-20%
- 渗透率 10-100 mD
- 含油饱和度 40-50%
- 泥质含量 10-20%
- 储层厚度 3-5m

**III类储层（低渗透储层）**：
- 孔隙度 10-15%
- 渗透率 1-10 mD
- 含油饱和度 30-40%
- 泥质含量 20-30%

**IV类储层（非有效储层）**：
- 孔隙度 < 10%
- 渗透率 < 1 mD
- 含油饱和度 < 30%
- 泥质含量 > 30%

评价标准需根据区块特点进行调整。
""",
                "category": "evaluation"
            },
            # ========== 资料知识 (Data Quality) ==========
            "well_log_data_quality": {
                "title": "测井资料质量标准与验收规范",
                "content": """
## 测井资料质量标准（SY/T 5132、SY/T 6605）

### 一、曲线质量验收标准
1. **重复性要求**：
   - 主曲线与重复曲线误差：GR < 5%，电阻率 < 5%，孔隙度曲线 < 3%
   - 重复测量井段不少于50m，应在目的层段选取
2. **曲线异常识别**：
   - 跳尖：单个采样点突变，通常为干扰，应编辑处理
   - 周波跳跃：声波曲线特征，指示裂缝或气层
   - 平台值：仪器饱和或故障，需重新测量
   - 负值异常：中子或密度曲线出现负值，指示井眼问题

### 二、环境影响校正
1. **井眼影响**：扩径段密度/中子不可靠，需校正或剔除
2. **泥浆影响**：重泥浆（含重晶石）影响PE和密度测量
3. **温度影响**：高温井需注意仪器耐温等级和温度校正
4. **地层水矿化度**：影响中子测井，需进行含氢指数校正

### 三、质量控制流程
1. 检查深度系统（电缆深度 vs 钻杆深度校正）
2. 检查曲线基线稳定性
3. 检查重复段质量
4. 检查仪器刻度（主刻度/检查刻度）记录
5. 环境校正（井径、泥浆、温度等）
""",
                "category": "data_quality"
            },
            "logging_acquisition_standards": {
                "title": "测井采集标准与测井系列选择",
                "content": """
## 测井采集标准

### 一、测井系列选择
| 井类型 | 基本测井系列 | 附加测井项目 |
|--------|-------------|-------------|
| 探井 | GR+SP+RT+RXO+DEN+CNL+AC | NMR、ECS、FMI、MDT |
| 评价井 | GR+SP+RT+RXO+DEN+CNL+AC | NMR、MDT/RFT |
| 开发井 | GR+SP+RT+DEN+CNL | 视需求加测NMR |
| 水平井 | LWD(GR+RES+DEN+CNL) | 地质导向、随钻成像 |

### 二、测量速度要求
- 常规测井：≤ 600m/h（确保采样密度≥8点/m）
- 高分辨率测井：≤ 300m/h
- 成像测井：≤ 200m/h
- NMR测井：≤ 150m/h

### 三、深度控制标准
- 深度误差：≤ 0.5‰（即1000m井深允许0.5m误差）
- 电缆深度校正：每口井必须进行钻杆深度对比校正
- 深度采样间隔：常规0.125m，高精度0.05m

### 四、测井顺序规范
1. 先测自然伽马和井径（确定井眼状况）
2. 再测电阻率系列（避免泥浆侵入影响）
3. 后测孔隙度系列（密度→中子→声波）
4. 最后测特殊项目（NMR、成像等）
""",
                "category": "data_quality"
            },
            "data_preprocessing": {
                "title": "测井数据预处理流程",
                "content": """
## 测井数据预处理工作流

### 一、深度对齐（Depth Matching）
1. 选择参考曲线（通常选GR，因其自然变化特征明显）
2. 计算各曲线与参考曲线的深度偏移量
3. 采用互相关法或特征点法进行深度校正
4. 校正后验证：同一深度各曲线响应一致性

### 二、环境校正
1. **井径校正**：扩径段密度/中子校正或标记为不可靠
2. **泥浆校正**：重泥浆对PE、密度的影响校正
3. **温度校正**：高温对电阻率的影响校正
4. **围岩校正**：薄层围岩效应对电阻率的影响

### 三、曲线编辑
1. 跳尖编辑：去除单点异常值，线性插值
2. 曲线拼接：多次测量曲线的无缝拼接
3. 坏曲线替换：使用冗余曲线或经验公式替代

### 四、标准化与归一化
1. **直方图法**：对GR等曲线进行区域标准化
2. **交会图法**：利用交会图检验曲线一致性
3. **趋势面法**：消除区域趋势对局部解释的影响

### 五、质量标记
- 对每段曲线标注质量等级：A（优质）、B（可用）、C（参考）、D（不可用）
- 建立质量标记曲线，供后续解释使用
""",
                "category": "data_quality"
            },
            # ========== 测井地质知识 (Logging Geology) ==========
            "depositional_environments": {
                "title": "沉积环境测井识别方法",
                "content": """
## 利用测井曲线识别沉积环境

### 一、GR曲线形态与沉积环境
| GR曲线形态 | 沉积环境 | 粒度特征 | 水动力条件 |
|------------|---------|---------|-----------|
| 钟形（向上变细） | 河流/三角洲前缘 | 下粗上细正韵律 | 向上减弱 |
| 漏斗形（向上变粗） | 三角洲前缘/河口坝 | 下细上粗反韵律 | 向上增强 |
| 箱形/柱状 | 浊积岩/河道砂体 | 粒度均匀 | 稳定强水动力 |
| 锯齿形 | 滨浅湖/潮坪 | 频繁互层 | 频繁变化 |
| 指状 | 河道/水下分流河道 | 突变界面 | 快速沉积 |
| 平缓低值 | 深湖/半深湖泥岩 | 细粒均质 | 安静环境 |

### 二、典型沉积相测井特征
1. **河流相**：
   - 砂体形态：透镜状，横向变化快
   - GR：钟形为主，底突变
   - RT：高阻，与围岩差异明显
   
2. **三角洲相**：
   - 前三角洲：漏斗形GR，向上变粗
   - 三角洲前缘：指状-钟形，多期叠置
   - 三角洲平原：箱形，砂体厚且均匀

3. **浊积岩相**：
   - GR：箱形或钟形，突变底界
   - 典型鲍玛序列：底部块状→上部渐变
   - DEN/AC：砂岩段孔隙度好

### 三、成像测井辅助沉积构造识别
- 交错层理：成像图上呈楔形/弧形纹理
- 平行层理：均匀条纹
- 生物扰动：斑点状不均匀纹理
- 冲刷面：明显的突变界面
""",
                "category": "logging_geology"
            },
            "diagenesis_effects": {
                "title": "成岩作用对测井响应的影响",
                "content": """
## 成岩作用对测井曲线的影响

### 一、压实作用
- **对DEN的影响**：随埋深增加，孔隙度减小，DEN增大
- **对AC的影响**：声波时差随深度减小（正常压实趋势）
- **异常超压识别**：偏离正常压实趋势线，AC偏大、DEN偏小
- 欠压实段往往与异常高压相关

### 二、胶结作用
- **硅质胶结**：DEN增大、CNL减小（石英含量增加）、AC减小
- **钙质胶结**：DEN显著增大（方解石密度2.71g/cm³）、PE增大
- **黏土矿物胶结**：CNL增大（含氢矿物增加）、GR可能增大

### 三、溶蚀作用
- **次生孔隙发育**：DEN减小、AC增大、CNL增大
- 溶蚀孔隙与原生孔隙的区分：
  - NMR T2谱呈双峰分布（大孔+小孔）
  - 声波-密度交会偏离正常趋势
  - 成像测井可见溶蚀孔洞

### 四、白云岩化
- 白云石密度（2.87g/cm³）大于石灰岩（2.71g/cm³）
- DEN-CN交会图上白云岩趋势线与石灰岩趋势线分开
- 白云岩中子孔隙度偏低（骨架含氢指数低）
- PE值：石灰岩~5b/e，白云岩~3b/e

### 五、成岩作用对储层评价的影响
1. 早期成岩（机械压实）：降低原生孔隙度
2. 中期成岩（胶结）：进一步降低孔隙度和渗透率
3. 晚期成岩（溶蚀）：可改善储层物性，形成次生孔隙
4. 需在测井解释中考虑成岩阶段对骨架参数选择的影响
""",
                "category": "logging_geology"
            },
            "reservoir_heterogeneity": {
                "title": "储层非均质性测井表征方法",
                "content": """
## 利用测井资料表征储层非均质性

### 一、层间非均质性
1. **渗透率变异系数（Vk）**：Vk = σk / K_mean
   - Vk < 0.5：均质储层
   - Vk 0.5-0.7：中等非均质
   - Vk > 0.7：强非均质
2. **突进系数（Tk）**：Tk = K_max / K_mean
3. **级差（Jk）**：Jk = K_max / K_min

### 二、层内非均质性
1. **渗透率韵律**：
   - 正韵律：渗透率向上递减（河流相特征）
   - 反韵律：渗透率向上递增（三角洲前缘特征）
   - 复合韵律：多期叠置
2. **夹层识别**：
   - GR突变增大
   - DEN增大、CNL减小（泥质夹层）
   - RT明显降低
   - 夹层厚度<0.5m需高分辨率测井识别

### 三、平面非均质性
1. 利用多井对比分析砂体横向连续性
2. 砂体连通性评价：对比标志层间的砂体展布
3. 测井相分析：利用GR曲线形态进行沉积微相划分

### 四、流动单元划分
1. **流动带指标（FZI）**：FZI = RQI / φz
   - RQI = 0.0314 × √(K/φ)
   - φz = φ/(1-φ)
2. 利用FZI聚类划分流动单元
3. 每个流动单元建立独立的孔渗关系
4. 测井曲线响应模式与流动单元的对应关系
""",
                "category": "logging_geology"
            },
            # ========== 试油知识 (Well Testing) ==========
            "dst_interpretation": {
                "title": "钻杆测试(DST)解释与测井渗透率对比",
                "content": """
## 钻杆测试（DST）资料解释

### 一、压力卡片识别
1. **初关井压力（ISIP）**：反映原始地层压力
2. **终关井压力（FSIP）**：反映测试后地层压力恢复程度
3. **流动压力**：反映地层产能和渗透性
4. **压力恢复曲线形态**：
   - 直线段：均质地层特征
   - 上翘：边界封闭或双重介质
   - 下弯：定压边界（如底水）

### 二、产能评价
| 产能等级 | 日产油量(m³/d) | 日产气量(10⁴m³/d) | 评价 |
|---------|---------------|------------------|------|
| 高产 | >50 | >10 | 工业油气流 |
| 中产 | 10-50 | 2-10 | 工业油气流 |
| 低产 | 1-10 | 0.5-2 | 低产油气流 |
| 微量 | <1 | <0.5 | 需改造 |
| 水层 | 产水为主 | - | 水层或油水同层 |

### 三、DST渗透率与测井渗透率对比
1. DST渗透率为有效渗透率（反映实际流动能力）
2. 测井渗透率为绝对渗透率（经验公式估算）
3. 两者差异原因：
   - 地层损害（正表皮）：DST渗透率偏低
   - 天然裂缝：DST渗透率可能远高于测井估算
   - 多相流动：DST反映有效渗透率
4. 利用DST结果标定测井渗透率模型，提高预测精度

### 四、压力恢复试井解释
- Horner法求地层压力和外推压力
- 半对数直线段斜率求渗透率
- 表皮系数S评价地层损害程度
""",
                "category": "well_testing"
            },
            "production_testing": {
                "title": "试油生产测试与测井解释整合",
                "content": """
## 试油测试数据与测井解释的整合应用

### 一、流体类型验证
1. **测井预测 vs 试油验证**：
   - 测井预测油层 → 试油证实产油：解释正确
   - 测井预测油层 → 试油产水：需分析原因（高束缚水、水锁等）
   - 测井预测水层 → 试油产油：需检查含油性识别标准
2. **气油比（GOR）与测井响应**：
   - 高GOR（>100m³/m³）：密度明显偏低、中子偏低、声波偏高
   - 低GOR：响应接近油层特征

### 二、含水率标定
1. 利用试油含水率（fw）标定测井含水饱和度（Sw）
2. 建立Sw-fw关系：fw = f(Sw, μw/μo, Krw/Kro)
3. 产水率预测模型：
   - fw < 5%：纯油层
   - fw 5-50%：油水同层
   - fw > 50%：含油水层

### 三、产能预测与测井参数关系
1. 产能指数（PI）= K × h / (μ × ln(re/rw))
2. 利用测井渗透率和有效厚度预测产能
3. 建立区块经验产能预测模型

### 四、试油资料反馈
1. 建立试油验证数据库
2. 统计解释符合率（目标>80%）
3. 根据试油结果调整解释标准和参数
4. 持续优化流体识别图版
""",
                "category": "well_testing"
            },
            "fluid_sampling": {
                "title": "MDT/RFT流体取样与地层压力分析",
                "content": """
## MDT/RFT/RCI流体取样与压力分析

### 一、地层压力梯度分析
1. **压力梯度计算**：
   - 水层压力梯度：~1.0 MPa/100m（正常压力）
   - 油层压力梯度：0.7-0.9 MPa/100m（取决于原油密度）
   - 气层压力梯度：0.1-0.3 MPa/100m
2. **流体界面确定**：
   - 油水界面（OWC）：压力梯度转折点
   - 气油界面（GOC）：压力梯度转折点
   - 利用多深度压力点线性回归求交点

### 二、流体取样分析
1. **MDT取样流程**：
   - 泵出阶段：排出泥浆滤液
   - 监测污染度：利用光学传感器实时监测
   - 取样阶段：污染度<10%时取样
2. **取样结果应用**：
   - 确定地层流体PVT参数
   - 确定地层水矿化度和Rw
   - 确定原油API度和粘度
   - 为测井解释提供关键参数

### 三、渗透率估算
1. **压降法**：K = q × μ / (4π × ΔP × Δt)
2. **压力恢复法**：利用球形流分析
3. 与测井渗透率对比验证

### 四、注意事项
1. 超压地层需注意安全操作
2. 低渗透地层取样时间长、成功率低
3. 裂缝性地层压力传递快，需快速响应
4. 取样点选择：优先选择测井响应好的渗透层
""",
                "category": "well_testing"
            },
            # ========== 测井区域解释经验 (Regional Experience) ==========
            "songliao_basin_experience": {
                "title": "松辽盆地（大庆）测井解释经验",
                "content": """
## 松辽盆地测井解释经验

### 一、地层特征
- **萨尔图油层（S）**：主力油层，砂岩发育好，GR低值，RT高值
- **葡萄花油层（P）**：次主力油层，砂泥岩互层
- **高台子油层（G）**：薄互层为主，解释难度大
- **扶余油层（F）**：特低渗透，需压裂改造

### 二、阿尔奇参数经验值
- a=0.81, b=1.0, m=1.94, n=1.84（大庆长垣砂岩）
- a=1.0, b=1.0, m=2.0, n=2.0（扶余致密砂岩）

### 三、水淹层识别（注水开发特色）
1. **高含水期特征**：
   - RT明显降低（注入水矿化度低）
   - SP幅度减小
   - 自然电位基线偏移
2. **水淹级别划分**：
   - 强水淹：Rt/Rxo < 1.5，含水率>80%
   - 中水淹：Rt/Rxo 1.5-3.0，含水率40-80%
   - 弱水淹：Rt/Rxo 3.0-5.0，含水率10-40%
   - 未水淹：Rt/Rxo > 5.0

### 四、剩余油评价
1. 利用碳氧比（C/O）测井识别剩余油
2. 脉冲中子测井（PND-S）监测水淹动态
3. 时间推移测井对比分析水淹前缘
""",
                "category": "regional_experience"
            },
            "bohai_bay_basin_experience": {
                "title": "渤海湾盆地测井解释经验",
                "content": """
## 渤海湾盆地测井解释经验

### 一、地质特点
- 复杂断块油气藏，断层发育
- 多套含油层系：东营组(Ed)、沙河街组(Es2/Es3)
- 砂体横向变化大，对比困难
- 盐膏层发育，影响测井质量

### 二、东营组(Ed)特征
- 砂岩为主，分选较差，泥质含量高
- GR中-高值（40-100 API）
- 电阻率中等（2-20 Ω·m）
- 孔隙度15-28%，渗透率10-500 mD
- 阿尔奇参数：a=1.0, m=2.05, n=2.0

### 三、沙河街组(Es2/Es3)特征
- Es2：扇三角洲沉积，砂体厚
- Es3：浊积岩发育，砂泥岩频繁互层
- 薄层识别困难，需高分辨率测井
- 地层压力系数高（1.1-1.3），需注意异常高压

### 四、特殊解释问题
1. **盐膏层影响**：盐岩段井径扩大严重，DEN/CNL不可靠
2. **高矿化度地层水**：Rw极低（0.01-0.05 Ω·m），低阻油层
3. **复杂岩性**：白云质砂岩、灰质砂岩需多矿物模型
4. **裂缝发育**：部分井段裂缝发育，AC出现周波跳跃
""",
                "category": "regional_experience"
            },
            "ordos_basin_experience": {
                "title": "鄂尔多斯盆地测井解释经验",
                "content": """
## 鄂尔多斯盆地测井解释经验

### 一、储层特征
- 以三叠系延长组为主要含油层系
- 长6、长7、长8为主要产层
- 典型致密砂岩储层：孔隙度6-12%，渗透率0.1-5 mD
- 天然裂缝不发育，需水平井+体积压裂开发

### 二、低阻油层识别（关键难题）
1. **低阻成因**：
   - 高束缚水饱和度（微孔隙发育）
   - 黏土矿物附加导电（伊利石、绿泥石含量高）
   - 地层水矿化度变化
2. **识别方法**：
   - Rt/Rw比值法：低阻油层Rt/Rw仍>3-5
   - 双孔隙度交会：密度-中子差异指示含油性
   - 核磁共振：T2几何均值区分束缚水与可动流体
   - 阵列感应：不同探测深度电阻率差异

### 三、解释参数
- 长6段：a=0.62, m=2.15, n=2.10
- 长7段：a=0.71, m=2.08, n=2.20（页岩油储层参数不同）
- 束缚水饱和度40-60%，有效孔隙度需扣除束缚水

### 四、水平井测井
1. LWD随钻测井为主（GR+RES+DEN+CNL）
2. 水平段地层对比：利用GR曲线与邻井对比
3. 储层钻遇率评价（目标>80%）
4. 地质导向：实时调整井轨迹保持在甜点层内
""",
                "category": "regional_experience"
            },
            "tarim_basin_experience": {
                "title": "塔里木盆地测井解释经验",
                "content": """
## 塔里木盆地测井解释经验

### 一、特殊挑战
- 超深井（>6000m），高温（>160°C）、高压（>100MPa）
- 碳酸盐岩储层为主（奥陶系、志留系）
- 缝洞型储层，非均质性极强
- 钻井液密度高（>1.6g/cm³），井眼条件差

### 二、碳酸盐岩储层测井识别
1. **裂缝识别**：
   - FMI/ARI成像测井：直接观察裂缝产状和密度
   - AC周波跳跃：指示开启裂缝
   - 双侧向电阻率差异：高角度裂缝特征
   - 斯通利波衰减：指示渗透性裂缝
2. **溶洞识别**：
   - DEN急剧减小（溶洞充填物密度低）
   - AC急剧增大或出现周波跳跃
   - 成像测井：圆形/椭圆形暗色区域
   - 井径扩大
3. **缝洞体划分**：
   - I类（缝洞型）：φ>6%，裂缝发育
   - II类（裂缝型）：φ 3-6%，以裂缝为主
   - III类（基质型）：φ<3%，储集性差

### 三、高温测井注意事项
1. 选用耐高温仪器（耐温>175°C）
2. 缩短测井时间，减少仪器在高温段停留
3. 温度对电阻率的影响校正
4. 注意仪器刻度温度与井下温度差异

### 四、油气水识别
- 碳酸盐岩含油性识别困难：
  - 电阻率受裂缝影响大，不能简单用Archie公式
  - 需结合NMR、DSI等多信息综合判断
  - 试油验证极为重要
""",
                "category": "regional_experience"
            },
            # ========== 区域测井特征 (Regional Characteristics) ==========
            "typical_log_responses_china": {
                "title": "中国主要盆地典型储层测井响应特征",
                "content": """
## 中国主要盆地典型储层测井响应特征

### 一、松辽盆地（大庆长垣）
| 层位 | GR(API) | DEN(g/cm³) | CNL(%) | AC(μs/ft) | RT(Ω·m) |
|------|---------|-----------|--------|-----------|---------|
| 萨尔图油层 | 40-70 | 2.20-2.45 | 20-30 | 85-110 | 5-50 |
| 葡萄花油层 | 50-80 | 2.25-2.50 | 18-28 | 80-105 | 3-30 |
| 高台子油层 | 60-90 | 2.30-2.55 | 15-25 | 75-100 | 2-20 |

### 二、渤海湾盆地（胜利油田）
| 层位 | GR(API) | DEN(g/cm³) | CNL(%) | AC(μs/ft) | RT(Ω·m) |
|------|---------|-----------|--------|-----------|---------|
| 东营组 | 40-100 | 2.15-2.50 | 20-32 | 85-120 | 2-20 |
| 沙河街Es2 | 35-80 | 2.20-2.55 | 15-28 | 70-100 | 3-30 |
| 沙河街Es3 | 50-100 | 2.25-2.60 | 12-25 | 65-95 | 2-25 |

### 三、鄂尔多斯盆地（长庆油田）
| 层位 | GR(API) | DEN(g/cm³) | CNL(%) | AC(μs/ft) | RT(Ω·m) |
|------|---------|-----------|--------|-----------|---------|
| 长6段 | 60-100 | 2.40-2.60 | 10-20 | 70-90 | 2-15 |
| 长7段 | 70-120 | 2.45-2.65 | 8-18 | 65-85 | 1.5-10 |
| 长8段 | 55-90 | 2.38-2.58 | 12-22 | 72-92 | 3-20 |

### 四、塔里木盆地（碳酸盐岩）
| 层位 | GR(API) | DEN(g/cm³) | CNL(%) | AC(μs/ft) | RT(Ω·m) |
|------|---------|-----------|--------|-----------|---------|
| 奥陶系灰ite | 10-30 | 2.55-2.75 | 2-8 | 50-65 | 50-500 |
| 奥陶系缝洞 | 20-50 | 2.20-2.55 | 5-15 | 60-90 | 10-100 |

### 五、四川盆地（天然气）
| 层位 | GR(API) | DEN(g/cm³) | CNL(%) | AC(μs/ft) | RT(Ω·m) |
|------|---------|-----------|--------|-----------|---------|
| 须家河组 | 40-80 | 2.40-2.65 | 8-18 | 65-85 | 10-200 |
| 飞仙关组 | 15-40 | 2.50-2.75 | 3-12 | 50-70 | 50-500 |
""",
                "category": "regional_characteristics"
            },
            "overseas_log_characteristics": {
                "title": "海外典型油气区测井响应特征",
                "content": """
## 海外典型油气区测井响应特征

### 一、中东地区
1. **阿拉伯组（Arab Formation, 侏罗系）**：
   - 碳酸盐岩为主（石灰岩/白云岩）
   - 高孔隙度（15-30%），高渗透率
   - GR: 10-40 API, DEN: 2.10-2.55 g/cm³
   - 裂缝-溶洞型储层，需成像测井
2. **Khuff组（二叠系）**：
   - 致密砂岩-碳酸盐岩互层
   - 低渗透率，需压裂
   - GR: 30-70 API, RT: 10-100 Ω·m

### 二、北海地区
1. **Brent群（侏罗系）**：
   - 优质砂岩，三角洲沉积
   - GR: 20-60 API, DEN: 2.15-2.40 g/cm³
   - 孔隙度20-30%，渗透率100-1000 mD
2. **Forties组（古新统）**：
   - 浊积砂岩
   - GR: 30-70 API, 孔隙度15-25%

### 三、西非地区
1. **浊积砂岩**：
   - 深水浊积扇沉积
   - 砂体薄（2-10m），GR: 30-60 API
   - 孔隙度20-30%，但横向变化大
2. **重质油藏**：
   - 高粘度原油，电阻率响应与轻质油不同
   - 需特殊流体识别方法

### 四、中亚地区（哈萨克斯坦）
1. **碳酸盐岩台地**：
   - 类似中东，但温度更低
   - 高矿化度地层水
2. **盐上层系**：
   - 盐丘构造，井眼条件差
   - 需特殊的井眼校正方法
""",
                "category": "regional_characteristics"
            },
            "formation_markers": {
                "title": "区域标志层与地层对比方法",
                "content": """
## 区域标志层识别与地层对比

### 一、标志层识别标准
1. **测井标志层特征**：
   - 岩性稳定、横向分布广
   - 测井响应特征独特、易于识别
   - 常见标志层：凝灰岩、煤层、特殊泥岩段、不整合面
2. **GR曲线标志**：
   - 高GR泥岩段（放射性异常层）
   - 低GR纯砂岩段（区域性纯净砂体）
   - 特殊GR曲线形态（如"圣诞树"形态）

### 二、中国主要盆地标志层
| 盆地 | 标志层 | 测井特征 | 地质意义 |
|------|--------|---------|---------|
| 松辽 | 嫩江组黑色泥岩 | 高GR、高AC | 区域盖层 |
| 渤海湾 | 沙四段盐岩 | 高密度、低GR | 分隔上下油藏 |
| 鄂尔多斯 | 张家滩页岩 | 极高GR、高AC | 长7底界标志 |
| 塔里木 | 良里塔格组 | 特殊GR峰值 | 奥陶系内部标志 |

### 三、地层对比方法
1. **标准层对比法**：以标志层为基准面进行等时对比
2. **旋回对比法**：利用沉积旋回进行层序对比
3. **GR曲线形态对比**：利用GR曲线特征形态进行井间对比
4. **地震-测井联合对比**：合成地震记录进行层位标定

### 四、注意事项
1. 断层会导致地层缺失或重复
2. 不整合面上下地层可能有大的时间间断
3. 相变会导致标志层消失或测井特征改变
4. 需综合多口井信息进行区域对比验证
""",
                "category": "regional_characteristics"
            },
            # ========== 测井解决方案知识 (Logging Solutions) ==========
            "tool_combinations": {
                "title": "测井仪器组合设计与选型",
                "content": """
## 测井仪器组合设计

### 一、常规测井系列
1. **标准九条曲线**：
   - GR（自然伽马）、SP（自然电位）、CAL（井径）
   - RT（深电阻率）、RXO（冲洗带电阻率）
   - DEN（密度）、CNL（补偿中子）、AC（声波）
   - PE（光电效应）
2. **增强型测井系列**：
   - 阵列感应（AIT/HILT）：多深度电阻率
   - 阵列声波（DSI/XMAC）：纵横波、斯通利波
   - 核磁共振（CMR/MRIL）：孔隙度分布、渗透率
   - 元素俘获（ECS/Litho Scanner）：元素含量

### 二、LWD随钻测井系列
1. **基本LWD**：GR + RES + DEN + CNL
2. **增强LWD**：+ NMR + 声波 + 成像
3. **地质导向**：+ 近钻头GR/RES + 方位成像
4. LWD优势：实时监测、减少井眼影响、侵入前测量

### 三、特殊测井项目选型
| 地质问题 | 推荐测井方法 | 目的 |
|---------|-------------|------|
| 裂缝评价 | FMI/ARI + DSI | 裂缝密度、产状、有效性 |
| 地应力 | FMI + DSI + 微压裂 | 最大/最小水平主应力方向 |
| 流体识别 | MDT + NMR | 流体类型、界面、可动性 |
| 岩石力学 | DSI + DEN + CNL | 弹性模量、破裂压力 |
| 剩余油 | C/O + PND-S | 剩余油饱和度分布 |

### 四、测井成本优化
1. 探井：全套测井（含成像、NMR、MDT）
2. 评价井：标准系列 + 关键井段特殊测井
3. 开发井：简化系列，重点监测目的层
4. 利用测井资料可替代性减少测井项目
""",
                "category": "logging_solutions"
            },
            "common_logging_problems": {
                "title": "常见测井问题与解决方案",
                "content": """
## 常见测井问题诊断与解决方案

### 一、井眼问题
1. **井眼扩大（Washout）**：
   - 表现：CAL >> 钻头直径，DEN/CNL偏离正常值
   - 解决：使用井眼校正算法，或参考未受影响曲线
   - 预防：控制泥浆性能，减少浸泡时间
2. **井眼缩径（Mudcake buildup）**：
   - 表现：CAL < 钻头直径，渗透层段泥饼厚
   - 影响：微电阻率受影响，但深探测曲线可用
3. **狗腿/键槽**：
   - 表现：仪器遇阻，某段数据缺失
   - 解决：使用小直径仪器或LWD数据

### 二、泥浆影响
1. **油基泥浆（OBM）**：
   - SP无法使用（无导电通路）
   - 浅电阻率偏高（油基泥浆高阻）
   - 需使用介电测井或核磁共振替代
2. **高矿化度泥浆**：
   - 冲洗带电阻率极低
   - 阵列感应受影响较小（多深度可反演）
3. **重泥浆（含重晶石）**：
   - PE异常偏高
   - DEN偏高（重晶石密度4.5g/cm³）
   - 需使用Litho Density或ECS替代

### 三、仪器问题
1. **仪器偏心**：大斜度/水平井中仪器贴壁不良
   - 解决：使用居中器或偏心校正算法
2. **温度漂移**：高温导致电子元件偏移
   - 解决：分段刻度、温度补偿
3. **源衰减**：放射性源强度随时间减弱
   - 解决：定期更换源、实时监测计数率

### 四、水平井特殊问题
1. 方位效应：上部/下部地层响应不同
2. 轨迹穿层：GR曲线出现"台阶"状变化
3. 需使用方位测井和地质导向技术
""",
                "category": "logging_solutions"
            },
            "advanced_interpretation": {
                "title": "高级测井解释方法与工作流",
                "content": """
## 高级测井解释方法

### 一、多矿物模型（ELAN/OPTIMA）
1. **基本原理**：
   - 将地层分解为多种矿物组分
   - 使用超定方程组求解各组分体积分数
   - 响应方程：测井值 = Σ(矿物体积分数 × 矿物响应值)
2. **常用矿物模型**：
   - 砂岩模型：石英 + 长石 + 黏土 + 方解石 + 孔隙流体
   - 碳酸盐岩模型：方解石 + 白云石 + 黏土 + 硬石膏 + 孔隙流体
   - 泥岩模型：伊利石 + 蒙脱石 + 高岭石 + 绿泥石 + 石英
3. **约束条件**：
   - 各组分体积分数之和 = 1
   - 各组分体积分数 ≥ 0
   - 利用PE约束矿物组合

### 二、饱和度高度函数（SHF）
1. **原理**：Sw = f(height above FWL, rock type)
2. **建立方法**：
   - 利用毛管压力数据（RCAL/SCAL）
   - 建立J函数：J = Pc × √(K/φ) / σcosθ
   - J-Sw关系转化为Sw-高度关系
3. **应用**：
   - 过渡带含水率预测
   - 非均质储层饱和度建模
   - 与测井Sw对比验证

### 三、核磁共振T2谱解释
1. **T2截止值**：区分束缚流体与可动流体
   - 砂岩：T2cutoff ≈ 33ms
   - 碳酸盐岩：T2cutoff ≈ 92ms（双峰分布）
2. **T2谱分析**：
   - 短T2组分：黏土束缚水
   - 中T2组分：毛管束缚水
   - 长T2组分：可动流体（油/气/自由水）
3. **渗透率估算**：
   - SDR模型：K = a × φ^b × T2gm^c
   - Coates模型：K = a × (BVI/FFI)^b × φ^c
   - Timur-Coates模型：K = C × φ^4 / T2cutoff^2

### 四、测井-地震联合反演
1. 利用测井约束地震反演
2. 建立井间属性模型
3. 提高储层预测精度
""",
                "category": "logging_solutions"
            },
            "logging_instruments": {
                "title": "测井仪器知识与技术参数",
                "content": """
## 测井仪器知识

### 一、常规电法测井仪器
| 仪器 | 测量项目 | 精度 | 纵向分辨率 | 探测深度 |
|------|---------|------|-----------|---------|
| 双侧向 (DLL) | LLD/LLS | ±5% | 0.6m | 深/浅 |
| 双感应 (DIL) | ILD/ILM | ±2mS/m | 1.2m | 深/中 |
| 阵列感应 (AIT/HDIL) | 多探测深度电阻率 | ±1mS/m | 0.3m | 0.25-3.0m |
| 微球聚焦 (MSFL) | 冲洗带电阻率 | ±5% | 0.1m | 0.1m |
| 微电极 (ML) | 微电位/微梯度 | - | 0.05m | 浅 |

### 二、声波测井仪器
| 仪器 | 测量项目 | 频率 | 源距 |
|------|---------|------|------|
| 常规声波 (BHC) | 纵波时差 | 20kHz | 0.9-1.5m |
| 长源距声波 (LSS) | 纵波/横波 | 10-20kHz | 2.4-3.0m |
| 阵列声波 (DSI/XMAC) | 全波列 | 多种 | 多种 |
| 偶极声波 | 横波各向异性 | 低频 | - |
| Sonic Scanner | 三维声波 | 多种 | 多种 |

### 三、放射性测井仪器
| 仪器 | 测量项目 | 源/类型 | 精度 |
|------|---------|---------|------|
| 自然伽马 (GR) | 总伽马/SGR/CGR | - | ±5% |
| 自然伽马能谱 (NGS) | K/U/Th/SGR/CGR | - | ±3% |
| 补偿中子 (CNL) | 中子孔隙度 | Am-Be源 | ±0.5pu |
| 岩性密度 (LDT) | 密度/PE | Cs-137源 | ±0.025g/cm³ |
| 三探测器密度 (TLD) | 密度/PE/井眼校正 | Cs-137源 | ±0.015g/cm³ |
| 地球化学 (ECS/GEM) | 元素含量 | Am-Be源+探测器 | ±5% |

### 四、成像测井仪器
| 仪器 | 类型 | 覆盖率 | 垂向分辨率 |
|------|------|--------|-----------|
| FMI | 电阻率成像 | 80% (8in) | 5mm |
| CMI | 电成像 | 60% | 5mm |
| XRMI | 电阻率成像 | 80% | 5mm |
| STAR | 声波成像 | 100% | 5mm |
| CAST | 声波成像 | 100% | 5mm |
| OBMI | 油基泥浆成像 | 32% | 5mm |

### 五、核磁共振(NMR)测井仪器
| 仪器 | 频率 | 回波间隔(TE) | 等待时间(TW) |
|------|------|-------------|-------------|
| CMR | 2MHz | 0.2-0.4ms | 0.5-12s |
| MRIL-Prime | 550-760kHz | 0.6ms | 1-12s |
| MREX | 多种 | 0.36ms | 1-12s |

### 六、地层测试器
| 仪器 | 测量项目 | 泵速 | 取样体积 |
|------|---------|------|---------|
| MDT | 压力/取样/渗透率 | 0.1-60cc/s | 450cc/样 |
| RDT | 压力/取样 | 0.1-40cc/s | 450cc/样 |
| RCI | 压力/取样 | 0.1-30cc/s | 450cc/样 |

### 七、仪器组合建议
1. **常规储层**：双侧向/双感应 + 补偿中子/密度 + 声波 + GR + SP + 井径
2. **复杂岩性**：阵列感应 + 三探测器密度 + 能谱GR + 阵列声波 + PE
3. **裂缝识别**：成像测井 + 偶极声波 + 双侧向
4. **低孔低渗**：核磁共振 + 阵列声波 + 高分辨率阵列感应
5. **流体识别**：地层测试器 + 核磁共振 + 阵列感应
""",
                "category": "logging_geology"
            },
            "logging_geology_basics": {
                "title": "测井地质学基础与应用",
                "content": """
## 测井地质学基础

### 一、测井曲线与沉积环境
| 曲线形态 | 沉积环境 | 解释 |
|---------|---------|------|
| 钟形 (GR向上变细) | 河道/点坝 | 向上变细的河道充填 |
| 漏斗形 (GR向上变粗) | 三角洲前缘/河口坝 | 进积序列 |
| 箱形 (GR突变) | 辫状河/浊积 | 快速沉积，稳定水动力 |
| 齿化箱形 | 曲流河/分流河道 | 交互沉积 |
| 线形 (GR低平直) | 碳酸盐岩台地/礁滩 | 纯净沉积 |
| 锯齿形 | 潮汐/风暴 | 频繁交替 |

### 二、岩性识别规则
| 岩性 | DEN | CNL | AC | PE | GR |
|------|-----|-----|----|----|-----|
| 石英砂岩 | 2.65 | -2~+2 | 55.5 | 1.81 | 20-40 |
| 长石砂岩 | 2.62 | -1~+3 | 53-58 | 2.0-2.5 | 40-80 |
| 岩屑砂岩 | 2.60-2.68 | 5-15 | 55-70 | 2.5-3.5 | 50-100 |
| 灰岩 | 2.71 | 0-3 | 47.5 | 5.08 | 10-30 |
| 白云岩 | 2.87 | 1-5 | 43.5 | 3.14 | 10-25 |
| 硬石膏 | 2.98 | -2~0 | 37.5 | 5.0 | 5-15 |
| 盐岩 | 2.03 | -2~0 | 67 | 4.7 | 0-5 |
| 泥岩/页岩 | 2.40-2.60 | 25-45 | 70-100 | 3.0-4.5 | 80-150 |
| 煤 | 1.20-1.80 | 40-60+ | 100-160 | 0.5-2.0 | 10-30 |
| 玄武岩 | 2.70-3.00 | 8-20 | 50-60 | 2.0-3.5 | 20-80 |

### 三、测井相分析
1. **测井相定义**：能表征地层特征且可与其它井进行对比的一组测井响应特征
2. **测井相要素**：幅度、形态、接触关系、旋回性、光滑程度
3. **常用分析曲线**：GR（最好）、SP、电阻率、密度、声波
4. **交会图技术**：
   - GR-深度：沉积旋回
   - M-N交会图：矿物识别
   - DEN-CNL交会图：岩性/孔隙度
   - DEN-AC交会图：岩性/压实

### 四、层序地层学测井响应
| 体系域 | GR趋势 | 沉积特征 |
|--------|--------|---------|
| 低位体系域 (LST) | 加积→进积 | 盆底扇、斜坡扇 |
| 海侵体系域 (TST) | 退积 | 退积准层序组 |
| 高位体系域 (HST) | 进积→加积 | 三角洲、滨岸 |
| 陆架边缘体系域 (SMST) | 加积 | 陆架边缘三角洲 |
""",
                "category": "logging_geology"
            },
            "regional_experience_database": {
                "title": "区域测井解释经验与参数库",
                "content": """
## 区域测井解释经验与参数库

### 一、中国主要盆地阿尔奇参数
| 盆地/油田 | 层位 | a | m | n | Rw(Ω·m) | 备注 |
|-----------|------|---|---|---|----------|------|
| 松辽盆地 | 扶杨油层 | 0.95 | 1.85 | 1.95 | 0.4-0.8 | 低渗透 |
| 松辽盆地 | 葡萄花 | 1.0 | 1.90 | 2.00 | 0.3-0.6 | 中高渗 |
| 渤海湾盆地 | 沙河街 | 0.85 | 1.95 | 2.00 | 0.2-0.5 | 复杂断块 |
| 鄂尔多斯盆地 | 延长组 | 0.90 | 1.80 | 1.90 | 0.3-0.5 | 特低渗 |
| 准噶尔盆地 | 三叠系 | 0.88 | 1.90 | 2.00 | 0.2-0.4 | 低阻油层 |
| 四川盆地 | 须家河 | 0.95 | 2.05 | 2.10 | 0.1-0.3 | 致密气 |
| 塔里木盆地 | 奥陶系 | 0.80 | 2.20 | 2.10 | 0.02-0.08 | 碳酸盐岩 |
| 柴达木盆地 | 古近系 | 0.90 | 1.90 | 2.00 | 0.3-0.6 | 咸水湖相 |

### 二、主要盆地标志层
| 盆地 | 标志层 | 测井特征 | 应用 |
|------|--------|---------|------|
| 松辽盆地 | 嫩江组泥岩 | GR高平直、RT低 | 区域对比 |
| 渤海湾盆地 | 沙一段生物灰岩 | DEN高、RT高、GR低 | 区域标志 |
| 鄂尔多斯盆地 | 张家滩页岩 | GR极高、AC高 | K1标志层 |
| 四川盆地 | 嘉陵江组膏盐 | DEN高>2.70、GR低 | 区域对比 |

### 三、储层评价标准（不同盆地）
| 盆地 | 储层类型 | Φ下限 | K下限(mD) | Vsh上限 | Sw上限 |
|------|---------|-------|-----------|---------|--------|
| 松辽 | 常规砂岩 | 8% | 1.0 | 0.40 | 0.60 |
| 松辽 | 低渗透 | 6% | 0.1 | 0.35 | 0.55 |
| 鄂尔多斯 | 特低渗 | 5% | 0.05 | 0.30 | 0.55 |
| 塔里木 | 碳酸盐岩 | 3% | 0.01 | 0.20 | 0.50 |
| 准噶尔 | 砾岩 | 7% | 0.5 | 0.40 | 0.55 |
| 四川 | 致密气 | 3% | 0.005 | 0.30 | 0.50 |

### 四、海外典型区域参数
| 区域 | 储层类型 | a | m | n | Φ下限 | 关键特征 |
|------|---------|---|---|---|-------|---------|
| 巴西盐下 | 碳酸盐岩 | 0.8 | 2.2 | 2.1 | 3% | 微生物灰岩 |
| 中东 | 碳酸盐岩 | 0.85 | 2.0 | 2.0 | 5% | 裂缝-孔洞型 |
| 北海 | 碎屑岩 | 0.95 | 1.9 | 2.0 | 8% | 高孔高渗 |
| 西非 | 浊积砂岩 | 0.90 | 1.85 | 2.0 | 7% | 深水沉积 |
| 北美 | 页岩油 | 0.95 | 1.8 | 2.0 | 3% | 有机质丰富 |
| 中亚 | 碳酸盐岩 | 0.82 | 2.1 | 2.05 | 4% | 礁滩相 |

### 五、区域解释经验法则
1. **低阻油层识别**（渤海湾盆地）：Rt<5Ω·m仍需考虑含油，结合Rxo/Rt比值和GR
2. **致密气评价**（四川盆地）：重点看声波和电阻率差值，孔隙度下限可到2%
3. **碳酸盐岩**（塔里木）：裂缝评价靠成像+双侧向差异，溶洞靠井径+密度
4. **火成岩**（松辽深层）：主要靠GR能谱区分岩性，电阻率评价裂缝
5. **盐下碳酸盐岩**（巴西）：硬石膏层是盖层，灰岩段密度降低指示储层
""",
                "category": "regional_experience"
            },
            "logging_solutions_guide": {
                "title": "测井解决方案与问题诊断",
                "content": """
## 测井解决方案与问题诊断

### 一、常见测井解释问题与解决方案
| 问题 | 表现 | 原因分析 | 解决方案 |
|------|------|---------|---------|
| 低阻油层漏判 | Rt<3Ω·m含油 | 高矿化度/高泥质 | 核磁共振/阵列感应/能谱GR |
| 高阻水层误判 | Rt>50Ω·m却是水层 | 致密/钙质胶结 | 声波-电阻率交会/成像 |
| 薄层分辨率低 | 曲线上薄层模糊 | 仪器分辨率不足 | 高分辨率阵列感应/成像 |
| 裂缝评价困难 | 不能确定裂缝有效性 | 裂缝充填/低角度 | 双侧向差异+声波+成像组合 |
| 气层识别不准 | 中子-密度交会模糊 | 挖掘效应/井眼影响 | 核磁共振+声波+密度组合 |
| 复杂岩性混淆 | 矿物模型不收敛 | 矿物组合不确定 | ECS/地球化学+多矿物优化 |
| 页岩油评价 | 传统模型失效 | 有机质/无机质混合 | TOC+核磁+地球化学+地应力 |
| 井眼垮塌 | DEN/PE失真 | 扩径/钻井液侵入 | 井径校正/多曲线对比 |

### 二、特殊储层评价方案
1. **裂缝性储层**：
   - 必备：成像测井 + 双侧向 + 偶极声波
   - 关键：裂缝密度/开度/倾向、双侧向正差异
   - 工作流：裂缝识别→有效缝筛选→裂缝参数计算→产能预测

2. **低孔低渗储层**：
   - 必备：核磁共振 + 阵列声波 + 地层测试
   - 关键：可动流体饱和度、渗透率模型、压力分析
   - 工作流：孔渗建模→可动流体分析→压裂选层

3. **火成岩储层**：
   - 必备：成像 + 能谱GR + 阵列声波 + 地球化学
   - 关键：岩性识别（能谱GR）、裂缝识别（成像）
   - 工作流：岩性识别→裂缝评价→储层分类

4. **页岩油/气储层**：
   - 必备：ECS/地球化学 + 核磁 + 声波扫描
   - 关键：TOC、成熟度、脆性、地应力
   - 工作流：TOC计算→矿物组分→脆性评价→甜点识别

### 三、测井资料质量控制清单
| 检查项 | 方法 | 标准 |
|--------|------|------|
| 深度对齐 | 各曲线深度/响应一致 | ±0.1m |
| 重复曲线 | 两次测量对比 | 相对误差<5% |
| 井径影响 | 扩径段曲线异常 | 井径<16in时基本可用 |
| 泥浆影响 | 对比邻井 | SY/T5132-2012 |
| 刻度检查 | 测前测后刻度 | 仪器厂家标准 |
| 温度影响 | 井底温度校正 | 按地温梯度 |
| 数据完整性 | 缺失段检查 | 缺失<5%为合格 |
""",
                "category": "logging_solutions"
            },
            "well_testing_knowledge": {
                "title": "试油测试与生产测井知识",
                "content": """
## 试油测试与生产测井知识

### 一、试油方法
| 方法 | 适用条件 | 获取参数 | 优点 | 缺点 |
|------|---------|---------|------|------|
| DST (中途测试) | 裸眼/套管 | 压力/产能/流体 | 快速评价 | 时间短 |
| 射孔测试 | 套管井 | 产能/压力/流体 | 精确分层 | 需套管完井 |
| 酸化/压裂后测试 | 低渗透 | 措施效果/产能 | 评价措施效果 | 成本高 |
| 系统试井 | 多油嘴 | 产能方程/IPR | 确定合理产量 | 需要时间 |
| 压力恢复试井 | 关井恢复 | 渗透率/表皮/边界 | 获取储层参数 | 影响生产 |
| 干扰试井 | 多井 | 连通性/导压系数 | 了解井间连通 | 多井配合 |

### 二、试油与测井关系
| 试油类型 | 目的 | 依托测井资料 |
|---------|------|-------------|
| 常规试油 | 验证解释结论 | 电阻率+孔隙度+岩性 |
| 分层测试 | 确定分层产能 | 储层划分+隔层评价 |
| 酸化 | 解除污染 | 岩性+矿物+孔隙度 |
| 压裂 | 改善渗透性 | 地应力+脆性+孔渗 |
| 注水/注气 | 补充能量 | 连通性+物性分析 |

### 三、生产测井 (PLT)
| 仪器 | 测量参数 | 应用 |
|------|---------|------|
| 流量计 | 各层产量 | 分层产量分配 |
| 持水率计 | 含水率 | 含水层识别 |
| 密度计 | 流体密度 | 流体性质 |
| 温度计 | 温度剖面 | 产层/漏失层识别 |
| 压力计 | 压力剖面 | 压力分析 |
| RST/RPM | 剩余油饱和度 | 油层动用程度 |
| 噪声测井 | 声波噪声 | 窜槽/管外流 |

### 四、试油数据与测井解释的标定
1. **参数修正**：
   - 根据试油结果反推阿尔奇参数 (a, m, n)
   - 修正渗透率计算模型系数
   - 确定储层下限 (Φ, Vsh, Sw)
2. **解释图版更新**：
   - 电阻率-孔隙度交会图
   - Sw-高度关系曲线
   - Pickett交会图
3. **经验积累**：
   - 建立区域解释标准
   - 形成试油-测井对应关系库
   - 指导后续井解释

### 五、生产信息与测井关联
| 生产指标 | 测井关联参数 | 分析目的 |
|---------|-------------|---------|
| 日产油 | Φ/K/Sw/厚度 | 产能预测精度验证 |
| 含水率 | Sw/束缚水饱和度 | 可动水与束缚水 |
| 累计产量 | 储量参数 | 动态储量复核 |
| 递减曲线 | 渗透率/导压系数 | 递减规律分析 |
| 见水时间 | 底水锥进/边水推进 | 水锥风险预测 |
""",
                "category": "well_testing"
            },
            "brazil_evaporite_sequence": {
                "title": "巴西蒸发岩-碳酸盐岩地层序列与解释经验",
                "content": """
## 巴西蒸发岩-碳酸盐岩地层序列

### 一、地层序列（自上而下）
1. **盐岩段（Halite）** — 蒸发岩顶部，厚层盐岩
2. **硬石膏段（Anhydrite）** — 过渡层，硬石膏为主
3. **碳酸盐岩段（Carbonate）** — 灰岩为主，夹白云岩

### 二、关键岩性识别特征

#### 盐岩（Halite/NaCl）
| 曲线 | 典型值 | 说明 |
|------|--------|------|
| 密度 DEN | 2.03 g/cm³ | 远低于所有硅酸盐/碳酸盐矿物 |
| 中子 CNL | 0~3% | 极低，接近零 |
| 声波 AC | 67 μs/ft | 高于灰岩(47.5)、白云岩(43.5) |
| PE | 4.7 b/e | 中等偏高 |
| GR | 0~5 API | 极低，无明显放射性 |
| 电阻率 RT | 极高 | 盐岩是绝缘体，电阻率极高 |

#### 硬石膏（Anhydrite/CaSO₄）
| 曲线 | 典型值 | 说明 |
|------|--------|------|
| 密度 DEN | 2.98 g/cm³ | 所有常见蒸发岩/碳酸盐岩中最重 |
| 中子 CNL | -2~0% | 极低，接近零 |
| 声波 AC | 37.5 μs/ft | 所有常见矿物中最快 |
| PE | 5.0 b/e | 高PE，强碳酸盐/蒸发岩信号 |
| GR | 10~20 API | 低 |

#### 灰岩（Limestone/CaCO₃）
| 曲线 | 典型值 | 说明 |
|------|--------|------|
| 密度 DEN | 2.71 g/cm³ | 灰岩骨架密度 |
| 中子 CNL | 0% | 石灰岩中子孔隙度零线 |
| 声波 AC | 47.5 μs/ft | |
| PE | 5.08 b/e | 高PE，碳酸盐岩特征 |
| GR | 10~30 API | 低 |

### 三、解释注意事项

1. **剖面类型判定**：
   - 本区为蒸发岩-碳酸盐岩序列，不应判为砂泥岩剖面
   - 盐岩段密度2.03远低于砂岩(2.65)，DEN-AC交会图不应使用砂泥岩聚类
   - 建议全程按碳酸盐岩/蒸发岩剖面处理

2. **盐岩段识别关键**：
   - 密度 < 2.20 g/cm³ 是盐岩的硬识别条件
   - 结合GR极低（<10 API）、高声波、极高电阻率确认
   - 盐岩非储层，不应参与储层评价

3. **硬石膏与灰岩区分**：
   - 硬石膏密度(2.98)明显高于灰岩(2.71)
   - 硬石膏声波(37.5)明显低于灰岩(47.5)
   - 硬石膏PE(5.0)与灰岩PE(5.08)接近，不能单靠PE区分

4. **碳酸盐岩段解释**：
   - 硬石膏之下为灰岩为主夹白云岩
   - 孔隙度由裂缝和溶蚀孔洞贡献
   - 电阻率高低取决于孔隙发育程度和流体性质
   - 致密灰岩段密度~2.71，中子≈0，声波~47.5，电阻率可达数千Ω·m

5. **储层下限参考**：
   - 碳酸盐岩孔隙度下限：3~6%
   - 裂缝性储层需结合FMI/成像资料

6. **矿物模型建议**：
   - 蒸发岩段矿物：Halite + Anhydrite + Calcite + Dolomite + Clay
   - 碳酸盐岩段矿物：Calcite + Dolomite + Anhydrite + Quartz + Clay
   - 四种常见矿物附加盐岩（Halite）

### 四、Halite矿物响应参数（用于多矿物优化模型）
- DEN: 2.03 g/cm³
- CNL: 0.0（小数）
- AC: 67.0 μs/ft
- PE: 4.7 b/e
- GR: 5 API
""",
                "category": "regional_characteristics"
            },
            "brazil_logging_interpretation_params": {
                "title": "巴西地区测井解释参数建议",
                "content": """
## 巴西地区测井解释参数

### 一、阿尔奇公式参数
- a = 0.8~1.0（碳酸盐岩）
- m = 2.0~2.2（碳酸盐岩胶结指数偏高）
- n = 2.0~2.1
- Rw = 根据实测水分析确定

### 二、储层下限标准
- 碳酸盐岩孔隙度下限：3~6%（裂缝型可降至3%）
- 泥质含量上限：VSH < 0.25
- 含水饱和度上限：Sw < 60%

### 三、非储层识别
- 盐岩：密度~2.03，GR<10，非储层
- 硬石膏：密度~2.98，AC~37.5，非储层
- 致密灰岩：密度~2.71，中子≈0，RT极高，非储层（孔隙度<下限）

### 四、油气层识别要点
- 灰岩段密度降低（<2.68），中子降低（气层低"挖掘效应"）
- 电阻率升高（与邻层水层对比）
- 声波略增大（孔隙发育）
- 结合气测显示和泥浆录井
""",
                "category": "regional_experience"
            },
            # ========== 蒸发岩综合识别知识 ==========
            "evaporite_three_factor_framework": {
                "title": "蒸发岩三要素综合识别框架：沉积环境+岩性+测井响应",
                "content": """
## 蒸发岩三要素综合识别框架

蒸发岩（盐岩、石膏、硬石膏）的识别必须综合考虑沉积环境、岩性上下文和测井响应三个维度，不能仅凭单一测井参数异常就下结论。

### 一、核心原则
蒸发岩是近纯矿物，各测井参数必须同时落入紧密窗口，单参数宽松决不允许触发识别。

### 二、三维度评估模型

#### 维度1：沉积环境评估（GR + VSH → 沉积相判别）
| GR+VSH组合 | 沉积相 | 蒸发岩可能性 | 得分系数 |
|------------|--------|------------|----------|
| GR<50, VSH<0.3 | 河道/水下分流河道 | 无 | ×0.15 |
| GR<70, VSH<0.4 | 河道边缘/河口坝 | 低 | ×0.3 |
| GR>130, VSH>0.5 | 泛滥平原/泥坪 | 极低 | ×0.2 |
| GR>100, VSH>0.4 | 过渡带/天然堤 | 低 | ×0.4 |
| GR 50-100, VSH 0.3-0.5 | 局限海/过渡环境 | 中等 | ×0.6 |
| GR<40, VSH<0.2, RT>200 | 局限海台地/潟湖 | 高 | 提升至0.6 |

#### 维度2：岩性上下文（密度-声波交汇）
| DEN-AC组合 | 岩性判断 | 蒸发岩可能性 |
|------------|--------|------------|
| DEN 2.40-2.70, AC 50-80 | 典型砂岩 | 低（×0.3） |
| DEN<2.40, AC>65 | 高孔隙度砂岩 | 低（×0.4） |
| DEN>2.85, AC<55 | 硬石膏/致密碳酸盐岩 | 高（提升至0.5） |

#### 维度3：测井响应一致性
| 参数组合 | 指示 | 得分影响 |
|----------|------|----------|
| DEN<2.40, AC>75 | 高孔隙度砂岩或井眼影响 | ×0.3 |
| DEN<2.50, AC>70, RT>100 | 致密砂岩/气层 | ×0.4 |

### 三、环境得分→阈值调制机制
环境得分（0-1）不绝对跳过检测，而是动态调制确认阈值：

| 环境得分 | 盐岩阈值 | 硬石膏阈值 | 石膏阈值 | 含义 |
|----------|---------|-----------|---------|------|
| >0.6 | 4.5 | 3.5 | 3.5 | 环境支持，较宽松 |
| 0.3-0.6 | 5.5 | 4.5 | 4.0 | 环境一般 |
| <0.3 | 7.0 | 6.0(+GR惩罚) | 5.5 | 环境不利，需极强证据 |

### 四、井级别基础得分
- 砂泥岩剖面：base=0.05（阈值极严格，但不绝对跳过）
- 碳酸盐岩剖面：base=0.6（可能伴生蒸发岩）
- 全井RT/DEN统计辅助调整

### 五、关键设计思想
1. 不绝对跳过：即使砂泥岩剖面，物理证据充分时仍可认定
   - 大段密度~2.85+低阻+低GR+低中子 → 硬石膏
   - 大段密度<2.2+低阻+扩径 → 盐岩
2. 碳酸盐岩剖面同理：大段砂泥岩特征也不应误判为蒸发岩
3. 岩性和沉积环境必须根据大段沉积环境综合判断
""",
                "category": "logging_solutions"
            },
            "special_mineral_log_response": {
                "title": "特殊矿物测井响应特征与识别标准",
                "content": """
## 特殊矿物测井响应特征表

### 一、蒸发岩矿物测井响应参数

| 矿物 | 密度(g/cm³) | 声波AC(μs/ft) | 中子CNL(%) | PE(b/e) | GR(API) | 电阻率 | 井径 |
|------|------------|--------------|-----------|---------|---------|--------|------|
| 盐岩 Halite | 2.03 | 67 | 0~3 | 4.7 | 0~5 | 极低(<50) | 扩径>1.1 |
| 石膏 Gypsum | 2.32 | 52 | 35~49 | 3.99 | <50 | 低(<50) | 轻微扩径 |
| 硬石膏 Anhydrite | 2.98 | 50 | -2~0 | 5.0 | 10~20 | 高(>100) | 正常 |

### 二、其他特殊矿物

| 矿物 | 密度(g/cm³) | 声波AC(μs/ft) | 中子CNL(%) | PE(b/e) | GR(API) | 电阻率 |
|------|------------|--------------|-----------|---------|---------|--------|
| 煤层 Coal | <1.6 | >105 | >40 | 1~2 | 20~80 | 低(<100) |
| 黄铁矿 Pyrite | >3.5 | 30~50 | 0~5 | >10 | <30 | 中-高 |

### 三、盐岩识别关键条件（六项必须同时满足）
1. 密度窗口：1.95 < DEN < 2.40（纯盐岩2.03）
2. 声波窗口：60 < AC < 75（纯盐岩67）
3. 中子窗口：-8 < CNL < 8（纯盐岩~0）
4. 低GR：< 40 API（蒸发岩无放射性）
5. 低电阻率：< 50 Ω·m（盐岩导电）
6. 明显扩径：CAL/BIT > 1.1（盐岩溶解导致扩径）

**联合排除条件**：AC>78 且 CNL>5 → 直接排除盐岩
- 盐岩AC~67，AC>78说明是高孔隙度砂岩或井眼影响
- 盐岩中子~0，CNL>5说明含氢指数偏高

### 四、硬石膏识别关键条件
1. 密度 > 2.85 g/cm³（超过所有砂泥岩和灰岩）
2. 电阻率 > 100 Ω·m（致密无孔，高阻）
3. 低声波 < 55 μs/ft（硬石膏AC约50）
4. 低GR < 40 API
5. 高PE > 4.0 b/e

### 五、石膏识别关键条件（四项必须同时满足）
1. 密度窗口：2.20-2.45 g/cm³
2. 极高中子：CNL > 35%（结晶水特征，石膏独有）
3. 声波窗口：45-60 μs/ft
4. 低GR：< 50 API

### 六、易混淆情况与区分

#### 砂岩 vs 盐岩
- 砂岩孔隙度20%时密度=2.12，与盐岩(2.03)接近
- 关键区分：砂岩AC高(>75)，盐岩AC低(~67)
- 关键区分：砂岩无扩径，盐岩必然扩径
- 关键区分：砂岩中子可高可低，盐岩中子极低

#### 硬石膏 vs 致密灰岩
- 硬石膏密度(2.98)明显高于灰岩(2.71)
- 硬石膏声波(50)低于灰岩(47.5)
- 需结合PE和区域地质背景

#### 砂岩(井眼影响) vs 盐岩
- 砂泥岩剖面中低密度可能是井眼影响而非盐岩
- 必须检查扩径：无扩径→不是盐岩
- 必须检查电阻率：高阻→不是盐岩
- 必须检查声波+中子：AC>78且CNL>5→不是盐岩
""",
                "category": "logging_solutions"
            },
            "sand_shale_evaporite_misidentification_prevention": {
                "title": "砂泥岩剖面蒸发岩误判防范策略",
                "content": """
## 砂泥岩剖面蒸发岩误判防范策略

### 一、问题背景
砂泥岩剖面（河道、三角洲、泛滥平原沉积）中，以下情况容易导致蒸发岩误判：
1. 井眼影响导致密度偏低 → 误判为盐岩
2. 致密砂岩密度高+高阻 → 误判为硬石膏
3. 局部测井异常点触发单参数阈值

### 二、核心防范策略

#### 策略1：环境得分调制阈值（非绝对跳过）
- 砂泥岩剖面基础得分=0.05（极低）
- 盐岩确认阈值从5.5提高至7.0（需要几乎所有条件完美匹配）
- 硬石膏确认阈值从4.5提高至6.0+1.0(GR惩罚)
- 石膏确认阈值从4.0提高至5.5

#### 策略2：强制物理门槛不可绕过
即使环境不利，以下物理门槛仍必须满足：
- 盐岩：必须扩径(CAL/BIT>1.1) + 低阻(RT<50) + 密度<2.40
- 硬石膏：必须密度>2.85 + 高阻(RT>100)
- 石膏：必须中子>35(结晶水) + 密度2.20-2.45

#### 策略3：声波+中子联合排除
- AC>78 且 CNL>5 → 直接排除盐岩
- 盐岩AC~67、中子~0，两者同时偏高说明是砂岩或井眼影响

#### 策略4：大段一致性检查
- 蒸发岩应是大段连续出现，不是零星几个深度点
- 砂泥岩剖面中个别点的密度异常通常是井眼影响
- 需要连续多段（至少>5m）满足条件才考虑蒸发岩

### 三、碳酸盐岩剖面反向约束
碳酸盐岩剖面中划分大段砂泥岩时同样需要谨慎：
- 碳酸盐岩剖面基础得分=0.6（蒸发岩可能性较高）
- 如果大段表现为低GR+低VSH+中等密度+高声波 → 典型砂岩特征
- 此时不应因剖面类型而强行判为蒸发岩

### 四、实际案例

#### TrakesKE-1井误判分析
- 问题：盐岩和硬石膏解释明显错误
- 原因：砂泥岩剖面中井眼影响导致低密度，被误判为盐岩
- 实际特征：低阻但无扩径，高阻但密度不够（应是砂岩）
- 沉积环境：河道、三角洲、泛滥平原 → 不会沉积蒸发岩
- 修复后：env_score ≈ 0.002 < 0.15，所有蒸发岩直接排除

### 五、总结
岩性识别必须综合考虑沉积环境和岩性和测井响应三个维度：
1. 沉积环境决定可能性（河道不会沉积盐岩）
2. 岩性上下文提供约束（DEN-AC交汇判断砂岩vs蒸发岩）
3. 测井响应确认一致性（各参数必须自洽地指向同一结论）
""",
                "category": "logging_solutions"
            }
        }
    
    def get_knowledge(self, key):
        """获取指定知识条目"""
        return self.knowledge_base.get(key)
    
    def get_all_knowledge(self):
        """获取所有内置知识"""
        return list(self.knowledge_base.values())
    
    def search_knowledge(self, query):
        """搜索内置知识"""
        results = []
        query_lower = query.lower()
        for key, knowledge in self.knowledge_base.items():
            if (query_lower in knowledge["title"].lower() or 
                query_lower in knowledge["content"].lower()):
                results.append(knowledge)
        return results


# ------------------------------
# 地区地质特征自动检测器
# ------------------------------
class RegionDetector:
    """基于测井曲线统计特征自动检测地区地质背景
    
    通过分析曲线数值的统计分布，匹配已知的地质特征签名，
    自动识别盐岩、蒸发岩、碳酸盐岩等地区特征，并关联到
    BuiltInKnowledge 中的地区知识条目。
    """
    
    # 地质特征签名库（基于曲线统计值的特征模式）
    # 每个签名定义了条件组合，匹配后关联到知识条目
    GEOLOGICAL_SIGNATURES = {
        "brazil_evaporite_carbonate": {
            "name": "巴西蒸发岩-碳酸盐岩序列",
            "description": "盐岩→硬石膏→灰岩/白云岩的蒸发岩-碳酸盐岩序列",
            "conditions": {
                # 必须同时满足至少N个条件才算匹配
                "min_match": 3,
                "rules": [
                    {
                        "id": "salt_low_density",
                        "curve": "DEN",
                        "description": "存在极低密度段（盐岩特征，DEN~2.03）",
                        "stat": "q10",      # 第10百分位
                        "operator": "<",
                        "value": 2.20
                    },
                    {
                        "id": "salt_low_gr",
                        "curve": "GR",
                        "description": "存在极低GR段（盐岩/硬石膏特征，GR<10）",
                        "stat": "q10",
                        "operator": "<",
                        "value": 15
                    },
                    {
                        "id": "anhydrite_high_density",
                        "curve": "DEN",
                        "description": "存在高密度段（硬石膏特征，DEN>2.95）",
                        "stat": "q90",
                        "operator": ">",
                        "value": 2.90
                    },
                    {
                        "id": "carbonate_high_density",
                        "curve": "DEN",
                        "description": "密度中位数>2.68（碳酸盐岩剖面，排除砂泥岩）",
                        "stat": "q50",
                        "operator": ">",
                        "value": 2.68
                    },
                    {
                        "id": "carbonate_high_pe",
                        "curve": "PE",
                        "description": "PE中位数>3.0（碳酸盐岩信号）",
                        "stat": "q50",
                        "operator": ">",
                        "value": 3.0
                    },
                    {
                        "id": "salt_high_ac",
                        "curve": "AC",
                        "description": "声波存在高值段（盐岩/孔隙发育，AC>65）",
                        "stat": "q90",
                        "operator": ">",
                        "value": 65
                    },
                    {
                        "id": "carbonate_low_ac",
                        "curve": "AC",
                        "description": "声波中位数<55（偏碳酸盐岩范围）",
                        "stat": "q50",
                        "operator": "<",
                        "value": 55
                    },
                    {
                        "id": "anhydrite_very_low_ac",
                        "curve": "AC",
                        "description": "声波存在极低段（硬石膏AC~37.5）",
                        "stat": "q10",
                        "operator": "<",
                        "value": 42
                    }
                ]
            },
            "linked_knowledge": [
                "brazil_evaporite_sequence",
                "brazil_logging_interpretation_params"
            ],
            "auto_tags": ["巴西", "Brazil", "蒸发岩", "盐岩", "硬石膏", "碳酸盐岩",
                          "halite", "anhydrite", "evaporite", "pre-salt"]
        },
        "carbonate_dominant": {
            "name": "碳酸盐岩为主剖面",
            "description": "灰岩/白云岩为主的碳酸盐岩剖面，少量砂泥岩",
            "conditions": {
                "min_match": 2,
                "rules": [
                    {
                        "id": "den_high",
                        "curve": "DEN",
                        "description": "密度中位数>2.68",
                        "stat": "q50", "operator": ">", "value": 2.68
                    },
                    {
                        "id": "pe_high",
                        "curve": "PE",
                        "description": "PE中位数>3.0",
                        "stat": "q50", "operator": ">", "value": 3.0
                    },
                    {
                        "id": "gr_low",
                        "curve": "GR",
                        "description": "GR中位数<60",
                        "stat": "q50", "operator": "<", "value": 60
                    },
                    {
                        "id": "ac_low",
                        "curve": "AC",
                        "description": "声波中位数<60",
                        "stat": "q50", "operator": "<", "value": 60
                    }
                ]
            },
            "linked_knowledge": [],
            "auto_tags": ["碳酸盐岩", "灰岩", "白云岩", "carbonate", "limestone", "dolomite"]
        },
        "sand_shale_dominant": {
            "name": "砂泥岩为主剖面",
            "description": "砂岩/泥岩为主的碎屑岩剖面",
            "conditions": {
                "min_match": 3,
                "rules": [
                    {
                        "id": "den_sand_range",
                        "curve": "DEN",
                        "description": "密度中位数在2.40-2.68范围",
                        "stat": "q50", "operator": "between", "value": [2.40, 2.68]
                    },
                    {
                        "id": "gr_moderate",
                        "curve": "GR",
                        "description": "GR范围较宽（砂泥岩互层），极差>40",
                        "stat": "range", "operator": ">", "value": 40
                    },
                    {
                        "id": "pe_low",
                        "curve": "PE",
                        "description": "PE中位数<3.0",
                        "stat": "q50", "operator": "<", "value": 3.0
                    },
                    {
                        "id": "ac_moderate",
                        "curve": "AC",
                        "description": "声波中位数在55-90范围",
                        "stat": "q50", "operator": "between", "value": [55, 90]
                    }
                ]
            },
            "linked_knowledge": [],
            "auto_tags": ["砂泥岩", "碎屑岩", "砂岩", "泥岩", "sandstone", "shale"]
        }
    }
    
    # 曲线别名映射（用于匹配LAS文件中的不同列名）
    CURVE_ALIASES = {
        'DEN': ['den', 'rho', 'rhob', 'rhoz', 'rhom', 'drho', 'zden', 'lden', 'density',
                'dens', 'RHOZ', 'RHOB', 'RHO', 'DEN', 'ZDEN'],
        'GR': ['gr', 'gamma', 'sgr', 'cgr', 'ecgr', 'hcgr', 'gr_edtc', 'GR', 'SGR', 'CGR',
               'GAMMA', 'GR_EDTC', 'ECGR', 'HCGR'],
        'PE': ['pe', 'pef', 'pefz', 'phot', 'PE', 'PEF', 'PEFZ', 'PHOT'],
        'AC': ['ac', 'dt', 'dtc', 'dt24', 'dtsm', 'dtp', 'dts', 'acoustic',
               'AC', 'DT', 'DTC', 'DT24', 'DTSM', 'DTP', 'DTS', 'ACOUSTIC',
               'slowness'],
        'CNL': ['cnl', 'nphi', 'tnph', 'npor', 'neu', 'neut', 'neutron',
                'CNL', 'NPHI', 'TNPH', 'NPOR', 'NEU', 'NEUT', 'NEUTRON'],
        'RT': ['rt', 'rild', 'rlld', 'rdeep', 'rla5', 'at90', 'af90',
               'RT', 'RILD', 'RLLD', 'RDEEP', 'RLA5', 'AT90', 'AF90'],
        'CAL': ['cal', 'cal1', 'cal2', 'bs', 'bit', 'hd',
                'CAL', 'CAL1', 'CAL2', 'BS', 'BIT', 'HD']
    }
    
    def __init__(self):
        self.detection_history = {}  # 记录已检测过的文件和结果
        self.detected_regions = {}   # 汇总的检测结果
    
    def _find_curve_column(self, columns, target_curve):
        """在列名列表中查找匹配目标曲线的列"""
        aliases = self.CURVE_ALIASES.get(target_curve, [target_curve.lower()])
        for col in columns:
            col_lower = col.lower().strip()
            col_upper = col.upper().strip()
            for alias in aliases:
                if col_lower == alias.lower() or col_upper == alias.upper():
                    return col
        # 模糊匹配
        for col in columns:
            col_lower = col.lower().strip()
            for alias in aliases:
                if alias.lower() in col_lower or col_lower in alias.lower():
                    return col
        return None
    
    def _compute_curve_stats(self, values):
        """计算曲线值的统计信息"""
        if values is None or len(values) == 0:
            return {}
        
        import numpy as np
        valid = values[np.isfinite(values) & (values > -999)]
        if len(valid) < 10:
            return {}
        
        return {
            'q10': float(np.percentile(valid, 10)),
            'q25': float(np.percentile(valid, 25)),
            'q50': float(np.percentile(valid, 50)),
            'q75': float(np.percentile(valid, 75)),
            'q90': float(np.percentile(valid, 90)),
            'mean': float(np.mean(valid)),
            'std': float(np.std(valid)),
            'min': float(np.min(valid)),
            'max': float(np.max(valid)),
            'range': float(np.max(valid) - np.min(valid)),
            'count': len(valid)
        }
    
    def _check_rule(self, stats, rule):
        """检查单条规则是否匹配"""
        curve = rule['curve']
        stat_name = rule['stat']
        operator = rule['operator']
        value = rule['value']
        
        if curve not in stats or not stats[curve]:
            return False
        
        curve_stat = stats[curve].get(stat_name)
        if curve_stat is None:
            return False
        
        if operator == '<':
            return curve_stat < value
        elif operator == '>':
            return curve_stat > value
        elif operator == '<=':
            return curve_stat <= value
        elif operator == '>=':
            return curve_stat >= value
        elif operator == 'between':
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return value[0] <= curve_stat <= value[1]
            return False
        else:
            return False
    
    def detect_from_las_data(self, df, file_path=None):
        """从测井数据DataFrame检测地质特征
        
        Args:
            df: pandas DataFrame，包含测井曲线数据
            file_path: 文件路径（用于记录检测历史）
            
        Returns:
            dict: 检测结果，包含 matched_signatures, detected_tags, linked_knowledge
        """
        import numpy as np
        
        columns = list(df.columns)
        
        # 1. 提取各曲线的有效数据并计算统计
        curve_stats = {}
        for target_curve in ['DEN', 'GR', 'PE', 'AC', 'CNL', 'RT', 'CAL']:
            col = self._find_curve_column(columns, target_curve)
            if col:
                values = df[col].values
                curve_stats[target_curve] = self._compute_curve_stats(values)
        
        if not curve_stats:
            return {'matched_signatures': [], 'detected_tags': [], 'linked_knowledge': [], 'confidence': 0}
        
        # 2. 匹配地质特征签名
        matched = []
        all_tags = []
        all_knowledge = []
        
        for sig_id, signature in self.GEOLOGICAL_SIGNATURES.items():
            conditions = signature['conditions']
            min_match = conditions['min_match']
            rules = conditions['rules']
            
            matched_count = 0
            matched_rules = []
            for rule in rules:
                if rule['curve'] in curve_stats and self._check_rule(curve_stats, rule):
                    matched_count += 1
                    matched_rules.append(rule['id'])
            
            if matched_count >= min_match:
                confidence = min(1.0, matched_count / len(rules) + 0.2)
                matched.append({
                    'signature_id': sig_id,
                    'name': signature['name'],
                    'description': signature['description'],
                    'confidence': round(confidence, 2),
                    'matched_rules': matched_rules,
                    'total_rules': len(rules),
                    'matched_count': matched_count
                })
                all_tags.extend(signature.get('auto_tags', []))
                all_knowledge.extend(signature.get('linked_knowledge', []))
        
        # 去重
        all_tags = list(dict.fromkeys(all_tags))
        all_knowledge = list(dict.fromkeys(all_knowledge))
        
        # 3. 记录检测历史
        if file_path:
            self.detection_history[file_path] = {
                'timestamp': datetime.now().isoformat(),
                'matched': matched,
                'curve_count': len(curve_stats)
            }
        
        result = {
            'matched_signatures': matched,
            'detected_tags': all_tags,
            'linked_knowledge': all_knowledge,
            'curve_stats_summary': {
                curve: {k: stats[k] for k in ['q10', 'q50', 'q90', 'mean', 'range', 'count']}
                for curve, stats in curve_stats.items() if stats
            },
            'confidence': round(
                sum(m['confidence'] for m in matched) / max(1, len(matched)), 2
            ) if matched else 0
        }
        
        # 汇总
        if matched:
            top_sig = matched[0]['signature_id']
            if top_sig not in self.detected_regions:
                self.detected_regions[top_sig] = {'count': 0, 'files': []}
            self.detected_regions[top_sig]['count'] += 1
            if file_path:
                self.detected_regions[top_sig]['files'].append(file_path)
        
        return result
    
    def detect_from_file(self, file_path):
        """从LAS/CSV/XLSX文件检测地质特征
        
        Args:
            file_path: LAS/CSV/XLSX文件路径
            
        Returns:
            dict: 检测结果
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        # 仅支持数据文件
        if ext not in ['.las', '.csv', '.xlsx', '.xls']:
            return None
        
        try:
            import pandas as pd
            
            if ext == '.las':
                try:
                    import lasio
                    las = lasio.read(file_path)
                    df = las.df()
                    if df.empty:
                        return None
                except ImportError:
                    return None
                except Exception:
                    return None
            elif ext == '.csv':
                df = pd.read_csv(file_path)
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path)
            else:
                return None
            
            return self.detect_from_las_data(df, file_path)
            
        except Exception:
            return None
    
    def detect_from_text(self, content):
        """从文本内容中检测地区地质特征
        
        解析文本中可能包含的曲线数值描述，如"密度~2.03"、"DEN<2.20"等，
        用于从文档/报告/解释文本中提取地质特征线索。
        
        Args:
            content: 文本内容
            
        Returns:
            dict: 检测结果
        """
        import re
        
        matched_signatures = []
        
        # 文本模式匹配
        text_patterns = {
            'salt_density': {
                'patterns': [
                    r'(密度|DEN|den|rho)\s*[~≈<≤]\s*2\\.?[01]\\d',
                    r'(密度|DEN|den|rho)\s*(约|大约|约为|在|为)\\s*2\\.0\\d',
                    r'density\s*[~≈<≤]\s*2\\.?[01]\\d'
                ],
                'signature': 'brazil_evaporite_carbonate',
                'confidence': 0.5
            },
            'anhydrite_density': {
                'patterns': [
                    r'(密度|DEN|den|rho)\s*[~≈>]\s*2\\.9[0-9]',
                    r'(硬石膏|anhydrite)',
                    r'density\s*[~≈>]\s*2\\.9[0-9]'
                ],
                'signature': 'brazil_evaporite_carbonate',
                'confidence': 0.4
            },
            'carbonate_keywords': {
                'patterns': [
                    r'(灰岩|石灰岩|白云岩|碳酸盐岩)',
                    r'(巴西|Brazil|brazil).*(蒸发岩|盐岩|硬石膏|碳酸盐岩)',
                    r'(蒸发岩|盐岩|硬石膏).*(巴西|Brazil|brazil)',
                    r'(limestone|dolomite|carbonate).*(salt|halite|anhydrite|evaporite)'
                ],
                'signature': 'brazil_evaporite_carbonate',
                'confidence': 0.6
            }
        }
        
        all_tags = []
        all_knowledge = []
        signature_map = {}
        
        for pattern_id, pattern_info in text_patterns.items():
            for pattern in pattern_info['patterns']:
                if re.search(pattern, content, re.IGNORECASE):
                    sig_id = pattern_info['signature']
                    if sig_id not in signature_map:
                        signature_map[sig_id] = {
                            'id': pattern_id,
                            'signature_id': sig_id,
                            'confidence': 0,
                            'count': 0,
                            'text_evidence': []
                        }
                    # 取最高置信度
                    sig_info = signature_map[sig_id]
                    sig_info['confidence'] = max(sig_info['confidence'], pattern_info['confidence'])
                    sig_info['count'] += 1
                    sig_info['text_evidence'].append(pattern)
                    break
        
        for sig_id, sig_info in signature_map.items():
            sig_def = self.GEOLOGICAL_SIGNATURES.get(sig_id, {})
            # 文本匹配置信度打折
            confidence = min(0.7, sig_info['confidence'] * (0.5 + 0.1 * sig_info['count']))
            matched_signatures.append({
                'signature_id': sig_id,
                'name': sig_def.get('name', sig_id),
                'confidence': round(confidence, 2),
                'source': 'text_pattern',
                'evidence': sig_info['text_evidence'][:3]
            })
            all_tags.extend(sig_def.get('auto_tags', []))
            all_knowledge.extend(sig_def.get('linked_knowledge', []))
        
        all_tags = list(dict.fromkeys(all_tags))
        all_knowledge = list(dict.fromkeys(all_knowledge))
        
        return {
            'matched_signatures': matched_signatures,
            'detected_tags': all_tags,
            'linked_knowledge': all_knowledge,
            'source': 'text_analysis',
            'confidence': round(
                sum(m['confidence'] for m in matched_signatures) / max(1, len(matched_signatures)), 2
            ) if matched_signatures else 0
        }
    
    def get_recommendations(self, detection_result):
        """根据检测结果生成知识推荐
        
        Args:
            detection_result: detect_from_las_data 或 detect_from_file 的返回结果
            
        Returns:
            list: 推荐的知识条目
        """
        if not detection_result or not detection_result.get('linked_knowledge'):
            return []
        
        builtin = BuiltInKnowledge()
        recommendations = []
        for knowledge_key in detection_result['linked_knowledge']:
            entry = builtin.get_knowledge(knowledge_key)
            if entry:
                recommendations.append({
                    'key': knowledge_key,
                    'title': entry['title'],
                    'relevance': 'high',
                    'category': entry.get('category', 'unknown')
                })
        
        return recommendations
    
    def generate_detection_report(self, detection_result):
        """生成人类可读的检测报告
        
        Args:
            detection_result: 检测结果
            
        Returns:
            str: Markdown格式的报告
        """
        if not detection_result:
            return "未检测到地区地质特征。"
        
        lines = ["## 地区地质特征自动检测报告", ""]
        
        matched = detection_result.get('matched_signatures', [])
        if not matched:
            lines.append("**未匹配到已知地质特征签名。**")
            if detection_result.get('curve_stats_summary'):
                lines.append("")
                lines.append("### 曲线统计摘要")
                lines.append("| 曲线 | P10 | P50 | P90 | 均值 | 极差 | 样本数 |")
                lines.append("|------|-----|-----|-----|------|------|--------|")
                for curve, stats in detection_result.get('curve_stats_summary', {}).items():
                    lines.append(f"| {curve} | {stats.get('q10', '-'):.2f} | {stats.get('q50', '-'):.2f} | "
                                f"{stats.get('q90', '-'):.2f} | {stats.get('mean', '-'):.2f} | "
                                f"{stats.get('range', '-'):.2f} | {stats.get('count', '-')} |")
            return '\n'.join(lines)
        
        lines.append(f"**检测到 {len(matched)} 个地质特征签名**，总体置信度：{detection_result.get('confidence', 0):.0%}")
        lines.append("")
        
        for i, m in enumerate(matched, 1):
            lines.append(f"### {i}. {m['name']}")
            lines.append(f"- **签名ID**: `{m['signature_id']}`")
            lines.append(f"- **描述**: {m.get('description', '')}")
            lines.append(f"- **置信度**: {m['confidence']:.0%}")
            lines.append(f"- **匹配规则**: {m.get('matched_count', 0)}/{m.get('total_rules', 0)}")
            if m.get('matched_rules'):
                lines.append(f"  - 匹配的规则: {', '.join(m['matched_rules'])}")
            lines.append("")
        
        if detection_result.get('linked_knowledge'):
            lines.append("### 关联知识条目")
            for kk in detection_result['linked_knowledge']:
                lines.append(f"- `{kk}`")
            lines.append("")
        
        if detection_result.get('detected_tags'):
            lines.append("### 自动标注")
            lines.append(f"标签: {', '.join(detection_result['detected_tags'])}")
            lines.append("")
        
        if detection_result.get('curve_stats_summary'):
            lines.append("### 曲线统计摘要")
            lines.append("| 曲线 | P10 | P50 | P90 | 均值 | 极差 | 样本数 |")
            lines.append("|------|-----|-----|-----|------|------|--------|")
            for curve, stats in detection_result.get('curve_stats_summary', {}).items():
                lines.append(f"| {curve} | {stats.get('q10', '-'):.2f} | {stats.get('q50', '-'):.2f} | "
                            f"{stats.get('q90', '-'):.2f} | {stats.get('mean', '-'):.2f} | "
                            f"{stats.get('range', '-'):.2f} | {stats.get('count', '-')} |")
        
        return '\n'.join(lines)

# ------------------------------
# 知识分类管理器
# ------------------------------
class KnowledgeClassifier:
    """知识分类管理器，将知识分为通用知识和地区经验知识"""
    
    # 知识分类定义
    KNOWLEDGE_CATEGORIES = {
        'general': {
            'name': '通用知识',
            'description': '测井解释方法、计算模型、理论公式、资料质量、测井地质、试油知识、解决方案等',
            'subcategories': ['interpretation_model', 'calculation', 'analysis', 'correction',
                              'data_quality', 'logging_geology', 'well_testing', 'logging_solutions']
        },
        'regional': {
            'name': '地区经验',
            'description': '地区经验参数、区块特征、区域解释经验、区域测井特征等',
            'subcategories': ['evaluation', 'well_data', 'regional_params',
                              'regional_experience', 'regional_characteristics']
        }
    }
    
    def __init__(self):
        self.category_rules = {
            'general': [
                '公式', '方法', '模型', '计算', '原理', '理论', '标准', '规范',
                'Archie', 'Simandoux', 'Waxman', 'Timur', 'Coates', 'Wyllie',
                'porosity', 'permeability', 'saturation', 'resistivity',
                'interpretation', 'analysis', 'correction', 'quality',
                '试油', 'DST', '采集', '质量', '预处理', '沉积', '成岩', '非均质',
                '工具', '方案', '仪器', '组合', 'LWD', 'NMR', 'ECS', 'FMI',
                'data_quality', 'well_testing', 'logging_solutions', 'logging_geology'
            ],
            'regional': [
                '油田', '区块', '地区', '井', '经验', '参数', '标定',
                '大庆', '胜利', '长庆', '塔里木', '辽河',
                '中东', '北海', '非洲', 'Daqing', 'Shengli', 'Tarim',
                '松辽', '渤海湾', '鄂尔多斯', '四川', '准噶尔',
                '东营组', '沙河街', '延长组', '奥陶系', '标志层',
                'Songliao', 'Ordos', 'Bohai', 'regional_experience', 'regional_characteristics',
                '巴西', 'Brazil', '蒸发岩', '盐岩', '硬石膏', 'halite', 'anhydrite',
                'evaporite', '碳酸盐岩序列', 'Brazil offshore', 'salt', 'pre-salt'
            ]
        }
    
    def classify_knowledge(self, title, content, source=""):
        """
        对知识进行分类
        
        Args:
            title: 知识标题
            content: 知识内容
            source: 知识来源（可选）
        
        Returns:
            'general' 或 'regional'
        """
        text = (title + " " + content + " " + source).lower()
        
        # 统计各类别的匹配关键词数量
        general_score = sum(1 for keyword in self.category_rules['general'] if keyword.lower() in text)
        regional_score = sum(1 for keyword in self.category_rules['regional'] if keyword.lower() in text)
        
        # 如果地区关键词匹配更多，则归类为地区经验
        if regional_score > general_score:
            return 'regional'
        return 'general'
    
    def get_category_name(self, category_code):
        """获取分类名称"""
        return self.KNOWLEDGE_CATEGORIES.get(category_code, {}).get('name', '未知')
    
    def get_category_description(self, category_code):
        """获取分类描述"""
        return self.KNOWLEDGE_CATEGORIES.get(category_code, {}).get('description', '')
    
    def classify_documents(self, documents):
        """批量分类文档"""
        classified = {
            'general': [],
            'regional': []
        }
        
        for doc in documents:
            category = self.classify_knowledge(
                doc.get('title', ''),
                doc.get('content', ''),
                doc.get('source', '')
            )
            doc['category'] = category
            classified[category].append(doc)
        
        return classified
    
    def merge_similar_knowledge(self, documents, similarity_threshold=0.8):
        """
        整合相似知识
        
        Args:
            documents: 文档列表
            similarity_threshold: 相似度阈值
        
        Returns:
            整合后的文档列表
        """
        merged = []
        processed_indices = set()
        
        for i, doc1 in enumerate(documents):
            if i in processed_indices:
                continue
            
            # 找到所有相似文档
            similar_docs = [doc1]
            processed_indices.add(i)
            
            for j, doc2 in enumerate(documents):
                if j in processed_indices or i == j:
                    continue
                
                if self._calculate_similarity(doc1, doc2) >= similarity_threshold:
                    similar_docs.append(doc2)
                    processed_indices.add(j)
            
            # 如果找到相似文档，进行整合
            if len(similar_docs) > 1:
                merged_doc = self._merge_documents(similar_docs)
                merged.append(merged_doc)
            else:
                merged.append(doc1)
        
        return merged
    
    def _calculate_similarity(self, doc1, doc2):
        """计算两篇文档的相似度"""
        text1 = (doc1.get('title', '') + " " + doc1.get('content', '')).lower()
        text2 = (doc2.get('title', '') + " " + doc2.get('content', '')).lower()
        
        # 提取关键词
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Jaccard相似度
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _merge_documents(self, documents):
        """整合多篇相似文档"""
        # 合并标题（取最长的）
        title = max([doc.get('title', '') for doc in documents], key=len)
        
        # 合并内容（去重）
        content_parts = []
        seen_content = set()
        
        for doc in documents:
            content = doc.get('content', '')
            if content and content not in seen_content:
                content_parts.append(content)
                seen_content.add(content)
        
        content = '\n\n---\n\n'.join(content_parts)
        
        # 合并来源
        sources = list(set([doc.get('source', '') for doc in documents if doc.get('source')]))
        
        # 取最早的时间戳
        timestamps = [doc.get('timestamp') for doc in documents if doc.get('timestamp')]
        timestamp = min(timestamps) if timestamps else datetime.now()
        
        return {
            'title': title,
            'content': content,
            'sources': sources,
            'timestamp': timestamp,
            'merged_from': len(documents)
        }
    
    def categorize_and_merge(self, documents):
        """分类并整合知识"""
        # 先分类
        classified = self.classify_documents(documents)
        
        # 再在每个类别内整合相似知识
        result = {}
        for category, docs in classified.items():
            result[category] = self.merge_similar_knowledge(docs)
        
        return result

# ------------------------------
# 知识库主类（增强版）
# ------------------------------
class WellLogKnowledgeBase:
    """测井解释知识库主类，支持自动更新和增量索引"""
    
    def __init__(self, config_file="config.yaml", auto_scan=True):
        self.config = self._load_config(config_file)
        self._init_directories()
        
        self.indexer = WhooshIndexer(self.config["paths"]["index_dir"])
        self.markdown_loader = MarkdownLoader(self.config["paths"]["local_docs"])
        self.crawler = EnhancedCrawler(self.config["crawler"])
        self.llm = LLMInterface(self.config["llm"])
        self.builtin_knowledge = BuiltInKnowledge()
        self.converter = DocumentConverter()
        self.classifier = KnowledgeClassifier()  # 添加分类器
        self.region_detector = RegionDetector()  # 地区地质特征自动检测器
        
        self.last_update_time = None
        self.update_thread = None
        self.running = False
        self.last_merge_time = None  # 记录上次整合时间
        
        # 加载内置知识到索引
        self._load_builtin_knowledge()
        
        # 自动扫描本地文档（如果启用）
        if auto_scan:
            self._auto_scan_local_documents()
        
        # 自动启动更新服务（如果配置启用）
        if self.config["auto_update"].get("auto_start", True):
            self.start_auto_update()
    
    def get_category_stats(self):
        """获取知识分类统计信息"""
        all_docs = self.markdown_loader.load_all()
        
        # 分类文档
        classified = self.classifier.classify_documents(all_docs)
        
        stats = {
            'total_docs': len(all_docs),
            'general_count': len(classified['general']),
            'regional_count': len(classified['regional']),
            'categories': {
                'general': {
                    'name': self.classifier.get_category_name('general'),
                    'description': self.classifier.get_category_description('general'),
                    'count': len(classified['general'])
                },
                'regional': {
                    'name': self.classifier.get_category_name('regional'),
                    'description': self.classifier.get_category_description('regional'),
                    'count': len(classified['regional'])
                }
            }
        }
        
        return stats
    
    def merge_knowledge(self):
        """整合相似知识"""
        all_docs = self.markdown_loader.load_all()
        
        # 分类并整合
        categorized = self.classifier.categorize_and_merge(all_docs)
        
        print("知识整合完成:")
        for category, docs in categorized.items():
            category_name = self.classifier.get_category_name(category)
            print(f"  {category_name}: {len(docs)} 个文档")
            
            # 统计整合的文档数
            merged_count = sum(1 for doc in docs if doc.get('merged_from', 1) > 1)
            if merged_count > 0:
                print(f"    其中 {merged_count} 个文档是从相似文档整合而来")
        
        return categorized
    
    def detect_region(self, file_path=None, input_dir=None, output_report=None):
        """自动检测测井数据文件的地区地质特征
        
        支持两种模式：
        1. 单文件检测：传入 file_path
        2. 批量检测：传入 input_dir 扫描目录中所有数据文件
        
        Args:
            file_path: 单个测井数据文件路径（LAS/CSV/XLSX）
            input_dir: 批量扫描的目录路径
            output_report: 输出报告路径（可选）
            
        Returns:
            dict: 检测结果汇总
        """
        results = []
        
        if file_path:
            # 单文件检测
            detection = self.region_detector.detect_from_file(file_path)
            if detection:
                results.append({
                    'file': file_path,
                    'detection': detection,
                    'recommendations': self.region_detector.get_recommendations(detection)
                })
        
        elif input_dir:
            # 批量扫描
            import glob
            data_extensions = ['.las', '.csv', '.xlsx', '.xls']
            
            for ext in data_extensions:
                for f in glob.glob(os.path.join(input_dir, f'**/*{ext}'), recursive=True):
                    detection = self.region_detector.detect_from_file(f)
                    if detection and detection.get('matched_signatures'):
                        results.append({
                            'file': f,
                            'detection': detection,
                            'recommendations': self.region_detector.get_recommendations(detection)
                        })
                
                # 也检查非递归的第一层
                for f in glob.glob(os.path.join(input_dir, f'*{ext}')):
                    detection = self.region_detector.detect_from_file(f)
                    if detection and detection.get('matched_signatures'):
                        results.append({
                            'file': f,
                            'detection': detection,
                            'recommendations': self.region_detector.get_recommendations(detection)
                        })
            
            # 去重（按文件路径）
            seen = set()
            unique_results = []
            for r in results:
                if r['file'] not in seen:
                    seen.add(r['file'])
                    unique_results.append(r)
            results = unique_results
        
        # 生成报告
        if output_report:
            self._save_detection_report(results, output_report)
        
        return {
            'total_files_scanned': len(results),
            'detected_regions': self.region_detector.detected_regions,
            'results': results,
            'summary': self._summarize_detection_results(results)
        }
    
    def _summarize_detection_results(self, results):
        """汇总检测结果"""
        summary = {
            'total': len(results),
            'signatures_found': {},
            'all_tags': [],
            'all_knowledge': []
        }
        
        for r in results:
            det = r['detection']
            for sig in det.get('matched_signatures', []):
                sid = sig['signature_id']
                if sid not in summary['signatures_found']:
                    summary['signatures_found'][sid] = {
                        'name': sig['name'],
                        'count': 0,
                        'files': []
                    }
                summary['signatures_found'][sid]['count'] += 1
                summary['signatures_found'][sid]['files'].append(os.path.basename(r['file']))
            summary['all_tags'].extend(det.get('detected_tags', []))
            summary['all_knowledge'].extend(det.get('linked_knowledge', []))
        
        summary['all_tags'] = list(dict.fromkeys(summary['all_tags']))
        summary['all_knowledge'] = list(dict.fromkeys(summary['all_knowledge']))
        
        return summary
    
    def _save_detection_report(self, results, output_path):
        """保存检测报告为Markdown文件"""
        lines = ["# 测井数据地区地质特征自动检测报告", ""]
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "")
        lines.append(f"**检测文件数**: {len(results)}", "")
        
        summary = self._summarize_detection_results(results)
        
        if summary['signatures_found']:
            lines.append("## 检测摘要", "")
            for sid, info in summary['signatures_found'].items():
                lines.append(f"- **{info['name']}**: {info['count']} 个文件")
            lines.append("")
        
        if summary['all_tags']:
            lines.append(f"**自动标注**: {', '.join(summary['all_tags'])}", "")
        
        if summary['all_knowledge']:
            lines.append(f"**关联知识**: {', '.join(summary['all_knowledge'])}", "")
        
        lines.append("---")
        lines.append("")
        
        for i, r in enumerate(results, 1):
            lines.append(f"## {i}. {os.path.basename(r['file'])}", "")
            det = r['detection']
            lines.append(self.region_detector.generate_detection_report(det))
            lines.append("")
            
            recs = r.get('recommendations', [])
            if recs:
                lines.append("### 知识推荐")
                for rec in recs:
                    lines.append(f"- [{rec['category']}] **{rec['title']}** (`{rec['key']}`)")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"📄 检测报告已保存: {output_path}")
    
    def _auto_scan_local_documents(self):
        """自动扫描本地文档并构建索引"""
        # 定义搜索目录（包括上级目录中的文档）
        search_dirs = [
            self.config["paths"]["local_docs"],
            "../",  # 上级目录
            "./",   # 当前目录
            "F:/360/"  # 参考资料目录
        ]
        
        converted_count = 0
        
        for search_dir in search_dirs:
            if os.path.exists(search_dir):
                count, _ = self.converter.batch_convert(search_dir, self.config["paths"]["local_docs"], recursive=True)
                converted_count += count
        
        if converted_count > 0:
            print(f"📂 发现并转换了 {converted_count} 个新文档")
            # 增量更新索引
            self.build_index(incremental=True)
    
    def _load_config(self, config_file):
        """加载配置文件"""
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return DEFAULT_CONFIG
    
    def _init_directories(self):
        """初始化目录结构"""
        for dir_path in self.config["paths"].values():
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
    
    def _load_builtin_knowledge(self):
        """将内置知识加载到索引"""
        builtin_docs = self.builtin_knowledge.get_all_knowledge()
        for doc in builtin_docs:
            doc["source"] = f"builtin://{doc['title']}"
            doc["timestamp"] = datetime.now()
            doc["content_hash"] = generate_file_hash(doc["content"])
        
        if builtin_docs:
            self.indexer.add_documents(builtin_docs)
            print(f"已加载 {len(builtin_docs)} 条内置知识")
    
    def build_index(self, incremental=False):
        """构建索引（支持增量更新）"""
        if not incremental:
            # 完全重建索引
            self.indexer.clear_index()
            # 重新加载内置知识
            self._load_builtin_knowledge()
        
        # 加载本地Markdown文档
        local_docs = self.markdown_loader.load_all()
        
        # 加载爬取的文档
        crawled_loader = MarkdownLoader(self.config["paths"]["crawled_docs"])
        crawled_docs = crawled_loader.load_all()
        
        # 添加到索引
        all_docs = local_docs + crawled_docs
        if all_docs:
            self.indexer.add_documents(all_docs)
        
        self.last_update_time = datetime.now()
        return all_docs
    
    def update_index_incrementally(self):
        """增量更新索引"""
        # 检查本地文件是否有更新
        if self.last_update_time and self.markdown_loader.has_new_files(self.last_update_time):
            self.build_index(incremental=True)
        
        # 检查爬取文件是否有更新
        crawled_loader = MarkdownLoader(self.config["paths"]["crawled_docs"])
        if self.last_update_time and crawled_loader.has_new_files(self.last_update_time):
            self.build_index(incremental=True)
    
    def search(self, query, top_n=None, region=None, well_name=None):
        """搜索知识库，支持地区和井名过滤"""
        n = top_n or self.config["search"]["top_n"]
        min_score = self.config["search"]["min_score"]
        results = self.indexer.search(query, top_n=n, min_score=min_score, 
                                     region=region, well_name=well_name)
        return results
    
    def ask(self, question, use_context=True):
        """向大模型提问"""
        context = ""
        
        if use_context:
            # 先搜索相关文档作为上下文
            search_results = self.search(question, top_n=3)
            
            # 添加内置知识搜索结果
            builtin_results = self.builtin_knowledge.search_knowledge(question)
            
            if search_results:
                context += "\n\n".join([
                    f"【来源: {r['source']}】\n{r['content'][:500]}..." 
                    for r in search_results
                ])
            
            if builtin_results:
                for r in builtin_results[:2]:
                    context += f"\n\n【内置知识: {r['title']}】\n{r['content'][:500]}..."
        
        # 调用LLM生成回答
        answer = self.llm.generate(question, context)
        
        search_results = self.search(question, top_n=3) if use_context else []
        
        return {
            "question": question,
            "answer": answer,
            "context_used": use_context,
            "sources": [r["source"] for r in search_results] if use_context else []
        }
    
    def crawl_url(self, url):
        """爬取指定URL"""
        result = self.crawler.fetch_and_save(
            url,
            save_dir=self.config["paths"]["crawled_docs"],
            max_depth=self.config["crawler"]["max_depth"]
        )
        
        # 更新索引
        self.build_index(incremental=True)
        return result
    
    def crawl_multiple_urls(self, urls):
        """爬取多个URL，单个失败不影响其他URL"""
        results = []
        failed_urls = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] 开始爬取: {url}")
            try:
                result = self.crawl_url(url)
                if result:
                    results.extend(result)
                    print(f"  成功: 获取 {len(result)} 个页面")
                else:
                    failed_urls.append(url)
            except Exception as e:
                print(f"  失败: {url} - {e}")
                failed_urls.append(url)
                continue
        if failed_urls:
            print(f"\n共 {len(failed_urls)} 个URL爬取失败:")
            for u in failed_urls:
                print(f"  - {u}")
        return results
    
    def crawl_all_sources(self, max_pages=50):
        """爬取所有配置的更新源"""
        # 获取配置的更新源URL列表
        update_sources = self.config["auto_update"].get("update_sources", [])
        
        if not update_sources:
            print("没有配置更新源URL")
            return []
        
        # 设置最大页数限制
        original_max_pages = self.config["crawler"]["max_pages"]
        self.config["crawler"]["max_pages"] = max_pages
        
        print(f"开始爬取 {len(update_sources)} 个更新源...")
        print(f"最大页数限制: {max_pages}")
        
        # 爬取所有源
        results = self.crawl_multiple_urls(update_sources)
        
        # 恢复原始配置
        self.config["crawler"]["max_pages"] = original_max_pages
        
        print(f"爬取完成，共获取 {len(results)} 个页面")
        
        # 如果爬取结果为0，提示用户检查网络配置
        if len(results) == 0:
            print("警告：爬取结果为0，请检查网络连接或代理配置")
            print("您可以在配置中设置代理参数: proxy_enabled, proxy_http, proxy_https")
        
        return results
    
    def add_local_document(self, content, title, category="local"):
        """添加本地文档"""
        filepath = self.markdown_loader.add_document(content, title, category)
        
        # 更新索引
        self.build_index(incremental=True)
        return filepath
    
    def add_builtin_knowledge(self, title, content, category="general"):
        """添加自定义内置知识"""
        knowledge = {
            "title": title,
            "content": content,
            "category": category,
            "source": f"builtin://{title}",
            "timestamp": datetime.now(),
            "content_hash": generate_file_hash(content)
        }
        
        self.indexer.add_document(**knowledge)
        print(f"已添加内置知识: {title}")
        return knowledge
    
    def get_stats(self):
        """获取知识库统计信息"""
        doc_count = self.indexer.get_document_count()
        local_count = len(self.markdown_loader.load_all())
        crawled_loader = MarkdownLoader(self.config["paths"]["crawled_docs"])
        crawled_count = len(crawled_loader.load_all())
        
        # 计算知识数据大小
        def _get_dir_size(path):
            total = 0
            if os.path.exists(path):
                for dirpath, dirnames, filenames in os.walk(path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total += os.path.getsize(fp)
                        except OSError:
                            pass
            return total
        
        local_size = _get_dir_size(self.config["paths"]["local_docs"])
        crawled_size = _get_dir_size(self.config["paths"]["crawled_docs"])
        index_size = _get_dir_size(self.config["paths"]["index_dir"])
        total_size = local_size + crawled_size + index_size
        
        return {
            "total_docs": doc_count,
            "local_docs": local_count,
            "crawled_docs": crawled_count,
            "index_path": self.config["paths"]["index_dir"],
            "last_updated": self.last_update_time.isoformat() if self.last_update_time else None,
            "auto_update_enabled": self.config["auto_update"]["enabled"],
            "update_interval_hours": self.config["auto_update"]["interval_hours"],
            "knowledge_size_bytes": total_size,
            "local_size_bytes": local_size,
            "crawled_size_bytes": crawled_size,
            "index_size_bytes": index_size
        }
    
    def _auto_update_loop(self):
        """自动更新循环（包含爬取、索引、地区检测、智能合并、优化）"""
        while self.running:
            try:
                print(f"\n[{datetime.now()}] 执行自动更新...")
                
                # 1. 爬取更新源
                for url in self.config["auto_update"]["update_sources"]:
                    if url and url.strip():
                        print(f"爬取更新源: {url}")
                        try:
                            self.crawl_url(url)
                        except Exception as e:
                            print(f"  爬取失败: {e}")
                
                # 2. 扫描本地新文档并自动检测地区特征
                self._auto_scan_local_documents()
                
                # 3. 增量更新索引
                self.update_index_incrementally()
                
                # 4. 自动整合相似知识（每次更新都执行，不再按周）
                if self.config["auto_update"].get("enable_merge", True):
                    try:
                        print(f"执行知识自动整合...")
                        docs_before = len(self.markdown_loader.load_all())
                        self.merge_knowledge()
                        docs_after = len(self.markdown_loader.load_all())
                        self.last_merge_time = datetime.now()
                        if docs_before > docs_after:
                            print(f"  整合完成: {docs_before} → {docs_after} 个文档")
                    except Exception as e:
                        print(f"  知识整合失败: {e}")
                
                # 5. 优化索引
                try:
                    self.indexer.optimize_index()
                except Exception:
                    pass
                
                # 6. 控制知识库大小
                self._limit_knowledge_size()
                
                # 7. 导出知识总结（供外部程序调用）
                if self.config["auto_update"].get("auto_export", False):
                    try:
                        self.export_knowledge_summary()
                    except Exception:
                        pass
                
                print(f"[{datetime.now()}] 自动更新完成")
                
            except Exception as e:
                print(f"自动更新出错: {e}")
            
            # 等待下一次更新
            for _ in range(self.config["auto_update"]["interval_hours"] * 3600):
                if not self.running:
                    break
                time.sleep(1)
    
    def export_knowledge_summary(self, output_dir=None):
        """导出知识总结到文件，将内置知识和总结规律保存到文件系统"""
        if output_dir is None:
            output_dir = os.path.join(self.config["paths"]["data_dir"], "knowledge_summary")
        
        print(f"正在导出知识总结到: {os.path.abspath(output_dir)}")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"已创建目录: {output_dir}")
        
        # 导出内置知识
        builtin_knowledge = self.builtin_knowledge.knowledge_base
        for key, knowledge in builtin_knowledge.items():
            filename = f"{key}.md"
            filepath = os.path.join(output_dir, filename)
            
            content = f"# {knowledge['title']}\n\n"
            content += f"分类: {knowledge.get('category', 'general')}\n\n"
            content += "---\n\n"
            content += knowledge['content']
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # 导出知识分类统计
        stats = self.get_category_stats()
        index_stats = self.get_stats()
        
        # 格式化知识大小
        def _fmt_size(b):
            if b >= 1024**3:
                return f"{b / 1024**3:.2f} GB"
            elif b >= 1024**2:
                return f"{b / 1024**2:.2f} MB"
            elif b >= 1024:
                return f"{b / 1024:.2f} KB"
            return f"{b} B"
        
        stats_file = os.path.join(output_dir, "knowledge_stats.md")
        with open(stats_file, 'w', encoding='utf-8') as f:
            f.write("# 知识库统计报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"## 文档统计\n\n")
            f.write(f"- 总文档数: {stats['total_docs']}\n\n")
            f.write(f"## 知识数据大小\n\n")
            f.write(f"- 总大小: {_fmt_size(index_stats.get('knowledge_size_bytes', 0))}\n")
            f.write(f"- 本地文档: {_fmt_size(index_stats.get('local_size_bytes', 0))}\n")
            f.write(f"- 爬取文档: {_fmt_size(index_stats.get('crawled_size_bytes', 0))}\n")
            f.write(f"- 索引数据: {_fmt_size(index_stats.get('index_size_bytes', 0))}\n\n")
            f.write("## 分类详情\n\n")
            for cat_code, cat_info in stats['categories'].items():
                f.write(f"### [{cat_code}] {cat_info['name']}\n")
                f.write(f"- 描述: {cat_info['description']}\n")
                f.write(f"- 文档数: {cat_info['count']}\n")
                f.write(f"- 占比: {(cat_info['count']/stats['total_docs']*100):.1f}%\n\n")
        
        # 导出索引统计
        index_file = os.path.join(output_dir, "index_stats.json")
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_stats, f, ensure_ascii=False, indent=2)
        
        print(f"知识总结已导出到: {os.path.abspath(output_dir)}")
        return output_dir
    
    def _limit_knowledge_size(self):
        """控制知识库大小，防止知识库过大"""
        max_docs_per_category = self.config["auto_update"].get("max_docs_per_category", 0)
        
        # 如果设置为0，表示不限制文档数量
        if max_docs_per_category <= 0:
            return
        
        all_docs = self.markdown_loader.load_all()
        categorized = self.classifier.classify_documents(all_docs)
        
        for category, docs in categorized.items():
            if len(docs) > max_docs_per_category:
                # 按时间排序，保留最新的文档
                docs_sorted = sorted(docs, key=lambda x: x.get('timestamp', datetime.min), reverse=True)
                docs_to_remove = docs_sorted[max_docs_per_category:]
                
                print(f"清理{self.classifier.get_category_name(category)}中过期文档: {len(docs_to_remove)} 个")
                for doc in docs_to_remove:
                    source = doc.get('source', '')
                    if source:
                        try:
                            if os.path.exists(source):
                                os.remove(source)
                                print(f"  删除: {os.path.basename(source)}")
                        except Exception as e:
                            print(f"  删除失败: {e}")
        
        # 重建索引以反映删除的文档
        self.build_index(incremental=True)
    
    def start_auto_update(self):
        """启动自动更新服务"""
        if not self.config["auto_update"]["enabled"]:
            print("自动更新未启用")
            return
        
        if self.running:
            print("自动更新服务已在运行")
            return
        
        self.running = True
        self.update_thread = threading.Thread(target=self._auto_update_loop, daemon=True)
        self.update_thread.start()
        print("自动更新服务已启动")
    
    def stop_auto_update(self):
        """停止自动更新服务"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=10)
        print("自动更新服务已停止")
    
    def backup_index(self):
        """备份索引"""
        import shutil
        backup_dir = self.config["paths"]["backup_dir"]
        index_dir = self.config["paths"]["index_dir"]
        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        backup_name = f"index_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_path = os.path.join(backup_dir, backup_name)
        
        if os.path.exists(index_dir):
            shutil.copytree(index_dir, backup_path)
            print(f"索引已备份到: {backup_path}")
            return backup_path
        return None

def interactive_cli(kb):
    """交互式命令行界面"""
    print("\n" + "="*60)
    print("🤖 测井解释知识库 - 交互式问答模式")
    print("="*60)
    print("输入问题直接提问，输入 'q' 或 'quit' 退出")
    print("输入 'help' 查看帮助")
    print("="*60)
    
    while True:
        try:
            user_input = input("\n>>> ").strip()
            
            if user_input.lower() in ['q', 'quit', 'exit']:
                print("👋 感谢使用测井解释知识库！")
                break
            
            if user_input.lower() == 'help':
                print("\n命令帮助:")
                print("  q / quit / exit - 退出程序")
                print("  help - 显示此帮助")
                print("  stats - 显示知识库统计")
                print("  search <关键词> - 搜索知识库")
                print("  search <关键词> -r <地区> -w <井名> - 按地区/井名搜索")
                print("  其他内容 - 直接向AI提问")
                continue
            
            if user_input.lower().startswith('stats'):
                stats = kb.get_stats()
                def _fmt(b):
                    if b >= 1024**3: return f"{b / 1024**3:.2f} GB"
                    elif b >= 1024**2: return f"{b / 1024**2:.2f} MB"
                    elif b >= 1024: return f"{b / 1024:.2f} KB"
                    return f"{b} B"
                print("\n📚 知识库统计:")
                print(f"   总文档数: {stats.get('total_docs', 0)}")
                print(f"   本地文档: {stats.get('local_docs', 0)}")
                print(f"   爬取文档: {stats.get('crawled_docs', 0)}")
                print(f"   知识总量: {_fmt(stats.get('knowledge_size_bytes', 0))}")
                continue
            
            if user_input.lower().startswith('search '):
                parts = user_input[7:].split()
                query_parts = []
                region = None
                well_name = None
                
                i = 0
                while i < len(parts):
                    if parts[i] == '-r' and i + 1 < len(parts):
                        region = parts[i + 1]
                        i += 2
                    elif parts[i] == '-w' and i + 1 < len(parts):
                        well_name = parts[i + 1]
                        i += 2
                    else:
                        query_parts.append(parts[i])
                        i += 1
                
                query = ' '.join(query_parts)
                if query:
                    results = kb.search(query, top_n=5, region=region, well_name=well_name)
                    if results:
                        print(f"\n🔍 搜索结果 ({len(results)}):")
                        for i, result in enumerate(results, 1):
                            print(f"\n[{i}] {result['title']}")
                            print(f"   来源: {result['source']}")
                            print(f"   评分: {result['score']:.3f}")
                            if result.get('region'):
                                print(f"   地区: {result['region']}")
                            if result.get('well_name'):
                                print(f"   井名: {result['well_name']}")
                            if result.get('oil_field'):
                                print(f"   油田: {result['oil_field']}")
                            print(f"   摘要: {result['content'][:100]}...")
                    else:
                        print(f"\n未找到 '{query}' 相关内容")
                continue
            
            if not user_input:
                continue
            
            # 向AI提问
            print("\n⏳ 正在思考...")
            result = kb.ask(user_input, use_context=True)
            print(f"\n💡 回答:")
            print(result['answer'])
            
            if result.get('sources'):
                print(f"\n📖 参考来源 ({len(result['sources'])}):")
                for i, src in enumerate(result['sources'], 1):
                    print(f"   [{i}] {src}")
                    
        except KeyboardInterrupt:
            print("\n\n👋 感谢使用测井解释知识库！")
            break
        except Exception as e:
            print(f"\n❌ 出错了: {e}")

# ------------------------------
# HTTP API服务模块
# ------------------------------
class KnowledgeBaseAPI:
    """知识库HTTP API服务，方便其他程序调用"""
    
    def __init__(self, kb):
        self.kb = kb
    
    def run(self, host="0.0.0.0", port=8000):
        """启动API服务"""
        try:
            import uvicorn
            from fastapi import FastAPI, HTTPException, Query
            from fastapi.middleware.cors import CORSMiddleware
            
            app = FastAPI(title="测井解释知识库API", description="测井专业知识检索和问答API")
            
            # 添加CORS中间件
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            @app.get("/api/search", summary="搜索知识库")
            def search(
                query: str = Query(..., description="搜索关键词"),
                top_n: int = Query(10, description="返回数量"),
                region: str = Query(None, description="按地区过滤"),
                well_name: str = Query(None, description="按井名过滤")
            ):
                """搜索知识库，支持地区和井名过滤"""
                results = self.kb.search(query, top_n=top_n, region=region, well_name=well_name)
                return {"success": True, "results": results}
            
            @app.get("/api/ask", summary="向AI提问")
            def ask(
                question: str = Query(..., description="问题内容"),
                use_context: bool = Query(True, description="是否使用知识库上下文")
            ):
                """向大模型提问，可选使用知识库上下文"""
                result = self.kb.ask(question, use_context=use_context)
                return {"success": True, "result": result}
            
            @app.get("/api/stats", summary="获取知识库统计")
            def stats():
                """获取知识库统计信息"""
                stats = self.kb.get_stats()
                return {"success": True, "stats": stats}
            
            @app.get("/api/category-stats", summary="获取知识分类统计")
            def category_stats():
                """获取知识分类统计信息"""
                stats = self.kb.get_category_stats()
                return {"success": True, "stats": stats}
            
            @app.get("/api/regions", summary="获取所有地区信息")
            def get_regions():
                """获取知识库中所有地区信息"""
                docs = self.kb.markdown_loader.load_all()
                regions = set()
                for doc in docs:
                    if doc.get('region'):
                        regions.add(doc['region'])
                return {"success": True, "regions": list(regions)}
            
            @app.get("/api/wells", summary="获取所有井名信息")
            def get_wells(region: str = Query(None, description="按地区过滤")):
                """获取知识库中所有井名信息"""
                docs = self.kb.markdown_loader.load_all()
                wells = set()
                for doc in docs:
                    if doc.get('well_name'):
                        if region:
                            if doc.get('region') == region:
                                wells.add(doc['well_name'])
                        else:
                            wells.add(doc['well_name'])
                return {"success": True, "wells": list(wells)}
            
            @app.post("/api/crawl", summary="爬取网页")
            def crawl_url(url: str):
                """爬取指定URL"""
                result = self.kb.crawl_url(url)
                return {"success": True, "crawled_count": len(result) if result else 0}
            
            @app.post("/api/update", summary="更新知识库")
            def update_knowledge():
                """更新知识库（爬取+重建索引+自动整合相似知识）"""
                self.kb.update_index_incrementally()
                # 自动整合相似知识
                try:
                    self.kb.merge_knowledge()
                except Exception:
                    pass
                return {"success": True, "message": "知识库已更新并完成自动整合"}
            
            @app.get("/api/health", summary="健康检查")
            def health():
                """API健康检查"""
                return {"status": "healthy", "service": "测井解释知识库"}
            
            @app.post("/api/detect-region", summary="自动检测地区地质特征")
            def detect_region(file_path: str):
                """从LAS/CSV/XLSX文件自动检测地区地质特征"""
                detection = self.kb.region_detector.detect_from_file(file_path)
                if detection:
                    report = self.kb.region_detector.generate_detection_report(detection)
                    recommendations = self.kb.region_detector.get_recommendations(detection)
                    return {
                        "success": True,
                        "detection": detection,
                        "report": report,
                        "recommendations": recommendations
                    }
                return {"success": False, "message": "未检测到地质特征或无数据文件"}
            
            print(f"\n🚀 知识库API服务启动成功")
            print(f"📡 API地址: http://{host}:{port}")
            print(f"📖 文档地址: http://{host}:{port}/docs")
            print(f"🔍 健康检查: http://{host}:{port}/api/health")
            print()
            print("=== 其他程序调用示例 ===")
            print("Python调用:")
            print("  import requests")
            print('  r = requests.get("http://{}:{}/api/search", params={{"query":"孔隙度计算","top_n":5}})'.format(host, port))
            print('  r = requests.get("http://{}:{}/api/ask", params={{"question":"什么是阿尔奇公式","use_context":True}})'.format(host, port))
            print("  r = requests.get('http://{}:{}/api/stats')".format(host, port))
            print("  r = requests.post('http://{}:{}/api/update')".format(host, port))
            print('  r = requests.post("http://{}:{}/api/detect-region", params={{"file_path":"data/well.las"}})'.format(host, port))
            print()
            print("命令行调用:")
            print("  python logIntKnowledge.py search -q '孔隙度计算' -n 5")
            print("  python logIntKnowledge.py ask -q '什么是阿尔奇公式'")
            print("  python logIntKnowledge.py detect-region -f data/well.las")
            print("=" * 60)
            
            uvicorn.run(app, host=host, port=port)
            
        except ImportError:
            print("需要安装FastAPI和uvicorn: pip install fastapi uvicorn")
            return
    
    def start_in_background(self, host="0.0.0.0", port=8000):
        """在后台启动API服务"""
        import threading
        thread = threading.Thread(target=self.run, args=(host, port), daemon=True)
        thread.start()
        print(f"🔧 API服务已在后台启动: http://{host}:{port}")


# ------------------------------
# 命令行接口
# ------------------------------
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="测井解释知识库管理工具")
    subparsers = parser.add_subparsers(dest="command", help="执行的命令")
    
    # cli命令 - 交互式问答模式
    subparsers.add_parser("cli", help="启动交互式问答模式")
    
    # api命令 - 启动HTTP API服务
    api_parser = subparsers.add_parser("api", help="启动HTTP API服务")
    api_parser.add_argument("--host", "-H", default="0.0.0.0", help="监听地址")
    api_parser.add_argument("--port", "-p", type=int, default=8000, help="监听端口")
    
    # export命令 - 导出知识总结
    export_parser = subparsers.add_parser("export", help="导出知识总结")
    export_parser.add_argument("--output", "-o", help="输出目录")
    
    # build命令
    build_parser = subparsers.add_parser("build", help="构建索引")
    build_parser.add_argument("--incremental", "-i", action="store_true", help="增量更新")
    
    # crawl命令
    crawl_parser = subparsers.add_parser("crawl", help="爬取网页")
    crawl_parser.add_argument("--url", "-u", required=True, help="要爬取的URL")
    crawl_parser.add_argument("--depth", "-d", type=int, default=2, help="爬取深度")
    
    # search命令
    search_parser = subparsers.add_parser("search", help="搜索知识库")
    search_parser.add_argument("--query", "-q", required=True, help="搜索内容")
    search_parser.add_argument("--top-n", "-n", type=int, default=10, help="返回数量")
    search_parser.add_argument("--region", "-r", help="按地区/油田过滤")
    search_parser.add_argument("--well", "-w", help="按井名过滤")
    
    # ask命令
    ask_parser = subparsers.add_parser("ask", help="向大模型提问")
    ask_parser.add_argument("--query", "-q", required=True, help="问题内容")
    ask_parser.add_argument("--no-context", "-nc", action="store_true", help="不使用上下文")
    
    # stats命令
    subparsers.add_parser("stats", help="显示统计信息")
    
    # auto-update命令
    au_parser = subparsers.add_parser("auto-update", help="自动更新控制")
    au_parser.add_argument("action", choices=["start", "stop", "status"], help="操作")
    
    # backup命令
    subparsers.add_parser("backup", help="备份索引")
    
    # optimize命令
    subparsers.add_parser("optimize", help="优化索引")
    
    # add命令
    add_parser = subparsers.add_parser("add", help="添加文档")
    add_parser.add_argument("--title", "-t", required=True, help="文档标题")
    add_parser.add_argument("--content", "-c", required=True, help="文档内容")
    add_parser.add_argument("--category", "-cat", default="local", help="分类")
    
    # import命令 - 批量导入文档（PPT/DOC/PDF转Markdown）
    import_parser = subparsers.add_parser("import", help="批量导入文档")
    import_parser.add_argument("--input", "-i", required=True, help="输入目录路径")
    import_parser.add_argument("--output", "-o", default="data/local", help="输出目录路径")
    import_parser.add_argument("--recursive", "-r", action="store_true", help="递归子目录")
    import_parser.add_argument("--rebuild-index", "-ri", action="store_true", help="导入后重建索引")
    
    # update命令 - 更新知识库（爬取+重建索引）
    update_parser = subparsers.add_parser("update", help="更新知识库")
    update_parser.add_argument("--crawl-only", "-co", action="store_true", help="只爬取不重建索引")
    update_parser.add_argument("--index-only", "-io", action="store_true", help="只重建索引不爬取")
    
    # classify命令 - 知识分类统计
    classify_parser = subparsers.add_parser("classify", help="知识分类统计")
    classify_parser.add_argument("--show-detail", "-d", action="store_true", help="显示详细分类信息")
    
    # merge命令 - 整合相似知识
    merge_parser = subparsers.add_parser("merge", help="整合相似知识")
    merge_parser.add_argument("--threshold", "-t", type=float, default=0.8, help="相似度阈值")
    
    # detect-region命令 - 自动检测地区地质特征
    detect_region_parser = subparsers.add_parser("detect-region", help="自动检测测井数据的地区地质特征")
    detect_region_parser.add_argument("--file", "-f", help="单个测井数据文件（LAS/CSV/XLSX）")
    detect_region_parser.add_argument("--dir", "-d", help="批量扫描目录中的所有数据文件")
    detect_region_parser.add_argument("--report", "-r", help="输出检测报告路径（Markdown格式）")
    detect_region_parser.add_argument("--scan-all", "-a", action="store_true", 
                                     help="扫描所有已转换的文档，从内容中检测")
    
    # project命令组 - 项目/地区知识库管理
    project_parser = subparsers.add_parser("project", help="项目/地区知识库管理")
    project_subparsers = project_parser.add_subparsers(dest="project_action", help="项目操作")
    
    # project create命令
    proj_create = project_subparsers.add_parser("create", help="创建新项目")
    proj_create.add_argument("--name", "-n", required=True, help="项目名称")
    proj_create.add_argument("--description", "-desc", default="", help="项目描述")
    proj_create.add_argument("--region", "-r", default="", help="地区/区块名称")
    proj_create.add_argument("--keywords", "-k", nargs='*', default=[], help="关键词列表")
    proj_create.add_argument("--source-dir", "-s", nargs='*', default=[], help="初始导入的文件夹路径")
    
    # project list命令
    project_subparsers.add_parser("list", help="列出所有项目")
    
    # project info命令
    proj_info = project_subparsers.add_parser("info", help="查看项目信息")
    proj_info.add_argument("--name", "-n", required=True, help="项目名称")
    
    # project import命令
    proj_import = project_subparsers.add_parser("import", help="导入文档到项目")
    proj_import.add_argument("--name", "-n", required=True, help="项目名称")
    proj_import.add_argument("--input", "-i", required=True, help="输入目录路径")
    proj_import.add_argument("--recursive", "-r", action="store_true", help="递归子目录")
    proj_import.add_argument("--no-filter", "-nf", action="store_true", help="不过滤非测井文档")
    
    # project crawl命令
    proj_crawl = project_subparsers.add_parser("crawl", help="为项目爬取网络知识")
    proj_crawl.add_argument("--name", "-n", required=True, help="项目名称")
    proj_crawl.add_argument("--url", "-u", nargs='*', required=True, help="要爬取的URL列表")
    proj_crawl.add_argument("--region-keywords", "-rk", nargs='*', default=[], help="地区关键词")
    
    # project search命令
    proj_search = project_subparsers.add_parser("search", help="搜索项目知识库")
    proj_search.add_argument("--name", "-n", required=True, help="项目名称")
    proj_search.add_argument("--query", "-q", required=True, help="搜索内容")
    proj_search.add_argument("--top-n", "-t", type=int, default=10, help="返回数量")
    
    # project update命令
    proj_update = project_subparsers.add_parser("update", help="更新项目知识库")
    proj_update.add_argument("--name", "-n", required=True, help="项目名称")
    proj_update.add_argument("--reimport", "-ri", action="store_true", help="重新导入源目录文档")
    proj_update.add_argument("--url", "-u", nargs='*', default=[], help="额外爬取的URL")
    
    # project delete命令
    proj_delete = project_subparsers.add_parser("delete", help="删除项目")
    proj_delete.add_argument("--name", "-n", required=True, help="项目名称")
    
    args = parser.parse_args()
    
    kb = WellLogKnowledgeBase()
    
    if args.command == "cli":
        interactive_cli(kb)
    
    elif args.command == "api":
        api = KnowledgeBaseAPI(kb)
        api.run(host=args.host, port=args.port)
        return  # API服务会阻塞运行，不需要后续提示
    
    elif args.command == "export":
        kb.export_knowledge_summary(args.output)
        print("知识总结导出完成")
    
    elif args.command == "build":
        kb.build_index(incremental=args.incremental)
        print("索引构建完成")
    
    elif args.command == "crawl":
        kb.crawl_url(args.url)
        print("爬取完成")
    
    elif args.command == "search":
        results = kb.search(args.query, top_n=args.top_n, region=args.region, well_name=args.well)
        for i, result in enumerate(results, 1):
            print(f"\n[{i}] {result['title']}")
            print(f"来源: {result['source']}")
            print(f"评分: {result['score']:.3f}")
            # 显示地区和井名信息（如果有）
            if result.get('region'):
                print(f"地区: {result['region']}")
            if result.get('well_name'):
                print(f"井名: {result['well_name']}")
            if result.get('oil_field'):
                print(f"油田: {result['oil_field']}")
            print(f"摘要: {result['content'][:200]}...")
    
    elif args.command == "ask":
        result = kb.ask(args.query, use_context=not args.no_context)
        print(f"\n问题: {result['question']}")
        print(f"\n回答:\n{result['answer']}")
        if result["sources"]:
            print(f"\n参考来源:")
            for src in result["sources"]:
                print(f"  - {src}")
    
    elif args.command == "stats":
        stats = kb.get_stats()
        def _fmt(b):
            if b >= 1024**3: return f"{b / 1024**3:.2f} GB"
            elif b >= 1024**2: return f"{b / 1024**2:.2f} MB"
            elif b >= 1024: return f"{b / 1024:.2f} KB"
            return f"{b} B"
        print("知识库统计信息:")
        for key, value in stats.items():
            if key.endswith('_size_bytes'):
                print(f"  {key}: {_fmt(value)}")
            else:
                print(f"  {key}: {value}")
    
    elif args.command == "auto-update":
        if args.action == "start":
            kb.start_auto_update()
        elif args.action == "stop":
            kb.stop_auto_update()
        elif args.action == "status":
            print(f"自动更新服务状态: {'运行中' if kb.running else '已停止'}")
    
    elif args.command == "backup":
        kb.backup_index()
    
    elif args.command == "optimize":
        kb.indexer.optimize_index()
        print("索引优化完成")
    
    elif args.command == "classify":
        stats = kb.get_category_stats()
        print("知识分类统计:")
        print(f"\n总文档数: {stats['total_docs']}")
        print(f"\n分类详情:")
        for cat_code, cat_info in stats['categories'].items():
            print(f"\n  [{cat_code}] {cat_info['name']}:")
            print(f"    描述: {cat_info['description']}")
            print(f"    文档数: {cat_info['count']}")
            print(f"    占比: {(cat_info['count']/stats['total_docs']*100):.1f}%")
        
        if args.show_detail:
            print("\n详细分类信息:")
            all_docs = kb.markdown_loader.load_all()
            classified = kb.classifier.classify_documents(all_docs)
            for cat, docs in classified.items():
                cat_name = kb.classifier.get_category_name(cat)
                print(f"\n  {cat_name} ({len(docs)}):")
                for doc in docs[:5]:  # 只显示前5个
                    print(f"    - {doc.get('title', '')[:50]}...")
    
    elif args.command == "merge":
        print(f"开始整合相似知识（相似度阈值: {args.threshold}）...")
        categorized = kb.classifier.categorize_and_merge(
            kb.markdown_loader.load_all()
        )
        
        print("\n知识整合结果:")
        for category, docs in categorized.items():
            cat_name = kb.classifier.get_category_name(category)
            merged_count = sum(1 for doc in docs if doc.get('merged_from', 1) > 1)
            print(f"\n  {cat_name}:")
            print(f"    文档总数: {len(docs)}")
            print(f"    整合文档数: {merged_count}")
        
        print("\n整合完成！")
    
    elif args.command == "detect-region":
        print("🔍 开始自动检测地区地质特征...\n")
        
        result = None
        
        if args.file:
            print(f"检测文件: {args.file}")
            result = kb.detect_region(file_path=args.file, output_report=args.report)
        elif args.dir:
            print(f"批量扫描目录: {args.dir}")
            result = kb.detect_region(input_dir=args.dir, output_report=args.report)
        elif args.scan_all:
            # 扫描所有已转换的文档内容
            print("扫描所有已转换文档...")
            all_docs = kb.markdown_loader.load_all()
            detected_count = 0
            for doc in all_docs:
                content = doc.get('content', '')
                if content:
                    text_detection = kb.region_detector.detect_from_text(content)
                    if text_detection and text_detection.get('matched_signatures'):
                        detected_count += 1
            print(f"从 {len(all_docs)} 个文档中检测到 {detected_count} 个包含地区特征的文档")
            result = {'total_files_scanned': len(all_docs), 'text_detections': detected_count}
        else:
            # 如果没有指定参数，自动扫描本地文档目录中的所有数据文件
            print("未指定文件或目录，自动扫描 data/ 目录...")
            result = kb.detect_region(input_dir='data', output_report=args.report)
        
        # 显示结果
        if result:
            summary = result.get('summary', {})
            if summary.get('signatures_found'):
                print(f"\n{'='*50}")
                print("检测结果摘要:")
                for sid, info in summary['signatures_found'].items():
                    print(f"  ✅ {info['name']}: {info['count']} 个文件")
                    for f in info['files'][:3]:
                        print(f"     - {f}")
                if summary.get('all_tags'):
                    print(f"\n  自动标注: {', '.join(summary['all_tags'])}")
                if summary.get('all_knowledge'):
                    print(f"  关联知识: {', '.join(summary['all_knowledge'])}")
                print(f"{'='*50}")
            else:
                print("未检测到已知的地质特征签名。")
            
            # 打印知识推荐
            for r in result.get('results', []):
                recs = r.get('recommendations', [])
                if recs:
                    print(f"\n📖 知识推荐 - {os.path.basename(r['file'])}:")
                    for rec in recs:
                        print(f"   [{rec['category']}] {rec['title']}")
        else:
            print("未找到可检测的测井数据文件。")
    
    elif args.command == "add":
        kb.add_local_document(args.content, args.title, args.category)
        print(f"文档已添加: {args.title}")
    
    elif args.command == "import":
        print(f"开始批量导入文档...")
        print(f"输入目录: {args.input}")
        print(f"输出目录: {args.output}")
        
        converter = DocumentConverter()
        converted, skipped = converter.batch_convert(
            args.input, 
            args.output, 
            recursive=args.recursive
        )
        
        if args.rebuild_index:
            print("\n重建索引...")
            kb.build_index(incremental=False)
        
        print(f"\n批量导入完成: 成功转换 {converted} 个文档, 跳过 {skipped} 个")
    
    elif args.command == "update":
        print("开始更新知识库...")
        
        if not args.index_only:
            print("1/2: 爬取网络更新源...")
            for url in kb.config["auto_update"]["update_sources"]:
                print(f"  爬取: {url}")
                kb.crawl_url(url)
        
        if not args.crawl_only:
            print("2/2: 重建索引...")
            kb.build_index(incremental=True)
        
        print("知识库更新完成!")
    
    elif args.command == "project":
        pm = ProjectKnowledgeManager()
        
        if args.project_action == "create":
            print(f"创建项目: {args.name}")
            pm.create_project(
                project_name=args.name,
                description=args.description,
                region=args.region,
                keywords=args.keywords,
                source_dirs=args.source_dir
            )
            print(f"项目 {args.name} 创建成功!")
        
        elif args.project_action == "list":
            projects = pm.list_projects()
            if projects:
                print("\n项目列表:")
                for i, proj in enumerate(projects, 1):
                    print(f"\n[{i}] {proj.get('name', '')}")
                    print(f"   地区: {proj.get('region', '')}")
                    print(f"   描述: {proj.get('description', '')}")
                    print(f"   文档数: {proj.get('document_count', 0)}")
                    print(f"   更新时间: {proj.get('last_updated', '')}")
            else:
                print("暂无项目")
        
        elif args.project_action == "info":
            info = pm.get_project_info(args.name)
            if info:
                print(f"\n项目信息 - {args.name}:")
                for key, value in info.items():
                    print(f"  {key}: {value}")
            else:
                print(f"项目 {args.name} 不存在")
        
        elif args.project_action == "import":
            print(f"向项目 {args.name} 导入文档...")
            count = pm.import_documents(
                project_name=args.name,
                source_dir=args.input,
                recursive=args.recursive,
                filter_logging=not args.no_filter
            )
            print(f"成功导入 {count} 个文档")
        
        elif args.project_action == "crawl":
            print(f"为项目 {args.name} 爬取网络知识...")
            count = pm.crawl_for_project(
                project_name=args.name,
                urls=args.url,
                region_keywords=args.region_keywords
            )
            print(f"成功爬取 {count} 个网页")
        
        elif args.project_action == "search":
            results = pm.search_project(args.name, args.query, top_n=args.top_n)
            if results:
                print(f"\n项目 {args.name} 搜索结果:")
                for i, result in enumerate(results, 1):
                    print(f"\n[{i}] {result['title']}")
                    print(f"来源: {result['source']}")
                    print(f"摘要: {result['content'][:150]}...")
            else:
                print(f"项目 {args.name} 中未找到相关内容")
        
        elif args.project_action == "update":
            print(f"更新项目 {args.name}...")
            crawl_urls = args.url if args.url else None
            count = pm.update_project(args.name, crawl_urls=crawl_urls, reimport=args.reimport)
            print(f"成功更新 {count} 个文档")
        
        elif args.project_action == "delete":
            confirm = input(f"确定删除项目 {args.name} 吗? (y/n): ")
            if confirm.lower() == 'y':
                pm.delete_project(args.name)
            else:
                print("取消删除")
        
        elif args.project_action is None:
            project_parser.print_help()
    
    elif args.command is None:
        parser.print_help()
    
    # 执行完成提示
    _print_completion_message(kb)

def _print_completion_message(kb):
    """打印执行完成提示信息"""
    stats = kb.get_stats()
    
    # 格式化知识大小的辅助函数
    def _format_size(size_bytes):
        if size_bytes >= 1024**3:  # >= 1GB
            return f"{size_bytes / 1024**3:.2f} G"
        elif size_bytes >= 1024**2:  # >= 1MB
            return f"{size_bytes / 1024**2:.2f} M"
        elif size_bytes >= 1024:  # >= 1KB
            return f"{size_bytes / 1024:.2f} K"
        else:
            return f"{size_bytes} B"
    
    print("\n" + "="*60)
    print("【测井解释知识库 - 操作完成】")
    print("="*60)
    
    # 知识库统计
    print(f"\n📚 知识库状态:")
    print(f"   总文档数: {stats.get('total_docs', 0)}")
    print(f"   本地文档: {stats.get('local_docs', 0)}")
    print(f"   爬取文档: {stats.get('crawled_docs', 0)}")
    
    # 知识数据大小
    total_size = stats.get('knowledge_size_bytes', 0)
    local_size = stats.get('local_size_bytes', 0)
    crawled_size = stats.get('crawled_size_bytes', 0)
    index_size = stats.get('index_size_bytes', 0)
    print(f"\n💾 知识数据大小:")
    print(f"   总大小:   {_format_size(total_size)}")
    print(f"   本地文档: {_format_size(local_size)}")
    print(f"   爬取文档: {_format_size(crawled_size)}")
    print(f"   索引数据: {_format_size(index_size)}")
    
    # 自动更新状态
    auto_update_enabled = stats.get('auto_update_enabled', False)
    if auto_update_enabled:
        interval = stats.get('update_interval_hours', 24)
        print(f"\n🔄 自动更新: 已启用 (每{interval}小时)")
        if stats.get('last_updated'):
            from datetime import datetime, timedelta
            last_update = datetime.fromisoformat(stats['last_updated'].replace('Z', '+00:00'))
            next_update = last_update + timedelta(hours=interval)
            print(f"   上次更新: {last_update.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   下次更新: {next_update.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"\n🔄 自动更新: 已禁用")
    
    # 存储位置（醒目显示）
    print(f"\n📁 【知识库存储位置】")
    print(f"   ┌─────────────────────────────────────────────────")
    print(f"   │ 索引目录:      {os.path.abspath(stats.get('index_path', 'index'))}")
    print(f"   │ 本地文档:      {os.path.abspath('data/local/')}")
    print(f"   │ 爬取文档:      {os.path.abspath('data/crawled/')}")
    print(f"   │ 项目知识库:    {os.path.abspath('projects/')}")
    print(f"   │ 备份目录:      {os.path.abspath('data/backup/')}")
    print(f"   └─────────────────────────────────────────────────")
    
    # 调用方式提示
    print(f"\n💡 调用方式:")
    print(f"   命令行: python logIntKnowledge.py <command>")
    print(f"   Python API: from logIntKnowledge import WellLogKnowledgeBase")
    print(f"   HTTP API: python logIntKnowledge.py api [-p 8000]")
    
    # HTTP API调用示例
    print(f"\n🌐 HTTP API调用示例:")
    print(f"   # 搜索知识库")
    print(f"   curl \"http://localhost:8000/api/search?query=阿尔奇公式&region=大庆\"")
    print(f"   # 向AI提问")
    print(f"   curl \"http://localhost:8000/api/ask?question=如何计算含水饱和度\"")
    print(f"   # 获取知识库统计")
    print(f"   curl http://localhost:8000/api/stats")
    print(f"   # 获取所有地区信息")
    print(f"   curl http://localhost:8000/api/regions")
    print(f"   # API文档: http://localhost:8000/docs")
    
    # Python API调用示例
    print(f"\n🐍 Python API调用示例:")
    print(f"   from logIntKnowledge import WellLogKnowledgeBase")
    print(f"   kb = WellLogKnowledgeBase()")
    print(f"   ")
    print(f"   # 搜索知识库（支持地区/井名过滤）")
    print(f"   results = kb.search('阿尔奇公式', region='大庆', well_name='W123')")
    print(f"   ")
    print(f"   # 向AI提问")
    print(f"   result = kb.ask('如何计算含水饱和度?')")
    print(f"   print(result['answer'])")
    print(f"   ")
    print(f"   # 获取统计信息")
    print(f"   stats = kb.get_stats()")
    
    # 自动更新说明
    print(f"\n🔄 自动更新服务:")
    if auto_update_enabled:
        print(f"   状态: 已启用")
        print(f"   频率: 每{interval}小时自动爬取更新")
        print(f"   更新源: {len(kb.config['auto_update']['update_sources'])} 个专业网站")
        print(f"   下次更新: {next_update.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"   状态: 已禁用")
        print(f"   启动命令: python logIntKnowledge.py auto-update start")
    
    # 地区地质特征自动检测
    print(f"\n🔍 地区地质特征自动检测:")
    print(f"   单文件:  python logIntKnowledge.py detect-region -f data/3-sps-111d_lqc.las")
    print(f"   批量扫描: python logIntKnowledge.py detect-region -d data/ -r report.md")
    print(f"   扫描文档: python logIntKnowledge.py detect-region --scan-all")
    print(f"   Python API:")
    print(f"      from logIntKnowledge import RegionDetector")
    print(f"      rd = RegionDetector()")
    print(f"      result = rd.detect_from_file('data/well.las')")
    print(f"      print(rd.generate_detection_report(result))")
    
    # 项目/地区知识库调用
    print(f"\n📁 项目/地区知识库:")
    print(f"   创建项目: python logIntKnowledge.py project create -n 大庆油田项目 -r 大庆 -s F:/360/大庆资料/")
    print(f"   搜索项目: python logIntKnowledge.py project search -n 大庆油田项目 -q 阿尔奇参数")
    
    # API服务器启动
    print(f"\n🚀 API服务器:")
    print(f"   启动API: python logIntKnowledge.py api --port 8000")
    print(f"   API文档: http://localhost:8000/docs")
    print(f"   健康检查: http://localhost:8000/api/health")
    
    # 批量文档导入
    print(f"\n📥 批量文档导入:")
    print(f"   导入目录: python logIntKnowledge.py import -i F:/360/资料/ -r -ri")
    print(f"   (支持PDF/Word/PPT/Excel/CSV/LAS/图片 转知识库)")
    print(f"   注意：PDF使用Docling→MinerU→PaddleOCR多级回退，支持多语言OCR")
    
    # 知识库导出
    print(f"\n📤 知识库导出:")
    print(f"   python logIntKnowledge.py export -o ./knowledge_summary/")
    
    # Python API
    print(f"\n🐍 Python调用:")
    print(f"   from logIntKnowledge import WellLogKnowledgeBase, RegionDetector")
    print(f"   kb = WellLogKnowledgeBase(auto_scan=False)  # 创建知识库实例")
    print(f"   results = kb.search('孔隙度计算', top_n=5)")
    print(f"   answer = kb.ask('阿尔奇公式参数应如何选择')")
    print(f"")  
    print(f"   # 地区特征自动检测")
    print(f"   rd = RegionDetector()")
    print(f"   detection = rd.detect_from_file('data/well.las')")
    print(f"   print(rd.generate_detection_report(detection))")
    
    print("\n" + "="*60)
    print("操作完成！如有问题请查看帮助: python logIntKnowledge.py --help")
    print("="*60)

if __name__ == "__main__":
    main()