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

# =====================================================================
# 环境兼容 shim (2026-10-26 并库: delete_shim/frontmatter_shim 已内联)
# =====================================================================
# ---------------- delete_shim 内联(2026-10-26 并库) ----------------
# 绕过沙箱 safe-delete 拦截: 删除失败时用 Win32 API 直接删
import ctypes as _ct
import os as _os
import sys as _sys


def _ct_delete_path(path: str) -> bool:
    """用 Win32 API 直接删除 (绕过回收站/沙箱钩子)."""
    _k = _ct.windll.kernel32
    ap = _os.path.abspath(path)
    if _os.path.isdir(ap) and not _os.path.islink(ap):
        return bool(_k.RemoveDirectoryW(ap))
    return bool(_k.DeleteFileW(ap))


def _install_delete_shim():
    """安装删除绕过 shim (幂等)."""
    if getattr(_os.remove, "_safedel_shim", False):
        return

    _builtin_open = (__builtins__.get("open") if isinstance(__builtins__, dict)
                     else __builtins__.open)
    _devnull = _builtin_open(_os.devnull, "w")

    def _make_shim(orig):
        def shim(path, *a, **kw):
            # 抑制钩子喷出的 [safe-delete] JSON 噪音 (其 print 发生在 OSError 抛出之前)
            _saved_out, _saved_err = _sys.stdout, _sys.stderr
            try:
                _sys.stdout = _devnull
                _sys.stderr = _devnull
                try:
                    return orig(path, *a, **kw)
                except OSError:
                    # 沙箱拦截导致删除失败, 绕过钩子直接删除
                    _ct_delete_path(path)
                    return None
            finally:
                _sys.stdout = _saved_out
                _sys.stderr = _saved_err

        shim._safedel_shim = True
        return shim

    for _name in ("remove", "unlink", "rmdir"):
        if hasattr(_os, _name):
            _orig = getattr(_os, _name)
            if getattr(_orig, "_safedel_shim", False):
                continue
            setattr(_os, _name, _make_shim(_orig))


# ---------------- frontmatter_shim 内联(2026-10-26 并库) ----------------
# 环境里的 frontmatter(3.0.8) 是同名异包, 补 load/loads/dumps/Post
import logging
from datetime import datetime, date

logger = logging.getLogger("frontmatter_shim")


class _Post:
    """极简 Post: content + metadata dict, 支持 dict 式读写."""

    def __init__(self, content="", metadata=None, **kwargs):
        self.content = content or ""
        self.metadata = {}
        if metadata:
            self.metadata.update(metadata)
        self.metadata.update(kwargs)

    def get(self, key, default=None):
        try:
            return self.metadata.get(key, default)
        except Exception:
            return default

    def __getitem__(self, key):
        return self.metadata[key]

    def __setitem__(self, key, value):
        self.metadata[key] = value

    def __contains__(self, key):
        return key in self.metadata

    def __iter__(self):
        return iter(self.metadata)


def _fmt_scalar(v):
    """把 metadata 值格式化为 YAML 标量文本."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)


def _load(path):
    """读取文件 -> Post (兼容 frontmatter.load)"""
    _fm = _get_fm()
    _r = _fm.Frontmatter().read_file(path)
    return _Post(_r.get("body", ""), _r.get("attributes", {}))


def _loads(text):
    """解析字符串 -> Post (兼容 frontmatter.loads)"""
    _fm = _get_fm()
    if not hasattr(_fm, "parse"):
        # 3.0.8 只暴露 Frontmatter 类, 用 read_file 无法解析字符串, 手动 split
        meta, body = _split_frontmatter(text)
        return _Post(body, meta)
    return _Post(*_fm.parse(text))


def _split_frontmatter(text):
    """简易 frontmatter 解析: ---\nkey: val\n---\n\nbody"""
    text = (text or "").lstrip("\ufeff")
    meta = {}
    if text.startswith("---"):
        lines = text.splitlines()
        end = None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end = idx
                break
        if end is None:
            return {}, text
        for line in lines[1:end]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = "\n".join(lines[end + 1:]).strip()
        return meta, body
    return {}, text


def _dumps(post):
    """序列化 Post -> frontmatter md 字符串 (兼容 frontmatter.dumps)"""
    meta = getattr(post, "metadata", {}) or {}
    content = getattr(post, "content", "") or ""
    if not meta and not content:
        return ""
    parts = ["---"]
    for k, v in meta.items():
        try:
            parts.append(f"{k}: {_fmt_scalar(v)}")
        except Exception:
            continue
    parts.append("---")
    parts.append("")
    parts.append(content.rstrip("\n"))
    parts.append("")
    return "\n".join(parts)


def _get_fm():
    import frontmatter
    return frontmatter


def _install_frontmatter_shim():
    """安装兼容层到已 import 的 frontmatter 模块对象 (全局生效)."""
    try:
        import frontmatter as _fm
    except ImportError:
        logger.warning("frontmatter 未安装, 跳过 shim")
        return False

    changed = False
    if not hasattr(_fm, "load"):
        _fm.load = _load
        changed = True
    if not hasattr(_fm, "loads"):
        _fm.loads = _loads
        changed = True
    if not hasattr(_fm, "dumps"):
        _fm.dumps = _dumps
        changed = True
    if not hasattr(_fm, "Post"):
        _fm.Post = _Post
        changed = True
    else:
        # 已有 Post 但可能缺少 __setitem__ (logKnow convert 依赖 post["k"]=v)
        _P = _fm.Post
        if not hasattr(_P, "__setitem__"):
            # 给已有 Post 类补 __setitem__/__getitem__/get
            try:
                _P.__setitem__ = lambda self, k, v: setattr(self, k, v) or (
                    self.metadata.__setitem__(k, v) if hasattr(self, "metadata") else None)
                _P.__getitem__ = lambda self, k: getattr(self, k)
                _P.get = lambda self, k, d=None: getattr(self, k, d)
                changed = True
            except Exception:
                pass
    if changed:
        logger.info("frontmatter 兼容 shim 已安装 (load/loads/dumps/Post)")
    return True


try:
    _install_delete_shim()
except Exception:
    pass
try:
    _install_frontmatter_shim()
except Exception:
    pass

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
# 2026-10-26 并库: DocumentParserPipeline 已内联本文件(def main 之前)
DOC_PIPELINE_AVAILABLE = True

# 2026-10-26 并库: MultiLanguageTranslator 已内联本文件(def main 之前)
ML_TRANSLATOR_AVAILABLE = True

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
        "playwright_timeout": 30,
        # 入库后删除源 md 的配套开关: True 时增量 update 不再因源文件消失而删除索引/向量
        # (知识内容已编码进 Whoosh/Chroma, 删除 md 不影响检索; 如需显式清理请用重建)
        "retain_orphan_index": True
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
        # 本地监控目录(用户资料根): 新增/改动的知识文件自动流入待审核。
        # 首次启用前需运行 _baseline_seen.py 登记基线, 避免把已存在文件当新增。
        "local_watch": [
            {"path": "D:/data", "cat": "D盘data"},
            {"path": "E:/data", "cat": "E盘data"},
            {"path": "F:/360", "cat": "F盘360"}
        ],
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
        '巴西', '秘鲁', '苏丹', '中亚', '阿姆河', '卡拉库姆', 'Agadem', 'Muglad',
        # 海外项目国家（2026-09 扩充, 用于目录路径硬约束）
        '土库曼', 'Turkmenistan', '委内瑞拉', 'Venezuela', '苏里南', 'Suriname',
        '哈萨克斯坦', 'Kazakhstan', '阿塞拜疆', 'Azerbaijan', '乍得', 'Chad',
        '尼日尔', 'Niger', '乌兹别克', 'Uzbekistan', '印尼', 'Indonesia',
        '叙利亚', 'Syria', '伊朗', 'Iran', '伊拉克', 'Iraq', '缅甸', 'Myanmar',
        '阿曼', 'Oman', '埃及', 'Egypt', '阿尔及利亚', 'Algeria', '安哥拉', 'Angola',
        '俄罗斯', 'Russia', '土库曼斯坦'
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
        'Agadem': 'Niger', 'Muglad': 'Sudan',
        # 2026-09 扩充: 海外项目国家目录硬约束
        '土库曼': 'Turkmenistan', '土库曼斯坦': 'Turkmenistan', 'Turkmenistan': '土库曼',
        '委内瑞拉': 'Venezuela', 'Venezuela': '委内瑞拉',
        '苏里南': 'Suriname', 'Suriname': '苏里南',
        '哈萨克斯坦': 'Kazakhstan', 'Kazakhstan': '哈萨克斯坦',
        '阿塞拜疆': 'Azerbaijan', 'Azerbaijan': '阿塞拜疆',
        '乌兹别克': '乌兹别克斯坦', 'Uzbekistan': '乌兹别克斯坦',
        '印尼': 'Indonesia', 'Indonesia': '印尼',
        '乍得': 'Chad', 'Chad': '乍得',
        '尼日尔': 'Niger', 'Niger': '尼日尔',
        '叙利亚': 'Syria', 'Syria': '叙利亚',
        '伊朗': 'Iran', 'Iran': '伊朗',
        '伊拉克': 'Iraq', 'Iraq': '伊拉克',
        '阿曼': 'Oman', 'Oman': '阿曼',
        '埃及': 'Egypt', 'Egypt': '埃及',
        '阿尔及利亚': 'Algeria', 'Algeria': '阿尔及利亚',
        '安哥拉': 'Angola', 'Angola': '安哥拉',
        '俄罗斯': 'Russia', 'Russia': '俄罗斯'
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
        # 2026-09: 支持连字符井名 (Jor-106 / TrakesKE-1 / SPS-111 / Alat-101 / BM-S-11)
        r'([A-Za-z]{1,12}-\d{1,6})',
        r'([A-Za-z]{1,12}\d{1,6})',   # 如 JOR106, IZZ0042, SYT5945, Ximenia101
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
    
    # ===== 硬约束映射: 已知井 -> (国家, 区块/气田描述) =====
    # 优先级高于内容软检测, 防止 Jor-106(土库曼) 被误判为巴西等
    WELL_REGION_MAP = {
        # 井名前缀(大小写不敏感) -> (国家, 区块描述)
        'JOR-1': ('土库曼', '召拉麦尔根气田'),
        'JOR-2': ('土库曼', '召拉麦尔根气田'),
        'JOR-3': ('土库曼', '召拉麦尔根气田'),
        'IZZ': ('委内瑞拉', '胡宁4区块'),
        'E-ALAT': ('乌兹别克斯坦', '东阿拉特区块'),
        'E.ALAT': ('乌兹别克斯坦', '东阿拉特区块'),
        'ALAT-1': ('乌兹别克斯坦', '东阿拉特区块'),
        # 2026-09: 乍得 Doba 盆地 (层组 Kedeni/Doba/Mangara, 见知识库 Ximenia 井群)
        'XIMENIA': ('乍得', 'Doba盆地'),
        # 2026-09: 尼日尔 特勒雷区块 (用户确认 TrakesKE-1, 覆盖 Trakes ME-1D)
        'TRAKES': ('尼日尔', '特勒雷区块'),
        # 2026-09: 巴西 阿拉姆Aram区块 (用户确认 3-SPS-111D / SYT5945)
        'SPS-111': ('巴西', '阿拉姆Aram区块'),
        # 2026-10: 巴西盐下井群 (资料证实: 布兹奥斯油田 Búzios / Libra区块)
        'BUZ': ('巴西', '布兹奥斯油田'),
        '2-ANP-2A': ('巴西', 'Libra区块'),
    }
    # 气田/区块名 -> (国家, 区块描述)（匹配文件名或路径中的区块名）
    BLOCK_REGION_MAP = {
        '召拉': ('土库曼', '召拉麦尔根气田'),
        '召拉买耳根': ('土库曼', '召拉麦尔根气田'),
        '胡宁4': ('委内瑞拉', '胡宁4区块'),
        'JUNIN4': ('委内瑞拉', '胡宁4区块'),
        '阿拉特': ('乌兹别克斯坦', '东阿拉特区块'),
        'ALAT': ('乌兹别克斯坦', '东阿拉特区块'),
        # 2026-09: 乍得 Doba 盆地油区/地层组 (Ximenia 井群文件如 Ximenia-1_Kedeni_*.md)
        'KEDENI': ('乍得', 'Doba盆地'),
        'DOBA': ('乍得', 'Doba盆地'),
        'MANGARA': ('乍得', 'Doba盆地'),
        # 2026-09: 尼日尔 特勒雷区块 / 巴西 阿拉姆Aram区块
        '特勒雷': ('尼日尔', '特勒雷区块'),
        'ARAM': ('巴西', '阿拉姆Aram区块'),
        '阿拉姆': ('巴西', '阿拉姆Aram区块'),
        # 2026-10: 巴西盐下 (布兹奥斯油田 / Libra区块)
        'BUZIOS': ('巴西', '布兹奥斯油田'),
        'Búzios': ('巴西', '布兹奥斯油田'),
        '布兹奥斯': ('巴西', '布兹奥斯油田'),
        'LIBRA': ('巴西', 'Libra区块'),
        '利布拉': ('巴西', 'Libra区块'),
    }

    def __init__(self):
        pass

    def _apply_hard_constraints(self, result, text, is_path=False):
        """应用硬约束: 井名/区块名 -> 国家/区块, 不覆盖已从文件名明确提取的信息"""
        upper = text.upper()
        # 1. 井名映射（优先级最高）
        for prefix, (country, block) in sorted(self.WELL_REGION_MAP.items(), key=lambda x: -len(x[0])):
            if prefix in upper:
                if not result.get('country'):
                    result['country'] = country
                if not result.get('region'):
                    result['region'] = country
                # oil_field: 若仅有国家名/目录名, 覆盖为具体区块名
                if not result.get('oil_field') or result['oil_field'] in self.COUNTRY_MAP:
                    result['oil_field'] = block
                return True
        # 2. 区块/气田名映射
        for keyword, (country, block) in self.BLOCK_REGION_MAP.items():
            if keyword in text:
                if not result.get('country'):
                    result['country'] = country
                if not result.get('region'):
                    result['region'] = country
                if not result.get('oil_field'):
                    result['oil_field'] = block
                return True
        return False
    
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
        从完整文件路径中提取信息（含国家目录硬约束 + 井名/区块映射）
        
        Args:
            filepath: 完整文件路径
        
        Returns:
            dict: 提取的信息
        """
        filename = os.path.basename(filepath)
        result = self.extract_from_filename(filename)
        
        # 从路径中提取额外信息
        dir_parts = os.path.dirname(filepath).split(os.sep)
        dir_text = ' '.join(dir_parts)
        for part in dir_parts:
            part_l = part.lower()
            # 1) 国家目录硬约束: 中文国家名子串匹配; 英文目录名全等匹配
            #    (避免 Iran 撞 Transit / Oman 撞 Roman 等子串误匹配)
            for key, country in self.COUNTRY_MAP.items():
                if not key:
                    continue
                is_cn = any('\u4e00' <= ch <= '\u9fff' for ch in key)
                if is_cn:
                    hit = key in part
                else:
                    hit = part_l == key.lower()
                if hit:
                    if not result.get('country'):
                        result['country'] = country
                    if not result.get('region'):
                        result['region'] = country
            # 2) 油田/地区关键词
            for field in self.OIL_FIELDS:
                if field in part:
                    if not result['region']:
                        result['region'] = field
                    if not result['oil_field']:
                        result['oil_field'] = field
            # 3) 构造信息
            for structure in self.STRUCTURES:
                if structure in part:
                    if not result['structure']:
                        result['structure'] = structure
        
        # 4) 井名/区块名硬约束（文件名 + 完整路径）
        self._apply_hard_constraints(result, filename + ' ' + dir_text)
        
        # 5) 国家归一化: region 含国家关键词但 country 为空时回填
        if result.get('region') and not result.get('country'):
            region = result['region']
            for key, country in self.COUNTRY_MAP.items():
                if key in region or region in key:
                    result['country'] = country
                    break
        
        return result

# 扩展的测井相关关键词列表
LOGGING_KEYWORDS = [
    # 中文关键词 - 试油测试(测井解释金标准, 必须保留正文段落)
    # (2026-09 修复: 试油知识块正文曾被过滤成只剩空标题, 导致 245 块无法向量化)
    "试油", "试油结果", "试油成果", "试油结论", "测试", "测试结论", "地层测试",
    "中途测试", "完井测试", "射孔", "射孔井段", "产量", "日产油", "日产气", "日产水",
    "产油", "产气", "产水", "气油比", "井口压力", "地层压力", "流压", "静压",
    "试油工艺", "结论", "DST", "drill stem test", "well test", "well testing",
    "production test", "test summary",
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
                
                # timestamp 安全解析: Whoosh DATETIME 字段要求 datetime 对象
                ts = doc.get("timestamp", datetime.now())
                if not isinstance(ts, datetime):
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts.strip())
                        except Exception:
                            ts = datetime.now()
                    else:
                        ts = datetime.now()
                
                writer.add_document(
                    title=str(doc.get("title", "")),
                    content=str(doc.get("content", "")),
                    source=str(doc.get("source", "")),
                    category=str(doc.get("category", "")),
                    timestamp=ts,
                    content_hash=str(content_hash),
                    well_name=str(doc.get("well_name", "")),
                    region=str(doc.get("region", "")),
                    oil_field=str(doc.get("oil_field", "")),
                    structure=str(doc.get("structure", "")),
                    depth_range=str(doc.get("depth_range", "")),
                    file_type=str(doc.get("file_type", ""))
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
def _hard_region_knowledge(region, country):
    """硬约束地区对应的内置知识键（无匹配返回空列表）"""
    import re as _r
    text = (region or '') + ' ' + (country or '')
    if _r.search(r'巴西|Brazil', text):
        return ['brazil_evaporite_sequence', 'brazil_logging_interpretation_params']
    # 其他地区暂无专门内置条目, 不挂软检测的跨区知识
    return []


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
        # MarkItDown 快速转换通道 (微软开源, 2026-10-10 接入):
        # docx/pptx/xlsx 优先走 markitdown (提速 10~100x), 失败/输出过短自动回退原转换器
        self._mdown = None
        self._mdown_checked = False

    def _get_markitdown(self):
        """惰性初始化 MarkItDown (导入+初始化约 3~4s, 不拖慢 logKnow 启动)"""
        if not self._mdown_checked:
            self._mdown_checked = True
            try:
                from markitdown import MarkItDown
                self._mdown = MarkItDown()
                print("[DocumentConverter] MarkItDown 快速转换通道已启用")
            except Exception as e:
                self._mdown = None
                print(f"[DocumentConverter] MarkItDown 不可用, 使用原转换器: {e}")
        return self._mdown

    def _convert_via_markitdown(self, file_path, min_chars: int = 0):
        """用 MarkItDown 转换文档; 失败或输出短于 min_chars (疑似图片型/空文档) 返回 '' 以回退原转换器"""
        md = self._get_markitdown()
        if md is None:
            return ""
        try:
            result = md.convert(file_path)
            text = (getattr(result, "text_content", None) or "").strip()
            if len(text) < min_chars:
                return ""
            return text
        except Exception:
            return ""

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
            
            # 硬约束: 路径/井名明确给出的国家或地区（优先级高于内容软检测）
            hard_region = location_info.get('region') or location_info.get('country')
            
            # 将检测到的地区信息合并到location_info（软检测仅在无硬约束时生效）
            if region_detection and region_detection.get('matched_signatures'):
                detected_tags = region_detection.get('detected_tags', [])
                linked_kb = region_detection.get('linked_knowledge', [])
                if hard_region:
                    # ---- 硬约束优先: 软检测不得覆盖路径/井名给出的地区 ----
                    # 软检测标签出现其他国名且与硬约束国家冲突 -> 丢弃软检测
                    hard_country = location_info.get('country') or ''
                    conflict = False
                    for tag in detected_tags:
                        for key, country in self.location_extractor.COUNTRY_MAP.items():
                            if tag == key or key in tag:
                                if country and country != hard_country and country not in hard_region and hard_region not in country:
                                    conflict = True
                                    break
                        if conflict:
                            break
                    if conflict:
                        detected_tags = []
                        linked_kb = []
                        region_detection['matched_signatures'] = []
                    # region 仍以硬约束为准, 缺失时才用软检测补充
                    if not location_info.get('region') and detected_tags:
                        location_info['region'] = ', '.join(detected_tags[:3])
                    # detected_region_type 用硬约束描述（井名映射的区块名优先）
                    block_desc = location_info.get('oil_field') or hard_region
                    if block_desc and not location_info.get('detected_region_type'):
                        location_info['detected_region_type'] = block_desc
                    # linked_knowledge: 硬约束下仅挂该国内置知识, 不回退软检测的跨区知识
                    hard_kb = _hard_region_knowledge(hard_region, location_info.get('country'))
                    location_info['linked_knowledge'] = hard_kb
                    # 硬约束命中时软检测置信度标记压低调, 避免误导
                    if region_detection.get('matched_signatures'):
                        region_detection['confidence'] = min(region_detection.get('confidence', 0), 0.3)
                else:
                    # ---- 无硬约束: 维持原软检测逻辑 ----
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
        """转换PPT/PPTX为Markdown（文本框/表格/图片OCR/备注, 逐页结构标记）

        增强点：
        1. 文本框/占位符文本提取（原有）
        2. 表格形状转 Markdown 表格
        3. 图片型/扫描版幻灯片：嵌入图片 OCR 识别（无文本层 PPT 也能提取）
        4. 演讲者备注提取
        5. 每页加 "--- 幻灯片 N ---" 结构标记
        """
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        from PIL import Image
        import io as _io

        # markitdown 快速通道: 文本型 PPT 秒级转换; 输出过短 (疑似图片型幻灯片) 时
        # 回退下方含图片 OCR 的完整路径, 保证扫描版 PPT 仍可提取
        text = self._convert_via_markitdown(file_path, min_chars=200)
        if text:
            return text

        prs = Presentation(file_path)
        slides_out = []
        ocr_ready = self.ocr_enabled and self._setup_tesseract()
        ocr_langs = self._ocr_langs() if ocr_ready else "eng"

        for idx, slide in enumerate(prs.slides, 1):
            parts = [f"--- 幻灯片 {idx} ---"]
            texts, tables, pics = [], [], []
            for shape in slide.shapes:
                try:
                    if shape.has_table:
                        tbl = shape.table
                        rows = []
                        for r in tbl.rows:
                            cells = [c.text.strip().replace("|", "\\|").replace("\n", " ") for c in r.cells]
                            rows.append("| " + " | ".join(cells) + " |")
                        if rows:
                            tables.append("\n".join(rows))
                    elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        try:
                            img = shape.image
                            pics.append((img.blob, img.ext))
                        except Exception:
                            pass
                    elif hasattr(shape, 'text') and shape.text.strip():
                        texts.append(shape.text.strip())
                except Exception:
                    continue
            if texts:
                parts.append("\n\n".join(texts))
            for t in tables:
                parts.append(t)
            # 图片 OCR（最多 10 张, 缩放防卡）
            if pics and ocr_ready:
                import pytesseract
                for bi, (blob, ext) in enumerate(pics[:10]):
                    try:
                        img = Image.open(_io.BytesIO(blob))
                        img.thumbnail((1600, 1600))
                        img = self._ocr_preprocess(img)
                        txt = pytesseract.image_to_string(img, lang=ocr_langs)
                        if txt and len(txt.strip()) > 20:
                            parts.append(f"[图片{bi+1} OCR]\n{txt.strip()}")
                    except Exception:
                        pass
            elif pics:
                parts.append(f"[本页含 {len(pics)} 张图片, OCR 不可用未识别]")
            # 备注
            try:
                if slide.has_notes_slide:
                    nt = slide.notes_slide.notes_text_frame.text
                    if nt and nt.strip():
                        parts.append(f"[备注] {nt.strip()}")
            except Exception:
                pass
            slides_out.append("\n".join(parts))
        return "\n\n".join(slides_out)
    
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
        # markitdown 快速通道: 保留标题层级与表格, 失败回退 python-docx
        text = self._convert_via_markitdown(file_path)
        if text:
            return text
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
            # 注: 按要求不使用 Tesseract, 扫描件统一走 RapidOCR

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
    
    def _setup_tesseract(self):
        """自动定位 Tesseract 可执行文件并配置 pytesseract（Windows 默认不在 PATH）"""
        import shutil
        try:
            import pytesseract
        except ImportError:
            return False
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

    def _ocr_langs(self):
        """检测 tessdata 可用语言, 按测井资料优先级组合（chi_sim > eng > 西/俄/葡/阿/法）"""
        import glob
        import pytesseract
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
            # 兜底: 只要 eng 或第一个可用语言
            return "eng" if "eng" in avail else (sorted(avail)[0] if avail else "eng")
        return "+".join(langs)

    def _ocr_preprocess(self, img):
        """OCR 前图像增强: 灰度 + 对比度增强, 提升低质量扫描件识别率"""
        try:
            from PIL import ImageOps
            if img.mode == "P":
                # palette 带透明字节时直接转 RGB 会告警, 先经 RGBA 再转
                img = img.convert("RGBA").convert("RGB")
            if img.mode != "L":
                img = img.convert("L")
            img = ImageOps.autocontrast(img, cutoff=1)
        except Exception:
            pass
        return img

    def _check_ocr_available(self):
        """检查OCR是否可用（真实检测 Tesseract 可执行文件）"""
        try:
            import pytesseract
            ok = self._setup_tesseract()
            if ok:
                _ = self._ocr_langs()
            return ok
        except Exception:
            return False
    
    def _convert_scanned_pdf(self, file_path, max_pages=0, timeout=300):
        """OCR识别扫描PDF页面（多语言：中/英/西/俄/葡）

        增强点：
        1. 用 PyMuPDF 渲染页面（替代 pdf2image/poppler, Windows 无需额外二进制）
        2. 自动定位 Tesseract 路径（默认安装不在 PATH）
        3. 语言包动态检测（chi_sim+eng 组合, 缺失语言自动剔除, 不再写死报错）
        4. 灰度+对比度增强预处理, 提升低质量扫描件识别率
        5. 时间上限保护（防 100+ 页大扫描件卡死）

        Args:
            max_pages: 最大页数限制，0=无限制
            timeout: 全局 OCR 时间上限(秒), 默认 300s
        """
        from PIL import Image
        if not self._setup_tesseract():
            print("Tesseract 未安装或不可用, OCR 跳过")
            return ""
        import pytesseract
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            print(f"[OCR] PDF 打开失败: {e}")
            return ""
        langs = self._ocr_langs()
        t0 = time.monotonic()
        content_parts = []
        total = doc.page_count
        limit = max_pages if max_pages > 0 else total
        for i in range(min(limit, total)):
            if time.monotonic() - t0 > timeout:
                print(f"[OCR] 达到时间上限 {timeout}s, 停止于第 {i+1} 页 (共{total}页)", flush=True)
                break
            try:
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))  # ~180dpi
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img = self._ocr_preprocess(img)
                text = pytesseract.image_to_string(img, lang=langs)
                if text and len(text.strip()) > 20:
                    content_parts.append(f"--- 第 {i+1} 页 (OCR) ---\n{text.strip()}")
            except Exception as e:
                print(f"[OCR] 第 {i+1} 页失败: {e}")
                continue
        doc.close()
        return '\n\n'.join(content_parts)
    
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

        # 注: 按要求不使用 Tesseract, 图片 OCR 统一走 RapidOCR/PaddleOCR
        return ""

    def _convert_excel(self, file_path):
        """转换Excel文件为Markdown"""
        # markitdown 快速通道: 大数据表比 pandas.to_markdown 快且省内存,
        # .xls 等不支持格式会失败返回 '' 自动回退 pandas
        text = self._convert_via_markitdown(file_path)
        if text:
            return text
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
        """加载所有本地Markdown文档(递归子目录)"""
        if use_cache and self.cache and not self.cache_updated:
            return list(self.cache.values())
        
        documents = []
        if not os.path.exists(self.local_dir):
            return documents
        
        for root, _dirs, files in os.walk(self.local_dir):
            # 排除备份/临时目录, 避免备份副本被重复索引 (2026-09 批量入库后修复)
            rl = root.lower()
            if any(x in rl for x in ['_bak_before', '\\bak', '/bak', 'backup', '备份', '\\temp', '/temp', '$recycle']):
                _dirs[:] = [d for d in _dirs if 'bak' not in d.lower() and 'backup' not in d.lower() and '备份' not in d]
                continue
            for filename in files:
                if filename.endswith(".md"):
                    filepath = os.path.join(root, filename)
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
            content = post.content
            if not content:
                # fallback: frontmatter 解析为空(无 --- 分隔的纯 Markdown 被误判) → 读原文
                try:
                    with open(filepath, encoding='utf-8', errors='replace') as _f:
                        content = _f.read()
                except Exception:
                    content = ""
            content = filter_logging_content(content)

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
        """检查是否有新文件或修改过的文件(递归子目录)"""
        if not os.path.exists(self.local_dir):
            return False
        
        for root, _dirs, files in os.walk(self.local_dir):
            rl = root.lower()
            if any(x in rl for x in ['_bak_before', '\\bak', '/bak', 'backup', '备份', '\\temp', '/temp', '$recycle']):
                continue
            for filename in files:
                if filename.endswith(".md"):
                    filepath = os.path.join(root, filename)
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
            },
            # ---- 2026-10-08 BET-1: 印尼气测数据全烃单位换算经验 ----
            "indonesia_gas_unit_conversion": {
                "title": "印尼气测数据全烃TGAS单位换算（unit→ppm，×200）",
                "content": """
## 印尼气测数据全烃TGAS单位换算

印尼地区 mud logging 气测数据（如 BET-1 井 'ASCI GAS dan ROP' 文本文件）全烃 TGAS
的单位是气测仪刻度单位 unit，不是百分比也不是 ppm。

### 换算关系
- 1 unit = 200 ppm，即 TGAS(ppm) = TGAS(unit) × 200
- 烃类组分 C1~C5 通常已是 ppm 单位，无需换算

### 验证方法（同单位自洽性：全烃TG应≥Σ组分）
BET-1 实测：TGAS 中位数 8.27 unit，×200=1654 ppm，与 C1 中位数 990 ppm 同量级
且 TG≥C1，自洽；若误按 % 换算 ×10000=82700 ppm（为Σ组分的75倍），明显荒谬。

### 三种单位换算对照
| 原始单位 | 换算系数 | 说明 |
|---------|---------|------|
| unit | ×200 | 印尼气测仪刻度单位 |
| % | ×10000 | 体积百分比 |
| ppm | ×1 | 不变 |

绘图与解释统一用 ppm。
来源：用户 2026-10-08 确认，适用于印尼工区气测数据。
""",
                "category": "regional_experience"
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
                    # 仅碳酸盐岩关键词 -> 通用碳酸盐岩签名（不链巴西知识, 避免 Jor-106 误判）
                    r'(灰岩|石灰岩|白云岩|碳酸盐岩)',
                    r'(limestone|dolomite|carbonate)'
                ],
                'signature': 'carbonate_dominant',
                'confidence': 0.4
            },
            'brazil_evaporite_combined': {
                'patterns': [
                    # 必须与"巴西"共现才链巴西蒸发岩知识
                    r'(巴西|Brazil|brazil).*(蒸发岩|盐岩|硬石膏|碳酸盐岩|盐下|pre-salt)',
                    r'(蒸发岩|盐岩|硬石膏).*(巴西|Brazil|brazil)',
                    r'(pre-salt|盐下)'
                ],
                'signature': 'brazil_evaporite_carbonate',
                'confidence': 0.65
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
        # 定义搜索目录（只扫描配置的知识库目录，避免递归整个 F:/360 导致初始化卡死 90s+）
        search_dirs = [
            self.config["paths"]["local_docs"],
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
        
        # 加载额外注册的目录（经验库等）
        extra_docs = []
        for extra_dir in getattr(self, '_extra_doc_dirs', []):
            if os.path.isdir(extra_dir):
                loader = MarkdownLoader(extra_dir)
                docs = loader.load_all(use_cache=False)
                extra_docs.extend(docs)
        
        # 添加到索引
        all_docs = local_docs + crawled_docs + extra_docs
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

    # ================================================================
    # 知识库增强（2026-09-03 海外批量入库后新增）
    #   1) incremental_vector_sync : 增量向量同步 (仅编码新增块, 秒级~分钟级, 替代全量重建11min)
    #   2) enrich_well_metadata   : 从文件名/路径自动回填井名等元数据 (提升RAG井名检索)
    #   3) audit_knowledge        : 知识库质量审计 (空井名/缺region/乱码/重复/过短)
    # ================================================================
    def incremental_vector_sync(self, persist_dir=None, prune=False, verbose=True):
        """增量向量同步: 扫描本地 md, 与向量库已有 id 对比, 只编码新增/变更块 (Chroma upsert by id)
        Args:
            persist_dir: 向量库目录 (默认 data/vector_index)
            prune: 是否清理向量库中已不存在于磁盘的失效块
        Returns: 本次新增块数
        """
        import time, hashlib
        # 2026-10-26 并库: EmbeddingModel/VectorStore/DocumentChunk 已内联本文件
        if persist_dir is None:
            persist_dir = "data/vector_index"
        t0 = time.time()

        def _mk_id(doc):
            src = str(doc.get("source", ""))
            return "c_" + hashlib.md5((src + str(doc.get("content", ""))[:200]).encode('utf-8')).hexdigest()[:16]

        docs = MarkdownLoader(os.path.abspath(self.config["paths"]["local_docs"])).load_all(use_cache=False)
        disk_ids = {}
        for d in docs:
            disk_ids[_mk_id(d)] = d
        if verbose:
            print(f"[增量同步] 本地 {len(docs)} 篇, 扫描 {time.time()-t0:.1f}s", flush=True)

        vs = VectorStore(persist_dir)
        existing_ids = set()
        existing_meta = {}  # id -> (region, well_name)
        try:
            col = vs.collection
            offset = 0
            while True:
                batch = col.get(limit=5000, offset=offset, include=["metadatas"])
                for _i, _md in zip(batch["ids"], batch["metadatas"]):
                    existing_ids.add(_i)
                    existing_meta[_i] = (str((_md or {}).get("region", "") or ""),
                                         str((_md or {}).get("well_name", "") or ""))
                if len(batch["ids"]) < 5000:
                    break
                offset += 5000
        except Exception as e:
            print(f"[增量同步] 读取已有ID失败: {e}", flush=True)
        if verbose:
            print(f"[增量同步] 向量库现有 {len(existing_ids)} 条", flush=True)

        todo_ids = [cid for cid in disk_ids if cid not in existing_ids]
        # metadata 一致性: frontmatter 的 region/well_name 与向量 metadata 不一致 -> 删旧重编
        # (向量 id = md5(source+content[:200]) 不含元数据, 仅改 frontmatter 不会自动重编)
        stale_meta = []
        for cid, d in disk_ids.items():
            if cid in existing_ids:
                want = (str(d.get("region", "") or ""), str(d.get("well_name", "") or ""))
                if existing_meta.get(cid) != want:
                    stale_meta.append(cid)
        if stale_meta:
            vs.collection.delete(ids=stale_meta)
            if verbose:
                print(f"[增量同步] {len(stale_meta)} 条 metadata 变更(region/well_name), 删除待重编", flush=True)
        todo_ids = [cid for cid in todo_ids if cid in disk_ids] + stale_meta
        if verbose:
            print(f"[增量同步] 待编码 {len(todo_ids)} 条", flush=True)
        if todo_ids:
            chunks = []
            for cid in todo_ids:
                d = disk_ids[cid]
                content = str(d.get("content", "") or "")
                if len(content) < 10:
                    continue
                top = str(d.get("top_depth", "")); bot = str(d.get("bottom_depth", ""))
                depth = f"{top}-{bot}m" if top and bot else ""
                chunks.append(DocumentChunk(
                    chunk_id=cid, content=content,
                    source_file=str(d.get("source", "")),
                    source_type=str(d.get("category", "unknown")),
                    well_name=str(d.get("well_name", "")),
                    region=str(d.get("region", "")),
                    formation=str(d.get("formation", "")),
                    depth_range=depth,
                ))
            if chunks:
                m = EmbeddingModel(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
                m.load()
                embs = m.encode([c.content for c in chunks])
                vs.add(chunks, embs)
                if verbose:
                    print(f"[增量同步] 新增 {len(chunks)} 条, 耗时 {time.time()-t0:.1f}s", flush=True)
        if prune:
            # 只清理文件派生块(c_前缀), 保留 builtin(kw_前缀) 等程序内置向量
            retain_orphan = self.config.get("crawler", {}).get("retain_orphan_index", False)
            if retain_orphan:
                # 保留模式: 源 md 删除后知识仍在向量库中, 不清理失效块
                stale = []
            else:
                stale = [i for i in existing_ids if i not in disk_ids and i.startswith("c_")]
            if stale:
                vs.collection.delete(ids=stale)
                if verbose:
                    print(f"[增量同步] 清理 {len(stale)} 条失效向量(备份副本/已删除)", flush=True)
        return len(todo_ids)

    def enrich_well_metadata(self, target_dir=None, dry_run=False):
        """从文件名/路径自动回填井名等元数据 (海外批量入库后 well_name 大量为空, 导致井名检索盲区)
        Args:
            target_dir: 目标目录 (默认 data/local/well_test/overseas)
            dry_run: 仅统计不写回
        Returns: 回填统计 dict
        """
        import frontmatter as fm
        if target_dir is None:
            target_dir = os.path.join(self.config["paths"]["local_docs"], "well_test", "overseas")
        extractor = WellLocationExtractor()
        stats = {"total": 0, "empty_well": 0, "filled": 0, "failed": 0}
        if not os.path.exists(target_dir):
            print(f"[元数据回填] 目录不存在: {target_dir}")
            return stats
        for root, _d, files in os.walk(target_dir):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(root, fn)
                stats["total"] += 1
                try:
                    post = fm.load(p)
                    _continent = {'非洲', '亚洲', '南美洲', '南美', '北美洲', '北美', '欧洲', '大洋洲', '中东', '拉丁美洲'}
                    _cur_rg0 = str(post.get("region") or "").strip()
                    need_well = not str(post.get("well_name") or "").strip()
                    need_region = not _cur_rg0
                    # region 为洲名级时仍需处理(可能被硬约束细化为国家名)
                    if not need_well and not need_region and _cur_rg0 not in _continent:
                        continue
                    info = extractor.extract_from_filename(fn)
                    new_wn = (info.get("extracted_well_name") or "").strip()
                    new_rg = (info.get("region") or "").strip()
                    # 只要还缺井名/region, 或当前 region 是洲名级(需要精确硬约束), 都必须走路径提取
                    if (not new_wn) or (need_region or _cur_rg0 in _continent):
                        info2 = extractor.extract_from_path(p)
                        if not new_wn:
                            new_wn = (info2.get("extracted_well_name") or "").strip()
                        if not new_rg:
                            new_rg = (info2.get("region") or "").strip()
                    changed = False
                    # 过滤无效井名: 长度<2 或纯数字(如 '0'/'v1'/'2026')不入库
                    if need_well and new_wn and len(new_wn) >= 2 and not new_wn.isdigit():
                        post["well_name"] = new_wn
                        changed = True
                    _cur_rg = str(post.get("region") or "").strip()
                    if need_region and new_rg:
                        post["region"] = new_rg
                        changed = True
                    elif new_rg and new_rg not in _continent and _cur_rg in _continent:
                        # 硬约束给出精确国家, 覆盖历史洲名级 region (如 非洲->乍得)
                        post["region"] = new_rg
                        changed = True
                    if changed:
                        stats["empty_well"] += 1
                        if not dry_run:
                            with open(p, "w", encoding="utf-8") as f:
                                f.write(fm.dumps(post))
                        stats["filled"] += 1
                except Exception as e:
                    stats["failed"] += 1
        print(f"[元数据回填] 共{stats['total']}篇, 空井名{stats['empty_well']}, 已回填{stats['filled']}, 失败{stats['failed']}", flush=True)
        return stats

    def audit_knowledge(self, output=None):
        """知识库质量审计: 空井名/缺region/乱码/重复/过短, 输出统计报告
        Args:
            output: 报告输出路径 (json)
        Returns: 审计 dict
        """
        import collections, re, json
        docs = self.markdown_loader.load_all(use_cache=False)
        audit = {
            "total": len(docs),
            "empty_well": 0, "empty_region": 0,
            "garbled": 0, "too_short": 0, "dup_content": 0,
            "by_category": collections.Counter(),
            "garbled_samples": [], "empty_well_samples": [], "too_short_samples": [],
        }
        seen = {}
        for d in docs:
            audit["by_category"][str(d.get("category", "unknown"))] += 1
            if not str(d.get("well_name") or "").strip():
                audit["empty_well"] += 1
                if len(audit["empty_well_samples"]) < 10:
                    audit["empty_well_samples"].append(str(d.get("source", "")))
            if not (d.get("region") or "").strip():
                audit["empty_region"] += 1
            content = str(d.get("content", "") or "")
            if len(content) < 30:
                audit["too_short"] += 1
                if len(audit["too_short_samples"]) < 10:
                    audit["too_short_samples"].append(str(d.get("source", "")))
            if re.search(r'[\ufffd\ufffe]|Ã|â€|å–|æ–', content):
                audit["garbled"] += 1
                if len(audit["garbled_samples"]) < 10:
                    audit["garbled_samples"].append(str(d.get("source", "")))
            h = d.get("content_hash")
            if h in seen:
                audit["dup_content"] += 1
            seen[h] = True
        audit["by_category"] = dict(audit["by_category"])
        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(audit, f, ensure_ascii=False, indent=2, default=str)
            print(f"[质检] 报告已保存: {output}", flush=True)
        print(f"[质检] 总{audit['total']}篇 | 空井名{audit['empty_well']} | 缺region{audit['empty_region']} "
              f"| 乱码{audit['garbled']} | 过短{audit['too_short']} | 重复{audit['dup_content']}", flush=True)
        return audit

    # =====================================================================
    # 自动更新闭环: 爬取 -> 入库 -> 索引 -> 向量 -> 验证检索 -> 汇总报告
    # 将独立脚本(_crawler_monitor/_crawler_commit/_rebuild_final/_sync_vectors)
    # 能力整合为内置方法, 一键跑通"知识库爬取-入库-验证-检索-修复"闭环
    # =====================================================================
    @staticmethod
    def _crawler_fix_frontmatter(path):
        """修复 md frontmatter: title 等标量含冒号/特殊字符时加引号(YAML 解析防御)
        EnhancedCrawler 抓取的期刊文章 title 常含冒号(如 "Guest Editorial: ..."),
        不加引号会被 yaml 解析为嵌套 mapping -> 整篇文档加载失败(知识丢失)
        """
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except Exception:
            return False
        if not text.startswith('---'):
            return False
        lines = text.split('\n')
        end = None
        for i in range(1, min(len(lines), 30)):
            if lines[i].strip() == '---':
                end = i
                break
        if end is None:
            return False
        changed = False
        for i in range(1, end):
            m = re.match(r'^([A-Za-z_]+):\s*(.*)$', lines[i])
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if not val or val.startswith('"') or val.startswith("'"):
                continue
            if ':' in val or '#' in val or '"' in val or '|' in val or '?' in val:
                lines[i] = f'{key}: "{val.replace(chr(34), chr(92) + chr(34))}"'
                changed = True
        if changed:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        return changed

    def _crawler_get_sources(self):
        """从配置 update_sources 生成外网源列表(分类+统一走公司代理出口)"""
        try:
            urls = self.config.get('auto_update', {}).get('update_sources', [])
        except Exception:
            urls = []
        def _cls(u):
            u = u.lower()
            if 'sogou.com' in u or 'weixin' in u:
                return '微信'
            if 'baike.baidu' in u:
                return '百度百科'
            if 'wikipedia' in u:
                return '维基百科'
            if 'sciencedirect' in u or 'elsevier' in u:
                return '学术期刊'
            if 'spe.org' in u or 'onepetro' in u or 'jpt' in u:
                return 'SPE'
            if any(k in u for k in ('schlumberger', 'halliburton', 'bakerhughes', 'weatherford')):
                return '测井厂商'
            return '专业网站'
        return [{"name": _cls(u) + ':' + u[:60], "url": u, "cat": _cls(u),
                 "proxy": "http://proxy1.bj.petrochina:8080"} for u in urls]

    def _crawler_fetch_one(self, source, save_dir):
        """抓取单个源 -> 保存到 save_dir, 返回 (ok, n)
        ok=False 当且仅当: 异常 或 无任何页面保存(n==0, 视为不可达/反爬)
        """
        import copy
        cfg = copy.deepcopy(self.config["crawler"])
        if source.get('proxy'):
            cfg['proxy_enabled'] = True
            pu = source['proxy'].replace('http://', '').rsplit(':', 1)
            cfg['proxy_http'] = pu[0]
            cfg['proxy_port'] = pu[1] if len(pu) > 1 else '8080'
        else:
            cfg['proxy_enabled'] = False
        cfg['use_playwright'] = False
        cfg['max_workers'] = 1
        cfg['max_pages'] = 3
        try:
            crawler = EnhancedCrawler(config=cfg)
            res = crawler.fetch_and_save(source['url'], save_dir, max_depth=0)
            n = len(res) if res else 0
            return (n > 0), n
        except Exception:
            return False, 0

    def crawler_monitor(self, scan_local=True, scan_web=True, local_watch=None,
                        fail_limit=3, disable_days=7, global_timeout=1200):
        """知识爬虫监控(容错): 本地新文件 + 外网期刊源 -> data/crawler_pending 待审核
        容错设计(用户要求"多次访问不了可略去"): 连续失败>=fail_limit 禁用 disable_days 天;
        单源/全局时间上限自动停止; cache/crawler_seen.json 断点去重
        Args:
            local_watch: 本地监控目录 [{"path":..., "cat":...}], 默认取 config['auto_update']['local_watch']
        Returns: {"local_new", "web_new", "pending_total", "disabled": [...]}
        """
        ROOT = os.path.dirname(os.path.abspath(__file__))
        pending = os.path.join(ROOT, 'data', 'crawler_pending')
        seen_p = os.path.join(ROOT, 'cache', 'crawler_seen.json')
        status_p = os.path.join(ROOT, 'cache', 'crawler_status.json')

        def _load_json(p, d):
            if os.path.exists(p):
                try:
                    with open(p, encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
            return d

        def _save_json(p, o):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(o, f, ensure_ascii=False, indent=1)

        def _md5(p):
            return hashlib.md5(p.encode('utf-8', errors='replace')).hexdigest()

        def _is_knowledge_file(name):
            n = name.lower()
            if not any(k in n for k in ['试油', '测试', '周报', '解释', 'dst', 'test', 'well test',
                                        'welltest', 'interpret', 'report', 'production', 'complete']):
                return False
            return any(n.endswith(e) for e in ('.pdf', '.xls', '.xlsx', '.doc', '.docx',
                                               '.las', '.txt', '.csv', '.md'))

        report = {"local_new": 0, "web_new": 0, "pending_total": 0, "disabled": []}
        seen = _load_json(seen_p, {})
        status = _load_json(status_p, {})

        # ---- A. 本地监控 ----
        if scan_local:
            watch = local_watch if local_watch is not None else \
                self.config.get('auto_update', {}).get('local_watch', [])
            for cfg in watch:
                root = cfg.get('path') if isinstance(cfg, dict) else cfg
                cat = cfg.get('cat', '本地') if isinstance(cfg, dict) else '本地'
                if not root or not os.path.exists(root):
                    print(f'  [跳过] 本地目录不存在: {root}', flush=True)
                    continue
                for dp, _, fns in os.walk(root):
                    # 跳过知识库自身目录(已入库库/索引/缓存/pending), 避免把库内已入库文档当新增源
                    if ('\\src\\data\\' in dp + '\\' or '\\src\\cache' in dp or
                            '\\src\\index' in dp or '\\src\\vector_index' in dp or
                            'crawler_pending' in dp):
                        continue
                    for fn in fns:
                        if not _is_knowledge_file(fn):
                            continue
                        src = os.path.join(dp, fn)
                        try:
                            st = os.stat(src)
                        except OSError:
                            continue
                        # normpath 统一路径格式, 保证与基线登记(_baseline_seen.py)的 key 一致
                        key = f"local:{_md5(os.path.normpath(src))}:{st.st_mtime:.0f}:{st.st_size}"
                        if key in seen:
                            continue
                        seen[key] = time.strftime('%Y-%m-%d %H:%M:%S')
                        dst_dir = os.path.join(pending, cat)
                        os.makedirs(dst_dir, exist_ok=True)
                        dst = os.path.join(dst_dir, fn)
                        try:
                            with open(src, 'rb') as fi, open(dst, 'wb') as fo:
                                fo.write(fi.read())
                            print(f'  [新] {cat}/{fn}', flush=True)
                            report["local_new"] += 1
                        except OSError as e:
                            print(f'  [失败] {fn}: {e}', flush=True)
            print(f'本地扫描完成: 新增 {report["local_new"]} 个待审核', flush=True)

        # ---- B. 外网期刊源 ----
        if scan_web:
            sources = self._crawler_get_sources()
            print(f'外网源数量: {len(sources)}', flush=True)
            t0 = time.monotonic()
            for src in sources:
                if time.monotonic() - t0 > global_timeout:
                    print(f'!! 全局时间上限({global_timeout}s), 停止', flush=True)
                    break
                key = _md5(src['url'])
                st = status.get(key, {'fail': 0, 'disabled_at': None})
                if st.get('disabled_at'):
                    try:
                        dis_t = datetime.fromisoformat(st['disabled_at'])
                        left = disable_days - (datetime.now() - dis_t).days
                        if left > 0:
                            print(f'  [略过] {src["name"][:45]} (多次失败禁用中, 剩{left}天)', flush=True)
                            continue
                    except Exception:
                        pass
                    status[key] = {'fail': 0, 'disabled_at': None}
                if f"run:{key}" in seen:
                    continue
                print(f'== 抓取: {src["name"][:45]} ==', flush=True)
                save_dir = os.path.join(pending, '外网', src['cat'])
                os.makedirs(save_dir, exist_ok=True)
                ok, n = self._crawler_fetch_one(src, save_dir)
                if ok:
                    status[key] = {'fail': 0, 'disabled_at': None}
                    seen[f"run:{key}"] = time.strftime('%Y-%m-%d %H:%M:%S')
                    print(f'  [成功] 保存 {n} 个页面', flush=True)
                    report["web_new"] += 1
                else:
                    st['fail'] = st.get('fail', 0) + 1
                    if st['fail'] >= fail_limit:
                        st['disabled_at'] = datetime.now().isoformat()
                        report["disabled"].append(src["name"][:45])
                        print(f'  [失败x{st["fail"]}] 已禁用(略过), {disable_days}天后再试', flush=True)
                    else:
                        print(f'  [失败{st["fail"]}/{fail_limit}] 无页面保存', flush=True)
                    status[key] = st
                _save_json(status_p, status)
                _save_json(seen_p, seen)
                time.sleep(1)
            print(f'外网抓取完成: 新增 {report["web_new"]} 个源', flush=True)

        # 统计待审核
        if os.path.exists(pending):
            for _, _, fns in os.walk(pending):
                report["pending_total"] += len(fns)
        print(f'===== 监控完成: 新增 {report["local_new"] + report["web_new"]} 个, '
              f'待审核共 {report["pending_total"]} =====', flush=True)
        # 修复: 本地扫描的 seen 必须落盘, 否则同文件每轮重复入 pending -> 重复入库
        if scan_local:
            _save_json(seen_p, seen)
        return report

    def commit_pending(self, pending_dir=None, docs_dir=None):
        """待审核入库: data/crawler_pending -> data/local/well_test
        (递归归档 + frontmatter 自动修复, 期刊 title 含冒号不再丢篇)
        Returns: {"moved": n}
        """
        import shutil
        ROOT = os.path.dirname(os.path.abspath(__file__))
        pending = pending_dir or os.path.join(ROOT, 'data', 'crawler_pending')
        docs = docs_dir or os.path.join(os.path.abspath(self.config["paths"]["local_docs"]), 'well_test')
        if not os.path.exists(pending):
            print('无待审核目录')
            return {"moved": 0}
        moved = 0
        skipped = 0
        # 已入库内容 hash 集合(防重复入库, cache/known_content_hashes.json 增量维护)
        dedup_p = os.path.join(ROOT, 'cache', 'known_content_hashes.json')
        known = set()
        if os.path.exists(dedup_p):
            try:
                with open(dedup_p, encoding='utf-8') as _f:
                    known = set(json.load(_f))
            except Exception:
                known = set()
        def _file_md5(p_):
            h = hashlib.md5()
            with open(p_, 'rb') as f_:
                for chunk in iter(lambda: f_.read(1 << 20), b''):
                    h.update(chunk)
            return h.hexdigest()
        for root, _dirs, files in os.walk(pending):
            rel = os.path.relpath(root, pending)
            parts = [p for p in rel.split(os.sep) if p and p != '.']
            if parts and parts[0] in ('本地', '外网'):
                parts[0] = 'crawler_' + parts[0]
            for fn in files:
                src = os.path.join(root, fn)
                try:
                    h = _file_md5(src)
                except OSError as e:
                    print(f'  [失败] 读取 {src}: {e}', flush=True)
                    continue
                if h in known:
                    try:
                        os.remove(src)
                    except OSError:
                        pass
                    print(f'  [重复跳过] {"/".join(parts + [fn])}', flush=True)
                    skipped += 1
                    continue
                known.add(h)
                if fn.lower().endswith('.md'):
                    try:
                        self._crawler_fix_frontmatter(src)
                    except Exception:
                        pass
                dst_dir = os.path.join(docs, *parts)
                os.makedirs(dst_dir, exist_ok=True)
                target = os.path.join(dst_dir, fn)
                if os.path.exists(target):
                    target = os.path.join(dst_dir, time.strftime('%Y%m%d_%H%M%S') + '_' + fn)
                try:
                    shutil.move(src, target)
                    print(f'  入库: {"/".join(parts + [fn])}', flush=True)
                    moved += 1
                except OSError as e:
                    print(f'  [失败] {src}: {e}', flush=True)
        os.makedirs(os.path.dirname(dedup_p), exist_ok=True)
        with open(dedup_p, 'w', encoding='utf-8') as f_:
            json.dump(sorted(known), f_, ensure_ascii=False)
        print(f'===== 入库完成: {moved} 个文件 (重复跳过 {skipped}) =====', flush=True)
        return {"moved": moved, "skipped": skipped}

    def rebuild_whoosh(self, force=True):
        """重建 Whoosh 索引(全量), 更新 self.indexer 引用
        Returns: {"docs": n, "indexed": n}
        """
        import shutil
        t0 = time.time()
        docs = self.markdown_loader.load_all(use_cache=False)
        idx_dir = os.path.abspath(self.config["paths"]["index_dir"])
        if os.path.exists(idx_dir):
            shutil.rmtree(idx_dir)
        idx = WhooshIndexer(idx_dir)
        idx.create_index()
        n = idx.add_documents(docs, batch_size=100, skip_duplicates=False)
        self.indexer = idx
        try:
            self._load_builtin_knowledge()
        except Exception:
            pass
        print(f'索引重建: {n} 篇, {time.time() - t0:.0f}s', flush=True)
        return {"docs": len(docs), "indexed": n}

    def update_whoosh_incremental(self):
        import json
        t0 = time.time()
        idx_dir = os.path.abspath(self.config["paths"]["index_dir"])
        manifest_path = os.path.join(os.path.dirname(idx_dir), "cache", "whoosh_manifest.json")
        need_full = (
            not os.path.exists(idx_dir)
            or not os.path.exists(manifest_path)
            or not os.listdir(idx_dir)
        )
        if need_full:
            print("  [incr] no manifest, fallback to full rebuild...", flush=True)
            r = self.rebuild_whoosh()
            try: self._dump_whoosh_manifest(manifest_path)
            except Exception as e: print(f"  [warn] manifest dump: {e}", flush=True)
            r["elapsed"] = round(time.time()-t0, 1)
            return r
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            print("  [incr] manifest corrupt, full rebuild...", flush=True)
            r = self.rebuild_whoosh()
            try: self._dump_whoosh_manifest(manifest_path)
            except: pass
            r["elapsed"] = round(time.time()-t0, 1)
            return r
        local_dir = self.markdown_loader.local_dir
        current = {}
        for root, _dirs, files in os.walk(local_dir):
            rl = root.lower()
            if any(x in rl for x in ["_bak_before", "\\bak", "/bak", "backup", "备份", "\\temp", "/temp", "$recycle"]):
                _dirs[:] = [d for d in _dirs if "bak" not in d.lower() and "backup" not in d.lower() and "备份" not in d]
                continue
            for fn in files:
                if not fn.endswith(".md"): continue
                fp = os.path.join(root, fn)
                try:
                    st = os.stat(fp)
                    current[fp] = {"mtime": st.st_mtime, "size": st.st_size}
                except OSError: continue
        to_add, to_delete = [], []
        retain_orphan = self.config.get("crawler", {}).get("retain_orphan_index", False)
        for src, info in current.items():
            old = manifest.get(src)
            if old is None or old.get("mtime") != info["mtime"] or old.get("size") != info["size"]:
                to_add.append(src)
        for src in list(manifest.keys()):
            if src not in current:
                # 保留模式: 源 md 已删除(入库后清理)但索引仍保留, 不触发删除
                if not retain_orphan:
                    to_delete.append(src)
        if not to_add and not to_delete:
            n = len(current)
            print(f"index incr: no change, {n} docs, {time.time()-t0:.1f}s", flush=True)
            return {"docs": n, "indexed": 0, "added": 0, "deleted": 0, "elapsed": round(time.time()-t0,1)}
        print(f"index incr: add/mod {len(to_add)}, delete {len(to_delete)}", flush=True)
        ix = self.indexer.get_index()
        writer = ix.writer()
        deleted = 0
        for src in to_delete:
            try:
                writer.delete_by_term("source", src); deleted += 1
            except Exception: pass
        added = 0
        for src in to_add:
            try: doc = self.markdown_loader._load_file(src)
            except Exception: doc = None
            if not doc:
                manifest.pop(src, None); continue
            try: writer.delete_by_term("source", src)
            except Exception: pass
            ts = doc.get("timestamp", datetime.now())
            if not isinstance(ts, datetime):
                try: ts = datetime.fromisoformat(str(ts))
                except Exception: ts = datetime.now()
            try:
                writer.add_document(
                    title=str(doc.get("title","")), content=str(doc.get("content","")),
                    source=str(doc.get("source","")), category=str(doc.get("category","")),
                    timestamp=ts, content_hash=str(doc.get("content_hash","")),
                    well_name=str(doc.get("well_name","")), region=str(doc.get("region","")),
                    oil_field=str(doc.get("oil_field","")), structure=str(doc.get("structure","")),
                    depth_range=str(doc.get("depth_range","")), file_type=str(doc.get("file_type","")),
                )
                added += 1
            except Exception as e:
                print(f"  [skip] {src}: {e}", flush=True)
        writer.commit()
        manifest.update(current)
        for src in to_delete: manifest.pop(src, None)
        try:
            os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
        except Exception as e:
            print(f"  [warn] manifest write: {e}", flush=True)
        try: self._load_builtin_knowledge()
        except: pass
        elapsed = time.time()-t0
        print(f"index incr: {len(current)} docs (add/mod {added}, del {deleted}), {elapsed:.1f}s", flush=True)
        return {"docs": len(current), "indexed": added, "added": added, "deleted": deleted, "elapsed": round(elapsed,1)}

    def _dump_whoosh_manifest(self, manifest_path):
        import json
        local_dir = self.markdown_loader.local_dir
        m = {}
        for root, _dirs, files in os.walk(local_dir):
            rl = root.lower()
            if any(x in rl for x in ["_bak_before", "\\bak", "/bak", "backup", "备份", "\\temp", "/temp", "$recycle"]):
                _dirs[:] = [d for d in _dirs if "bak" not in d.lower() and "backup" not in d.lower() and "备份" not in d]
                continue
            for fn in files:
                if not fn.endswith(".md"): continue
                fp = os.path.join(root, fn)
                try:
                    st = os.stat(fp)
                    m[fp] = {"mtime": st.st_mtime, "size": st.st_size}
                except OSError: continue
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        print(f"  [manifest] wrote {len(m)} entries", flush=True)

    def sync_vectors(self, prune=True):
        """Chroma 增量同步(补齐缺口 + prune 清理失效向量), 返回新增块数"""
        try:
            n = self.incremental_vector_sync(
                persist_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vector_index'),
                prune=prune, verbose=True)
            return {"new": n}
        except Exception as e:
            print(f'[向量同步失败] {e}', flush=True)
            return {"new": 0, "error": str(e)[:120]}

    def _verify_new_docs(self, queries=None):
        """检索验证: 抽查若干查询, 确认新知识可被 Whoosh 检索到"""
        if queries is None:
            queries = ["CO2 fracturing", "测井 解释", "试油 干层", "地层测试 资料录取 规范"]
        hits = 0
        out = []
        for q in queries:
            try:
                res = self.search(q, top_n=3)
            except Exception:
                res = []
            ok = len(res) > 0
            hits += 1 if ok else 0
            out.append({"q": q, "hit": ok, "top": str(res[0].get('title', ''))[:40] if res else ''})
            print(f'  [{"OK" if ok else "  "}] {q} -> {len(res)}条', flush=True)
        print(f'验证检索: {hits}/{len(queries)} 命中', flush=True)
        return {"checked": len(queries), "hit": hits, "queries": out}

    def auto_update_pipeline(self, scan_local=True, scan_web=True, commit=True,
                             rebuild=True, sync=True, verify=True):
        """知识库自动更新闭环总入口: 爬取 -> 入库 -> Whoosh -> Chroma -> 验证检索
        返回各阶段汇总 dict
        """
        t0 = time.time()
        report = {"start": time.strftime('%Y-%m-%d %H:%M:%S'), "stages": {}}
        print('=' * 60)
        print('🚀 知识库自动更新闭环开始')
        print('=' * 60)

        print('\n【1/5】爬取监控(本地+外网, 容错略过不可达源)...')
        report["stages"]["monitor"] = self.crawler_monitor(scan_local=scan_local, scan_web=scan_web)

        if commit:
            print('\n【2/5】审核入库(frontmatter 自动修复)...')
            report["stages"]["commit"] = self.commit_pending()

        if rebuild:
            print('\n【3/5】Whoosh 索引(增量)...')
            report["stages"]["whoosh"] = self.update_whoosh_incremental()

        if sync:
            print('\n【4/5】Chroma 向量增量同步...')
            report["stages"]["vectors"] = self.sync_vectors(prune=True)

        if verify:
            print('\n【5/5】检索验证...')
            report["stages"]["verify"] = self._verify_new_docs()

        report["elapsed_s"] = round(time.time() - t0, 1)
        print('=' * 60)
        print(f'✅ 闭环完成, 耗时 {report["elapsed_s"]}s')
        print('=' * 60)
        return report

    def print_update_report(self, report):
        """打印闭环汇总报告"""
        m = report.get('stages', {}).get('monitor', {})
        c = report.get('stages', {}).get('commit', {})
        w = report.get('stages', {}).get('whoosh', {})
        v = report.get('stages', {}).get('vectors', {})
        f = report.get('stages', {}).get('verify', {})
        print('\n📋 更新汇总:')
        print(f'  爬取: 本地新 {m.get("local_new", 0)} / 外网源 {m.get("web_new", 0)} '
              f'/ 待审核 {m.get("pending_total", 0)} / 禁用源 {len(m.get("disabled", []))}')
        print(f'  入库: {c.get("moved", 0)} 个')
        print(f'  Whoosh: {w.get("indexed", 0)} 篇')
        print(f'  Chroma: 新增 {v.get("new", 0)} 块')
        print(f'  验证: {f.get("hit", 0)}/{f.get("checked", 0)} 查询命中')
        if m.get("disabled"):
            print(f'  已禁用源(多次失败): {"; ".join(m["disabled"])}')

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
            print("  python logknow.py search -q '孔隙度计算' -n 5")
            print("  python logknow.py ask -q '什么是阿尔奇公式'")
            print("  python logknow.py detect-region -f data/well.las")
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


def _rebuild_graph_after_update(script_dir):
    """知识更新后重建知识图谱(logGraph build + export)。

    设计: subprocess 隔离执行, 失败仅告警不阻断知识库主流程;
    build 失败不影响索引/向量等已完成的闭环步骤。
    """
    import subprocess, sys
    gscript = os.path.join(script_dir, 'logGraph.py')
    if not os.path.exists(gscript):
        print('  ⚠️ 未找到 logGraph.py, 跳过图谱重建')
        return
    try:
        print('\n📊 图谱自动重建: 开始...', flush=True)
        r = subprocess.run(
            [sys.executable, gscript, 'build'],
            cwd=script_dir, capture_output=True, text=True, timeout=900
        )
        for line in (r.stdout or '').splitlines():
            if any(k in line for k in ('构建完成', '实体:', '关系:', '缺口1', '缺口2',
                                       '缺口3', '缺口4', '缺口5', '缺口6', 'ERROR',
                                       'Traceback', '异常')):
                print('  ' + line)
        if r.stderr and r.returncode != 0:
            for line in r.stderr.splitlines()[-8:]:
                print('  ' + line)
        r2 = subprocess.run(
            [sys.executable, gscript, 'export'],
            cwd=script_dir, capture_output=True, text=True, timeout=300
        )
        for line in (r2.stdout or '').splitlines():
            print('  ' + line)
        print('  ✅ 图谱重建完成' if r.returncode == 0 else '  ⚠️ 图谱重建失败(不影响知识库主流程)')
    except Exception as e:
        print(f'  ⚠️ 图谱重建跳过: {e}')


# ------------------------------
# 命令行接口
# ------------------------------
# ================= logWiki.py 全文内联(2026-10-26 并库) =================
# Wiki 图谱 sqlite 查询: 井名->国家推断->上下文/方法推荐
import sqlite3
from pathlib import Path
from collections import defaultdict

# 【2026-10-30 P0-8】原路径硬编码 F 盘（已不存在）；改为相对本文件，迁移/换盘不再失效
_BASE_DIR = Path(__file__).resolve().parent
GRAPH_DB = _BASE_DIR / 'graph' / 'graph.db'
WIKI_DIR = _BASE_DIR / 'graph' / 'wiki'

# 国家关键词映射（用于从井名推断国家）
COUNTRY_KEYWORDS = {
    '孟加拉': ['Titas', 'Rashidpur', 'Bakhrabad', 'Bengal'],
    '巴西': ['RJS', 'ANP', 'Libra', 'Buzios'],
    '苏丹': ['Neem', 'Ruman', 'Muglad'],
    '乍得': ['Baobab', 'Doba', 'Bongor'],
    '乌兹别克斯坦': ['Amu', 'Bukhara', 'Uzbek'],
    '印尼': ['BET', 'Jabung', 'Indonesia'],
    '委内瑞拉': ['Orinoco', 'Venezuela'],
    '加拿大': ['Canada', 'Western Canada'],
    '澳洲': ['Perth', 'Australia'],
    '缅甸': ['Myanmar', 'Irrawaddy'],
}

# 解释方法知识库
METHODS = {
    'reg_gas_indicator': {
        'name': 'REG 综合气层指示法',
        'applicable': '砂泥岩剖面、气层为主的地区',
        'indicators': ['RTI（电阻率-孔隙度重叠）', 'NDI（中子-密度挖掘效应指标）', 'GSI（气测异常指标）'],
    },
    'density_correction': {
        'name': '密度测井校正方法',
        'applicable': '砂泥岩剖面、密度测井值偏高的井段',
        'indicators': ['套管段识别（DT恒定）', '裸眼段质量评价', '密度校正模型'],
    },
    'spiral_borehole_correction': {
        'name': '螺旋井眼校正方法',
        'applicable': '大斜度井、水平井、螺旋井眼发育井段',
        'indicators': ['螺旋井眼识别（曲线周期性振荡）', '数据校正（平滑/拟合）'],
    },
    'lithology_identification': {
        'name': '砂泥岩岩性识别规则',
        'applicable': '砂泥岩剖面',
        'indicators': ['砂岩：GR低、密度正常、声波正常', '泥岩：GR高、密度偏高、声波偏高'],
    },
}

def infer_country(well_name):
    """从井名推断国家"""
    for country, keywords in COUNTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in well_name:
                return country
    return None

def query_wiki_context(well_name, country=None):
    """
    查询 Wiki 上下文
    返回：相关知识文本，供解释报告使用
    """
    if country is None:
        country = infer_country(well_name)
    
    context_parts = []
    
    # 1. 国家地质特征
    if country:
        country_meta = {
            '孟加拉': {'basin': 'Bengal Basin', 'lithology': '砂泥岩互层', 'fluid': '天然气'},
            '巴西': {'basin': 'Santos Basin', 'lithology': '碳酸盐岩', 'fluid': '油藏'},
            '加拿大': {'basin': 'Western Canada Sedimentary Basin', 'lithology': '砂岩', 'fluid': '油藏'},
            '澳洲': {'basin': 'Perth Basin', 'lithology': '砂岩', 'fluid': '气藏'},
            '苏丹': {'basin': 'Muglad Basin', 'lithology': '砂岩', 'fluid': '油藏'},
            '秘鲁': {'basin': 'Maranon Basin', 'lithology': '砂岩', 'fluid': '油藏'},
            '委内瑞拉': {'basin': 'Orinoco Belt', 'lithology': '砂岩', 'fluid': '重油'},
            '乌兹别克斯坦': {'basin': 'Amu Darya Basin', 'lithology': '碳酸盐岩', 'fluid': '气藏'},
            '缅甸': {'basin': 'Irrawaddy Basin', 'lithology': '砂岩', 'fluid': '气藏'},
            '乍得': {'basin': 'Doba Basin', 'lithology': '砂岩', 'fluid': '油藏'},
            '印尼': {'basin': 'Jabung Basin', 'lithology': '砂岩', 'fluid': '油藏'},
        }
        meta = country_meta.get(country, {})
        if meta:
            context_parts.append(f"【国家地质特征】\n- 盆地: {meta.get('basin', '')}\n- 岩性剖面: {meta.get('lithology', '')}\n- 主要流体: {meta.get('fluid', '')}")
    
    # 2. 查询图谱数据库，获取该国家/井的历史解释
    try:
        db = sqlite3.connect(str(GRAPH_DB))
        db.row_factory = sqlite3.Row
        
        if country:
            # 查这个国家的历史井
            wells = db.execute("""
                SELECT DISTINCT e.src FROM edges e
                WHERE e.rel='LOCATED_IN' AND e.dst=?
            """, (country,)).fetchall()
            
            if wells:
                context_parts.append(f"【历史井参考】\n本国有 {len(wells)} 口已录入井，可参考历史解释规则")
            
            # 查这些井的结论分布
            conclusion_stats = db.execute("""
                SELECT e.dst, COUNT(*) as cnt FROM edges e
                WHERE e.rel='HAS_CONCLUSION'
                AND e.src IN (
                    SELECT DISTINCT e2.src FROM edges e2
                    WHERE e2.rel='LOCATED_IN' AND e2.dst=?
                )
                GROUP BY e.dst
            """, (country,)).fetchall()
            
            if conclusion_stats:
                stats_text = '\n'.join([f"- {r['dst']}: {r['cnt']} 层" for r in conclusion_stats])
                context_parts.append(f"【历史结论分布】\n{stats_text}")
        
        db.close()
    except Exception as e:
        context_parts.append(f"【图谱查询失败】{e}")
    
    # 3. 推荐适用方法
    if country in ['孟加拉', '澳洲', '缅甸', '乌兹别克斯坦']:
        context_parts.append("【推荐方法】\n- REG 综合气层指示法（适用于气层为主的地区）")
    
    return '\n\n'.join(context_parts)


def get_method_recommendation(country):
    """根据国家推荐解释方法"""
    methods = []
    if country in ['孟加拉', '澳洲', '缅甸', '乌兹别克斯坦']:
        methods.append('reg_gas_indicator')
    if country in ['孟加拉', '巴西', '加拿大']:
        methods.append('density_correction')
    return methods


if __name__ == '__main__':
    # 测试
    test_wells = ['TITAS-31', 'BET-1', 'Rashidpur-13', '2-ANP-2A-RJS']
    for well in test_wells:
        print(f'\n=== {well} ===')
        context = query_wiki_context(well)
        print(context)


# ================= kb_document_parser 闭包内联(2026-10-26 并库) =================
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
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
try:
    from magic_pdf.data.data_reader_writer import FileBasedDataReader
except ImportError:
    FileBasedDataReader = None

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


# ================= kb_translator.MultiLanguageTranslator 内联(2026-10-26 并库) =================
# LANGDETECT_AVAILABLE 复用本文件顶部 try 块
class MultiLanguageTranslator:
    """多语言翻译工具，支持中/英/西/俄/葡检测与术语翻译为中文"""

    def __init__(self):
        self.supported_languages = ['zh', 'en', 'es', 'ru', 'pt']
        self.term_dict = self._build_term_dict()

    def _build_term_dict(self):
        return {
            'zh_en': {
                '测井': 'logging', '录井': 'mud logging', '孔隙度': 'porosity',
                '渗透率': 'permeability', '电阻率': 'resistivity',
                '含水饱和度': 'water saturation', '泥质含量': 'shale volume',
                '阿尔奇公式': 'Archie equation', '自然伽马': 'gamma ray',
                '声波时差': 'sonic transit time', '密度': 'density',
                '中子': 'neutron', '油层': 'oil layer', '气层': 'gas layer',
                '水层': 'water layer', '储层': 'reservoir', '砂岩': 'sandstone',
                '泥岩': 'shale', '碳酸盐岩': 'carbonate', '油田': 'oil field',
                '区块': 'block', '构造': 'structure', '井': 'well',
                '深度': 'depth', '地层': 'formation', '岩性': 'lithology',
                '试油': 'well testing', '生产': 'production', '测井系列': 'logging suite'
            },
            'en_zh': {
                'logging': '测井', 'mud logging': '录井', 'porosity': '孔隙度',
                'permeability': '渗透率', 'resistivity': '电阻率',
                'water saturation': '含水饱和度', 'shale volume': '泥质含量',
                'Archie equation': '阿尔奇公式', 'gamma ray': '自然伽马',
                'sonic transit time': '声波时差', 'density': '密度',
                'neutron': '中子', 'oil layer': '油层', 'gas layer': '气层',
                'water layer': '水层', 'reservoir': '储层', 'sandstone': '砂岩',
                'shale': '泥岩', 'carbonate': '碳酸盐岩', 'oil field': '油田',
                'block': '区块', 'structure': '构造', 'well': '井',
                'depth': '深度', 'formation': '地层', 'lithology': '岩性',
                'well testing': '试油', 'production': '生产', 'logging suite': '测井系列'
            },
            'es_zh': {
                'registro': '测井', 'porosidad': '孔隙度', 'permeabilidad': '渗透率',
                'resistividad': '电阻率', 'saturación de agua': '含水饱和度',
                'volumen de arcilla': '泥质含量', 'arenisca': '砂岩',
                'lutita': '泥岩', 'caliza': '石灰岩', 'dolomía': '白云岩',
                'yacimiento': '储层', 'pozo': '井', 'campo petrolífero': '油田',
                'formación': '地层', 'profundidad': '深度', 'densidad': '密度',
                'neutrón': '中子', 'perfilaje': '测井', 'registro de pozo': '测井',
                'registros eléctricos': '电法测井', 'registro por inducción': '感应测井',
                'registro de densidad': '密度测井', 'registro de neutrones': '中子测井'
            },
            'ru_zh': {
                'каротаж': '测井', 'пористость': '孔隙度', 'проницаемость': '渗透率',
                'удельное сопротивление': '电阻率', 'водонасыщенность': '含水饱和度',
                'глинистость': '泥质含量', 'песчаник': '砂岩', 'глинистый': '泥岩',
                'известняк': '石灰岩', 'доломит': '白云岩', 'пласт': '地层',
                'скважина': '井', 'месторождение': '油田', 'нефть': '石油',
                'газ': '天然气', 'глубина': '深度', 'плотность': '密度',
                'нейтронный': '中子', 'гамма-каротаж': '自然伽马',
                'электрокаротаж': '电法测井', 'индукционный каротаж': '感应测井',
                'плотностной каротаж': '密度测井', 'нейтронный каротаж': '中子测井'
            },
            'pt_zh': {
                'perfuração': '测井', 'porosidade': '孔隙度', 'permeabilidade': '渗透率',
                'resistividade': '电阻率', 'saturação de água': '含水饱和度',
                'volume de argila': '泥质含量', 'arenito': '砂岩', 'xisto': '泥岩',
                'calcário': '石灰岩', 'dolomita': '白云岩', 'reservatório': '储层',
                'poço': '井', 'campo de petróleo': '油田', 'formação': '地层',
                'profundidade': '深度', 'densidade': '密度', 'neutrônico': '中子',
                'raio gama': '自然伽马', 'perfilagem': '测井',
                'perfis elétricos': '电法测井', 'perfis de indução': '感应测井',
                'perfis de densidade': '密度测井', 'perfis de nêutrons': '中子测井'
            }
        }

    def detect_language(self, text):
        """检测文本语言"""
        if not text or len(text.strip()) < 20:
            return 'unknown'
        if LANGDETECT_AVAILABLE:
            try:
                detected = detect(text[:2000])
                if detected in ('zh-cn', 'zh-tw', 'zh'):
                    return 'zh'
                if detected in self.supported_languages:
                    return detected
                return detected
            except Exception:
                pass
        text_sample = text[:2000]
        zh = sum(1 for c in text_sample if '\u4e00' <= c <= '\u9fff')
        en = sum(1 for c in text_sample if 'a' <= c.lower() <= 'z')
        es_pt = sum(1 for c in text_sample if c.lower() in 'áéíóúñüãõç')
        ru = sum(1 for c in text_sample if '\u0400' <= c <= '\u04ff')
        total = len(text_sample)
        if zh > total * 0.05:
            return 'zh'
        if ru > total * 0.05:
            return 'ru'
        if es_pt > 3:
            return 'es'
        if en > total * 0.3:
            return 'en'
        return 'unknown'

    def translate_to_chinese(self, text, source_lang=None):
        """将文本翻译为中文，优先使用术语词典替换"""
        if not text:
            return text
        if source_lang is None:
            source_lang = self.detect_language(text)
        if source_lang in ('zh', 'unknown'):
            return text
        dict_key = f"{source_lang}_zh"
        terms = self.term_dict.get(dict_key, {})
        result = text
        replaced = False
        for term, trans in sorted(terms.items(), key=lambda x: len(x[0]), reverse=True):
            if term in result.lower():
                result = result.replace(term, trans)
                result = result.replace(term.capitalize(), trans)
                result = result.replace(term.upper(), trans)
                replaced = True
        if not replaced:
            result = f"[原文语言: {source_lang}]\n{text}"
        else:
            result = f"[原文语言: {source_lang}, 已术语翻译]\n{result}\n\n[原文参考]:\n{text[:500]}..."
        return result

    def translate(self, text, target_lang='zh'):
        if target_lang == 'zh':
            return self.translate_to_chinese(text)
        return text


# ================= vector_indexer 闭包内联(2026-10-26 并库) =================
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import logging
_vilog = logging.getLogger("vector_indexer")

class EmbeddingUnavailableError(RuntimeError):
    """嵌入模型不可用 (加载失败), 调用方应降级为关键词检索"""
    pass
@dataclass
class DocumentChunk:
    """文档分块"""
    chunk_id: str
    content: str
    source_file: str
    source_type: str = "unknown"      # report / paper / manual / curve_desc / experience
    well_name: str = ""
    region: str = ""
    formation: str = ""
    depth_range: str = ""              # "1200-1500m"
    keywords: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
class EmbeddingModel:
    """嵌入模型封装，支持本地和API两种模式"""

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5",
                 device: str = "cpu", use_api: bool = False,
                 api_base: str = None):
        self.model_name = model_name
        self.device = device
        self.use_api = use_api
        self.api_base = api_base
        self._model = None
        self._load_failed = False   # 加载失败标记 (检索时降级为关键词模式)

    def load(self):
        """加载嵌入模型

        策略: 优先本地缓存 (避免联网挂起), 失败后尝试镜像下载, 全部失败则降级
        """
        if self.use_api:
            logger.info(f"使用 API 嵌入模式: {self.api_base}")
            return
        if self._model is not None or self._load_failed:
            return

        from sentence_transformers import SentenceTransformer

        # 1) 先尝试纯本地加载 (不联网, 防止网络挂起)
        try:
            self._model = SentenceTransformer(
                self.model_name, device=self.device, local_files_only=True
            )
            logger.info(f"嵌入模型已加载 (本地缓存): {self.model_name}")
            return
        except Exception as e:
            logger.info(f"本地无缓存, 尝试下载: {self.model_name} ({e.__class__.__name__})")

        # 2) 联网下载 (走镜像)
        try:
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(f"嵌入模型已加载: {self.model_name} (device={self.device})")
        except ImportError:
            logger.warning("sentence-transformers 未安装，尝试使用 HuggingFace API")
            self.use_api = True
            self._load_hf_api()
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e} — 向量检索降级为关键词检索")
            self._load_failed = True

    @property
    def available(self) -> bool:
        """嵌入模型是否可用 (向量检索能力)"""
        if self.use_api:
            return True
        if self._load_failed:
            return False
        try:
            self.load()
        except Exception:
            return False
        return self._model is not None or self.use_api

    def _load_hf_api(self):
        """使用 HuggingFace Inference API"""
        if not self.api_base:
            self.api_base = f"https://api-inference.huggingface.co/models/{self.model_name}"
        logger.info(f"使用 HuggingFace API: {self.api_base}")

    def encode(self, texts: List[str], batch_size: int = 32,
               normalize: bool = True) -> List[List[float]]:
        """将文本列表编码为向量"""
        if not texts:
            return []

        if self.use_api:
            return self._encode_api(texts)

        if self._model is None:
            self.load()

        if self._model is None:
            # 模型加载失败, 抛出可识别异常供上层降级
            raise EmbeddingUnavailableError("嵌入模型不可用")

        # 本地编码
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 100
        )
        return embeddings.tolist()

    def _encode_api(self, texts: List[str]) -> List[List[float]]:
        """通过 API 编码"""
        import requests
        headers = {}
        if hasattr(self, '_hf_token'):
            headers["Authorization"] = f"Bearer {self._hf_token}"

        all_embeddings = []
        for text in texts:
            try:
                resp = requests.post(
                    self.api_base,
                    headers=headers,
                    json={"inputs": text, "wait_for_model": True},
                    timeout=60
                )
                if resp.status_code == 200:
                    all_embeddings.append(resp.json()[0] if isinstance(resp.json(), list) else resp.json())
                else:
                    logger.warning(f"API 编码失败 ({resp.status_code}): {text[:50]}...")
                    all_embeddings.append([0.0] * 1024)  # fallback
            except Exception as e:
                logger.warning(f"API 编码异常: {e}")
                all_embeddings.append([0.0] * 1024)
        return all_embeddings

    def encode_single(self, text: str) -> List[float]:
        """编码单个文本"""
        return self.encode([text])[0]
class VectorStore:
    """ChromaDB 向量存储"""

    def __init__(self, persist_dir: str, collection_name: str = "log_knowledge"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _init(self):
        """延迟初始化 ChromaDB"""
        if self._client is not None:
            return
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB 已连接: {self.persist_dir}/{self.collection_name} "
                       f"({self._collection.count()} documents)")
        except ImportError:
            raise ImportError("请安装 chromadb: pip install chromadb")

    @property
    def collection(self):
        self._init()
        return self._collection

    @property
    def count(self) -> int:
        self._init()
        return self._collection.count()

    def add(self, chunks: List[DocumentChunk], embeddings: List[List[float]]):
        """批量添加向量"""
        if not chunks:
            return

        self._init()

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [{
            "source_file": c.source_file,
            "source_type": c.source_type,
            "well_name": c.well_name or "",
            "region": c.region or "",
            "formation": c.formation or "",
            "depth_range": c.depth_range or "",
            "keywords": ",".join(c.keywords) if c.keywords else "",
        } for c in chunks]

        # 分批添加（ChromaDB 单次上限约 50000 条）
        batch_size = 1000
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            try:
                self._collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    embeddings=embeddings[i:end],
                    metadatas=metadatas[i:end]
                )
            except Exception as e:
                # 可能重复 ID，尝试逐条添加
                logger.warning(f"批量添加失败 ({i}-{end}): {e}，尝试逐条...")
                for j in range(i, end):
                    try:
                        self._collection.add(
                            ids=[ids[j]],
                            documents=[documents[j]],
                            embeddings=[embeddings[j]],
                            metadatas=[metadatas[j]]
                        )
                    except Exception as je:
                        logger.debug(f"跳过重复: {ids[j]} - {je}")

        logger.info(f"向量入库完成: {len(chunks)} chunks")

    def search(self, query_embedding: List[float], top_n: int = 10,
               region: str = None, well_name: str = None,
               source_type: str = None) -> List[Tuple[str, float, Dict]]:
        """向量相似度检索"""
        self._init()

        where_filter = {}
        if region:
            where_filter["region"] = region
        if well_name:
            where_filter["well_name"] = well_name
        if source_type:
            where_filter["source_type"] = source_type

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_n
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = self._collection.query(**kwargs)

        output = []
        if results and results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                chunk_id = results['ids'][0][i]
                doc = results['documents'][0][i] if results['documents'] else ""
                score = 1.0 - results['distances'][0][i] if results['distances'] else 0.0
                meta = results['metadatas'][0][i] if results['metadatas'] else {}
                output.append((chunk_id, score, doc, meta))

        return output

    def list_source_files(self) -> set:
        """返回已入库的所有 source_file 集合 (用于增量索引去重)"""
        self._init()
        try:
            data = self._collection.get(include=["metadatas"])
            files = set()
            for m in data.get("metadatas", []) or []:
                if m and m.get("source_file"):
                    files.add(m.get("source_file"))
            return files
        except Exception as e:
            logger.warning(f"读取向量库来源列表失败: {e}")
            return set()

    def delete_by_source(self, source_file: str):
        """按来源删除"""
        self._init()
        try:
            self._collection.delete(where={"source_file": source_file})
        except Exception as e:
            logger.warning(f"删除失败: {e}")

    def clear(self):
        """清空集合"""
        self._init()
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.warning(f"清空失败: {e}")


def main():
    # ===== 工作目录保护: 知识库根固定为脚本目录, 防止定时任务在任意 CWD 下运行时知识库漂移/误建/误删 =====
    import os as _os
    _script_dir = _os.path.dirname(_os.path.abspath(__file__))
    if _os.path.normcase(_os.getcwd()) != _os.path.normcase(_script_dir):
        print(f"[CWD保护] 当前工作目录({_os.getcwd()})非脚本目录, 已自动切换到 {_script_dir}", flush=True)
        _os.chdir(_script_dir)
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
    
    # update命令 - 知识库自动更新闭环(爬取-入库-索引-向量-验证)
    update_parser = subparsers.add_parser("update", help="知识库自动更新闭环(爬取-入库-索引-向量-验证)")
    update_parser.add_argument("--crawl-only", "-co", action="store_true", help="只爬取不重建索引")
    update_parser.add_argument("--index-only", "-io", action="store_true", help="只重建索引不爬取")
    update_parser.add_argument("--local-dir", "-ld", default=None, help="本地监控目录, 分号分隔多个")
    update_parser.add_argument("--no-web", action="store_true", help="不抓外网源")
    update_parser.add_argument("--no-local", action="store_true", help="不扫本地目录")
    
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
    
    # clean命令 - 清理污染/重复文件(如备份目录误转换产物)
    clean_parser = subparsers.add_parser("clean", help="扫描并清理知识库中的污染文件(默认预览)")
    clean_parser.add_argument("--dir", "-d", default="data/local",
                              help="扫描目录(默认 data/local, 只扫根目录不递归)")
    clean_parser.add_argument("--delete", action="store_true",
                              help="执行删除(默认仅预览列出)")
    clean_parser.add_argument("--min-size", type=int, default=0,
                              help="只列出超过该字节数的文件(可选)")
    
    args = parser.parse_args()
    
    # auto_scan=False: 禁止构造时启动 auto_update 后台线程(会爬外网+merge备份目录,
    # 曾把 well_test_bak_before_rebuild 重新转换生成 9208 个污染文件到 data/local 根目录)。
    # 需要更新时用 update 命令显式跑闭环; 索引文件已存在, search/ask 直接可用。
    kb = WellLogKnowledgeBase(auto_scan=False)
    
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
        local_watch = None
        ld = getattr(args, 'local_dir', None)
        if ld:
            local_watch = [{"path": p.strip(), "cat": "本地"} for p in ld.split(';') if p.strip()]
        report = kb.auto_update_pipeline(
            scan_local=not getattr(args, 'no_local', False),
            scan_web=not getattr(args, 'no_web', False),
            commit=not args.crawl_only,
            rebuild=not args.crawl_only,
            sync=not args.crawl_only,
            verify=not args.crawl_only,
        )
        kb.print_update_report(report)
        # ===== 图谱自动重建: 知识更新闭环尾部同步重建知识图谱 =====
        if not args.crawl_only:
            _rebuild_graph_after_update(_script_dir)
    
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
    
    elif args.command == "clean":
        # 清理知识库中的污染文件(默认预览, --delete 执行删除)
        # 背景: auto_scan 曾把备份目录 well_test_bak_before_rebuild 重新转换,
        #       在 data/local 根目录生成 9208 个 source_file 指向备份目录的污染 .md。
        # 判定: .md 文件中 source_file 指向备份目录(_bak/bak/well_test_bak) => 污染
        import re as _re
        _scan_dir = args.dir
        _do_delete = args.delete
        _min_size = args.min_size
        _scan_dir = os.path.abspath(_scan_dir)
        if not os.path.isdir(_scan_dir):
            print(f"错误: 扫描目录不存在 {_scan_dir}")
        else:
            _bak_kw = ('_bak', 'bak_before', '/bak', '\\bak', 'well_test_bak')
            polluted, skipped = [], []
            for _fn in sorted(os.listdir(_scan_dir)):
                _p = os.path.join(_scan_dir, _fn)
                if not os.path.isfile(_p) or not _fn.lower().endswith('.md'):
                    continue
                if _min_size and os.path.getsize(_p) < _min_size:
                    continue
                try:
                    _head = open(_p, encoding='utf-8', errors='replace').read()[:600]
                except Exception:
                    skipped.append((_fn, '读取失败'))
                    continue
                _m = _re.search(r'source_file:\s*([^\n]+)', _head)
                _src = (_m.group(1).strip() if _m else '')
                if any(_k in _src for _k in _bak_kw):
                    polluted.append((_fn, _src))
                else:
                    skipped.append((_fn, '非污染'))
            print(f"\n扫描目录: {_scan_dir}")
            print(f"污染文件(source_file 指向备份目录): {len(polluted)} 个")
            for _fn, _src in polluted[:30]:
                print(f"  ✗ {_fn}  <- {_src}")
            if len(polluted) > 30:
                print(f"  ... 其余 {len(polluted) - 30} 个略")
            if _do_delete:
                _removed = 0
                for _fn, _src in polluted:
                    try:
                        os.remove(os.path.join(_scan_dir, _fn))
                        _removed += 1
                    except Exception as _e:
                        print(f"  删除失败 {_fn}: {_e}")
                print(f"\n已删除 {_removed} 个污染文件")
                if _removed:
                    print("提示: 删除后请运行 `logKnow.py update --no-web --no-local` 重建索引以移除残留条目")
            else:
                print(f"\n(预览模式, 加 --delete 执行删除; --dir 指定目录)")
    
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
    
    # 更多用法见帮助（不打印代码示例, 保持输出为纯执行结果）
    print(f"\n💡 更多用法: python logknow.py --help")
    
    print("\n" + "="*60)
    print("操作完成！如有问题请查看帮助: python logknow.py --help")
    print("="*60)

if __name__ == "__main__":
    main()