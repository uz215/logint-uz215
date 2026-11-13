#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库定时更新服务
每天固定时间（如9:00和21:00）自动更新知识库
"""

import os
import sys
import time
import schedule
import logging
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('knowledge_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KnowledgeScheduler:
    """知识库定时调度器"""
    
    def __init__(self, update_times=['09:00', '21:00']):
        self.update_times = update_times
        self.last_update_time = None
        self.total_documents = 0
        self.crawled_documents = 0
        self.local_documents = 0
        self.running = False
        
    def get_knowledge_stats(self):
        """获取知识库统计信息"""
        try:
            # 统计本地文档
            local_dir = 'data/local'
            self.local_documents = len([f for f in os.listdir(local_dir) if f.endswith('.md')]) if os.path.exists(local_dir) else 0
            
            # 统计爬取文档
            crawled_dir = 'data/crawled'
            self.crawled_documents = len([f for f in os.listdir(crawled_dir) if f.endswith('.md')]) if os.path.exists(crawled_dir) else 0
            
            self.total_documents = self.local_documents + self.crawled_documents
            
            return {
                'total': self.total_documents,
                'local': self.local_documents,
                'crawled': self.crawled_documents,
                'last_update': self.last_update_time
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return None
    
    def print_stats(self):
        """打印知识库统计信息"""
        stats = self.get_knowledge_stats()
        if stats:
            print("\n" + "=" * 60)
            print("知识库统计信息")
            print("=" * 60)
            print(f"总文档数: {stats['total']:,}")
            print(f"  - 本地文档: {stats['local']:,}")
            print(f"  - 爬取文档: {stats['crawled']:,}")
            print(f"最后更新时间: {stats['last_update']}")
            print("=" * 60 + "\n")
    
    def run_update(self):
        """运行知识库更新"""
        logger.info("=" * 60)
        logger.info(f"开始知识库更新 - {datetime.now()}")
        logger.info("=" * 60)
        
        try:
            # 导入模块
            from logknow import EnhancedCrawler, WhooshIndexer
            
            # 1. 爬取网页知识
            logger.info("步骤1: 爬取网页知识")
            crawler = EnhancedCrawler()
            
            # 爬取多个源
            urls_to_crawl = [
                'https://baike.baidu.com/item/%E6%B5%8B%E4%BA%95%E8%A7%A3%E9%87%8A',
                'https://baike.baidu.com/item/%E5%AE%9A%E7%A9%BA%E5%BA%A6',
                'https://baike.baidu.com/item/%E6%B3%84%E9%80%9A%E7%8E%87',
                'https://baike.baidu.com/item/%E9%98%BF%E5%B0%94%E5%A5%87%E5%85%AC%E5%BC%8F',
                'https://baike.baidu.com/item/%E6%B0%B4%E5%90%AB%E5%9C%BA%E5%9F%BA',
            ]
            
            crawled_count = 0
            for url in urls_to_crawl:
                try:
                    results = crawler.fetch_and_save(url, 'data/crawled', max_depth=1)
                    crawled_count += len(results) if results else 0
                except Exception as e:
                    logger.warning(f"爬取 {url} 失败: {e}")
            
            logger.info(f"爬取完成，新增 {crawled_count} 个文档")
            
            # 2. 重建索引
            logger.info("步骤2: 重建搜索索引")
            indexer = WhooshIndexer()
            indexer.build_index(incremental=True)
            
            # 3. 更新统计
            self.last_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 4. 显示统计
            self.print_stats()
            
            logger.info("=" * 60)
            logger.info("知识库更新完成")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"知识库更新失败: {e}")
            import traceback
            traceback.print_exc()
    
    def start(self):
        """启动定时服务"""
        self.running = True
        
        print("\n" + "=" * 60)
        print("知识库定时更新服务已启动")
        print("=" * 60)
        print(f"更新时间: {', '.join(self.update_times)}")
        print("按 Ctrl+C 停止服务")
        print("=" * 60 + "\n")
        
        # 设置定时任务
        for update_time in self.update_times:
            schedule.every().day.at(update_time).do(self.run_update)
            logger.info(f"已设置定时任务: 每天 {update_time}")
        
        # 立即运行一次更新
        self.run_update()
        
        # 循环执行
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
            self.running = False
    
    def stop(self):
        """停止定时服务"""
        self.running = False
        logger.info("定时服务已停止")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="知识库定时更新服务")
    parser.add_argument('--times', '-t', nargs='+', default=['09:00', '21:00'],
                        help="更新时间，如 '09:00 21:00'")
    parser.add_argument('--once', '-o', action='store_true',
                        help="只运行一次更新")
    parser.add_argument('--stats', '-s', action='store_true',
                        help="只显示统计信息")
    
    args = parser.parse_args()
    
    scheduler = KnowledgeScheduler(update_times=args.times)
    
    if args.stats:
        scheduler.print_stats()
    elif args.once:
        scheduler.run_update()
    else:
        scheduler.start()

if __name__ == '__main__':
    main()