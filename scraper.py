import os
import sys
import logging
import requests
import asyncio
import time
import random
from tqdm import tqdm
from urllib.parse import urljoin
from colorama import init, Fore, Style
from dotenv import load_dotenv

# 初始化 colorama
init()

# 載入環境變數
load_dotenv()

# 添加工作目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 導入自定義模組
from utils.anti_crawl import AntiCrawl
from utils.parsers import GPUParser
from utils.database import Database

# 取得 logger
logger = logging.getLogger(__name__)

class GPUScraper:
    """GPU 爬蟲主類"""
    
    def __init__(self):
        self.base_url = os.getenv('BASE_URL', 'https://www.techpowerup.com')
        self.anti_crawl = AntiCrawl()
        self.db = Database()
        self.processed_urls = set()  # 用於去重
    
    async def fetch_url(self, url, absolute=True):
        """獲取頁面內容"""
        if not absolute:
            url = urljoin(self.base_url, url)
        
        if url in self.processed_urls:
            logger.info(f"跳過已處理的 URL: {url}")
            return None
        
        for attempt in range(5):  # 嘗試 5 次
            try:
                headers = self.anti_crawl.get_headers()
                logger.info(f"請求 URL: {url}")
                
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                self.anti_crawl.random_delay()
                self.processed_urls.add(url)
                return response.text
            except requests.exceptions.RequestException as e:
                if not self.anti_crawl.handle_retry(attempt):
                    logger.error(f"無法獲取 {url}: {str(e)}")
                    return None
        
        return None
    
    async def scrape_product_list(self):
        """爬取產品列表"""
        url = urljoin(self.base_url, '/gpu-specs/')
        html = await self.fetch_url(url)
        
        if not html:
            logger.error("無法獲取產品列表")
            return []
        
        return GPUParser.parse_product_list(html)
    
    async def scrape_product_detail(self, gpu):
        """爬取產品詳情"""
        html = await self.fetch_url(gpu['url'], absolute=False)
        
        if not html:
            logger.error(f"無法獲取產品詳情: {gpu['name']}")
            return None, None, None
        
        # 解析產品詳情
        product_data, specs_data = GPUParser.parse_product_detail(html, gpu['url'])
        
        # 解析主板部分
        board_data = GPUParser.parse_boards_section(html)
        
        return product_data, specs_data, board_data
    
    async def scrape_review(self, review_url):
        """爬取評測內容"""
        html = await self.fetch_url(review_url, absolute=False)
        
        if not html:
            logger.error(f"無法獲取評測頁面: {review_url}")
            return None
        
        # 解析評測選項
        options = GPUParser.parse_review_options(html)
        review_contents = []
        
        # 爬取每個選項的內容
        for option in options:
            option_url = option['value']
            option_html = await self.fetch_url(option_url, absolute=False)
            
            if option_html:
                content, review_data = GPUParser.parse_review_content(option_html, option['text'])
                review_contents.append({
                    'type': option['text'],
                    'content': content,
                    'data': review_data
                })
        
        return review_contents
    
    async def process_product(self, gpu):
        """處理單個產品"""
        print(f"{Fore.CYAN}正在處理 GPU: {gpu['name']}{Style.RESET_ALL}")
        
        # 爬取詳情
        product_data, specs_data, board_data = await self.scrape_product_detail(gpu)
        
        if not product_data:
            return
        
        # 存入產品資料
        product = await self.db.create_product(product_data)
        product_id = product.F_SeqNo
        
        # 將規格分類並存入
        if specs_data:
            categories = {}
            
            # 先建立所有類別
            for spec in specs_data:
                if spec['category'] not in categories:
                    category = await self.db.create_spec_category(spec['category'])
                    categories[spec['category']] = category.F_ID
            
            # 然後存入規格
            for spec in specs_data:
                await self.db.create_spec(
                    product_id,
                    categories[spec['category']],
                    spec['name'],
                    spec['value']
                )
        
        # 處理主板數據
        if board_data:
            for board in board_data:
                # 若主板有評測頁面
                if 'review_url' in board:
                    review_contents = await self.scrape_review(board['review_url'])
                    
                    if review_contents:
                        for content in review_contents:
                            review = await self.db.create_review(
                                product_id,
                                content['type'],
                                content['content'].get('title', ''),
                                content['content'].get('body', '')
                            )
                            
                            # 儲存結構化數據
                            for data_item in content['data']:
                                await self.db.create_review_data(
                                    review.F_SeqNo,
                                    data_item.get('data_type', content['type']),
                                    data_item.get('data_key', ''),
                                    data_item.get('data_value', ''),
                                    data_item.get('data_unit', ''),
                                    data_item.get('product_name', board.get('name', ''))
                                )
    
    async def run(self, limit=None):
        """執行爬蟲"""
        try:
            print(f"{Fore.GREEN}開始爬取 GPU 資料{Style.RESET_ALL}")
            
            # 爬取產品列表
            gpu_list = await self.scrape_product_list()
            
            if not gpu_list:
                logger.error("未找到 GPU 列表")
                return
            
            # 可能限制處理數量（用於測試）
            if limit:
                gpu_list = gpu_list[:limit]
            
            # 使用 tqdm 顯示進度
            for gpu in tqdm(gpu_list, desc="處理 GPU", unit="個"):
                await self.process_product(gpu)
                
                # 額外的隨機延遲，避免被封
                extra_delay = random.uniform(1, 3)
                time.sleep(extra_delay)
            
            print(f"{Fore.GREEN}爬蟲完成！共處理 {len(gpu_list)} 個 GPU{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"爬蟲過程中發生錯誤: {str(e)}")
        finally:
            # 關閉數據庫連接
            await self.db.disconnect()

# 入口點
if __name__ == "__main__":
    try:
        # 解析命令列參數
        import argparse
        parser = argparse.ArgumentParser(description='TechPowerUp GPU 爬蟲')
        parser.add_argument('--limit', type=int, help='限制爬取的 GPU 數量（用於測試）')
        args = parser.parse_args()
        
        # 執行爬蟲
        scraper = GPUScraper()
        asyncio.run(scraper.run(limit=args.limit))
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}使用者中斷爬蟲程序{Style.RESET_ALL}")
        sys.exit(0)