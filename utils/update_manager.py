import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

from utils.parsers import GPUParser

logger = logging.getLogger(__name__)

class UpdateManager:
    """評測資料更新管理器"""
    
    def __init__(self, scraper, db, state, storage_manager):
        self.scraper = scraper
        self.db = db
        self.state = state
        self.storage_manager = storage_manager
        self.anti_crawl = self.scraper.anti_crawl
        self.base_url = self.scraper.base_url
        
    async def crawl_review_urls(self):
        """爬取所有評測 URL 並存儲"""
        logger.info("開始爬取評測 URL")
        
        # 爬取產品列表頁面查找評測連結
        url = urljoin(self.base_url, '/gpu-specs/')
        html = await self.scraper.fetch_url(url)
        
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
                html = await self.scraper.fetch_url(gpu_url, absolute=False)
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
            # 查詢相關的評測記錄
            query = """
                SELECT R.F_SeqNo, R.F_Main_Review_URL 
                FROM dbo.C_Product_Review R 
                JOIN dbo.C_Product P ON R.F_Master_ID = P.F_SeqNo
                WHERE P.F_SeqNo = ? AND P.F_Product LIKE ?
            """
            
            def fetch_reviews():
                self.db.cursor.execute(query, (product_id, f"%{board_name}%"))
                return self.db.cursor.fetchall()
            
            reviews = await self.db.run_db_query(fetch_reviews)
            
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
        """爬取評測子頁面 URL"""
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
        
        # 處理每個評測
        for review_id, review_type, main_url in reviews:
            logger.info(f"處理評測 {review_id}, 類型: {review_type}, URL: {main_url}")
            
            # 獲取評測頁面內容
            html = await self.scraper.fetch_url(main_url, absolute=False)
            if not html:
                logger.error(f"無法獲取評測頁面 {main_url}")
                continue
            
            # 解析評測選項，獲取匹配類型的子頁面 URL
            options = GPUParser.parse_review_options(html)
            
            # 尋找與評測類型匹配的選項
            matching_option = None
            for option in options:
                option_text = option.get('text', '').lower()
                if self.match_review_type(review_type, option_text):
                    matching_option = option
                    break
            
            if matching_option:
                # 更新評測記錄的子頁面 URL
                update_query = """
                    UPDATE dbo.C_Product_Review 
                    SET F_Page_URL = ?, F_UpdateTime = ? 
                    WHERE F_SeqNo = ?
                """
                
                def update_review():
                    self.db.cursor.execute(update_query, (matching_option['value'], datetime.now(), review_id))
                    self.db.conn.commit()
                    return True
                
                await self.db.run_db_query(update_review)
                logger.info(f"更新評測 {review_id} 的子頁面 URL: {matching_option['value']}")
            else:
                logger.warning(f"找不到與評測類型 {review_type} 匹配的子頁面")
            
            # 休息一下，避免請求過快
            await asyncio.sleep(self.anti_crawl.get_random_delay())
        
        logger.info("完成評測子頁面 URL 爬取")
        return True
    
    def match_review_type(self, db_type, option_text):
        """匹配資料庫中的評測類型與頁面選項"""
        db_type = db_type.lower()
        option_text = option_text.lower()
        
        # 定義匹配規則
        match_rules = {
            'pictures': ['pictures', 'teardown', 'cooler'],
            'temperatures': ['temperatures', 'fan noise', 'noise'],
            'overclocking': ['overclocking', 'power limits'],
            'circuit board': ['circuit', 'pcb', 'board analysis']
        }
        
        # 檢查每個規則
        for key, patterns in match_rules.items():
            if any(pattern in db_type for pattern in patterns):
                return any(pattern in option_text for pattern in patterns)
        
        # 如果沒有明確的規則，嘗試直接匹配
        return db_type in option_text or option_text in db_type
    
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
            
            # 獲取評測頁面內容
            html = await self.scraper.fetch_url(url_to_fetch, absolute=False)
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
                    # 刪除現有規格
                    delete_query = """
                        DELETE FROM dbo.C_Specs_Database 
                        WHERE F_Master_Table = 'C_Product' AND F_Master_ID = ? 
                        AND F_Type IN (SELECT F_ID FROM dbo.S_Flag WHERE F_Name IN ('Physical Properties', 'TDP Compare', 'GPU', 'Memory'))
                    """
                    
                    def delete_specs():
                        self.db.cursor.execute(delete_query, (board_id,))
                        self.db.conn.commit()
                        return True
                    
                    await self.db.run_db_query(delete_specs)
                    logger.info(f"刪除產品 {board_id} 的現有規格")
                    
                    # 添加新規格
                    await self.storage_manager._store_all_specs(board_id, review_specs_data)
                    logger.info(f"添加產品 {board_id} 的新規格")
            
            return True
        except Exception as e:
            logger.error(f"更新評測 {review_info['review_id']} 時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def full_update(self):
        """執行全量更新"""
        logger.info("開始執行全量更新")
        
        # 1. 更新所有評測 URL
        self.state.set_progress(10)
        await self.crawl_review_urls()
        
        # 2. 更新所有子頁面 URL
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
        
        # 4. 更新每個評測
        success_count = 0
        for i, (review_id, main_url, product_id, product_name) in enumerate(reviews):
            # 動態更新進度，從30%到95%
            progress = 30 + int(65 * (i / len(reviews))) if reviews else 30
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
            await asyncio.sleep(self.anti_crawl.get_random_delay())
        
        logger.info(f"全量更新完成，成功更新 {success_count}/{len(reviews)} 個評測")
        return success_count
    async def incremental_update(self):
        """執行增量更新，只更新有變化的評測"""
        logger.info("開始執行增量更新")
        
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
                html = await self.scraper.fetch_url(main_url, absolute=False)
                if not html:
                    logger.warning(f"無法獲取評測頁面 {main_url}")
                    continue
                
                # 解析發布日期
                posted_date = GPUParser.parse_review_posted_date(html)
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
                
                # 休息一下，避免請求過快
                await asyncio.sleep(self.anti_crawl.get_random_delay())
                
            except Exception as e:
                logger.error(f"檢查評測 {review_id} 是否需要更新時出錯: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info(f"找到 {len(reviews_to_update)} 個需要更新的評測")
        
        # 更新每個需要更新的評測
        success_count = 0
        for review_info in reviews_to_update:
            result = await self.update_review(review_info)
            if result:
                success_count += 1
            
            # 休息一下，避免請求過快
            await asyncio.sleep(self.anti_crawl.get_random_delay())
        
        logger.info(f"增量更新完成，成功更新 {success_count}/{len(reviews_to_update)} 個評測")
        return success_count