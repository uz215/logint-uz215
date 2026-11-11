#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫工具模块 - 提供内容提取和保存的通用功能
消除重复的内容提取和文件保存逻辑
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


class ContentExtractor:
    """内容提取工具类"""
    
    CONTENT_SELECTORS = [
        'article', 'main',
        'div[class*="content"]', 'div[class*="article"]',
        'div[id*="content"]', 'div[id*="article"]',
        '.article-content', '.post-content', '.entry-content',
        '#content', '.content',
        '.markdown-body', '.wiki-content'
    ]
    
    @classmethod
    def extract_title(cls, soup: BeautifulSoup) -> str:
        """提取页面标题"""
        if soup.title:
            title = soup.title.string
            return title.strip() if title else "Untitled"
        return "Untitled"
    
    @classmethod
    def extract_content_by_selectors(
        cls, 
        soup: BeautifulSoup, 
        selectors: Optional[List[str]] = None,
        min_length: int = 200
    ) -> Optional[str]:
        """通过选择器提取内容
        
        Args:
            soup: BeautifulSoup对象
            selectors: CSS选择器列表，如果为None则使用默认选择器
            min_length: 最小内容长度
            
        Returns:
            提取的文本内容，如果内容太短则返回None
        """
        selectors = selectors or cls.CONTENT_SELECTORS
        
        for selector in selectors:
            try:
                content_tags = soup.select(selector)
                if content_tags:
                    content_text = '\n\n'.join(
                        tag.get_text(separator='\n', strip=True) 
                        for tag in content_tags
                    )
                    if content_text and len(content_text) >= min_length:
                        return content_text
            except Exception:
                continue
        
        return None
    
    @classmethod
    def extract_paragraphs(cls, soup: BeautifulSoup) -> str:
        """提取所有段落文本"""
        paragraphs = soup.find_all('p')
        return '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    
    @classmethod
    def extract_full_text(cls, soup: BeautifulSoup) -> str:
        """提取页面所有文本"""
        return soup.get_text(separator='\n', strip=True)
    
    @classmethod
    def check_security_page(cls, soup: BeautifulSoup) -> bool:
        """检查是否为安全验证页面"""
        title = cls.extract_title(soup)
        security_keywords = [
            "安全验证", "验证码", "验证", 
            "CAPTCHA", "Security Check", 
            "人机验证", "安全检查"
        ]
        return any(keyword in title for keyword in security_keywords)
    
    @classmethod
    def check_anti_crawl_page(cls, soup: BeautifulSoup, url: str = "") -> bool:
        """检查是否为反爬页面"""
        page_text = soup.get_text().lower()
        
        anti_crawl_keywords = [
            "访问频率过快", "请稍后重试", "系统繁忙",
            "too many requests", "rate limit", 
            "access denied", "禁止访问"
        ]
        
        return any(keyword.lower() in page_text for keyword in anti_crawl_keywords)
    
    @classmethod
    def filter_by_keywords(
        cls, 
        content: str, 
        keywords: List[str],
        match_all: bool = False
    ) -> bool:
        """根据关键词过滤内容
        
        Args:
            content: 内容文本
            keywords: 关键词列表
            match_all: 是否要求匹配所有关键词，默认False表示匹配任一关键词
            
        Returns:
            是否通过过滤
        """
        content_lower = content.lower()
        keywords_lower = [k.lower() for k in keywords]
        
        if match_all:
            return all(keyword in content_lower for keyword in keywords_lower)
        else:
            return any(keyword in content_lower for keyword in keywords_lower)
    
    @classmethod
    def extract_by_class(cls, soup: BeautifulSoup, class_name: str) -> Optional[str]:
        """根据class名称提取内容"""
        content_div = soup.find('div', {'class': class_name})
        if content_div:
            return content_div.get_text(separator='\n\n', strip=True)
        return None
    
    @classmethod
    def extract_by_id(cls, soup: BeautifulSoup, element_id: str) -> Optional[str]:
        """根据id提取内容"""
        content_div = soup.find('div', {'id': element_id})
        if content_div:
            return content_div.get_text(separator='\n\n', strip=True)
        return None


class ContentSaver:
    """内容保存工具类"""
    
    def __init__(self, save_dir: str = "data/crawled"):
        self.save_dir = save_dir
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """确保保存目录存在"""
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
    
    def generate_filename(self, url: str, extension: str = ".md") -> str:
        """生成文件名"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        url_hash = hash(url) % 10000
        return f"{timestamp}_{url_hash}{extension}"
    
    def format_content(
        self, 
        title: str, 
        url: str, 
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """格式化保存内容"""
        formatted = f"# {title}\n\n"
        formatted += f"来源: {url}\n\n"
        
        if metadata:
            formatted += "元信息:\n"
            for key, value in metadata.items():
                formatted += f"- {key}: {value}\n"
            formatted += "\n"
        
        formatted += "---\n\n"
        formatted += content_text
        return formatted
    
    def save(
        self, 
        content_data: Dict[str, Any], 
        url: str,
        filename: Optional[str] = None
    ) -> bool:
        """保存内容到文件
        
        Args:
            content_data: 包含title和content的字典
            url: 内容来源URL
            filename: 可选的自定义文件名
            
        Returns:
            是否保存成功
        """
        try:
            title = content_data.get('title', 'Untitled')
            content_text = content_data.get('content', '')
            metadata = content_data.get('metadata')
            
            min_length = content_data.get('min_length', 200)
            if not content_text or len(content_text) < min_length:
                print("  ✗ 内容太少")
                return False
            
            filename = filename or self.generate_filename(url)
            filepath = os.path.join(self.save_dir, filename)
            
            formatted_content = self.format_content(title, url, content_text, metadata)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(formatted_content)
            
            print(f"  ✓ 成功! 保存到: {filename}")
            print(f"  内容长度: {len(content_text)} 字符")
            return True
            
        except IOError as e:
            print(f"  ✗ 文件保存失败: {type(e).__name__}: {e}")
            return False
        except Exception as e:
            print(f"  ✗ 保存失败: {type(e).__name__}: {e}")
            return False
    
    def save_batch(self, items: List[Dict[str, Any]], urls: List[str]) -> tuple:
        """批量保存内容
        
        Args:
            items: 内容数据列表
            urls: 对应的URL列表
            
        Returns:
            (成功数, 总数)
        """
        success_count = 0
        for content_data, url in zip(items, urls):
            if self.save(content_data, url):
                success_count += 1
        return success_count, len(items)
    
    def get_save_path(self, filename: str) -> str:
        """获取保存文件的完整路径"""
        return os.path.join(self.save_dir, filename)


class URLHandler:
    """URL处理工具类"""
    
    @staticmethod
    def clean_url(url: str) -> str:
        """清理URL"""
        url = url.strip()
        if url.startswith('http://') or url.startswith('https://'):
            return url
        return f"https://{url}"
    
    @staticmethod
    def extract_domain(url: str) -> str:
        """提取域名"""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """检查URL是否有效"""
        from urllib.parse import urlparse
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    @staticmethod
    def encode_query(query: str) -> str:
        """URL编码查询字符串"""
        from urllib.parse import quote
        return quote(query)
