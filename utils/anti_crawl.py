import random
import time
import asyncio
from fake_useragent import UserAgent
import logging
import os
from datetime import datetime

# 獲取 logger 實例，不進行配置
logger = logging.getLogger(__name__)

class AntiCrawl:
    
    def __init__(self):
        self.ua = UserAgent()
        self.min_delay = 30
        self.max_delay = 60
        self.retry_delays = [600, 900, 1200, 1800, 2400, 3600, 4800, 7200, 10800, 14400, 21600, 28800, 43200, 57600, 86400]
        self.max_retries = len(self.retry_delays)
    
    def get_headers(self):
        """生成隨機 User-Agent 和其他頭部信息"""
        # print(f'使用者代理: {self.ua.getEdge}')
        return {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.techpowerup.com/',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'TE': 'Trailers',
        }
    
    def get_random_delay(self):
        """返回一個隨機延遲值，不執行延遲"""
        return random.uniform(self.min_delay, self.max_delay)
    
    def random_delay(self):
        """同步隨機延遲，模擬人類行為"""
        delay = self.get_random_delay()
        logger.info(f"等待 {delay:.2f} 秒...")
        time.sleep(delay)
        return delay
    
    async def random_delay_async(self):
        """非同步隨機延遲，模擬人類行為"""
        delay = self.get_random_delay()
        logger.info(f"等待 {delay:.2f} 秒...")
        await asyncio.sleep(delay)
        return delay
    
    def handle_retry(self, attempt):
        """處理同步重試邏輯"""
        if attempt >= self.max_retries:
            logger.error("達到最大重試次數，放棄請求")
            return False
        
        delay = self.retry_delays[attempt]
        logger.warning(f"請求失敗，{delay} 秒後重試 (嘗試 {attempt+1}/{self.max_retries})")
        time.sleep(delay)
        return True
    
    async def handle_retry_async(self, attempt):
        """處理非同步重試邏輯"""
        if attempt >= self.max_retries:
            logger.error("達到最大重試次數，放棄請求")
            return False
        
        delay = self.retry_delays[attempt]
        logger.warning(f"請求失敗，{delay} 秒後重試 (嘗試 {attempt+1}/{self.max_retries})")
        await asyncio.sleep(delay)
        return True