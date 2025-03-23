import os
import sys
import logging
import aiohttp  # 改用 aiohttp 代替 requests
import asyncio
import time
import random
from tqdm import tqdm
from urllib.parse import urljoin
from colorama import init, Fore, Style
from dotenv import load_dotenv
from datetime import datetime

# 初始化 colorama
init()

# 載入環境變數
load_dotenv()

# 設定默認的 BASE_URL（如果環境變數未設定）
DEFAULT_BASE_URL = 'https://www.techpowerup.com'

# 添加工作目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 導入自定義模組
from utils.anti_crawl import AntiCrawl
from utils.parsers import GPUParser
from utils.database import Database
from utils.state_manager import ScrapeState, StorageManager  # 新增導入

# 設置詳細日誌
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)
log_file = os.path.join(logs_dir, f'scraper_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class GPUScraper:
    """GPU 爬蟲主類"""
    
    def __init__(self):
        self.base_url = os.getenv('BASE_URL', DEFAULT_BASE_URL)
        self.anti_crawl = AntiCrawl()
        self.db = Database()
        self.state = ScrapeState()  # 添加爬蟲狀態管理
        self.storage_manager = StorageManager(self.db, self.state)  # 添加存儲管理器
        self.processed_urls = set()  # 用於去重
        self.session = None  # aiohttp session
        
        # 添加任務佇列
        self.product_queue = asyncio.Queue()  # 產品佇列
        self.board_queue = asyncio.Queue()    # 主板評測佇列
    
    async def setup_session(self):
        """設置 aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            logger.info("建立 HTTP 會話")
    
    async def fetch_url(self, url, absolute=True):
        """非同步獲取頁面內容"""
        await self.setup_session()
        
        if not absolute:
            url = urljoin(self.base_url, url)
        
        if url in self.processed_urls:
            logger.info(f"跳過已處理的 URL: {url}")
            return None
        
        for attempt in range(5):  # 嘗試 5 次
            try:
                headers = self.anti_crawl.get_headers()
                logger.info(f"請求 URL: {url}")
                
                async with self.session.get(url, headers=headers, timeout=30) as response:
                    response.raise_for_status()
                    html = await response.text()
                
                # 使用非同步等待延遲
                await asyncio.sleep(self.anti_crawl.get_random_delay())
                self.processed_urls.add(url)
                return html
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if not await self.anti_crawl.handle_retry_async(attempt):
                    logger.error(f"無法獲取 {url}: {str(e)}")
                    return None
                await asyncio.sleep(1)  # 額外延遲
        
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
    
    async def product_worker(self):
        """處理產品佇列的工作協程"""
        while True:
            try:
                gpu = await self.product_queue.get()
                
                logger.info(f"開始處理產品: {gpu['name']}")
                print(f"{Fore.CYAN}正在處理 GPU: {gpu['name']}{Style.RESET_ALL}")
                
                # 爬取產品詳情
                product_data, specs_data, board_data = await self.scrape_product_detail(gpu)
                
                if not product_data:
                    logger.warning(f"無法獲取產品 {gpu['name']} 的詳情")
                    self.product_queue.task_done()
                    continue
                
                # 存儲產品和規格
                try:
                    product_id = await self.storage_manager.store_product_complete(product_data, specs_data)
                    logger.info(f"成功存儲產品 {gpu['name']} (ID: {product_id}) 和規格")
                    
                    # 處理所有主板
                    if board_data:
                        for board in board_data:
                            try:
                                # 如果主板有自己的URL，爬取詳細規格
                                board_specs = {}
                                if 'url' in board and board['url']:
                                    board_url = board['url']
                                    board_html = await self.fetch_url(board_url, absolute=False)
                                    if board_html:
                                        board_specs = GPUParser.parse_board_details(board_html, board_url)
                                        logger.info(f"成功爬取主板 {board.get('name', '未知主板')} 的詳細規格")
                                
                                # 添加規格到主板數據
                                if board_specs:
                                    board['specs'] = board_specs
                                
                                # 確保有廠商資訊
                                if 'vendor' not in board and 'name' in board:
                                    # 嘗試從名稱中提取廠商
                                    board_name = board['name']
                                    if ' ' in board_name:
                                        board['vendor'] = board_name.split(' ')[0]
                                    else:
                                        board['vendor'] = "Unknown"
                                
                                # 存儲主板基本資料
                                board_id = await self.storage_manager.store_board(product_id, board)
                                
                                # 如果有評測連結，加入評測佇列
                                if board_id and 'review_url' in board and board['review_url']:
                                    await self.board_queue.put({
                                        'product_id': product_id, 
                                        'board_id': board_id,
                                        'board_name': board.get('name', '未知主板'),
                                        'review_url': board['review_url']
                                    })
                                    logger.info(f"將主板 {board.get('name', '未知主板')} 的評測加入佇列")
                            except Exception as e:
                                logger.error(f"處理主板 {board.get('name', '未知主板')} 時發生錯誤: {str(e)}")
                                import traceback
                                logger.error(traceback.format_exc())
                                continue
                except Exception as e:
                    logger.error(f"處理產品 {gpu['name']} 時發生錯誤: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # 標記任務完成
                self.product_queue.task_done()
                logger.info(f"完成處理產品: {gpu['name']}")
                
            except Exception as e:
                logger.error(f"產品工作協程發生錯誤: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.product_queue.task_done()
    
    async def board_worker(self):
        """處理主板評測佇列的工作協程"""
        while True:
            try:
                board_task = await self.board_queue.get()
                
                logger.info(f"開始處理主板評測: {board_task['board_name']}")
                
                # 爬取評測內容
                review_contents = await self.scrape_review(board_task['review_url'])
                
                if review_contents:
                    # 存儲評測資料到主板記錄
                    await self.storage_manager.store_review(
                        board_task['product_id'],  # GPU ID，用於狀態追蹤
                        board_task['board_id'],    # 主板ID，實際關聯評測的對象
                        board_task['board_name'],  # 主板名稱
                        review_contents
                    )
                    logger.info(f"成功存儲主板 {board_task['board_name']} 的評測")
                else:
                    logger.warning(f"無法獲取主板 {board_task['board_name']} 的評測內容")
                
                # 標記任務完成
                self.board_queue.task_done()
                
            except Exception as e:
                logger.error(f"主板評測工作協程發生錯誤: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.board_queue.task_done()
    
    async def run(self, limit=None):
        """執行爬蟲"""
        try:
            print(f"{Fore.GREEN}開始爬取 GPU 資料{Style.RESET_ALL}")
            logger.info("開始執行爬蟲")
            
            # 建立 HTTP 會話
            await self.setup_session()
            
            # 爬取產品列表
            gpu_list = await self.scrape_product_list()
            
            if not gpu_list:
                logger.error("未找到 GPU 列表")
                return
            
            logger.info(f"獲取到 {len(gpu_list)} 個 GPU")
            
            # 可能限制處理數量（用於測試）
            if limit:
                gpu_list = gpu_list[:limit]
                logger.info(f"限制處理數量為 {limit} 個 GPU")
            
            # 將所有產品加入佇列
            for gpu in gpu_list:
                await self.product_queue.put(gpu)
            
            # 啟動工作協程
            product_workers = []
            board_workers = []
            
            # 產品處理工作協程
            for i in range(3):  # 同時處理 3 個產品
                worker = asyncio.create_task(self.product_worker())
                product_workers.append(worker)
                logger.info(f"啟動產品工作協程 #{i+1}")
            
            # 主板評測處理工作協程
            for i in range(3):  # 同時處理 3 個評測
                worker = asyncio.create_task(self.board_worker())
                board_workers.append(worker)
                logger.info(f"啟動主板評測工作協程 #{i+1}")
            
            # 等待產品佇列處理完成
            await self.product_queue.join()
            logger.info("所有產品處理完成")
            
            # 等待主板評測佇列處理完成
            await self.board_queue.join()
            logger.info("所有主板評測處理完成")
            
            # 取消工作協程
            for worker in product_workers + board_workers:
                worker.cancel()
            
            # 輸出統計信息
            stats = self.state.get_stats()
            print(f"{Fore.GREEN}爬蟲完成！共處理 {stats['products']} 個 GPU, {stats['specs']} 條規格, {stats['reviews']} 個評測{Style.RESET_ALL}")
            logger.info(f"爬蟲完成。統計: {stats}")
            
        except Exception as e:
            logger.error(f"爬蟲過程中發生錯誤: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # 關閉 HTTP 會話
            if self.session:
                await self.session.close()
                logger.info("HTTP 會話已關閉")
            
            # 關閉數據庫連接
            await self.db.disconnect()
            logger.info("資料庫連接已關閉")

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
        logger.info("使用者中斷爬蟲程序")
        sys.exit(0)