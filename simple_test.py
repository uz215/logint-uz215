#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试爬虫功能
"""

import os
import sys

# 清理代理环境变量
for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import requests

# 测试1: 直接访问百度
print("测试1: 直接访问百度")
try:
    response = requests.get("http://www.baidu.com", timeout=10, proxies={"http": None, "https": None})
    print(f"✓ 成功! 状态码: {response.status_code}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试2: 访问百度百科
print("\n测试2: 访问百度百科")
try:
    response = requests.get("https://baike.baidu.com/item/%E6%B5%8B%E4%BA%95", timeout=10, proxies={"http": None, "https": None})
    print(f"✓ 成功! 状态码: {response.status_code}")
    print(f"标题: {response.text[:500]}")
except Exception as e:
    print(f"✗ 失败: {e}")

print("\n测试完成!")
