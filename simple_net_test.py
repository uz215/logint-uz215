#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单网络测试
"""

import os
import sys

# 清理代理环境变量
for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import requests

def test_connection(url, name):
    """测试连接"""
    print(f"测试 {name}: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        response = requests.get(url, headers=headers, timeout=10, proxies={"http": None, "https": None})
        print(f"  ✓ 成功! 状态码: {response.status_code}")
        return True
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("简单网络测试")
    print("=" * 60)
    
    sites = [
        ("http://www.baidu.com", "百度"),
        ("http://www.cnpc.com.cn", "中国石油"),
        ("http://www.163.com", "网易"),
        ("http://www.sina.com.cn", "新浪"),
    ]
    
    print("\n使用 proxies={None, None} (绕过系统代理):")
    for url, name in sites:
        test_connection(url, name)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
