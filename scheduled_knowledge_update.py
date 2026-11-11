#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库定时更新脚本
每天自动爬取网页知识并更新索引
"""

import os
import sys
import time
import schedule
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('knowledge_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_knowledge_update():
    """运行知识库更新"""
    logger.info("=" * 60)
    logger.info(f"开始知识库定时更新 - {datetime.now()}")
    logger.info("=" * 60)
    
    try:
        # 导入并运行更新
        from logknow import WellLogKnowledgeBase
        
        kb = WellLogKnowledgeBase()
        
        # 爬取网页知识
        logger.info("开始爬取网页知识...")
        kb.crawl_all_sources(max_pages=50)
        logger.info("网页爬取完成")
        
        # 重建索引
        logger.info("开始重建索引...")
        kb.rebuild_index()
        logger.info("索引重建完成")
        
        # 导出知识总结
        logger.info("开始导出知识总结...")
        kb.export_summary()
        logger.info("知识总结导出完成")
        
        # 统计信息
        stats = kb.get_statistics()
        logger.info(f"知识库统计: {stats}")
        
        logger.info("=" * 60)
        logger.info("知识库定时更新完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"知识库更新失败: {e}")
        import traceback
        traceback.print_exc()

def run_crawl_only():
    """仅运行爬取任务"""
    logger.info(f"开始网页爬取 - {datetime.now()}")
    
    try:
        from logknow import WellLogKnowledgeBase
        kb = WellLogKnowledgeBase()
        kb.crawl_all_sources(max_pages=30)
        logger.info("网页爬取完成")
    except Exception as e:
        logger.error(f"网页爬取失败: {e}")

def run_index_only():
    """仅运行索引更新"""
    logger.info(f"开始索引更新 - {datetime.now()}")
    
    try:
        from logknow import WellLogKnowledgeBase
        kb = WellLogKnowledgeBase()
        kb.rebuild_index()
        logger.info("索引更新完成")
    except Exception as e:
        logger.error(f"索引更新失败: {e}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="知识库定时更新脚本")
    parser.add_argument('--mode', '-m', choices=['once', 'schedule', 'crawl', 'index', 'daily'], 
                        default='once', help="运行模式")
    parser.add_argument('--interval', '-i', type=int, default=12, help="定时更新间隔（小时）")
    
    args = parser.parse_args()
    
    if args.mode == 'once':
        # 运行一次更新
        run_knowledge_update()
        
    elif args.mode == 'schedule':
        # 定时运行（按间隔）
        logger.info(f"启动定时更新服务，每{args.interval}小时运行一次")
        
        # 立即运行一次
        run_knowledge_update()
        
        # 设置定时任务
        schedule.every(args.interval).hours.do(run_knowledge_update)
        
        # 循环执行
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
            
    elif args.mode == 'daily':
        # 每天固定时间运行（10:00 和 15:00）
        logger.info("启动定时更新服务，每天 10:00 和 15:00 自动运行")
        
        # 设置定时任务
        schedule.every().day.at("10:00").do(run_knowledge_update)
        schedule.every().day.at("15:00").do(run_knowledge_update)
        
        logger.info("定时任务已设置：每天 10:00 和 15:00")
        
        # 循环执行
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
            
    elif args.mode == 'crawl':
        # 仅爬取
        run_crawl_only()
        
    elif args.mode == 'index':
        # 仅更新索引
        run_index_only()

if __name__ == '__main__':
    main()