#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试维基百科爬取（爬虫友好网站）
"""

import os
import sys

# 在导入requests之前先清理代理环境变量
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

import requests
from bs4 import BeautifulSoup
from logIntKnowledge import EnhancedCrawler, DEFAULT_CONFIG

def test_wikipedia_direct():
    """直接测试维基百科访问"""
    print("=" * 60)
    print("直接测试维基百科访问")
    print("=" * 60)
    
    url = "https://zh.wikipedia.org/zh-cn/%E6%B5%8B%E4%BA%95"
    
    try:
        response = requests.get(url, timeout=30)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "Untitled"
            print(f"页面标题: {title}")
            
            # 提取内容
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if content_div:
                paragraphs = content_div.find_all('p')
                print(f"找到 {len(paragraphs)} 个段落")
                if paragraphs:
                    print(f"第一段内容预览:\n{paragraphs[0].get_text()[:300]}...")
            return True
        else:
            print(f"访问失败，状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"访问失败: {e}")
        return False

def test_crawler_wikipedia():
    """测试爬虫爬取维基百科"""
    print("\n" + "=" * 60)
    print("测试EnhancedCrawler爬取维基百科")
    print("=" * 60)
    
    custom_config = DEFAULT_CONFIG["crawler"].copy()
    custom_config["proxy_enabled"] = False
    custom_config["max_pages"] = 3
    custom_config["max_workers"] = 1
    custom_config["request_interval"] = 2
    
    crawler = EnhancedCrawler(config=custom_config)
    
    url = "https://zh.wikipedia.org/zh-cn/%E6%B5%8B%E4%BA%95"
    print(f"\n开始爬取: {url}")
    
    try:
        result = crawler.fetch_and_save(url, 'data/crawled', max_depth=1)
        print(f"\n爬取结果:")
        print(f"  爬取页面数: {crawler.crawled_count}")
        print(f"  结果列表长度: {len(result)}")
        
        for i, item in enumerate(result):
            print(f"  [{i+1}] {item['title']}")
            print(f"      URL: {item['url']}")
            print(f"      文件: {item['source']}")
            
            # 显示文件内容
            with open(item['source'], 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"      内容长度: {len(content)} 字符")
                
        return True
    except Exception as e:
        print(f"爬取失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("维基百科爬取测试")
    print("=" * 60)
    
    # 直接测试维基百科
    test_wikipedia_direct()
    
    # 使用爬虫测试
    test_crawler_wikipedia()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
