import os
import sys
import gc
import logging
import aiohttp  # 改用 aiohttp 代替 requests
import asyncio
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urljoin
from colorama import init, Fore, Style
from dotenv import load_dotenv
from datetime import datetime
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, BackgroundTasks
import uvicorn

# 導入自定義模組
from utils.anti_crawl import AntiCrawl
from utils.parsers import GPUParser
from utils.database import Database
from utils.state_manager import ScrapeState, StorageManager

# 初始化 FastAPI 應用
app = FastAPI(title="GPU 爬蟲 API", description="自動化爬取 GPU 相關資訊的 API")

# 初始化 colorama
init()

# 載入環境變數
load_dotenv()

# 設定默認的 BASE_URL（如果環境變數未設定）
DEFAULT_BASE_URL = 'https://www.techpowerup.com'

# 添加工作目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 設置日誌格式
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 僅設置控制台輸出
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# 配置根 logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # 您可以調整日誌級別，如改為 logging.WARNING 減少輸出
root_logger.handlers = []  # 清除任何現有的處理器
root_logger.addHandler(console_handler)

# 獲取該模塊的 logger
logger = logging.getLogger(__name__)

# 添加 API 路由
@app.get("/")
def read_root():
    return {"message": "GPU 爬蟲 API 已啟動"}

@app.get("/run-scraper")
async def run_scraper(background_tasks: BackgroundTasks, mode: str = None):
    """啟動爬蟲的 API 端點，支持不同的運行模式"""
    global is_scraper_running
    
    if is_scraper_running:
        return {
            "success": False,
            "message": "爬蟲已在執行中，請稍後再試"
        }
    
    # 根據模式決定要啟動的任務
    if mode is None:
        # 原始模式 - 完整爬蟲
        background_tasks.add_task(start_scraper)
        return {
            "success": True,
            "message": "爬蟲已在背景啟動，完成後將發送郵件通知"
        }
    elif mode == "full":
        # 全量更新模式
        from utils.update_review import UpdateManager
        background_tasks.add_task(start_full_update)
        return {
            "success": True,
            "message": "全量更新任務已在背景啟動，完成後將發送郵件通知"
        }
    elif mode == "incremental":
        # 增量更新模式
        from utils.update_review import UpdateManager
        background_tasks.add_task(start_incremental_update)
        return {
            "success": True,
            "message": "增量更新任務已在背景啟動，完成後將發送郵件通知"
        }
    else:
        return {
            "success": False,
            "message": "無效的模式參數，有效值：null (原始爬蟲), full (全量更新), incremental (增量更新)"
        }

@app.get("/run-scraper-selected")
async def start_selected_scraper(gpu_name=None):
    """以指定的 GPU 名稱執行爬蟲"""
    global is_scraper_running, last_scrape_result, current_scraper
    
    if is_scraper_running:
        logger.info("爬蟲已在執行，忽略本次請求")
        return
    
    start_time = datetime.now()
    
    try:
        is_scraper_running = True
        logger.info(f"指定 GPU 爬蟲開始執行: {start_time.isoformat()}")
        
        # 初始化爬蟲
        scraper = GPUScraper()
        current_scraper = scraper  # 保存引用以便檢查狀態
        
        # 執行選擇性爬蟲
        await scraper.run_selected(gpu_name)
        
        # 獲取爬蟲統計結果
        stats = scraper.state.get_stats()
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 更新全局變量，保存結果
        last_scrape_result = {
            "mode": "selected_gpu",
            "gpu_name": gpu_name,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "stats": {
                "products": stats['products'],
                "specs": stats['specs'],
                "reviews": stats['reviews'],
                "elapsed_time": round(duration, 2)
            },
            "success": True
        }
        
        logger.info(f"指定 GPU 爬蟲完成: {end_time.isoformat()}, 耗時: {duration}秒")
        
    except Exception as e:
        logger.error(f"指定 GPU 爬蟲執行錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 記錄錯誤信息
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        last_scrape_result = {
            "mode": "selected_gpu",
            "gpu_name": gpu_name,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "error": str(e),
            "success": False
        }
        
    finally:
        is_scraper_running = False

async def run_scraper_selected(background_tasks: BackgroundTasks, gpu_name: str = None):
    """啟動爬蟲並只爬取指定的 GPU"""
    global is_scraper_running
    
    if is_scraper_running:
        return {
            "success": False,
            "message": "爬蟲已在執行中，請稍後再試"
        }
    
    # 啟動帶有 GPU 名稱參數的背景任務
    background_tasks.add_task(start_selected_scraper, gpu_name)
    
    return {
        "success": True,
        "message": f"已開始爬取 GPU: {gpu_name if gpu_name else '全部'}，完成後將發送通知"
    }
    
@app.get("/status")
async def get_status():
    """獲取爬蟲狀態和最近一次結果的 API 端點"""
    global is_scraper_running, last_scrape_result, current_scraper
    
    status = {
        "is_running": is_scraper_running,
        "last_result": last_scrape_result
    }
    
    # 如果當前有正在運行的爬蟲，獲取其詳細狀態
    if is_scraper_running and 'current_scraper' in globals() and current_scraper:
        try:
            current_state = current_scraper.state.get_status()
            status["current_task"] = current_state
        except Exception as e:
            logger.error(f"獲取當前狀態時出錯: {str(e)}")
    
    return status

# 全局變數用於追蹤爬蟲狀態和結果
is_scraper_running = False
last_scrape_result = None

# 發送郵件函數
def send_email(subject, body, recipients=None):
    """發送郵件通知"""
    # 從環境變數獲取郵件設置
    sender_email = "DAD Center <DADCenter@msi.com.tw>"
    smtp_server = "172.16.0.10"
    smtp_port = "25"
    
    # 如果未提供收件人，從環境變數獲取
    if not recipients:
        recipients_str = "dad_service@msi.com.tw"
        recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
    
    # 檢查必要參數
    if not smtp_server or not sender_email or not recipients:
        logger.error("郵件設置不完整，無法發送郵件通知")
        return False
    
    # 創建郵件
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.send_message(msg)
        server.quit()
        logger.info(f"郵件已成功發送給 {recipients}")
        return True
    except Exception as e:
        logger.error(f"發送郵件時出錯: {str(e)}")
        return False

# 背景任務執行爬蟲
async def start_scraper():
    global is_scraper_running, last_scrape_result
    if is_scraper_running:
        logger.info("爬蟲已在執行，忽略本次請求")
        return
    
    start_time = datetime.now()
    
    try:
        is_scraper_running = True
        logger.info(f"爬蟲開始執行: {start_time.isoformat()}")
        
        scraper = GPUScraper()
        await scraper.run()
        
        # 獲取爬蟲統計結果
        stats = scraper.state.get_stats()
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 更新全局變量，保存結果
        last_scrape_result = {
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "stats": {
                "products": stats['products'],
                "specs": stats['specs'],
                "reviews": stats['reviews'],
                "elapsed_time": round(stats['elapsed_time'], 2)
            },
            "success": True
        }
        
        logger.info(f"爬蟲完成: {end_time.isoformat()}, 耗時: {duration}秒")
        
        # 發送郵件通知
        email_subject = "GPU 爬蟲完成通知"
        email_body = f"""爬蟲已完成！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
完成時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

統計信息:
- 共處理 {stats['products']} 個 GPU
- 共處理 {stats['specs']} 條規格
- 共處理 {stats['reviews']} 個評測

此郵件由自動系統發送，請勿回覆。"""
        
        send_email(email_subject, email_body)
        
    except Exception as e:
        logger.error(f"爬蟲執行錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 記錄錯誤信息
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        last_scrape_result = {
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "error": str(e),
            "success": False
        }
        
        # 發送錯誤通知郵件
        email_subject = "GPU 爬蟲執行失敗通知"
        email_body = f"""爬蟲執行失敗！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
失敗時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

錯誤信息: {str(e)}

此郵件由自動系統發送，請勿回覆。"""
        
        send_email(email_subject, email_body)
    finally:
        is_scraper_running = False


# 全量更新背景任務
async def start_full_update():
    global is_scraper_running, last_scrape_result, current_scraper
    if is_scraper_running:
        logger.info("爬蟲已在執行，忽略本次請求")
        return
    
    start_time = datetime.now()
    
    try:
        is_scraper_running = True
        logger.info(f"全部評測更新開始執行: {start_time.isoformat()}")
        
        # 初始化爬蟲和更新管理器
        scraper = GPUScraper()
        from utils.update_review import UpdateManager
        update_manager = UpdateManager(scraper, scraper.db, scraper.state, scraper.storage_manager)
        
        # 設置狀態
        scraper.state.set_running(True)
        scraper.state.set_task_info("全量更新")
        scraper.state.set_progress(0)

        # 執行全量更新
        update_count = await update_manager.full_update()

        # 完成後更新狀態
        scraper.state.set_running(False)
        scraper.state.set_progress(100)
        scraper.state.set_task_result("成功")
        scraper.state.set_last_update_time(datetime.now())
        scraper.state.set_last_update_count(update_count)
        
        # 獲取爬蟲統計結果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 更新全局變量，保存結果
        last_scrape_result = {
            "mode": "full_update",
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "stats": {
                "updated_reviews": update_count,
                "elapsed_time": round(duration, 2)
            },
            "success": True
        }
        
        logger.info(f"全部評測更新完成: {end_time.isoformat()}, 耗時: {duration}秒, 更新了 {update_count} 個評測")
        
        # 發送郵件通知
        email_subject = "GPU 爬蟲評測更新完成通知"
        email_body = f"""評測更新已完成！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
完成時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

統計信息:
- 共更新 {update_count} 個評測

此郵件由自動系統發送，請勿回覆。"""
        
        send_email(email_subject, email_body)
        
    except Exception as e:
        logger.error(f"評測更新執行錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 記錄錯誤信息
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        last_scrape_result = {
            "mode": "full_update",
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "error": str(e),
            "success": False
        }
        
        
        # 發送錯誤通知郵件
        email_subject = "GPU 爬蟲評測更新失敗通知"
        email_body = f"""評測更新執行失敗！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
失敗時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

錯誤信息: {str(e)}

此郵件由自動系統發送，請勿回覆。"""
        
        send_email(email_subject, email_body)
    finally:
        is_scraper_running = False

# 增量更新背景任務
async def start_incremental_update():
    global is_scraper_running, last_scrape_result
    if is_scraper_running:
        logger.info("爬蟲已在執行，忽略本次請求")
        return
    
    start_time = datetime.now()
    
    try:
        is_scraper_running = True
        logger.info(f"增量更新開始執行: {start_time.isoformat()}")
        
        # 初始化爬蟲和更新管理器
        scraper = GPUScraper()
        from utils.update_review import UpdateManager
        update_manager = UpdateManager(scraper, scraper.db, scraper.state, scraper.storage_manager)
        
        # 執行增量更新
        update_count = await update_manager.incremental_update()
        
        # 獲取爬蟲統計結果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 更新全局變量，保存結果
        last_scrape_result = {
            "mode": "incremental_update", 
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "stats": {
                "updated_reviews": update_count,
                "elapsed_time": round(duration, 2)
            },
            "success": True
        }
        
        logger.info(f"增量更新完成: {end_time.isoformat()}, 耗時: {duration}秒, 更新了 {update_count} 個評測")
        
        # 發送郵件通知
        email_subject = "GPU 爬蟲增量更新完成通知"
        email_body = f"""增量更新已完成！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
完成時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

統計信息:
- 共更新 {update_count} 個評測

此郵件由自動系統發送，請勿回覆。"""
        
        # send_email(email_subject, email_body)
        
    except Exception as e:
        logger.error(f"增量更新執行錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 記錄錯誤信息
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        last_scrape_result = {
            "mode": "incremental_update",
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "error": str(e),
            "success": False
        }
        
        # 發送錯誤通知郵件
        email_subject = "GPU 爬蟲增量更新失敗通知"
        email_body = f"""增量更新執行失敗！

開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
失敗時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
總耗時: {round(duration, 2)}秒

錯誤信息: {str(e)}

此郵件由自動系統發送，請勿回覆。"""
        
        # send_email(email_subject, email_body)
    finally:
        is_scraper_running = False


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
    
    async def fetch_url(self, url, absolute=True, check_processed=True):
        """非同步獲取頁面內容"""
        await self.setup_session()
        
        if not absolute:
            url = urljoin(self.base_url, url)
        
        if check_processed and url in self.processed_urls:
            logger.info(f"跳過已處理的 URL: {url}")
            return None
        
        for attempt in range(15):  # 嘗試 5 次
            try:
                headers = self.anti_crawl.get_headers()
                logger.info(f"請求 URL: {url}")
                
                async with self.session.get(url, headers=headers, timeout=200) as response:
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
        # print(f'product_data: {product_data}')
        # print(f'specs_data: {specs_data}')

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
                content, review_data, specs_data = GPUParser.parse_review_content(option_html, option['text'])
                review_contents.append({
                    'type': option['text'],
                    'content': content,
                    'data': review_data,
                    'specs_data': specs_data
                })
        
        return review_contents
    async def setup_product_cache(self):
        """建立產品名稱快取，使用通用方法處理廠商名稱"""
        self.product_cache = {}  # 格式: {簡化名稱: ID}
        
        # 查詢所有已存在的產品
        query = "SELECT F_SeqNo, F_Product FROM dbo.C_Product"
        
        def fetch_products():
            self.db.cursor.execute(query)
            return self.db.cursor.fetchall()
        
        products = await self.db.run_db_query(fetch_products)
        
        # 處理每個產品名稱，建立映射
        for product_id, product_name in products:
            # 存儲原始完整名稱
            self.product_cache[product_name] = product_id
            
            # 通用方法：去掉第一個空格前的部分（廠商名）
            if ' ' in product_name:
                simplified_name = product_name.split(' ', 1)[1]
                self.product_cache[simplified_name] = product_id
                logger.debug(f"產品映射: '{product_name}' → '{simplified_name}' (ID: {product_id})")
        
        logger.info(f"已建立產品快取，包含 {len(products)} 個產品，總映射數量: {len(self.product_cache)}")
        return self.product_cache
    
    async def product_worker(self):
        """處理產品佇列的工作協程"""
         # 確保產品快取已建立
        if not hasattr(self, 'product_cache'):
            await self.setup_product_cache()

        while True:
            try:
                gpu = await self.product_queue.get()
                product_name = gpu['name']
                
                logger.info(f"開始處理產品: {gpu['name']}")
                print(f"{Fore.CYAN}正在處理 GPU: {gpu['name']}{Style.RESET_ALL}")

                # 檢查方案: 直接檢查產品名稱是否在快取中
                if product_name in self.product_cache:
                    product_id = self.product_cache[product_name]
                    logger.info(f"產品 '{product_name}' 已存在 (ID: {product_id})，跳過處理")
                    # print(f"{Fore.YELLOW}產品 '{product_name}' 已存在，跳過處理{Style.RESET_ALL}")
                    self.product_queue.task_done()
                    continue

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
                                        board_specs = GPUParser.parse_product_detail(board_html, board_url)
                                        logger.info(f"成功爬取主板 {board.get('name', '未知主板')} 的詳細規格")
                                
                                # 添加規格到主板數據
                                if board_specs:
                                    board['specs'] = board_specs

                                # print(f'board: {board}')

                                # 確保有廠商資訊
                                if 'vendor' not in board and 'name' in board:
                                    # 嘗試從名稱中提取廠商
                                    board_name = board['name']
                                    if ' ' in board_name:
                                        board['vendor'] = board_name.split(' ')[0]
                                    else:
                                        board['vendor'] = "Unknown"
                                
                               

                                product_data = convert_to_product_data(board)
                                specs_data = convert_to_specs_data(board)
                                # 存儲主板基本資料
                                board_id = await self.storage_manager.store_product_complete(product_data,specs_data)
                                
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
                
                gc.collect()  # 強制垃圾回收
                logger.info(f"已強制進行垃圾回收，完成處理產品: {gpu['name']}")
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
                
                gc.collect()  # 強制垃圾回收
                logger.info(f"已強制進行垃圾回收，完成處理主板評測: {board_task['board_name']}")
                # 標記任務完成
                self.board_queue.task_done()
                
            except Exception as e:
                logger.error(f"主板評測工作協程發生錯誤: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.board_queue.task_done()
    
    async def display_gpu_menu(self, gpu_list):
        """顯示 GPU 選單並獲取用戶選擇"""
        print(f"\n{Fore.CYAN}=== GPU 列表 ==={Style.RESET_ALL}")
        
        
        while True:
            
            # 清空螢幕
            os.system('cls' if os.name == 'nt' else 'clear')
            sort_gpu_list = sorted(gpu_list, key=lambda x: x['name'])
            gpu_list = sort_gpu_list

            # 顯示當前頁的 GPU
            for i, gpu in enumerate(gpu_list,start=1):
                print(f"{Fore.GREEN}{i}. {gpu['name']}{Style.RESET_ALL}")
            

            # 提示用戶輸入
            choice = input(f"\n{Fore.CYAN}請輸入選項編號或導航命令（留空以選擇所有 GPU）: {Style.RESET_ALL}").lower()
            
            # 如果輸入為空，返回所有 GPU
            if choice.strip() == "":
                return gpu_list


            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(gpu_list):
                    return gpu_list[idx-1]
                else:
                    print(f"{Fore.RED}無效的選擇{Style.RESET_ALL}")
                    input("按 Enter 繼續...")

    async def run_selected(self, gpu_name=None):
        """執行爬蟲，只處理特定 GPU"""
        try:
            print(f"{Fore.GREEN}開始爬取指定 GPU: {gpu_name}{Style.RESET_ALL}")
            logger.info(f"開始執行指定 GPU 爬蟲: {gpu_name}")
            
            # 建立 HTTP 會話
            await self.setup_session()
            
            # 爬取產品列表
            gpu_list = await self.scrape_product_list()
            
            if not gpu_list:
                logger.error("未找到 GPU 列表")
                return
            
            logger.info(f"獲取到 {len(gpu_list)} 個 GPU")
            
            # 篩選出完全匹配的 GPU（不區分大小寫但需完全匹配）
            if gpu_name:
                gpu_name_lower = gpu_name.lower().strip()
                filtered_list = [gpu for gpu in gpu_list if gpu['name'].lower().strip() == gpu_name_lower]
                
                # 如果找不到完全匹配的，可以顯示提示
                if not filtered_list:
                    logger.error(f"未找到完全匹配 '{gpu_name}' 的 GPU")
                    logger.info("可能的匹配有:")
                    for gpu in gpu_list:
                        if gpu_name_lower in gpu['name'].lower():
                            logger.info(f"- {gpu['name']}")
                    return
                
                gpu_list = filtered_list
                
                logger.info(f"篩選後保留 {len(gpu_list)} 個 GPU")
                for gpu in gpu_list:
                    logger.info(f"將處理: {gpu['name']}")
                    
            # 將篩選後的 GPU 加入佇列
            for gpu in gpu_list:
                await self.product_queue.put(gpu)
            
            # 啟動工作協程
            product_workers = []
            board_workers = []
            
            # 產品處理工作協程
            worker = asyncio.create_task(self.product_worker())
            product_workers.append(worker)
            logger.info("啟動產品工作協程")
            
            # 主板評測處理工作協程
            for i in range(3):  # 同時處理 3 個評測
                worker = asyncio.create_task(self.board_worker())
                board_workers.append(worker)
                logger.info(f"啟動主板評測工作協程 #{i+1}")
            
            # 等待產品佇列處理完成
            await self.product_queue.join()
            logger.info("產品處理完成")
            
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

            # # 可能限制處理數量（用於測試）
            # if limit:
            #     gpu_list = gpu_list[:limit]
            #     logger.info(f"限制處理數量為 {limit} 個 GPU")
            
            # # 顯示選單並獲取用戶選擇
            # selected_gpu = await self.display_gpu_menu(gpu_list)
            # if not selected_gpu:
            #     print(f"{Fore.YELLOW}已取消操作{Style.RESET_ALL}")
            #     return
            
            # print(f"\n{Fore.GREEN}已選擇: {selected_gpu['name']}{Style.RESET_ALL}")
            
            # # 將選中的 GPU 加入佇列
            # if isinstance(selected_gpu, list):  # 如果是列表(多個GPU)
            #     for gpu in selected_gpu:
            #         await self.product_queue.put(gpu)
            # else:  # 如果是字典(單個GPU)
            #     await self.product_queue.put(selected_gpu)
            # 將所有 GPU 加入佇列
            for gpu in gpu_list:
                await self.product_queue.put(gpu)
            
            # 啟動工作協程
            product_workers = []
            board_workers = []
            
            # # 產品處理工作協程（只需要一個，因為只處理一個 GPU）
            # worker = asyncio.create_task(self.product_worker())
            # product_workers.append(worker)
            # logger.info("啟動產品工作協程")

            # 產品處理工作協程
            worker = asyncio.create_task(self.product_worker())
            product_workers.append(worker)
            logger.info(f"啟動單一產品工作協程")
            
            # 主板評測處理工作協程
            for i in range(3):  # 同時處理 3 個評測
                worker = asyncio.create_task(self.board_worker())
                board_workers.append(worker)
                logger.info(f"啟動主板評測工作協程 #{i+1}")
            
            # 等待產品佇列處理完成
            await self.product_queue.join()
            logger.info("產品處理完成")
            
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

def convert_to_product_data(board):
    # 取出基本資訊
    base_info, specs_list = board['specs']

    # 整理規格資訊
    description_parts = []
    for spec in specs_list:
        description_parts.append(f"{spec['name']}: {spec['value']}")

    # 組合 `product_data`
    product_data = {
        **base_info,  # 直接合併基本資訊
        'F_Desc': ' | '.join(description_parts)  # 規格轉成描述
    }
    return product_data

def convert_to_specs_data(board):
    _, specs_list = board['specs']  # 取得規格清單
    return specs_list  # 直接回傳規格列表

# 入口點
if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8104)
