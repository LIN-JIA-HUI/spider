import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

from utils.parsers import GPUParser
from utils.database import Database
from scraper import GPUScraper, AntiCrawl

logger = logging.getLogger(__name__)

class UpdateManager:
    """評測資料更新管理器"""
    
    def __init__(self, scraper, db: Database, state, storage_manager):
        self.scraper = scraper
        self.db = db
        self.state = state
        self.storage_manager = storage_manager
        self.anti_crawl = self.scraper.anti_crawl
        self.base_url = self.scraper.base_url
        self.specs_cache = {}  
        self.html_cache = {}  # 頁面內容快取
        
    async def crawl_review_urls(self):
        """爬取所有評測 URL 並存儲"""
        logger.info("開始爬取評測 URL")
        
        # 爬取產品列表頁面查找評測連結
        url = urljoin(self.base_url, '/gpu-specs/')
        html = await self.scraper.fetch_url(url, check_processed=False)
        
        if not html:
            logger.error("無法獲取產品列表")
            return False
        
        # 獲取產品列表
        gpu_list = GPUParser.parse_product_list(html)
        logger.info(f"找到 {len(gpu_list)} 個 GPU 產品")
        
        # 獲取已有產品的快取
        await self.scraper.setup_product_cache()
        product_cache = self.scraper.product_cache
        
        # 爬取每個產品詳情頁面的評測連結
        total_reviews = 0
        for gpu in gpu_list:
            gpu_url = gpu['url']
            logger.info(f"處理產品 {gpu['name']} 的評測連結")
            
            # 檢查產品是否在快取中
            if gpu['name'] in product_cache:
                product_id = product_cache[gpu['name']]
                
                # 爬取產品詳情頁面
                html = await self.scraper.fetch_url(gpu_url, absolute=False, check_processed=False)
                if not html:
                    logger.error(f"無法獲取產品 {gpu['name']} 的詳情頁面")
                    continue
                
                # 解析主板區域，獲取評測連結
                board_data = GPUParser.parse_boards_section(html)
                
                if board_data:
                    for board in board_data:
                        if 'review_url' in board and board['review_url']:
                            await self.store_review_url(product_id, board.get('name', '未知主板'), board['review_url'])
                            total_reviews += 1
            
            # 休息一下，避免請求過快
            await asyncio.sleep(self.anti_crawl.get_random_delay())
        
        logger.info(f"完成評測 URL 爬取，共處理 {total_reviews} 個評測連結")
        return True
    
    async def store_review_url(self, product_id, board_name, review_url):
        """存儲評測主 URL"""
        try:
            # 先查詢獲取主板ID
            query = """
                SELECT P.F_SeqNo 
                FROM dbo.C_Product P 
                WHERE P.F_Product LIKE ?
            """
            
            def fetch_board_id():
                self.db.cursor.execute(query, (f"%{board_name}%"))
                result = self.db.cursor.fetchone()
                return result[0] if result else None
            
            board_id = await self.db.run_db_query(fetch_board_id)
            
            if not board_id:
                logger.warning(f"找不到名稱為 {board_name} 的主板記錄")
                return False
            # 查詢相關的評測記錄
            query = """
                SELECT R.F_SeqNo, R.F_Main_Review_URL 
                FROM dbo.C_Product_Review R 
                WHERE R.F_Master_ID = ?
            """
            
            def fetch_reviews():
                self.db.cursor.execute(query, (board_id))
                return self.db.cursor.fetchall()
            
            reviews = await self.db.run_db_query(fetch_reviews)
            logger.debug(f"board_id: {board_id}, reviews: {reviews}")
            
            if reviews:
                # 更新現有評測記錄的 URL
                for review_id, existing_url in reviews:
                    # 只在 URL 為空或不同時更新
                    if not existing_url or existing_url != review_url:
                        update_query = """
                            UPDATE dbo.C_Product_Review 
                            SET F_Main_Review_URL = ?, F_UpdateTime = ? 
                            WHERE F_SeqNo = ?
                        """
                        
                        def update_review():
                            self.db.cursor.execute(update_query, (review_url, datetime.now(), review_id))
                            self.db.conn.commit()
                            return True
                        
                        await self.db.run_db_query(update_review)
                        logger.info(f"更新產品 {product_id} 的主板 {board_name} 的評測 URL")
            else:
                logger.warning(f"找不到產品 {product_id} 的主板 {board_name} 的評測記錄")
            
            return True
        except Exception as e:
            logger.error(f"存儲評測 URL 失敗: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def crawl_review_subpages(self):
        """爬取評測子頁面 URL 並同時快取頁面內容"""
        logger.info("開始爬取評測子頁面 URL")
        
        # 獲取所有有主評測 URL 的記錄
        query = """
            SELECT R.F_SeqNo, R.F_Type, R.F_Main_Review_URL 
            FROM dbo.C_Product_Review R 
            WHERE R.F_Main_Review_URL IS NOT NULL AND R.F_Main_Review_URL <> ''
        """
        
        def fetch_reviews():
            self.db.cursor.execute(query)
            return self.db.cursor.fetchall()
        
        reviews = await self.db.run_db_query(fetch_reviews)
        logger.info(f"找到 {len(reviews)} 個有主評測 URL 的記錄")

        # 按主評測 URL 分組，以便一次處理同一 URL 的所有評測記錄
        reviews_by_url = {}
        for review_id, review_type, main_url in reviews:
            if main_url not in reviews_by_url:
                reviews_by_url[main_url] = []
            reviews_by_url[main_url].append((review_id, review_type))
        
        # 依次處理每個唯一的主評測 URL
        for main_url, review_entries in reviews_by_url.items():
            logger.info(f"處理主評測 URL: {main_url}，共 {len(review_entries)} 條記錄")
            
            # 獲取評測頁面內容
            html = await self.scraper.fetch_url(main_url, absolute=False, check_processed=False)
            if not html:
                logger.error(f"無法獲取評測頁面 {main_url}")
                continue
            
            # 將主頁面內容加入快取
            self.html_cache[main_url] = html
            
            # 解析評測選項，獲取所有子頁面 URL
            options = GPUParser.parse_review_options(html)
            logger.info(f"找到 {len(options)} 個子頁面選項")
            
            # 為每個評測記錄找到匹配的選項
            for review_id, review_type in review_entries:
                logger.info(f"處理評測 {review_id}，類型: {review_type}")
                
                # 尋找與評測類型匹配的選項
                matching_options = []
                for option in options:
                    option_text = option.get('text', '').lower()
                    db_type = review_type.lower()
                    
                    # 直接比較字符串
                    if db_type == option_text or db_type in option_text or option_text in db_type:
                        matching_options.append(option)
                        logger.info(f"找到匹配選項: {option_text} -> {option['value']}")
                
                # 如果找到匹配選項，使用最佳匹配（通常是第一個匹配）
                if matching_options:
                    best_match = matching_options[0]
                    page_url = best_match['value']
                    
                    # 更新評測記錄的子頁面 URL
                    update_query = """
                        UPDATE dbo.C_Product_Review 
                        SET F_Page_URL = ?, F_UpdateTime = ? 
                        WHERE F_SeqNo = ?
                    """
                    
                    def update_review():
                        self.db.cursor.execute(update_query, (page_url, datetime.now(), review_id))
                        self.db.conn.commit()
                        return True
                    
                    await self.db.run_db_query(update_review)
                    logger.info(f"更新評測 {review_id} 的子頁面 URL: {page_url}")
                    
                    # 同時獲取子頁面內容並快取
                    page_html = await self.scraper.fetch_url(page_url, absolute=False, check_processed=False)
                    if page_html:
                        # 將子頁面內容加入快取
                        self.html_cache[page_url] = page_html
                        logger.info(f"已快取子頁面內容: {page_url}")
                else:
                    logger.warning(f"找不到與評測類型 {review_type} 匹配的子頁面")
            
            # 每處理完一個主評測 URL 後休息一下
            await asyncio.sleep(self.anti_crawl.get_random_delay())
        
        logger.info("完成評測子頁面 URL 爬取和內容快取")
        return True
    
    async def update_review(self, review_info):
        """更新單個評測內容"""
        try:
            review_id = review_info['review_id']
            main_url = review_info['main_url']
            product_id = review_info['product_id']
            
            # 獲取評測記錄
            query = """
                SELECT R.F_Type, R.F_Page_URL 
                FROM dbo.C_Product_Review R 
                WHERE R.F_SeqNo = ?
            """
            
            def fetch_review():
                self.db.cursor.execute(query, (review_id,))
                return self.db.cursor.fetchone()
            
            review_data = await self.db.run_db_query(fetch_review)
            
            if not review_data:
                logger.error(f"找不到評測記錄 {review_id}")
                return False
            
            review_type, page_url = review_data
            
            # 如果沒有子頁面 URL，使用主 URL
            url_to_fetch = page_url if page_url else main_url
            
            # 優先從快取獲取頁面內容
            html = None
            if url_to_fetch in self.html_cache:
                html = self.html_cache[url_to_fetch]
                logger.info(f"從快取獲取評測頁面 {url_to_fetch}")
            else:
                # 如果快取中沒有，再從網絡獲取
                html = await self.scraper.fetch_url(url_to_fetch, absolute=False, check_processed=False)
                if html:
                    # 將獲取的內容加入快取
                    self.html_cache[url_to_fetch] = html
                    logger.info(f"從網絡獲取並快取評測頁面 {url_to_fetch}")
            
            if not html:
                logger.error(f"無法獲取評測頁面 {url_to_fetch}")
                return False
            
            # 解析評測內容
            content, review_data, review_specs_data = GPUParser.parse_review_content(html, review_type)
            
            if not content:
                logger.error(f"無法解析評測頁面 {url_to_fetch} 的內容")
                return False
            
            # 更新評測內容
            update_query = """
                UPDATE dbo.C_Product_Review 
                SET F_Desc = ?, F_UpdateTime = ? 
                WHERE F_SeqNo = ?
            """
            
            def update_review_content():
                self.db.cursor.execute(update_query, (content.get('body', ''), datetime.now(), review_id))
                self.db.conn.commit()
                return True
            
            await self.db.run_db_query(update_review_content)
            logger.info(f"更新評測 {review_id} 的內容")
            
            # 如果有規格數據，更新產品規格
            if review_specs_data:
                # 獲取產品 ID
                query = "SELECT F_Master_ID FROM dbo.C_Product_Review WHERE F_SeqNo = ?"
                
                def fetch_product_id():
                    self.db.cursor.execute(query, (review_id,))
                    result = self.db.cursor.fetchone()
                    return result[0] if result else None
                
                board_id = await self.db.run_db_query(fetch_product_id)
                
                if board_id:
                    # 直接更新此評測的規格資料
                    await self.update_specs_for_product(board_id, review_specs_data)
                    logger.info(f"已直接更新產品 {board_id} 的規格資料，包含 {len(review_specs_data)} 個項目")
            
            return True
        except Exception as e:
            logger.error(f"更新評測 {review_info['review_id']} 時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def update_specs_for_product(self, board_id, specs_list):
        """更新特定產品的規格資料，僅更新或插入新的規格項目"""
        try:
            # 組織規格資料按類別和名稱
            specs_by_name = {}
            for spec in specs_list:
                category = spec.get('category')
                name = spec.get('name')
                value = spec.get('value')
                
                if category and name and value is not None:
                    # 使用類別+名稱作為唯一識別符
                    key = f"{category}|{name}"
                    specs_by_name[key] = {
                        'category': category,
                        'name': name,
                        'value': value
                    }
            
            # 獲取所有相關類別
            categories = list(set(spec.get('category') for spec in specs_list if spec.get('category')))
            
            # 獲取現有的規格數據
            existing_specs = {}
            if categories:
                # 構建查詢
                placeholders = ', '.join(['?'] * len(categories))
                select_query = f"""
                    SELECT F.F_Name as Category, S.F_Name, S.F_Value, S.F_SeqNo 
                    FROM dbo.C_Specs_Database S
                    JOIN dbo.S_Flag F ON S.F_Type = F.F_ID
                    WHERE S.F_Master_Table = 'C_Product' 
                    AND S.F_Master_ID = ? 
                    AND F.F_Name IN ({placeholders})
                """
                
                def fetch_existing_specs():
                    params = [board_id] + categories
                    self.db.cursor.execute(select_query, params)
                    return self.db.cursor.fetchall()
                
                existing_data = await self.db.run_db_query(fetch_existing_specs)
                
                # 組織現有規格為字典，鍵為類別|名稱
                for category, name, value, seq_no in existing_data:
                    key = f"{category}|{name}"
                    existing_specs[key] = {
                        'category': category,
                        'name': name,
                        'value': value,
                        'seq_no': seq_no
                    }
                
            # 1. 更新現有項目
            update_count = 0
            for key, spec in specs_by_name.items():
                if key in existing_specs and existing_specs[key]['value'] != spec['value']:
                    # 僅當值有變化時更新
                    update_query = """
                        UPDATE dbo.C_Specs_Database 
                        SET F_Value = ?, F_UpdateTime = ? 
                        WHERE F_SeqNo = ?
                    """
                    
                    def update_spec():
                        self.db.cursor.execute(update_query, (
                            spec['value'], 
                            datetime.now(), 
                            existing_specs[key]['seq_no']
                        ))
                        self.db.conn.commit()
                        return True
                    
                    await self.db.run_db_query(update_spec)
                    update_count += 1
            
            # 2. 插入新項目（不存在於現有規格中的項目）
            new_specs = []
            for key, spec in specs_by_name.items():
                if key not in existing_specs:
                    new_specs.append(spec)
            
            # 使用現有的存儲管理器添加新規格
            if new_specs:
                await self.storage_manager._store_all_specs(board_id, new_specs)
                
            logger.info(f"更新產品 {board_id} 的規格資料：更新 {update_count} 項，新增 {len(new_specs)} 項")
            
            return True
        except Exception as e:
            logger.error(f"更新產品 {board_id} 的規格資料時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False  
        
    async def full_update(self):
        """執行全部更新"""
        logger.info("開始執行全部評測更新")
        
        # 1. 更新所有評測 URL
        self.state.set_progress(10)
        await self.crawl_review_urls()
        
        # 2. 更新所有子頁面 URL (同時快取頁面內容)
        self.state.set_progress(20)
        await self.crawl_review_subpages()
        
        # 3. 獲取所有評測記錄
        self.state.set_progress(30)
        query = """
            SELECT R.F_SeqNo, R.F_Main_Review_URL, P.F_SeqNo as P_ID, P.F_Product 
            FROM dbo.C_Product_Review R 
            JOIN dbo.C_Product P ON R.F_Master_ID = P.F_SeqNo
            WHERE R.F_Main_Review_URL IS NOT NULL AND R.F_Main_Review_URL <> ''
        """
        
        def fetch_reviews():
            self.db.cursor.execute(query)
            return self.db.cursor.fetchall()
        
        reviews = await self.db.run_db_query(fetch_reviews)
        logger.info(f"找到 {len(reviews)} 個評測記錄進行全量更新")
        
        # 4. 更新每個評測（立即更新規格資料）
        success_count = 0
        for i, (review_id, main_url, product_id, product_name) in enumerate(reviews):
            # 動態更新進度，從30%到85%
            progress = 30 + int(55 * (i / len(reviews))) if reviews else 30
            self.state.set_progress(progress)
            
            review_info = {
                'review_id': review_id,
                'main_url': main_url,
                'product_id': product_id,
                'product_name': product_name
            }
            
            result = await self.update_review(review_info)
            if result:
                success_count += 1
            
            # 休息一下，避免請求過快
            # 使用較短的延遲，因為大部分頁面已經快取
            await asyncio.sleep(self.anti_crawl.get_random_delay() * 0.5)
        
        
        logger.info(f"全量更新完成，成功更新 {success_count}/{len(reviews)} 個評測")
        self.state.set_progress(100)
        return success_count
    
    async def incremental_update(self):
        """執行增量更新，只更新有變化的評測"""
        logger.info("開始執行增量更新")

        # 清空暫存，確保每次增量更新都從乾淨的狀態開始
        self.specs_cache = {}
        self.html_cache = {}  # 清空頁面快取
        
        # 獲取所有有評測URL的記錄
        query = """
            SELECT R.F_SeqNo, R.F_Main_Review_URL, P.F_SeqNo as P_ID, P.F_Product, R.F_UpdateTime 
            FROM dbo.C_Product_Review R 
            JOIN dbo.C_Product P ON R.F_Master_ID = P.F_SeqNo
            WHERE R.F_Main_Review_URL IS NOT NULL AND R.F_Main_Review_URL <> ''
        """
        
        def fetch_reviews():
            self.db.cursor.execute(query)
            return self.db.cursor.fetchall()
        
        reviews = await self.db.run_db_query(fetch_reviews)
        logger.info(f"找到 {len(reviews)} 個有評測URL的記錄進行增量更新檢查")
        
        # 需要更新的評測列表
        reviews_to_update = []
        
        # 檢查每個評測是否需要更新
        for review_id, main_url, product_id, product_name, update_time in reviews:
            try:
                # 獲取評測頁面
                html = await self.scraper.fetch_url(main_url, absolute=False, check_processed=False)
                if not html:
                    logger.warning(f"無法獲取評測頁面 {main_url}")
                    continue
                
                # 將獲取的頁面加入快取
                self.html_cache[main_url] = html
                
                # 解析發布日期
                posted_date = GPUParser.parse_review_posted_date(html)
                logger.info(f"評測 {review_id} 的發布日期: {posted_date}")
                if posted_date:
                    # 將字串日期轉換為datetime對象
                    posted_datetime = datetime.strptime(posted_date, "%Y-%m-%d")
                    
                    # 如果資料庫中沒有更新時間或更新時間早於發布日期，則需要更新
                    if not update_time or update_time.date() < posted_datetime.date():
                        reviews_to_update.append({
                            'review_id': review_id,
                            'main_url': main_url,
                            'product_id': product_id,
                            'product_name': product_name
                        })
                        logger.info(f"評測 {review_id} ({product_name}) 需要更新 - DB: {update_time and update_time.date()}, 網站: {posted_datetime.date()}")
                        
                        # 同時獲取子頁面URL並快取其內容
                        # 獲取評測記錄
                        query = """
                            SELECT R.F_Type, R.F_Page_URL 
                            FROM dbo.C_Product_Review R 
                            WHERE R.F_SeqNo = ?
                        """
                        
                        def fetch_page_url():
                            self.db.cursor.execute(query, (review_id,))
                            return self.db.cursor.fetchone()
                        
                        page_data = await self.db.run_db_query(fetch_page_url)
                        if page_data and page_data[1]:  # 如果有子頁面URL
                            page_url = page_data[1]
                            # 獲取子頁面內容並快取
                            page_html = await self.scraper.fetch_url(page_url, absolute=False, check_processed=False)
                            if page_html:
                                self.html_cache[page_url] = page_html
                                logger.info(f"已快取子頁面內容: {page_url}")
                
                # 休息一下，避免請求過快
                await asyncio.sleep(self.anti_crawl.get_random_delay())
                
            except Exception as e:
                logger.error(f"檢查評測 {review_id} 是否需要更新時出錯: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info(f"找到 {len(reviews_to_update)} 個需要更新的評測")
        
        # 更新每個需要更新的評測
        success_count = 0
        for i, review_info in enumerate(reviews_to_update):
            # 更新進度
            progress = 30 + int(55 * (i / len(reviews_to_update))) if reviews_to_update else 30
            self.state.set_progress(progress)
            
            result = await self.update_review(review_info)
            if result:
                success_count += 1
            
            # 使用較短的延遲，因為大部分頁面已經快取
            await asyncio.sleep(self.anti_crawl.get_random_delay() * 0.5)
        
        logger.info(f"增量更新完成，成功更新 {success_count}/{len(reviews_to_update)} 個評測")
        self.state.set_progress(100)
        return success_count